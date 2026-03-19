'''
depth_maps generates maps for ERH and ERV after an NLL run, using a result file
'''

import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.append(parent_dir)

from parameters import Parameters
import pandas as pd
from obspy import UTCDateTime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from multiprocessing import Pool,cpu_count


# FUNCTION
def readFile(file):
    with open(file,'r') as f:
        lines = f.readlines()
    
    events = []
    for line in lines:
        infos = line.split()

        year = '19' + infos[0].rjust(2,'0') if float(infos[0]) > 75 else '20' + infos[0].rjust(2,'0')
        month = infos[1]
        day = infos[2]
        date = UTCDateTime(f'{year}-{month}-{day}T00:00:00.00Z')
        latitude = float(infos[6])
        longitude = float(infos[7])
        depth = float(infos[8])

        events.append([date,latitude,longitude,depth])

    events_df = pd.DataFrame(events, columns=['date','latitude','longitude','depth'])
    events_df['time'] = events_df['date'].apply(lambda x: pd.Timestamp(x.datetime))

    return events_df

def filteredDates(events, time_range):
    filtered_events = {}

    start_year = 1976
    end_year = 2026

    for period_start in range(start_year, end_year, time_range):
        period_end = period_start + 4

        start_date = pd.Timestamp(f"{period_start}-01-01")
        end_date = pd.Timestamp(f"{period_end}-12-31")

        mask = (events['time'] >= start_date) & (events['time'] <= end_date)
        filtered_events[f"{period_start}-{period_end}"] = events[mask]

    return filtered_events

def addSubplot(events,ax,type):
    # Limits for the depth colorbar (in km)
    vmin = 0
    vmax = 25

    # Define limits and number of bins for the grid
    # lat_min, lat_max = events['latitude'].min(), events['latitude'].max()
    # lon_min, lon_max = events['longitude'].min(), events['longitude'].max()
    lat_min, lat_max = 42.0, 44.0
    lon_min, lon_max = -2.25, 3.5
    bins_lat = 400
    bins_lon = 860

    # 2D grid for coordinates
    lat_edges = np.linspace(lat_min, lat_max, bins_lat + 1)
    lon_edges = np.linspace(lon_min, lon_max, bins_lon + 1)

    # Initialize the output grid
    median = np.zeros((bins_lat, bins_lon))
    count = np.zeros((bins_lat, bins_lon), dtype=int)

    # Window size for overlap (±1 bin = 9 cells)
    window_size = 4

    # Compute median for each cell using a sliding window
    for i in range(bins_lat):
        for j in range(bins_lon):
            # Define the window boundaries
            lat_low = max(lat_edges[i] - window_size * (lat_edges[1] - lat_edges[0]), lat_min)
            lat_high = min(lat_edges[i+1] + window_size * (lat_edges[1] - lat_edges[0]), lat_max)
            lon_low = max(lon_edges[j] - window_size * (lon_edges[1] - lon_edges[0]), lon_min)
            lon_high = min(lon_edges[j+1] + window_size * (lon_edges[1] - lon_edges[0]), lon_max)

            # Select points within the window
            mask = (
                (events['latitude'] >= lat_low) &
                (events['latitude'] <= lat_high) &
                (events['longitude'] >= lon_low) &
                (events['longitude'] <= lon_high)
            )
            window_data = events[mask]

            # Compute median for the window
            if len(window_data) > 0:
                median[i, j] = np.median(window_data[type.lower()])
                count[i, j] = len(window_data)
            else:
                median[i, j] = np.nan
                count[i, j] = 0

    # Mask for the slots with less than 10 values
    mask = count < 10
    median_masked = np.ma.masked_where(mask, median)

    # Add plots
    mesh = ax.pcolormesh(
        lon_edges,
        lat_edges,
        median_masked,
        vmax=vmax,
        vmin=vmin,
        cmap="rocket_r",
        shading='auto',
        alpha=0.9,
    )

    sns.scatterplot(
        x=events['longitude'],
        y=events['latitude'],
        s=0.6,
        color='black',
        linewidth=0,
        ax=ax,
    )

    ax.text(
        0.99, 0.98, f"Mean Depth: {np.nanmean(events[type.lower()]):.1f}\nMax Depth: {np.nanmax(events[type.lower()]):.1f}" +
        f"\nStd Depth: {np.nanstd(events[type.lower()]):.1f}\nQ99 Depth: {np.nanquantile(events[type.lower()],0.99):.1f}",
        transform=ax.transAxes,
        fontweight='bold', color='black', fontsize=8,
        ha='right', va='top',
    )

    ax.text(
        0.01, 0.98, type,
        transform=ax.transAxes,
        fontweight='bold', color='black',
        ha='left', va='top',
    )

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    return mesh

def generate_plot(args, mapFolder):
    date, df = args
    fig, axes = plt.subplots(1, 1, figsize=(12, 6), layout='constrained')
    mesh = addSubplot(df, axes, type='DEPTH')

    fig.colorbar(mesh, ax=axes, label='Median depth (km) - 3x3 grid', shrink=0.7, pad=0.025, aspect=50)
    plt.suptitle(f"Depth map\n{date}", fontweight='bold')

    plt.savefig(f"{mapFolder + date}.pdf")
    plt.close()

def genFigure(params):
    events = readFile(params.file)
    events_filtered = filteredDates(events, params.time_range)

    args_list = list(events_filtered.items())
    args_list_map = [(args, params.mapFolder) for args in args_list]

    n_cores = int(cpu_count() / 1.5)
    print(f"Using {n_cores}/{cpu_count()} CPU cores")

    with Pool(processes=n_cores) as pool:
        pool.starmap(generate_plot, args_list_map)

    print(f'Succesfully saved figures @ {params.mapFolder}')

# MAIN
if __name__ == '__main__':
    params = Parameters(
        file = 'RESULT/GLOBAL_PR_TEST.txt',
        mapFolder = 'RESULT/MAPS/DEPTHS/',
        time_range = 5, # in years
    )
    
    genFigure(params)
