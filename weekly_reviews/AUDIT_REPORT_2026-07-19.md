# Weekly Code Audit — 2026-07-19

Scope: Python files touched on the `claude` branch in the last 7 days (since the
2026-07-12 audit). This window covers a batch of correctness/perf fixes across the
harmonization and NLL-runfile stages (OMP time parsing, magnitude-model selection,
station-code lookups, AOI rebuild, fusion match-frame indexing) plus three **new**
SSST analysis/visualization tools in `complem_figures/`
(`event_ranking.py`, `plot_pdf_cloud.py`, `ssst_evolution.py`).

Each recent change was reviewed against its diff and the surrounding code. Findings
below were verified against the actual source; the recent changes are, on the whole,
genuine bug-fixes and performance wins with no regressions. Most findings are
pre-existing fragilities that the recent edits make slightly more reachable, or
hardening opportunities in the new tools.

## Files reviewed

- NLL_run/append_station_delays.py
- NLL_run/filter_distant_picks.py
- NLL_run/generate_regional_runfiles.py
- fetch_obs/OMP.py
- fetch_inventory/_fill_missing_elevations.py
- global_obs/apply_magnitude_models.py
- global_obs/remap_picks_to_unified_codes.py
- global_obs/filter_events_by_aoi.py
- global_obs/fuse_bulletins.py
- complem_figures/event_ranking.py
- complem_figures/plot_pdf_cloud.py
- complem_figures/ssst_evolution.py

## Findings

### NLL_run/generate_regional_runfiles.py
- **[Medium]** Lines 139–140 (`_find_station_info`): `codes = alternate_code_map.get(alternate_code)`
  returns `None` for any station code whose code-map block failed to parse, and the very
  next line dereferences `codes[0]`, raising an opaque `TypeError: 'NoneType' object is not
  subscriptable`. `_gen_gtsrce` calls this for every station code found in the bulletin with
  no guard. This is pre-existing, but the same-commit "reset station variables per code-map
  block" fix means unparseable blocks are now *absent* from `alternate_code_map` (rather than
  carrying leaked values), making this path more reachable. Fix: handle `codes is None`
  explicitly — log and skip the station (or raise a clear error naming the missing
  `alternate_code`) instead of failing on the subscript.

### NLL_run/append_station_delays.py
- Clean. The change from `lines[i + 3]` to `locdelay_lines[i]` is correct: `statCorr_df` is
  built directly from `locdelay_lines` with a default `RangeIndex`, so indices map 1:1 to
  `locdelay_lines` positions. No off-by-one, no regression. (Appended correction order is
  arbitrary because `idx` is a `set`, but NLL is order-insensitive here — not worth changing.)

### NLL_run/filter_distant_picks.py
- Clean. Building `coords_by_code` after `drop_duplicates(subset='AlternateCode', keep='first')`
  preserves the old `.iloc[0]` "first match" semantics exactly, and the `None` check replaces
  the old `sta_row.empty` check correctly. O(picks × stations) → O(picks) with no behavior change.

### fetch_obs/OMP.py
- **[Low]** Lines 152–163: the `hour >= 24` clamp (`weird_hour`) runs *before* the second/minute
  overflow cascade. For an original time of `23:59:60`, the cascade does `minute -= 60; hour += 1`,
  producing `hour = 24` after the clamp has already passed. `UTCDateTime(...)` then raises and the
  event is counted as `n_skipped_invalid` and silently dropped — a valid midnight-boundary event is
  lost. Fix: after the cascade, roll `hour >= 24` into the next day (construct the datetime and add a
  `timedelta`) rather than leaving `hour = 24`.
- **[Low]** Lines ~218–221 (pre-existing, adjacent to the change): asymmetry in the P/S drop logic —
  if the **P** second field is missing/`*`, the whole phase line is `continue`d, so a station with an
  **S** reading but no P has its S pick dropped. The recent commit fixed the mirror case (P picks were
  being dropped when S was absent); this reverse case remains. Only relevant if S-without-P picks
  matter for the catalog. Not introduced by this diff.
