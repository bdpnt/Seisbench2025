import glob
import pandas as pd
from obspy import read_inventory

##### VERIFY IF EXISTS IN ANY FDSN NETWORK
file = 'stations/OMP_stations_XML/ARGELES_sta_ORG.csv'
df = pd.read_csv(file, usecols=['station','latitude','longitude','elevation'])
stationList = df.station.to_list()

# Folder to check
folder = "stations/FDSN_stations_XML/*.xml"  # Find all .xml

foundStations = set()
for folderFile in glob.glob(folder):
    # Read inventory
    inventory = read_inventory(folderFile,format='STATIONXML')

    # Check for any station in inventory
    for network in inventory.networks:
        for station in network.stations:
            if station.code in stationList:
                foundStations.add((station.code))

# Remove stations in foundStations from frame
removeStations = {station for station in foundStations}
df = df[~df['station'].isin(removeStations)]

# Add network
df.insert(0,'network','XX')

# Save as csv
df.to_csv('ARGELES_sta.csv',index=False)
    