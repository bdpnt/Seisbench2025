'''
genRunFiles_in generates all files required for an NLL process, from both
an OBS file and an Inventory file. It generates 
'''

### Separer W,C,E
from obspy import read_inventory
import os

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
def genChildObs(parameters):
    #---- Load global file
    with open(parameters.fileBulletin,'r') as f:
        lines = f.readlines()

    #---- Start new file
    nbEQ = 0
    with open(parameters.fileBulletinIn,'w') as f:
        f.writelines(lines[:4])
        for ID,line in enumerate(lines):
            if line.startswith('# '):
                latitude = float(line.split()[7])
                longitude = float(line.split()[8])
                if (latitude >= parameters.latMin_event and latitude <= parameters.latMax_event) and (longitude >= parameters.lonMin_event and longitude <= parameters.lonMax_event):
                    nbEQ += 1
                    f.writelines(line)
                    endPicks = False
                    while not endPicks:
                        ID += 1
                        pick = lines[ID]
                        if not pick.startswith('\n'):
                            f.writelines(pick)
                        else:
                            endPicks = True
                    f.writelines('\n')

    print(f'Succesfully generated Bulletin @ {parameters.fileBulletinIn} [{nbEQ} EQ]')

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
    sta_elev = station.elevation / 1000 if (hasattr(station, 'elevation') and station.elevation is not None) else float(0)
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

    with open(parameters.fileStations,'w') as f:
        for alternateCode in uniqueStations:
            line = getStationLine(inventory,alternateCodeMap,alternateCode)
            f.write(line)
    
    print(f'Succesfully generated GTSRCE file @ {parameters.fileStations}')

def verifyFoldersExistence(parameters):
    params = [
        parameters.fileBulletinIn,
        parameters.fileBulletinOut,
        parameters.fileStations,
        parameters.fileRunSave,
        parameters.fileModel,
        parameters.fileTime,
    ]

    for param in params:
        path = '/'.join(param.split('/')[:-1])
        os.makedirs(path, exist_ok=True)

def genRun(parameters):
    lines = []

    # Region coordinates
    lines.append('CONTROL 1 54321\n')
    lines.append(f'TRANS  LAMBERT  WGS-84  {parameters.latMin_box} {parameters.lonMin_box}  41 44 0.0\n')
    lines.append('\n')

    # Velocity model
    lines.append('# Velocity model\n')
    lines.append(f'VGOUT  {parameters.fileModel}\n')
    lines.append('VGTYPE P\n')
    lines.append(f'VGGRID  2 {parameters.VGGRID[0]} {parameters.VGGRID[1]}  0.0 0.0 -3  0.05 0.05 0.05  SLOW_LEN\n')
    lines.append('\n')
    lines.append('LAYER    0.0  5.5 0.0       3.2   0.00   2.72 0.0\n')
    lines.append('LAYER    1    5.6 0.0       3.26  0.00  2.7 0.0\n')
    lines.append('LAYER    4    6.1 0.0       3.55  0.00  2.8 0.0\n')
    lines.append('LAYER    11   6.4 0.0       3.72  0.00  2.8 0.0\n')
    lines.append('LAYER    34   8.0 0.00      4.50  0.00  3.32 0.0\n')
    lines.append('\n')
    lines.append(f'GTFILES  {parameters.fileModel}  {parameters.fileTime} P\n')
    lines.append('GTMODE GRID2D ANGLES_NO\n')
    lines.append('\n')

    # Bulletin to read and write
    lines.append('# Bulletin to read and write\n')
    lines.append(f'LOCFILES {parameters.fileBulletinIn} NLLOC_OBS  {parameters.fileTime}  {parameters.fileBulletinOut}\n')
    lines.append('LOCHYPOUT SAVE_HYPO71_SUM\n')
    lines.append('\n')

    # Localization method
    lines.append('# Localization method\n')
    lines.append(f'LOCGRID {parameters.LOCGRID[0]} {parameters.LOCGRID[1]} {parameters.LOCGRID[2]} 0.0 0.0 -3  0.05 0.05 0.05 PROB_DENSITY SAVE\n')
    lines.append('LOCSEARCH  OCT 50 50 5 0.001 50000 500 1 0\n')
    lines.append('LOCMETH EDT_OT_WT 9999 4 -1 -1 1.72 6 -1.0 0\n')
    lines.append('\n')

    # Stations coordinates
    lines.append('# Stations coordinates\n')
    lines.append(f'INCLUDE {parameters.fileStations}\n')
    lines.append('\n')

    # Localization parameters
    lines.append('# Localization parameters\n')
    lines.append('GT_PLFD  1.0e-7  0\n')
    lines.append('LOCGAU 0.05 0.0\n')
    lines.append('LOCGAU2 0.01 0.01 2.0\n')
    lines.append('LOCPHASEID  P   P p G PN PG\n')
    lines.append('LOCPHASEID  S   S s G SN SG\n')
    lines.append('LOCQUAL2ERR 0.05 0.15 0.05 0.15 99999.9\n')
    lines.append('LOCPHSTAT 9999.0 -1 9999.0 1.0 1.0 9999.9 -9999.9 9999.9\n')
    lines.append('\n')

    # Save run file
    with open(parameters.fileRunSave,'w',encoding='utf-8') as f:
        f.writelines(lines)

    print(f'Succesfully generated run file @ {parameters.fileRunSave}')

# MAIN
if __name__ == '__main__':
    parameters = Parameters(
        fileBulletin = "obs/GLOBAL.obs", # GLOBAL OBS file to use
        fileInventory = 'stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
        fileBulletinIn = "obs/GLOBAL_E.obs", # child OBS events file to generate
        fileStations = 'stations/GTSRCE_E.txt', # GTSRCE stations file to generate
        fileRunSave = 'run/run_E.in', # run file to generate
        latMin_event = 42.0, # minimum latitude for the event box
        latMax_event = 43.25, # maximum latitude for the event box
        lonMin_event = 1.5, # minimum longitude for the event box
        lonMax_event = 3.25, # maximum longitude for the event box
        fileModel = 'model/Pyrenees_E/Pyrenees_E', # model file to generate
        fileTime = 'time/Pyrenees_E/Pyrenees_E', # time file to generate
        fileBulletinOut = 'loc/GLOBAL_E/GLOBAL_E.obs', # loc file to generate
        latMin_box = 41.55, # minimum latitude for the main box
        lonMin_box = 0.3, # minimum longitude for the main box
        VGGRID = [9000,800], # VGGRID h/v parameters
        LOCGRID = [6800,4500,800], # LOCGRID E/W ; N/S ; U/D parameters
    )

    verifyFoldersExistence(parameters) # Verify that all folders exist for the files to generate
    genChildObs(parameters) # Generate the OBS file
    genGTSRCE(parameters) # Generate the GTSRCE file
    genRun(parameters) # Generate the run file