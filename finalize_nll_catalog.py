"""
finalize_nll_catalog.py
============================
Finalize the NLL-relocated catalog and produce obs/FINAL.obs.

Steps:
  1. Cleans second-pass NLL output for all 6 zones.
  2. Merges the 6 regional results into RESULT/FINAL.txt.
  3. Rematches relocated events back to obs/GLOBAL.obs to recover metadata
     (e.g. magnitude) absent from NLL output.
  4. Saves matched events to obs/FINAL.obs.

Usage
-----
    python finalize_nll_catalog.py
"""

import os

from NLL_run.match_pre_post_relocation import MatchCatalogsParams
from NLL_run.merge_regional_results    import merge_bulletins
from NLL_run.parse_nll_output          import CleanPostRunParams
import NLL_run

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOC    = os.path.join(_PROJECT_ROOT, 'loc')
_RESULT = os.path.join(_PROJECT_ROOT, 'RESULT')
_OBS    = os.path.join(_PROJECT_ROOT, 'obs')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline():
    """Clean second-pass NLL output, merge results, and produce obs/FINAL.obs."""
    # Clean the files post-run
    for key in range(1, 7):
        params_clean = CleanPostRunParams(
            folderLoc    = os.path.join(_LOC,    f'GLOBAL_{key}'),
            obsFile      = f'GLOBAL_{key}.obs',
            fileBulletin = os.path.join(_RESULT, f'GLOBAL_{key}_PR.txt'),
        )

        NLL_run.parse_nll_output.write_events(params_clean)

    # Generate the FINAL.txt file
    result_files = [os.path.join(_RESULT, f'GLOBAL_{key}_PR.txt') for key in range(1, 7)]

    merge_bulletins(result_files, os.path.join(_RESULT, 'FINAL.txt'))

    # Match events pre/post NLL
    params_final = MatchCatalogsParams(
        file_obs   = os.path.join(_OBS, 'GLOBAL.obs'),
        file_final = os.path.join(_RESULT, 'FINAL.txt'),
        save_file  = os.path.join(_OBS, 'FINAL.obs'),
    )

    NLL_run.match_pre_post_relocation.save_bulletin(params_final)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    run_pipeline()


if __name__ == '__main__':
    main()
