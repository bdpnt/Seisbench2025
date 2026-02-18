'''
genGTSRCE creates the GTSRCE.txt file needed for the NLL workflow, from Bulletin @ obs/GLOBAL.obs
and Inventory @ stations/GLOBAL_inventory.xml
'''

from obspy import read_inventory

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
def build_alternateCodeMap(inventory):
    code_map = {}
    for network in inventory:
        for station in network:
            code_map[station.alternate_code] = (network.code, station.code)
    return code_map

def findStationInfo(inventory,alternateCodeMap,alternateCode):
    codes = alternateCodeMap.get(alternateCode)
    station = inventory.select(network=codes[0],station=codes[1]).networks[0].stations[0]
    sta_lat = station.latitude
    sta_lon = station.longitude
    sta_elev = station.elevation if (hasattr(station, 'elevation') and station.elevation is not None) else float(0)
    return sta_lat,sta_lon,sta_elev

def getStationLine(inventory,alternateCodeMap,alternateCode):
    sta_lat,sta_lon,sta_elev = findStationInfo(inventory,alternateCodeMap,alternateCode)
    return f"GTSRCE {alternateCode} LATLON {sta_lat:.6f} {sta_lon:.6f} 0.0 {sta_elev:.3f}\n"

def genGTSRCE(parameters):
    #---- Bulletin
    with open(parameters.fileBulletin,'r') as f:
        lines = f.readlines()

    uniqueStations = set()
    for line in lines:
        if not (line.startswith('\n') or line.startswith('#')):
            code = line.split()[0]
            uniqueStations.add(code)

    #---- Inventory
    inventory = read_inventory(parameters.fileInventory, format='STATIONXML')

    #---- Save to the file
    alternateCodeMap = build_alternateCodeMap(inventory)

    with open(parameters.fileSave,'w') as f:
        for alternateCode in uniqueStations:
            line = getStationLine(inventory,alternateCodeMap,alternateCode)
            f.write(line)

# MAIN
if __name__ == '__main__':
    parameters = Parameters(
        fileBulletin = 'obs/GLOBAL.obs',
        fileInventory = 'stations/GLOBAL_inventory.xml',
        fileSave = 'stations/GTSRCE.txt'
    )

    genGTSRCE(parameters)