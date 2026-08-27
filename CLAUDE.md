# CLAUDE.md — Shallow_Depth_DL_Catalog

## Project Overview

Shallow_Depth_DL_Catalog is an earthquake catalog processing and relocation pipeline focused on the **Pyrenees region** (latitude 41–45°N, longitude -3 to 4°E), covering seismicity from **1978 to 2025**.

The goal is to produce a unified, publication-quality earthquake catalog with harmonized magnitudes and improved hypocenter locations, by integrating data from 5 independent seismic networks.

---

## Pipeline Summary

The workflow follows 5 main stages:

### 1. Station Inventory Fusion
- Source: FDSN XML files + OMP CSV files (in `stations/`)
- Script: `build_global_inventory.py` → calls modules in `fetch_inventory/`
- Output: `stations/GLOBAL_inventory.xml` + `stations/GLOBAL_code_map.txt`
- Each station gets a unique code; duplicates are removed by distance threshold (20m)

### 2. Catalog Fetching & Conversion
- Sources: RESIF (FDSN), ICGC, IGN, LDG, OMP (in `org_catalogs/`)
- Script: `fetch_all_bulletins.py` → calls modules in `fetch_obs/`
- Output: individual `.obs` files per source in `obs/`

### 3. Catalog Harmonization
- Script: `build_global_bulletin.py` → calls modules in `global_obs/`
- Steps:
  1. **remap_picks_to_unified_codes.py** — associates picks with unified station codes
  2. **generate_magnitude_models.py** — builds regression models to convert all magnitude types to ML
  3. **apply_magnitude_models.py** — applies the models to all `.obs` files
  4. **filter_events_by_aoi.py** — filters each source bulletin to the area of interest (run in `pygmt_env`)
  5. **fuse_bulletins.find_and_merge_doubles** — de-duplicates each source catalog individually before fusion (1 s / 50 km)
  6. **fuse_bulletins.py** — spatially/temporally merges all catalogs into `obs/GLOBAL.obs`
  7. **plot_global_catalog_map.py** — generates a map of the merged catalog
- Matching thresholds: strict 15 km / 2 s / 1.5 mag units; loose 50 km / 30 s confirmed by ≥1 shared P-phase pick

### 4. Earthquake Relocation (NonLinLoc)
The study area is too large for a single NLL run, so it is split into **6 geographic zones**, processed with up to **3 zones running concurrently** (zones are independent; NLL runs are the bottleneck).

- **`run_NLL.py`** — for each zone: generates one `.obs` file and one `.in` run file `run/nll/run_<N>_DELAYS.in` (plus GTSRCE station file), runs Vel2Grid → Grid2Time → NLLoc via `NLL_run/run_zone.py`, cleans up `.hdr` files, then generates a second-pass run file `run/nll/run_<N>_NLL.in` by appending per-station delay corrections derived from first-run arrival-time residuals and reruns NLLoc via `run_zone.py` with `--corrections-pass` (grids already built), cleaning up `.hdr` files again right after — this per-zone `.hdr` cleanup keeps at most a few zones' worth on disk at once instead of waiting for all 6 zones to finish. Once all zones are done, exports the locdelay summary via `export_locdelay_info` to `run/nll/locdelays/`. NLL working folders live inside `run/`: `nll_model/` (velocity grids), `nll_time/` (travel-time grids), `nll_loc/` (per-zone NLLoc output).
- **`NLL_run/run_zone.py`** — runs Vel2Grid → Grid2Time → NLLoc in sequence for a given `.in` file; `--corrections-pass` skips Vel2Grid/Grid2Time; accepts a `zone_label` to prefix log output when zones run concurrently

### 5. Post-relocation Processing
- **`run_NLL.py`** (after all 6 zones complete):
  1. Reads the 6 per-zone NLL CSV summaries, deduplicates zone-overlap events (kept: lowest `pdfVolume`), writes → `RESULT/NLL_result.csv`
  2. Rematches relocated events back to `obs/GLOBAL.obs` via `publicId` to recover metadata not present in NLL output (e.g. magnitude)
  3. Saves matched events to `obs/NLL_result.obs`
