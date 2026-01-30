import os
from datetime import datetime
from collections import defaultdict

# ==============================
# PARAMÈTRES
# ==============================
OBS_FILE = "obs/TEST_IGN_20-25.obs"
STATIONS_DIR = "stations/Stations_FDSN"
OUTPUT_FILE = "stations/GTSRCE_IGN_RENASS.txt"
COORD_TOL_DEG = 0.0002  # tolérance angulaire en degrés (~10 m)
# Voies autorisées (2 premières lettres du channel)
ALLOWED_CHANNEL_PREFIXES = {"HH", "HN", "EH", "EN","SH"}
# Location codes autorisés
ALLOWED_LOCATION_CODES = {"00", ""}


# ==============================
# A. LECTURE DU FICHIER OBS
# ==============================
station_times = defaultdict(list)

current_event_time = None
reported_stations = set()

with open(OBS_FILE, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        # Ligne événement
        if line.startswith("#"):
            parts = line.split()
            # # YYYY MM DD HH MM SS.s LAT LON DEPTH
            year, month, day = map(int, parts[1:4])
            hour, minute = map(int, parts[4:6])
            second = float(parts[6])
            current_event_time = datetime(
                year, month, day, hour, minute, int(second),
                int((second % 1) * 1e6)
            )
            continue

        # Ligne station
        parts = line.split()
        station = parts[0]
        date_str = parts[6]       # YYYYMMDD
        time_str = parts[7]       # HHMM
        sec = float(parts[8])

        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        hour = int(time_str[:2])
        minute = int(time_str[2:4])

        arrival_time = datetime(
            year, month, day, hour, minute,
            int(sec), int((sec % 1) * 1e6)
        )

        station_times[station].append(arrival_time)

# ==============================
# B. LECTURE DES FICHIERS STATIONS
# ==============================
stations_db = defaultdict(list)


for fname in os.listdir(STATIONS_DIR):
    if not fname.endswith(".txt"):
        continue

    with open(os.path.join(STATIONS_DIR, fname), "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.strip().split("|")
            network = parts[0]
            station = parts[1]
            location = parts[2]
            channel = parts[3]
            lat = float(parts[4])
            lon = float(parts[5])
            elev_km = float(parts[6]) / 1000.0


            # Filtrage location code
            if location not in ALLOWED_LOCATION_CODES:
                continue

            # Filtrage type de voie (HH, EH, etc.)
            channel_prefix = channel[:2]
            if channel_prefix not in ALLOWED_CHANNEL_PREFIXES:
                continue
                
            start = datetime.fromisoformat(parts[15])
            end = datetime.fromisoformat(parts[16])

            stations_db[station].append({
                "network": network,
                "lat": lat,
                "lon": lon,
                "elev": elev_km,
                "start": start,
                "end": end,
                "raw": line
            })

# ==============================
# C. ASSOCIATION STATIONS / TEMPS
# ==============================
with open(OUTPUT_FILE, "w") as out:
    for station, times in station_times.items():

        valid_entries = []

        for t in times:
            for entry in stations_db.get(station, []):
                if entry["start"] <= t <= entry["end"]:
                    valid_entries.append(entry)

        if not valid_entries:
            print(f"[WARN] Aucune coordonnée valide pour {station}")
            continue

        # Vérification cohérence coordonnées
        # Coordonnée de référence (première entrée valide)
        ref = valid_entries[0]
        ref_lat = ref["lat"]
        ref_lon = ref["lon"]
        ref_elev = ref["elev"]

        incoherent = []

        for e in valid_entries[1:]:
            dlat = abs(e["lat"] - ref_lat)
            dlon = abs(e["lon"] - ref_lon)

            if dlat > COORD_TOL_DEG or dlon > COORD_TOL_DEG:
                incoherent.append(e)

        if incoherent:
            if station not in reported_stations:
                print(f"\n[ERREUR COORDONNÉES] Station {station}")
                print("Coordonnées incompatibles (> tolérance) :")
                print(ref["raw"])
                for e in incoherent:
                    print(e["raw"])

                reported_stations.add(station)

            continue

        # Coordonnées moyennées (option propre)
        lat = sum(e["lat"] for e in valid_entries) / len(valid_entries)
        lon = sum(e["lon"] for e in valid_entries) / len(valid_entries)
        elev = sum(e["elev"] for e in valid_entries) / len(valid_entries)

        out.write(
            f"GTSRCE {station} LATLON {lat:.6f} {lon:.6f} 0.0 {elev:.3f}\n"
        )

print(f"\nFichier écrit : {OUTPUT_FILE}")
