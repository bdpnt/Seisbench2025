"""
merge_pyrenees_picks.py
============================
Merge RaspberryShake/PhaseNet pick files into two consolidated text files.

Reads all .txt pick files from picks_station_pyrenees/ and
picks_station_pyrenees2/ and concatenates them into two merged output files,
one per source directory. No format conversion is done here; use
convert_picks.py with --format TEMP_RSB to convert the merged files to
GLOBAL.obs format.

Usage
-----
    python temp_picks/merge_pyrenees_picks.py

    # Override defaults
    python temp_picks/merge_pyrenees_picks.py --input-dir temp_picks/all_picks/PICKS_PHASENET_TOUS --output-dir temp_picks/all_picks
"""

import argparse
import logging
import os
from datetime import datetime

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_DEFAULT_INPUT_DIR  = os.path.join(_MODULE_DIR, 'all_picks', 'PICKS_PHASENET_TOUS')
_DEFAULT_OUTPUT_DIR = os.path.join(_MODULE_DIR, 'pick_files')
_DEFAULT_LOG_DIR    = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('merge_pyrenees_picks')

_SOURCE_DIRS = [
    ('picks_station_pyrenees',  'merged_pyrenees.txt'),
    ('picks_station_pyrenees2', 'merged_pyrenees2.txt'),
]

# Minimum PhaseNet pick probability ('prob=' field) required to keep a line
DEFAULT_MIN_PHASE_SCORE = 0.5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    basename  = os.path.splitext(os.path.basename(__file__))[0]
    log_path  = os.path.join(log_dir, f"{basename}_{timestamp}.log")

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)

    return log_path


def _merge_directory(src_dir, output_path, min_phase_score):
    """
    Concatenate all .txt files in src_dir into output_path, dropping lines
    whose 'prob=' value is below min_phase_score.

    Returns (n_files, n_lines, n_dropped_low_score).
    """
    txt_files = sorted(
        f for f in os.listdir(src_dir) if f.endswith('.txt')
    )
    n_files             = len(txt_files)
    n_lines             = 0
    n_dropped_low_score = 0

    with open(output_path, 'w', encoding='utf-8') as out:
        for fname in txt_files:
            fpath = os.path.join(src_dir, fname)
            warned = False
            with open(fpath, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.split()
                    try:
                        prob = float(parts[-1].split('=', 1)[1])
                    except (IndexError, ValueError):
                        if not warned:
                            logger.warning(f"Cannot parse prob= in {fname}, keeping line(s) as-is.")
                            warned = True
                        out.write(line)
                        n_lines += 1
                        continue

                    if prob < min_phase_score:
                        n_dropped_low_score += 1
                        continue

                    out.write(line)
                    n_lines += 1

    return n_files, n_lines, n_dropped_low_score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_all(input_dir=None, output_dir=None, log_dir=None, min_phase_score=None):
    """
    Merge all RaspberryShake/PhaseNet pick files into two consolidated files.

    Processes picks_station_pyrenees/ and picks_station_pyrenees2/ separately,
    writing one merged .txt file per source directory, and drops lines whose
    'prob=' value is below min_phase_score.

    Parameters
    ----------
    input_dir : str, optional
        Base directory containing the two source subdirectories.
        Defaults to temp_picks/all_picks/PICKS_PHASENET_TOUS/.
    output_dir : str, optional
        Directory where merged .txt files are written.
        Defaults to temp_picks/pick_files/.
    log_dir : str, optional
        Directory for the log file. Defaults to temp_picks/console_output/.
    min_phase_score : float, optional
        Minimum 'prob=' value required to keep a pick line.
        Defaults to DEFAULT_MIN_PHASE_SCORE (0.5).

    Returns
    -------
    dict
        Summary with keys: 'log', 'outputs' (list of output paths),
        and per-directory counts under 'stats' (list of dicts with
        'subdir', 'n_files', 'n_lines', 'n_dropped_low_score', 'output').
    """
    input_dir       = input_dir       or _DEFAULT_INPUT_DIR
    output_dir      = output_dir      or _DEFAULT_OUTPUT_DIR
    log_dir         = log_dir         or _DEFAULT_LOG_DIR
    min_phase_score = min_phase_score if min_phase_score is not None else DEFAULT_MIN_PHASE_SCORE

    log_path = _setup_logger(log_dir)
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Input base : {input_dir}")
    logger.info(f"Output dir : {output_dir}")
    logger.info(f"Min phase score : {min_phase_score}")

    outputs = []
    stats   = []

    for subdir_name, output_name in _SOURCE_DIRS:
        src_dir     = os.path.join(input_dir, subdir_name)
        output_path = os.path.join(output_dir, output_name)

        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory not found, skipping: {src_dir}")
            continue

        n_files, n_lines, n_dropped_low_score = _merge_directory(src_dir, output_path, min_phase_score)
        logger.info(
            f"{subdir_name}: {n_files} files, {n_lines} lines, "
            f"{n_dropped_low_score} dropped (low phase_score) → {output_path}"
        )

        outputs.append(output_path)
        stats.append({
            'subdir':              subdir_name,
            'n_files':             n_files,
            'n_lines':             n_lines,
            'n_dropped_low_score': n_dropped_low_score,
            'output':              output_path,
        })

    logger.info(f"Log: {log_path}")

    return {'log': log_path, 'outputs': outputs, 'stats': stats}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Merge RaspberryShake/PhaseNet .txt pick files into two consolidated files.'
    )
    parser.add_argument(
        '--input-dir', default=None,
        help='Base directory containing picks_station_pyrenees/ and picks_station_pyrenees2/.'
    )
    parser.add_argument(
        '--output-dir', default=None,
        help='Directory where merged .txt files are written.'
    )
    parser.add_argument(
        '--log-dir', default=None,
        help='Directory for log files.'
    )
    parser.add_argument(
        '--min-phase-score', type=float, default=None, metavar='SCORE',
        help=f'Minimum prob= value required to keep a pick (default: {DEFAULT_MIN_PHASE_SCORE}).'
    )
    args = parser.parse_args()
    merge_all(args.input_dir, args.output_dir, args.log_dir, min_phase_score=args.min_phase_score)


if __name__ == '__main__':
    main()
