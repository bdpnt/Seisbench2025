"""
_fill_missing_elevations.py
============================
Fill in missing (zero) elevations in a station CSV by querying the
Open-Elevation API.

Usage
-----
    python fetch_inventory/_fill_missing_elevations.py \\
        --file  stations/OMP_stations_XML/ADDITIONAL_sta.csv \\
        --save  stations/OMP_stations_XML/ADDITIONAL_sta_filled.csv
"""

import argparse
import time

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_elevation(lat, lng):
    """
    Query the Open-Elevation API and return the elevation in metres.

    Returns 0 on any error (API failure or network issue).
    """
    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lng}"
    try:
        response = requests.get(url).json()
        if 'results' in response:
            return int(response['results'][0]['elevation'])
        print(f"API error for ({lat}, {lng}): {response}")
        return 0
    except Exception as e:
        print(f"Request failed for ({lat}, {lng}): {e}")
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_elevation(file, file_save):
    """
    Fill missing elevations (value 0) in a station CSV via Open-Elevation.

    Parameters
    ----------
    file      : str — input CSV path
    file_save : str — output CSV path

    Returns
    -------
    dict with key: output
    """
    df = pd.read_csv(file, dtype={'latitude': 'float64', 'longitude': 'float64', 'elevation': 'float32'})

    for idx in df.index[df['elevation'] == 0]:
        df.at[idx, 'elevation'] = _get_elevation(df.at[idx, 'latitude'], df.at[idx, 'longitude'])
        time.sleep(1)  # avoid rate limiting

    df.to_csv(file_save, index=False)
    return {'output': file_save}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Fill missing elevations in a station CSV via Open-Elevation API.'
    )
    parser.add_argument('--file', required=True, help='Input station CSV')
    parser.add_argument('--save', required=True, help='Output CSV path')
    args = parser.parse_args()

    check_elevation(args.file, args.save)


if __name__ == '__main__':
    main()
