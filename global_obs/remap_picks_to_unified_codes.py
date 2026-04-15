"""
remap_picks_to_unified_codes.py
============================
Associate every pick in an .obs bulletin with its unified alternate station code
from the global inventory, removing picks whose station cannot be matched.

Usage
-----
    python global_obs/remap_picks_to_unified_codes.py \
        --file-inventory stations/GLOBAL_inventory.xml \
        --folder-bulletin "obs/*.obs"
"""

import argparse
import glob
import os
import sys

from obspy import read_inventory, UTCDateTime
import pandas as pd
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AssociatePicksParams:
    """
    Configuration for remapping picks to unified station codes.

    Attributes
    ----------
    file_inventory  : str — path to the STATIONXML inventory file
    folder_bulletin : str — glob pattern for the .obs bulletin files to update
    """
    file_inventory:  str
    folder_bulletin: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_unique_stations(inventory):
    """
    Build a DataFrame of all stations in the inventory with their alternate codes and active date ranges.

    Parameters
    ----------
    inventory : obspy.core.inventory.Inventory

    Returns
    -------
    pd.DataFrame with columns: Network, Code, AlternateCode, StartDate, EndDate
    """
    unique_sta = pd.DataFrame(columns=['Network', 'Code', 'AlternateCode', 'StartDate', 'EndDate'])
    for net in inventory.networks:
        for sta in net.stations:
            new_row = {
                'Network':       net.code,
                'Code':          sta.code.split('_')[0],
                'AlternateCode': sta.alternate_code,
                'StartDate':     sta.start_date,
                'EndDate':       sta.end_date,
            }
            unique_sta = pd.concat([unique_sta, pd.DataFrame([new_row])], ignore_index=True)
    return unique_sta


def _find_code(line, unique_sta):
    """
    Look up the alternate code for the station referenced in a pick line.

    Parameters
    ----------
    line       : str          — raw pick line from an .obs bulletin
    unique_sta : pd.DataFrame — produced by find_unique_stations()

    Returns
    -------
    str or None or False
        Alternate code (9-char left-justified) if found, None if no unique
        match, False if the pick date cannot be parsed.
    """
    station_name = (
        line[:9].lstrip('.').strip() if line.startswith('.')
        else line[:9].split('.')[1].strip()
    )
    matching = unique_sta.index[unique_sta.Code == station_name].tolist()

    if not matching:
        return None

    year   = line[31:35]
    month  = line[35:37]
    day    = line[37:39]
    hour   = line[40:42]
    minute = line[42:44]
    second = line[45:47]

    try:
        date_line = UTCDateTime(f'{year}-{month}-{day}T{hour}:{minute}:{second}Z')
    except Exception:
        return False

    alternate_code = None

    if len(matching) == 1:
        alternate_code = unique_sta.AlternateCode.loc[matching[0]]

    working = []
    for i, (start, end) in enumerate(
        zip(unique_sta.StartDate.loc[matching], unique_sta.EndDate.loc[matching])
    ):
        if start is None:
            continue
        if end is None:
            end = UTCDateTime(2500, 12, 31)
        if start <= date_line <= end:
            working.append(i)

    if len(working) == 1:
        alternate_code = unique_sta.AlternateCode.loc[matching[working[0]]]

    if alternate_code is None:
        return None

    return alternate_code.ljust(9)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def remap_picks_to_unified_codes(parameters):
    """
    Update all bulletin files so every pick references its unified alternate station code.

    Picks whose station cannot be matched in the inventory are removed.

    Parameters
    ----------
    parameters : AssociatePicksParams

    Returns
    -------
    dict
        'output'    — glob pattern used (same as parameters.folder_bulletin)
        'n_removed' — total picks removed across all files
        'n_total'   — total picks seen across all files
    """
    print('\n#########')

    inventory = read_inventory(parameters.file_inventory, format='STATIONXML')
    print(f'\nStations from Inventory @ {parameters.file_inventory} successfully retrieved')

    unique_sta = find_unique_stations(inventory)

    total_removed = 0
    total_picks   = 0

    for file_bulletin in glob.glob(parameters.folder_bulletin):
        with open(file_bulletin, 'r', encoding='utf-8') as f:
            lines_bulletin = f.readlines()
        print(f'\nPicks from Bulletin @ {file_bulletin} successfully retrieved:')

        org_length = 0
        new_length = 0
        new_bulletin = []

        for line in lines_bulletin:
            if not line.startswith('#') and line != '\n':
                org_length += 1
                code_line = _find_code(line, unique_sta)
                if code_line not in (None, False):
                    new_bulletin.append(code_line + line[9:])
                    new_length += 1
            else:
                new_bulletin.append(line)

        picks_removed         = org_length - new_length
        picks_removed_percent = picks_removed / org_length * 100 if org_length else 0.0
        total_removed        += picks_removed
        total_picks          += org_length

        print(f'    - picks removed: {picks_removed}/{org_length} ({picks_removed_percent:.3f} %)')

        with open(file_bulletin, 'w') as f:
            f.writelines(new_bulletin)

        print(f'    - bulletin successfully saved @ {file_bulletin}')

    print('\n#########\n')
    return {
        'output':    parameters.folder_bulletin,
        'n_removed': total_removed,
        'n_total':   total_picks,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Remap .obs bulletin picks to unified alternate station codes.'
    )
    parser.add_argument('--file-inventory',  required=True,
                        help='Path to the STATIONXML inventory file')
    parser.add_argument('--folder-bulletin', required=True,
                        help='Glob pattern for .obs bulletin files (e.g. "obs/*.obs")')
    args = parser.parse_args()

    params = AssociatePicksParams(
        file_inventory  = args.file_inventory,
        folder_bulletin = args.folder_bulletin,
    )
    remap_picks_to_unified_codes(params)


if __name__ == '__main__':
    main()
