"""
_convert_csv_to_stationxml.py
============================
Convert an OMP station CSV file to a StationXML inventory.

The CSV must contain columns: network, station, latitude, longitude,
elevation, starttime, endtime.

Usage
-----
    python fetch_inventory/_convert_csv_to_stationxml.py \\
        --file  stations/OMP_stations_XML/ADDITIONAL_sta.csv \\
        --save  stations/OMP_stations_XML/ADDITIONAL_inventory.xml \\
        --description ADDITIONAL
"""

import argparse
import logging

import pandas as pd
from obspy import Inventory
from obspy.core.inventory import Network, Station


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def csv_to_stationxml(file, file_save, network_description='ADDITIONAL'):
    """
    Convert an OMP station CSV to a StationXML inventory.

    Parameters
    ----------
    file                : str — input CSV path
    file_save           : str — output StationXML path
    network_description : str — description string for the Network object

    Returns
    -------
    dict with key: output
    """
    column_use   = ['network', 'station', 'latitude', 'longitude', 'elevation', 'starttime', 'endtime']
    column_types = {'network': 'str', 'station': 'str', 'latitude': 'float64',
                    'longitude': 'float64', 'elevation': 'float32'}

    df = pd.read_csv(
        file, usecols=column_use, dtype=column_types,
        parse_dates=['starttime', 'endtime'],
        date_format='%Y:%m:%dT%H:%M:%S',
    )

    logger.info(f"Loaded {len(df)} station(s) from {file}")

    inventory = Inventory(source='Additional')

    for net_code in df.network.unique():
        net_df  = df[df.network == net_code]
        network = Network(
            code=net_code,
            stations=None,
            total_number_of_stations=len(net_df),
            description=network_description,
        )
        logger.info(f"Network {net_code}: {len(net_df)} station(s)")

        for _, row in net_df.iterrows():
            station = Station(
                code      = row.station,
                latitude  = row.latitude,
                longitude = row.longitude,
                elevation = row.elevation if not pd.isna(row.elevation) else 0,
                start_date = row.starttime,
                end_date   = row.endtime if not pd.isna(row.endtime) else None,
            )
            network.stations.append(station)

        inventory.networks.append(network)

    n_total = sum(len(net.stations) for net in inventory.networks)
    inventory.write(file_save, format='STATIONXML')
    logger.info(f"StationXML written: {file_save} ({len(inventory.networks)} network(s), {n_total} station(s))")
    return {'output': file_save}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert an OMP station CSV to a StationXML inventory.'
    )
    parser.add_argument('--file',        required=True, help='Input station CSV')
    parser.add_argument('--save',        required=True, help='Output StationXML path')
    parser.add_argument('--description', default='ADDITIONAL', help='Network description string')
    args = parser.parse_args()

    csv_to_stationxml(args.file, args.save, args.description)


if __name__ == '__main__':
    main()
