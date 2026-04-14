# Seisbench2025

A pipeline for building a unified, publication-quality earthquake catalog for the **Pyrenees region** (lat 41–45°N, lon -3 to 4°E), integrating data from five independent seismic networks over the period **1978–2025**.

The workflow covers catalog fetching, station inventory fusion, magnitude harmonization, event merging, probabilistic earthquake relocation with NonLinLoc, and result visualization.

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

All catalogs are converted to a common `.obs` format, magnitudes are harmonized to **ML**, and events are merged into a single `GLOBAL.obs` bulletin. Earthquakes are then relocated using **NonLinLoc** across 6 geographic sub-zones, and final results are compiled into `RESULT/FINAL.txt` and `obs/FINAL.obs`.

---

## Project Structure

```
Seisbench2025/
│
├── fetch_all_bulletins.py        # Entry point: fetch & convert all catalogs
├── build_global_inventory.py     # Entry point: fuse all station inventories
├── build_global_bulletin.py      # Entry point: harmonize & merge catalogs
├── prepare_nll_inputs.py         # Entry point: prepare NLL run files (6 zones)
├── generate_nll_corrections.py   # Entry point: prepare second-pass NLL run files
├── finalize_nll_catalog.py       # Entry point: compile and match final catalog
├── parameters.py             # Simple parameter container class
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
│   ├── filter_events_by_aoi.py
│   ├── fuse_bulletins.py
│   └── plot_global_catalog_map.py
│
├── NLL_run/                  # NonLinLoc workflow modules
│   ├── generate_regional_runfiles.py
│   ├── append_ssst_corrections.py
│   ├── parse_nll_output.py
│   ├── filter_distant_picks.py
│   ├── match_pre_post_relocation.py
│   └── merge_regional_results.py
│
├── complem_figures/          # Visualization & statistical analysis
│   ├── event_maps.py
│   ├── depth_maps.py
│   ├── error_maps.py
│   ├── cross_section.py
│   └── gutenberg_richter.py
│
├── zone_Arette/              # Focused analysis of the Arette seismic zone
│
├── temp_picks/               # External pick ingestion & QC sub-pipeline
│   ├── build_theoretical_tables.py  # Compute P/S travel-time bands (Pyrocko/cake)
│   ├── convert_picks.py             # Convert external pick files to .obs format
│   ├── match_picks.py               # Match converted picks to bulletin events
│   ├── sort_picks.py                # Sort picks by arrival time within each event
│   ├── plot_travel_times.py         # Plot theoretical bands vs observed picks
│   ├── models/                      # Velocity model files (.nd)
│   ├── pick_files/                  # Input pick files (raw external format)
│   ├── tables_Pyr.csv               # Computed travel-time table
│   ├── figures/                     # Output figures
│   └── console_output/              # Log files
│
├── ORGCATALOGS/              # Raw input catalogs (not modified)
├── obs/                      # .obs bulletin files (source + merged)
├── stations/                 # Station inventories (XML + unified)
├── run/                      # NLL run configuration files (.in)
├── loc/                      # NLL output files per zone
├── RESULT/                   # Parsed relocation results (.txt)
├── model/                    # Velocity model grids (NLL)
├── time/                     # Travel time grids (NLL)
└── MAGMODELS/                # Saved magnitude conversion models
```

---

## Pipeline

### 1. Station Inventory Fusion

**Script:** `build_global_inventory.py`  
**Module:** `fetch_inventory/merge_station_inventories.py` → `mergeInventory()`

Merges all station XML inventories (FDSN networks + OMP) into a single unified inventory. Each station receives a unique code; duplicates within 20 m are removed. OMP CSV data is pre-processed with `_remove_fdsn_duplicates.py`, `_fill_missing_elevations.py`, and `_convert_csv_to_stationxml.py` before fusion.

**Outputs:**
- `stations/GLOBAL_inventory.xml` — unified QuakeML inventory
- `stations/GLOBAL_code_map.txt` — mapping between original and unified station codes

---

### 2. Catalog Fetching & Conversion

**Script:** `fetch_all_bulletins.py`  
**Modules:** `fetch_obs/` (one module per source)

Downloads or reads each catalog and converts it to the `.obs` format. RESIF and ICGC are fetched dynamically; IGN, LDG, and OMP are read from local files in `ORGCATALOGS/`.

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
| 1 | `remap_picks_to_unified_codes.py` | `associatePicks()` | Associates picks with unified station codes from global inventory |
| 2 | `generate_magnitude_models.py` | `convertMagnitudes()` | Builds ODR regression models: MLv→ML, mb_Lg→ML, ML(ICGC)→ML |
| 3 | `apply_magnitude_models.py` | `updateAllFiles()` | Applies magnitude models to all `.obs` files |
| 4 | `filter_events_by_aoi.py` | — | Removes events outside the area of interest |
| 5 | `fuse_bulletins.py` | `fusionAll()`, `find_and_merge_doubles()` | Matches and merges all catalogs into `GLOBAL.obs` |
| 6 | `plot_global_catalog_map.py` | — | Generates a map of the merged catalog |

**Matching thresholds (fusion):** ≤15 km distance, ≤2 s time, ≤1.5 magnitude units, ≥2 common picks.

