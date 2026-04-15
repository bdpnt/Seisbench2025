"""
plot_global_catalog_map.py
============================
Generate a PyGMT map of all events in an .obs bulletin, coloured by depth.

Usage
-----
    python global_obs/plot_global_catalog_map.py \
        --file-name obs/GLOBAL.obs \
        --fig-save  obs/MAPS/GLOBAL.pdf
"""

import argparse
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
import pygmt as pg
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MapGlobalParams:
    """
    Configuration for plotting the global catalog map.

    Attributes
    ----------
    file_name : str — path to the .obs bulletin file
    fig_save  : str — path for the output PDF figure
    """
    file_name: str
    fig_save:  str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_global_catalog_map(parameters):
    """
    Generate a PyGMT map of all events in an .obs bulletin, coloured by depth.

    Parameters
    ----------
    parameters : MapGlobalParams

    Returns
    -------
    dict with key: output
    """
    with open(parameters.file_name, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f'Catalog successfully read @ {parameters.file_name}')

    events = [
        line.lstrip('# ').rstrip('\n').split(' ')
        for line in lines
        if not line.startswith('###') and line.startswith('#')
    ]
    events_df = (
        pd.DataFrame(events)
        .drop(columns=[0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16])
        .rename(columns={6: 'Latitude', 7: 'Longitude', 8: 'Depth', 9: 'Magnitude'})
        .astype(float)
    )

    region = [-2.25, 3.5, 42, 44]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE="fancy+"):
        fig.basemap(region=region, projection="M6i", frame='af')
    fig.coast(water="skyblue", land='#777777', resolution='i',
              area_thresh='0/0/1', borders="1/0.75p,black")

    pg.makecpt(cmap="viridis", series=[0, 15, 1], reverse=True)
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
    fig.savefig(parameters.fig_save, dpi=300)
    plt.close('all')

    print(f'Figure successfully saved @ {parameters.fig_save}')
    return {'output': parameters.fig_save}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate a PyGMT map of all events in an .obs bulletin.'
    )
    parser.add_argument('--file-name', required=True, help='Input .obs bulletin file')
    parser.add_argument('--fig-save',  required=True, help='Output PDF figure path')
    args = parser.parse_args()

    params = MapGlobalParams(file_name=args.file_name, fig_save=args.fig_save)
    plot_global_catalog_map(params)


if __name__ == '__main__':
    main()