- Note: the `quality_p.isdigit()`/`quality_s.isdigit()` guards correctly prevent the prior `int()`
  crash on blank/non-digit qualities — that part of the change is sound.

### global_obs/apply_magnitude_models.py
- **[Low]** Lines ~187–191: key-based model selection (`next(k for k in keys if '≥' in k ...)`) is more
  robust to dict ordering than the old positional `[0]`/`[1]`, but it now hard-depends on the literal
  Unicode `≥` (U+2265) / `<` characters in the joblib keys produced by `generate_magnitude_models.py`.
  If a model is ever regenerated with a different label format, `next(...)` raises `StopIteration`,
  which is swallowed by the broad `except Exception` and mislabeled as "Model missing — skipped",
  silently dropping all conversions for that pair with no distinct diagnostic. Fix: catch
  `StopIteration` separately (or assert key presence) for a clearer message, and add a comment noting
  the `≥`/`<` key contract shared with `generate_magnitude_models.py`.

### fetch_inventory/_fill_missing_elevations.py
- Clean. Adding `timeout=10` is correct; `requests.exceptions.Timeout` subclasses `Exception` and is
  caught, returning `0` as intended. (The bundled commit message "select magnitude models by key" does
  not describe this file — commit-message mislabel only, not a code issue.)

### global_obs/remap_picks_to_unified_codes.py
- Clean. Building one `pd.DataFrame(rows, ...)` instead of repeated `pd.concat`, plus
  `groupby('Code').indices` for O(1) lookup, is a genuine, behavior-preserving perf win.
  Informational: `groupby(...).indices` returns positional locations used later via `.loc[...]`; this
  is correct only because `find_unique_stations` returns a default `RangeIndex` (positions == labels).
  Currently safe — a one-line comment documenting that assumption would harden it.

### global_obs/filter_events_by_aoi.py
- **[Low]** Lines ~241–242: the bulletin is rewritten in place via `open(file_name, 'w')` after the new
  block list is built. The commit's "atomically per event block" refers to correct block-level grouping
  (verified — separators and trailing/leading out-of-AOI blocks are handled, and the old `pop(-1)` /
  unbounded `while` `IndexError`s are fixed), *not* filesystem atomicity. Since the file is both input
  and output, an exception during `writelines` would truncate the source `.obs`. Consider writing to a
  temp file and `os.replace()`. Pre-existing, not a regression.

### global_obs/fuse_bulletins.py
- **[Low]** Lines ~1312–1314: the module-CLI defaults for `--loose-dist-thresh` (30.0) and
  `--loose-time-thresh` (10.0) diverge from the documented/production loose thresholds (50 km / 30 s),
  which are passed explicitly by `build_global_bulletin.py`. Harmless as long as fusion is always driven
  through the orchestrator, but a foot-gun for anyone invoking the module CLI directly expecting the
  documented behavior. Suggest aligning the CLI defaults to 50.0 / 30.0.
- The recent change itself is correct: `found_possible.append(row_label)` (preserving original index
  labels) plus pre-built `groupby` dicts for `strict_match`/`possible_match` removes an
  O(n_main × n_matches) scan, and `check_similar_picks`'s `{phase_key: [count, first_time]}` collapse is
  O(1) with no dead code. Strict (15 km / 2 s / 1.5 mag, mag only enforced for ML–ML LDG/OMP) and loose
  (50 km / 30 s, ≥1 shared P-pick) threshold logic and the per-source 1 s / 50 km dedup were sanity-checked
  and match CLAUDE.md.

### complem_figures/ssst_evolution.py
- **[Medium]** Lines ~49 and ~167: `_YLIM = (1e-3, 1e3)` is a single hardcoded y-range applied via
  `ax.set_ylim(*_YLIM)` to all three panels, but the metrics have different units/scales (`pdfVolume`
  in km³, `EllipsoidLen3` in km, `RMS` in s). Values outside `[1e-3, 1e3]` are silently clipped
  off-figure with no warning — e.g. a tight-location `pdfVolume` below 1e-3 or median/IQR bands leaving
  the frame. For a QC/publication figure this can hide real data. Fix: per-metric autoscaling or
  per-metric limits instead of one shared constant.
