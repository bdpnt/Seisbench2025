"""
Add picks from a temporary external obs file into matching events in GLOBAL.obs.

Two-step workflow:
  1. remapStationCodes  — replace bare station names with unified alternate codes
  2. mergeExternalPicks — inject the remapped picks into matching GLOBAL.obs events

Usage (step 1 only, from the command line)
------------------------------------------
    python add_temporary_picks.py <input_obs> [<output_obs>]

If <output_obs> is omitted, the input file is updated in-place.
"""

import sys
import os

from dataclasses import dataclass
import pandas as pd
from obspy import read_inventory, UTCDateTime

from .remap_picks_to_unified_codes import findUniqueStations
from .fuse_bulletins import (
    retrieveEvents_fromFile,
    get_catalogFrame,
    find_matchEvents,
    find_pickLines,
    check_similarPicks,
)


@dataclass
class RemapStationCodesParams:
    inputPath: str
    outputPath: str
    inventoryPath: str
    sourceName: str = 'TEMP'


@dataclass
class MergeExternalPicksParams:
    globalPath: str
    temporaryPath: str
    outputPath: str
    distKm: float = 15.0
    timeS:  float = 2.0


def _findAlternateCode(station_name, date_str, time_str, uniqueSta):
    """Return the alternate code for a bare station name, filtered by pick date.

    Parameters
    ----------
    station_name : str  bare station name, e.g. 'RESF'
    date_str     : str  YYYYMMDD from the pick line
    time_str     : str  HHMM from the pick line
    uniqueSta    : DataFrame produced by findUniqueStations()

    Returns
    -------
    str or None  alternate code (e.g. 'FR.0057'), or None if no unique match
    """
    matching = uniqueSta.index[uniqueSta.Code == station_name].tolist()
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
        start = uniqueSta.StartDate.loc[idx]
        end   = uniqueSta.EndDate.loc[idx]
        if start is None:
            continue
        if end is None:
            end = UTCDateTime(2500, 12, 31)
        if start <= pick_time <= end:
            active.append(idx)

    if len(active) == 1:
        return uniqueSta.AlternateCode.loc[active[0]]
    return None  # no match or ambiguous


def _format_pick_line(alt_code, fields, source_name='TEMP'):
    """Reconstruct a pick line in exact GLOBAL.obs fixed-column format.

    Takes whitespace-split fields from a Pyrocko pick line and an already-looked-up
    alternate station code, and returns a line whose columns are byte-for-byte
    compatible with GLOBAL.obs (same positions for station, phase, date, HHMM,
    and seconds as expected by fuse_bulletins helpers).

    GLOBAL.obs column layout (0-indexed):
      0-8   station (9 chars, left-justified)
      9     space
      10    Ins
      11-14 spaces
      15    Comp
      16-19 spaces
      20    Onset
      21    space
      22    Phase
      23-28 spaces
      29    Dir
      30    space
      31-38 Date (YYYYMMDD)
      39    space
      40-43 HHMM
      44    space
      45-50 SS.sss (6 chars)
      51    space
      52-54 GAU
      55    space
      56-65 Err (10 chars, left-justified)
      66-74 CodaDur
      75    space
      76-84 P2PAmp
      85    space
      86-94 PeriodAmp
      95    space
      96+   # RealPhase Channel PickOrigin PGV
    """
    ins    = fields[1]
    comp   = fields[2]
    onset  = fields[3]
    phase  = fields[4]
    direc  = fields[5]
    date   = fields[6]
    hhmm   = fields[7]
    sec    = fields[8]  # already zero-padded by remapStationCodes
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


