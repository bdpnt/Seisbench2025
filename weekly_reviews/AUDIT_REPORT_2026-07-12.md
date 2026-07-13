# Weekly Code Audit — 2026-07-12

Scope: Python files touched on the `claude` branch in the last 7 days (since the
2026-07-05 audit). This window covers the new SSST relocation stage
(`run_SSST.py`, `NLL_run/run_ssst.py`, `NLL_run/generate_ssst_runfiles.py`,
`NLL_run/reformate_obs.py`) plus the `FINAL` → `NLL_result` / `loc/` → `run/nll_loc/`
path-rename sweep and the NLL restructure.

## Files reviewed

- NLL_run/append_station_delays.py
- NLL_run/export_locdelay_info.py
- NLL_run/generate_regional_runfiles.py
- NLL_run/generate_ssst_runfiles.py
- NLL_run/match_pre_post_relocation.py
- NLL_run/merge_regional_results.py
- NLL_run/parse_nll_output.py
- NLL_run/reformate_obs.py
- NLL_run/run_ssst.py
- NLL_run/run_zone.py
- add_temp_picks.py
- complem_figures/depth_histogram.py
- complem_figures/depth_maps.py
- complem_figures/error_maps.py
- complem_figures/event_maps.py
- complem_figures/zone_map.py
- generate_complem_figures.py
- generate_complem_maps.py
- run_NLL.py
- run_SSST.py
- temp_picks/match_picks.py

## Findings

### NLL_run/run_ssst.py
- **[Medium]** Lines 264–292: the per-event obs chunks are rebuilt from scratch on
  every iteration. `_run_nlloc_parallel` runs once per SSST iteration (up to
  `len(CHAR_DISTS)+1` = 6 times by default); each call deletes all `obsfiles_*`
  dirs, re-globs the full obs set, and physically `shutil.copy2`-copies every
  per-event `.nlloc_obs` file into fresh chunk dirs. For the SSST iterations
  `loc_obs` is identical, so the same (potentially thousands of) small files are
  re-copied 5–6×. Suggested fix: build the `obsfiles_<index>/` chunks once, keyed
  by `loc_obs`, and reuse them across iterations; rebuild only when `loc_obs`
  changes (the final iteration's `locObsFinal`).
- **[Low]** Lines 333–364: the merge does `shutil.copytree(..., dirs_exist_ok=True)`
  of every chunk dir into `out_root` and then `_remove_path` deletes the originals.
  Chunk dirs and `out_root` are siblings on one filesystem, so this doubles write
  volume for what could be per-file `shutil.move`/`os.replace` — most noticeable on
  the final iteration where `SAVE_FMAMP`/`SAVE_NLLOC_OCTREE` produce large output.
- **[Low]** Lines 198–201: the `_build_skeleton_conf` docstring states that
  `INCLUDE`, `LOCFILES` and `LOCMETH` are all neutralised and that
  `_run_nlloc_parallel` "appends fresh, iteration-specific versions." In fact
  `_run_nlloc_parallel` re-appends only `LOCFILES`/`LOCMETH`/`LOCCOM`/`LOCHYPOUT` —
  `INCLUDE` (the `GTSRCE` station file) is commented out and never re-added. This is
  functionally correct (NLLoc reads station coordinates from the travel-time grid
  headers, not from `GTSRCE`), but the comment is misleading. Fix: correct the
  docstring to say `INCLUDE` is dropped because NLLoc does not consume `GTSRCE`.

### NLL_run/reformate_obs.py
- **[Low]** Line 35: `_PROJECT_ROOT` is defined but never used anywhere in the
  module — dead code introduced with the file. Remove it.
- **[Low]** Lines 97–103 / 158,185: the output filename is `f'{event_id}.nlloc_obs'`
  opened in `'w'` mode. If two events share a `publicId` (or, when `PUBLIC_ID` is
  absent, an identical origin-time fallback id), the second write silently clobbers
  the first file, yet `n_written` is incremented for both — silent event loss
  reported as a full count. Low because upstream dedup should keep `publicId`s
  unique; a collision check (track seen ids in a set, log and disambiguate) would
  make the guarantee explicit.
- **[Low]** Lines 163–174: the `#` event-header parse indexes `metadata[1..8]` and
  `float()`/`int()`s them with no length/format guard, so a single malformed or
  short `#` line (e.g. a stray `##` comment, which passes the `startswith('#')`
  test) raises `IndexError`/`ValueError` and aborts the whole bulletin. Inputs are
  pipeline-generated so this is unlikely in practice; a `len(metadata) >= 9` check
  (skip-and-log) would harden the boundary.

### NLL_run/generate_ssst_runfiles.py
- **[Low]** Lines 204–206: `nx_ls`/`ny_ls` are derived to cover the LOCGRID
  horizontal extent, but `nz_ls` is a hardcoded constant (`lsGridNz=40`) and `z0` is
  copied verbatim from LOCGRID — nothing ties the LS grid's vertical extent to the
  actual LOCGRID vertical extent. With current defaults this is fine (LSGRID reaches
  -3 + 39×1 km = 36 km, covering the 35 km LOCGRID). But the guard at lines 278–287
  only *warns* (does not raise) when a stale `run_<N>_DELAYS.in` has a LOCGRID
  beyond 35 km — in exactly that case the LS grid under-covers the bottom of the
  search grid and an incomplete correction grid is generated silently. Latent /
  benign for correctly regenerated (nz=761) run files. Fix: derive `nz_ls` from the
  parsed LOCGRID vertical extent the same way `nx_ls`/`ny_ls` are, or raise instead
  of warn when the LOCGRID bottom exceeds the LSGRID bottom.

### run_SSST.py
- **[Low]** Line 274: `zones = args.zones.split(',')` does not strip whitespace, so a
  natural invocation like `--zones "1, 2"` yields `['1', ' 2']`; `' 2'` is not a key
  of `_ZONES`, and the validation at lines 276–278 aborts with
  `unknown zone(s):  2` instead of running zones 1 and 2. Fix:
  `zones = [z.strip() for z in args.zones.split(',') if z.strip()] if args.zones else None`.

## Not defects (checked, no action)

- `NLL_run/generate_regional_runfiles.py:260` — `nz=800`→`761` is correct
  (-3 km start, 0.05 km spacing → 35 km bottom = 761 nodes) and carries an
  explanatory comment.
- `NLL_run/generate_regional_runfiles.py:330` — the `LOCMETH` field change `6`→`145`
  is `maxNum3DGridMemory`, which is inert under the `GRID2D` (`GTMODE GRID2D`) mode
  used here; no runtime effect.
- The bulk of this week's diff is the `FINAL`→`NLL_result` and `loc/`→`run/nll_loc/`
  path/name-rename sweep across `complem_figures/*`, `generate_complem_*.py`,
  `add_temp_picks.py`, `temp_picks/match_picks.py`, and the NLL_run modules — pure
  docstring/path edits with no logic change.
- `NLL_run/run_ssst.py` iteration/`charDists` indexing, resume math, round-robin
  chunk filtering, and CSV-header merge were cross-checked and are correct.
- `run_SSST.py` zone-tuple unpacking, finalize-merge gating on missing per-zone
  CSVs, and iteration windowing were cross-checked and are correct.

## Summary

21 files reviewed, 7 issues found (1 Medium, 6 Low). No High-severity issues. The
new SSST code is internally consistent; the Medium item is a redundant-I/O
optimization in the per-iteration NLLoc fan-out, and the remaining items are minor
robustness, dead-code, and comment-accuracy fixes.
