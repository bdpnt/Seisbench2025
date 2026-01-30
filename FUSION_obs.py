import math
from datetime import datetime
from typing import List, Tuple




 #============================================================
# UTILITAIRES
# ============================================================

def parse_header_line(line: str):
    """Parse a header line starting with # and return a dict with event info."""
    parts = line[1:].split()
    year, month, day, hour, minute = map(int, parts[:5])
    sec = float(parts[5])
    lat = float(parts[6])
    lon = float(parts[7])
    depth = float(parts[8])

    t0 = datetime(year, month, day, hour, minute, int(sec), int((sec % 1) * 1e6))
    return {
        "datetime": t0,
        "lat": lat,
        "lon": lon,
        "depth": depth,
        "raw": line.rstrip("\n")   # original unchanged text
    }


def haversine(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points géographiques."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


# ============================================================
# LECTURE DES FICHIERS
# ============================================================

def read_bulletin(filename: str):
    """
    Lecture d'un fichier bulletin.
    Retourne une liste d'événements :
        event = { "header": {...}, "picks": [(station, phase, rawline), ...] }
    """
    events = []
    current_event = None

    with open(filename, "r") as f:
        for line in f:
            if not line.strip():
                continue

            if line.startswith("#"):
                # Nouveau séisme
                if current_event:
                    events.append(current_event)
                current_event = {
                    "header": parse_header_line(line),
                    "picks": []
                }
            else:
                # Ligne de station
                station = line[0:5].strip()
                phase = line[19:20].strip()
                current_event["picks"].append((station, phase, line.rstrip("\n")))

        if current_event:
            events.append(current_event)

    return events


# ============================================================
# COMPARAISON DE DEUX SÉISMES
# ============================================================

def events_match(ev1, ev2, max_time_diff, max_dist_km):
    """Retourne True si deux séismes sont similaires."""
    t1 = ev1["header"]["datetime"]
    t2 = ev2["header"]["datetime"]
    dt = abs((t1 - t2).total_seconds())

    if dt > max_time_diff:
        return False

    d = haversine(ev1["header"]["lat"], ev1["header"]["lon"],
                  ev2["header"]["lat"], ev2["header"]["lon"])

    return d <= max_dist_km


# ============================================================
# FUSION
# ============================================================

def merge_picks(primary_event, secondary_event):
    """Fusionne les picks d'un événement, en gardant priorité au fichier prioritaire."""
    out = { (sta, pha): raw for (sta, pha, raw) in primary_event["picks"] }

    for sta, pha, raw in secondary_event["picks"]:
        if (sta, pha) not in out:
            out[(sta, pha)] = raw

    # Retourne les lignes triées dans l'ordre original (par simple ordre station,phase)
    return [out[k] for k in sorted(out.keys())]


def merge_two_bulletins(file_primary, file_secondary,
                        output_file,
                        max_time_diff=2,  # secondes
                        max_dist_km=10,   # km
                        near_time_diff=10):
    """
    Fusionne deux fichiers bulletins.
    file_primary : fichier prioritaire.
    """
    E1 = read_bulletin(file_primary)
    E2 = read_bulletin(file_secondary)

    used_E2 = set()
    suspicious_pairs = []

    merged_events = []

    for i, ev1 in enumerate(E1):
        matched = False

        for j, ev2 in enumerate(E2):
            if j in used_E2:
                continue

            if events_match(ev1, ev2, max_time_diff, max_dist_km):
                # FUSION
                merged_picks = merge_picks(ev1, ev2)
                merged_events.append((ev1["header"]["raw"], merged_picks))
                used_E2.add(j)
                matched = True
                break

            # Si proche en temps mais pas fusionné, à signaler
            dt = abs((ev1["header"]["datetime"] - ev2["header"]["datetime"]).total_seconds())
            if dt <= near_time_diff:
                suspicious_pairs.append((ev1, ev2))

        # Pas trouvé → on garde l'événement de E1 tel quel
        if not matched:
            merged_events.append((ev1["header"]["raw"],
                                  [raw for (_, _, raw) in ev1["picks"]]))

    # Maintenant les événements restants de E2
    for j, ev2 in enumerate(E2):
        if j not in used_E2:
            merged_events.append((ev2["header"]["raw"],
                                  [raw for (_, _, raw) in ev2["picks"]]))

    # Écriture du fichier fusionné
    with open(output_file, "w") as f:
        for header, picks in merged_events:
            f.write(header + "\n")
            for p in picks:
                f.write(p + "\n")
            f.write("\n")

    # Affichage des séismes suspects
    print("\n=== SÉISMES PROCHES MAIS NON FUSIONNÉS ===")
    for ev1, ev2 in suspicious_pairs:
        print("\n--- POTENTIEL CONFLIT ---")
        print(ev1["header"]["raw"])
        print(ev2["header"]["raw"])
        print("Picks ev1:")
        for _, _, raw in ev1["picks"]:
            print("   ", raw)
        print("Picks ev2:")
        for _, _, raw in ev2["picks"]:
            print("   ", raw)

    print("\nFusion terminée. Résultat écrit dans:", output_file)

####################


merge_two_bulletins(
    "obs/OMP/RESUME_78-19.obs", # fichier prioritaire (la loc est choisie)
    "obs/OMP/RESUME_2016.obs", # fichier pour completer les phases
    "obs/PHASES_78-19.obs", # fichier sortie
    max_time_diff=5, # temps max pour considérer que deux evenements sont identidques
    max_dist_km=15, # distance max pour considérer deux séismes identiques
    near_time_diff=20 # affiche les possible correspondances
)
