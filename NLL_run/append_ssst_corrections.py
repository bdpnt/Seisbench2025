"""
append_ssst_corrections.py
============================
Generate a second-pass NLL run file by appending SSST static corrections.

Reads the station static corrections (LOCDELAY entries) from the first NLL
run's last.stat_totcorr file, filters them by minimum phase count, and
appends the qualifying corrections to a copy of the original run file.

Usage
-----
    python NLL_run/append_ssst_corrections.py \\
        --loc-folder  loc/GLOBAL_1 \\
        --run-file    run/run_1.in \\
        --run-save    run/run_1_PR.in \\
        --min-phases  100
"""

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT    = os.path.dirname(_MODULE_DIR)
_DEFAULT_LOG_DIR = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('append_ssst_corrections')


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SecondRunParams:
    locFolderName: str
    fileRunName:   str
    fileRunSave:   str
    minPhases:     int = 100


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logger(log_dir, input_path):
    os.makedirs(log_dir, exist_ok=True)
    basename  = os.path.splitext(os.path.basename(input_path))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"{basename}_{timestamp}.log")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)
    return log_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_second_run(parameters, log_dir=None):
    """
    Append qualifying SSST station corrections to the run file and write the
    second-pass run file.

    Corrections are taken from last.stat_totcorr in the loc folder. Only
    entries with PhaseNum >= minPhases and StdDev >= 0 are included.

    Parameters
    ----------
    parameters : SecondRunParams
    log_dir    : str, optional — log directory (default: NLL_run/console_output/)

    Returns
    -------
    dict with keys: output, log, n_corrections
    """
    log_path = _setup_logger(log_dir or _DEFAULT_LOG_DIR, parameters.fileRunSave)
    logger.info(f"Loc folder   : {parameters.locFolderName}")
    logger.info(f"Run file     : {parameters.fileRunName}")
    logger.info(f"Min phases   : {parameters.minPhases}")

    loc_stat_corr = parameters.locFolderName + '/last.stat_totcorr'
    with open(loc_stat_corr, 'r') as f:
        lines = f.readlines()

    statCorr = [line.split()[1:6] for line in lines if line.startswith('LOCDELAY')]
    statCorr_df = pd.DataFrame(
        statCorr,
        columns=['StationCode', 'PhaseType', 'PhaseNum', 'TotCorr', 'StdDev'],
    )
    statCorr_df = statCorr_df.astype({
        'StationCode': 'str',
        'PhaseType':   'str',
        'PhaseNum':    'int32',
        'TotCorr':     'float64',
        'StdDev':      'float64',
    })

    idx = set(
        statCorr_df[
            (statCorr_df.PhaseNum >= parameters.minPhases) &
            (statCorr_df.StdDev   >= 0)
        ].index
    )
    statCorr_list = [lines[i + 3] for i in idx]

    with open(parameters.fileRunName, 'r') as f:
        run_lines = f.readlines()

    run_lines.append('# Stations TotCorr\n')
    run_lines.extend(statCorr_list)

    with open(parameters.fileRunSave, 'w') as f:
        f.writelines(run_lines)

    logger.info(f"Corrections  : {len(statCorr_list)}")
    logger.info(f"Output       : {parameters.fileRunSave}")

    return {
        'output':        parameters.fileRunSave,
        'log':           log_path,
        'n_corrections': len(statCorr_list),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Append SSST static corrections to a NLL run file.'
    )
    parser.add_argument('--loc-folder',  required=True,
                        help='NLL loc folder containing last.stat_totcorr')
    parser.add_argument('--run-file',    required=True,
                        help='First-pass run file to copy from')
    parser.add_argument('--run-save',    required=True,
                        help='Output second-pass run file')
    parser.add_argument('--min-phases',  type=int, default=100,
                        help='Minimum phase count for a correction to be used (default: 100)')
    parser.add_argument('--log-dir',     default=None,
                        help='Log directory (default: NLL_run/console_output/)')
    args = parser.parse_args()

    generate_second_run(
        SecondRunParams(
            locFolderName = args.loc_folder,
            fileRunName   = args.run_file,
            fileRunSave   = args.run_save,
            minPhases     = args.min_phases,
        ),
        log_dir = args.log_dir,
    )


if __name__ == '__main__':
    main()