- **`add_temp_picks.py`** (optional, run after): augments `obs/NLL_result.obs` with picks from external sources → `obs/NLL_result_augmented.obs`

### 6. SSST Relocation
Final stage, run after `add_temp_picks.py`: relocates `obs/NLL_result_augmented.obs` with iterative Source-Specific Station Terms (NonLinLoc `Loc2ssst`). Zones run **strictly sequentially** (memory-bound), everything inside a zone in parallel (`NLLOC_CORES` NLLoc chunks / `LOC2SSST_CORES` Loc2ssst instances).

- **`run_SSST.py`** — orchestrator; campaign configuration (RUN_NAME, CHAR_DISTS, VPVS, core counts, LSPHSTAT) at the top of the file; CLI `--zones`, `--iteration-start`, `--iteration-stop` (partial campaigns/resume). Per zone: cuts `obs/GLOBAL_<N>_SSST.obs` + `stations/GTSRCE_SSST_<N>.txt`, derives `run/ssst/run_<N>_NLL.in` (NLLoc) and `run/ssst/run_<N>_SSST.in` (Loc2ssst) from `run/nll/run_<N>_DELAYS.in` (`NLL_run/generate_ssst_runfiles.py`), splits the bulletin into per-event files in `obs/nlloc_obs/GLOBAL_<N>/` (`NLL_run/reformate_obs.py`), builds P+S grids in `run/ssst_model|ssst_time` (VpVs −9.99, real S grids), and runs the iteration loop (`NLL_run/run_ssst.py`: len(CHAR_DISTS) SSST iterations + final NLLoc-only relocation, outputs under `run/ssst_loc/<RUN_NAME>/`).
- After all zones: merges the final-iteration CSVs → `RESULT/SSST_result.csv` (dedup by lowest `pdfVolume`), rematches against `obs/NLL_result_augmented.obs` via `publicId` → `obs/SSST_result.obs` (same modules as the NLL stage).
- **`NLL_run/pdf_metrics.py`** — last step of `run_SSST.py` (after the merge and the rematch): reads the per-event `.scat` clouds of each zone's final SSST iteration and rewrites `RESULT/SSST_result.csv` in place with the location-PDF quality columns, then saves the diagnostic figures below. Non-fatal there (the results are already written) and idempotent, so it can be rerun standalone on any campaign; ~65 s for ~46 k events (~50 s metrics, ~15 s figures).
  ```bash
  python NLL_run/pdf_metrics.py --run-name ssst_run1
  python NLL_run/pdf_metrics.py --run-name ssst_run1 --figures false   # metrics only
  ```
  Uses its own `.scat` reader — **not** `obspy.io.nlloc.util.read_nlloc_scatter`, which does `np.fromfile(...)[4:]` and silently drops the first 3 samples of every file (4 records dropped where the header is 1).

  Figures land in `complem_figures/pdf_metrics/` (plotting is wrapped: a failure there never touches the already-written CSV):
  - `<run>_metrics_vs_quality.pdf` — Ψ / `C68` / `dip_stat` against depth, RMS, Nphs, Gap, Dist (hexbin density + median/IQR over equal-count bins + the per-bin Gaussian null)
  - `<run>_error_vs_quality.pdf` — the inverse view: the published error `true_erh` / `true_erz` (log axis) against RMS, Gap, Nphs, Ψ, `C68`, and a box split on `dip_reject`. Each panel reports Spearman ρ **and** ρ given Nphs, because the marginal ρ of RMS against ERH is +0.00 while the Nphs-controlled one is +0.62 — RMS rises with the phase count and ERH falls with it, and the two cancel. Ψ is the strongest single correlate of the published error (ρ = −0.87 ERH, −0.85 ERZ); Ψ and `C68` are computed on whitened samples, so neither is definitionally tied to the size of the ellipsoid
  - `<run>_gridmap.pdf` — the same three metrics as lon/lat windowed-median maps
  - `<run>_gridmap_depth.pdf` — those maps split into depth quartiles, colour scale shared per row
  - `<run>_voxels_<metric>.html` — interactive 3-D lat/lon/depth cells (Plotly)

  The maps colour by `C68_z = (C68 − 0.68) / C68_sigma_n` rather than raw `C68`, and the 1-D nulls are per bin: both are read from each event's own `J_null_p95` / `C68_sigma_n`, so nothing breaks when `n_scat` is not near-constant as it happens to be in `ssst_run1`.