**Outputs:**
- `obs/GLOBAL.obs` — unified catalog
- `obs/MAPS/` — statistics figures
- `MAGMODELS/` — serialized magnitude models

---

### 4. Earthquake Relocation (NonLinLoc)

The study area is too large for a single NLL run, so it is divided into **6 geographic zones**. Each zone is processed independently, then results are merged.

#### Pre-run — `prepare_nll_inputs.py`

Calls `NLL_run/generate_regional_runfiles.py` → `genRun()` for each zone:
- Generates `obs/GLOBAL_1.obs` … `obs/GLOBAL_6.obs` (regional subsets, with far picks removed)
- Generates `stations/GTSRCE_1.txt` … `stations/GTSRCE_6.txt` (station lists)
- Generates `run/run_1.in` … `run/run_6.in` (NLL configuration files)

Then run NLL externally for each zone:

```bash
Vel2Grid run/run_<N>.in
Grid2Time run/run_<N>.in
NLLoc run/run_<N>.in
```

#### Second pass (SSST) — `generate_nll_corrections.py`

Uses arrival-time residuals from the first run to compute station corrections (SSST), then generates second-pass run files `run/run_<N>_PR.in`.

Run NLL again:

```bash
Vel2Grid run/run_<N>_PR.in
Grid2Time run/run_<N>_PR.in
NLLoc run/run_<N>_PR.in
```

---

### 5. Post-relocation Processing

**Script:** `finalize_nll_catalog.py`  
**Modules:** `NLL_run/parse_nll_output.py`, `NLL_run/merge_regional_results.py`, `NLL_run/match_pre_post_relocation.py`

1. Parses NLL `.hypo_71` output files for each zone → `RESULT/GLOBAL_<N>_PR.txt`
2. Merges all 6 regional results → `RESULT/FINAL.txt`
3. Rematches relocated events back to `obs/GLOBAL.obs` to recover metadata absent from NLL output (magnitude, pick details, etc.)
4. Saves matched events → `obs/FINAL.obs`

---

## Complementary Analysis

Scripts in `complem_figures/` for post-processing visualization:

| Script | Description |
|--------|-------------|
| `event_maps.py` | Geographic maps of seismicity (from `.obs` or `.txt`) |
| `depth_maps.py` | Depth distribution maps |
| `error_maps.py` | Spatial distribution of location uncertainties (ERH, ERV) |
| `cross_section.py` | Vertical cross-sections of seismicity |
| `gutenberg_richter.py` | Magnitude-frequency distribution (Gutenberg-Richter law) |

`zone_Arette/` contains a focused analysis of the Arette seismic zone, including gap/RMS statistics across different station distance cutoffs and yearly temporal analysis.

---

## External Pick Ingestion (temp_picks)

Scripts in `temp_picks/` implement a self-contained sub-pipeline for ingesting picks from external sources (e.g. Pyrocko-generated bulletins) into `GLOBAL.obs`.

| Step | Script | Description |
|------|--------|-------------|
| 1 | `build_theoretical_tables.py` | Uses Pyrocko's `cake` CLI to compute P/S travel-time envelopes across ±5% velocity models and source depths of 0–30 km, for epicentral distances 0–100 km → `tables_Pyr.csv` |
| 2 | `convert_picks.py` | Converts external pick files to the project's `.obs` pick line format; maps short station names to internal codes via `GLOBAL_code_map.txt`. Supports format `TEMP_OBS`; new formats are added as handler functions. |
| 3 | `match_picks.py` | For each converted pick, finds candidate events within a 60 s origin-time window, filters by theoretical travel-time residual (±0.1 s P, ±0.3 s S), and appends matched picks to the bulletin. Runs `sort_picks` automatically on the output. |
| 4 | `sort_picks.py` | Sorts all pick lines within each event block by ascending arrival time. Also usable as a standalone script on any bulletin. |
| 5 | `plot_travel_times.py` | QC figure: overlays all observed (distance, travel time) picks from a bulletin on top of the theoretical P/S bands. |

All scripts are importable as a Python package (`from temp_picks.match_picks import match_picks`) and accept `--help` for CLI usage.

---

## Dependencies

| Package | Use |
|---------|-----|
| `obspy` | Seismic data I/O, FDSN client, inventory management |
| `pandas`, `numpy` | Data manipulation |
| `scipy` | ODR regression, spatial queries (KDTree), statistics |
| `matplotlib`, `seaborn` | Plotting |
| `pygmt` | Geographic maps (requires separate `pygmt_env` conda environment) |
| `joblib` | Magnitude model serialization |
| `requests` | ICGC catalog fetching |
| `seisbench`, `torch` | PhaseNet phase detection (`run_gamma_detection.py`) |
| `pyrocko` / `cake` | Theoretical travel-time computation (`temp_picks/build_theoretical_tables.py`) |
| `pyproj` | Coordinate transformations |
| **NonLinLoc** | Probabilistic earthquake location (external tool, run manually) |

---

## A note on AI assistance

Parts of this codebase were written or modified with the help of **[Claude Code](https://claude.ai/code)** (Anthropic). As a researcher, I believe in being transparent about the use of AI tools in scientific work. All AI-generated code in this project has been reviewed and verified line-by-line before being committed to the main branch.
