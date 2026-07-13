# Full Codebase Audit — 2026-07-12

**Scope:** Pipeline Python sources — `run_NLL.py`, `run_SSST.py`, `add_temp_picks.py`, `build_global_bulletin.py`, `build_global_inventory.py`, and modules under `NLL_run/`, `global_obs/`, `fetch_inventory/`, `fetch_obs/`, `temp_picks/`. Excluded from this pass: `codes_other/`, `.ipynb_checkpoints/`, `complem_figures/`, `zone_Arette/`, top-level `generate_complem_*.py`, `run_gamma_detection.py`, and a few small helpers (`fetch_obs/{ICGC,IGN,LDG,RESIF}.py`, `global_obs/{add_temporary_picks,list_magnitude_types,plot_global_catalog_map}.py`, `fetch_inventory/_convert_csv_to_stationxml.py`, `fetch_inventory/_remove_fdsn_duplicates.py`, `temp_picks/{build_theoretical_tables,plot_travel_times}.py`) — visualization and legacy code.

**Files scanned:** 26 core pipeline modules
**Issues found:** 15 (2 high, 9 medium, 4 low)

---

## Logic errors

### NLL_run/append_station_delays.py

```
File: NLL_run/append_station_delays.py
Line: 117
Category: Logic error
Severity: High
Issue: `statCorr_list = [lines[i + 3] for i in idx]` mixes two different index spaces. `idx` are DataFrame row indices (0..N-1 across LOCDELAY-only rows), but they are used to index `lines` — the full file including headers — with a hard-coded offset of +3. This is only correct if (a) LOCDELAY lines start at exactly line 3 in the file, and (b) they are strictly contiguous with no blank/comment lines between them. Any deviation in NLL's `last.stat_totcorr` layout picks up the wrong lines and appends garbage as station delays.
Suggestion: Build a parallel `locdelay_line_numbers` list at the same time as `statCorr` (single pass) and index that:
    locdelay_lines = [(i, line) for i, line in enumerate(lines) if line.startswith('LOCDELAY')]
    statCorr = [line.split()[1:6] for _, line in locdelay_lines]
    ...
    statCorr_list = [locdelay_lines[i][1] for i in idx]
```

### NLL_run/generate_regional_runfiles.py

```
File: NLL_run/generate_regional_runfiles.py
Line: 106-118 (_build_alternate_code_map)
Category: Logic error
Severity: Medium
Issue: `network_code` and `station_code` are assigned only inside the inner `if code_line.startswith('  Station'):` branch. If an "Alternate Code" block is malformed and has no `Station` line, the previous iteration's values leak into `code_map[alternate_code]`, silently associating the alternate code with the wrong station. If the FIRST block is malformed, `NameError` is raised, but for any later malformed block the association is silently wrong.
Suggestion: Initialise `network_code = station_code = None` at the start of the outer loop and only add to `code_map` when both are set.
```

### global_obs/fuse_bulletins.py

```
File: global_obs/fuse_bulletins.py
Line: 603
Category: Logic error
Severity: Medium
Issue: `found_possible.append(possible_row.index[0])` records the FIRST index of the candidate frame regardless of which candidate row was actually validated by the pick check. If `possible_row` has ≥2 rows and the second is the one that passes `sim_picks >= 1`, we still record the index of the first — later dropped via `possible_match.drop(found_possible)`, which then drops the wrong row from `possible_match`.
Suggestion: Record `row.name` (the index label of the row currently being iterated) instead: `found_possible.append(row.name)`.
```

```
File: global_obs/fuse_bulletins.py
Line: 316
Category: Logic error
Severity: Low
Issue: `list(all_phases.keys()).index(phase_key)` rebuilds a full key list and does a linear scan on every duplicate pick. Correct because dict preserves insertion order and `all_times` has one entry per key, but this is fragile and O(N²) — see performance section.
Suggestion: Keep a `phase_key -> time_str` dict instead of two parallel structures; the index lookup disappears.
```

### fetch_obs/OMP.py

```
File: fetch_obs/OMP.py
Line: 158-160
Category: Logic error
Severity: Medium
Issue: When `second >= 60`, code decrements `second` and increments `minute`, but does not cascade further (`minute` may then be ≥ 60, `hour` might need bumping, etc.). The subsequent `UTCDateTime` validation catches invalid values by SKIPPING the event, so a malformed source row silently drops a real event instead of being repaired.
Suggestion: Build the origin time with `datetime + timedelta(seconds=second)` so overflow cascades naturally to minute/hour/day.
```