### 7. Final Bulletin Export
Last stage, run after `run_SSST.py`. Merges `obs/SSST_result.obs` (magnitudes + picks) and `RESULT/SSST_result.csv` (full-precision hypocentres + PDF metrics) on `publicId` into `RESULT/FINAL.xml`, a QuakeML 1.2 bulletin.

- **`final_steps.py`** — orchestrator; the post-SSST finalization stage. Currently one step, further steps get appended as `[n/N]`.
- **`NLL_run/export_quakeml.py`** — the export. All 46 224 events, all 1 001 095 picks. ~5 min, ~3.4 GB peak RAM, ~0.86 GB output. Serializes in chunks of 5 000 events and splices the bodies into one file (obspy has no streaming QuakeML writer).
  ```bash
  python final_steps.py
  python NLL_run/export_quakeml.py --obs obs/SSST_result.obs --csv RESULT/SSST_result.csv \
      --inventory stations/GLOBAL_inventory.xml --output RESULT/FINAL.xml
  ```
- Each event carries `pyr:usable` = `(C68 − 0.68)/C68_sigma_n ≥ −2` **and** `not dip_reject` **and** metrics present → 45 415 usable / 809 unusable, plus a `pyr:rejectReason` string. **Ψ is exported but never rejects** (directionless; 81 % of the catalog exceeds its own `J` null). The `C68` cut is against the simulated null, not raw 0.68 — that difference is 155 events flagged instead of 2 944.
- Station codes are resolved to real `NET.STA` via inventory `alternate_code`, epoch-aware; when several candidates cover the same date the `XX` network loses (placeholder for uncalled/unknown networks — currently decides only `FR.0013` → `FR.MTHF`). Resolution is never destructive: every pick keeps `pyr:unifiedCode`, and codes covering several stations also carry `pyr:alternateStations` (the non-chosen ones, **including date-mismatched entries**) as waveform-retrieval fallbacks — ~15% of picks.
- The `pyr:` prefix is bound to `http://shallow-depth-dl-catalog/quakeml/1.0`. QuakeML 1.2's schema is closed, so every non-standard field lives in that namespace; validators skip foreign namespaces, which is why the file still validates.
- `read_events('RESULT/FINAL.xml')` works (46 224 events in 255 s, 0 warnings) but peaks at **~15 GB RAM** — ~2M objects, of which picks+arrivals are 83% (12.5 KB per pick, 55.8 KB per event). So the stage writes the catalog three ways: `FINAL.xml` (everything, ~15 GB), `FINAL_catalog.xml` (all events, picks stripped, measured 2.5 GB / 33 s — the FDSN `includearrivals=false` convention), and `FINAL_<from>_<to>.xml` (5-year calendar periods set by `_SPLIT_YEARS`, each independently valid; together an exact partition of `FINAL.xml`). Parts are very uneven — `FINAL_2020_2024.xml` holds 40% of all picks and measures 6.0 GB, vs 0.05 GB for 1975-1979. Disable either companion with `--no-catalog` / `--no-parts`.
- Prefer `lxml.etree.iterparse` for anything that does not need the whole catalog resident; it walks the full file in seconds at flat memory.
- `Mag 0.00` (5 010 events) is an OMP placeholder, written through unchanged because magnitudes are recomputed later — do not fit it as data.

---

## Complementary Analysis

