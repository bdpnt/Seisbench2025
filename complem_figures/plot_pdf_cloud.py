"""
plot_pdf_cloud.py
============================
Visualize the NLLoc PDF location scatter-cloud of a single event across all
SSST iterations (loc_ssst_corr0 ... loc_ssst_corrN, the last being the final
NLLoc-only pass), as an interactive 3D scene: one smooth confidence-ellipsoid
surface per iteration, built directly from the mean/covariance NLLoc already
computes and reports in each .hyp file's STATISTICS line (no re-estimation
from the scattered samples), plus the raw sample cloud and the point-estimate
convergence path. Click a legend entry to show/hide that iteration.

Requires: seisbench_env (obspy, pyproj, plotly)

Usage
-----
    python complem_figures/plot_pdf_cloud.py \\
        --run-name ssst_run1 \\
        --event-id PYRENEES_049798 --zone 1

    python complem_figures/plot_pdf_cloud.py \\
        --run-name ssst_run1 \\
        --lat 43.115 --lon -1.500 --date 2023-05-19T03:06:57 \\
        --radius-km 10 --window-days 5
"""

import argparse
import glob
import os
import re
import subprocess
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.colors as pcolors
import plotly.graph_objects as go
import pyproj
from obspy.io.nlloc.util import read_nlloc_scatter
from scipy.stats import chi2

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_TRANS_RE = re.compile(
    r'TRANSFORM\s+LAMBERT\s+RefEllipsoid\s+(\S+)\s+'
    r'LatOrig\s+([-\d.]+)\s+LongOrig\s+([-\d.]+)\s+'
    r'FirstStdParal\s+([-\d.]+)\s+SecondStdParal\s+([-\d.]+)\s+'
    r'RotCW\s+([-\d.]+)'
)