```
File: fetch_obs/OMP.py
Line: 200-203
Category: Logic error
Severity: Medium
Issue: `if quality_p == '4' or quality_s == '0': ... continue` skips the ENTIRE phase (both P and S) when S has quality 0. If quality 0 for S means "no S pick" (rather than "bad S"), this silently drops legitimate P picks whenever an event has no S reading at that station.
Suggestion: Verify OMP quality-0 semantics against the source-format docs; if quality 0 == "no S", the check should only skip the S write, not the whole phase.
```

```
File: fetch_obs/OMP.py
Line: 206
Category: Logic error
Severity: Low
Issue: `int(quality_p) >= 2 or int(quality_s) >= 3` crashes on non-digit characters (spaces, '?', etc.). Reachable only when quality_p ∉ {'4','9'} and quality_s ≠ '0' and station ≠ 'LARF'.
Suggestion: `int(quality_p) if quality_p.isdigit() else 0`, same for S.
```

### global_obs/filter_events_by_aoi.py

```
File: global_obs/filter_events_by_aoi.py
Line: 202-212
Category: Logic error
Severity: Medium
Issue: The output-rebuild loop calls `new_lines.pop(-1)` when an out-of-AOI event header is encountered — meant to remove the blank line preceding a dropped event. But (a) it assumes there IS a blank line just before every '# ' header, and (b) for two consecutive out-of-AOI events, the blank between them is never appended (because we don't hit the `line.startswith('\n')` branch for a header that's in the ELIF chain, but we did fall through), so the pop can silently remove the header of a KEPT event instead. Also, `while not lines[i].startswith('\n')` has no `i < len(lines)` bound and IndexErrors if the file lacks a trailing blank.
Suggestion: Iterate once, tracking a "current block" (header + picks + blank) and emit or drop the block atomically, rather than rebuilding line-by-line with `pop`.
```

### fetch_inventory/_fill_missing_elevations.py

```
File: fetch_inventory/_fill_missing_elevations.py
Line: 37
Category: Logic error
Severity: Low
Issue: `requests.get(url).json()` — no timeout. On a stalled server the call blocks indefinitely, hanging the whole inventory build.
Suggestion: `requests.get(url, timeout=10)`.
```

### global_obs/apply_magnitude_models.py

```
File: global_obs/apply_magnitude_models.py
Line: 187-188
Category: Logic error
Severity: Low
Issue: `model_ge_2 = list(models.values())[0]` / `model_lt_2 = list(models.values())[1]` relies on dict insertion order matching a specific convention (M≥2 first). Currently correct because `generate_magnitude_models.py:539-541` inserts them that way, but silently produces wrong magnitudes if the joblib is ever re-saved with the other order.
Suggestion: Look up by label, e.g. `models[label_geq]`, using a shared label constant.
```

---

## Performance issues

### global_obs/remap_picks_to_unified_codes.py

```
File: global_obs/remap_picks_to_unified_codes.py
Line: 86-96 (find_unique_stations)
Category: Performance
Severity: Medium
Issue: Grows a DataFrame with `pd.concat([df, pd.DataFrame([row])])` inside a loop over every station. That's the classic O(N²) DataFrame-growth antipattern; each concat copies the accumulator. On a ~2k-station inventory, this runs seconds-to-minutes when it should be milliseconds.
Suggestion: Append plain dicts to a list, then call `pd.DataFrame(rows)` once after the loop.
```

```
File: global_obs/remap_picks_to_unified_codes.py
Line: 119
Category: Performance
Severity: Medium
Issue: `unique_sta.index[unique_sta.Code == station_name].tolist()` scans the entire `unique_sta` DataFrame for EVERY pick line. Cost is O(P × S) where P = picks (10⁵–10⁶) and S = stations. Dominates runtime of the whole remap step.
Suggestion: Build `code_to_indices = unique_sta.groupby('Code').indices` once, then `matching = list(code_to_indices.get(station_name, []))`.
```

### NLL_run/filter_distant_picks.py

