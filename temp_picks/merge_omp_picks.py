"""
merge_omp_picks.py
============================
Merge OMP/PhaseNet pick CSVs into a single consolidated file.

Reads all PICKS_*.csv files from all yearly subdirectories under picks_OMP/,
skipping stations listed in STATIONS_TO_DROP, and concatenates them into one
merged CSV with a single header row. No format conversion is done here; use
convert_picks.py with --format TEMP_OMP to convert to GLOBAL.obs format.

Usage
-----
    python temp_picks/merge_omp_picks.py

    # Override defaults
    python temp_picks/merge_omp_picks.py --input-dir temp_picks/all_picks/PICKS_PHASENET_TOUS/picks_OMP --output temp_picks/pick_files/merged_omp.csv
"""

import argparse
import logging
import os
from datetime import datetime

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_DEFAULT_INPUT_DIR  = os.path.join(_MODULE_DIR, 'all_picks', 'PICKS_PHASENET_TOUS', 'picks_OMP')
_DEFAULT_OUTPUT     = os.path.join(_MODULE_DIR, 'pick_files', 'merged_omp.csv')
_DEFAULT_LOG_DIR    = os.path.join(_MODULE_DIR, 'console_output')

# Add station codes here to exclude them from the merged output
STATIONS_TO_DROP = {'SMC'}

logger = logging.getLogger('merge_omp_picks')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"merge_omp_{timestamp}.log")

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)

    return log_path


def _station_code_from_filename(filename):
    """Extract station code from PICKS_{CODE}.csv → '{CODE}'."""
    basename = os.path.basename(filename)
    return basename.removeprefix('PICKS_').removesuffix('.csv')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_omp(input_dir=None, output_path=None, log_dir=None):
    """
    Merge all OMP PhaseNet pick CSVs into a single file.

    Iterates all yearly subdirectories in input_dir, collects every
    PICKS_*.csv file, skips stations in STATIONS_TO_DROP, and writes
    one merged CSV with a single header row.

    Parameters
    ----------
    input_dir : str, optional
        Directory containing yearly subdirs (PICKS_PHASENET_*).
        Defaults to temp_picks/all_picks/PICKS_PHASENET_TOUS/picks_OMP/.
    output_path : str, optional
        Destination CSV file. Defaults to temp_picks/pick_files/merged_omp.csv.
    log_dir : str, optional
        Directory for the log file. Defaults to temp_picks/console_output/.

    Returns
    -------
    dict
        Summary with keys: 'output', 'log', 'n_files', 'n_rows', 'n_dropped_files'.
    """
    input_dir   = input_dir   or _DEFAULT_INPUT_DIR
    output_path = output_path or _DEFAULT_OUTPUT
    log_dir     = log_dir     or _DEFAULT_LOG_DIR

    log_path = _setup_logger(log_dir)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info(f"Input dir  : {input_dir}")
    logger.info(f"Output     : {output_path}")
    if STATIONS_TO_DROP:
        logger.info(f"Dropping stations: {', '.join(sorted(STATIONS_TO_DROP))}")

    yearly_dirs = sorted(
        d for d in os.listdir(input_dir)
        if os.path.isdir(os.path.join(input_dir, d))
    )

    header_written  = False
    n_files         = 0
    n_rows          = 0
    n_dropped_files = 0

    with open(output_path, 'w', encoding='utf-8') as out:
        for year_dir in yearly_dirs:
            year_path = os.path.join(input_dir, year_dir)
            csv_files = sorted(
                f for f in os.listdir(year_path) if f.endswith('.csv')
            )
            for fname in csv_files:
                code = _station_code_from_filename(fname)
                if code in STATIONS_TO_DROP:
                    n_dropped_files += 1
                    continue

                fpath = os.path.join(year_path, fname)
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                if not lines:
                    continue

                if not header_written:
                    out.write(lines[0])
                    header_written = True

                data_lines = lines[1:]
                for line in data_lines:
                    out.write(line)
                    n_rows += 1

                n_files += 1

    logger.info(f"Files merged : {n_files}")
    logger.info(f"Rows written : {n_rows}")
    logger.info(f"Files dropped (stations in STATIONS_TO_DROP): {n_dropped_files}")
    logger.info(f"Log: {log_path}")

    return {
        'output':          output_path,
        'log':             log_path,
        'n_files':         n_files,
        'n_rows':          n_rows,
        'n_dropped_files': n_dropped_files,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Merge OMP PhaseNet pick CSVs into a single consolidated file.'
    )
    parser.add_argument(
        '--input-dir', default=None,
        help='Directory containing yearly PICKS_PHASENET_* subdirectories.'
    )
    parser.add_argument(
        '--output', default=None,
        help='Output CSV file path.'
    )
    parser.add_argument(
        '--log-dir', default=None,
        help='Directory for log files.'
    )
    args = parser.parse_args()
    merge_omp(args.input_dir, args.output, args.log_dir)


if __name__ == '__main__':
    main()
