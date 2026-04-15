"""
add_temporary_picks.py
============================
Add picks from a temporary external obs file into matching events in GLOBAL.obs.

Two-step workflow:
  1. remap_station_codes  — replace bare station names with unified alternate codes
  2. merge_external_picks — inject the remapped picks into matching GLOBAL.obs events

Usage
-----
    # Step 1: remap station codes (in-place if output is omitted)
    python global_obs/add_temporary_picks.py remap \
        --input-path     obs/TEMP.obs \
        --output-path    obs/TEMP_remapped.obs \
        --inventory-path stations/GLOBAL_inventory.xml

    # Step 2: merge remapped picks into GLOBAL.obs
    python global_obs/add_temporary_picks.py merge \
        --global-path    obs/GLOBAL.obs \
        --temporary-path obs/TEMP_remapped.obs \
        --output-path    obs/GLOBAL_updated.obs
"""

import argparse
import os
import sys
from dataclasses import dataclass

import pandas as pd
from obspy import read_inventory, UTCDateTime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .remap_picks_to_unified_codes import find_unique_stations
    from .fuse_bulletins import (
        retrieve_events_from_file,
        get_catalog_frame,
        find_match_events,
        find_pick_lines,
        check_similar_picks,
    )
except ImportError:
    from remap_picks_to_unified_codes import find_unique_stations
    from fuse_bulletins import (
        retrieve_events_from_file,
        get_catalog_frame,
        find_match_events,
        find_pick_lines,
        check_similar_picks,
    )


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RemapStationCodesParams:
    """
    Configuration for step 1: remapping station codes.

    Attributes
    ----------
    input_path     : str — path to the input .obs file with bare station names
    output_path    : str — path for the remapped output .obs file
    inventory_path : str — path to the STATIONXML inventory file
    source_name    : str — tag written into the PickOrigin column (default: 'TEMP')
    """
    input_path:     str
    output_path:    str
    inventory_path: str
    source_name:    str = 'TEMP'


@dataclass
class MergeExternalPicksParams:
    """
    Configuration for step 2: merging remapped picks into GLOBAL.obs.

    Attributes
    ----------
    global_path    : str   — path to the reference GLOBAL.obs bulletin
    temporary_path : str   — path to the remapped external bulletin
    output_path    : str   — path for the merged output bulletin
    dist_km        : float — spatial matching threshold (km, default: 15.0)
    time_s         : float — time matching threshold (s, default: 2.0)
    """
    global_path:    str
    temporary_path: str
    output_path:    str
    dist_km:        float = 15.0
    time_s:         float = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_alternate_code(station_name, date_str, time_str, unique_sta):
    """
    Return the alternate code for a bare station name, filtered by pick date.

    Parameters
    ----------
    station_name : str        — bare station name, e.g. 'RESF'
    date_str     : str        — YYYYMMDD from the pick line
    time_str     : str        — HHMM from the pick line
    unique_sta   : DataFrame  — produced by find_unique_stations()

    Returns
    -------
    str or None — alternate code (e.g. 'FR.0057'), or None if no unique match
    """
    matching = unique_sta.index[unique_sta.Code == station_name].tolist()
    if not matching:
        return None

    try:
        pick_time = UTCDateTime(
            f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
            f'T{time_str[:2]}:{time_str[2:4]}:00Z'
        )
    except Exception:
        return None

    active = []
    for idx in matching:
        start = unique_sta.StartDate.loc[idx]
        end   = unique_sta.EndDate.loc[idx]
        if start is None:
            continue
        if end is None:
            end = UTCDateTime(2500, 12, 31)
        if start <= pick_time <= end:
            active.append(idx)

    if len(active) == 1:
        return unique_sta.AlternateCode.loc[active[0]]
    return None


def _format_pick_line(alt_code, fields, source_name='TEMP'):
    """
    Reconstruct a pick line in exact GLOBAL.obs fixed-column format.

    Takes whitespace-split fields from a Pyrocko pick line and an already-looked-up
    alternate station code.

    GLOBAL.obs column layout (0-indexed):
      0-8   station (9 chars, left-justified)
      10    Ins  |  15 Comp  |  20 Onset  |  22 Phase  |  29 Dir
      31-38 Date (YYYYMMDD)  |  40-43 HHMM  |  45-50 SS.sss
      52-54 GAU  |  56-65 Err (10 chars)  |  66-74 CodaDur
      76-84 P2PAmp  |  86-94 PeriodAmp  |  96+ # RealPhase Channel PickOrigin PGV
    """
    ins    = fields[1]
    comp   = fields[2]
    onset  = fields[3]
    phase  = fields[4]
    direc  = fields[5]
    date   = fields[6]
    hhmm   = fields[7]
    sec    = fields[8]
    err    = f"{float(fields[10]):<10}"
    coda   = fields[11] if len(fields) > 11 else '-1.00e+00'
    amp    = fields[12] if len(fields) > 12 else '-1.00e+00'
    period = fields[13] if len(fields) > 13 else '-1.00e+00'

    return (
        f"{alt_code:<9} {ins}    {comp}    {onset} {phase}      {direc} "
        f"{date} {hhmm} {sec} GAU {err}"
        f"{coda} {amp} {period} "
        f"# {phase:<7}None {source_name:<10}None\n"
    )


