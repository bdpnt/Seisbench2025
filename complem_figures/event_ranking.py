"""
event_ranking.py
============================
Rank every event by how much its location improved (or degraded) across the
full relocation pipeline: RESULT/NLL_result.csv (pre-SSST) vs
RESULT/SSST_result.csv (post-SSST, final). Ranking metric is pdfVolume, the
same metric merge_regional_results.py already uses to pick zone-overlap
winners. Flags events relocated independently in more than one of the 6
zones (info lost once merge_regional_results.py deduplicates), and events
whose winning zone changed between the two stages.

Optionally saves a whole-Pyrenees gridmap PDF of the median pdfVolume/
ellipsoidVolume change (requires matplotlib/seaborn, e.g. seisbench_env).

Usage
-----
    python complem_figures/event_ranking.py --run-name ssst_run1
    python complem_figures/event_ranking.py --run-name ssst_run1 --figures true
"""

import argparse
import glob
import os
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EventRankingParams:
    nll_result_csv:  str
    ssst_result_csv: str
    nll_loc_root:    str
    ssst_root:       str
    run_name:        str
    zones:           list = field(default_factory=lambda: ['1', '2', '3', '4', '5', '6'])
    output:          str = None
    figures:         bool = False
    metric:          str = 'pct_change'
    figure_output:   str = None
    bin_size:        float = 0.02
    min_count:       int = 10


# ---------------------------------------------------------------------------
# Helpers — raw per-zone pdfVolume loading (for multi-zone detection)
# ---------------------------------------------------------------------------

def _load_raw_zone_pdfvolumes(nll_loc_root, zones):
    """Load publicId/pdfVolume/zone from every raw (un-deduplicated) NLL per-zone CSV."""
    frames = []
    for zone in zones:
        path = os.path.join(nll_loc_root, f'GLOBAL_{zone}', f'GLOBAL_{zone}.obs.sum.grid0.loc.csv')
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, skipinitialspace=True, usecols=['publicId', 'pdfVolume'])
        df['zone'] = zone
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=['publicId', 'pdfVolume', 'zone'])
    return pd.concat(frames, ignore_index=True)


def _final_ssst_zone_csv(ssst_root, run_name, zone):
    """Return the final (highest loc_ssst_corr<N>) per-zone SSST CSV path, or None if absent."""
    pattern = os.path.join(ssst_root, run_name, f'Pyrenees_{zone}_SSST', 'loc_ssst_corr*', f'GLOBAL_{zone}')
    step_dirs = []
    for d in glob.glob(pattern):
        match = re.search(r'loc_ssst_corr(\d+)', d)
        step_dirs.append((int(match.group(1)), d))
    if not step_dirs:
        return None
    _, last_dir = max(step_dirs)
    csv_path = os.path.join(last_dir, f'Pyrenees_{zone}.sum.grid0.loc.csv')
    return csv_path if os.path.exists(csv_path) else None


def _load_ssst_final_zone_pdfvolumes(ssst_root, run_name, zones):
    """Load publicId/pdfVolume/zone from every zone's final SSST-iteration CSV."""
    frames = []
    for zone in zones:
        path = _final_ssst_zone_csv(ssst_root, run_name, zone)
        if path is None:
            continue
        df = pd.read_csv(path, skipinitialspace=True, usecols=['publicId', 'pdfVolume'])
        df['zone'] = zone
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=['publicId', 'pdfVolume', 'zone'])
    return pd.concat(frames, ignore_index=True)


def _multi_zone_table(raw_df):
    """
    Reduce a long publicId/pdfVolume/zone frame to one row per event.

    Returns
    -------
    pd.DataFrame indexed by publicId, columns: n_zones, zones (str, sorted zone list)
    """
    grouped = raw_df.groupby('publicId')['zone'].agg(lambda z: sorted(set(z)))
    return pd.DataFrame({
        'n_zones': grouped.apply(len),
        'zones': grouped.apply(lambda z: ','.join(f'GLOBAL_{v}' for v in z)),
    })


# ---------------------------------------------------------------------------
# Core ranking
# ---------------------------------------------------------------------------