- **[Low]** Line ~136: `net = np.log(values[:,-1] / values[:,0])` assumes all metric values are strictly
  positive and non-null; a zero/NaN first-iteration value yields `inf`/`nan` that flows into the plot.
  Realistically these are > 0 — a `> 0` guard or a comment noting the assumption would harden it.

### complem_figures/plot_pdf_cloud.py
- **[Low]** Lines ~165–172 (`_load_iteration`): `os.path.exists(scat_path)` is checked but `hdr_path` is
  not; `_read_lambert_params(hdr_path)` opens the `.hdr` unconditionally, so an iteration with a present
  `.scat` but missing `.hdr` throws an unhandled `FileNotFoundError` instead of the graceful "skip this
  iteration" the `.scat` branch does. Fix: guard `hdr_path` the same way.
- **[Low]** Line ~445: `--confidence` help text says `(default: 0.9)` but the actual default is `0.68`
  (`PdfCloudParams.confidence=0.68`). Stale help string — update to `(default: 0.68)`.
- **[Low]** Lines ~222–227 (`_load_nll_reference`): reads columns `expect_lon`/`expect_lat`/`expect_z`
  from `NLL_result.csv`. These names appear nowhere else in the repo (all other coordinate reads use
  `latitude`/`longitude`/`depth`). They are almost certainly the real NLLoc `SAVE_NLLOC_SUM` expectation
  columns — the same function correctly uses the native `latitude`/`longitude`/`depth` names for the
  hypocenter — but a missing *column* raises an uncaught `KeyError` (only `row.empty` is guarded), so if
  the CSV schema ever differs the NLL reference crashes rather than degrading. Worth confirming against a
  real `.sum.grid0.loc.csv` header, or wrapping the column access to skip the reference on `KeyError`.
- **[Low]** Lines ~287–327: the convergence path prepends the pre-SSST NLL reference hypocenter to the
  SSST iteration points, so the black path joins the NLL point to the SSST solutions. Plausibly intentional
  (shows NLL→SSST movement), but undocumented; when the cross-zone winner has `nll_ref['zone'] != zone` the
  joined segment mixes solutions from different zones. Add a brief comment, or exclude the NLL point when
  zones differ.

### complem_figures/event_ranking.py
- **[Low]** Lines ~144–145: `log_ratio` / `pct_change` (`np.log(post/pre)`, `post/pre - 1`) assume all
  `pdfVolume` values are strictly positive and non-null; a zero/NaN pre-value produces `inf`/`nan` that
  then flows into sorting and `np.percentile`. Realistically `pdfVolume > 0`, so Low — a `> 0` guard or a
  comment noting the assumption would harden it. The ellipsoid-volume formula (4/3·π·L1·L2·L3), the
  best/worst/degraded sort directions, and the shared-`publicId` merges were verified correct.

## Summary
12 files reviewed, 14 issues found (2 Medium, 12 Low). No High-severity issues. Five of the
recently changed files (`append_station_delays.py`, `filter_distant_picks.py`,
`_fill_missing_elevations.py`, `remap_picks_to_unified_codes.py`, plus the reviewed portions of
`fuse_bulletins.py`) are clean — the recent edits are correct bug-fixes/perf wins. The two Mediums are a
reachable `None`-dereference `TypeError` in `generate_regional_runfiles._find_station_info` and a shared
hardcoded y-limit in the new `ssst_evolution.py` that can silently clip QC/publication data off-figure.
The remaining Lows are edge-case data loss (OMP `hour=24` midnight boundary), silent-failure/foot-gun
hardening, and documentation/help-text nits in the three new `complem_figures/` tools.
