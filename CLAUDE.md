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
- Each event carries `pyr:usable` = `(C68 − 0.68)/C68_sigma_n ≥ −2` **and** `not dip_reject` **and** metrics present → 40 793 usable / 5 431 unusable, plus a `pyr:rejectReason` string. **Ψ is exported but never rejects** (directionless; 81 % of the catalog exceeds its own `J` null). The `C68` cut is against the simulated null, not raw 0.68 — that difference is 155 events flagged instead of 2 944.
- Station codes are resolved to real `NET.STA` via inventory `alternate_code`, epoch-aware; the unified code is kept as `pyr:unifiedCode` on every pick.
- `Mag 0.00` (5 010 events) is an OMP placeholder, written through unchanged because magnitudes are recomputed later — do not fit it as data.

---

## Complementary Analysis

Scripts in `complem_figures/` for visualization and statistics:
- `event_maps.py` — geographic maps of seismicity
- `gutenberg_richter.py` — magnitude-frequency distribution
- `depth_maps.py` — depth distribution
- `depth_histogram.py` — histogram of event depths
- `error_maps.py` — location uncertainty maps
- `cross_section.py` — vertical cross-sections
- `station_map.py` — map of seismic stations
- `zone_map.py` — overview map of the 6 NLL zones
- `event_ranking.py` — ranks events by pdfVolume/ellipsoidVolume change (NLL → SSST); flags multi-zone/zone-changed events; carries the PDF-quality columns (post-SSST only) when `pdf_metrics.py` has annotated the CSV, and runs without them otherwise; optional gridmap PDF
- `plot_pdf_cloud.py` — interactive 3D PDF scatter-cloud of one event across SSST iterations (Plotly)
- `ssst_evolution.py` — per-zone pdfVolume/EllipsoidLen3/RMS evolution across SSST iterations (convergence QC)

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
- `dip_stat` / `dip_pval` / `dip_reject` — Hartigan's dip test on the depth marginal, computed at a common subsample of 400 so p-values are comparable across events. A rejection means two competing depth solutions and no defensible scalar depth.
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