def build_ranking(nll_result_csv, ssst_result_csv, nll_loc_root, ssst_root, run_name, zones):
    """
    Build the event-ranking table and the dropped-events table.

    Returns
    -------
    (ranking_df, dropped_df) : both pd.DataFrame
        ranking_df sorted ascending by log_ratio (most improved first).
        dropped_df: events present in nll_result_csv but absent from ssst_result_csv.
    """
    nll_df = pd.read_csv(nll_result_csv, skipinitialspace=True)
    ssst_df = pd.read_csv(ssst_result_csv, skipinitialspace=True)

    stage_cols = ['publicId', 'source', 'pdfVolume', 'true_erh', 'true_erz',
                  'EllipsoidLen1', 'EllipsoidLen2', 'EllipsoidLen3']
    context_cols = ['publicId', 'date-time', 'latitude', 'longitude']
    merged = nll_df[stage_cols].merge(
        ssst_df[stage_cols], on='publicId', how='inner', suffixes=('_pre', '_post')
    )
    merged = merged.merge(ssst_df[context_cols], on='publicId', how='left')

    dropped_ids = set(nll_df['publicId']) - set(ssst_df['publicId'])
    dropped_df = nll_df[nll_df['publicId'].isin(dropped_ids)][context_cols + ['source', 'pdfVolume']].copy()

    merged['log_ratio'] = np.log(merged['pdfVolume_post'] / merged['pdfVolume_pre'])
    merged['pct_change'] = (merged['pdfVolume_post'] / merged['pdfVolume_pre'] - 1) * 100

    # Gaussian-ellipsoid volume from the confidence-ellipsoid semi-axes, for comparison against
    # pdfVolume (NLLoc's OCT-tree-integrated, possibly non-Gaussian PDF volume) — the two can
    # diverge a lot for poorly-constrained/non-Gaussian events. Informational only.
    for suffix in ('_pre', '_post'):
        merged[f'ellipsoidVolume{suffix}'] = (
            4 / 3 * np.pi
            * merged[f'EllipsoidLen1{suffix}'] * merged[f'EllipsoidLen2{suffix}'] * merged[f'EllipsoidLen3{suffix}']
        )

    raw_nll = _load_raw_zone_pdfvolumes(nll_loc_root, zones)
    raw_ssst = _load_ssst_final_zone_pdfvolumes(ssst_root, run_name, zones)
    multi_pre = _multi_zone_table(raw_nll).add_suffix('_pre')
    multi_post = _multi_zone_table(raw_ssst).add_suffix('_post')

    merged = merged.merge(multi_pre, left_on='publicId', right_index=True, how='left')
    merged = merged.merge(multi_post, left_on='publicId', right_index=True, how='left')
    merged[['n_zones_pre', 'n_zones_post']] = merged[['n_zones_pre', 'n_zones_post']].fillna(1).astype(int)
    merged['zones_pre'] = merged['zones_pre'].fillna(merged['source_pre'])
    merged['zones_post'] = merged['zones_post'].fillna(merged['source_post'])

    merged['multi_zone'] = (merged['n_zones_pre'] > 1) | (merged['n_zones_post'] > 1)
    merged['zone_changed'] = merged['source_pre'] != merged['source_post']

    merged = merged.sort_values('log_ratio').reset_index(drop=True)

    ordered_cols = [
        'publicId', 'date-time', 'latitude', 'longitude',
        'source_pre', 'source_post', 'pdfVolume_pre', 'pdfVolume_post',
        'log_ratio', 'pct_change', 'true_erh_pre', 'true_erh_post',
        'true_erz_pre', 'true_erz_post',
        'ellipsoidVolume_pre', 'ellipsoidVolume_post',
        'n_zones_pre', 'zones_pre', 'n_zones_post', 'zones_post',
        'multi_zone', 'zone_changed',
    ]
    return merged[ordered_cols], dropped_df


# ---------------------------------------------------------------------------
# Gridmap
# ---------------------------------------------------------------------------

# Whole-Pyrenees domain, matching complem_figures/error_maps.py and depth_maps.py.
_LAT_MIN, _LAT_MAX = 42.0, 44.0
_LON_MIN, _LON_MAX = -2.25, 3.5


def _metric_series(ranking_df, base_col, metric):
    """Return a post-minus-pre series for `base_col` (pdfVolume/ellipsoidVolume) under `metric`."""
    pre, post = ranking_df[f'{base_col}_pre'], ranking_df[f'{base_col}_post']
    if metric == 'pct_change':
        return (post / pre - 1) * 100
    return post - pre


