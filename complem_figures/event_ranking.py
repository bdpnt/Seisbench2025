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

Meant as a companion to plot_pdf_cloud.py: the console summary prints a
ready-to-run plot_pdf_cloud.py command line for each listed event.

Usage
-----
    python complem_figures/event_ranking.py --run-name ssst_run1
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
    top_n:           int = 15
    output:          str = None


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
# Console summary
# ---------------------------------------------------------------------------

def _format_plot_cmd(run_name, event_id, zone):
    zone_key = zone.replace('GLOBAL_', '')
    return (f'python complem_figures/plot_pdf_cloud.py --run-name {run_name} '
            f'--event-id {event_id} --zone {zone_key}')


def _print_event_line(row, run_name, zone_col='source_post'):
    zone = row[zone_col]
    print(f"  {row['publicId']}  ({row['date-time']})")
    print(f"    pdfVolume: {row['pdfVolume_pre']:.4g} -> {row['pdfVolume_post']:.4g}  "
          f"(log_ratio={row['log_ratio']:+.3f}, {row['pct_change']:+.1f}%)")
    print(f"    true_erh: {row['true_erh_pre']:.3g} -> {row['true_erh_post']:.3g} km   "
          f"true_erz: {row['true_erz_pre']:.3g} -> {row['true_erz_post']:.3g} km")
    print(f"    {_format_plot_cmd(run_name, row['publicId'], zone)}")


def _print_console_summary(ranking_df, dropped_df, top_n, run_name):
    print(f"\n{'=' * 70}\nBEST IMPROVEMENT (top {top_n}, pdfVolume shrank the most)\n{'=' * 70}")
    for _, row in ranking_df.head(top_n).iterrows():
        _print_event_line(row, run_name)

    print(f"\n{'=' * 70}\nWORST / DEGRADED (top {top_n}, pdfVolume grew the most)\n{'=' * 70}")
    for _, row in ranking_df.tail(top_n).iloc[::-1].iterrows():
        flag = '  [DEGRADED]' if row['log_ratio'] > 0 else ''
        print(f"{flag}")
        _print_event_line(row, run_name)

    multi = ranking_df[ranking_df['multi_zone']]
    print(f"\n{'=' * 70}\nMULTI-ZONE EVENTS ({len(multi)} found, showing up to {top_n})\n{'=' * 70}")
    for _, row in multi.head(top_n).iterrows():
        print(f"  {row['publicId']}  pre-zones=[{row['zones_pre']}]  post-zones=[{row['zones_post']}]")
        _print_event_line(row, run_name)

    changed = ranking_df[ranking_df['zone_changed']]
    print(f"\n{'=' * 70}\nWINNING ZONE CHANGED ({len(changed)} found, showing up to {top_n})\n{'=' * 70}")
    for _, row in changed.head(top_n).iterrows():
        print(f"  {row['publicId']}  {row['source_pre']} -> {row['source_post']}")
        _print_event_line(row, run_name)

    print(f"\n{'=' * 70}\nDROPPED BY SSST STAGE ({len(dropped_df)} event(s), showing up to {top_n})\n{'=' * 70}")
    for _, row in dropped_df.head(top_n).iterrows():
        print(f"  {row['publicId']}  ({row['date-time']})  pdfVolume_pre={row['pdfVolume']:.4g}")
        print(f"    {_format_plot_cmd(run_name, row['publicId'], row['source'])}  (pre-SSST zone; not in final catalog)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ranking(params):
    """
    Build the event ranking, save it to CSV, and print a console summary.

    Parameters
    ----------
    params : EventRankingParams

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

    _print_console_summary(ranking_df, dropped_df, params.top_n, params.run_name)

    return {
        'output_path': output_path,
        'n_events': len(ranking_df),
        'n_multi_zone': int(ranking_df['multi_zone'].sum()),
        'n_dropped': len(dropped_df),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
    parser.add_argument('--top-n', type=int, default=15,
                        help='Number of events to print per console section (default: 15)')
    parser.add_argument('--output', default=None,
                        help='Output CSV path (default: complem_figures/event_ranking/<run-name>_ranking.csv)')
    args = parser.parse_args()

    generate_ranking(EventRankingParams(
        nll_result_csv  = args.nll_result_csv,
        ssst_result_csv = args.ssst_result_csv,
        nll_loc_root    = args.nll_loc_root,
        ssst_root       = args.ssst_root,
        run_name        = args.run_name,
        zones           = args.zones,
        top_n           = args.top_n,
        output          = args.output,
    ))


if __name__ == '__main__':
    main()
