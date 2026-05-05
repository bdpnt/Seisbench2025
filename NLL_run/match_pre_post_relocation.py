"""
match_pre_post_relocation.py
============================
Match pre-NLL .obs events to their NonLinLoc-relocated counterparts.

Reads the global GLOBAL.obs bulletin and the NLL result file, then runs an
interactive one-to-one matching that updates each event header with the
relocated coordinates, depth, RMS, and uncertainty. Unique picks from
flagged duplicates can be merged into the kept event. The matched bulletin
is written to a new output file.

Usage
-----
    python NLL_run/match_pre_post_relocation.py \\
        --obs    obs/GLOBAL.obs \\
        --final  RESULT/FINAL.txt \\
        --output obs/FINAL.obs
"""

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from obspy import UTCDateTime as Timing
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT    = os.path.dirname(_MODULE_DIR)
_DEFAULT_LOG_DIR = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('match_pre_post_relocation')


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
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MatchCatalogsParams:
    file_obs:   str
    file_final: str
    save_file:  str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_obs(file):
    """
    Parse an .obs bulletin into a DataFrame of event headers plus the raw
    lines list.

    Parameters
    ----------
    file : str — path to the .obs bulletin

    Returns
    -------
    (pd.DataFrame, list[str])
    """
    with open(file, 'r') as f:
        lines = f.readlines()

    obs = [
        [*line.lstrip('# ').rstrip('\n').split(), idx]
        for idx, line in enumerate(lines)
        if line.startswith('# ')
    ]

    df = pd.DataFrame(obs, columns=[
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'MagType', 'MagAuthor',
        'PhaseCount', 'HorUncer', 'VerUncer', 'AzGap', 'RMS', 'BulletinID',
    ])

    cols_to_num = [
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'PhaseCount',
        'HorUncer', 'VerUncer', 'AzGap', 'RMS',
    ]
    df[cols_to_num] = df[cols_to_num].apply(pd.to_numeric, errors='coerce')
    df['Time'] = pd.to_datetime(
        df['Year'].astype(str) + '-'
        + df['Month'].astype(str) + '-'
        + df['Day'].astype(str) + 'T'
        + df['Hour'].astype(str) + ':'
        + df['Min'].astype(str) + ':'
        + df['Sec'].astype(str) + 'Z'
    )
    return df, lines


def _read_final(file):
    """
    Parse a plain-text NLL result file (hypo_71 format) into a DataFrame.

    Parameters
    ----------
    file : str — path to the NLL result bulletin

    Returns
    -------
    pd.DataFrame
    """
    with open(file, 'r') as f:
        lines = f.readlines()

    final = [line.rstrip('\n').split() for line in lines]
    final = [
        [int(line[0]) + 1900 if int(line[0]) > 75 else int(line[0]) + 2000] + line[1:]
        for line in final
    ]

    df = pd.DataFrame(final, columns=[
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'RMS', 'PhaseCount',
        'HorUncer', 'VerUncer', 'AzGap',
    ])

    cols_to_num = [
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'PhaseCount',
        'HorUncer', 'VerUncer', 'AzGap', 'RMS',
    ]
    df[cols_to_num] = df[cols_to_num].apply(pd.to_numeric, errors='coerce')
    df['Time'] = pd.to_datetime(
        df['Year'].astype(str) + '-'
        + df['Month'].astype(str) + '-'
        + df['Day'].astype(str) + 'T'
        + df['Hour'].astype(str) + ':'
        + df['Min'].astype(str) + ':'
        + df['Sec'].astype(str) + 'Z'
    )
    return df


def _phase_key(phase_line: str) -> tuple:
    """
    Return a (station, phase_type) tuple that uniquely identifies a phase
    regardless of timing differences or '?' vs '*' wildcards.

    Parameters
    ----------
    phase_line : str — one raw pick line from the bulletin

    Returns
    -------
    (str, str) or None if the line is malformed
    """
    tokens = phase_line.split()
    if len(tokens) < 5:
        return None
    return (tokens[0], tokens[4])


