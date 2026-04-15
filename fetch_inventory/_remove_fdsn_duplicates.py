"""
_remove_fdsn_duplicates.py
============================
Remove from an OMP station CSV any stations that already appear in the
FDSN StationXML inventories, to avoid duplicates when merging.

Usage
-----
    python fetch_inventory/_remove_fdsn_duplicates.py \\
        --file       stations/OMP_stations_XML/ARGELES_sta_ORG.csv \\
        --folder     "stations/FDSN_stations_XML/*.xml" \\
        --save       stations/OMP_stations_XML/ARGELES_sta.csv
"""

import argparse

import glob
import pandas as pd
from obspy import read_inventory


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_networks(file, folder, file_save):
    """
    Remove stations from a CSV that already exist in any FDSN StationXML.

    Parameters
    ----------
    file      : str — input CSV path (must contain a 'station' column)
    folder    : str — glob pattern for FDSN StationXML files
    file_save : str — output CSV path (filtered)

    Returns
    -------
    dict with key: output
    """
    df           = pd.read_csv(file, usecols=['station', 'latitude', 'longitude', 'elevation'])
    station_list = df.station.to_list()

    found = set()
    for folder_file in glob.glob(folder):
        inv = read_inventory(folder_file, format='STATIONXML')
        for network in inv.networks:
            for station in network.stations:
                if station.code in station_list:
                    found.add(station.code)

    df = df[~df['station'].isin(found)]
    df.insert(0, 'network', 'XX')
    df.to_csv(file_save, index=False)

    return {'output': file_save}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Remove from a station CSV any stations already in FDSN inventories.'
    )
    parser.add_argument('--file',   required=True, help='Input station CSV')
    parser.add_argument('--folder', required=True, help='Glob pattern for FDSN StationXML files')
    parser.add_argument('--save',   required=True, help='Output CSV path')
    args = parser.parse_args()

    check_networks(args.file, args.folder, args.save)


if __name__ == '__main__':
    main()
