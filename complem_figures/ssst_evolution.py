"""
ssst_evolution.py
============================
Plot the per-event evolution of location-error proxies across SSST iterations,
one figure per zone.

For each zone, tracks pdfVolume, EllipsoidLen3 and RMS across every SSST
iteration step (loc_ssst_corr0 ... loc_ssst_corrN, the last being the final
NLLoc-only pass). One thin line per event, colored by its net trend
(log(last/first), normalized per metric by its own 95th-percentile clip so
all three panels share one diverging colorbar), with a bold median + IQR
band overlaid.

Known limitation: above ~5,000-10,000 events per zone, individual lines
blend into a density haze rather than being individually readable -
expected, not a bug; only extreme outliers stay visually distinct.

Usage
-----
    python complem_figures/ssst_evolution.py \\
        --run-name ssst_run1 \\
        --zones 1 2 3 4 5 6 \\
        --output-dir complem_figures/ssst_evolution/
"""

import argparse
import glob
import os
import re
import warnings
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.collections import LineCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.cm import ScalarMappable

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_METRICS = ['pdfVolume', 'EllipsoidLen3', 'RMS']
_YLIM = (1e-3, 1e3)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SsstEvolutionParams:
    ssst_root:  str
    run_name:   str
    zones:      list = field(default_factory=lambda: ['1', '2', '3', '4', '5', '6'])
    output_dir: str = os.path.join(_MODULE_DIR, 'ssst_evolution')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_zone_steps(ssst_root, run_name, zone_key):
    """
    Load every SSST-iteration summary CSV for one zone into a long-format DataFrame.

    Parameters
    ----------
    ssst_root : str — path to run/ssst_loc
    run_name  : str — campaign name (e.g. 'ssst_run1')
    zone_key  : str — zone key (e.g. '1')

    Returns
    -------
    pd.DataFrame with columns: publicId, step, pdfVolume, EllipsoidLen3, RMS
        (only events present at every step for this zone)
    """
    pattern = os.path.join(
        ssst_root, run_name, f'Pyrenees_{zone_key}_SSST',
        'loc_ssst_corr*', f'GLOBAL_{zone_key}', f'Pyrenees_{zone_key}.sum.grid0.loc.csv',
    )
    files = glob.glob(pattern)
    if not files:
        return pd.DataFrame(columns=['publicId', 'step'] + _METRICS)

    frames = []
    for file in files:
        match = re.search(r'loc_ssst_corr(\d+)', file)
        step = int(match.group(1))
        df = pd.read_csv(file, skipinitialspace=True)
        df = df[['publicId'] + _METRICS].copy()
        df['step'] = step
        frames.append(df)

    long_df = pd.concat(frames, ignore_index=True)

    n_steps = long_df['step'].nunique()
    shared_ids = set.intersection(*[
        set(long_df.loc[long_df['step'] == s, 'publicId']) for s in long_df['step'].unique()
    ])
    if len(shared_ids) < long_df['publicId'].nunique():
        n_dropped = long_df['publicId'].nunique() - len(shared_ids)
        warnings.warn(
            f'Zone {zone_key}: {n_dropped} event(s) missing from at least one of the '
            f'{n_steps} SSST steps — excluding them from the evolution plot.'
        )
    long_df = long_df[long_df['publicId'].isin(shared_ids)]

    return long_df.sort_values(['publicId', 'step']).reset_index(drop=True)


