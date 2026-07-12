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
- Reference: `SSST_INTEGRATION.md` (porting notes from the validated CODES_SSST workflow).

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

> **Environments**:
> - `seisbench_env` → `generate_complem_figures.py` (Gutenberg-Richter, depth maps, error maps)
> - `pygmt_env`     → `generate_complem_maps.py` (event maps for each zone and final catalog)

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
| `convert_picks.py` | Converts external pick files to `.obs` pick line format; maps station names to internal codes via `GLOBAL_code_map.txt`. Formats `TEMP_OBS`, `TEMP_RSB`, and `TEMP_OMP` are supported; new formats are registered in `FORMAT_HANDLERS`. Unresolved stations are logged as an end-of-run summary. |
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

---

## Git Workflow

- All AI-generated commits go to the **`claude` branch**, never to `main`
- Commit messages must be clean and descriptive so changes are understandable without reading the diff
- Use the format `type: description` — e.g. `fix: ...`, `feat: ...`, `docs: ...`. Never use scoped form `fix(module): ...`
- **Never push automatically to main** — commit and push to the **`claude` branch** without asking, but notice the user
- The user reviews changes locally and decides when to merge or push to `main`

### Pull Request Format
- PR body: **Summary section only** (bullet points of what changed and why). No "Test plan" section.
