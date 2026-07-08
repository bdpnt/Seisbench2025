# SSST_INTEGRATION.md — Porting the NLL-SSST workflow into Shallow_Depth_DL_Catalog

Reference document for building a new project module from the two scripts
validated in `/Users/bdupont/Desktop/Codes/CODES_SSST`:

| Source file | Role |
|---|---|
| `CODES_SSST/run_ssst_VF.py` | Iterative NLLoc + Loc2ssst SSST relocation workflow (validated on 624 events, 5 SSST iterations + final relocation) |
| `CODES_SSST/reformate_box.py` | Converts a multi-event `.obs` bulletin into per-event `.nlloc_obs` files |
| `CODES_SSST/NLL_run_6.in` | Working example of the NLLoc control file (`NLL_XXX.in`) |
| `CODES_SSST/SSST_run_6.in` | Working example of the Loc2ssst control file (`SSST_XXX.in`) |

---

## 1. Purpose & target workflow

### What NLL-SSST adds over the current pipeline

The existing `run_NLL.py` pipeline applies **static** per-station delay
corrections (`LOCDELAY`, one number per station/phase, derived from first-pass
residuals): the first-pass run file `run/nll/run_<N>_DELAYS.in` produces the
residuals, and the second-pass `run/nll/run_<N>_NLL.in` applies the resulting
`LOCDELAY` lines. SSST (Source-Specific Station Terms, via NonLinLoc's `Loc2ssst`)
replaces this with **spatially varying** correction grids: each station/phase
gets a 3-D correction volume, smoothed with a characteristic distance that
shrinks over iterations (first iteration ≈ static terms, last iterations
capture local structure). Each iteration relocates the catalog with the
previous iteration's corrected travel-time grids, then recomputes corrections
from the new residuals. A final NLLoc-only pass relocates the full catalog
with the last corrected grids.

Measured on the CODES_SSST test run (zone 6, 624 events, `CHAR_DISTS =
[9999, 50, 15, 5, 1]`): mean RMS 0.154 → 0.094 s, median RMS 0.144 → 0.068 s
across iterations.

### Module contract (first sketch)

1. Generate the `.obs` files per zone (already available:
   `NLL_run/generate_regional_runfiles._gen_child_obs` writes
   `obs/GLOBAL_<N>.obs` from `obs/GLOBAL.obs` and the `_ZONES` bounding boxes
   in `run_NLL.py`).
2. Then, **zone per zone, strictly sequentially** (SSST is memory-bound, see
   §5 — zones cannot run concurrently like they do in `run_NLL.py`):
   1. `reformate_box.py` logic → one `.nlloc_obs` file per event;
   2. generate the two control files `NLL_<N>.in` and `SSST_<N>.in`;
   3. run the `run_ssst_VF.py` workflow → per-zone relocated outputs.

Parallelism lives **inside** a zone: `NUM_CORES` concurrent NLLoc processes
(catalog split into obs-file chunks) and `NUM_CORES` concurrent Loc2ssst
processes (station list split into disjoint sets).

---

## 2. Source script: `run_ssst_VF.py`

### How it works

- **Iteration plan** — `CHAR_DISTS` is the list of smoothing widths (km).
  Iteration `N` (0-based) = one NLLoc relocation + one Loc2ssst with
  `LSPARAMS CHAR_DISTS[N] 0.0000001`. First value huge (9999) → static
  corrections. After `len(CHAR_DISTS)` SSST iterations, iteration
  `len(CHAR_DISTS)` is a **final NLLoc-only** relocation of `CATALOG_FINAL`
  (may be a superset of `CATALOG`) with `SAVE_NLLOC_OCTREE` and `SAVE_FMAMP`
  forced on. The CLI takes one optional `iteration_start` for resuming.
- **Grid chaining** — iteration 0 locates with the initial Grid2Time grids
  (`INIT_TIME_ROOT`); each Loc2ssst writes corrected grids to
  `ssst_corr{N}/<catalog>/<model>` which become the next iteration's
  `time_root`. Before each Loc2ssst, **all** current `*.time.*` grids are
  symlinked into the new directory; Loc2ssst then overwrites the links of the
  stations it corrects with real files, so stations without corrections keep
  resolving to their previous grid instead of disappearing.
- **Skeleton mechanism** — `_build_skeleton_conf()` copies `CONTROL_FILE`
  with any line containing `INCLUDE`, `LOCFILES` or `LOCMETH` commented out.
  Each parallel NLLoc chunk gets a copy of the skeleton with these appended:

  ```
  LOCCOM {RUN_NAME} {SSST_MODEL_NAME} loc_ssst_corr{iteration}
  LOCFILES tmp/obsfiles_{i}/*.nlloc_obs NLLOC_OBS  {time_root}  {out_root}_{i}/{PROJECT_NAME}  0
  LOCMETH EDT_OT_WT 9999.0 {min_num_phases_loc} -1 -1 {vpvs} -1 -1 1
  LOCHYPOUT SAVE_NLLOC_ALL  NLL_FORMAT_VER_2  {SAVE_NLLOC_OCTREE} {SAVE_FMAMP}
  ```

  (NLL takes the **last** occurrence of a statement, which is why the
  original `LOCHYPOUT` may stay in the file but must not carry SAVE flags —
  see §4.) Each chunk's obs files are copied into `tmp/obsfiles_{i}/`; NLLoc
  console output goes to a per-chunk log `tmp/<control>.log`.
- **Loc2ssst step** — a shared per-iteration control file =
  `SSST_CONTROL_FILE` + appended:

  ```
  LSPARAMS {char_dist} 0.0000001
  LSMODE ANGLES_NO
  LSOUT {ls_out_root}
  LSLOCFILES {out_root}.*.*.grid0.loc.hyp
  LOCFILES {loc_obs} NLLOC_OBS  {time_root}  {out_root}  0
  LOCMETH EDT_OT_WT 9999.0 {min_num_phases_loc} -1 -1 {vpvs} -1 -1 1
  ```

  Each parallel instance gets a copy with one extra `LSSTATIONS A=B=C=...`
  line. Splitting by station is **pure parallelization**: each station's
  correction depends only on that station's residuals, so results are
  identical to a single-instance run.
- **Merge** — per-chunk NLLoc output dirs `{out_root}_{i}` are `copytree`'d
  into `{out_root}` (per-event files have unique names), then the three
  summary files are rebuilt by explicit concatenation:
  `.sum.grid0.loc.hyp` and `.stations` (plain concat) and `.csv` (header
  kept from the first chunk only). A
  `WARNING.concatenated_output_of_multiple_NLLoc_runs.WARNING` marker is
  dropped in the dir. At the end of the run the chunk dirs are deleted with
  the glob `loc_ssst_corr*/{catalog}_[0-9]*`.
- **Single sources of truth**
  - The NLLoc min-phases threshold is **read from the `LSPHSTAT` NRdgsMin
    value (2nd number) of `SSST_CONTROL_FILE`** (`_read_min_num_phases`), so
    NLLoc never locates events Loc2ssst would reject.
  - The Loc2ssst station list is **read from `STATIONS_FILE`** (GTSRCE
    format, 2nd column = station code; `_read_station_codes` skips comments
    and duplicates) and split round-robin: `codes[i::NUM_CORES]`.
- **Bookkeeping** — the script archives itself + both control files +
  `run_ssst_relocations.log` into `OUT/RUN_NAME/`, and appends the final
  summary-hyp path to `ssst.list`.

### Prerequisites

- `NLLoc` and `Loc2ssst` binaries on `PATH`.
- Travel-time grids must already exist at `INIT_TIME_ROOT` (the script never
  runs Vel2Grid/Grid2Time). **With `VPVS = -9.99` this includes S grids** —
  see §4, "P and S grids".
- Subprocesses run with `cwd = <module dir>`, so relative paths inside the
  control files resolve against the module directory.
- Avoid symlinked directories in the `OUT` path itself (shell resolution of
  the linked travel-time files can break).

### Per-zone adaptation table

| `run_ssst_VF.py` variable | Meaning | Project per-zone value |
|---|---|---|
| `RUN_NAME` | run identifier (output subdir + archive) | one per SSST campaign, e.g. `ssst_run1` |
| `PROJECT_NAME` | basename of NLLoc output files | see naming note below |
| `OUT` | output root | project choice, e.g. `run/ssst_loc/` (NLL working folders live under `run/` since the 2026-07 restructure) |
| `CATALOG` | obs set used to derive corrections | `GLOBAL_<N>` |
| `CATALOG_FINAL` | obs set for the final relocation | `GLOBAL_<N>` (same, unless corrections are derived from a subset) |
| `CONTROL_FILE` | NLLoc control file | `run/nll/NLL_<N>.in` (generated per zone, §4; the generated `.in` files live in `run/nll/`) |
| `SSST_CONTROL_FILE` | Loc2ssst control file | `run/nll/SSST_<N>.in` (generated per zone, §5) |
| `MODEL` | basename of the velocity/time grids | `Pyrenees_<N>` |
| `VPVS` / `VPVS_ITER` | LOCMETH VpVsRatio (iter 0 / later) | `-9.99` (use real S grids) — see §4 |
| `CHAR_DISTS` | smoothing schedule (km) | validated: `[9999, 50, 15, 5, 1]` |
| `LOC_OBS` | glob of per-event obs files | `run/nlloc_obs/GLOBAL_<N>/*.nlloc_obs` (output of §3) |
| `SSST_MODEL_NAME` | output subdir name | see naming note below |
| `INIT_TIME_ROOT` | initial time-grid file root | `run/nll_time/Pyrenees_<N>/Pyrenees_<N>` (**only if grids are compatible**, see §4) |
| `SAVE_NLLOC_OCTREE` / `SAVE_FMAMP` | extra saves before final iter | keep `''` (final iteration forces them on) |
| `NUM_CORES` | parallel NLLoc / Loc2ssst instances | 10 on the current machine — consider splitting, §8 |
| `STATIONS_FILE` | GTSRCE file for the station list | `stations/GTSRCE_<N>.txt` (already produced by `generate_regional_runfiles._gen_gtsrce`) |
| `LOG_FILE` | run journal | must become per-zone, §8 |

**Naming note** — in CODES_SSST, `SSST_MODEL_NAME = f'{PROJECT_NAME}_{MODEL}_SSST'`
produced `run_6_run_6_SSST` because both variables held `run_6`. In the
module, derive everything from a single zone identifier (e.g.
`PROJECT_NAME = MODEL = 'Pyrenees_<N>'`, `SSST_MODEL_NAME = 'Pyrenees_<N>_SSST'`)
so directory names stay readable.

### Required refactor

`run_ssst_VF.py` configures everything through module-level constants. For a
per-zone loop, convert them to a params dataclass + function arguments,
following the existing `GenRunParams` pattern in
[`NLL_run/generate_regional_runfiles.py`](NLL_run/generate_regional_runfiles.py)
(e.g. `SSSTRunParams` consumed by `run_ssst(params)`). Keep the PATTERNS.md
structure the script already has: module docstring with Usage, stdlib-only
imports, `_MODULE_DIR` anchor, section separators, `_`-prefixed helpers,
Public API returning a summary dict, thin argparse CLI.

---

## 3. Source script: `reformate_box.py`

### How it works

Reads a multi-event `.obs` bulletin and writes **one `.nlloc_obs` file per
event** into an output directory, filtered by a lat/lon bounding box and a
minimum phase count. Key behaviors:

- **Event identity comes from the `PUBLIC_ID` line** (the line immediately
  after the `# ` event header in project `.obs` files):
  `current_event = line.split()[1]`. It becomes both the output filename
  `<publicId>.nlloc_obs` and the `PUBLIC_ID <publicId>` header line of the
  file. **This is what lets relocated events be rematched to
  `obs/GLOBAL.obs` via `publicId`** — the exact mechanism `run_NLL.py`
  already uses (`match_pre_post_relocation`), and NLLoc propagates it into
  its `.hyp`/`.csv` output. The date-time string built from the `# ` header
  is only a fallback when no `PUBLIC_ID` line exists.
- **Per-event file layout**: 3 header lines
  (`PUBLIC_ID ...`, a placeholder `QUALITY ...` line, the `PHASE` column
  header), then the pick lines.
- **Pick lines get a `PriorWt` of `1.00e+00` appended** at the end of the
  fields, **before** any trailing `#` comment
  (`fields.rstrip() + "  1.00e+00 #" + comment`).
- Lines starting with `###` are ignored; blank lines separate events.

### Adaptation

- Wrap as a function with parameters: input bulletin (`obs/GLOBAL_<N>.obs`),
  output dir (`run/nlloc_obs/GLOBAL_<N>/`), bbox (`_ZONES[N]` from `run_NLL.py`),
  `min_phases`. Since the per-zone `.obs` is already box-filtered by
  `_gen_child_obs`, the bbox filter becomes a pass-through safety check.
- The script currently duplicates the "write event if it passes the filters"
  block (once in the loop, once after it for the last event) — factor it
  into a helper when porting.
- Follow PATTERNS.md (docstring, `_MODULE_DIR`, Public API + CLI) like the
  other `NLL_run/` modules.

---

## 4. `NLL_XXX.in` — required content

This control file serves **double duty**:

- **(a) grid building** — read by Vel2Grid/Grid2Time (statements `VGOUT`,
  `VGGRID`, `LAYER`, `GTFILES`, `GTMODE`, `INCLUDE`);
- **(b) NLLoc skeleton** — `run_ssst_VF.py` comments out `INCLUDE`,
  `LOCFILES`, `LOCMETH` and appends fresh ones per chunk (§2). Everything
  else passes through to every NLLoc instance unchanged.

Statement-by-statement (values = validated `NLL_run_6.in`, per-zone values
follow `generate_regional_runfiles.generate_run`):

| Statement | Example (zone 6) | Notes |
|---|---|---|
| `CONTROL` | `CONTROL 1 54321` | message level 1, fixed RNG seed |
| `TRANS` | `TRANS LAMBERT WGS-84 41.85 1.03 42 44 0.0` | per-zone SW corner from `_compute_grid_corners` (bbox + 100 km margin). **Must be identical in `SSST_XXX.in`** and identical to whatever built any reused time grids |
| `VGOUT` | `VGOUT out/run_6/model/run_6` | velocity-grid file root → project: `run/nll_model/Pyrenees_<N>/Pyrenees_<N>` |
| `VGTYPE` | `VGTYPE P` | **also add `VGTYPE S`** if building S grids (see below) |
| `VGGRID` | `VGGRID 2 9000 800 0.0 0.0 -3 0.05 0.05 0.05 SLOW_LEN` | 2-D (nx=2) grid, 0.05 km spacing, z from −3 km; ny/nz per zone as in `GenRunParams.VGGRID` |
| `LAYER` ×5 | same 5-layer 1-D model as `generate_regional_runfiles` | |
| `GTFILES` | `GTFILES out/run_6/model/run_6 out/run_6/time/run_6 P 0` | project: `GTFILES run/nll_model/Pyrenees_<N>/Pyrenees_<N> run/nll_time/Pyrenees_<N>/Pyrenees_<N> P` — **a second Grid2Time pass with `S` is needed for S grids** |
| `GTMODE` | `GTMODE GRID2D ANGLES_NO` | 2-D grids expanded radially per station |
| `INCLUDE` | `INCLUDE GTSRCE_6.txt` | project: `stations/GTSRCE_<N>.txt`. Needed by **Grid2Time only** — the SSST skeleton comments it out; NLLoc reads station coordinates from the time-grid headers |
| `LOCFILES` | any placeholder | neutralized by the skeleton, re-appended per chunk |
| `LOCHYPOUT` | `LOCHYPOUT SAVE_NLLOC_ALL NLL_FORMAT_VER_2 SAVE_HYPO71_SUM` | **must NOT contain `SAVE_NLLOC_OCTREE` or `SAVE_FMAMP`** — the script appends the authoritative `LOCHYPOUT` and adds those flags itself on the final iteration only |
| `LOCGRID` | `LOCGRID 6025 6224 761 0.0 0.0 -3 0.05 0.05 0.05 PROB_DENSITY SAVE` | see grid-containment warning below |
| `LOCSEARCH` | `LOCSEARCH OCT 50 50 5 0.001 50000 500 1 0` | oct-tree search |
| `LOCMETH` | any placeholder | neutralized by the skeleton; the appended version is `EDT_OT_WT 9999.0 <NRdgsMin from LSPHSTAT> -1 -1 <vpvs> -1 -1 1` |
| `GT_PLFD` | `GT_PLFD 1.0e-7 0` | Podvin-Lecomte finite-difference param |
| `LOCGAU` / `LOCGAU2` | `LOCGAU 0.05 0.0` / `LOCGAU2 0.01 0.01 2.0` | travel-time error model |
| `LOCPHASEID` | `LOCPHASEID P P p G PN PG` + `LOCPHASEID S S s G SN SG` | phase mapping (both P and S) |
| `LOCQUAL2ERR` | `LOCQUAL2ERR 0.05 0.15 0.05 0.15 99999.9` | quality → uncertainty (s) |
| `LOCPHSTAT` | `LOCPHSTAT 9999.0 -1 9999.0 1.0 1.0 9999.9 -9999.9 9999.9` | residual statistics selection |

### Grid containment (validated failure)

The search grid must fit **strictly inside** the travel-time grid, including
depth. With the time grid `nz = 800` (z: −3 → 36.95 km at 0.05 km), a
`LOCGRID`/`LSGRID` reaching 37.0 km triggers an interpolation artifact at the
bottom layer (~192 000 `DEBUG ERROR` messages per station/phase in testing —
cosmetic but massive). Use `LOCGRID nz = 761` (→ 35.0 km max depth) — since
the 2026-07 restructure this is already the project default in
`generate_regional_runfiles._compute_grid_corners` — and keep the
`LSGRID`/`LSOUTGRID` z-extent ≤ 36.0 km.

### P **and** S grids

`run_ssst_VF.py` was validated with `VPVS = -9.99`, which tells NLLoc and
Loc2ssst to use **real S travel-time grids** (`<model>.S.<sta>.time.*`) —
required for SSST to compute independent S station terms. The grids currently
built by `run_NLL.py` (`GTFILES ... P`, `LOCMETH ... 1.72 ...`) are
**P-only**. The module must therefore build S grids too (add `VGTYPE S` and a
Grid2Time pass with `GTFILES ... S`), or the existing `run/nll_time/Pyrenees_<N>`
grids cannot be reused as `INIT_TIME_ROOT` with `-9.99`. Falling back to a
fixed `VpVs = 1.72` would locate, but S corrections could not be gridded
independently — decide explicitly.

---

## 5. `SSST_XXX.in` — required content

Base file read by every Loc2ssst instance, **before** the script appends the
per-iteration block (§2). Values = validated `SSST_run_6.in`.

**Must contain:**

| Statement | Example (zone 6) | Notes |
|---|---|---|
| `CONTROL` | `CONTROL 1 54321` | |
| `TRANS` | `TRANS LAMBERT WGS-84 41.85 1.03 42 44 0.0` | **identical to `NLL_XXX.in`** |
| `LSGRID` | `LSGRID 305 315 40 0.0 0.0 -3 1.0 1.0 1.0 SSST_TIMECORR FLOAT` | correction-grid geometry — **coarse!** see memory box below |
| `LSOUTGRID` | `LSOUTGRID 305 315 40 0.0 0.0 -3 1.0 1.0 1.0 TIME FLOAT` | corrected-time output grid, same geometry |
| `LSMODE` | `LSMODE ANGLES_NO` | (the script also appends one; harmless duplicate) |
| `LSPHSTAT` | `LSPHSTAT 0.15 6 200.0 0.3 0.5 10.0` | fields: `RMSMax NRdgsMin GapMax PResidualMax SResidualMax EllLen3Max`. **NRdgsMin (here 6) is read by the script and reused as the NLLoc min-phases** — the single place this threshold is set |
| `LOCPHASEID` | `LOCPHASEID P P Pg Pn` + `LOCPHASEID S S Sg Sn` | phase mapping for residual collection |

**Must NOT contain** (appended at runtime, per iteration / per instance):
`LSPARAMS`, `LSOUT`, `LSLOCFILES`, `LOCFILES`, `LOCMETH`, `LSSTATIONS`.
A commented `#LSPARAMS ...` placeholder is fine.

### Memory sizing (validated failure)

Loc2ssst allocates the `LSGRID` volume **plus a duplicate 3-D buffer**, per
instance: memory ≈ `nx·ny·nz·4 bytes × 2 × NUM_CORES` concurrent instances.
Copying the fine `LOCGRID` dimensions (6025×6224×800) into `LSGRID` requested
~120 GB **per buffer** and killed the run on a 52 GB machine. The validated
coarse grid (305×315×40 at 1.0 km ≈ 15 MB/buffer) is smooth enough — the
corrections are smoothed by `CHAR_DIST` anyway, so ~1 km spacing loses
nothing. This memory footprint (× stations × phases on disk, × instances in
RAM) is **the reason zones must run sequentially**.

---

## 6. Output tree & downstream hooks

Per zone, one run produces (`K = len(CHAR_DISTS)`, catalog = `GLOBAL_<N>`,
files named `{PROJECT_NAME}.*`):

```
OUT/RUN_NAME/
├── run_ssst_VF.py, NLL_<N>.in, SSST_<N>.in,          # archived copies
│   run_ssst_relocations.log
└── <SSST_MODEL_NAME>/
    ├── loc_ssst_corr0/<catalog>/                     # iteration-0 locations
    │   ├── <proj>.<date>.<time>.grid0.loc.hyp        # one per event
    │   ├── <proj>.sum.grid0.loc.hyp                  # merged summary (concat)
    │   ├── <proj>.sum.grid0.loc.csv                  # merged CSV (1 header)
    │   ├── <proj>.sum.grid0.loc.stations
    │   └── WARNING.concatenated_output_of_multiple_NLLoc_runs.WARNING
    ├── ssst_corr0/<catalog>/                         # iteration-0 corrected grids
    │   ├── <model>.{P,S}.<sta>.time.{buf,hdr}        # real files or symlinks
    │   └── <model>.{P,S}.<sta>.ssst_corr.*           # correction grids
    ├── loc_ssst_corr1/ ... ssst_corr{K-1}/           # same, per iteration
    └── loc_ssst_corrK/<catalog>/                     # final relocation, adds:
        ├── <proj>.<date>.<time>.grid0.loc.octree     # one per event
        └── <proj>.sum.grid0.loc.fmamp
```

Plus, next to the module: `ssst.list` (appended path of the final
`.sum.grid0.loc.hyp`) and `run_ssst_relocations.log`.

**Downstream hook** — the final iteration's `*.sum.grid0.loc.csv` has the
same format as the current per-zone
`run/nll_loc/GLOBAL_<N>/GLOBAL_<N>.obs.sum.grid0.loc.csv`, including `publicId`
and `pdfVolume`. It plugs directly into the existing chain of `run_NLL.py`:
`merge_bulletins` (6 zone CSVs → `RESULT/NLL_result.csv`, duplicates resolved by
lowest `pdfVolume`) → `save_bulletin` (publicId rematch → `obs/NLL_result.obs`).

**Disk cleanup after validation** — the intermediate iterations are
deletable: `ssst_corr{0..K-2}` (only the last grids matter for reruns) and
`loc_ssst_corr{0..K-1}` (only the final locations matter). The log ends with
ready-to-paste `rm -r` commands (written for 3 iterations — adjust indices).

---

## 7. Pitfalls checklist (each one cost real debugging time)

- **Empty obs glob = silent no-op**: if `LOC_OBS` matches nothing, NLLoc
  chunks "succeed" on zero events and every Loc2ssst fails with "no matching
  .hyp files". Add a fail-fast (`raise FileNotFoundError`) on an empty obs
  glob **and** on an empty `{INIT_TIME_ROOT}*.time.*` glob.
- **LSGRID memory**: never copy LOCGRID dimensions into LSGRID (§5).
- **Grid z-containment**: LOCGRID and LSGRID/LSOUTGRID must stay inside the
  time grid's depth extent (§4).
- **Cleanup glob**: chunk dirs must be matched with `{catalog}_[0-9]*` — a
  bare `*_?` glob also matches the merged `<catalog>` dir when the catalog
  name itself ends in `_<digit>` (e.g. `run_6`), deleting the results.
- **CSV merge**: `copytree` alone leaves only the last chunk's summary CSV;
  the explicit concatenation (header from first chunk only) is mandatory.
- **Naming**: derive `SSST_MODEL_NAME` from one identifier (§2 naming note).
- **TRANS consistency**: `NLL_XXX.in`, `SSST_XXX.in`, and any reused time
  grids must share the same TRANS; reusing `run/nll_time/Pyrenees_<N>` grids
  also requires matching grid dims — and they are P-only today (§4).
- **Min-phases desync**: never hardcode the NLLoc min-phases; read it from
  `LSPHSTAT` NRdgsMin (already implemented, keep it).

---

## 8. Recommended improvements when porting

Documented here as porting requirements — the CODES_SSST originals are left
as validated:

- **Fail-fast on subprocess failure** *(required)*: raise/abort the iteration
  if any NLLoc chunk or Loc2ssst instance exits non-zero. Today a failure
  only prints `status=1`; the merge then silently produces a partial catalog
  that feeds the next iteration's corrections.
- **Round-robin obs chunking**: replace
  `chunk_size = 1 + count // NUM_CORES` contiguous slicing (can yield fewer
  chunks than cores, plus a tiny last chunk) with
  `obs_files[i::NUM_CORES]` — the station split already does exactly this.
- **Separate `NLLOC_CORES` / `LOC2SSST_CORES`**: NLLoc is CPU-bound and light
  on memory; Loc2ssst holds ~2 LSGRID buffers per instance. Decoupling the
  two knobs lets RAM cap only the Loc2ssst side.
- **Per-iteration chunk cleanup**: delete each iteration's `{catalog}_<i>`
  dirs right after that iteration's merge (or move files instead of
  `copytree`) — currently every iteration's duplicates stay on disk until the
  end of the whole run. Same philosophy as the per-zone `.hdr` cleanup in
  `run_NLL.py`.
- **Per-zone run artifacts**: `run_ssst_relocations.log`, `tmp/`, and
  `ssst.list` are fixed module-level paths — a zone loop overwrites the log
  and shares `tmp/`. Make them per-zone via the `SSSTRunParams` refactor.
- *Optional*: dynamic work queue for NLLoc chunks (more, smaller chunks
  dispatched as workers free up) to reduce the straggler effect of static
  chunking — the slowest chunk currently gates every iteration.
