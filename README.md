# Shallow_Depth_DL_Catalog

A pipeline for building a unified, publication-quality earthquake catalog for the **Pyrenees region** (lat 41–45°N, lon -3 to 4°E), integrating data from five independent seismic networks over the period **1978–2025**.

The workflow covers catalog fetching, station inventory fusion, magnitude harmonization, event merging, two-stage probabilistic earthquake relocation with NonLinLoc (per-station delay corrections, then iterative SSST), and result visualization.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Pipeline](#pipeline)
  - [1. Station Inventory Fusion](#1-station-inventory-fusion)
  - [2. Catalog Fetching & Conversion](#2-catalog-fetching--conversion)
  - [3. Catalog Harmonization](#3-catalog-harmonization)
  - [4. Earthquake Relocation (NonLinLoc)](#4-earthquake-relocation-nonlinloc)
  - [5. Post-relocation Processing](#5-post-relocation-processing)
  - [6. External Pick Ingestion (temp_picks)](#6-external-pick-ingestion-temp_picks)
  - [7. SSST Relocation](#7-ssst-relocation)
- [Complementary Analysis](#complementary-analysis)
- [Dependencies](#dependencies)
- [A note on AI assistance](#a-note-on-ai-assistance)

---

## Overview

Five seismic catalogs are integrated:

| Source | Network | Format | Period |
|--------|---------|--------|--------|
| RESIF | French national network | FDSN / QuakeML | 2020–2025 |
| ICGC | Catalan network | Web / text | 2020–2025 |
| IGN | Spanish national network | Text | 2020–2025 |
| LDG | French seismological bulletin | Text | 2020–2025 |
| OMP | Pyrenean Observatory | Text / .mag | 1978–2019 |

All catalogs are converted to a common `.obs` format, magnitudes are harmonized to a common **ML (LDG)** scale, and events are merged into a single `GLOBAL.obs` bulletin. Earthquakes are then relocated using **NonLinLoc** across 6 geographic sub-zones, and final results are compiled into `RESULT/NLL_result.csv` and `obs/NLL_result.obs`. After external picks are ingested (`obs/NLL_result_augmented.obs`), a final **SSST** relocation stage (`run_SSST.py`, iterative NLLoc + Loc2ssst) produces `RESULT/SSST_result.csv` and `obs/SSST_result.obs`.

---

## Project Structure

```
Shallow_Depth_DL_Catalog/
│
├── fetch_all_bulletins.py        # Entry point: fetch & convert all catalogs
├── build_global_inventory.py     # Entry point: fuse all station inventories
├── build_global_bulletin.py      # Entry point: harmonize & merge catalogs
├── run_NLL.py                # Entry point: run NLL relocation (6 zones) and finalize the catalog
├── add_temp_picks.py             # Entry point: augment NLL_result.obs with external picks
├── run_SSST.py               # Entry point: SSST relocation of the augmented catalog
├── generate_complem_figures.py   # Entry point: matplotlib figures (seisbench_env)
├── generate_complem_maps.py      # Entry point: PyGMT event maps (pygmt_env)
├── run_gamma_detection.py        # Entry point: standalone PhaseNet/GaMMA detection
│
├── fetch_obs/                # Catalog fetching & .obs conversion modules
│   ├── RESIF.py
│   ├── ICGC.py
│   ├── IGN.py
│   ├── LDG.py
│   └── OMP.py
│
├── fetch_inventory/          # Station inventory fusion modules
│   ├── merge_station_inventories.py
│   ├── _remove_fdsn_duplicates.py
│   ├── _fill_missing_elevations.py
│   └── _convert_csv_to_stationxml.py
│
├── global_obs/               # Catalog harmonization modules
│   ├── remap_picks_to_unified_codes.py
│   ├── list_magnitude_types.py
│   ├── generate_magnitude_models.py
│   ├── apply_magnitude_models.py
│   ├── add_temporary_picks.py
│   ├── filter_events_by_aoi.py
│   ├── fuse_bulletins.py
│   └── plot_global_catalog_map.py
│
├── NLL_run/                  # NonLinLoc workflow modules
│   ├── run_zone.py                  # Run Vel2Grid → Grid2Time → NLLoc for one zone
│   ├── generate_regional_runfiles.py
│   ├── append_station_delays.py
│   ├── export_locdelay_info.py
│   ├── parse_nll_output.py          (deprecated)
│   ├── filter_distant_picks.py
│   ├── match_pre_post_relocation.py
│   ├── merge_regional_results.py
│   ├── generate_ssst_runfiles.py    # SSST: derive control files from the NLL run files
│   ├── reformate_obs.py             # SSST: split a bulletin into per-event .nlloc_obs
│   └── run_ssst.py                  # SSST: iterative NLLoc + Loc2ssst workflow (one zone)
│
├── complem_figures/          # Visualization & statistical analysis
│   ├── event_maps.py
│   ├── depth_maps.py
│   ├── error_maps.py
│   ├── depth_histogram.py
│   ├── gutenberg_richter.py
│   ├── cross_section.py
│   ├── station_map.py
│   └── zone_map.py
│
├── zone_Arette/              # Focused analysis of the Arette seismic zone
│
├── temp_picks/               # External pick ingestion & QC sub-pipeline
│   ├── build_theoretical_tables.py  # Compute P/S travel-time bands (Pyrocko/cake)
│   ├── merge_omp_picks.py           # Merge yearly OMP/PhaseNet CSV files
│   ├── merge_pyrenees_picks.py      # Merge RaspberryShake/PhaseNet text files
│   ├── convert_picks.py             # Convert external pick files to .obs format
│   ├── match_picks.py               # Match converted picks to bulletin events
│   ├── sort_picks.py                # Sort picks by arrival time within each event
│   ├── plot_travel_times.py         # Plot theoretical bands vs observed picks
│   ├── models/                      # Velocity model files (.nd)
│   ├── pick_files/                  # Input pick files (raw) + merged outputs
│   ├── tables_Pyr.csv               # Computed travel-time table
│   ├── figures/                     # Output figures
│   └── console_output/              # Log files
│
├── org_catalogs/              # Raw input catalogs (not modified)
├── obs/                      # .obs bulletin files (source + merged)
├── stations/                 # Station inventories (XML + unified)
├── run/                      # NLL working directory
│   ├── nll/                  # NLL run configuration files (.in) + locdelays/
│   ├── nll_model/            # Velocity model grids (NLL)
│   ├── nll_time/             # Travel time grids (NLL)
│   ├── nll_loc/              # NLL output files per zone
│   ├── ssst/                 # SSST control files (.in), per-zone tmp/, log/ (run journals)
│   ├── ssst_model/           # Velocity model grids (SSST, P+S)
│   ├── ssst_time/            # Travel time grids (SSST, P+S)
│   └── ssst_loc/             # SSST output per campaign (iterations + final locations)
├── RESULT/                   # Merged relocation results (.csv)
└── mag_model/                # Saved magnitude conversion models
```
(`obs/nlloc_obs/GLOBAL_<N>/` holds the per-event `.nlloc_obs` files of the SSST stage.)

---

## Conventions

All Python scripts in this project share the same interface contract:
- **CLI**: every script accepts `--help` and can be run directly from the command line
- **Public API**: every module is importable as a Python package (e.g. `from temp_picks.match_picks import match_picks`)
- **Logging**: timestamped log files are written to a `console_output/` directory local to each sub-pipeline

---

## Pipeline

Entry points, in execution order:

```
build_global_inventory.py → fetch_all_bulletins.py → build_global_bulletin.py
→ run_NLL.py → add_temp_picks.py → run_SSST.py
```

### 1. Station Inventory Fusion

**Script:** `build_global_inventory.py`  
**Module:** `fetch_inventory/merge_station_inventories.py` → `merge_inventory()`

Merges all station XML inventories (FDSN networks + OMP) into a single unified inventory. Each station receives a unique code; duplicates within 20 m are removed. OMP CSV data is pre-processed with `_remove_fdsn_duplicates.py`, `_fill_missing_elevations.py`, and `_convert_csv_to_stationxml.py` before fusion.

**Outputs:**
- `stations/GLOBAL_inventory.xml` — unified QuakeML inventory
- `stations/GLOBAL_code_map.txt` — mapping between original and unified station codes

---

### 2. Catalog Fetching & Conversion

**Script:** `fetch_all_bulletins.py`  
**Modules:** `fetch_obs/` (one module per source)

Downloads or reads each catalog and converts it to the `.obs` format. RESIF and ICGC are fetched dynamically; IGN, LDG, and OMP are read from local files in `org_catalogs/`.

**Outputs:** individual `.obs` files in `obs/`  
(e.g. `RESIF_20-25.obs`, `IGN_20-25.obs`, `OMP_78-19.obs`, …)

#### .obs format

Each event occupies one block separated by a blank line:

```
# YYYY MM DD HH MM SS.ss  Lat  Lon  Dep  Mag  MagType  Author  Nph  ErrH  ErrV  Gap  RMS
STA.CODE  INS  CMP  ONSET  PHASE  DIR  YYYYMMDD  HHMM  S.MS  Err  ErrMag  Coda  Amp  Period  # Phase  Chan  Origin  PGV
...
```

---

### 3. Catalog Harmonization

**Script:** `build_global_bulletin.py`  
**Module:** `global_obs/`

Runs the following steps in sequence:

| Step | Module | Function | Description |
|------|--------|----------|-------------|
| 1 | `remap_picks_to_unified_codes.py` | `remap_picks_to_unified_codes()` | Associates picks with unified station codes from global inventory |
| 2 | `generate_magnitude_models.py` | `convert_magnitudes()` | Builds piecewise ODR regression models (breakpoint at M=2): MLv RESIF, mb_Lg IGN, ML ICGC → ML LDG |
| 3 | `apply_magnitude_models.py` | `apply_magnitude_models()` | Applies the models to convert all `.obs` magnitudes to ML LDG |
| 4 | `filter_events_by_aoi.py` | `filter_events_by_aoi()` | Removes events outside the area of interest |
| 5 | `fuse_bulletins.py` | `find_and_merge_doubles()` | Deduplicates each source catalog individually before fusion |
| 6 | `fuse_bulletins.py` | `fuse_bulletins()` | Matches and merges all cleaned catalogs into `GLOBAL.obs` |
| 7 | `plot_global_catalog_map.py` | `plot_global_catalog_map()` | Generates a map of the merged catalog |

**Matching thresholds (step 6 fusion):** strict ≤15 km / ≤2 s / ≤1.5 mag units (ML–ML pairs); loose ≤50 km / ≤30 s, confirmed by ≥1 shared P-phase pick (same station, Δt ≤ 1 s).

**Outputs:**
- `obs/GLOBAL.obs` — unified catalog
- `obs/MAPS/` — statistics figures
- `mag_model/` — serialized magnitude models

---

### 4. Earthquake Relocation (NonLinLoc)

The study area is too large for a single NLL run, so it is divided into **6 geographic zones**. Each zone is processed independently — up to **3 zones run concurrently** — then results are merged.

**Script:** `run_NLL.py`

For each zone:

1. **First pass.** Calls `NLL_run/generate_regional_runfiles.py` → `generate_run()`:
   - Generates `obs/GLOBAL_<N>.obs` (regional subset, with far picks removed — done once globally before any zone starts)
   - Generates `stations/GTSRCE_<N>.txt` (station list)
   - Generates `run/nll/run_<N>_DELAYS.in` (NLL configuration file)

   NLL is then launched automatically via `NLL_run/run_zone.py`, which runs Vel2Grid → Grid2Time → NLLoc in sequence. Before each run it checks free disk space on the output filesystem, and after each step it scans the subprocess output for fatal disk/memory errors (which NLL programs can otherwise report as a silent exit code 0), aborting the pipeline if one is detected. Console log lines are prefixed with the zone label (e.g. `[zone 3]`) since multiple zones may log concurrently.
   - Cleans up `.hdr` files left by NLL in the `run/nll_loc/GLOBAL_<N>/` folder.

2. **Second (corrections) pass.** Calls `NLL_run/append_station_delays.py` → `append_station_delays()` to read per-station average residuals (LOCDELAY entries) from the first pass and append qualifying station delay corrections to a second-pass run file `run/nll/run_<N>_NLL.in`. NLLoc is then launched automatically via `NLL_run/run_zone.py` with `--corrections-pass` (Vel2Grid and Grid2Time are skipped since the grids are already built).
   - Cleans up `.hdr` files left by NLL in the `run/nll_loc/GLOBAL_<N>/` folder again, right after this zone's second pass, and deletes the zone's travel-time grids (`run/nll_time/Pyrenees_<N>/`) — nothing reads them after the second pass and they dominate disk usage. This per-zone cleanup keeps at most a few zones' worth on disk at a time instead of waiting for all 6 zones to finish.

`generate_run()` and `append_station_delays()` reconfigure a shared logger on every call, which isn't safe if two zones call them at the same instant, so `run_NLL.py` serializes just those two (fast, non-NLL) calls behind a lock; the slow NLL subprocess runs themselves are not serialized and run fully in parallel across zones.

#### Diagnostic — `NLL_run/export_locdelay_info.py`

Called automatically by `run_NLL.py` once all zones have completed both passes. Reads the LOCDELAY station corrections from all second-pass run files and exports them to `run/nll/locdelays/locdelay_summary.txt`, keeping only entries with |residual| > 0.3 s. Useful for identifying stations with systematically biased travel-time residuals.

---

### 5. Post-relocation Processing

**Script:** `run_NLL.py` (runs after all 6 zones complete)
**Modules:** `NLL_run/merge_regional_results.py`, `NLL_run/match_pre_post_relocation.py`

1. Reads the 6 per-zone NLL CSV summaries (`run/nll_loc/GLOBAL_<N>/GLOBAL_<N>.obs.sum.grid0.loc.csv`), deduplicates events that appear in multiple overlapping zones (kept: lowest `pdfVolume`), and writes → `RESULT/NLL_result.csv`. True horizontal/vertical errors (`true_erh` / `true_erz`) are derived from the 3-D confidence ellipsoid, rescaled to DOF-appropriate 68% confidence factors: `true_erz` is a 1-DOF marginal standard deviation, `true_erh` is a 2-DOF horizontal error ellipse reduced to the geometric mean of its semi-axes.
2. Rematches relocated events back to `obs/GLOBAL.obs` via the `publicId` field to recover metadata absent from NLL output (magnitude, pick details, etc.).
3. Saves matched events → `obs/NLL_result.obs`

---

### 6. External Pick Ingestion (temp_picks)

**Script:** `add_temp_picks.py`
**Modules:** `temp_picks/`

Sits between the NLL and SSST relocation stages: a self-contained sub-pipeline for ingesting picks from external sources into `obs/NLL_result.obs`, producing `obs/NLL_result_augmented.obs` (the input of `run_SSST.py`). The root-level script **`add_temp_picks.py`** orchestrates steps 1–6 automatically; steps whose output already exists are skipped.

| Step | Script | Description |
|------|--------|-------------|
| 1 | `build_theoretical_tables.py` | Uses Pyrocko's `cake` CLI to compute P/S travel-time envelopes across ±5% velocity models and source depths of 0–30 km, for epicentral distances 0–100 km → `tables_Pyr.csv` |
| 2 | `plot_travel_times.py` | QC figure: overlays all observed (distance, travel time) picks from a bulletin on top of the theoretical P/S bands. Skipped if the figure already exists. Also usable as a standalone script. |
| 3 | `merge_omp_picks.py` | Merges all yearly OMP/PhaseNet CSV files from `picks_OMP/` subdirectories → `pick_files/merged_omp.csv`. Station `SMC` and year `2026` are excluded by default; configurable via `--drop-years`. Rows with a PhaseNet `phase_score` below 0.5 (default) are dropped. |
| 4 | `merge_pyrenees_picks.py` | Concatenates RaspberryShake/PhaseNet `.txt` files from `picks_station_pyrenees/` and `picks_station_pyrenees2/` → `pick_files/merged_pyrenees.txt` and `pick_files/merged_pyrenees2.txt`. Lines with a `prob=` value below 0.5 (default) are dropped. |
| 5 | `convert_picks.py` | Converts external pick files to the project's `.obs` pick line format; maps short station names to internal codes via `GLOBAL_code_map.txt`. Supports formats `TEMP_OBS`, `TEMP_RSB`, `TEMP_OMP`, `TEMP_OTH`, and `TEMP_STB`; new formats are added as handler functions. `TEMP_STB` (Strasbourg/RENASS-OMP picks, `temp_picks/all_picks/PICKS_MARC/`) reads directories of parquet files instead of a single text file, and drops picks below a `phase_score` threshold (default 0.5). Unresolved stations are reported as an end-of-run summary. |
| 6 | `match_picks.py` | For each converted pick, finds candidate events within a 60 s origin-time window, filters by theoretical travel-time residual (±0.1 s P, ±0.3 s S, plus ±2.5 s t0-error margin), and appends matched picks to the bulletin. Chains against `obs/NLL_result.obs` → `obs/NLL_result_augmented.obs`. Runs `sort_picks` automatically on the output. |
| — | `sort_picks.py` | Sorts all pick lines within each event block by ascending arrival time. Invoked automatically by step 6; also usable as a standalone script on any bulletin. |

---

### 7. SSST Relocation

**Script:** `run_SSST.py`
**Modules:** `NLL_run/generate_ssst_runfiles.py`, `NLL_run/reformate_obs.py`, `NLL_run/run_ssst.py`

Final relocation stage, run **after** `run_NLL.py` and `add_temp_picks.py`. It relocates the augmented catalog (`obs/NLL_result_augmented.obs`) with **Source-Specific Station Terms** (NonLinLoc's `Loc2ssst`): instead of the single static `LOCDELAY` correction per station of the NLL stage, each station/phase gets a 3-D correction grid, smoothed with a characteristic distance that shrinks over iterations (`CHAR_DISTS`, default `[9999, 50, 15, 5, 1]` km — the first, huge value is equivalent to static terms). Each iteration relocates the catalog with the previous iteration's corrected travel-time grids, then recomputes the corrections from the new residuals; a final NLLoc-only pass relocates the catalog with the last grids (saving oct-tree and fmamp output).

Zones are processed **strictly sequentially** (Loc2ssst holds two full correction-grid buffers in RAM per instance), but everything inside a zone runs in parallel: the catalog is split round-robin across `NLLOC_CORES` concurrent NLLoc processes, and the station list across `LOC2SSST_CORES` concurrent Loc2ssst instances (a per-station split is exact — each station's correction depends only on its own residuals).

Per zone:

1. **`NLL_run/generate_ssst_runfiles.py`** — cuts the zone bulletin `obs/GLOBAL_<N>_SSST.obs` from the augmented catalog, writes `stations/GTSRCE_SSST_<N>.txt` (only the stations picked in the zone), and derives both control files from the NLL-stage `run/nll/run_<N>_DELAYS.in` (TRANS, grids, and localization parameters are reused verbatim, so the zone information entered in `run_NLL.py` stays the single source of truth): `run/ssst/run_<N>_NLL.in` (NLLoc) and `run/ssst/run_<N>_SSST.in` (Loc2ssst, with LSGRID/LSOUTGRID derived from the LOCGRID extent at a coarse 1 km spacing).
2. **`NLL_run/reformate_obs.py`** — splits the zone bulletin into one `.nlloc_obs` file per event in `obs/nlloc_obs/GLOBAL_<N>/` (named and headed by `publicId`, which NLLoc propagates into its output — the rematch key).
3. **`NLL_run/run_ssst.py`** — builds the initial **P and S** travel-time grids (`VpVs = -9.99`: real S grids, so S station terms are gridded independently; skipped when already present), then runs the iteration loop. Fails fast on any non-zero NLLoc/Loc2ssst exit, on fatal disk/memory errors in the subprocess logs, and on empty obs/grid globs. Supports partial campaigns and resuming (`--iteration-start` / `--iteration-stop`).
4. **Grid cleanup** — the zone's travel-time grids (the big disk consumers) are deleted automatically once the zone is done: every `ssst_corr<i>/` grid set except the last, which is kept with its symlinks materialized (the resume input of a partial campaign, the reusable final SSST model of a finished one). The initial grids (`run/ssst_time/Pyrenees_<N>/`) go too as soon as iteration 0 has run.

Once all zones are complete, the final-iteration CSVs feed the same chain as the NLL stage: `merge_regional_results.merge_bulletins` → `RESULT/SSST_result.csv` (zone-overlap duplicates resolved by lowest `pdfVolume`), then `match_pre_post_relocation.save_bulletin` rematching against `obs/NLL_result_augmented.obs` → `obs/SSST_result.obs`.

The campaign configuration (`RUN_NAME`, `CHAR_DISTS`, `VPVS`, core counts, `LSPHSTAT` — whose `NRdgsMin` doubles as the NLLoc min-phases threshold, read back from the generated Loc2ssst control so the two selections cannot diverge) lives at the top of `run_SSST.py`. Per-zone run journals are written to `run/ssst/log/`; intermediate location outputs (`loc_ssst_corr<i>/`) are deletable after validation (each journal ends with the ready-to-paste commands), and the chunk directories of each iteration are deleted automatically after each merge.

Reference document: `SSST_INTEGRATION.md` (porting notes from the validated CODES_SSST workflow).

---

## Complementary Analysis

Two driver scripts run the `complem_figures/` modules in **different conda environments**:
- `generate_complem_figures.py` (`seisbench_env`) — matplotlib figures: depth histograms, Gutenberg-Richter distributions, and per-period depth and error maps
- `generate_complem_maps.py` (`pygmt_env`) — PyGMT event maps for each of the 6 NLL zones and the final catalog

Each module can also be run standalone:

| Script | Description |
|--------|-------------|
| `event_maps.py` | Geographic maps of seismicity (from `.obs`, `.txt`, or `.csv` NLL summary) |
| `depth_maps.py` | Per-period windowed-median depth maps |
| `error_maps.py` | Per-period spatial distribution of location uncertainties (ERH, ERV) |
| `depth_histogram.py` | Histogram of event depths |
| `gutenberg_richter.py` | Magnitude-frequency distribution (Gutenberg-Richter law) |
| `cross_section.py` | Vertical cross-sections of seismicity |
| `station_map.py` | Map of seismic stations |
| `zone_map.py` | Overview map of the 6 NLL relocation zones |

Map modules apply a quality filter (erh ≤ 3 km, erv ≤ 3 km, gap ≤ 300°, rms ≤ 0.5 s) by default; use `--no-filter` for pre-relocation catalogs where errors are unavailable.

`zone_Arette/` contains a focused analysis of the Arette seismic zone, including gap/RMS statistics across different station distance cutoffs and yearly temporal analysis.

---

## Dependencies

| Package | Use |
|---------|-----|
| `obspy` | Seismic data I/O, FDSN client, inventory management |
| `pandas`, `numpy` | Data manipulation |
| `pyarrow` | Parquet I/O (`temp_picks/convert_picks.py`'s `TEMP_STB` format) |
| `scipy` | ODR regression, spatial queries (KDTree), statistics |
| `scikit-learn` | Regression diagnostics (R²) for magnitude models |
| `matplotlib`, `seaborn` | Plotting |
| `xarray` | Grid handling for cross-sections |
| `pygmt` | Geographic maps (requires separate `pygmt_env` conda environment) |
| `joblib` | Magnitude model serialization |
| `requests` | ICGC catalog fetching |
| `seisbench`, `torch` | PhaseNet phase detection — `run_gamma_detection.py` |
| `gamma` | GaMMA event association — `run_gamma_detection.py` |
| `pyproj` | Coordinate transformations |
| **NonLinLoc** | Probabilistic earthquake location — Vel2Grid, Grid2Time, NLLoc, Loc2ssst (external tool, invoked automatically by `run_NLL.py` / `run_SSST.py`) |
| **Pyrocko** / **cake** | Theoretical travel-time computation (`temp_picks/build_theoretical_tables.py`) |

---

## A note on AI assistance

Parts of this codebase were written or modified with the help of **[Claude Code](https://claude.ai/code)** (Anthropic). As a researcher, I believe in being transparent about the use of AI tools in scientific work. All AI-generated code in this project has been reviewed before being committed to the main branch.