def remapStationCodes(parameters):
    """Remap bare station names in a Pyrocko obs file to unified alternate codes.

    Parameters
    ----------
    parameters : RemapStationCodesParams
    """
    inventory = read_inventory(parameters.inventoryPath, format='STATIONXML')
    uniqueSta = findUniqueStations(inventory)
    print(f"Inventory loaded: {len(uniqueSta)} station entries")

    with open(parameters.inputPath, 'r', encoding='utf-8') as f:
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
        fields = line.split()

        if len(fields) < 8:
            new_lines.append(line)
            continue

        station_name = fields[0]
        date_str     = fields[6]   # YYYYMMDD
        time_str     = fields[7]   # HHMM

        alt_code = _findAlternateCode(station_name, date_str, time_str, uniqueSta)

        if alt_code is None:
            unmatched.add(station_name)
            continue   # drop unmatched pick, consistent with pipeline behaviour

        # Zero-pad seconds to match GLOBAL.obs convention (e.g. 9.44 → 09.440)
        fields[8] = f"{float(fields[8]):06.3f}"

        new_lines.append(_format_pick_line(alt_code, fields, parameters.sourceName))
        n_matched += 1

    with open(parameters.outputPath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    n_dropped = n_total - n_matched
    print(f"Picks matched : {n_matched}/{n_total}")
    if n_dropped:
        print(f"Picks dropped : {n_dropped}  —  unmatched stations: {sorted(unmatched)}")
    print(f"Output written: {parameters.outputPath}")


def get_catalogFrame_temporary(eventLines):
    """Build a catalog DataFrame from Pyrocko-format event header lines.

    Pyrocko headers look like:
        # 2020.000000 12.000000 4.000000 6.000000 41.000000 27.460000 42.778833 0.545333 11.590000 1.000000
          year        month     day      hour      minute    second    lat       lon       dep       mag

    All values are floats; there are only 10 fields (no magType / magAuthor).
    Returns a DataFrame with the same columns as get_catalogFrame() so both
    can be passed to find_matchEvents().
    """
    rows = []
    for line in eventLines:
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


def _merge_pick_dicts(global_picks, new_picks):
    """Merge two lists of pick lines, with new_picks overriding same station+phase.

    Parameters
    ----------
    global_picks : list of str  existing pick lines from GLOBAL.obs
    new_picks    : list of str  incoming pick lines from the remapped file

    Returns
    -------
    list of str  merged pick lines (existing order preserved; new picks appended)
    """
    # Build ordered dict from existing picks keyed by (station, phase)
    picks = {}
    order = []
    for line in global_picks:
        key = (line[:9].strip(), line[22])
        picks[key] = line
        order.append(key)

    # Apply incoming picks: replace if key exists, otherwise append
    for line in new_picks:
        key = (line[:9].strip(), line[22])
        if key not in picks:
            order.append(key)
        picks[key] = line

    return [picks[k] for k in order]


def mergeExternalPicks(parameters):
    """Merge picks from a remapped external obs file into GLOBAL.obs events.

    For each event in GLOBAL.obs that matches an event in the new file:
      - picks sharing the same (station, phase) are replaced by the new pick
      - picks present only in the new file are appended
    Events in the new file without a GLOBAL.obs match are dropped.
    GLOBAL.obs is never modified; the result is written to parameters.outputPath.

    Parameters
    ----------
    parameters : MergeExternalPicksParams
    """
    print('\n#########')

    # Load both catalogs
    globalEventLines, globalIDs, globalLines = retrieveEvents_fromFile(parameters.globalPath)
    newEventLines,    newIDs,    newLines    = retrieveEvents_fromFile(parameters.temporaryPath)

    globalFrame = get_catalogFrame(globalEventLines)
    newFrame    = get_catalogFrame_temporary(newEventLines)

    # Match events — magnitude threshold set very high so it never activates
    # for non-LDG/OMP authors (purely spatial/temporal matching)
    strictMatches, possibleMatches, _ = find_matchEvents(
        globalFrame, newFrame,
        parameters.distKm,       parameters.distKm * 2,
        parameters.timeS,        parameters.timeS * 5,
        magThresh=99.0,
    )

    # Build lookup: global event index → new event index (after both passes)
    matched = {}

    for _, row in strictMatches.iterrows():
        matched[row['catalog1_idx']] = int(row['catalog2_idx'])

    # Validate loose candidates with at least 1 common P-phase pick
    for _, row in possibleMatches.iterrows():
        g_idx = row['catalog1_idx']
        n_idx = int(row['catalog2_idx'])
        if g_idx in matched:
            continue
        sim = check_similarPicks(globalLines, newLines, globalIDs[g_idx], newIDs[n_idx])
        if sim >= 1:
            matched[g_idx] = n_idx

    # Build output preserving GLOBAL.obs structure
    # Keep the three ### header lines
    new_out = [line for line in globalLines if line.startswith('###')]
    new_out.append('\n')

    n_merged = 0
    n_kept   = 0

    for g_idx, event_header in enumerate(globalEventLines):
        header_line  = globalLines[globalIDs[g_idx]]
        global_picks = find_pickLines(globalLines, globalIDs[g_idx])

        if g_idx in matched:
            n_idx     = matched[g_idx]
            new_picks = find_pickLines(newLines, newIDs[n_idx])
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

    with open(parameters.outputPath, 'w', encoding='utf-8') as f:
        f.writelines(new_out)

    print(f"Events merged (new picks added) : {n_merged}")
    print(f"Events kept as-is (no match)    : {n_kept}")
    print(f"Events dropped (new file only)  : {len(newEventLines) - n_merged}")
    print(f"Output written : {parameters.outputPath}")
    print('#########\n')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    params = RemapStationCodesParams(
        inputPath     = sys.argv[1],
        outputPath    = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1],
        inventoryPath = sys.argv[3] if len(sys.argv) > 3 else '',
    )
    remapStationCodes(params)
