"""
merge_regional_results.py
============================
Merge any number of NonLinLoc relocated bulletin files into one.

Duplicate events shared between overlapping adjacent zones are detected using
time and distance thresholds. Only the solution with the lower RMS is kept.
Overlaps are resolved pairwise in adjacency order:
  file1↔file2, file2↔file3, file3↔file4, …

Bulletin format (space-separated columns):
  YY  MM  DD  HH  MM  SS.ss  lat  lon  depth  mag  rms  npha  erh  erv  gap

Year convention:
  YY < 75  →  2000 + YY
  YY >= 75 →  1900 + YY

Usage
-----
    python NLL_run/merge_regional_results.py \\
        RESULT/GLOBAL_1.txt RESULT/GLOBAL_2.txt ... \\
        -o RESULT/FINAL.txt
"""

import argparse
import logging
import math
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT    = os.path.dirname(_MODULE_DIR)
_DEFAULT_LOG_DIR = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('merge_regional_results')


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logger(log_dir, output_path):
    os.makedirs(log_dir, exist_ok=True)
    basename  = os.path.splitext(os.path.basename(output_path))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"{basename}_{timestamp}.log")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)
    return log_path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_year(yy: int) -> int:
    """Convert a two-digit year to a four-digit year using the 75-year cutoff convention."""
    return 2000 + yy if yy < 75 else 1900 + yy


