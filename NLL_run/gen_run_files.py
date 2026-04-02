'''
genRunFiles_in generates all files required for an NLL process, from both
an OBS file and an Inventory file. It generates the child OBS file, the
GTSRCE file and the IN (run) file.
'''

from obspy import read_inventory
import os
import math

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

def build_alternateCodeMap(inventory,fileMap):
    with open(fileMap,'r') as f:
        lines = f.readlines()

    code_map = {}
    for ID,line in enumerate(lines):
        if line.startswith('Alternate'):
            alternate_code = line.split()[-1]
            codeID = ID
            endCode = False
            while not endCode:
                codeID += 1
                codeLine = lines[codeID]
                if codeLine.startswith('\n'):
                    endCode = True
                elif codeLine.startswith('  Station'):
                    station_code = codeLine.split('.')[-1].rstrip('\n')
                    network_code = codeLine.split(':')[-1].split('.')[0].strip()
            code_map[alternate_code] = (network_code, station_code)

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
    alternateCodeMap = build_alternateCodeMap(inventory,parameters.fileMap)

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

def compute_new_grid_corners(lat_sw, lon_sw, lat_ne, lon_ne):
    """
    Compute the new southwestern corner coordinates and grid size for NonLinLoc.

    Parameters:
    - lat_sw, lon_sw: Original southwestern corner (latitude, longitude)
    - lat_ne, lon_ne: Original northeastern corner (latitude, longitude)

    Returns:
    - lat_new_sw, lon_new_sw: New southwestern corner (latitude, longitude)
    - lat_new_ne, lon_new_ne: New northeastern corner (latitude, longitude)
    - dx, dy: Grid size in km (longitude, latitude)
    - npoints_x, npoints_y, npoints_z: Number of grid points in x, y, z directions
    """
    R = 6371.0  # Earth radius in km

    def latlon_to_km(lat, lon, lat0, lon0):
        lat_rad = lat * (math.pi / 180.0)
        lon_rad = lon * (math.pi / 180.0)
        lat0_rad = lat0 * (math.pi / 180.0)
        lon0_rad = lon0 * (math.pi / 180.0)
        x = R * (lon_rad - lon0_rad) * math.cos((lat0_rad + lat_rad) / 2.0)
        y = R * (lat_rad - lat0_rad)
        return x, y

    def km_to_latlon(x, y, lat0, lon0):
        lat0_rad = lat0 * (math.pi / 180.0)
        lon0_rad = lon0 * (math.pi / 180.0)
        lat_rad = lat0_rad + y / R
        lon_rad = lon0_rad + x / (R * math.cos(lat0_rad))
        lat = lat_rad * (180.0 / math.pi)
        lon = lon_rad * (180.0 / math.pi)
        return lat, lon

    # Convert original corners to km offsets from southwestern corner
    x0, y0 = latlon_to_km(lat_sw, lon_sw, lat_sw, lon_sw)
    x1, y1 = latlon_to_km(lat_ne, lon_ne, lat_sw, lon_sw)

    # Apply 200 km extension (100 km in each direction)
    x_new_sw = x0 - 100
    x_new_ne = x1 + 100
    y_new_sw = y0 - 100
    y_new_ne = y1 + 100

    # Convert new corners back to lat/lon
    lat_new_sw, lon_new_sw = km_to_latlon(x_new_sw, y_new_sw, lat_sw, lon_sw)
    lat_new_ne, lon_new_ne = km_to_latlon(x_new_ne, y_new_ne, lat_sw, lon_sw)

    # Grid size in km
    dx = x_new_ne - x_new_sw
    dy = y_new_ne - y_new_sw

    # Number of points
    npoints_x = round(dx / 0.05)
    npoints_y = round(dy / 0.05)
    npoints_z = 800

    print(f'Min. points for VGGRID: {math.sqrt(npoints_x**2 + npoints_y**2):.0f}')

    return ((round(lat_new_sw,2), round(lon_new_sw,2)),
            (round(lat_new_ne,2), round(lon_new_ne,2)),
            (npoints_x, npoints_y, npoints_z))

def genRun(parameters):
    verifyFoldersExistence(parameters) # Verify that all folders exist for the files to generate
    genChildObs(parameters) # Generate the OBS file
    genGTSRCE(parameters) # Generate the GTSRCE file

    # Compute coordinates from original coordinates
    (latMin_box,lonMin_box), (_,_), (dx,dy,dz) = compute_new_grid_corners(parameters.latMin_event,
                                                                          parameters.lonMin_event,
                                                                          parameters.latMax_event,
                                                                          parameters.lonMax_event)

    # Save
    lines = []

    # Region coordinates
    lines.append('CONTROL 1 54321\n')
    lines.append(f'TRANS  LAMBERT  WGS-84  {latMin_box} {lonMin_box}  42 44 0.0\n')
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
    lines.append(f'LOCGRID {dx} {dy} {dz} 0.0 0.0 -3  0.05 0.05 0.05 PROB_DENSITY SAVE\n')
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
    