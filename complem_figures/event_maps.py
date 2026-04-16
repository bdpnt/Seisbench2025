"""
event_maps.py
============================
Generate a PyGMT map of seismic events coloured by depth.

Reads a .txt (NLL result) or .obs bulletin, filters high-error events, and
plots each event on a Pyrenees basemap coloured by depth. Optionally overlays
station positions and zone-boundary rectangles.

Usage
-----
    python complem_figures/event_maps.py \\
        --bulletin  obs/FINAL.obs \\
        --output    complem_figures/event_maps/FINAL.pdf
"""

import argparse
import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pygmt as pg

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EventMapsParams:
    fileBulletin: str
    figSave:      str
    fileStations: Optional[str]  = None
    region_in:    Optional[list] = None
    region_out:   Optional[list] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _remove_high_err(df):
    """Filter out events with location errors or quality metrics above thresholds."""
    df = df[df.erh <= 3.0]
    df = df[df.erv <= 3.0]
    df = df[df.gap <= 300]
    df = df[df.rms <= 0.5]
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_figure(parameters):
    """
    Read a .txt or .obs bulletin, filter high-error events, and save a
    PyGMT map coloured by depth.

    Parameters
    ----------
    parameters : EventMapsParams

    Returns
    -------
    dict with keys: output
    """
    ext = parameters.fileBulletin.split('.')[-1]

    if ext == 'txt':
        with open(parameters.fileBulletin, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        print(f"Catalog read @ {parameters.fileBulletin}")
        events = [line.split() for line in lines]
        events_df = (
            pd.DataFrame(events)
            .drop(columns=[0, 1, 2, 3, 4, 5, 11])
            .rename(columns={6: 'Latitude', 7: 'Longitude', 8: 'Depth',
                              9: 'Magnitude', 10: 'rms', 12: 'erh',
                              13: 'erv', 14: 'gap'})
            .astype(float)
        )
        events_df = _remove_high_err(events_df)

    elif ext == 'obs':
        with open(parameters.fileBulletin, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        print(f"Catalog read @ {parameters.fileBulletin}")
        events = [line.lstrip('# ').rstrip('\n').split()
                  for line in lines if line.startswith('# ')]
        events_df = (
            pd.DataFrame(events)
            .drop(columns=[0, 1, 2, 3, 4, 5, 10, 11, 12])
            .rename(columns={6: 'Latitude', 7: 'Longitude', 8: 'Depth',
                              9: 'Magnitude', 13: 'erh', 14: 'erv',
                              15: 'gap', 16: 'rms'})
            .astype(float)
        )
        events_df = _remove_high_err(events_df)

    else:
        print(f'Unsupported format (expected "txt" or "obs"): {parameters.fileBulletin}')
        return {'output': None}

    region = [-4.0, 4, 41, 45]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE='fancy+'):
        fig.basemap(region=region, projection='M6i', frame='af')
    fig.coast(water='skyblue', land='#777777', resolution='i',
              area_thresh='0/0/1', borders='1/0.75p,black')

    if parameters.region_out:
        ro = parameters.region_out
        fig.plot(
            x=[ro[0][1], ro[1][1], ro[1][1], ro[0][1], ro[0][1]],
            y=[ro[0][0], ro[0][0], ro[1][0], ro[1][0], ro[0][0]],
            close=True, pen='2p,red', transparency=50,
        )

    if parameters.region_in:
        ri = parameters.region_in
        fig.plot(
            x=[ri[0][1], ri[1][1], ri[1][1], ri[0][1], ri[0][1]],
            y=[ri[0][0], ri[0][0], ri[1][0], ri[1][0], ri[0][0]],
            close=True, pen='0.5p,blue', fill='blue', transparency=85,
        )

    if parameters.fileStations:
        stations = pd.read_csv(
            parameters.fileStations, header=0, delimiter=' ',
            names=['Code', 'x', 'y', 'z', 'Latitude', 'Longitude', 'Depth'],
        ).drop(columns=['x', 'y', 'z'])
        fig.plot(x=stations.Longitude, y=stations.Latitude,
                 style='i0.1c', fill='black', transparency=40)

    pg.makecpt(cmap='viridis', series=[0, 15, 1], reverse=True)
    fig.plot(
        x=events_df.Longitude,
        y=events_df.Latitude,
        style='c0.02c',
        fill=events_df.Depth,
        cmap=True,
        transparency=15,
    )

    fig.colorbar(frame=['a5f5+lDepth [km] (events above 15 are in black)'])
    fig.savefig(parameters.figSave, dpi=300)

    print(f"Figure saved @ {parameters.figSave}")
    return {'output': parameters.figSave}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate a PyGMT depth-coloured event map.'
    )
    parser.add_argument('--bulletin',  required=True,
                        help='Input bulletin file (.txt NLL result or .obs)')
    parser.add_argument('--output',    required=True,
                        help='Output figure path (PDF or PNG)')
    parser.add_argument('--stations',  default=None,
                        help='Optional last.stations file to overlay station positions')
    args = parser.parse_args()

    generate_figure(EventMapsParams(
        fileBulletin = args.bulletin,
        figSave      = args.output,
        fileStations = args.stations,
    ))


if __name__ == '__main__':
    main()
