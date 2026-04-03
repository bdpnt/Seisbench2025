import glob
import pandas as pd
from obspy import read_inventory


def check_networks(file, folder, file_save):
    """Remove stations from a CSV that already exist in any FDSN StationXML inventory."""
    df = pd.read_csv(file, usecols=['station','latitude','longitude','elevation'])
    stationList = df.station.to_list()

    foundStations = set()
    for folderFile in glob.glob(folder):
        inventory = read_inventory(folderFile, format='STATIONXML')

        for network in inventory.networks:
            for station in network.stations:
                if station.code in stationList:
                    foundStations.add(station.code)

    df = df[~df['station'].isin(foundStations)]

    # Add network
    df.insert(0, 'network', 'XX')

    df.to_csv(file_save, index=False)


if __name__ == '__main__':
    check_networks(
        file='stations/OMP_stations_XML/ARGELES_sta_ORG.csv',
        folder='stations/FDSN_stations_XML/*.xml',
        file_save='stations/OMP_stations_XML/ARGELES_sta.csv',
    )
