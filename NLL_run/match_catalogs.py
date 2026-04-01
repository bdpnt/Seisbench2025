#### MATCH CATALOGS
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
from obspy import UTCDateTime as Timing

## PARAMETERS
file_pre_NLL = '../obs/GLOBAL_W.obs'
file_post_NLL = '../RESULT/GLOBAL_PR_W.txt'

save_file = '../RESULT/FINAL_W.obs'

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

def match_catalogues(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    max_dt_seconds: float = 10.0,
    max_dist_km: float = 50.0,
    min_ambiguous_dt: float = 0.5,
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

    Parameters
    ----------
    df1 : pd.DataFrame
        Primary catalogue. Provides all columns except the four spatial/
        temporal ones.
    df2 : pd.DataFrame
        Reference catalogue. Provides latitude, longitude, depth, and time
        for the matched events.
    max_dt_seconds : float
        Maximum allowed time difference in seconds (default: 10).
    max_dist_km : float
        Maximum allowed 3-D distance in kilometres (default: 50).
    min_ambiguous_dt : float
        Minimum time between matches for an event to not be considered ambiguously matched
        when multiple matches are available.

    Returns
    -------
    pd.DataFrame
        Matched catalogue. Index is reset.
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

    # Work on copies so originals are never mutated
    d1 = df1.copy()
    d2 = df2.copy()

    # Ensure datetime dtype
    d1['Time'] = pd.to_datetime(d1['Time'])
    d2['Time'] = pd.to_datetime(d2['Time'])

    # Sort df2 by time to make the time-proximity search efficient
    d2 = d2.sort_values('Time').reset_index(drop=False)  # keeps original index as 'index'
    d2_times = d2['Time'].values.astype("int64")          # nanoseconds

    # ------------------------------------------------------------------ #
    # 1. Build a 3-D spatial tree on df2 (lat, lon, depth → Cartesian km) #
    # ------------------------------------------------------------------ #
    def to_cartesian(lat_deg, lon_deg, depth_km):
        """Convert geographic coords to Cartesian (km), depth positive down."""
        R = 6371.0  # Earth radius in km
        lat = np.radians(lat_deg)
        lon = np.radians(lon_deg)
        r = R - depth_km          # depth positive downward
        x = r * np.cos(lat) * np.cos(lon)
        y = r * np.cos(lat) * np.sin(lon)
        z = r * np.sin(lat)
        return np.column_stack([x, y, z])

    xyz2 = to_cartesian(
        d2['Lat'].values,
        d2['Lon'].values,
        d2['Dep'].values,
    )
    tree = cKDTree(xyz2)

    # ------------------------------------------------------------------ #
    # 2. Match loop                                                        #
    # ------------------------------------------------------------------ #
    max_dt_ns = int(max_dt_seconds * 1e9)            # convert to nanoseconds
    ambiguous_threshold_ns = int(min_ambiguous_dt * 1e9)

    # A conservative upper bound for the KD-tree query:
    R = 6371.0
    chord_threshold = max_dist_km  # Euclidean km in Cartesian space

    used_df2_indices = set()   # tracks already-matched df2 positions
    match_records = []

    # Pre-sort d1 by time so "next event" is meaningful
    d1 = d1.sort_values('Time').reset_index(drop=True)

    for i, row1 in d1.iterrows():
        t1_ns = row1['Time'].value  # int64 nanoseconds

        # -- Step 1: time window -----------------------------------------
        lo = np.searchsorted(d2_times, t1_ns - max_dt_ns, side="left")
        hi = np.searchsorted(d2_times, t1_ns + max_dt_ns, side="right")

        if lo >= hi:
            continue   # no candidates in time window → drop

        candidates_pos = np.arange(lo, hi)

        # -- Step 2: space window ----------------------------------------
        xyz1 = to_cartesian(
            np.array([row1['Lat']]),
            np.array([row1['Lon']]),
            np.array([row1['Dep']]),
        )
        nearby = tree.query_ball_point(xyz1[0], r=chord_threshold)
        nearby_set = set(nearby)

        valid_pos = [p for p in candidates_pos if p in nearby_set and p not in used_df2_indices]

        if not valid_pos:
            continue   # no candidates pass both filters → drop

        # -- Step 3: interactive resolution of ambiguous matches ---------
        if len(valid_pos) > 1:
            candidate_times = d2_times[valid_pos]

            is_ambiguous = False

            unique_times = np.unique(candidate_times)
            if len(unique_times) == 1:
                is_ambiguous = True
                ambiguity_reason = "all candidates share an identical timestamp"
            else:
                diff_matrix = np.abs(candidate_times[:, None] - candidate_times[None, :])
                min_dt_between_candidates = np.min(diff_matrix[diff_matrix > 0])
                if min_dt_between_candidates < ambiguous_threshold_ns:
                    is_ambiguous = True
                    ambiguity_reason = (
                        f"candidates are within {min_dt_between_candidates/1e9:.2f}s of each other"
                    )

            if is_ambiguous:
                sep = "─" * 72

                # --- df1 event info ---
                df1_info = (
                    f"  df1 event  │ Time: {row1['Time']}  "
                    f"Lat: {row1['Lat']:.4f}  Lon: {row1['Lon']:.4f}  "
                    f"Dep: {row1['Dep']:.1f} km  "
                    f"BullID : {row1['BulletinID']}"
                )

                # --- next df1 event ---
                if i + 1 < len(d1):
                    nxt = d1.iloc[i + 1]
                    next_info = (
                        f"  Next df1   │ Time: {nxt['Time']}  "
                        f"Lat: {nxt['Lat']:.4f}  Lon: {nxt['Lon']:.4f}  "
                        f"Dep: {nxt['Dep']:.1f} km"
                    )
                else:
                    next_info = "  Next df1   │ (none — this is the last event)"

                # --- candidate info (always two per the docstring assumption) ---
                cand_lines = []
                for k, p in enumerate(valid_pos):
                    r2 = d2.iloc[p]
                    dt_s = (d2_times[p] - t1_ns) / 1e9
                    xyz_c = to_cartesian(
                        np.array([r2['Lat']]),
                        np.array([r2['Lon']]),
                        np.array([r2['Dep']]),
                    )
                    dist_km = float(np.linalg.norm(xyz1[0] - xyz_c[0]))
                    cand_lines.append(
                        f"  Candidate {k+1} │ Time: {r2['Time']}  "
                        f"Lat: {r2['Lat']:.4f}  Lon: {r2['Lon']:.4f}  "
                        f"Dep: {r2['Dep']:.1f} km  "
                        f"Δt: {dt_s:+.3f}s  Δd: {dist_km:.2f} km"
                    )

                print(f"\n{sep}")
                print(f"  AMBIGUOUS MATCH  ({ambiguity_reason})")
                print(sep)
                print(df1_info)
                print(next_info)
                print(sep)
                for line in cand_lines:
                    print(line)
                print(sep)
                print("  1 → assign Candidate 1")
                print("  2 → assign Candidate 2")
                print("  s → skip this df1 event")

                while True:
                    choice = input("  Your choice [1 / 2 / s]: ").strip().lower()
                    if choice in ("1", "2", "s"):
                        break
                    print("  Invalid input — please enter 1, 2, or s.")

                if choice == "s":
                    print(f"  → Skipped.\n")
                    continue
                else:
                    chosen_idx = int(choice) - 1
                    valid_pos = [valid_pos[chosen_idx]]
                    print(f"  → Assigned Candidate {choice}.\n")

        # -- Step 4: pick closest in time among valid candidates ---------
        dt_values = np.abs(d2_times[valid_pos] - t1_ns)
        best_local = int(np.argmin(dt_values))
        best_pos = valid_pos[best_local]

        used_df2_indices.add(best_pos)

        # -- Step 5: build output row ------------------------------------
        matched_row2 = d2.iloc[best_pos]

        out_row = row1.drop(labels=update_cols).to_dict()

        for col in update_cols:
            out_row[col] = matched_row2[col]

        n = len(valid_pos)
        out_row['_n_candidates'] = n
        out_row['_has_multiple_matches'] = n > 1
        out_row['_old_lat'] = row1['Lat']
        out_row['_old_lon'] = row1['Lon']

        match_records.append(out_row)

    # ------------------------------------------------------------------ #
    # 3. Assemble result                                                   #
    # ------------------------------------------------------------------ #
    if not match_records:
        out_cols = [c for c in d1.columns if c not in update_cols] + update_cols + ["_df2_idx"]
        return pd.DataFrame(columns=out_cols)

    result = pd.DataFrame(match_records).reset_index(drop=True)
    result = result[['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','MagType','MagAuthor','PhaseCount','HorUncer','VerUncer','AzGap','RMS','BulletinID']]
    return result

def update_bulletin(lines, matched_df):
    blocks = []
    current_block = []
    event_indices = []  # Store the index of the event line for each block

    # Split the file into blocks and precompute event line indices
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
        event_indices.append(len(lines) - len(current_block))  # Store the event line index for the last block

    # Process blocks: update or skip based on BulletinID
    updated_blocks = []
    for block, event_index in zip(blocks, event_indices):
        if not block:
            continue
        row = matched_df[matched_df.BulletinID == event_index]
        if not row.empty:
            # Update the event line (replace with your dataframe data)
            updated_event_line = f"# {str(row.Year.iloc[0])} {str(row.Month.iloc[0])} {str(row.Day.iloc[0])} {str(row.Hour.iloc[0])} {str(row.Min.iloc[0])} {str(row.Sec.iloc[0])} " \
                + f"{str(row.Lat.iloc[0])} {str(row.Lon.iloc[0])} {str(row.Dep.iloc[0])} {str(row.Mag.iloc[0])} {str(row.MagType.iloc[0])} {str(row.MagAuthor.iloc[0])} " \
                + f"{str(row.PhaseCount.iloc[0])} {str(row.HorUncer.iloc[0])} {str(row.VerUncer.iloc[0])} {str(row.AzGap.iloc[0])} {str(row.RMS.iloc[0])}\n"
            updated_block = [updated_event_line] + [line for line in block[1:]]
            updated_blocks.append(updated_block)

    # Reconstruct the file content
    lines[0] = f'### Bulletin generated on the {Timing.now()}\n'
    updated_content = lines[0:4]  # Use header lines
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
)

updated_bulletin = update_bulletin(lines_pre_NLL, matched)

save_bulletin(updated_bulletin, save_file)