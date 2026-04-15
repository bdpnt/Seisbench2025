# CLAUDE.md — Seisbench2025

## Project Overview

Seisbench2025 is an earthquake catalog processing and relocation pipeline focused on the **Pyrenees region** (latitude 41–45°N, longitude -3 to 4°E), covering seismicity from **1978 to 2025**.

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
- Sources: RESIF (FDSN), ICGC, IGN, LDG, OMP (in `ORGCATALOGS/`)
- Script: `fetch_all_bulletins.py` → calls modules in `fetch_obs/`
- Output: individual `.obs` files per source in `obs/`

### 3. Catalog Harmonization
- Script: `build_global_bulletin.py` → calls modules in `global_obs/`
- Steps:
  1. **remap_picks_to_unified_codes.py** — associates picks with unified station codes
  2. **generate_magnitude_models.py** — builds regression models to convert all magnitude types to ML
  3. **apply_magnitude_models.py** — applies the models to all `.obs` files
  4. **fuse_bulletins.py** — spatially/temporally merges all catalogs into `obs/GLOBAL.obs`
  5. **plot_global_catalog_map.py** — generates a map of the merged catalog
- Matching thresholds: 15 km distance, 2 s time, 1.5 magnitude units, ≥2 picks

### 4. Earthquake Relocation (NonLinLoc)
The study area is too large for a single NLL run, so it is split into **6 geographic zones**.

- **`prepare_nll_inputs.py`** — generates one `.obs` file and one `.in` run file per zone, plus GTSRCE station files
- External (run manually in terminal):
  ```
  Vel2Grid run/<runfile.in>
  Grid2Time run/<runfile.in>
  NLLoc run/<runfile.in>
  ```
- **`generate_nll_corrections.py`** — generates second-pass run files using SSST (Static Station Set Travel-time) corrections from the first run
- Second pass: same external commands repeated

### 5. Post-relocation Processing
- **`finalize_nll_catalog.py`**:
  1. Cleans NLL output files
  2. Merges the 6 regional results into `RESULT/FINAL.txt`
  3. Rematches relocated events back to `obs/GLOBAL.obs` to recover metadata not present in NLL output (e.g. magnitude)
  4. Saves matched events to `obs/FINAL.obs`

---

## Complementary Analysis

Scripts in `complem_figures/` for visualization and statistics:
- `event_maps.py` — geographic maps of seismicity
- `gutenberg_richter.py` — magnitude-frequency distribution
- `depth_maps.py` — depth distribution
- `error_maps.py` — location uncertainty maps
- `cross_section.py` — vertical cross-sections

`zone_Arette/` — focused analysis of the Arette seismic zone.

---

## Key Data Formats

### `.obs` (custom seismic bulletin)
- One block per event, separated by blank lines
- Event line starts with `# `: location, magnitude, quality parameters (azimuth gap, RMS, horizontal/vertical uncertainty)
- Following lines: one pick per station (station code, phase P/S, arrival time, uncertainties)

### NLL output
- `.hyp` / `FINAL.txt` — relocated hypocenter parameters
- Does **not** contain magnitude or full pick metadata → rematching to `.obs` is necessary

---

## Git Workflow

- All AI-generated commits go to the **`claude` branch**, never to `main`
- Commit messages must be clean and descriptive so changes are understandable without reading the diff
- **Never push automatically to main** — commit and push to the **`claude` branch** without asking, but notice the user
- The user reviews changes locally and decides when to merge or push to `main`
