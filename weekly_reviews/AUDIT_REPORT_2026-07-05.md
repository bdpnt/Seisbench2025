# Weekly Code Audit — 2026-07-05

## Scope

Python files touched on the `claude` branch in the last 7 days. The changes fall into three groups:

1. **NLL pipeline compaction** (commit `27ce90f`): `prepare_nll_inputs.py`, `generate_nll_corrections.py`, and `finalize_nll_catalog.py` were merged into a single orchestrator `nll_phase_1.py` that runs zones 3-at-a-time via a thread pool. New helper `NLL_run/merge_regional_results.py`. The three source scripts no longer exist and were not reviewed.
2. **NLL run hardening** (commit `0623487`): `NLL_run/run_zone.py` gained low-disk warnings and fatal disk/memory pattern detection.
3. **External pick ingestion** (commits `db56ac8`, `8216f9a`, `487b220`, `33636b6`, `584a6e8`): phase-probability filtering added to the merge steps, a new `TEMP_OTH` pick format added to `convert_picks.py`, and it wired into `add_temp_picks.py`.

## Files reviewed
- nll_phase_1.py
- NLL_run/merge_regional_results.py
- NLL_run/run_zone.py
- add_temp_picks.py
- temp_picks/convert_picks.py
- temp_picks/match_picks.py
- temp_picks/merge_omp_picks.py
- temp_picks/merge_pyrenees_picks.py

(`finalize_nll_catalog.py`, `generate_nll_corrections.py`, `prepare_nll_inputs.py` appear in the 7-day log but were deleted in the compaction and no longer exist.)

## Findings

### temp_picks/convert_picks.py
- **[Medium]** Lines 427–447 (`convert_temp_oth`): the S-pick block is not gated on the P
  arrival being usable. The P pick is only emitted when `quality_p < 4 or quality_p == 9`
  (line 429), but the S pick that follows (line 435 onward) is derived from `p_dt` for **any**
  `quality_p` as long as an S sub-field with `quality_s < 4` is present. The docstring (lines
  388–394) is explicit that a quality-4 P — an "unusable placeholder time (blank or `0.00`)" —
  should cause the line to be "dropped entirely" because "the S offset is only meaningful relative
  to a real P arrival." The only guard that drops such lines is the blank-field check at lines
  415–416 (`if not ss_str or not frac_str`), which catches a *blank* placeholder but **not** the
  documented `"0.00"` placeholder (there `ss_str="0"`, `frac_str="00"`, both non-empty). Result:
  a quality-4 (or 5–8) line carrying a `0.00`/unusable P time but a valid S offset emits an S pick
  anchored to a meaningless P time — contrary to the stated intent. Suggested fix: gate the S-pick
  block on the same condition that keeps the P pick (`if (quality_p < 4 or quality_p == 9) and
  rest.strip():`). Downstream `match_picks` residual filtering will reject most grossly mis-timed
  S picks, which limits real-world impact, but the pick should not be generated in the first place.

### NLL_run/merge_regional_results.py
- **[Low]** Lines 159–162 of `nll_phase_1.py` build the merge input list unconditionally for all
  6 zones, and `merge_bulletins` (line 133–137 here) calls `pd.read_csv(path)` on each with no
  existence/empty handling. If any zone produces no `*.obs.sum.grid0.loc.csv` (e.g. a zone whose
  lat/lon box contained no events), the merge aborts with a bare `FileNotFoundError` and no zone
  context. Suggested fix: skip (with a warning) missing/empty zone CSVs, or validate the list
  before concatenating.
- **[Low]** Lines 82–83 (`_build_covariance`): `v3_dir = np.cross(v1 / len1, v2 / len2)` and the
  subsequent `/ np.linalg.norm(v3_dir)` have no guard against a zero-length semi-axis (`len1`/`len2`
  == 0 → division by zero) or against the first two ellipsoid axes being parallel (`norm(v3_dir)`
  == 0). Either degenerate case propagates `nan`/`inf` silently into `true_erh`/`true_erz`. Rare in
  practice for well-constrained NLLoc solutions, but unguarded. Consider validating the axis lengths
  and cross-product norm before dividing.

### NLL_run/run_zone.py
- No new issues. The added low-disk warning (`_check_disk`) and post-run fatal-pattern scan
  (`_FATAL_PATTERNS`) are sound: patterns are matched only after a zero exit code, catching the case
  where NLL prints an allocation/space failure but still exits 0. The hardcoded `_NLL_BIN` path and
  the library-level `sys.exit()` on failure were already reported in AUDIT_REPORT_2026-06-28.md and
  are unchanged here — not re-litigated.

### nll_phase_1.py
- No issues. The `_logger_lock` correctly serializes the two helpers (`generate_run`,
  `append_station_delays`) that reconfigure a shared module logger, keeping only the slow subprocess
  runs parallel. Submodule attribute access (`NLL_run.generate_regional_runfiles.generate_run`) is
  valid because the corresponding `from NLL_run.<mod> import ...` lines register the submodules on
  the package. `future.result()` correctly re-raises per-zone failures.

### add_temp_picks.py
- No issues. The chained matching that reads and writes `FINAL_augmented.obs` in place (iterations
  2–5) is safe because `match_picks.load_bulletin` reads the whole file into memory and closes it
  before the output file is opened for writing.

### temp_picks/match_picks.py
- No issues. Time-window candidate selection via `bisect` is correct (events in
  `[arrival − 60 s, arrival]`), the residual band correctly adds the phase tolerance plus the
  `T0_TOL` origin-time margin, and duplicate `(station, phase)` detection via `pick_keys` works
  across chained runs since the reloaded bulletin already carries previously added picks.

### temp_picks/merge_omp_picks.py, temp_picks/merge_pyrenees_picks.py
- No issues. The phase-score filter columns match the documented source layouts
  (`parts[5]` = `phase_score` for OMP; trailing `prob=` token for RSB). The parse-failure fallback
  (keep row, warn once per file) is a deliberate, documented choice. Header handling in the OMP
  merge correctly writes exactly one header row and skips subsequent files' headers.

## Summary
8 files reviewed, 3 issues found (1 Medium, 2 Low). The Medium is a real logic gap in the new
`TEMP_OTH` converter (S picks emitted for unusable P arrivals); the two Low findings are unguarded
boundary cases in the new zone-merge helper.
