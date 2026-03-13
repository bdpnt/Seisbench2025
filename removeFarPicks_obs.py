'''
removeFarPicks_obs removes the picks from stations too far to the event 
'''

import math
from obspy import read_inventory
import pandas as pd

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
    """Distance in km between two geographical points"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def getStationsCoords(parameters):
    inventory = read_inventory(parameters.fileInventory, format='STATIONXML')

    staData = []
    for net in inventory.networks:
        for sta in net.stations:
            staData.append({
                'AlternateCode': sta.alternate_code,
                'Latitude': sta.latitude,
                'Longitude': sta.longitude,
            })

    staCoords = pd.DataFrame(staData)
    staCoords = staCoords.drop_duplicates(subset='AlternateCode', keep='first')

    return staCoords

def removeFarPicks(parameters):
    #---- Retrieve stations coordinates
    staCoords = getStationsCoords(parameters)

    #---- Retrieve Bulletin
    with open(parameters.fileBulletin, 'r') as f:
        lines = f.readlines()
    
    #---- Check lines for picks whose station are too far
    pickCount = 0
    removeID = set()
    for ID,line in enumerate(lines):
        if line.startswith('# '):
            event_coords = (float(line.split()[7]), float(line.split()[8]))

            pickID = ID
            endPicks = False
            while not endPicks:
                pickID += 1
                pick = lines[pickID]

                if pick.startswith('\n'):
                    endPicks = True
                    continue

                pick_altCode = pick[:7].strip()
                pickLat = staCoords[staCoords.AlternateCode == pick_altCode].Latitude.iloc[0]
                pickLon = staCoords[staCoords.AlternateCode == pick_altCode].Longitude.iloc[0]

                distToEvent = haversine(pickLat,pickLon,event_coords[0],event_coords[1])

                if distToEvent > parameters.maxDistance:
                    removeID.add(pickID)

                # Update pick count
                pickCount += 1
    
    #---- Remove picks from stations too far
    lines = [line for ID,line in enumerate(lines) if ID not in removeID]

    #---- Save the new OBS
    with open(parameters.fileBulletin, 'w') as f:
        f.writelines(lines)

    print(f'\nSuccesfully saved the updated Bulletin @ {parameters.fileBulletin}')
    print(f'    - removed {pickCount - len(removeID)} / {pickCount} picks')
                
# MAIN
if __name__ == '__main__':
    parameters = Parameters(
        fileBulletin = 'obs/GLOBAL.obs',
        fileInventory = 'stations/GLOBAL_inventory.xml',
        maxDistance = 80, # max distance between event and station, in kilometers
    )

    removeFarPicks(parameters)