def _add_gridmap_subplot(events, ax, values, label, bin_size, min_count):
    """
    Render a windowed-median diff grid and event scatter onto a matplotlib axis.

    Parameters
    ----------
    events : pd.DataFrame — events with latitude/longitude columns
    ax     : matplotlib Axes
    values : pd.Series    — per-event metric value (post - pre based), aligned with events' index
    label  : str          — panel label (e.g. 'pdfVolume')
    bin_size  : float     — grid cell size in degrees
    min_count : int       — minimum event count for a cell to be shown

    Returns
    -------
    matplotlib QuadMesh
    """
    import seaborn as sns

    bins_lat = max(int(round((_LAT_MAX - _LAT_MIN) / bin_size)), 1)
    bins_lon = max(int(round((_LON_MAX - _LON_MIN) / bin_size)), 1)

    lat_edges   = np.linspace(_LAT_MIN, _LAT_MAX, bins_lat + 1)
    lon_edges   = np.linspace(_LON_MIN, _LON_MAX, bins_lon + 1)
    median      = np.zeros((bins_lat, bins_lon))
    count       = np.zeros((bins_lat, bins_lon), dtype=int)
    window_size = 4

    lat, lon = events['latitude'], events['longitude']
    for i in range(bins_lat):
        for j in range(bins_lon):
            lat_low  = max(lat_edges[i]   - window_size * (lat_edges[1] - lat_edges[0]), _LAT_MIN)
            lat_high = min(lat_edges[i+1] + window_size * (lat_edges[1] - lat_edges[0]), _LAT_MAX)
            lon_low  = max(lon_edges[j]   - window_size * (lon_edges[1] - lon_edges[0]), _LON_MIN)
            lon_high = min(lon_edges[j+1] + window_size * (lon_edges[1] - lon_edges[0]), _LON_MAX)
            mask = (lat >= lat_low) & (lat <= lat_high) & (lon >= lon_low) & (lon <= lon_high)
            window = values[mask]
            if len(window) > 0:
                median[i, j] = np.median(window)
                count[i, j]  = len(window)
            else:
                median[i, j] = np.nan

    median_masked = np.ma.masked_where(count < min_count, median)
    vmax = np.nanpercentile(np.abs(median_masked.filled(np.nan)), 95)
    vmax = vmax if vmax > 0 else 1.0

    mesh = ax.pcolormesh(lon_edges, lat_edges, median_masked,
                         vmin=-vmax, vmax=vmax, cmap='coolwarm',
                         shading='auto', alpha=0.9)

    sns.scatterplot(x=lon, y=lat, s=0.6, color='black', linewidth=0, ax=ax)

    ax.text(0.01, 0.98, label, transform=ax.transAxes,
            fontweight='bold', color='black', ha='left', va='top')

    ax.set_xlim(_LON_MIN, _LON_MAX)
    ax.set_ylim(_LAT_MIN, _LAT_MAX)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    return mesh