def _merge_pick_dicts(global_picks, new_picks):
    """
    Merge two lists of pick lines, with new_picks overriding same station+phase.

    Parameters
    ----------
    global_picks : list of str — existing pick lines from GLOBAL.obs
    new_picks    : list of str — incoming pick lines from the remapped file

    Returns
    -------
    list of str — merged pick lines (existing order preserved; new picks appended)
    """
    picks = {}
    order = []
    for line in global_picks:
        key = (line[:9].strip(), line[22])
        picks[key] = line
        order.append(key)

    for line in new_picks:
        key = (line[:9].strip(), line[22])
        if key not in picks:
            order.append(key)
        picks[key] = line

    return [picks[k] for k in order]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def remap_station_codes(parameters):
    """
    Remap bare station names in a Pyrocko obs file to unified alternate codes.

    Parameters
    ----------
    parameters : RemapStationCodesParams

    Returns
    -------
    dict
        'output'    — path to the remapped output file
        'n_matched' — number of picks successfully matched
        'n_total'   — total pick lines processed
    """
    inventory = read_inventory(parameters.inventory_path, format='STATIONXML')
    unique_sta = find_unique_stations(inventory)
    print(f'Inventory loaded: {len(unique_sta)} station entries')

    with open(parameters.input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    n_total   = 0
    n_matched = 0
    unmatched = set()

    for line in lines:
        if line.startswith('#') or line.strip() == '':
            new_lines.append(line)
            continue

        n_total += 1
        fields   = line.split()

        if len(fields) < 8:
            new_lines.append(line)
            continue

        station_name = fields[0]
        date_str     = fields[6]
        time_str     = fields[7]

        alt_code = _find_alternate_code(station_name, date_str, time_str, unique_sta)

        if alt_code is None:
            unmatched.add(station_name)
            continue

        fields[8] = f"{float(fields[8]):06.3f}"
        new_lines.append(_format_pick_line(alt_code, fields, parameters.source_name))
        n_matched += 1

    with open(parameters.output_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    n_dropped = n_total - n_matched
    print(f'Picks matched : {n_matched}/{n_total}')
    if n_dropped:
        print(f'Picks dropped : {n_dropped}  —  unmatched stations: {sorted(unmatched)}')
    print(f'Output written: {parameters.output_path}')

    return {'output': parameters.output_path, 'n_matched': n_matched, 'n_total': n_total}


def get_catalog_frame_temporary(event_lines):
    """
    Build a catalog DataFrame from Pyrocko-format event header lines.

    Pyrocko headers look like:
        # year month day hour minute second lat lon dep mag
    All values are floats; there are only 10 fields (no magType / magAuthor).
    Returns a DataFrame with the same columns as get_catalog_frame() so both
    can be passed to find_match_events().

    Parameters
    ----------
    event_lines : list of str

    Returns
    -------
    pd.DataFrame
    """
    rows = []
    for line in event_lines:
        f = line.split()
        year, month, day   = int(float(f[0])), int(float(f[1])), int(float(f[2]))
        hour, minute       = int(float(f[3])), int(float(f[4]))
        second             = float(f[5])
        lat, lon, dep, mag = float(f[6]), float(f[7]), float(f[8]), float(f[9])
        rows.append({
            'year':      str(year),
            'month':     str(month),
            'day':       str(day),
            'hour':      str(hour),
            'minute':    str(minute),
            'second':    f'{second:.6f}',
            'latitude':  lat,
            'longitude': lon,
            'depth':     dep,
            'magnitude': mag,
            'magType':   'unknown',
            'magAuthor': 'unknown',
        })

    df = pd.DataFrame(rows)
    df['time'] = pd.to_datetime(
        df['year'] + '-' + df['month'].str.zfill(2) + '-' + df['day'].str.zfill(2) + 'T' +
        df['hour'].str.zfill(2) + ':' + df['minute'].str.zfill(2) + ':' + df['second'] + 'Z'
    )
    return df


def merge_external_picks(parameters):
    """
    Merge picks from a remapped external obs file into GLOBAL.obs events.

    For each GLOBAL.obs event matching an event in the new file:
      - picks sharing the same (station, phase) are replaced by the new pick
      - picks present only in the new file are appended
    Events in the new file without a GLOBAL.obs match are dropped.
    GLOBAL.obs is never modified; the result is written to parameters.output_path.

    Parameters
    ----------
    parameters : MergeExternalPicksParams

    Returns
    -------
    dict
        'output'    — path to the merged output file
        'n_merged'  — events that received new picks
        'n_kept'    — events left unchanged
    """
    print('\n#########')

    global_event_lines, global_ids, global_lines = retrieve_events_from_file(parameters.global_path)
    new_event_lines,    new_ids,    new_lines    = retrieve_events_from_file(parameters.temporary_path)

    global_frame = get_catalog_frame(global_event_lines)
    new_frame    = get_catalog_frame_temporary(new_event_lines)

    strict_matches, possible_matches, _ = find_match_events(
        global_frame, new_frame,
        parameters.dist_km,       parameters.dist_km * 2,
        parameters.time_s,        parameters.time_s * 5,
        mag_thresh=99.0,
    )

    matched = {}

    for _, row in strict_matches.iterrows():
        matched[row['catalog1_idx']] = int(row['catalog2_idx'])

    for _, row in possible_matches.iterrows():
        g_idx = row['catalog1_idx']
        n_idx = int(row['catalog2_idx'])
        if g_idx in matched:
            continue
        if check_similar_picks(global_lines, new_lines, global_ids[g_idx], new_ids[n_idx]) >= 1:
            matched[g_idx] = n_idx

    new_out = [line for line in global_lines if line.startswith('###')]
    new_out.append('\n')

    n_merged = 0
    n_kept   = 0

    for g_idx, _ in enumerate(global_event_lines):
        header_line  = global_lines[global_ids[g_idx]]
        global_picks = find_pick_lines(global_lines, global_ids[g_idx])

        if g_idx in matched:
            n_idx     = matched[g_idx]
            new_picks = find_pick_lines(new_lines, new_ids[n_idx])
            merged    = _merge_pick_dicts(global_picks, new_picks)
            new_out.append(header_line)
            new_out.extend(merged)
            new_out.append('\n')
            n_merged += 1
        else:
            new_out.append(header_line)
            new_out.extend(global_picks)
            new_out.append('\n')
            n_kept += 1

    with open(parameters.output_path, 'w', encoding='utf-8') as f:
        f.writelines(new_out)

    print(f'Events merged (new picks added) : {n_merged}')
    print(f'Events kept as-is (no match)    : {n_kept}')
    print(f'Events dropped (new file only)  : {len(new_event_lines) - n_merged}')
    print(f'Output written : {parameters.output_path}')
    print('#########\n')

    return {'output': parameters.output_path, 'n_merged': n_merged, 'n_kept': n_kept}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Add picks from a temporary external obs file into GLOBAL.obs.'
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # remap sub-command
    p_remap = sub.add_parser('remap', help='Remap bare station codes to unified alternate codes')
    p_remap.add_argument('--input-path',     required=True)
    p_remap.add_argument('--output-path',    required=True)
    p_remap.add_argument('--inventory-path', required=True)
    p_remap.add_argument('--source-name',    default='TEMP')

    # merge sub-command
    p_merge = sub.add_parser('merge', help='Merge remapped picks into GLOBAL.obs')
    p_merge.add_argument('--global-path',    required=True)
    p_merge.add_argument('--temporary-path', required=True)
    p_merge.add_argument('--output-path',    required=True)
    p_merge.add_argument('--dist-km',  type=float, default=15.0)
    p_merge.add_argument('--time-s',   type=float, default=2.0)

    args = parser.parse_args()

    if args.command == 'remap':
        params = RemapStationCodesParams(
            input_path     = args.input_path,
            output_path    = args.output_path,
            inventory_path = args.inventory_path,
            source_name    = args.source_name,
        )
        remap_station_codes(params)
    else:
        params = MergeExternalPicksParams(
            global_path    = args.global_path,
            temporary_path = args.temporary_path,
            output_path    = args.output_path,
            dist_km        = args.dist_km,
            time_s         = args.time_s,
        )
        merge_external_picks(params)


if __name__ == '__main__':
    main()