_STATISTICS_RE = re.compile(
    r'STATISTICS\s+ExpectX\s+([-\d.eE+]+)\s+Y\s+([-\d.eE+]+)\s+Z\s+([-\d.eE+]+)\s+'
    r'CovXX\s+([-\d.eE+]+)\s+XY\s+([-\d.eE+]+)\s+XZ\s+([-\d.eE+]+)\s+'
    r'YY\s+([-\d.eE+]+)\s+YZ\s+([-\d.eE+]+)\s+ZZ\s+([-\d.eE+]+)'
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PdfCloudParams:
    ssst_root:  str
    run_name:   str
    event_id:   str
    zone:       str
    confidence: float = 0.68
    output:     str = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_iteration_dirs(ssst_root, run_name, zone):
    """Return sorted (step, dir) pairs for every loc_ssst_corr<N>/GLOBAL_<zone> folder."""
    pattern = os.path.join(ssst_root, run_name, f'Pyrenees_{zone}_SSST', 'loc_ssst_corr*', f'GLOBAL_{zone}')
    step_dirs = []
    for d in glob.glob(pattern):
        match = re.search(r'loc_ssst_corr(\d+)', d)
        step_dirs.append((int(match.group(1)), d))
    return sorted(step_dirs)


def _find_hyp_path(iter_dir, event_id):
    """Locate the .hyp file whose PUBLIC_ID line matches event_id, via grep (fast across thousands of files)."""
    proc = subprocess.run(
        ['grep', '-rlF', f'PUBLIC_ID {event_id}', iter_dir],
        capture_output=True, text=True,
    )
    matches = proc.stdout.strip().splitlines()
    return matches[0] if matches else None


def _sibling(hyp_path, ext):
    return hyp_path[:-len('.hyp')] + ext


def _read_lambert_params(hdr_path):
    """Parse the per-event TRANSFORM LAMBERT line from a .grid0.loc.hdr file."""
    with open(hdr_path) as f:
        text = f.read()
    match = _TRANS_RE.search(text)
    if not match:
        raise ValueError(f'No LAMBERT TRANSFORM found in {hdr_path}')
    _, lat0, lon0, p1, p2, rot = match.groups()
    if float(rot) != 0.0:
        warnings.warn(f'{hdr_path}: non-zero RotCW ({rot}) is not supported by this converter — ignoring.')
    return dict(lat0=float(lat0), lon0=float(lon0), p1=float(p1), p2=float(p2))


def _geographic_to_local_transformer(params):
    """Build a (lon,lat)->(x,y) transformer into the event's local Lambert km frame."""
    crs = pyproj.CRS.from_proj4(
        f"+proj=lcc +lat_1={params['p1']} +lat_2={params['p2']} +lat_0={params['lat0']} "
        f"+lon_0={params['lon0']} +x_0=0 +y_0=0 +ellps=WGS84 +units=km"
    )
    return pyproj.Transformer.from_crs('EPSG:4326', crs, always_xy=True)


def _parse_statistics(hyp_path):
    """Parse the STATISTICS line of a .hyp file: expectation point + covariance, both local km."""
    with open(hyp_path) as f:
        text = f.read()
    match = _STATISTICS_RE.search(text)
    if not match:
        raise ValueError(f'No STATISTICS line found in {hyp_path}')
    ex, ey, ez, cxx, cxy, cxz, cyy, cyz, czz = map(float, match.groups())
    center = np.array([ex, ey, ez])
    cov = np.array([
        [cxx, cxy, cxz],
        [cxy, cyy, cyz],
        [cxz, cyz, czz],
    ])
    return center, cov


def _load_iteration(iter_dir, step, event_id):
    """Load one iteration's PDF cloud (x/y/z/pdf), covariance statistics, and point-estimate
    hypocenter for one event.

    x/y/z are kept in NLLoc's native local Lambert-projected km frame (as recorded in the .scat
    file) rather than converted to lon/lat degrees, matching the frame NLLoc's own STATISTICS
    (expectation + covariance) are reported in.
    """
    hyp_path = _find_hyp_path(iter_dir, event_id)
    if hyp_path is None:
        return None

    scat_path = _sibling(hyp_path, '.scat')
    hdr_path = _sibling(hyp_path, '.hdr')
    if not os.path.exists(scat_path):
        warnings.warn(f'{event_id}: missing .scat at step {step} — skipping this iteration.')
        return None

    cloud = read_nlloc_scatter(scat_path)
    center, cov = _parse_statistics(hyp_path)
    to_local = _geographic_to_local_transformer(_read_lambert_params(hdr_path))

    csv_matches = glob.glob(os.path.join(iter_dir, 'Pyrenees_*.sum.grid0.loc.csv'))
    hyp_x = hyp_y = hyp_z = date_str = None
    if csv_matches:
        df = pd.read_csv(csv_matches[0], skipinitialspace=True)
        row = df.loc[df['publicId'] == event_id]
        if not row.empty:
            row = row.iloc[0]
            hyp_x, hyp_y = to_local.transform(row['longitude'], row['latitude'])
            hyp_z = row['depth']
            date_str = row['date-time']

    return {
        'step': step,
        'x': cloud['x'], 'y': cloud['y'], 'z': cloud['z'], 'pdf': cloud['pdf'],
        'center': center, 'cov': cov,
        'hyp_x': hyp_x, 'hyp_y': hyp_y, 'hyp_z': hyp_z, 'date': date_str,
    }


def _ellipsoid_surface(center, cov, confidence, n=24):
    """
    Parametric confidence-ellipsoid surface from a 3x3 covariance matrix.

    The region {(x-center)^T cov^-1 (x-center) <= chi2.ppf(confidence, df=3)} contains
    `confidence` of the probability mass of a 3D Gaussian with this mean/covariance — the
    standard construction for a location-uncertainty confidence ellipsoid. Always smooth by
    construction (unlike a convex hull of scattered points, which is a faceted polyhedron).

    Returns
    -------
    X, Y, Z : (n, n) arrays suitable for go.Surface
    """
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.clip(eigvals, 0, None)
    scale = np.sqrt(chi2.ppf(confidence, df=3) * eigvals)

    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    unit_sphere = np.stack([
        np.outer(np.cos(u), np.sin(v)),
        np.outer(np.sin(u), np.sin(v)),
        np.outer(np.ones_like(u), np.cos(v)),
    ], axis=-1)

    pts = (unit_sphere * scale) @ eigvecs.T + center
    return pts[..., 0], pts[..., 1], pts[..., 2]


def _build_figure(iterations, confidence, event_id, zone, run_name):
    """Build the interactive 3D figure: one confidence ellipsoid + raw cloud + hypocenter per iteration."""
    steps = [it['step'] for it in iterations]
    n_steps = len(steps)
    colors = pcolors.sample_colorscale('Plasma', [i / max(n_steps - 1, 1) for i in range(n_steps)])

    traces = []
    hyp_xs, hyp_ys, hyp_zs = [], [], []
    rng = np.random.default_rng(0)

    for it, color in zip(iterations, colors):
        label = 'Final' if it['step'] == steps[-1] else f'Iter {it["step"]}'
        group = f'iter{it["step"]}'
        x, y, z = it['x'], it['y'], it['z']

        ex, ey, ez = _ellipsoid_surface(it['center'], it['cov'], confidence)
        traces.append(go.Surface(
            x=ex, y=ey, z=ez,
            colorscale=[[0, color], [1, color]], showscale=False, opacity=0.35,
            name=label, legendgroup=group, showlegend=True,
        ))

        n_show = min(len(x), 3000)
        idx = rng.choice(len(x), size=n_show, replace=False) if len(x) > n_show else np.arange(len(x))
        traces.append(go.Scatter3d(
            x=x[idx], y=y[idx], z=z[idx],
            mode='markers', marker=dict(size=1.5, color=color, opacity=0.3),
            name=label, legendgroup=group, showlegend=False,
        ))

        if it['hyp_x'] is not None:
            traces.append(go.Scatter3d(
                x=[it['hyp_x']], y=[it['hyp_y']], z=[it['hyp_z']],
                mode='markers',
                marker=dict(size=6, color=color, symbol='diamond', line=dict(color='black', width=1)),
                name=label, legendgroup=group, showlegend=False,
            ))
            hyp_xs.append(it['hyp_x'])
            hyp_ys.append(it['hyp_y'])
            hyp_zs.append(it['hyp_z'])

    if len(hyp_xs) > 1:
        traces.append(go.Scatter3d(
            x=hyp_xs, y=hyp_ys, z=hyp_zs,
            mode='lines', line=dict(color='black', width=3),
            name='Convergence path', showlegend=True,
        ))

    date_str = next((it['date'] for it in iterations if it['date']), 'unknown date')
    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=(
            f'{event_id} — Zone {zone} ({run_name}) — {date_str}<br>'
            f'<sub>{confidence:.0%} confidence ellipsoid per iteration — click a legend entry to toggle it</sub>'
        )),
        scene=dict(
            xaxis_title='Easting (km, local)', yaxis_title='Northing (km, local)', zaxis_title='Depth (km)',
            zaxis=dict(autorange='reversed'),
            aspectmode='data',
        ),
        legend=dict(itemsizing='constant'),
    )
    return fig