def _diff_phases(kept_bid: int, dropped_bid: int, phase_index: dict) -> list:
    """
    Return phase lines from the dropped event that are NOT already present
    in the kept event, compared by (station, phase_type) key only.

    Parameters
    ----------
    kept_bid    : int  — BulletinID of the kept event
    dropped_bid : int  — BulletinID of the dropped duplicate
    phase_index : dict — maps BulletinID → list of raw phase strings

    Returns
    -------
    list[str] — new phase lines from the dropped event
    """
    if not phase_index:
        return []

    kept_phases    = phase_index.get(kept_bid,    [])
    dropped_phases = phase_index.get(dropped_bid, [])
    kept_keys      = {_phase_key(p) for p in kept_phases if _phase_key(p) is not None}

    return [
        ph for ph in dropped_phases
        if _phase_key(ph) is not None and _phase_key(ph) not in kept_keys
    ]


def _update_bulletin(lines, matched_df):
    """
    Rebuild a bulletin from lines, keeping only events present in matched_df
    and updating their header lines with the matched values.

    If a row carries a non-empty '_extra_phases' list, those phase lines are
    appended at the end of the event's phase block.

    Parameters
    ----------
    lines      : list[str]    — raw bulletin lines
    matched_df : pd.DataFrame — output of match_catalogues()

    Returns
    -------
    list[str] — updated bulletin lines ready to be written to disk
    """
    blocks        = []
    current_block = []
    event_indices = []

    for i, line in enumerate(lines):
        if line.startswith('# '):
            if current_block:
                blocks.append(current_block)
            current_block = [line]
            event_indices.append(i)
        else:
            if current_block:
                current_block.append(line)
    if current_block:
        blocks.append(current_block)

    updated_blocks = []
    for block, event_index in zip(blocks, event_indices):
        if not block:
            continue

        row = matched_df[matched_df.BulletinID == event_index]
        if row.empty:
            continue

        r = row.iloc[0]

        updated_event_line = (
            f"# {r.Year} {r.Month} {r.Day} {r.Hour} {r.Min} {r.Sec} "
            f"{r.Lat} {r.Lon} {r.Dep} {r.Mag} {r.MagType} {r.MagAuthor} "
            f"{r.PhaseCount} {r.HorUncer} {r.VerUncer} {r.AzGap} {r.RMS}\n"
        )

        phase_lines    = [l for l in block[1:] if not (l.startswith('\n') or l == '')]
        trailing_blank = [l for l in block[1:] if      l.startswith('\n') or l == '']

        try:
            extra = r['_extra_phases']
        except (KeyError, TypeError):
            extra = None

        if extra is not None and len(extra) > 0:
            extra_lines = [ph if ph.endswith('\n') else ph + '\n' for ph in extra]
            phase_lines = phase_lines + extra_lines

        updated_blocks.append([updated_event_line] + phase_lines + trailing_blank)

    lines[0] = f'### Bulletin generated on the {Timing.now()}\n'
    updated_content = lines[0:4]
    for block in updated_blocks:
        updated_content.extend(block)

    return updated_content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_catalogues(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    max_dt_seconds: float = 10.0,
    max_dist_km: float = 50.0,
    min_ambiguous_dt: float = 0.5,
    bulletin_lines: list = None,
) -> pd.DataFrame:
    """
    Match seismic events from catalogue 1 to catalogue 2, one-to-one.

    For each event in df1:
      1. Find all df2 candidates within max_dt_seconds.
      2. Among those, keep only candidates within max_dist_km.
      3. Among survivors, pick the one closest in time.
      4. Matching is strictly one-to-one.
      5. Ambiguous matches trigger an interactive prompt.

    Interactive choices at an ambiguous prompt
    ------------------------------------------
    1   → assign Candidate 1
    2   → assign Candidate 2
    1d  → assign Candidate 1 + drop next df1 event as duplicate
    2d  → assign Candidate 2 + drop next df1 event as duplicate
    s   → skip current df1 event
    sd  → skip current df1 event as duplicate of the next one
    p   → print phase lines for current and next df1 events (requires bulletin_lines)

    Parameters
    ----------
    df1              : pd.DataFrame — primary catalogue; needs 'BulletinID' when
                       bulletin_lines is provided
    df2              : pd.DataFrame — reference catalogue
    max_dt_seconds   : float        — maximum time difference in seconds (default: 10)
    max_dist_km      : float        — maximum 3-D distance in km (default: 50)
    min_ambiguous_dt : float        — minimum time separation between candidates
                       for the match to be unambiguous (default: 0.5 s)
    bulletin_lines   : list[str], optional — raw bulletin file lines; enables the
                       'p' prompt and phase merging for duplicates

    Returns
    -------
    pd.DataFrame with an added '_extra_phases' column
    """
    update_cols = [
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'RMS', 'PhaseCount',
        'HorUncer', 'VerUncer', 'AzGap',
    ]

    for col in update_cols:
        if col not in df1.columns:
            raise ValueError(f"Column '{col}' not found in df1.")
        if col not in df2.columns:
            raise ValueError(f"Column '{col}' not found in df2.")

    if bulletin_lines is not None and 'BulletinID' not in df1.columns:
        raise ValueError("df1 must contain a 'BulletinID' column when bulletin_lines is provided.")

    d1 = df1.copy()
    d2 = df2.copy()
    d1['Time'] = pd.to_datetime(d1['Time'])
    d2['Time'] = pd.to_datetime(d2['Time'])

    d2       = d2.sort_values('Time').reset_index(drop=False)
    d2_times = d2['Time'].values.astype('int64')

    # Pre-index phases from bulletin_lines
    phase_index: dict = {}
    if bulletin_lines is not None:
        current_id = None
        for line_idx, line in enumerate(bulletin_lines):
            if line.startswith('# '):
                current_id = line_idx
                phase_index[current_id] = []
            elif line.startswith('\n') or line == '':
                current_id = None
            elif current_id is not None:
                phase_index[current_id].append(line.rstrip('\n'))

    def _print_phases(event_row, label: str, sep: str) -> None:
        bid    = event_row['BulletinID']
        phases = phase_index.get(bid, [])
        print(f"\n  {label} phases  (BulletinID={bid})")
        print(sep)
        for ph in phases:
            print(f"    {ph}")
        if not phases:
            print("    (no phases found for this BulletinID)")
        print(sep)

    def to_cartesian(lat_deg, lon_deg, depth_km):
        R   = 6371.0
        lat = np.radians(lat_deg)
        lon = np.radians(lon_deg)
        r   = R - depth_km
        x   = r * np.cos(lat) * np.cos(lon)
        y   = r * np.cos(lat) * np.sin(lon)
        z   = r * np.sin(lat)
        return np.column_stack([x, y, z])

    xyz2 = to_cartesian(d2['Lat'].values, d2['Lon'].values, d2['Dep'].values)
    tree = cKDTree(xyz2)

    max_dt_ns              = int(max_dt_seconds   * 1e9)
    ambiguous_threshold_ns = int(min_ambiguous_dt * 1e9)
    chord_threshold        = max_dist_km

    used_df2_indices  = set()
    double_drop_map:  dict = {}
    pending_extra_bid: int = None
    match_records          = []

    d1 = d1.sort_values('Time').reset_index(drop=True)

    for i, row1 in d1.iterrows():

        if i in double_drop_map:
            print(
                f"  DROPPED (duplicate): df1 event at {row1['Time']} "
                f"(flagged as double of the event at index {i - 1})."
            )
            logger.info(f"DROPPED (duplicate): df1 event at {row1['Time']}  index={i}")
            continue

        t1_ns = row1['Time'].value

        lo = np.searchsorted(d2_times, t1_ns - max_dt_ns, side='left')
        hi = np.searchsorted(d2_times, t1_ns + max_dt_ns, side='right')
        if lo >= hi:
            continue

        candidates_pos = np.arange(lo, hi)

        xyz1       = to_cartesian(np.array([row1['Lat']]), np.array([row1['Lon']]),
                                   np.array([row1['Dep']]))
        nearby     = tree.query_ball_point(xyz1[0], r=chord_threshold)
        nearby_set = set(nearby)
        valid_pos  = [p for p in candidates_pos if p in nearby_set and p not in used_df2_indices]

        if not valid_pos:
            continue

        drop_next_as_double = False
        next_i              = None

        if len(valid_pos) > 1:
            _next_j = i + 1
            while _next_j in double_drop_map and _next_j < len(d1):
                _next_j += 1
            _next_within_30s = (
                _next_j < len(d1)
                and abs(d1.iloc[_next_j]['Time'].value - t1_ns) <= int(30e9)
            )
            _dt_cands  = np.abs(d2_times[valid_pos] - t1_ns)
            _best_j    = int(np.argmin(_dt_cands))
            _best_dt_s = _dt_cands[_best_j] / 1e9

            if not _next_within_30s and _best_dt_s < 5.0:
                valid_pos = [valid_pos[_best_j]]
                logger.info(
                    f"AUTO-RESOLVED: df1 event at {row1['Time']}  "
                    f"best_dt={_best_dt_s:.3f}s  no next df1 event within 30s"
                )
            else:
                candidate_times = d2_times[valid_pos]
                is_ambiguous    = False

                unique_times = np.unique(candidate_times)
                if len(unique_times) == 1:
                    is_ambiguous     = True
                    ambiguity_reason = 'all candidates share an identical timestamp'
                else:
                    diff_matrix    = np.abs(candidate_times[:, None] - candidate_times[None, :])
                    min_dt_between = np.min(diff_matrix[diff_matrix > 0])
                    if min_dt_between < ambiguous_threshold_ns:
                        is_ambiguous     = True
                        ambiguity_reason = (
                            f"candidates are within {min_dt_between/1e9:.2f}s of each other"
                        )

                if is_ambiguous:
                    sep = '─' * 72

                    df1_info = (
                        f"  df1 event  │ Time: {row1['Time']}  "
                        f"Lat: {row1['Lat']:.4f}  Lon: {row1['Lon']:.4f}  "
                        f"Dep: {row1['Dep']:.1f} km"
                    )

                    next_i  = i + 1
                    while next_i in double_drop_map:
                        next_i += 1
                    has_next = next_i < len(d1)
                    if has_next:
                        nxt = d1.iloc[next_i]
                        next_info = (
                            f"  Next df1   │ Time: {nxt['Time']}  "
                            f"Lat: {nxt['Lat']:.4f}  Lon: {nxt['Lon']:.4f}  "
                            f"Dep: {nxt['Dep']:.1f} km"
                        )
                    else:
                        nxt       = None
                        next_info = '  Next df1   │ (none — this is the last event)'

                    cand_lines = []
                    for k, p in enumerate(valid_pos):
                        r2      = d2.iloc[p]
                        dt_s    = (d2_times[p] - t1_ns) / 1e9
                        xyz_c   = to_cartesian(np.array([r2['Lat']]), np.array([r2['Lon']]),
                                               np.array([r2['Dep']]))
                        dist_km = float(np.linalg.norm(xyz1[0] - xyz_c[0]))
                        cand_lines.append(
                            f"  Candidate {k+1} │ Time: {r2['Time']}  "
                            f"Lat: {r2['Lat']:.4f}  Lon: {r2['Lon']:.4f}  "
                            f"Dep: {r2['Dep']:.1f} km  "
                            f"Δt: {dt_s:+.3f}s  Δd: {dist_km:.2f} km"
                        )

                    phase_option_available  = bulletin_lines is not None
                    double_option_available = has_next
                    valid_choices = {'1', '2', 's', 'sd'}
                    if double_option_available:
                        valid_choices |= {'1d', '2d'}
                    if phase_option_available:
                        valid_choices.add('p')

                    hint_parts = ['1', '2', 's', 'sd']
                    if double_option_available:
                        hint_parts += ['1d', '2d']
                    if phase_option_available:
                        hint_parts.append('p')
                    choice_hint = '[' + ' / '.join(hint_parts) + ']'

                    def _print_prompt() -> None:
                        print(f"\n{sep}")
                        print(f"  AMBIGUOUS MATCH  ({ambiguity_reason})")
                        print(sep)
                        print(df1_info)
                        print(next_info)
                        print(sep)
                        for cl in cand_lines:
                            print(cl)
                        print(sep)
                        print('  1  → assign Candidate 1')
                        print('  2  → assign Candidate 2')
                        if double_option_available:
                            print('  1d → assign Candidate 1  +  drop next df1 event as duplicate')
                            print('  2d → assign Candidate 2  +  drop next df1 event as duplicate')
                        print('  s  → skip this df1 event')
                        print('  sd → skip this df1 event as duplicate of the next one')
                        if phase_option_available:
                            print('  p  → show phases for current & next df1 event')

                    _print_prompt()

                    while True:
                        choice = input(f'  Your choice {choice_hint}: ').strip().lower()
                        if choice not in valid_choices:
                            print(f"  Invalid input — please enter one of: {', '.join(sorted(valid_choices))}.")
                            continue
                        if choice == 'p':
                            _print_phases(row1, 'Current df1 event', sep)
                            if nxt is not None:
                                _print_phases(nxt, 'Next df1 event', sep)
                            else:
                                print('\n  (no next event)')
                            _print_prompt()
                            continue
                        break

                    if choice == 's':
                        print('  → Skipped.\n')
                        logger.info(f"SKIPPED: df1 event at {row1['Time']}")
                        continue

                    if choice == 'sd':
                        pending_extra_bid = row1['BulletinID']
                        print(
                            f"  → Skipped as duplicate of next event.  "
                            f"Unique phases from BulletinID={pending_extra_bid} "
                            f"will be merged into the next matched event.\n"
                        )
                        logger.info(
                            f"SKIPPED as duplicate: df1 event at {row1['Time']}  "
                            f"BulletinID={pending_extra_bid}"
                        )
                        continue

                    drop_next_as_double = choice.endswith('d')
                    chosen_idx          = int(choice[0]) - 1
                    valid_pos           = [valid_pos[chosen_idx]]

                    logger.info(
                        f"AMBIGUOUS resolved: choice={choice!r}  "
                        f"df1_time={row1['Time']}  "
                        f"candidate_time={d2.iloc[valid_pos[0]]['Time']}"
                    )

                    if drop_next_as_double:
                        kept_bid = row1['BulletinID'] if 'BulletinID' in row1.index else None
                        double_drop_map[next_i] = kept_bid
                        print(
                            f"  → Assigned Candidate {choice[0]}  +  "
                            f"next df1 event (index {next_i}, Time: {nxt['Time']}) "
                            f"flagged as duplicate.\n"
                        )
                        logger.info(
                            f"DROPPED next event as duplicate: df1 index={next_i}  "
                            f"time={nxt['Time']}"
                        )
                    else:
                        print(f"  → Assigned Candidate {choice}.\n")

        dt_values  = np.abs(d2_times[valid_pos] - t1_ns)
        best_local = int(np.argmin(dt_values))
        best_pos   = valid_pos[best_local]
        used_df2_indices.add(best_pos)

        matched_row2 = d2.iloc[best_pos]
        out_row      = row1.drop(labels=update_cols).to_dict()
        for col in update_cols:
            out_row[col] = matched_row2[col]

        out_row['_n_candidates']         = len(valid_pos)
        out_row['_has_multiple_matches'] = len(valid_pos) > 1
        out_row['_old_lat']              = row1['Lat']
        out_row['_old_lon']              = row1['Lon']

        if pending_extra_bid is not None and phase_index:
            kept_bid = out_row.get('BulletinID')
            extra    = _diff_phases(kept_bid, pending_extra_bid, phase_index)
            out_row['_extra_phases'] = extra
            out_row['_dropped_i']    = None
            if extra:
                print(
                    f"  INFO: {len(extra)} unique phase(s) from duplicate "
                    f"(BulletinID={pending_extra_bid}) merged into "
                    f"event BulletinID={kept_bid}."
                )
                logger.info(
                    f"MERGED: {len(extra)} phase(s) from BulletinID={pending_extra_bid} "
                    f"into BulletinID={kept_bid}"
                )
            pending_extra_bid = None

        elif drop_next_as_double and phase_index:
            out_row['_extra_phases'] = None
            out_row['_dropped_i']    = next_i

        else:
            out_row['_extra_phases'] = None
            out_row['_dropped_i']    = None

        match_records.append(out_row)

    # Resolve _extra_phases for the 1d/2d path
    for rec in match_records:
        dropped_i = rec.pop('_dropped_i')
        if dropped_i is not None and phase_index:
            kept_bid    = rec.get('BulletinID')
            dropped_bid = d1.iloc[dropped_i]['BulletinID']
            extra       = _diff_phases(kept_bid, dropped_bid, phase_index)
            rec['_extra_phases'] = extra
            if extra:
                print(
                    f"  INFO: {len(extra)} unique phase(s) from duplicate "
                    f"(BulletinID={dropped_bid}) merged into "
                    f"event BulletinID={kept_bid}."
                )
                logger.info(
                    f"MERGED: {len(extra)} phase(s) from BulletinID={dropped_bid} "
                    f"into BulletinID={kept_bid}"
                )

    if not match_records:
        out_cols = [c for c in d1.columns if c not in update_cols] + update_cols
        return pd.DataFrame(columns=out_cols)

    result = pd.DataFrame(match_records).reset_index(drop=True)
    result = result[[
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'MagType', 'MagAuthor',
        'PhaseCount', 'HorUncer', 'VerUncer', 'AzGap', 'RMS',
        'BulletinID', '_extra_phases',
    ]]
    return result


