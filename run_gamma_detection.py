#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de détection sismique robuste :
- Lecture FDSN ou SDS
- Détection avec PhaseNet
- Association événements avec GaMMA
- Écriture fichiers NLL / GTSRCE / picks
- Gestion robuste des erreurs (le script continue toujours)
"""

import os
import obspy
from obspy.clients.fdsn import Client
from obspy import UTCDateTime, Stream
from obspy.core.inventory import Inventory, Network, Station, Channel, Site
from obspy.clients.fdsn.header import FDSNNoDataException

from pyproj import CRS, Transformer
import pandas as pd
import numpy as np
import seaborn as sns

from gamma.utils import association
import seisbench.models as sbm
import torch
import time
import traceback

# --- Proxy ---
import seisbench as sb;
sb.use_backup_repository()

# -------------------------------
# -------- CONFIGURATION --------
# -------------------------------

# --- Projection ---
WGS84 = CRS.from_epsg(4326)
LAM93 = CRS.from_epsg(2154)
transformer_to_lam93 = Transformer.from_crs(WGS84, LAM93, always_xy=True)
transformer_to_wgs84 = Transformer.from_crs(LAM93, WGS84, always_xy=True)

# --- Zone d’étude ---
LAT_MIN, LON_MIN = 42.0, -2
LAT_MAX, LON_MAX = 43.3, 3.5

# --- Choix des canaux à conserver ---
CHANNEL_PREFIXES = ("HH", "HN", "EH", "SH")  #

# --- Temps ---
START_TIME = UTCDateTime("2025-10-01T00:00:00")
END_TIME   = UTCDateTime("2025-10-01T12:00:00")
STEP_HOURS = 12  # intervalle horaire

# --- Prétraitement ---
NEW_SAMPLING_RATE = 100.0
FREQMIN, FREQMAX = 1.0, 20.0

# --- Sources ---
DATA_SOURCES = [
    {
        "name": "http://fdsnws.sismologia.ign.es",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_Pyrenees_ES.txt",
        "phasnet_config": {"P_threshold": 0.3, "S_threshold": 0.3, "batch_size": 256},
        "isSDS": False
    },
    {
        "name": "RESIF",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_France_FR.txt",
        "phasnet_config": {"P_threshold": 0.3, "S_threshold": 0.3, "batch_size": 256},
        "isSDS": False
    },
    {
        "name": "RESIF",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_France_RA.txt",
        "phasnet_config": {"P_threshold": 0.3, "S_threshold": 0.3, "batch_size": 256},
        "isSDS": False
    },
    {
        "name": "RESIF",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_France_RD.txt",
        "phasnet_config": {"P_threshold": 0.3, "S_threshold": 0.3, "batch_size": 256},
        "isSDS": False
    },
    {
        "name": "ICGC",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_Pyrenees_CA.txt",
        "phasnet_config": {"P_threshold": 0.3, "S_threshold": 0.3, "batch_size": 256},
        "isSDS": False
    },
    {
        "name": "RASPISHAKE",
        "station_file": "stations/STATIONS_FDSN/FDSNstation_Pyrenees_AM.txt",
        "phasnet_config": {"P_threshold": 0.4, "S_threshold": 0.4, "batch_size": 256},
        "isSDS": False
    },
]

# --- Fichiers de sortie ---
sortieNLL   = "obs/phases.obs" # toutes les phases
GTSRCE      = "stations/GTSRCE.txt"
picks_stat  = "picks/picks.txt"



# --- GaMMA ---
GAMMA_CONFIG = {
    "dims": ["x(km)", "y(km)", "z(km)"],
    "use_dbscan": True,
    "use_amplitude": False,
    "x(km)": (100, 750),
    "y(km)": (6100, 6400),
    "z(km)": (-5, 40),
    "vel": {"p": 5.5, "s": 5.5 / 1.72},
    "method": "BGMM",
    "oversample_factor": 4,
    "dbscan_eps": 25, # temps de fenetre (dist_max/VS = 75/3)
    "dbscan_min_samples": 3,
    "min_picks_per_eq": 7,
    "max_sigma11": 3.0,
    "max_sigma22": 2.0,
    "max_sigma12": 2.0,
}

sns.set_theme(font_scale=1.2)
sns.set_style("ticks")

# -------------------------------
# --------- FUNCTIONS -----------
# -------------------------------

def safe_filter_and_interp(st):
    """Prétraitement robuste avec interpolation avant filtrage."""
    if len(st) == 0:
        return st
    try:
        st.detrend("linear").taper(max_percentage=0.05)
        st.interpolate(sampling_rate=NEW_SAMPLING_RATE, method="linear")
        nyquist = st[0].stats.sampling_rate / 2
        freqmax_adj = min(FREQMAX, 0.99 * nyquist)
        st.filter("bandpass", freqmin=FREQMIN, freqmax=freqmax_adj,
                  corners=4, zerophase=True)
    except Exception as e:
        print(f"⚠️  Erreur filtrage : {e}")
        return Stream()
    return st


def get_inventory_and_stream(client_name, t0, t1, txt_path, sds_root=None):
    """
    Charge un inventaire depuis txt + récupère un stream via FDSN ou SDS.
    Continue même si une station échoue.
    """
    networks_dict = {}
    with open(txt_path, "r") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("|")
            net_code, sta_code, loc_code, chan_code = parts[:4]
            latitude, longitude, elevation = map(float, parts[4:7])
            sample_rate = float(parts[14])
            start_date, end_date = UTCDateTime(parts[15]), UTCDateTime(parts[16])

            # --- filtre géographique et temporel
            if not (LAT_MIN <= latitude <= LAT_MAX and LON_MIN <= longitude <= LON_MAX):
                continue
            if t0 < start_date or t1 > end_date:
                continue

            # --- filtre de type de canal (HH*, HN*, EH*, SH*)
            if not chan_code.startswith(CHANNEL_PREFIXES):
                continue  # <--- on saute les canaux non désirés

            # filtre location
            if loc_code not in ("00", "..", ""):
                continue

            if net_code not in networks_dict:
                networks_dict[net_code] = {}
            if sta_code not in networks_dict[net_code]:
                networks_dict[net_code][sta_code] = Station(
                    code=sta_code, latitude=latitude, longitude=longitude,
                    elevation=elevation, creation_date=start_date,
                    site=Site(name=sta_code), channels=[]
                )

            networks_dict[net_code][sta_code].channels.append(Channel(
                code=chan_code, location_code=loc_code, latitude=latitude,
                longitude=longitude, elevation=elevation, depth=0.0,
                sample_rate=sample_rate, start_date=start_date,
                end_date=end_date
            ))

    inv = Inventory(
        networks=[Network(code=net_code, stations=list(stations.values()))
                  for net_code, stations in networks_dict.items()],
        source=f"Generated from {txt_path}"
    )

    stream = Stream()
    client = None if sds_root else Client(client_name)

    for net in inv:
        for sta in net.stations:
            for chan in sta.channels:
                try:
                    if sds_root:
                        st = Stream()
                        current_day = t0.date
                        while UTCDateTime(current_day) <= t1:
                            year = current_day.year
                            jday = f"{UTCDateTime(current_day).julday:03d}"
                            file_path = os.path.join(
                                sds_root, net.code, sta.code, chan.code, f"{year}.{jday}"
                            )
                            if os.path.exists(file_path):
                                st += obspy.read(file_path)
                            current_day = UTCDateTime(current_day) + 86400
                    else:
                        st = client.get_waveforms(
                            network=net.code, station=sta.code,
                            location=chan.location_code or "", channel=chan.code,
                            starttime=t0, endtime=t1
                        )
                    st = safe_filter_and_interp(st)
                    stream += st
                except FDSNNoDataException:
                    print(f"⚠️  Pas de données : {net.code}.{sta.code}.{chan.code}")
                except Exception as e:
                    print(f"⚠️  Erreur {net.code}.{sta.code}.{chan.code} : {e}")
                    traceback.print_exc()
    return inv, stream

# -------------------------------
# -------- MAIN -----------------
# -------------------------------

if __name__ == "__main__":

    # Suppression si les fichiers existent déjà
    for f in [sortieNLL, GTSRCE, picks_stat]:
        if os.path.exists(f):
            os.remove(f)
            print(f"🗑️  Fichier supprimé : {f}")

    t0global = time.time()

    # --- Device ---
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print("💻 Device utilisé :", device)

    # --- PhaseNet ---
    picker = sbm.PhaseNet.from_pretrained("instance").to(device)

    # --- Fichiers sortie ---
    f_obs = open(sortieNLL, "a")
    f_gts = open(GTSRCE, "a")
    f_pck = open(picks_stat, "a")

    current_time = START_TIME
    while current_time < END_TIME:
        t0boucle = time.time()
        t0, t1 = current_time, current_time + STEP_HOURS * 3600
        print(f"\n⏳ Intervalle {t0} → {t1}")

        all_picks, all_stations = [], []

        for source in DATA_SOURCES:
            name = source["name"]
            cfg = source["phasnet_config"]
            sds_root = source.get("sds_root", None) if source.get("isSDS", False) else None

            print(f"📡 Source {name}...")
            try:
                inv, stream = get_inventory_and_stream(name, t0, t1, source["station_file"], sds_root)
                if len(stream) == 0:
                    print(f"⚠️  Aucun stream pour {name}")
                    continue


                # --- Normalisation du location_code pour le Stream ---
                def normalize_stream_locations(st):
                    for tr in st:
                        # ex: tr.id = 'FR.ATE.00.HHE'
                        parts = tr.id.split(".")
                        if len(parts) == 4:
                            net, sta, loc, chan = parts
                            if loc in ("00", "..", ""):
                                # on peut mettre le loc à HH, HN, etc. selon chan
                                # ici simple: on met loc = chan[:2] (HH, HN, EH, SH)
                                loc = chan[:2]
                            tr.id = f"{net}.{sta}.{loc}.{chan}"
                    return st

                stream = normalize_stream_locations(stream)
                
                picks = picker.classify(
                    stream,
                    batch_size=cfg["batch_size"],
                    P_threshold=cfg["P_threshold"],
                    S_threshold=cfg["S_threshold"]
                ).picks

                if not picks:
                    print(f"⚠️  Aucun pick pour {name}")
                    continue

                pick_df = pd.DataFrame([{
                    "id": p.trace_id,
                    "timestamp": p.peak_time.datetime,
                    "prob": p.peak_value,
                    "type": p.phase.lower()
                } for p in picks])
                all_picks.append(pick_df)
                
                #print(pick_df)
                #print(inv)
                #print(inv[0].stations)
                
                station_df = pd.DataFrame([{
                    "id": f"{net.code}.{sta.code}.{sta.channels[0].code[:2]}",
                    "longitude": sta.longitude,
                    "latitude": sta.latitude,
                    "elevation(m)": sta.elevation
                } for net in inv for sta in net.stations])
                
                station_df["x(km)"], station_df["y(km)"] = zip(*station_df.apply(
                    lambda x: transformer_to_lam93.transform(x["longitude"], x["latitude"]), axis=1
                ))
                station_df["x(km)"] /= 1000
                station_df["y(km)"] /= 1000
                station_df["z(km)"] = -station_df["elevation(m)"] / 1000
                all_stations.append(station_df)

                print(f"✅ {len(pick_df)} picks sur {len(station_df)} stations ({name})")

            except Exception as e:
                print(f"❌ Erreur source {name} : {e}")
                traceback.print_exc()

        if not all_picks:
            print("⚠️  Aucun pick dans cet intervalle.")
            current_time = t1
            continue

        pick_df = pd.concat(all_picks, ignore_index=True)
        station_df = pd.concat(all_stations, ignore_index=True)

        # GAMMA bounds dynamiques
        GAMMA_CONFIG["bfgs_bounds"] = (
            (GAMMA_CONFIG["x(km)"][0]-1, GAMMA_CONFIG["x(km)"][1]+1),
            (GAMMA_CONFIG["y(km)"][0]-1, GAMMA_CONFIG["y(km)"][1]+1),
            (station_df["z(km)"].min()-1, GAMMA_CONFIG["z(km)"][1]+1),
            (None, None)
        )

        try:
            catalogs, assignments = association(pick_df, station_df,
                                                GAMMA_CONFIG, method=GAMMA_CONFIG["method"])
            catalog = pd.DataFrame(catalogs)
            assignments = pd.DataFrame(assignments, columns=["pick_idx", "event_idx", "prob_gamma"])
        except Exception as e:
            print(f"❌  Erreur GAMMA : {e}")
            traceback.print_exc()
            current_time = t1
            continue

        if catalog.empty:
            print("⚠️  Aucun événement détecté.")
            current_time = t1
            continue

        # Conversion coords événements
        catalog["lon"], catalog["lat"] = zip(*catalog.apply(
            lambda row: transformer_to_wgs84.transform(row["x(km)"]*1000, row["y(km)"]*1000), axis=1
        ))

        # --- Écriture fichiers ---
        try:
            for _, event in catalog.iterrows():
                event_idx = event["event_index"]
                origin_time = UTCDateTime(event["time"])
                lat, lon, depth = event["lat"], event["lon"], event["z(km)"]

                f_obs.write(f"# {origin_time.year} {origin_time.month:02d} {origin_time.day:02d} "
                            f"{origin_time.hour:02d} {origin_time.minute:02d} "
                            f"{origin_time.second + origin_time.microsecond/1e6:.3f} "
                            f"{lat:.6f} {lon:.6f} {depth:.3f}\n")

                assigned_picks = assignments[assignments["event_idx"] == event_idx]
                for _, ass in assigned_picks.iterrows():
                    pick = pick_df.iloc[int(ass["pick_idx"])]
                    pick_time = UTCDateTime(pick["timestamp"])
                    #station_id = pick["id"].split(".")[1]
                    station_id = ".".join(pick["id"].split(".")[:3])  # ex: RA.PYMO.HN
                    phase = pick["type"].upper()
                    weight = 0.05 if phase == "P" else 0.15
                    date_str = pick_time.strftime("%Y%m%d")
                    hour_str = f"{pick_time.hour:02d}{pick_time.minute:02d}"
                    seconds = pick_time.second + pick_time.microsecond / 1e6
                    #f_obs.write(f"{station_id:<6} ?    ?    ? {phase:<2} ? {date_str} {hour_str} {seconds:.4f} GAU  {weight:.2f}     -1.00e+00 -1.00e+00 -1.00e+00\n")
                    f_obs.write(f"{station_id:<12} ?    ?    ? {phase:<2} ? {date_str} {hour_str} {seconds:.4f} GAU  {weight:.2f}     -1.00e+00 -1.00e+00 -1.00e+00\n")
                f_obs.write("\n")

            for _, sta in station_df.iterrows():
                #sta_code = sta["id"].split(".")[1]
                sta_code = sta["id"]  # déjà au format NET.STA.CHAN
                lat, lon = sta["latitude"], sta["longitude"]
                elev_km = abs(sta["elevation(m)"]/1000.0)
                #f_gts.write(f"GTSRCE {sta_code} LATLON {lat:.4f} {lon:.4f} 0.0 {elev_km:.3f}\n")
                f_gts.write(f"GTSRCE {sta_code} LATLON {lat:.4f} {lon:.4f} 0.0 {elev_km:.3f}\n")

            for _, ass in assignments.iterrows():
                pick = pick_df.iloc[int(ass["pick_idx"])]
                #sta_code = pick["id"].split(".")[1]
                sta_code = ".".join(pick["id"].split(".")[:3])
                event_id = int(ass["event_idx"])
                phase = pick["type"].upper()
                prob = float(pick["prob"])
                time_str = UTCDateTime(pick["timestamp"]).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                f_pck.write(f"{sta_code} {phase} {time_str} prob={prob:.3f} event={event_id}\n")

            print(f"🎯 {len(catalog)} événements ajoutés")
        except Exception as e:
            print(f"❌  Erreur écriture fichiers : {e}")
            traceback.print_exc()

        current_time = t1
        print(f"⏱️ Intervalle traité en {time.time()-t0boucle:.1f} s")

    # Fermeture fichiers
    f_obs.close()
    f_gts.close()
    f_pck.close()

    # Nettoyage GTSRCE
    with open(GTSRCE, "r") as f:
        lines = sorted(set(f.readlines()))
    with open(GTSRCE, "w") as f:
        f.writelines(lines)
        f.close()
    print(f"\n✅ Nettoyage terminé : {len(lines)} stations uniques dans {GTSRCE}")
    print(f"⏱️ Temps total : {time.time()-t0global:.1f} s")

