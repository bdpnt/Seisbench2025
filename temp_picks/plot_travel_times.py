"""
plot_travel_times.py
============================
Overlay observed picks from a bulletin on top of the theoretical P/S
travel-time bands, producing a two-panel figure for visual quality control.

For each pick in the bulletin the script computes:
  - epicentral distance (km)  : haversine between event epicenter and station
  - observed travel time (s)  : pick arrival time − event origin time

These are plotted as a scatter on top of the theoretical band from the CSV.

Usage
-----
    # All defaults
    python temp_picks/plot_travel_times.py

    # Custom paths
    python temp_picks/plot_travel_times.py \\
        --tables    temp_picks/tables_Pyr.csv \\
        --bulletin  obs/GLOBAL.obs \\
        --inventory stations/GLOBAL_inventory.xml \\
        --output    temp_picks/figures/travel_times_observed.png
"""

import argparse
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Ensure project root is on sys.path so package imports work when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from temp_picks.match_picks import (
    load_bulletin,
    load_inventory,
    haversine_km,
    parse_pick_line,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_DEFAULT_TABLES    = os.path.join(_MODULE_DIR,    'tables_Pyr.csv')
_DEFAULT_BULLETIN  = os.path.join(_PROJECT_ROOT,  'obs', 'GLOBAL.obs')
_DEFAULT_INVENTORY = os.path.join(_PROJECT_ROOT,  'stations', 'GLOBAL_inventory.xml')
_DEFAULT_OUTPUT    = os.path.join(_MODULE_DIR,    'figures', 'travel_times_observed.png')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_travel_times(tables_file, bulletin_file, inventory_file, output_path):
    """
    Generate a two-panel P/S travel-time figure with observed picks overlaid.

    Parameters
    ----------
    tables_file    : str — path to the theoretical travel-time CSV
    bulletin_file  : str — path to the bulletin (GLOBAL.obs format)
    inventory_file : str — path to the StationXML inventory
    output_path    : str — path for the saved PNG figure
    """
    # --- Load data ---
    print(f"Loading tables     : {tables_file}")
    tables = pd.read_csv(tables_file)
    max_dist = tables['distance'].max()

    print(f"Loading inventory  : {inventory_file}")
    inventory = load_inventory(inventory_file)

    print(f"Loading bulletin   : {bulletin_file}")
    _, events = load_bulletin(bulletin_file)
    print(f"  {len(events)} events loaded.")

    # --- Collect observed (distance, travel_time) per phase ---
    p_dist, p_tt = [], []
    s_dist, s_tt = [], []
    n_skipped = 0

    for event in events:
        for pick_line in event.picks:
            try:
                station_code, phase, arrival_dt = parse_pick_line(pick_line)
            except ValueError:
                n_skipped += 1
                continue

            pos = inventory.get(station_code)
            if pos is None:
                n_skipped += 1
                continue

            sta_lat, sta_lon = pos
            dist_km = haversine_km(event.lat, event.lon, sta_lat, sta_lon)
            obs_tt  = (arrival_dt - event.event_dt).total_seconds()

            if obs_tt < 0 or dist_km > max_dist:
                n_skipped += 1
                continue

            if phase == 'P':
                p_dist.append(dist_km)
                p_tt.append(obs_tt)
            elif phase == 'S':
                s_dist.append(dist_km)
                s_tt.append(obs_tt)

    print(f"  P picks: {len(p_dist)}  |  S picks: {len(s_dist)}  |  skipped: {n_skipped}")

    # --- Plot ---
    sns.set_theme(style="whitegrid")
    palette = sns.color_palette("tab10")

    fig, (ax_p, ax_s) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # Y-axis limits: use S-wave max + 20% margin for both panels (comparable scale)
    s_ymax = tables['ts_high'].max() * 1.2
    p_ymax = s_ymax

    # P-wave panel
    ax_p.scatter(p_dist, p_tt, s=0.5, color=palette[0], alpha=0.6, label='Observed picks', zorder=1, linewidths=0)
    ax_p.fill_between(
        tables['distance'], tables['tp_low'], tables['tp_high'],
        color=palette[0], alpha=0.5, label='Theoretical band', zorder=2
    )
    ax_p.set_ylim(0, p_ymax)
    ax_p.set_ylabel('Travel time (s)')
    ax_p.set_title('P-wave arrivals')
    ax_p.legend(markerscale=6, loc='upper left')

    # S-wave panel
    ax_s.scatter(s_dist, s_tt, s=0.5, color=palette[1], alpha=0.6, label='Observed picks', zorder=1, linewidths=0)
    ax_s.fill_between(
        tables['distance'], tables['ts_low'], tables['ts_high'],
        color=palette[1], alpha=0.5, label='Theoretical band', zorder=2
    )
    ax_s.set_ylim(0, s_ymax)
    ax_s.set_xlabel('Epicentral distance (km)')
    ax_s.set_ylabel('Travel time (s)')
    ax_s.set_title('S-wave arrivals')
    ax_s.legend(markerscale=6, loc='upper left')

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"Figure saved to    : {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Plot theoretical travel-time bands with observed pick scatter.'
    )
    parser.add_argument('--tables',    default=_DEFAULT_TABLES,    help='Theoretical travel-time CSV')
    parser.add_argument('--bulletin',  default=_DEFAULT_BULLETIN,  help='Bulletin file (GLOBAL.obs format)')
    parser.add_argument('--inventory', default=_DEFAULT_INVENTORY, help='StationXML inventory file')
    parser.add_argument('--output',    default=_DEFAULT_OUTPUT,    help='Output PNG path')
    args = parser.parse_args()

    plot_travel_times(args.tables, args.bulletin, args.inventory, args.output)


if __name__ == '__main__':
    main()