```
File: NLL_run/filter_distant_picks.py
Line: 149
Category: Performance
Severity: Medium
Issue: `sta_coords[sta_coords.AlternateCode == alt_code]` scans the full station-coords DataFrame for every pick line in the global bulletin. `remove_far_picks` is invoked once per pipeline run but on a ~10⁶-line file that adds noticeable wall-time.
Suggestion: Build `code_to_latlon = dict(zip(sta_coords.AlternateCode, zip(sta_coords.Latitude, sta_coords.Longitude)))` once before the loop, then look up in O(1).
```

### global_obs/fuse_bulletins.py

```
File: global_obs/fuse_bulletins.py
Line: 549-550
Category: Performance
Severity: Medium
Issue: `strict_match[strict_match.catalog1_idx == event_idx1]` and the corresponding `possible_match` filter run inside a loop over every event in `main_bulletin`. That's O(N × M) for the concatenation step, repeated once per secondary bulletin (~6 sources). Adds a big fixed cost to the fusion.
Suggestion: `strict_by_idx = strict_match.groupby('catalog1_idx')` once, then `match_row = strict_by_idx.get_group(event_idx1)` guarded with a membership check; same for `possible_match`.
```

```
File: global_obs/fuse_bulletins.py
Line: 316
Category: Performance
Severity: Low
Issue: `list(all_phases.keys()).index(phase_key)` on every duplicate phase makes `check_similar_picks` O(K²) in the number of unique phases K, called per candidate event pair. K is small (~30) so real cost is negligible, but the pattern shows up hot in profiling.
Suggestion: Store the recorded arrival time in the same dict as the count, e.g. `all_phases[phase_key] = {'count': 1, 'time': phase_time}`.
```

### global_obs/filter_events_by_aoi.py

```
File: global_obs/filter_events_by_aoi.py
Line: 205
Category: Performance
Severity: Low
Issue: `events_df.loc[events_df.ID == idx, 'inAOI'].values[0]` runs a linear DataFrame scan for every event header line. Cost is O(N²) in event count; a ~10k-event catalog runs multiple seconds when it should be sub-second.
Suggestion: `id_to_inaoi = dict(zip(events_df.ID, events_df.inAOI))` once, then `id_to_inaoi[idx]`.
```

### NLL_run/merge_regional_results.py

```
File: NLL_run/merge_regional_results.py
Line: 167-172
Category: Performance
Severity: Low
Issue: `merged.apply(lambda r: _compute_true_erh(*r[_ell_args]), axis=1)` computes an eigen-decomposition per row via Python-level dispatch. Fine for the ~10³ merged events but scales poorly if the pipeline grows.
Suggestion: If needed later, vectorise: build 2D arrays of the ellipsoid vectors, then apply `np.linalg.eigvalsh` on the stacked 2×2 blocks.
```

---

## Summary

| File | Logic errors | Performance issues |
|------|--------------|--------------------|
| NLL_run/append_station_delays.py | 1 High | – |
| NLL_run/generate_regional_runfiles.py | 1 Medium | – |
| NLL_run/filter_distant_picks.py | – | 1 Medium |
| NLL_run/merge_regional_results.py | – | 1 Low |
| global_obs/fuse_bulletins.py | 1 Medium, 1 Low | 1 Medium, 1 Low |
| global_obs/remap_picks_to_unified_codes.py | – | 2 Medium |
| global_obs/filter_events_by_aoi.py | 1 Medium | 1 Low |
| global_obs/apply_magnitude_models.py | 1 Low | – |
| fetch_obs/OMP.py | 2 Medium, 1 Low | – |
| fetch_inventory/_fill_missing_elevations.py | 1 Low | – |

## Recommended fix order

1. **`append_station_delays.py:117`** (High) — silent wrong station delays would degrade every second-pass NLL relocation.
2. **`fuse_bulletins.py:603`** (Medium) — `possible_match.drop(found_possible)` drops the wrong row from the "possible" tracker.
3. **`OMP.py:200-203`** (Medium) — potential drop of good P picks depending on OMP quality-0 semantics; verify against the source-format spec first.
4. **`generate_regional_runfiles.py:106-118`** (Medium) — silent wrong station↔network association for malformed code-map blocks.
5. **`OMP.py:158-160`** (Medium) — cascade time-overflow correctly so events aren't silently dropped by the validator.
6. **`filter_events_by_aoi.py:202-212`** (Medium) — `new_lines.pop(-1)` can remove kept-event data.
7. **Performance items** — start with `remap_picks_to_unified_codes.py` (biggest wall-time win) and `filter_distant_picks.py`.
