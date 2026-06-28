# Weekly Code Audit — 2026-06-28

## Scope

Python files touched on the `claude` branch in the last 7 days. The changes fall into two groups:

1. **New feature** — automate NLL runs from Python (commit `2055ca9`): new `NLL_run/run_zone.py`, plus integration in `prepare_nll_inputs.py` and `generate_nll_corrections.py`.
2. **Directory-rename refactors** (commits `3365ac3`, `8d50afd`, `322b8d2`): `MAGMODELS/`→`mag_model/`, `FAILLES/`→`failles/`, `ORGCATALOGS/`→`org_catalogs/`. These only change path string literals.

## Files reviewed
- NLL_run/run_zone.py
- prepare_nll_inputs.py
- generate_nll_corrections.py
- build_global_bulletin.py
- global_obs/apply_magnitude_models.py
- global_obs/generate_magnitude_models.py
- fetch_all_bulletins.py
- fetch_obs/ICGC.py
- fetch_obs/IGN.py
- fetch_obs/LDG.py
- fetch_obs/OMP.py
- fetch_obs/RESIF.py
- complem_figures/cross_section.py
- zone_Arette/plot_cross_section.py

## Findings

### NLL_run/run_zone.py
- **[Medium]** Line 28: The NLL binary directory is hardcoded to a single user's machine —
  `_NLL_BIN = "/Users/bdupont/Desktop/Codes/NonLinLoc/src/bin"`. Because `prepare_nll_inputs.py`
  and `generate_nll_corrections.py` now call `run_zone` automatically, the entire automated
  relocation pipeline is wired to one absolute path and will fail on any other machine (or in a
  CI/clean-clone environment). There is no comment explaining the path and no override mechanism.
  Suggested fix: read the directory from an environment variable with this path as a documented
  fallback, e.g. `_NLL_BIN = os.environ.get("NLL_BIN", "/Users/bdupont/.../src/bin")`, and add a
  short comment.

- **[Medium]** Line 51: `_run` calls `sys.exit(result.returncode)` when an NLL program returns
  non-zero. `run_zone` is documented as a "Public API" and is imported and called from inside the
  6-zone loops of both orchestrators. Aborting via `sys.exit()` from within a reusable library
  function gives the caller no chance to handle the failure, log per-zone context, clean up, or
  continue with remaining zones — one zone's failure silently terminates the whole batch. Suggested
  fix: raise an exception (e.g. `subprocess.run(cmd, check=True)`, or a `RuntimeError`) from the
  library function and let the CLI layer (`_main`) translate it to a process exit code.

- **[Low]** Lines 46–52: If `_NLL_BIN` is wrong or the binaries are absent, `subprocess.run` raises
  an uncaught `FileNotFoundError` and the user sees a raw traceback rather than the clear
  `"<label> failed"` message the function otherwise produces. Consider a pre-flight
  `os.path.isfile(_exe(name))` check (or catching `FileNotFoundError`) so a missing/misconfigured
  binary path reports a clear, actionable error. Related to the hardcoded path above.

### prepare_nll_inputs.py
- No issues. `run_zone` is imported and used; the replaced `print()` separator was cosmetic. The
  failure behavior of the loop is governed by `run_zone` (see the `sys.exit` finding above).

### generate_nll_corrections.py
- No issues. `run_zone(..., corrections_pass=True)` is correctly placed after
  `append_station_delays` inside the loop, and `export_locdelay_info` correctly runs once after the
  loop. (`key` is an `int` here vs. a `str` in `prepare_nll_inputs.py`, but both produce identical
  filenames via f-strings — not a defect.)

### Directory-rename refactors (the remaining 11 files)
- No issues. Verified that every quoted path string literal referencing `MAGMODELS`, `FAILLES`, or
  `ORGCATALOGS` was updated to its lowercase replacement, with no stale string-literal references
  remaining anywhere in the codebase. The Python variable identifiers `_MAGMODELS`, etc. were left
  unchanged, which is cosmetic only and does not affect behavior.

## Summary
14 files reviewed, 3 issues found (2 Medium, 1 Low) — all in the new `NLL_run/run_zone.py`. The
directory-rename refactors are clean and complete.
