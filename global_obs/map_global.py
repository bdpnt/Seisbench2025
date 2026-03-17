'''
mapGlobalBulletin_obs generates a map of all the events in GLOBAL.obs Bulletin
'''

import pygmt as pg
import pandas as pd

def genGlobalFigure(parameters):
    #---- Read OBS file
    with open(parameters.fileName,'r',encoding='utf-8') as f:
        lines = f.readlines()
    print(f"Catalog succesfully read @ {parameters.fileName}")

    events = [line.lstrip('# ').rstrip('\n').split(' ') for line in lines if (not line.startswith('###') and line.startswith('#'))]
    events_df = pd.DataFrame(events).drop(columns=[0,1,2,3,4,5,10,11,12,13,14,15,16]).rename(columns={6:'Latitude',7:'Longitude',8:'Depth',9:'Magnitude'}).astype(float)

    #---- Set Pyrenees borders
    region = [-2.25,3.5,42,44]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE="fancy+"):
        fig.basemap(region=region, projection="M6i", frame='af')
    fig.coast(water="skyblue", land='#777777', resolution='i', area_thresh='0/0/1', borders="1/0.75p,black")

    #---- Plot events
    pg.makecpt(cmap="viridis", series=[0,15,1], reverse=True)
    fig.plot(
        x=events_df.Longitude,
        y=events_df.Latitude,
        style="cc",
        size=0.03 * events_df.Magnitude,
        fill=events_df.Depth,
        cmap=True,
        transparency=30,
    )

    fig.colorbar(frame=['a5f5+lDepth [km] (events above 15 are in black)'])
    fig.savefig(parameters.figSave, dpi=300)

    print(f"Figure succesfully saved @ {parameters.figSave}")
