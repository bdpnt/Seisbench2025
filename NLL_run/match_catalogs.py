#### MATCH CATALOGS
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
from obspy import UTCDateTime as Timing

## PARAMETERS
file_pre_NLL = 'obs/GLOBAL_W.obs'
file_post_NLL = 'RESULT/GLOBAL_PR_W.txt'

save_file = 'RESULT/FINAL_W.obs'

## FUNCTION
def read_file(file):
    with open(file, 'r') as f:
        lines = f.readlines()
    return lines

# Pre NLL
lines_pre_NLL = read_file(file_pre_NLL)

pre_NLL = [
    [*line.lstrip('# ').rstrip('\n').split(), idx] 
    for idx, line in enumerate(lines_pre_NLL) 
    if line.startswith('# ')
]

pre_df = pd.DataFrame(pre_NLL, columns=['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','MagType','MagAuthor','PhaseCount','HorUncer','VerUncer','AzGap','RMS','BulletinID'])

cols_to_num = ['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','PhaseCount','HorUncer','VerUncer','AzGap','RMS']
pre_df[cols_to_num] = pre_df[cols_to_num].apply(pd.to_numeric, errors='coerce')

pre_df['Time'] = pd.to_datetime(
    pre_df['Year'].astype(str) + '-' \
    + pre_df['Month'].astype(str) + '-' \
    + pre_df['Day'].astype(str) + 'T' \
    + pre_df['Hour'].astype(str) + ':' \
    + pre_df['Min'].astype(str) + ':' \
    + pre_df['Sec'].astype(str) + 'Z'
)

del pre_NLL

# Post NLL
lines_post_NLL = read_file(file_post_NLL)

post_NLL = [line.rstrip('\n').split() for line in lines_post_NLL]
post_NLL = [[int(line[0]) + 1900 if int(line[0]) > 75 else int(line[0]) + 2000] + line[1:] for line in post_NLL]

post_df = pd.DataFrame(post_NLL, columns=['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','RMS','PhaseCount','HorUncer','VerUncer','AzGap'])

cols_to_num = ['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','PhaseCount','HorUncer','VerUncer','AzGap','RMS']
post_df[cols_to_num] = post_df[cols_to_num].apply(pd.to_numeric, errors='coerce')

# Short Fix for under 0 seconds event
post_df['Sec'] = [sec if sec >= 0 else 0 for sec in post_df['Sec']]

post_df['Time'] = pd.to_datetime(
    post_df['Year'].astype(str) + '-' \
    + post_df['Month'].astype(str) + '-' \
    + post_df['Day'].astype(str) + 'T' \
    + post_df['Hour'].astype(str) + ':' \
    + post_df['Min'].astype(str) + ':' \
    + post_df['Sec'].astype(str) + 'Z'
)

del lines_post_NLL, post_NLL

def _phase_key(phase_line: str) -> tuple:
    """
    Return a (station, phase_type) tuple that uniquely identifies a phase
    regardless of timing differences or '?' vs '*' wildcards.

    Phase line format (space-separated tokens):
      col 0 : station  e.g. "FR.0035"
      col 1 : ?/*
      col 2 : ?/*
      col 3 : ?/*
      col 4 : phase type  e.g. "P" or "S"
      ...
    """
    tokens = phase_line.split()
    if len(tokens) < 5:
        return None   # malformed line — ignore
    return (tokens[0], tokens[4])


