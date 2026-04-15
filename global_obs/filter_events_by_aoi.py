"""
filter_events_by_aoi.py
============================
Remove events outside the catalog-specific Area of Interest (AOI) from .obs
bulletins, and save a PyGMT map of the remaining events.

The AOI boundary is a straight line in lat/lon space; events on the wrong side
are discarded.  Additional north/south bounds are applied to the whole Pyrenees
region regardless of source.

Usage
-----
    python global_obs/filter_events_by_aoi.py \
        --file-names obs/RESIF_20-25.obs obs/IGN_20-25.obs \
        --fig-saves  obs/MAPS/RESIF_20-25.pdf obs/MAPS/IGN_20-25.pdf
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import List

import pandas as pd
import pygmt as pg


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class UpdateAOIParams:
    """
    Configuration for AOI filtering.

    Attributes
    ----------
    file_names : List[str] — paths to the .obs bulletin files to filter
    fig_saves  : List[str] — paths for the output PDF figures (one per file)
    """
    file_names: List[str] = field(default_factory=list)
    fig_saves:  List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _which_line_coords(name):
    """
    Return the boundary line coordinates and AOI direction for a named source catalog.

    Parameters
    ----------
    name : str — file path or name containing a source identifier

    Returns
    -------
    (line_coords, aoi_above) : (list of (lat, lon) or None, bool or None)
    """
    if 'RESIF' in name:
        return [(43, -2.25), (42, 2.25)], True
    elif 'IGN' in name or 'ICGC' in name:
        return [(43.75, -2.25), (42, 6.25)], False
    else:
        return None, None


def _is_in_aoi(lat, lon, line_coords, aoi_above=True):
    """
    Return True if the point (lat, lon) is on the correct side of the boundary line.

    Uses the cross product to determine which side of the line the point lies on.

    Parameters
    ----------
    lat        : float
    lon        : float
    line_coords: list of two (lat, lon) tuples defining the boundary line
    aoi_above  : bool — True means the AOI is above (cross < 0 side) the line
    """
    y, x     = lat, lon
    y1, x1   = line_coords[0]
    y2, x2   = line_coords[1]
    cross    = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    return cross < 0 if aoi_above else cross > 0


def _frame_update_in_aoi(frame, line_coords, aoi_above=True):
    """
    Add an inAOI boolean column to a DataFrame flagging events inside the AOI.

    Parameters
    ----------
    frame       : pd.DataFrame with Latitude and Longitude columns
    line_coords : list of two (lat, lon) tuples, or None (no primary boundary)
    aoi_above   : bool
    """
    if line_coords is not None:
        frame['inAOI'] = frame.apply(
            lambda row: _is_in_aoi(row.Latitude, row.Longitude, line_coords, aoi_above=aoi_above),
            axis=1,
        )
    else:
        frame['inAOI'] = True

    frame['inAOI'] = frame.apply(
        lambda row: row.inAOI and _is_in_aoi(
            row.Latitude, row.Longitude, [(44, -0.25), (43.25, 3.5)], aoi_above=False
        ),
        axis=1,
    )
    frame['inAOI'] = frame.apply(
        lambda row: row.inAOI and _is_in_aoi(
            row.Latitude, row.Longitude, [(42.5, -2.25), (42, 0.25)], aoi_above=True
        ),
        axis=1,
    )
    return frame


def _remove_outside_aoi(file_name, fig_save):
    """
    Remove events outside the catalog-specific AOI from an .obs file and save a map.

    Parameters
    ----------
    file_name : str — path to the .obs bulletin file (updated in-place)
    fig_save  : str — path for the output PDF figure
    """
    line_coords, aoi_above = _which_line_coords(file_name)

    region = [-2.25, 3.5, 42, 44]

    fig = pg.Figure()
    with pg.config(MAP_FRAME_TYPE="fancy+"):
        fig.basemap(region=region, projection="M6i", frame='af')
    fig.coast(water="skyblue", land='#777777', resolution='i',
              area_thresh='0/0/1', borders="1/0.75p,black")

    with open(file_name, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f'Catalog successfully read @ {file_name}')

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

    events_df     = _frame_update_in_aoi(events_df, line_coords, aoi_above=aoi_above)
    events_in     = events_df[events_df.inAOI]
    events_out    = events_df[~events_df.inAOI]

    if events_out.empty:
        print(f'No outside AOI events found in Catalog @ {file_name}\n')
    else:
        fig.plot(
            x=events_out.Longitude,
            y=events_out.Latitude,
            style="cc",
            size=0.03 * events_out.Magnitude,
            fill="white",
            transparency=75,
        )

    pg.makecpt(cmap="viridis", series=[0, 15, 1], reverse=True)
    fig.plot(
        x=events_in.Longitude,
        y=events_in.Latitude,
        style="cc",
        size=0.03 * events_in.Magnitude,
        fill=events_in.Depth,
        cmap=True,
        transparency=30,
    )

    fig.colorbar(frame=['a5f5+lDepth [km] (events above 15 are in black)'])
    fig.savefig(fig_save, dpi=300)

    print(f'Figure successfully saved @ {fig_save}')

    events_df['ID'] = [idx for idx, line in enumerate(lines) if line.startswith('# ')]

    new_lines = []
    for idx, line in enumerate(lines):
        if line.startswith('###') or line.startswith('\n'):
            new_lines.append(line)
        elif line.startswith('# ') and events_df.loc[events_df.ID == idx, 'inAOI'].values[0]:
            i = idx
            while not lines[i].startswith('\n'):
                new_lines.append(lines[i])
                i += 1
        elif line.startswith('# '):
            new_lines.pop(-1)

    with open(file_name, 'w') as f:
        f.writelines(new_lines)
    print(f'Catalog successfully saved @ {file_name}\n')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_events_by_aoi(parameters):
    """
    Apply AOI filtering to all source bulletin files listed in parameters.

    Parameters
    ----------
    parameters : UpdateAOIParams

    Returns
    -------
    dict
        'output'    — list of file paths processed
        'fig_saves' — list of figure paths produced
    """
    print('\n#######\n')
    for idx, file_name in enumerate(parameters.file_names):
        _remove_outside_aoi(file_name, parameters.fig_saves[idx])
    print('#######\n')
    return {'output': parameters.file_names, 'fig_saves': parameters.fig_saves}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Filter .obs bulletins to the Pyrenees AOI and save maps.'
    )
    parser.add_argument('--file-names', nargs='+', required=True,
                        help='Paths to the .obs bulletin files to filter')
    parser.add_argument('--fig-saves',  nargs='+', required=True,
                        help='Output PDF figure paths (one per file)')
    args = parser.parse_args()

    params = UpdateAOIParams(file_names=args.file_names, fig_saves=args.fig_saves)
    filter_events_by_aoi(params)


if __name__ == '__main__':
    main()
