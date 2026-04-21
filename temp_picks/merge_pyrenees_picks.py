"""
merge_pyrenees_picks.py
============================
Merge RaspberryShake/PhaseNet pick files into two consolidated text files.

Reads all .txt pick files from picks_stations_pyrenees/ and
picks_stations_pyrenees2/ and concatenates them into two merged output files,
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
_DEFAULT_OUTPUT_DIR = os.path.join(_MODULE_DIR, 'all_picks')
_DEFAULT_LOG_DIR    = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('merge_pyrenees_picks')

_SOURCE_DIRS = [
    ('picks_stations_pyrenees',  'merged_pyrenees.txt'),
    ('picks_stations_pyrenees2', 'merged_pyrenees2.txt'),
]


def _setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"merge_pyrenees_{timestamp}.log")

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(console)

    return log_path


def merge_directory(src_dir, output_path):
    """
    Concatenate all .txt files in src_dir into output_path.

    Returns (n_files, n_lines).
    """
    txt_files = sorted(
        f for f in os.listdir(src_dir) if f.endswith('.txt')
    )
    n_files = len(txt_files)
    n_lines = 0

    with open(output_path, 'w', encoding='utf-8') as out:
        for fname in txt_files:
            fpath = os.path.join(src_dir, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                for line in f:
                    out.write(line)
                    n_lines += 1

    return n_files, n_lines


def merge_all(input_dir, output_dir, log_dir):
    log_path = _setup_logger(log_dir)
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Input base : {input_dir}")
    logger.info(f"Output dir : {output_dir}")

    for subdir_name, output_name in _SOURCE_DIRS:
        src_dir     = os.path.join(input_dir, subdir_name)
        output_path = os.path.join(output_dir, output_name)

        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory not found, skipping: {src_dir}")
            continue

        n_files, n_lines = merge_directory(src_dir, output_path)
        logger.info(f"{subdir_name}: {n_files} files, {n_lines} lines → {output_path}")

    logger.info(f"Log: {log_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Merge RaspberryShake/PhaseNet .txt pick files into two consolidated files.'
    )
    parser.add_argument(
        '--input-dir', default=_DEFAULT_INPUT_DIR,
        help='Base directory containing picks_stations_pyrenees/ and picks_stations_pyrenees2/.'
    )
    parser.add_argument(
        '--output-dir', default=_DEFAULT_OUTPUT_DIR,
        help='Directory where merged .txt files are written.'
    )
    parser.add_argument(
        '--log-dir', default=_DEFAULT_LOG_DIR,
        help='Directory for log files.'
    )
    args = parser.parse_args()
    merge_all(args.input_dir, args.output_dir, args.log_dir)


if __name__ == '__main__':
    main()
