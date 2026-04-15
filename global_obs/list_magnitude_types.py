"""
list_magnitude_types.py
============================
List all magnitude types present in an .obs bulletin and their event counts.

Usage
-----
    python global_obs/list_magnitude_types.py --file-name obs/GLOBAL.obs
"""

import argparse
import os
import sys


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _retrieve_events(file_name):
    """Read an .obs file and return a list of event header lines (stripped of the leading '# ')."""
    with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
        cat_lines = f.readlines()

    event_lines = []
    for line in cat_lines:
        if line.startswith('###'):
            continue
        elif line.startswith('#'):
            event_lines.append(line.rstrip('\n').lstrip('# '))

    print(f'Events from Catalog @ {file_name} successfully retrieved')
    return event_lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_magnitude_types(parameters):
    """
    Count and print all magnitude types found in an .obs bulletin file.

    Parameters
    ----------
    parameters : object with attribute file_name : str
        Path to the .obs bulletin file.

    Returns
    -------
    dict
        'output'    — path to the input file
        'mag_types' — dict mapping magnitude-type strings to event counts
    """
    event_lines = _retrieve_events(parameters.file_name)

    mag_types = {}
    for line in event_lines:
        parts   = line.split()
        mag_key = parts[10] + ' ' + parts[11]
        mag_types[mag_key] = mag_types.get(mag_key, 0) + 1

    print(f'Magnitude types available in Catalog @ {parameters.file_name}:')
    for mag_key, count in mag_types.items():
        print(f'    - {mag_key} ({count})')

    return {'output': parameters.file_name, 'mag_types': mag_types}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='List all magnitude types and their counts in an .obs bulletin.'
    )
    parser.add_argument('--file-name', required=True, help='Path to the .obs bulletin file')
    args = parser.parse_args()

    class _Params:
        file_name = args.file_name

    list_magnitude_types(_Params())


if __name__ == '__main__':
    main()