def parse_line(line: str, source_file: str):
    """Parse one bulletin line. Returns a dict or None if blank/comment."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split()
    if len(parts) < 15:
        logger.warning(f"Skipping malformed line in {source_file!r}: {line!r}")
        return None

    try:
        yy   = int(parts[0])
        mo   = int(parts[1])
        dd   = int(parts[2])
        hh   = int(parts[3])
        mm   = int(parts[4])
        ss   = float(parts[5])
        lat  = float(parts[6])
        lon  = float(parts[7])
        dep  = float(parts[8])
        mag  = float(parts[9])
        rms  = float(parts[10])
        npha = float(parts[11])
        erh  = float(parts[12])
        erv  = float(parts[13])
        gap  = float(parts[14])
    except ValueError as e:
        logger.warning(f"Could not parse line in {source_file!r}: {e}")
        return None

    year     = parse_year(yy)
    sec_int  = int(ss)
    microsec = int(round((ss - sec_int) * 1e6))

    try:
        dt = datetime(year, mo, dd, hh, mm, sec_int, microsec)
    except ValueError as e:
        logger.warning(f"Invalid datetime in {source_file!r}: {e}")
        return None

    return {
        "datetime": dt,
        "lat":  lat,
        "lon":  lon,
        "dep":  dep,
        "mag":  mag,
        "rms":  rms,
        "npha": npha,
        "erh":  erh,
        "erv":  erv,
        "gap":  gap,
        "raw":  line,
        "src":  source_file,
    }


def load_bulletin(filepath: str):
    """Read all events from a bulletin file and return them as a list of dicts."""
    events = []
    with open(filepath, "r") as fh:
        for line in fh:
            ev = parse_line(line, filepath)
            if ev:
                events.append(ev)
    logger.info(f"Loaded {len(events):>5d} events from {filepath!r}")
    return events


# ---------------------------------------------------------------------------
# Distance / time helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle surface distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def three_d_distance_km(ev1, ev2) -> float:
    """3-D hypocentral distance in km."""
    horiz = haversine_km(ev1["lat"], ev1["lon"], ev2["lat"], ev2["lon"])
    vert  = abs(ev1["dep"] - ev2["dep"])
    return math.sqrt(horiz ** 2 + vert ** 2)


def time_diff_seconds(ev1, ev2) -> float:
    """Return the absolute time difference in seconds between two events."""
    return abs((ev1["datetime"] - ev2["datetime"]).total_seconds())


# ---------------------------------------------------------------------------
# Duplicate detection between exactly two lists
# ---------------------------------------------------------------------------

def find_and_resolve_duplicates(list_a, list_b,
                                time_thresh_s: float,
                                dist_thresh_km: float,
                                label_a: str,
                                label_b: str):
    """
    Compare every event in list_a against every event in list_b.
    For each matching pair keep the one with the lower RMS.
    Returns (cleaned_list_a, cleaned_list_b, n_duplicates).
    """
    drop_a = set()
    drop_b = set()
    n_dup  = 0

    for i, ea in enumerate(list_a):
        # Skip events from A that were already matched in a previous iteration
        if i in drop_a:
            continue
        for j, eb in enumerate(list_b):
            # Skip events from B that were already matched
            if j in drop_b:
                continue
            # Fast pre-filter on time before computing the more expensive distance
            if time_diff_seconds(ea, eb) > time_thresh_s:
                continue
            # Full 3-D distance check
            if three_d_distance_km(ea, eb) <= dist_thresh_km:
                n_dup += 1
                dt = time_diff_seconds(ea, eb)
                dd = three_d_distance_km(ea, eb)
                # Keep the event with the lower RMS; tie → keep from list_a
                if eb["rms"] < ea["rms"]:
                    drop_a.add(i)
                    winner, loser = label_b, label_a
                else:
                    drop_b.add(j)
                    winner, loser = label_a, label_b
                logger.info(
                    f"DUP #{n_dup:04d}  Δt={dt:.2f}s  Δd={dd:.2f}km  "
                    f"rms_a={ea['rms']:.4f}  rms_b={eb['rms']:.4f}  "
                    f"keep from {winner}, drop from {loser}"
                )
                # One-to-one matching: once ea is matched, move on to next ea
                break

    keep_a = [ev for k, ev in enumerate(list_a) if k not in drop_a]
    keep_b = [ev for k, ev in enumerate(list_b) if k not in drop_b]
    return keep_a, keep_b, n_dup


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_event(ev) -> str:
    """Reconstruct the original bulletin line (raw copy)."""
    return ev["raw"]


def write_bulletin(events, filepath: str):
    """Sort events chronologically and write them to a bulletin file."""
    # Sort chronologically before writing
    events_sorted = sorted(events, key=lambda e: e["datetime"])
    with open(filepath, "w") as fh:
        for ev in events_sorted:
            fh.write(format_event(ev) + "\n")
    logger.info(f"Written {len(events_sorted):>5d} events → {filepath!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_bulletins(bulletin_files, output_path,
                    time_thresh_s=2.0, dist_thresh_km=20.0, log_dir=None):
    """
    Load, deduplicate, and merge a list of NLL bulletin files into one.

    Parameters
    ----------
    bulletin_files : list[str] — paths to bulletin files, in adjacency order
    output_path    : str       — path for the merged output file
    time_thresh_s  : float     — origin-time window for duplicate detection (default: 2 s)
    dist_thresh_km : float     — 3-D distance threshold for duplicate detection (default: 20 km)
    log_dir        : str, optional — log directory (default: NLL_run/console_output/)

    Returns
    -------
    dict with keys: output, log, n_merged, n_duplicates
    """
    log_path = _setup_logger(log_dir or _DEFAULT_LOG_DIR, output_path)

    n = len(bulletin_files)
    logger.info(f"Files              : {n}")
    logger.info(f"Time threshold     : {time_thresh_s} s")
    logger.info(f"Distance threshold : {dist_thresh_km} km")

    bulletins = [load_bulletin(f) for f in bulletin_files]
    logger.info(f"Total raw events   : {sum(len(b) for b in bulletins)}")

    # Deduplicate adjacent pairs in a single loop. After resolving pair (i, i+1),
    # the cleaned version of list i+1 is reused as the left-hand side when
    # resolving pair (i+1, i+2), so an event already dropped cannot be re-matched.
    total_dup = 0
    for i in range(n - 1):
        label_a = bulletin_files[i]
        label_b = bulletin_files[i + 1]
        logger.info(f"Pass {i+1}/{n-1}: {label_a} ↔ {label_b}")
        bulletins[i], bulletins[i + 1], nd = find_and_resolve_duplicates(
            bulletins[i], bulletins[i + 1],
            time_thresh_s, dist_thresh_km,
            label_a, label_b,
        )
        total_dup += nd

    merged = [ev for b in bulletins for ev in b]
    logger.info(f"Total duplicates removed : {total_dup}")
    logger.info(f"Events in merged catalog : {len(merged)}")

    write_bulletin(merged, output_path)

    return {
        'output':       output_path,
        'log':          log_path,
        'n_merged':     len(merged),
        'n_duplicates': total_dup,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """Parse CLI arguments, load bulletins, deduplicate adjacent zone pairs, and write the merged output."""
    parser = argparse.ArgumentParser(
        description="Merge NonLinLoc bulletin files and remove duplicate events."
    )
    parser.add_argument("bulletins", nargs="+", metavar="FILE",
                        help="Bulletin files to merge, in adjacency order "
                             "(file1↔file2, file2↔file3, …).")
    parser.add_argument("-t", "--time", type=float, default=2.0,
                        help="Time threshold in seconds (default: 2).")
    parser.add_argument("-d", "--dist", type=float, default=20.0,
                        help="3-D distance threshold in km (default: 20).")
    parser.add_argument("-o", "--output", default="merged_bulletin.txt",
                        help="Output file name (default: merged_bulletin.txt).")
    args = parser.parse_args()

    if len(args.bulletins) < 2:
        print("ERROR: Please supply at least 2 bulletin files.", file=sys.stderr)
        sys.exit(1)

    merge_bulletins(args.bulletins, args.output, args.time, args.dist)


if __name__ == "__main__":
    main()