def save_bulletin(parameters, log_dir=None):
    """
    Match the pre-NLL .obs bulletin to the NLL result file and write the
    updated bulletin to disk.

    Parameters
    ----------
    parameters : MatchCatalogsParams
    log_dir    : str, optional — log directory (default: NLL_run/console_output/)

    Returns
    -------
    dict with keys: output, log, n_matched
    """
    log_path = _setup_logger(log_dir or _DEFAULT_LOG_DIR, parameters.save_file)
    logger.info(f"Obs file     : {parameters.file_obs}")
    logger.info(f"Final file   : {parameters.file_final}")
    logger.info(f"Output       : {parameters.save_file}")

    obs_df, lines = _read_obs(parameters.file_obs)
    final_df      = _read_final(parameters.file_final)

    matched = match_catalogues(
        obs_df, final_df,
        max_dt_seconds = 5.0,
        max_dist_km    = 50.0,
        bulletin_lines = lines,
    )

    updated_bulletin = _update_bulletin(lines, matched)

    with open(parameters.save_file, 'w') as f:
        f.writelines(updated_bulletin)

    logger.info(f"Matched      : {len(matched)} events")

    return {
        'output':    parameters.save_file,
        'log':       log_path,
        'n_matched': len(matched),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Match pre-NLL .obs events to NLL-relocated events and write the updated bulletin.'
    )
    parser.add_argument('--obs',    required=True, help='Pre-relocation GLOBAL.obs bulletin')
    parser.add_argument('--final',  required=True, help='NLL result file (FINAL.txt)')
    parser.add_argument('--output', required=True, help='Output updated bulletin file')
    args = parser.parse_args()

    save_bulletin(MatchCatalogsParams(
        file_obs   = args.obs,
        file_final = args.final,
        save_file  = args.output,
    ))


if __name__ == '__main__':
    main()
