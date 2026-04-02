#!/usr/bin/env python3
"""
merge_nll_bulletins.py
----------------------
Merges up to three NonLinLoc relocated bulletin files.
Duplicate events (shared between overlapping zones) are detected using
time and distance thresholds, and only the best-RMS solution is kept.

Bulletin format (space-separated columns):
  YY  MM  DD  HH  MM  SS.ss  lat  lon  depth  mag  rms  npha  erh  erv  gap

Year convention:
  YY < 75  →  2000 + YY
  YY >= 75 →  1900 + YY
"""

import sys
import math
import argparse
from datetime import datetime, timedelta
from itertools import combinations


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_year(yy: int) -> int:
    return 2000 + yy if yy < 75 else 1900 + yy


def parse_line(line: str, source_file: str):
    """Parse one bulletin line. Returns a dict or None if the line is blank/comment."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split()
    if len(parts) < 15:
        print(f"  [WARN] Skipping malformed line in {source_file!r}: {line!r}", file=sys.stderr)
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
        print(f"  [WARN] Could not parse line in {source_file!r}: {e}", file=sys.stderr)
        return None

    year = parse_year(yy)
    sec_int  = int(ss)
    microsec = int(round((ss - sec_int) * 1e6))

    try:
        dt = datetime(year, mo, dd, hh, mm, sec_int, microsec)
    except ValueError as e:
        print(f"  [WARN] Invalid datetime in {source_file!r}: {e}", file=sys.stderr)
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
    events = []
    with open(filepath, "r") as fh:
        for line in fh:
            ev = parse_line(line, filepath)
            if ev:
                events.append(ev)
    print(f"  Loaded {len(events):>5d} events from {filepath!r}")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Distance / time helpers
# ─────────────────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle surface distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def three_d_distance_km(ev1, ev2) -> float:
    """3-D hypocentral distance in km (surface distance + depth difference)."""
    horiz = haversine_km(ev1["lat"], ev1["lon"], ev2["lat"], ev2["lon"])
    vert  = abs(ev1["dep"] - ev2["dep"])
    return math.sqrt(horiz ** 2 + vert ** 2)


def time_diff_seconds(ev1, ev2) -> float:
    return abs((ev1["datetime"] - ev2["datetime"]).total_seconds())


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection between exactly two lists
# ─────────────────────────────────────────────────────────────────────────────

def find_and_resolve_duplicates(list_a, list_b,
                                time_thresh_s: float,
                                dist_thresh_km: float,
                                label_a: str,
                                label_b: str):
    """
    Compare every event in list_a against every event in list_b.
    For each matching pair keep the one with the lower RMS.
    Returns (keep_from_a, keep_from_b, n_duplicates).
    """
    drop_a = set()   # indices into list_a to discard
    drop_b = set()   # indices into list_b to discard
    n_dup  = 0

    for i, ea in enumerate(list_a):
        for j, eb in enumerate(list_b):
            if j in drop_b:
                continue  # already matched
            dt = time_diff_seconds(ea, eb)
            if dt > time_thresh_s:
                continue  # fast pre-filter on time
            dd = three_d_distance_km(ea, eb)
            if dd <= dist_thresh_km:
                n_dup += 1
                # Keep the event with the lower RMS; tie → keep from list_a
                if eb["rms"] < ea["rms"]:
                    drop_a.add(i)
                    winner, loser = label_b, label_a
                else:
                    drop_b.add(j)
                    winner, loser = label_a, label_b
                print(
                    f"    DUP #{n_dup:04d}  Δt={dt:.2f}s  Δd={dd:.2f}km  "
                    f"rms_a={ea['rms']:.4f}  rms_b={eb['rms']:.4f}  "
                    f"→ keep from {winner}, drop from {loser}"
                )
                break  # one-to-one matching: move on to next ea

    keep_a = [ev for k, ev in enumerate(list_a) if k not in drop_a]
    keep_b = [ev for k, ev in enumerate(list_b) if k not in drop_b]
    return keep_a, keep_b, n_dup


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def format_event(ev) -> str:
    """Reconstruct the original bulletin line (raw copy)."""
    return ev["raw"]


def write_bulletin(events, filepath: str):
    # Sort chronologically before writing
    events_sorted = sorted(events, key=lambda e: e["datetime"])
    with open(filepath, "w") as fh:
        for ev in events_sorted:
            fh.write(format_event(ev) + "\n")
    print(f"  Written {len(events_sorted):>5d} events → {filepath!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge NonLinLoc bulletin files and remove duplicate events."
    )
    parser.add_argument("bulletins", nargs="+", metavar="FILE",
                        help="Two or three bulletin files to merge (order matters for overlap: "
                             "file1↔file2 and file2↔file3 are the overlapping pairs).")
    parser.add_argument("-t", "--time", type=float, default=2.0,
                        help="Time threshold in seconds for duplicate detection (default: 2).")
    parser.add_argument("-d", "--dist", type=float, default=20.0,
                        help="3-D distance threshold in km for duplicate detection (default: 20).")
    parser.add_argument("-o", "--output", default="merged_bulletin.txt",
                        help="Output file name (default: merged_bulletin.txt).")
    args = parser.parse_args()

    if not (2 <= len(args.bulletins) <= 3):
        print("ERROR: Please supply exactly 2 or 3 bulletin files.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  NonLinLoc Bulletin Merger")
    print(f"  Time threshold  : {args.time} s")
    print(f"  Distance threshold: {args.dist} km")
    print(f"{'='*60}\n")

    # ── Load ──────────────────────────────────────────────────────────────────
    print("[ Loading bulletins ]")
    bulletins = [load_bulletin(f) for f in args.bulletins]
    total_raw = sum(len(b) for b in bulletins)
    print(f"  Total raw events: {total_raw}\n")

    # ── Deduplicate adjacent pairs ────────────────────────────────────────────
    # Overlaps are only between adjacent files (A↔B and B↔C).
    # We resolve A↔B first, then B↔C on the already-cleaned lists.

    print("[ Detecting & resolving duplicates ]")

    if len(bulletins) == 2:
        print(f"  Pass 1/1: {args.bulletins[0]} ↔ {args.bulletins[1]}")
        b0, b1, nd = find_and_resolve_duplicates(
            bulletins[0], bulletins[1],
            args.time, args.dist,
            args.bulletins[0], args.bulletins[1]
        )
        merged = b0 + b1
        total_dup = nd

    else:  # 3 files
        print(f"  Pass 1/2: {args.bulletins[0]} ↔ {args.bulletins[1]}")
        b0, b1, nd1 = find_and_resolve_duplicates(
            bulletins[0], bulletins[1],
            args.time, args.dist,
            args.bulletins[0], args.bulletins[1]
        )
        print(f"  Pass 2/2: {args.bulletins[1]} ↔ {args.bulletins[2]}")
        b1, b2, nd2 = find_and_resolve_duplicates(
            b1, bulletins[2],
            args.time, args.dist,
            args.bulletins[1], args.bulletins[2]
        )
        merged = b0 + b1 + b2
        total_dup = nd1 + nd2

    print(f"\n  Total duplicates removed : {total_dup}")
    print(f"  Events in merged catalog : {len(merged)}\n")

    # ── Write output ──────────────────────────────────────────────────────────
    print("[ Writing merged bulletin ]")
    write_bulletin(merged, args.output)
    print(f"\nDone. Merged catalog saved to {args.output!r}\n")


if __name__ == "__main__":
    main()