def _diff_phases(kept_bid: int, dropped_bid: int, phase_index: dict) -> list:
    """
    Return phase lines from the dropped event that are NOT already present
    in the kept event, compared by (station, phase_type) key only.

    Parameters
    ----------
    kept_bid : int
        BulletinID of the event that is kept.
    dropped_bid : int
        BulletinID of the event that is dropped as a duplicate.
    phase_index : dict
        Maps BulletinID → list of raw phase strings (no trailing newline).

    Returns
    -------
    list of str
        Phase lines from the dropped event that are new to the kept event.
        Returns an empty list if phase_index is empty or BulletinIDs are missing.
    """
    if not phase_index:
        return []

    kept_phases    = phase_index.get(kept_bid,    [])
    dropped_phases = phase_index.get(dropped_bid, [])

    kept_keys = {_phase_key(p) for p in kept_phases if _phase_key(p) is not None}

    extra = []
    for ph in dropped_phases:
        key = _phase_key(ph)
        if key is not None and key not in kept_keys:
            extra.append(ph)
    return extra


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
      1. Find all df2 candidates within `max_dt_seconds`.
      2. Among those, keep only candidates within `max_dist_km`.
      3. Among survivors, pick the one closest in time.
      4. Matching is strictly one-to-one: once a df2 event is assigned,
         it is no longer available for other df1 events.
      5. df1 events with no valid match are dropped. Ambiguously matched
         events prompt the user to pick a candidate or skip the event.
         When `bulletin_lines` is provided, the user may also press 'p'
         to inspect the phases of the current and next df1 events before
         making their choice.

    Interactive choices at an ambiguous prompt
    ------------------------------------------
    1   → assign Candidate 1 to the current df1 event
    2   → assign Candidate 2 to the current df1 event
    1d  → assign Candidate 1 AND drop the next df1 event as a duplicate;
          unique phases from the next event are merged into this one
    2d  → assign Candidate 2 AND drop the next df1 event as a duplicate;
          unique phases from the next event are merged into this one
    s   → skip the current df1 event (no match recorded)
    sd  → skip the current df1 event AND flag it as a duplicate of the
          next one; its unique phases will be merged into the next event
    p   → (only when bulletin_lines supplied) print phase lines for the
          current and next df1 events, then re-display the prompt

    Parameters
    ----------
    df1 : pd.DataFrame
        Primary catalogue. Must contain a 'BulletinID' column when
        `bulletin_lines` is supplied.
    df2 : pd.DataFrame
        Reference catalogue. Provides spatial/temporal columns for matched events.
    max_dt_seconds : float
        Maximum allowed time difference in seconds (default: 10).
    max_dist_km : float
        Maximum allowed 3-D distance in kilometres (default: 50).
    min_ambiguous_dt : float
        Minimum time separation between candidates for the match to be
        considered unambiguous (default: 0.5 s).
    bulletin_lines : list of str, optional
        Raw bulletin file as a list of lines (e.g. open(...).readlines()).
        Lines starting with "# " are event headers whose list index is the
        BulletinID stored in df1. Phase lines follow until the next blank line.
        Enables the 'p' prompt option and phase-merging for duplicates.

    Returns
    -------
    pd.DataFrame
        Matched catalogue with an added '_extra_phases' column.
        '_extra_phases' is a (possibly empty) list of raw phase strings
        harvested from a dropped duplicate event, or None when no duplicate
        was flagged for that event.  Index is reset.
    """

    update_cols = ['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','RMS','PhaseCount','HorUncer','VerUncer','AzGap']

    # ------------------------------------------------------------------ #
    # 0. Sanity checks                                                     #
    # ------------------------------------------------------------------ #
    for col in update_cols:
        if col not in df1.columns:
            raise ValueError(f"Column '{col}' not found in df1.")
        if col not in df2.columns:
            raise ValueError(f"Column '{col}' not found in df2.")

    if bulletin_lines is not None and 'BulletinID' not in df1.columns:
        raise ValueError("df1 must contain a 'BulletinID' column when bulletin_lines is provided.")

    # Work on copies so originals are never mutated
    d1 = df1.copy()
    d2 = df2.copy()

    # Ensure datetime dtype
    d1['Time'] = pd.to_datetime(d1['Time'])
    d2['Time'] = pd.to_datetime(d2['Time'])

    # Sort df2 by time to make the time-proximity search efficient
    d2 = d2.sort_values('Time').reset_index(drop=False)
    d2_times = d2['Time'].values.astype("int64")   # nanoseconds

    # ------------------------------------------------------------------ #
    # 0b. Pre-index phases from bulletin_lines (if provided)              #
    # ------------------------------------------------------------------ #
    phase_index: dict = {}
    if bulletin_lines is not None:
        current_id = None
        for line_idx, line in enumerate(bulletin_lines):
            if line.startswith("# "):
                current_id = line_idx
                phase_index[current_id] = []
            elif line.startswith("\n") or line == "":
                current_id = None
            elif current_id is not None:
                phase_index[current_id].append(line.rstrip("\n"))

    def _print_phases(event_row, label: str, sep: str) -> None:
        bid    = event_row['BulletinID']
        phases = phase_index.get(bid, [])
        print(f"\n  {label} phases  (BulletinID={bid})")
        print(sep)
        if phases:
            for ph in phases:
                print(f"    {ph}")
        else:
            print("    (no phases found for this BulletinID)")
        print(sep)

    # ------------------------------------------------------------------ #
    # 1. Build a 3-D spatial tree on df2                                   #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 2. Match loop                                                        #
    # ------------------------------------------------------------------ #
    max_dt_ns              = int(max_dt_seconds    * 1e9)
    ambiguous_threshold_ns = int(min_ambiguous_dt  * 1e9)
    chord_threshold        = max_dist_km

    used_df2_indices = set()
    # Maps dropped df1 index → BulletinID of the kept event it is a double of,
    # so we can compute extra phases when we build the kept event's output row.
    double_drop_map: dict  = {}   # { dropped_i: kept_bid }  (for 1d/2d)
    # BulletinID of a skipped event whose phases should be merged into the
    # NEXT matched event (set by the 'sd' choice, cleared on first use).
    pending_extra_bid: int = None

    match_records = []

    d1 = d1.sort_values('Time').reset_index(drop=True)

    for i, row1 in d1.iterrows():

        # -- Double-drop check (1d / 2d path) ----------------------------
        if i in double_drop_map:
            print(
                f"  DROPPED (duplicate): df1 event at {row1['Time']} "
                f"(flagged as double of the event at index {i - 1})."
            )
            continue

        t1_ns = row1['Time'].value

        # -- Step 1: time window -----------------------------------------
        lo = np.searchsorted(d2_times, t1_ns - max_dt_ns, side="left")
        hi = np.searchsorted(d2_times, t1_ns + max_dt_ns, side="right")
        if lo >= hi:
            continue

        candidates_pos = np.arange(lo, hi)

        # -- Step 2: space window ----------------------------------------
        xyz1 = to_cartesian(
            np.array([row1['Lat']]), np.array([row1['Lon']]), np.array([row1['Dep']])
        )
        nearby     = tree.query_ball_point(xyz1[0], r=chord_threshold)
        nearby_set = set(nearby)
        valid_pos  = [p for p in candidates_pos if p in nearby_set and p not in used_df2_indices]

        if not valid_pos:
            continue

        # -- Step 3: interactive resolution of ambiguous matches ---------
        drop_next_as_double = False   # set True by 1d/2d
        next_i              = None

        if len(valid_pos) > 1:
            candidate_times = d2_times[valid_pos]
            is_ambiguous    = False

            unique_times = np.unique(candidate_times)
            if len(unique_times) == 1:
                is_ambiguous     = True
                ambiguity_reason = "all candidates share an identical timestamp"
            else:
                diff_matrix    = np.abs(candidate_times[:, None] - candidate_times[None, :])
                min_dt_between = np.min(diff_matrix[diff_matrix > 0])
                if min_dt_between < ambiguous_threshold_ns:
                    is_ambiguous     = True
                    ambiguity_reason = (
                        f"candidates are within {min_dt_between/1e9:.2f}s of each other"
                    )

            if is_ambiguous:
                sep = "─" * 72

                df1_info = (
                    f"  df1 event  │ Time: {row1['Time']}  "
                    f"Lat: {row1['Lat']:.4f}  Lon: {row1['Lon']:.4f}  "
                    f"Dep: {row1['Dep']:.1f} km"
                )

                # Next unprocessed df1 event (skip already-queued drops)
                next_i = i + 1
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
                    next_info = "  Next df1   │ (none — this is the last event)"

                cand_lines = []
                for k, p in enumerate(valid_pos):
                    r2      = d2.iloc[p]
                    dt_s    = (d2_times[p] - t1_ns) / 1e9
                    xyz_c   = to_cartesian(
                        np.array([r2['Lat']]), np.array([r2['Lon']]), np.array([r2['Dep']])
                    )
                    dist_km = float(np.linalg.norm(xyz1[0] - xyz_c[0]))
                    cand_lines.append(
                        f"  Candidate {k+1} │ Time: {r2['Time']}  "
                        f"Lat: {r2['Lat']:.4f}  Lon: {r2['Lon']:.4f}  "
                        f"Dep: {r2['Dep']:.1f} km  "
                        f"Δt: {dt_s:+.3f}s  Δd: {dist_km:.2f} km"
                    )

                phase_option_available  = bulletin_lines is not None
                double_option_available = has_next
                valid_choices = {"1", "2", "s", "sd"}
                if double_option_available:
                    valid_choices |= {"1d", "2d"}
                if phase_option_available:
                    valid_choices.add("p")

                hint_parts = ["1", "2", "s", "sd"]
                if double_option_available:
                    hint_parts += ["1d", "2d"]
                if phase_option_available:
                    hint_parts.append("p")
                choice_hint = "[" + " / ".join(hint_parts) + "]"

                def _print_prompt() -> None:
                    print(f"\n{sep}")
                    print(f"  AMBIGUOUS MATCH  ({ambiguity_reason})")
                    print(sep)
                    print(df1_info)
                    print(next_info)
                    print(sep)
                    for line in cand_lines:
                        print(line)
                    print(sep)
                    print("  1  → assign Candidate 1")
                    print("  2  → assign Candidate 2")
                    if double_option_available:
                        print("  1d → assign Candidate 1  +  drop next df1 event as duplicate")
                        print("  2d → assign Candidate 2  +  drop next df1 event as duplicate")
                    print("  s  → skip this df1 event")
                    print("  sd → skip this df1 event as duplicate of the next one")
                    if phase_option_available:
                        print("  p  → show phases for current & next df1 event")

                _print_prompt()

                while True:
                    choice = input(f"  Your choice {choice_hint}: ").strip().lower()
                    if choice not in valid_choices:
                        print(f"  Invalid input — please enter one of: {', '.join(sorted(valid_choices))}.")
                        continue
                    if choice == "p":
                        _print_phases(row1, "Current df1 event", sep)
                        if nxt is not None:
                            _print_phases(nxt, "Next df1 event", sep)
                        else:
                            print("\n  (no next event)")
                        _print_prompt()
                        continue
                    break

                # -- Handle skip choices ---------------------------------
                if choice == "s":
                    print(f"  → Skipped.\n")
                    continue

                if choice == "sd":
                    # Drop this event, carry its BulletinID forward so the
                    # next matched event can absorb its unique phases.
                    pending_extra_bid = row1['BulletinID']
                    print(
                        f"  → Skipped as duplicate of next event.  "
                        f"Unique phases from BulletinID={pending_extra_bid} "
                        f"will be merged into the next matched event.\n"
                    )
                    continue

                # -- Handle assign choices (1, 2, 1d, 2d) ----------------
                drop_next_as_double = choice.endswith("d")
                chosen_idx          = int(choice[0]) - 1
                valid_pos           = [valid_pos[chosen_idx]]

                if drop_next_as_double:
                    kept_bid = row1['BulletinID'] if 'BulletinID' in row1.index else None
                    double_drop_map[next_i] = kept_bid
                    print(
                        f"  → Assigned Candidate {choice[0]}  +  "
                        f"next df1 event (index {next_i}, Time: {nxt['Time']}) "
                        f"flagged as duplicate.\n"
                    )
                else:
                    print(f"  → Assigned Candidate {choice}.\n")

        # -- Step 4: pick closest in time among valid candidates ---------
        dt_values  = np.abs(d2_times[valid_pos] - t1_ns)
        best_local = int(np.argmin(dt_values))
        best_pos   = valid_pos[best_local]
        used_df2_indices.add(best_pos)

        # -- Step 5: build output row ------------------------------------
        matched_row2 = d2.iloc[best_pos]
        out_row      = row1.drop(labels=update_cols).to_dict()
        for col in update_cols:
            out_row[col] = matched_row2[col]

        out_row['_n_candidates']        = len(valid_pos)
        out_row['_has_multiple_matches'] = len(valid_pos) > 1
        out_row['_old_lat']             = row1['Lat']
        out_row['_old_lon']             = row1['Lon']

        # -- Step 6: attach extra phases ---------------------------------
        # Two possible sources, resolved in priority order:
        #   (a) sd path  → pending_extra_bid was set by the previous iteration
        #   (b) 1d/2d path → drop_next_as_double is True; resolve post-loop
        #                    via _dropped_i (same mechanism as before)

        if pending_extra_bid is not None and phase_index:
            # (a) The previous event was skipped as a duplicate of this one
            kept_bid  = out_row.get('BulletinID')
            extra     = _diff_phases(kept_bid, pending_extra_bid, phase_index)
            out_row['_extra_phases'] = extra
            out_row['_dropped_i']    = None
            n_extra = len(extra)
            if n_extra:
                print(
                    f"  INFO: {n_extra} unique phase(s) from duplicate "
                    f"(BulletinID={pending_extra_bid}) merged into "
                    f"event BulletinID={kept_bid}."
                )
            pending_extra_bid = None   # consumed — reset for next iteration

        elif drop_next_as_double and phase_index:
            # (b) The next event will be dropped; resolve after the loop
            out_row['_extra_phases'] = None
            out_row['_dropped_i']    = next_i

        else:
            out_row['_extra_phases'] = None
            out_row['_dropped_i']    = None

        match_records.append(out_row)

    # ------------------------------------------------------------------ #
    # 3. Resolve _extra_phases for the 1d/2d path (post-loop)            #
    # ------------------------------------------------------------------ #
    for rec in match_records:
        dropped_i = rec.pop('_dropped_i')
        if dropped_i is not None and phase_index:
            kept_bid    = rec.get('BulletinID')
            dropped_bid = d1.iloc[dropped_i]['BulletinID']
            extra       = _diff_phases(kept_bid, dropped_bid, phase_index)
            rec['_extra_phases'] = extra
            n_extra = len(extra)
            if n_extra:
                print(
                    f"  INFO: {n_extra} unique phase(s) from duplicate "
                    f"(BulletinID={dropped_bid}) merged into "
                    f"event BulletinID={kept_bid}."
                )

    # ------------------------------------------------------------------ #
    # 4. Assemble result                                                   #
    # ------------------------------------------------------------------ #
    if not match_records:
        out_cols = [c for c in d1.columns if c not in update_cols] + update_cols + ["_df2_idx"]
        return pd.DataFrame(columns=out_cols)

    result = pd.DataFrame(match_records).reset_index(drop=True)
    result = result[[
        'Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep',
        'Mag','MagType','MagAuthor','PhaseCount','HorUncer','VerUncer',
        'AzGap','RMS','BulletinID',
        '_extra_phases',
    ]]
    return result


# ======================================================================= #


def update_bulletin(lines, matched_df):
    """
    Rebuild a bulletin from `lines`, keeping only events present in
    `matched_df` and updating their header lines with the matched values.

    If a row in `matched_df` carries a non-empty '_extra_phases' list,
    those phase lines (unique phases harvested from a dropped duplicate)
    are appended at the end of the event's phase block, before the
    trailing blank line.

    Parameters
    ----------
    lines : list of str
        Raw bulletin lines (e.g. from open(...).readlines()).
    matched_df : pd.DataFrame
        Output of match_catalogues().  Must contain 'BulletinID' and,
        optionally, '_extra_phases'.

    Returns
    -------
    list of str
        Updated bulletin lines, ready to be written to disk.
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
        event_indices.append(len(lines) - len(current_block))

    updated_blocks = []
    for block, event_index in zip(blocks, event_indices):
        if not block:
            continue

        row = matched_df[matched_df.BulletinID == event_index]
        if row.empty:
            continue   # event was not matched — drop it

        r = row.iloc[0]

        # --- rebuild the header line ---
        updated_event_line = (
            f"# {r.Year} {r.Month} {r.Day} {r.Hour} {r.Min} {r.Sec} "
            f"{r.Lat} {r.Lon} {r.Dep} {r.Mag} {r.MagType} {r.MagAuthor} "
            f"{r.PhaseCount} {r.HorUncer} {r.VerUncer} {r.AzGap} {r.RMS}\n"
        )

        # --- split existing block into phase lines and trailing blank lines ---
        phase_lines    = [l for l in block[1:] if not (l.startswith("\n") or l == "")]
        trailing_blank = [l for l in block[1:] if      l.startswith("\n") or l == ""]

        # --- append extra phases from a merged duplicate (if any) ---
        try:
            extra = r['_extra_phases']
        except (KeyError, TypeError):
            extra = None

        if extra is not None and len(extra) > 0:
            extra_lines = [ph if ph.endswith("\n") else ph + "\n" for ph in extra]
            phase_lines = phase_lines + extra_lines

        updated_blocks.append([updated_event_line] + phase_lines + trailing_blank)

    # --- reconstruct file ---
    lines[0] = f'### Bulletin generated on the {Timing.now()}\n'
    updated_content = lines[0:4]
    for block in updated_blocks:
        updated_content.extend(block)

    return updated_content

def save_bulletin(lines,save_file):
    with open(save_file, 'w') as f:
        f.writelines(lines)
    print(f'Succesfully saved Bulletin @ {save_file}')

## RUN CODE

matched = match_catalogues(
    pre_df, post_df,
    max_dt_seconds=5.0,
    max_dist_km=50.0,
    bulletin_lines=lines_pre_NLL,
)

updated_bulletin = update_bulletin(lines_pre_NLL, matched)

save_bulletin(updated_bulletin, save_file)