def _generate_gridmap_figure(ranking_df, metric, output_path, bin_size, min_count):
    """Build and save the whole-Pyrenees pdfVolume/ellipsoidVolume gridmap PDF."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme()
    events = ranking_df[['latitude', 'longitude']]

    fig, axes = plt.subplots(2, 1, figsize=(12, 10), layout='constrained')

    pdf_values = _metric_series(ranking_df, 'pdfVolume', metric)
    ellipsoid_values = _metric_series(ranking_df, 'ellipsoidVolume', metric)

    unit = '%' if metric == 'pct_change' else 'km³'
    mesh_pdf = _add_gridmap_subplot(events, axes[0], pdf_values, 'pdfVolume', bin_size, min_count)
    mesh_ellipsoid = _add_gridmap_subplot(events, axes[1], ellipsoid_values, 'ellipsoidVolume', bin_size, min_count)

    fig.colorbar(mesh_pdf, ax=axes[0], label=f'Median pdfVolume change ({unit})', shrink=0.85, pad=0.02)
    fig.colorbar(mesh_ellipsoid, ax=axes[1], label=f'Median ellipsoidVolume change ({unit})', shrink=0.85, pad=0.02)

    plt.suptitle(f'pdfVolume / ellipsoidVolume change, pre-SSST → post-SSST\nmetric={metric}',
                 fontweight='bold')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_METRIC_SUFFIXES = {'pct_change': '_pct', 'diff': '_raw'}


def _suffixed_path(path, suffix):
    """Insert `suffix` before the file extension, e.g. ('foo.pdf', '_pct') -> 'foo_pct.pdf'."""
    root, ext = os.path.splitext(path)
    return f'{root}{suffix}{ext}'


def generate_ranking(params):
    """
    Build the event ranking, save it to CSV, and optionally save gridmap figure(s).

    Parameters
    ----------
    params : EventRankingParams
        params.metric selects 'pct_change', 'diff', or 'both' (one gridmap PDF per metric,
        filenames suffixed '_pct'/'_raw').

    Returns
    -------
    dict with keys: output_path, n_events, n_multi_zone, n_dropped
    """
    ranking_df, dropped_df = build_ranking(
        params.nll_result_csv, params.ssst_result_csv,
        params.nll_loc_root, params.ssst_root, params.run_name, params.zones,
    )

    output_path = params.output or os.path.join(
        _MODULE_DIR, 'event_ranking', f'{params.run_name}_ranking.csv'
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    ranking_df.to_csv(output_path, index=False)
    print(f'Ranking saved @ {output_path} ({len(ranking_df)} events)')

    if params.figures:
        base_output = params.figure_output or os.path.join(
            _MODULE_DIR, 'event_ranking', f'{params.run_name}_gridmap.pdf'
        )
        metrics = ['pct_change', 'diff'] if params.metric == 'both' else [params.metric]
        for metric in metrics:
            figure_output = _suffixed_path(base_output, _METRIC_SUFFIXES[metric])
            _generate_gridmap_figure(ranking_df, metric, figure_output, params.bin_size, params.min_count)
            print(f'Gridmap saved @ {figure_output}')

    return {
        'output_path': output_path,
        'n_events': len(ranking_df),
        'n_multi_zone': int(ranking_df['multi_zone'].sum()),
        'n_dropped': len(dropped_df),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _str2bool(value):
    if value.lower() in ('true', '1', 'yes'):
        return True
    if value.lower() in ('false', '0', 'no'):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got '{value}'")


def main():
    parser = argparse.ArgumentParser(
        description='Rank events by pdfVolume improvement between the NLL and SSST relocation stages.'
    )
    parser.add_argument('--run-name', default='ssst_run1',
                        help='SSST campaign name (default: ssst_run1)')
    parser.add_argument('--nll-result-csv', default=os.path.join(_PROJECT_ROOT, 'RESULT', 'NLL_result.csv'),
                        help='Pre-SSST merged catalog (default: RESULT/NLL_result.csv)')
    parser.add_argument('--ssst-result-csv', default=os.path.join(_PROJECT_ROOT, 'RESULT', 'SSST_result.csv'),
                        help='Post-SSST merged catalog (default: RESULT/SSST_result.csv)')
    parser.add_argument('--nll-loc-root', default=os.path.join(_PROJECT_ROOT, 'run', 'nll_loc'),
                        help='Root folder containing GLOBAL_<zone>/ raw NLL CSVs (default: run/nll_loc)')
    parser.add_argument('--ssst-root', default=os.path.join(_PROJECT_ROOT, 'run', 'ssst_loc'),
                        help='Root folder containing <run-name>/Pyrenees_<zone>_SSST/... (default: run/ssst_loc)')
    parser.add_argument('--zones', nargs='+', default=['1', '2', '3', '4', '5', '6'],
                        help='Zone keys to scan for multi-zone detection (default: 1 2 3 4 5 6)')
    parser.add_argument('--output', default=None,
                        help='Output CSV path (default: complem_figures/event_ranking/<run-name>_ranking.csv)')
    parser.add_argument('--figures', type=_str2bool, default=False,
                        help='Save a whole-Pyrenees pdfVolume/ellipsoidVolume gridmap PDF (default: false)')
    parser.add_argument('--metric', choices=['pct_change', 'diff', 'both'], default='pct_change',
                        help="Gridmap metric: 'pct_change' ((post/pre-1)*100), 'diff' (post-pre, km³), "
                             "or 'both' (one PDF per metric, suffixed _pct/_raw) (default: pct_change)")
    parser.add_argument('--figure-output', default=None,
                        help='Gridmap PDF path, suffixed _pct/_raw before the extension '
                             '(default: complem_figures/event_ranking/<run-name>_gridmap.pdf)')
    parser.add_argument('--bin-size', type=float, default=0.02,
                        help='Gridmap cell size in degrees (default: 0.02)')
    parser.add_argument('--min-count', type=int, default=10,
                        help='Minimum events per gridmap cell to display (default: 10)')
    args = parser.parse_args()

    generate_ranking(EventRankingParams(
        nll_result_csv  = args.nll_result_csv,
        ssst_result_csv = args.ssst_result_csv,
        nll_loc_root    = args.nll_loc_root,
        ssst_root       = args.ssst_root,
        run_name        = args.run_name,
        zones           = args.zones,
        output          = args.output,
        figures         = args.figures,
        metric          = args.metric,
        figure_output   = args.figure_output,
        bin_size        = args.bin_size,
        min_count       = args.min_count,
    ))


if __name__ == '__main__':
    main()
