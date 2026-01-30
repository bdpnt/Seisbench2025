from obspy import Inventory
from obspy.core.inventory import Network, Station, Channel, util
import pandas as pd

#--- Read the CSV file
file = 'stations/OMP_stations_XML/ADDITIONAL_sta.csv'
networkDescription = 'ADDITIONAL'
fileSave = 'stations/OMP_stations_XML/ADDITIONAL_inventory.xml'

# Read file with specific types for non-datetimes
columnUse = [
    'network',
    'station',
    'latitude',
    'longitude',
    'elevation',
    'starttime',
    'endtime',
]
columnTypes = {
    'network': 'str',
    'station': 'str',
    'latitude': 'float32',
    'longitude': 'float32',
    'elevation': 'float32',
}

df = pd.read_csv(file, usecols=columnUse, dtype=columnTypes, parse_dates=['starttime','endtime'], date_format='%Y:%m:%dT%H:%M:%S')

#--- Create an inventory
inventory = Inventory(
    source='Additional',
)

#--- Create the network
# Only one network per file
net_codes = df.network.unique()

for net_code in net_codes:
    net_stations_number = len(df[df.network == net_code])

    network = Network(
        code=net_code,
        stations=None,
        total_number_of_stations=net_stations_number,
        description=networkDescription
    )

#--- Create the station and append to network
    for _, row in df[df.network == net_code].iterrows():
        sta_code = row.station
        sta_latitude = row.latitude
        sta_longitude = row.longitude
        sta_elevation = row.elevation if not pd.isna(row.elevation) else 0
        sta_startdate = row.starttime
        sta_enddate = row.endtime if not pd.isna(row.endtime) else None

        station = Station(
            code=sta_code,
            latitude=sta_latitude,
            longitude=sta_longitude,
            elevation=sta_elevation,
            start_date=sta_startdate,
            end_date=sta_enddate,
        )

        network.stations.append(station)

#--- Append network to inventory
    inventory.networks.append(network)

#--- Save inventory
inventory.write(fileSave,format='STATIONXML')