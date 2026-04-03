'''
postRunClean removes unnecessary files after an NLL run, and generates the
final NLL result file. It also generates a map of the events.
'''

import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.append(parent_dir)

from dataclasses import dataclass, field
from typing import Optional
import pygmt as pg
import pandas as pd

@dataclass
class EventMapsParams:
    fileBulletin: str
    figSave: str
    fileStations: Optional[str] = None
    region_in: Optional[list] = None
    region_out: Optional[list] = None

# FUNCTION
def removeHighErr(df):
    """Filter out events with location errors or quality metrics above acceptable thresholds."""
    df = df[df.erh <= 3.0]
    df = df[df.erv <= 3.0]
    df = df[df.gap <= 300]
    df = df[df.rms <= 0.5]
    return df

def genFigure(parameters):
    """Read a .txt or .obs bulletin, filter high-error events, and save a PyGMT map coloured by depth."""
    #---- Read OBS file
    if parameters.fileBulletin.split('.')[-1] == "txt":
        with open(parameters.fileBulletin,'r',encoding='utf-8') as f:
            lines = f.readlines()
        print(f"Catalog succesfully read @ {parameters.fileBulletin}")

        events = [event.split() for event in lines]
        events_df = pd.DataFrame(events).drop(columns=[0,1,2,3,4,5,11]).rename(columns={6:'Latitude',7:'Longitude',8:'Depth',9:'Magnitude',10:'rms',12:'erh',13:'erv',14:'gap'})\
            .astype(float)
        events_df = removeHighErr(events_df)

    elif parameters.fileBulletin.split('.')[-1] == "obs":
        with open(parameters.fileBulletin,'r',encoding='utf-8') as f:
            lines = f.readlines()

        print(f"Catalog succesfully read @ {parameters.fileBulletin}")

        events = [line.lstrip('# ').rstrip('\n').split() for line in lines if line.startswith('# ')]
        events_df = pd.DataFrame(events).drop(columns=[0,1,2,3,4,5,10,11,12]).rename(columns={6:'Latitude',7:'Longitude',8:'Depth',9:'Magnitude',13:'erh',14:'erv',15:'gap',16:'rms'})\
            .astype(float)
        events_df = removeHighErr(events_df)
    else:
        print(f'File is not in a compatible format ("txt"/"obs"): {parameters.fileBulletin}')
        return

    #---- Set Pyrenees borders
    region = [-4.0,4,41,45]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE="fancy+"):
        fig.basemap(region=region, projection="M6i", frame='af')
    fig.coast(water="skyblue", land='#777777', resolution='i', area_thresh='0/0/1', borders="1/0.75p,black")

    #---- Plot rectangles
    if parameters.region_out:
        fig.plot(
            x=[parameters.region_out[0][1], parameters.region_out[1][1], parameters.region_out[1][1], parameters.region_out[0][1], parameters.region_out[0][1]],
            y=[parameters.region_out[0][0], parameters.region_out[0][0], parameters.region_out[1][0], parameters.region_out[1][0], parameters.region_out[0][0]],
            close=True,
            pen="2p,red",
            transparency=50,
        )

    if parameters.region_in:
        fig.plot(
            x=[parameters.region_in[0][1], parameters.region_in[1][1], parameters.region_in[1][1], parameters.region_in[0][1], parameters.region_in[0][1]],
            y=[parameters.region_in[0][0], parameters.region_in[0][0], parameters.region_in[1][0], parameters.region_in[1][0], parameters.region_in[0][0]],
            close=True,
            pen="0.5p,blue",
            fill="blue",
            transparency=85,
        )
    
    #---- Plot stations
    if parameters.fileStations:
        # Read last.stations file
        stations = pd.read_csv(parameters.fileStations, header=0, delimiter=' ', names=['Code','x','y','z','Latitude','Longitude','Depth']).drop(columns=['x','y','z'])

        # Plot
        fig.plot(
            x=stations.Longitude,
            y=stations.Latitude,
            style="i0.1c",
            fill='black',
            transparency=40,
        )

    #---- Plot events
    pg.makecpt(cmap="viridis", series=[0,15,1], reverse=True)
    fig.plot(
        x=events_df.Longitude,
        y=events_df.Latitude,
        style="c0.02c",
        # size=1 * events_df.Magnitude, # the Magnitude is 0 for all
        fill=events_df.Depth,
        cmap=True,
        transparency=15,
    )

    fig.colorbar(frame=['a5f5+lDepth [km] (events above 15 are in black)'])
    fig.savefig(parameters.figSave, dpi=300)

    print(f"Figure succesfully saved @ {parameters.figSave}")


# MAIN
if __name__ == "__main__":
    all_runs = {
        "1": ("RESULT/GLOBAL_1.txt", "loc/GLOBAL_1/last.stations", "complem_figures/event_maps/GLOBAL_1.pdf",
              ((42.50, -2.00), (43.50, -0.75)), ((41.60, -3.22), (44.40, 0.46))),
        "2": ("RESULT/GLOBAL_2.txt", "loc/GLOBAL_2/last.stations", "complem_figures/event_maps/GLOBAL_2.pdf",
              ((42.50, -1.00), (43.25, 0.50)), ((41.60, -2.22), (44.15, 1.71))),
        "3": ("RESULT/GLOBAL_3.txt", "loc/GLOBAL_3/last.stations", "complem_figures/event_maps/GLOBAL_3.pdf",
              ((42.00, 0.25), (43.25, 1.00)), ((41.10, -0.96), (44.15, 2.20))),
        "4": ("RESULT/GLOBAL_4.txt", "loc/GLOBAL_4/last.stations", "complem_figures/event_maps/GLOBAL_4.pdf",
              ((42.00, 0.75), (43.00, 2.25)), ((41.10, -0.46), (43.90, 3.45))),
        "5": ("RESULT/GLOBAL_5.txt", "loc/GLOBAL_5/last.stations", "complem_figures/event_maps/GLOBAL_5.pdf",
              ((42.00, 2.00), (43.00, 3.50)), ((41.10, 0.79), (43.90, 4.70))),
        "6": ("RESULT/GLOBAL_6.txt", "loc/GLOBAL_6/last.stations", "complem_figures/event_maps/GLOBAL_6.pdf",
              ((42.75, 2.25), (43.75, 3.50)), ((41.85, 1.03), (44.65, 4.75))),
        "Final": ("obs/FINAL.obs", None, "complem_figures/event_maps/FINAL.pdf",
                  None, None),
    }

    for key,item in all_runs.items():
        params = EventMapsParams(
            fileBulletin = item[0],
            fileStations = item[1],
            figSave = item[2],
            region_in = item[3],
            region_out = item[4],
        )

        genFigure(params)