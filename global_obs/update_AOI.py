'''
updateBulletinAOI_obs removes events outside the area of interest for RESIF, IGN
and ICGC Bulletins.
'''

import pygmt as pg
from math import cos, sin, radians
import pandas as pd

def whichLineCoords(name):
    if name.__contains__('RESIF'):
        return [(43, -2.25),(42, 2.25)], True
    elif name.__contains__('IGN') or name.__contains__('ICGC'):
        return [(43.75, -2.25),(42, 6.25)], False
    else:
        return None,None

def is_inAOI(lat, lon, lineCoords, AOI_above=True):
    """
    Returns True if the point (lat, lon) is above/below the line defined by coords1 and coords2.
    """
    y, x = lat, lon
    y1, x1 = lineCoords[0]
    y2, x2 = lineCoords[1]

    # Cross product to determine the side of the line
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)

    if AOI_above:
        return cross < 0
    else:
        return cross > 0

def frameUpdate_inAOI(frame, lineCoords, AOI_above=True):
    # Find events outside of AOI
    if lineCoords is not None:
        frame['inAOI'] = frame.apply(lambda row: is_inAOI(row.Latitude, row.Longitude, lineCoords, AOI_above=AOI_above), axis=1)
    else:
        frame['inAOI'] = True

    # Find events too far from Pyrenees (North and South)
    frame['inAOI'] = frame.apply(lambda row: row.inAOI and is_inAOI(row.Latitude, row.Longitude, [(44, -0.25),(43.25, 3.5)], AOI_above=False), axis=1)
    frame['inAOI'] = frame.apply(lambda row: row.inAOI and is_inAOI(row.Latitude, row.Longitude, [(42.5, -2.25),(42, 0.25)], AOI_above=True), axis=1)

    return frame

def remove_outsideAOI(fileName, figSave):
    #---- Retrieve AOI line coordinates
    lineCoords, AOI_above = whichLineCoords(fileName)

    #---- Set Pyrenees borders
    region = [-2.25,3.5,42,44]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE="fancy+"):
        fig.basemap(region=region, projection="M6i", frame='af')
    fig.coast(water="skyblue", land='#777777', resolution='i', area_thresh='0/0/1', borders="1/0.75p,black")

    #---- Read OBS file
    with open(fileName,'r',encoding='utf-8') as f:
        lines = f.readlines()
    print(f"Catalog succesfully read @ {fileName}")

    events = [line.lstrip('# ').rstrip('\n').split(' ') for line in lines if (not line.startswith('###') and line.startswith('#'))]
    events_df = pd.DataFrame(events).drop(columns=[0,1,2,3,4,5,10,11,12,13,14,15,16]).rename(columns={6:'Latitude',7:'Longitude',8:'Depth',9:'Magnitude'}).astype(float)

    #---- Determine events outside AOI
    events_df = frameUpdate_inAOI(events_df, lineCoords, AOI_above=AOI_above)
    events_inAOI = events_df[events_df.inAOI]
    events_notInAOI = events_df[~events_df.inAOI]

    if events_notInAOI.empty:
        print(f"No outside AOI events found in Catalog @ {fileName}\n")
    else:
        fig.plot(
            x=events_notInAOI.Longitude,
            y=events_notInAOI.Latitude,
            style="cc",
            size=0.03 * events_notInAOI.Magnitude,
            fill="white",
            transparency=75,
        )

    pg.makecpt(cmap="viridis", series=[0,15,1], reverse=True)
    fig.plot(
        x=events_inAOI.Longitude,
        y=events_inAOI.Latitude,
        style="cc",
        size=0.03 * events_inAOI.Magnitude,
        fill=events_inAOI.Depth,
        cmap=True,
        transparency=30,
    )

    fig.colorbar(frame=['a5f5+lDepth [km] (events above 15 are in black)'])
    fig.savefig(figSave, dpi=300)

    print(f"Figure succesfully saved @ {figSave}")

    #---- Update the OBS
    events_df['ID'] = [id for id,line in enumerate(lines) if line.startswith('# ')]

    newLines = []
    for id, line in enumerate(lines):
        if line.startswith('###') or line.startswith('\n'):
            newLines.append(line)
        elif line.startswith('# ') and events_df.loc[events_df.ID == id, 'inAOI'].values[0]:
            i = id
            while not lines[i].startswith('\n'):
                newLines.append(lines[i])
                i += 1
        elif line.startswith('# '):
            newLines.pop(-1) # remove the last '\n' so they are not multiple between events
    
    with open(fileName, 'w') as f:
        f.writelines(newLines)
    print(f"Catalog succesfully saved @ {fileName}\n")

def updateBulletins(parameters):
    print('\n#######\n')
    for id,fileName in enumerate(parameters.fileNames):
        remove_outsideAOI(fileName, parameters.figSaves[id])
    print('#######\n')
