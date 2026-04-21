"""
add_temp_picks.py
============================
Orchestrate the full temp_picks ingestion pipeline.

Runs each step in order and raises on the first failure to avoid downstream
inconsistencies. Steps whose output already exists are skipped.

Pipeline
--------
1. Build theoretical P/S travel-time tables (skipped if CSV already exists).
2. Plot observed picks vs. theoretical bands for QC (skipped if figure already exists).
3. Merge OMP PhaseNet CSV picks into a single file.
4. Merge RaspberryShake/PhaseNet picks (pyrenees and pyrenees2) into separate files.
5. Convert all pick files to GLOBAL.obs pick line format.
6. Match each converted pick file against obs/FINAL.obs; picks accumulate across runs.

Usage
-----
    python add_temp_picks.py
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_TEMP_PICKS   = os.path.join(_PROJECT_ROOT, 'temp_picks')
_PICK_FILES   = os.path.join(_TEMP_PICKS,   'pick_files')

sys.path.insert(0, _PROJECT_ROOT)

from temp_picks.build_theoretical_tables import save_theoretical_tables
from temp_picks.convert_picks            import convert_file
from temp_picks.match_picks              import match_picks
from temp_picks.merge_omp_picks          import merge_omp
from temp_picks.merge_pyrenees_picks     import merge_all as merge_pyrenees
from temp_picks.plot_travel_times        import plot_travel_times

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TABLES_CSV       = os.path.join(_TEMP_PICKS,   'tables_Pyr.csv')
_TABLES_FIG       = os.path.join(_TEMP_PICKS,   'figures', 'tables_Pyr.png')
_TT_FIGURE        = os.path.join(_TEMP_PICKS,   'figures', 'travel_times_observed.png')
_INVENTORY        = os.path.join(_PROJECT_ROOT, 'stations', 'GLOBAL_inventory.xml')
_BULLETIN         = os.path.join(_PROJECT_ROOT, 'obs',      'FINAL.obs')
_OUTPUT_BULLETIN  = os.path.join(_PROJECT_ROOT, 'obs',      'FINAL_augmented.obs')

_VIEHLA_OBS    = os.path.join(_PICK_FILES, 'viehla_final.obs')
_PYRENEES_TXT  = os.path.join(_PICK_FILES, 'merged_pyrenees.txt')
_PYRENEES2_TXT = os.path.join(_PICK_FILES, 'merged_pyrenees2.txt')
_OMP_CSV       = os.path.join(_PICK_FILES, 'merged_omp.csv')

# Ordered list of (input_file, format) for conversion, then matching
_PICKS_TO_CONVERT = [
    (_VIEHLA_OBS,    'TEMP_OBS'),
    (_PYRENEES_TXT,  'TEMP_RSB'),
    (_PYRENEES2_TXT, 'TEMP_RSB'),
    (_OMP_CSV,       'TEMP_OMP'),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline():
    """
    Run the full temp_picks ingestion pipeline end-to-end.

    Returns
    -------
    dict
        Summary with key 'output' (path to the augmented bulletin).
    """
    # Step 1 — Theoretical travel-time tables
    if os.path.exists(_TABLES_CSV):
        print(f"[1/6] Tables already exist, skipping: {_TABLES_CSV}")
    else:
        print("[1/6] Building theoretical travel-time tables ...")
        save_theoretical_tables(output=_TABLES_CSV, figure_output=_TABLES_FIG)

    # Step 2 — Travel-time QC figure
    if os.path.exists(_TT_FIGURE):
        print(f"[2/6] Travel-time figure already exists, skipping: {_TT_FIGURE}")
    else:
        print("[2/6] Plotting observed travel times ...")
        plot_travel_times(_TABLES_CSV, _BULLETIN, _INVENTORY, _TT_FIGURE)

    # Step 3 — Merge OMP picks
    print("[3/6] Merging OMP picks ...")
    merge_omp()

    # Step 4 — Merge Pyrenees picks
    print("[4/6] Merging Pyrenees picks ...")
    merge_pyrenees()

    # Step 5 — Convert all pick files
    print("[5/6] Converting pick files ...")
    for input_path, fmt in _PICKS_TO_CONVERT:
        base, _ = os.path.splitext(input_path)
        output_path = base + '_converted.obs'
        print(f"  {os.path.basename(input_path)} ({fmt}) → {os.path.basename(output_path)}")
        convert_file(input_path, fmt, output_path=output_path)

    # Step 6 — Match picks against bulletin (chained: each run augments the previous output)
    converted_files = [
        os.path.splitext(p)[0] + '_converted.obs'
        for p, _ in _PICKS_TO_CONVERT
    ]
    print(f"[6/6] Matching {len(converted_files)} pick file(s) against bulletin ...")
    current_bulletin = _BULLETIN
    for pick_file in converted_files:
        print(f"  Matching {os.path.basename(pick_file)} against {os.path.basename(current_bulletin)} ...")
        match_picks(
            pick_file      = pick_file,
            bulletin_file  = current_bulletin,
            inventory_file = _INVENTORY,
            tables_file    = _TABLES_CSV,
            output_file    = _OUTPUT_BULLETIN,
        )
        current_bulletin = _OUTPUT_BULLETIN

    print(f"\nDone. Augmented bulletin: {_OUTPUT_BULLETIN}")
    return {'output': _OUTPUT_BULLETIN}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    run_pipeline()


if __name__ == '__main__':
    main()
