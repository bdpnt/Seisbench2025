'''
fusionInventory_xml merges several Inventory into one, by safely comparing stations
in each Network and merging them if necessary, otherwise renaming them.
'''

from obspy import read_inventory, UTCDateTime
from obspy.core.inventory import Inventory
import glob
from collections import Counter, defaultdict
import datetime
import math

# CLASS
class Parameters:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        attrs = ', '.join(f"{k}={v}" for k, v in self.__dict__.items())
        return f"Parameters({attrs})"

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

# FUNCTION
def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two geographical points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def checkInventory(inventory):
    # Get unique stations in networks
    uniqueSta = defaultdict(list)
    for net in inventory.networks:
        for sta in net.stations:
            uniqueSta[sta.code.split('_')[0]].append(net.code)

    uniqueSta = {sta: nets for sta, nets in uniqueSta.items() if len(nets) >= 2} # check for really unique stations
    uniqueSta = {sta: nets for sta, nets in uniqueSta.items() if any(item != nets[0] for item in nets)} # check for only same network

    # Manually remove unwanted stations from specific network
    for station, networks in uniqueSta.items():
        print('\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n')
        print(f"\nStation: {station}")
        for network in networks:
            current_inv = inventory.select(network=network, station=station)
            print(f"  In Network: {network}")
            for net in current_inv.networks:
                for sta in net.stations:
                    print(sta.__str__())
        print("____________________")

        remove_nets = input('Network(s) to remove, if any, separated by commas (e.g. > FR,RD): ')
        remove_nets = remove_nets.split(',')
        for network in remove_nets:
            inventory = inventory.remove(network=network, station=station)
    
    return inventory

def addAlternateCode(inventory):
    # Loop on all stations from all networks:
    for network in inventory.networks:
        netCode = network.code
        staID = 0
        for station in network:
            station.alternate_code = netCode + '.' + str(staID).rjust(4,'0')
            staID += 1
    
    return inventory

def mergeInventory(parameters):
    #--- Create an inventory
    inventory = Inventory()

    #--- Merge all inventories
    for folderFile in glob.glob(parameters.folderPath):
        fileInventory = read_inventory(folderFile,format='STATIONXML')
        inventory.extend(fileInventory)

    #--- Merge duplicate networks
    # Find duplicates
    allNetworks = [net.code for net in inventory.networks]
    duplicateNetworks = [code for code,count in Counter(allNetworks).items() if count > 1]

    # Merge duplicates (not caring about stations at this step)
    for networkCode in duplicateNetworks:
        foundNetworks = [net for net in inventory.networks if net.code == networkCode]
        mainNetwork = foundNetworks[0]
        for subNetwork in foundNetworks[1:]:
            for station in subNetwork:
                mainNetwork.stations.append(station)
            inventory.networks.remove(subNetwork)
    
    #--- Merge duplicate stations inside same network
    for network in inventory.networks:
        # Find all stations with the same code (potential duplicates)
        station_groups = defaultdict(list)
        for sta in network.stations:
            station_groups[sta.code].append(sta)

        # Process each group of stations with the same code
        for _, stationsWithThisCode in station_groups.items():
            if len(stationsWithThisCode) <= 1:
                continue

            # Sort stations by start date (earliest first)
            stationsWithThisCode.sort(key=lambda sta: getattr(sta, 'start_date', None) or UTCDateTime(datetime.datetime.max))

            # Create graph: nodes are indices of stations, edges when distance <= acceptedDistance
            n = len(stationsWithThisCode)
            graph = defaultdict(list)

            for i in range(n):
                for j in range(i+1, n):
                    sta1 = stationsWithThisCode[i]
                    sta2 = stationsWithThisCode[j]
                    if haversine(sta1.latitude, sta1.longitude,
                                sta2.latitude, sta2.longitude) <= parameters.acceptedDistance/1000:
                        graph[i].append(j)
                        graph[j].append(i)

            # Find connected components (clusters) using DFS
            visited = [False] * n
            clusters = []

            for i in range(n):
                if not visited[i]:
                    cluster_indices = []
                    stack = [i]
                    visited[i] = True
                    while stack:
                        node = stack.pop()
                        cluster_indices.append(node)
                        for neighbor in graph.get(node, []):
                            if not visited[neighbor]:
                                visited[neighbor] = True
                                stack.append(neighbor)
                    clusters.append([stationsWithThisCode[idx] for idx in cluster_indices])

            # Process each cluster
            for it,cluster in enumerate(clusters):
                # Pass if there are no duplicates in the cluster
                if len(cluster) <= 1:
                    cluster[0].code = f'{cluster[0].code}_{it}' # rename the station (no need to check for multiple clusters here)
                    continue

                # Select the station with earliest start date as main station
                mainStation = min(cluster, key=lambda sta: getattr(sta, 'start_date', None) or UTCDateTime(datetime.datetime.max))

                # Rename the station if there are multiple clusters
                if len(clusters) > 1:
                    mainStation.code = f'{mainStation.code}_{it}' # rename the station

                # Stations to be removed (all except mainStation at exactly mainIndex, because sometimes stations are exactly identical in their informations)
                mainIndex = cluster.index(mainStation)
                stations_to_remove = [sta for i, sta in enumerate(cluster) if i != mainIndex]

                # Merge data from all stations to mainStation
                for sta in stations_to_remove:
                    # Elevation: take from any station that has it
                    if not hasattr(mainStation, 'elevation') and hasattr(sta, 'elevation'):
                        mainStation.elevation = sta.elevation

                    # Start date: take the earliest
                    if hasattr(sta, 'start_date') and sta.start_date is not None:
                        current_start = getattr(mainStation, 'start_date', None)
                        if current_start is None or sta.start_date < current_start:
                            mainStation.start_date = sta.start_date

                    # End date: take the latest or None
                    if hasattr(sta, 'end_date'):
                        current_end = getattr(mainStation, 'end_date', None)
                        if sta.end_date is None:
                            mainStation.end_date = None
                        elif current_end is not None and sta.end_date > current_end:
                            mainStation.end_date = sta.end_date

                    # Merge channels (avoid duplicates)
                    for channel in sta.channels:
                        if channel not in mainStation.channels:
                            mainStation.channels.append(channel)

                # Remove all stations except the main one from the network
                for sta in stations_to_remove:
                    if sta in network.stations:  # Safety check
                        network.stations.remove(sta)
    
    #--- Verify that all stations are distinct by network/time
    inventory = checkInventory(inventory)

    #--- Add alternate code as NET.0000
    inventory = addAlternateCode(inventory)

    #--- Write the merged Inventory
    inventory.write(parameters.saveName,format='STATIONXML')
    print("____________________")
    print(f"\nInventory successfully saved @ {parameters.saveName}\n")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        folderPath = 'stations/*/*.xml',
        saveName = 'stations/GLOBAL_inventory.xml',
        acceptedDistance = 10, # in m, accepted distance between two stations considered as similar
    )

    #---- Write merged Inventory
    mergeInventory(parameters)