Scripts in `complem_figures/` for visualization and statistics:
- `event_maps.py` — geographic maps of seismicity
- `gutenberg_richter.py` — magnitude-frequency distribution
- `depth_maps.py` — depth distribution
- `depth_histogram.py` — histogram of event depths
- `error_maps.py` — location uncertainty maps
- `cross_section.py` — vertical cross-sections; `--format 6` reads `RESULT/SSST_result.csv` directly (`true_erh`/`true_erz` as the error filter), colours the section by `--use-err erh|erv|psi|c68z`, and `--usable` applies the same acceptance test as `pyr:usable` in the QuakeML export
- `station_map.py` — map of seismic stations
- `zone_map.py` — overview map of the 6 NLL zones
- `event_ranking.py` — ranks events by pdfVolume/ellipsoidVolume change (NLL → SSST); flags multi-zone/zone-changed events; carries the PDF-quality columns (post-SSST only) when `pdf_metrics.py` has annotated the CSV, and runs without them otherwise; optional gridmap PDF
- `plot_pdf_cloud.py` — interactive 3D PDF scatter-cloud of one event across SSST iterations (Plotly)
- `ssst_evolution.py` — per-zone pdfVolume/EllipsoidLen3/RMS evolution across SSST iterations (convergence QC)
- `ssst_corrections.py` — reconstructs and maps the SSST travel-time corrections themselves. The `.ssst` grids Loc2ssst wrote are deleted by `run_SSST.py`'s own cleanup, so the field is recomputed from the surviving per-event `.hyp` locations with Loc2ssst's own formula (`corr = Σ res·w / Σ w`, `w = exp(−d²/L²) + floor`, **d measured event-to-grid-node, not to the station**). `res = obs − pred` and the correction is *added* to the predicted time, so red = arrivals later than the 1-D model predicts. Each iteration is an increment; the final grids carry their sum. Outputs to `complem_figures/ssst_corrections/`:
  - `<run>_station_atlas.pdf` — one page per station×phase field (300 with ≥100 usable arrivals): five increments (9999→50→15→5→1 km) + cumulative total, depth-slice maps on a shared diverging scale, unsupported nodes greyed. A station in two zones is drawn in its better-sampled one — the zones ran separate Loc2ssst passes, so their fields are independent.
  - `<run>_spread_map.pdf` — catalog-wide map of the **across-station** spread of the total correction per event (P only). A correction common to all of an event's stations is absorbed by the origin time and cannot move the hypocentre, so the dispersion — not the mean — is the part that *can* relocate. **Not an impact map**: against the pure SSST displacement (iteration-0 vs final location, same picks) ρ = +0.10, or +0.20 given Nphs; median displacement rises only 0.95 → 1.27 km across the whole spread range. What moves a hypocentre is the *azimuthal pattern* of the differential correction, which a std discards. Nphs suppresses the marginal ρ (spread ρ = +0.42 with Nphs, displacement ρ = −0.18) — the same confound as RMS vs ERH in `pdf_metrics.py`. For reference the pure SSST displacement has median 1.09 km, p90 4.74 km.

  **Nothing is interpolated between map nodes** — one flat `pcolormesh` cell per independently evaluated node; the smoothness on the page is the Gaussian kernel itself. So node spacing is a real constraint: the 0.02° default is ~2.2 km lat / ~1.6 km lon at 43°N, which **undersamples the L = 1 km panel**. The 300-page atlas keeps it coarse on purpose (213 s); use `--stations FR.0041:P --map-spacing 0.005` (~55 s/page, writes `*_station_atlas_selection.pdf`) for pages that go on a slide.

  `--extent=lon0,lon1,lat0,lat1` (the `=` form is required when lon0 is negative) draws every page on one shared frame so pages can be compared, clipped to each zone's `LSGRID` — read from `run/ssst/run_<N>_SSST.in`, since off that box Loc2ssst computed nothing. Default frames each page on its own station's events, which is tighter but not comparable page to page.

  **`--depth` defaults to each station's own median event depth**, not a fixed value. The kernel is 3-D, so a slice `dz` off the event mass damps every event by `exp(−dz²/L²)` — negligible at L = 15 km, fatal at L = 1 km. A fixed 10 km slice against a catalog median of 6.6–7.3 km cut `FR.0041`'s median summed weight in the finest panel from 5.7 to 2.0. Pass `--depth` only to put several stations on a common plane.

  ```bash
  python complem_figures/ssst_corrections.py                 # both, ~7 min
  python complem_figures/ssst_corrections.py --extract-only  # fill the cache only
  ```
  Parsing the ~276 k per-event `.hyp` files takes ~100 s, cached as `.npz` per (zone, iteration) in `run/ssst_corrections_cache/` (33 MB). **Validated against the binary**: Loc2ssst re-run on zone 6 (`FR.0047`, P and S) agrees node-by-node over all 303×313×40 nodes to 0.0000 ms at L=9999 and 0.0736 ms at L=1, against ±0.36 s amplitudes; its own "163 accepted" matches the module's LSPHSTAT selection exactly. Omitting `LOCFILES` from the control file is what keeps that check cheap — `ihave_time_input_grids = flag_out_grid * flag_nlloc_outfile` (`Loc2ssst.c:590`), so Loc2ssst writes the correction grid and skips the travel-time grids, needing no Grid2Time rebuild.

  Note when reading the figures: increments are **not** monotonically decreasing — they peak at L = 15 km, the scale where the residual field has real spatial structure. And LSPHSTAT admits only a subset of the catalog: 23 727 events at iteration 0, rising to 34 674 by the final relocation.