def _resolve_event_by_location(result_csv, lat, lon, date, radius_km, window_days):
    """Search RESULT/SSST_result.csv for the event nearest (lat, lon, date) within tolerance."""
    df = pd.read_csv(result_csv, skipinitialspace=True)
    df['date-time'] = pd.to_datetime(df['date-time'])
    target_date = pd.to_datetime(date)

    r_earth = 6371.0
    lat1, lon1 = np.radians(df['latitude']), np.radians(df['longitude'])
    lat2, lon2 = np.radians(lat), np.radians(lon)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    dist_km = 2 * r_earth * np.arcsin(np.sqrt(a))
    dt_days = (df['date-time'] - target_date).abs().dt.total_seconds() / 86400.0

    candidates = df[(dist_km <= radius_km) & (dt_days <= window_days)]
    if candidates.empty:
        raise ValueError(f'No event found within {radius_km} km / {window_days} days of ({lat}, {lon}, {date})')
    if len(candidates) > 1:
        print('Multiple candidates found:')
        print(candidates[['publicId', 'source', 'latitude', 'longitude', 'date-time']].to_string(index=False))
        raise ValueError('Ambiguous search — narrow --radius-km / --window-days or use --event-id/--zone directly.')

    row = candidates.iloc[0]
    return row['publicId'], row['source'].replace('GLOBAL_', '')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_figure(params):
    """
    Generate and save the PDF scatter-cloud iteration-overlay figure for one event.

    Parameters
    ----------
    params : PdfCloudParams

    Returns
    -------
    dict with keys: output_path, iterations_found
    """
    iter_dirs = _find_iteration_dirs(params.ssst_root, params.run_name, params.zone)
    if not iter_dirs:
        raise FileNotFoundError(
            f'No SSST iteration folders found under {params.ssst_root}/{params.run_name}/Pyrenees_{params.zone}_SSST'
        )

    iterations = []
    for step, iter_dir in iter_dirs:
        data = _load_iteration(iter_dir, step, params.event_id)
        if data is not None:
            iterations.append(data)

    if not iterations:
        raise ValueError(f'Event {params.event_id} not found in any SSST iteration for zone {params.zone}')

    output_path = params.output or os.path.join(_MODULE_DIR, 'pdf_cloud', f'{params.event_id}.html')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig = _build_figure(iterations, params.confidence, params.event_id, params.zone, params.run_name)
    fig.write_html(output_path, include_plotlyjs=True)
    print(f'Figure saved @ {output_path} ({len(iterations)} iteration(s) found)')

    return {'output_path': output_path, 'iterations_found': [it['step'] for it in iterations]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Visualize the NLLoc PDF scatter-cloud evolution of one event across SSST iterations.'
    )
    parser.add_argument('--ssst-root', default=os.path.join(_PROJECT_ROOT, 'run', 'ssst_loc'),
                        help='Root folder containing <run-name>/Pyrenees_<zone>_SSST/...')
    parser.add_argument('--run-name', default='ssst_run1',
                        help='SSST campaign name (default: ssst_run1)')
    parser.add_argument('--result-csv', default=os.path.join(_PROJECT_ROOT, 'RESULT', 'SSST_result.csv'),
                        help='Merged catalog used for --lat/--lon/--date search (default: RESULT/SSST_result.csv)')
    parser.add_argument('--event-id', help='Event publicId (requires --zone)')
    parser.add_argument('--zone', help='Zone key, e.g. 1..6 (requires --event-id)')
    parser.add_argument('--lat', type=float, help='Approximate latitude for location search')
    parser.add_argument('--lon', type=float, help='Approximate longitude for location search')
    parser.add_argument('--date', help='Approximate ISO date/time for location search')
    parser.add_argument('--radius-km', type=float, default=10.0, help='Search radius for --lat/--lon (default: 10)')
    parser.add_argument('--window-days', type=float, default=5.0, help='Search time window for --date (default: 5)')
    parser.add_argument('--confidence', type=float, default=0.68,
                        help='Confidence-ellipsoid level per iteration surface (default: 0.9)')
    parser.add_argument('--output', default=None,
                        help='Output HTML path (default: complem_figures/pdf_cloud/<event_id>.html)')
    args = parser.parse_args()

    if args.event_id and args.zone:
        event_id, zone = args.event_id, args.zone
    elif args.lat is not None and args.lon is not None and args.date:
        event_id, zone = _resolve_event_by_location(
            args.result_csv, args.lat, args.lon, args.date, args.radius_km, args.window_days
        )
        print(f'Resolved to event {event_id}, zone {zone}')
    else:
        parser.error('Provide either --event-id and --zone, or --lat, --lon and --date.')

    generate_figure(PdfCloudParams(
        ssst_root  = args.ssst_root,
        run_name   = args.run_name,
        event_id   = event_id,
        zone       = zone,
        confidence = args.confidence,
        output     = args.output,
    ))


if __name__ == '__main__':
    main()