def _plot_metric(ax, long_df, metric, steps):
    """
    Draw one metric's per-event evolution panel (LineCollection + median/IQR overlay).

    Parameters
    ----------
    ax      : matplotlib Axes
    long_df : pd.DataFrame — long-format data for one zone (columns: publicId, step, <metric>)
    metric  : str          — column name to plot
    steps   : list[int]    — sorted step numbers

    Returns
    -------
    matplotlib.cm.ScalarMappable — shared colormap/norm used for this panel's lines
    """
    wide = long_df.pivot(index='publicId', columns='step', values=metric)[steps]
    values = wide.to_numpy()
    n_events = values.shape[0]

    net = np.log(values[:, -1] / values[:, 0])
    clip = np.percentile(np.abs(net), 95)
    clip = clip if clip > 0 else 1.0
    norm_net = np.clip(net / clip, -1, 1)

    cmap = plt.get_cmap('coolwarm')
    norm = TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)
    line_colors = cmap(norm(norm_net))

    if n_events > 2000:
        alpha, linewidth = 0.03, 0.5
    elif n_events > 500:
        alpha, linewidth = 0.05, 0.6
    else:
        alpha, linewidth = 0.08, 0.8
    line_colors[:, 3] = alpha

    segments = np.stack([
        np.tile(steps, (n_events, 1)),
        values,
    ], axis=-1)
    lc = LineCollection(segments, colors=line_colors, linewidths=linewidth, zorder=2)
    ax.add_collection(lc)

    median = np.nanmedian(values, axis=0)
    p25 = np.nanpercentile(values, 25, axis=0)
    p75 = np.nanpercentile(values, 75, axis=0)
    ax.fill_between(steps, p25, p75, color='black', alpha=0.15, zorder=3)
    ax.plot(steps, median, color='black', linewidth=2, zorder=4)

    ax.set_xlim(steps[0], steps[-1])
    ax.set_ylim(*_YLIM)
    ax.set_yscale('log')
    ax.set_xticks(steps)
    ax.set_xticklabels([str(s) for s in steps[:-1]] + ['Final'])
    ax.set_xlabel('SSST iteration')
    ax.set_title(metric)

    pct_decrease = (net < 0).mean() * 100
    median_pct_change = (np.exp(np.median(net)) - 1) * 100
    ax.text(0.98, 0.98,
            f'N = {n_events}\n'
            f'Net decrease: {pct_decrease:.0f}%\n'
            f'Median change: {median_pct_change:+.0f}%',
            transform=ax.transAxes, ha='right', va='top',
            fontweight='bold', fontsize=8)

    return ScalarMappable(norm=norm, cmap=cmap)


def _plot_zone(long_df, zone_key, run_name, output_path):
    """Build and save the 3-panel evolution figure for one zone."""
    sns.set_theme()
    steps = sorted(long_df['step'].unique())

    fig, axes = plt.subplots(1, len(_METRICS), figsize=(6 * len(_METRICS), 6), layout='constrained')
    sm = None
    for ax, metric in zip(axes, _METRICS):
        sm = _plot_metric(ax, long_df, metric, steps)

    fig.colorbar(sm, ax=axes, orientation='horizontal', location='bottom',
                 shrink=0.4, pad=0.08, aspect=40,
                 label='Normalized net trend (clipped at 95th pct; blue=improved, red=worsened)')

    plt.suptitle(f'SSST evolution — Zone {zone_key} ({run_name})', fontweight='bold')
    plt.savefig(output_path, dpi=300)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_figure(params):
    """
    Generate and save one SSST-evolution figure per zone.

    Parameters
    ----------
    params : SsstEvolutionParams

    Returns
    -------
    dict with keys: output_dir, zones_plotted
    """
    os.makedirs(params.output_dir, exist_ok=True)

    zones_plotted = []
    for zone_key in params.zones:
        long_df = _load_zone_steps(params.ssst_root, params.run_name, zone_key)
        if long_df.empty:
            warnings.warn(f'Zone {zone_key}: no SSST output found under {params.ssst_root}/{params.run_name} — skipping.')
            continue

        output_path = os.path.join(params.output_dir, f'{params.run_name}_zone{zone_key}.png')
        _plot_zone(long_df, zone_key, params.run_name, output_path)
        zones_plotted.append(zone_key)
        print(f'Figure saved @ {output_path}')

    return {'output_dir': params.output_dir, 'zones_plotted': zones_plotted}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Plot per-event evolution of location-error proxies across SSST iterations, per zone.'
    )
    parser.add_argument('--ssst-root', default=os.path.join(_PROJECT_ROOT, 'run', 'ssst_loc'),
                        help='Root folder containing <run-name>/Pyrenees_<zone>_SSST/...')
    parser.add_argument('--run-name', default='ssst_run1',
                        help='SSST campaign name (default: ssst_run1)')
    parser.add_argument('--zones', nargs='+', default=['1', '2', '3', '4', '5', '6'],
                        help='Zone keys to plot (default: 1 2 3 4 5 6)')
    parser.add_argument('--output-dir', default=os.path.join(_MODULE_DIR, 'ssst_evolution'),
                        help='Output folder for PNG figures')
    args = parser.parse_args()

    generate_figure(SsstEvolutionParams(
        ssst_root  = args.ssst_root,
        run_name   = args.run_name,
        zones      = args.zones,
        output_dir = args.output_dir,
    ))


if __name__ == '__main__':
    main()