`complem_figures/pdf_metrics/` holds figures too, but they are written by `NLL_run/pdf_metrics.py` (see above), not by a module living here.

> **Environments**: `seisbench_env` is the project default — the whole pipeline (`build_global_inventory.py` → `run_SSST.py`) runs in it unprefixed. `pygmt_env` is the only exception, for the modules importing PyGMT or `xarray`.
> - `seisbench_env` → `generate_complem_figures.py` (Gutenberg-Richter, depth maps, error maps)
> - `pygmt_env`     → `generate_complem_maps.py` (event maps for each zone and final catalog), `cross_section.py`, and the two `build_global_bulletin.py` steps it launches itself via `conda run` (`filter_events_by_aoi.py`, `plot_global_catalog_map.py`)

`event_ranking.py`, `plot_pdf_cloud.py`, and `ssst_evolution.py` are standalone diagnostics, not wired into the two driver scripts above; they read `RESULT/*.csv` and `run/nll_loc/` / `run/ssst_loc/<run-name>/` directly.

`zone_Arette/` — focused analysis of the Arette seismic zone.

---

## External Pick Ingestion (temp_picks/)

A self-contained sub-pipeline for ingesting picks from external sources into `obs/NLL_result.obs`, producing `obs/NLL_result_augmented.obs`. All scripts live in `temp_picks/` and are importable as a package (`from temp_picks.<module> import <function>`). Log files are written to `temp_picks/console_output/`.

The root-level script **`add_temp_picks.py`** orchestrates the full pipeline (steps 1–5 below) in sequence.

| Script | Role |
|--------|------|
| `build_theoretical_tables.py` | Runs Pyrocko's `cake` CLI to compute P/S travel-time envelopes (±5% velocity, 0–100 km) → `temp_picks/tables_Pyr.csv` |
| `merge_omp_picks.py` | Merges all yearly OMP/PhaseNet CSV files from `picks_OMP/` subdirectories → `pick_files/merged_omp.csv`; station `SMC` and year `2026` excluded by default |
| `merge_pyrenees_picks.py` | Concatenates RaspberryShake/PhaseNet `.txt` files from `picks_station_pyrenees/` and `picks_station_pyrenees2/` → `pick_files/merged_pyrenees.txt` and `pick_files/merged_pyrenees2.txt` |
| `convert_picks.py` | Converts external pick files to `.obs` pick line format; maps station names to internal codes via `GLOBAL_code_map.txt`. Formats `TEMP_OBS`, `TEMP_RSB`, `TEMP_OMP`, `TEMP_OTH`, and `TEMP_STB` are supported; new formats are registered in `FORMAT_HANDLERS`. `TEMP_STB` (Strasbourg/RENASS-OMP parquet picks) reads directories of parquet files instead of a single text file and drops picks below a `phase_score` threshold. Unresolved stations are logged as an end-of-run summary. |
| `match_picks.py` | Matches converted picks to bulletin events: 60 s time window + residual filter (±0.1 s P, ±0.3 s S, plus ±2.5 s t0-error margin); appends new picks and updates `PhaseCount`; chains against `obs/NLL_result.obs` → `obs/NLL_result_augmented.obs`; auto-sorts output via `sort_picks`. |
| `sort_picks.py` | Sorts pick lines within each event block by ascending arrival time. |
| `plot_travel_times.py` | QC figure: scatter of observed (distance, travel time) picks over theoretical P/S bands. |

---

## Key Data Formats

### `.obs` (custom seismic bulletin)
- One block per event, separated by blank lines
- Event line starts with `# `: location, magnitude, quality parameters (azimuth gap, RMS, horizontal/vertical uncertainty)
- Following lines: one pick per station (station code, phase P/S, arrival time, uncertainties)

### NLL output
- Per-zone CSV summary: `run/nll_loc/GLOBAL_<N>/GLOBAL_<N>.obs.sum.grid0.loc.csv` — relocated hypocenter parameters including `publicId` (links back to the input `.obs` event), `pdfVolume` (location PDF volume; smaller = tighter), the confidence-ellipsoid axes, etc.
- Merged result: `RESULT/NLL_result.csv` — deduplicated across all 6 zones; horizontal/vertical uncertainties `true_erh` / `true_erz` are derived from the 3-D confidence ellipsoid, rescaled to DOF-appropriate 68% confidence factors (not axis-aligned `errH`/`errZ` projections, and not NLL's raw 3-DOF ellipsoid scaling): `true_erz` is a 1-DOF marginal standard deviation, `true_erh` is a 2-DOF horizontal error ellipse reduced via the geometric mean of its semi-axes
- Does **not** contain magnitude or full pick metadata → rematching to `obs/GLOBAL.obs` via `publicId` is necessary
- `ellipsoidVolume` = 4/3·π·Len1·Len2·Len3, written alongside `true_erh`/`true_erz` for direct comparison against `pdfVolume`

### Location-PDF quality columns (`RESULT/SSST_result.csv` only)
Added by `NLL_run/pdf_metrics.py` from the `.scat` scatter clouds.
- `J` / `Psi` — negentropy `KL(p ‖ N(μ,Σ))` in nats and `Psi = exp(-J)`, the effective-volume ratio. `Psi = 1` is exactly Gaussian. **Directionless — never a rejection criterion on its own.**
- `C68` — posterior mass inside the nominal 68% ellipsoid. The only directional metric, so it drives keep/reject: `> 0.68` conservative (safe), `< 0.68` over-confident.
- `dip_stat` / `dip_pval` / `dip_sep_km` / `dip_reject` — Hartigan's dip test on the depth marginal, computed at a common subsample of 400 so p-values are comparable across events. `dip_sep_km` is the width of Hartigan's modal interval, i.e. how far apart the competing depths are. **`dip_reject` needs both conditions**: `dip_pval < 0.05` **and** `dip_sep_km > true_erz`. The dip statistic is a vertical distance on the ECDF and is invariant under rescaling of the depth axis, so it registers that a second mode exists but never how far away — on its own it discards events whose bimodality is real but sits entirely inside the quoted error, where `depth ± true_erz` already covers both modes. Requiring the separation term moves the count 5 329 → 661. The threshold is `_DIP_SEP_ERZ_FACTOR` in `pdf_metrics.py`; at 2.0 it would be vacuous (the `dip_sep_km`/`true_erz` ratio tops out at 2.24 over this catalog).
- `J_null_p95` / `C68_sigma_n` — per-event n-matched Gaussian nulls. **`J` and `C68` are uninterpretable without them**: the k-NN estimator bias depends on n, and the `C68` null spread is not binomial (μ/Σ are fitted on the samples being tested).
- `n_scat` — sample count backing every metric above.
- These measure **consistency, not accuracy** — velocity-model bias is invisible to all of them.

---

## Git Workflow

- All AI-generated commits go to the **`claude` branch**, never to `main`
- Commit messages must be clean and descriptive so changes are understandable without reading the diff
- Use the format `type: description` — e.g. `fix: ...`, `feat: ...`, `docs: ...`. Never use scoped form `fix(module): ...`
- **Never push automatically to main** — commit and push to the **`claude` branch** without asking, but notice the user
- The user reviews changes locally and decides when to merge or push to `main`

### Pull Request Format
- PR body: **Summary section only** (bullet points of what changed and why). No "Test plan" section.
