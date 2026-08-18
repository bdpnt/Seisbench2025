"""
pdf_metrics.py
============================
Per-event location-PDF quality metrics, computed from the NonLinLoc `.scat`
scatter clouds of the final SSST relocation and appended to a merged result CSV.

The metrics answer one question: does the Gaussian confidence ellipsoid NLLoc
reports actually represent the posterior it was derived from? They measure
internal *consistency*, not accuracy — velocity-model error is a bias none of
them can see.

  J        negentropy KL(p || N(mu, Sigma)) in nats; 0 for an exactly Gaussian PDF
  Psi      exp(-J), the effective-volume ratio V_eff(PDF) / V_eff(ellipsoid)
  C68      fraction of posterior mass inside the nominal 68% ellipsoid; > 0.68
           means the reported errors are conservative, < 0.68 over-confident
  dip_stat Hartigan dip statistic on the depth marginal (multimodality)

J and C68 are meaningless without an n-matched Gaussian null: the k-NN entropy
estimator is biased in a sample-size-dependent way, and the C68 null spread is
NOT binomial (mu/Sigma are fitted on the very samples being tested, which
suppresses the scatter). `gaussian_null` simulates both per distinct n; the
resulting `J_null_p95` / `C68_sigma_n` columns are what make a later cut a
one-line comparison.

Environment: needs `diptest` (imported lazily, only by depth_dip) -> seisbench_env.

Usage
-----
    python NLL_run/pdf_metrics.py --run-name ssst_run1
    python NLL_run/pdf_metrics.py --run-name ssst_run1 --output /tmp/annotated.csv
"""

import argparse
import glob
import logging
import os
import re
import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.special import digamma, gammaln
from scipy.stats import chi2 as chi2dist

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT    = os.path.dirname(_MODULE_DIR)
_DEFAULT_LOG_DIR = os.path.join(_MODULE_DIR, 'console_output')

logger = logging.getLogger('pdf_metrics')

# Columns this module writes. Listed so a re-run can drop them before
# recomputing, which is what keeps the CLI idempotent.
METRIC_COLUMNS = [
    'ellipsoidVolume', 'n_scat', 'J', 'Psi', 'C68',
    'J_null_p95', 'C68_sigma_n', 'dip_stat', 'dip_pval', 'dip_reject',
]

_KNN_K        = 5      # k for the Kozachenko-Leonenko entropy estimator
_NULL_SIMS    = 500    # Gaussian clouds simulated per distinct n
_DIP_COMMON_N = 400    # common subsample size for the dip test (< observed min n)
_DIP_ALPHA    = 0.05

_CHI2_68_3DOF = chi2dist.ppf(0.68, df=3)
_GAUSS_ENTROPY_3D = 0.5 * 3 * np.log(2 * np.pi * np.e)   # 4.2568 nats


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PdfMetricsParams:
    result_csv: str
    ssst_root:  str
    run_name:   str
    zones:      list = field(default_factory=lambda: ['1', '2', '3', '4', '5', '6'])
    output:     str = None      # None -> rewrite result_csv in place
    log_dir:    str = None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    basename  = os.path.splitext(os.path.basename(__file__))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"{basename}_{timestamp}.log")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)
    return log_path


# ---------------------------------------------------------------------------
# .scat reader
# ---------------------------------------------------------------------------

# NLLoc scatter file: int32 nSamples, 12 unused bytes, then nSamples records of
# 4 float32 (x, y, z, log-likelihood), x/y/z in the local Lambert km frame.
_SCAT_DTYPE = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('pdf', '<f4')])
_SCAT_HEADER_BYTES = 16


def read_scat(path):
    """
    Read a NonLinLoc .scat file into a structured array (fields x, y, z, pdf).

    Drop-in replacement for obspy.io.nlloc.util.read_nlloc_scatter, which is
    unusable here: it does `np.fromfile(...)[4:]`, dropping the first four
    16-byte *records* where the header is a single 16-byte record — silently
    discarding the first 3 samples of every file.

    Samples are unweighted: NLLoc draws them with density proportional to the
    posterior, so `pdf` is carried for API compatibility but is not a weight.

    Raises ValueError if the declared sample count and the file size disagree.
    """
    with open(path, 'rb') as fh:
        buf = fh.read()

    if len(buf) < _SCAT_HEADER_BYTES:
        raise ValueError(f'{path}: shorter than the {_SCAT_HEADER_BYTES}-byte header')

    n_samples = struct.unpack('<i', buf[:4])[0]
    body = buf[_SCAT_HEADER_BYTES:]
    if n_samples < 0 or len(body) != n_samples * _SCAT_DTYPE.itemsize:
        raise ValueError(
            f'{path}: header declares {n_samples} samples but the body holds '
            f'{len(body) / _SCAT_DTYPE.itemsize:.2f}')

    return np.frombuffer(body, dtype=_SCAT_DTYPE, count=n_samples)


def scat_xyz(scat):
    """Return the (n, 3) float64 coordinate array of a structured scatter array."""
    return np.column_stack([scat['x'], scat['y'], scat['z']]).astype(np.float64)


# ---------------------------------------------------------------------------
# Iteration-directory resolution (shared with complem_figures/)
# ---------------------------------------------------------------------------

def find_iteration_dirs(ssst_root, run_name, zone):
    """Return sorted (step, dir) pairs for every loc_ssst_corr<N>/GLOBAL_<zone> folder."""
    pattern = os.path.join(ssst_root, run_name, f'Pyrenees_{zone}_SSST',
                           'loc_ssst_corr*', f'GLOBAL_{zone}')
    step_dirs = []
    for path in glob.glob(pattern):
        match = re.search(r'loc_ssst_corr(\d+)', path)
        step_dirs.append((int(match.group(1)), path))
    return sorted(step_dirs)


def final_iteration_dir(ssst_root, run_name, zone):
    """Return the highest-numbered loc_ssst_corr<N>/GLOBAL_<zone> folder, or None."""
    step_dirs = find_iteration_dirs(ssst_root, run_name, zone)
    return step_dirs[-1][1] if step_dirs else None


def sibling(hyp_path, ext):
    """Swap the .hyp extension of a per-event NLLoc output path for `ext`."""
    return hyp_path[:-len('.hyp')] + ext


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def whiten(xyz):
    """
    Centre and whiten samples by their own Sigma^(-1/2), so cov(out) = I.

    The reference Gaussian for both J and C68 is the one matched to the cloud's
    own mean and covariance — exactly the distribution NLLoc's confidence
    ellipsoid draws — so whitening reduces both metrics to their standard-normal
    form. Returns None if the covariance is singular (degenerate cloud).

    bias=True (ddof=0) is deliberate: NLLoc derives the STATISTICS CovXX..ZZ line
    — and hence the published ellipsoid — from these same scatter samples with
    that normalisation. Verified against 20 events' .hyp files, where ddof=1 left
    a constant n/(n-1) offset (0.21% at n=479) and ddof=0 leaves none. C68 must
    test the ellipsoid that was actually published.
    """
    centred = xyz - xyz.mean(axis=0)
    cov = np.cov(centred, rowvar=False, bias=True)
    eigvals, eigvecs = np.linalg.eigh(cov)
    if np.any(eigvals <= 0) or not np.all(np.isfinite(eigvals)):
        return None
    return centred @ (eigvecs * eigvals ** -0.5) @ eigvecs.T


def negentropy(white, k=_KNN_K):
    """
    Negentropy J = KL(p || N(mu, Sigma)) in nats, from pre-whitened samples.

    Kozachenko-Leonenko k-NN differential entropy estimator:
        H = -psi(k) + psi(n) + log(c_d) + (d/n) * sum(log(eps_i))
    with eps_i the distance to the i-th sample's k-th neighbour and c_d the
    volume of the unit d-ball. After whitening the reference is the standard
    normal, so J = 0.5*d*log(2*pi*e) - H.

    Duplicate samples would give log(0); they are jittered far below the NLLoc
    grid spacing rather than dropped, so n (and hence the matching null) is
    unchanged.
    """
    n, d = white.shape
    eps = _knn_radius(white, k)
    if eps is None:
        return np.nan

    log_unit_ball = (d / 2) * np.log(np.pi) - gammaln(d / 2 + 1)
    entropy = (-digamma(k) + digamma(n) + log_unit_ball
               + (d / n) * np.sum(np.log(eps)))
    return float(0.5 * d * np.log(2 * np.pi * np.e) - entropy)


def _knn_radius(white, k, _rng=np.random.default_rng(0)):
    """Distance to each sample's k-th neighbour, jittering duplicates away from 0."""
    for attempt in range(3):
        distances, _ = cKDTree(white).query(white, k=k + 1)
        eps = distances[:, k]
        if np.all(eps > 0):
            return eps
        white = white + _rng.normal(scale=1e-6, size=white.shape)
    return None


def coverage_68(white):
    """
    Fraction of samples inside the nominal 68% Gaussian confidence ellipsoid.

    For whitened samples the squared Mahalanobis radius is just |w|^2, so this
    is the fraction with |w|^2 <= chi2.ppf(0.68, 3). Equals 0.68 for a Gaussian
    PDF; above means the reported ERH/ERZ are conservative, below means they are
    over-confident.
    """
    return float(np.mean(np.sum(white ** 2, axis=1) <= _CHI2_68_3DOF))


_null_cache = {}


def gaussian_null(n, n_sim=_NULL_SIMS, seed=0):
    """
    Simulate the n-matched Gaussian null for J and C68.

    Returns (J_p95, C68_sigma): the 95th percentile of J and the standard
    deviation of C68 over `n_sim` genuinely Gaussian clouds of size n, run
    through the identical whitening + estimator pipeline.

    This is not optional. The k-NN entropy estimator's bias depends on n, so a
    fixed J threshold would flag sparsely-sampled events for reasons unrelated
    to their PDFs. And the C68 spread is not binomial: sqrt(.68*.32/n)
    overestimates it (0.021 vs ~0.012 at n=479) because mu and Sigma are
    estimated from the same samples being tested.

    Cached per n — the catalog holds only ~82 distinct sample counts.
    """
    key = (n, n_sim, seed)
    if key in _null_cache:
        return _null_cache[key]

    rng = np.random.default_rng(seed + n)
    j_values = np.empty(n_sim)
    c_values = np.empty(n_sim)
    for i in range(n_sim):
        white = whiten(rng.standard_normal((n, 3)))
        j_values[i] = negentropy(white)
        c_values[i] = coverage_68(white)

    result = (float(np.nanpercentile(j_values, 95)), float(np.nanstd(c_values, ddof=1)))
    _null_cache[key] = result
    return result


def depth_dip(depths, public_id, common_n=_DIP_COMMON_N):
    """
    Hartigan's dip test on the depth marginal, at a catalog-wide common n.

    A rejection means the depth PDF has two competing solutions, so no scalar
    depth +/- error is honest — the one unconditional reject criterion, since
    depth is the target quantity.

    The dip test's power grows with n, so p-values from different sample sizes
    are not comparable. Every event is therefore subsampled to `common_n`
    (below the smallest observed scatter count) using an RNG seeded from its
    publicId — deterministic across runs and independent between events.
    """
    from diptest import diptest      # lazy: only this function needs seisbench_env

    if len(depths) < common_n:
        return np.nan, np.nan

    rng = np.random.default_rng(zlib.crc32(public_id.encode()))
    subsample = depths[rng.choice(len(depths), size=common_n, replace=False)]
    stat, pval = diptest(np.asarray(subsample, dtype=np.float64))
    return float(stat), float(pval)


def event_metrics(scat_path, public_id):
    """
    Compute every per-event metric for one .scat file.

    On failure every metric is NaN except `dip_reject`, which stays False: it is a
    reject flag, and an unreadable cloud is no evidence of multimodality. Keeping
    it a pure boolean also stops the column degrading to object dtype — the NaN in
    `dip_pval` is what marks the event as unevaluated.
    """
    blank = {col: np.nan for col in METRIC_COLUMNS if col != 'ellipsoidVolume'}
    blank['dip_reject'] = False

    try:
        scat = read_scat(scat_path)
    except (OSError, ValueError) as exc:
        logger.warning(f'{public_id}: unreadable .scat ({exc})')
        return blank

    xyz = scat_xyz(scat)
    n_samples = len(xyz)
    white = whiten(xyz)
    if white is None:
        logger.warning(f'{public_id}: singular covariance over {n_samples} samples')
        return {**blank, 'n_scat': n_samples}

    j_value = negentropy(white)
    c68 = coverage_68(white)
    j_null_p95, c68_sigma = gaussian_null(n_samples)
    dip_stat, dip_pval = depth_dip(xyz[:, 2], public_id)

    return {
        'n_scat':      n_samples,
        'J':           j_value,
        'Psi':         float(np.exp(-j_value)) if np.isfinite(j_value) else np.nan,
        'C68':         c68,
        'J_null_p95':  j_null_p95,
        'C68_sigma_n': c68_sigma,
        'dip_stat':    dip_stat,
        'dip_pval':    dip_pval,
        'dip_reject':  bool(dip_pval < _DIP_ALPHA) if np.isfinite(dip_pval) else False,
    }


# ---------------------------------------------------------------------------
# Catalog-scale plumbing
# ---------------------------------------------------------------------------

def build_scat_index(ssst_root, run_name, zones):
    """
    Map (zone_source, publicId) -> .scat path over every zone's final iteration.

    The .scat/.hyp filenames carry the *input* event time, not the publicId, and
    the relocated origin time differs from it — so the join key has to come from
    the PUBLIC_ID line (line 2) of each .hyp. Read in bulk here rather than
    grepping per event, which is what plot_pdf_cloud.py does for its single-event
    case and would be hopeless across ~46 k events.
    """
    index = {}
    for zone in zones:
        iter_dir = final_iteration_dir(ssst_root, run_name, zone)
        if iter_dir is None:
            logger.warning(f'zone {zone}: no loc_ssst_corr* directory found')
            continue

        source = os.path.basename(iter_dir)      # GLOBAL_<zone>, matching the CSV
        n_zone = 0
        for hyp_path in glob.glob(os.path.join(iter_dir, '*.hyp')):
            if '.sum.' in os.path.basename(hyp_path):
                continue                         # concatenated summary, no .scat
            with open(hyp_path) as fh:
                fh.readline()                    # NLLOC ... line
                second = fh.readline()
            if not second.startswith('PUBLIC_ID'):
                continue
            scat_path = sibling(hyp_path, '.scat')
            if os.path.exists(scat_path):
                index[(source, second.split()[1])] = scat_path
                n_zone += 1
        logger.info(f'zone {zone}: indexed {n_zone} scatter clouds from {iter_dir!r}')

    return index


def compute_metrics(params):
    """
    Append the PDF-quality columns to a merged result CSV.

    Metrics are computed only for each event's winning zone: `source` already
    records which zone survived the lowest-pdfVolume dedup, so joining on
    (source, publicId) skips the ~7 600 losing solutions.

    Returns dict with keys: output, log, n_events, n_missing.
    """
    log_path = _setup_logger(params.log_dir or _DEFAULT_LOG_DIR)
    logger.info(f'Result CSV : {params.result_csv!r}')
    logger.info(f'Run name   : {params.run_name}')

    df = pd.read_csv(params.result_csv, skipinitialspace=True)
    df = df.drop(columns=[c for c in METRIC_COLUMNS if c in df.columns])

    df['ellipsoidVolume'] = (4 / 3 * np.pi * df['EllipsoidLen1']
                             * df['EllipsoidLen2'] * df['EllipsoidLen3'])

    index = build_scat_index(params.ssst_root, params.run_name, params.zones)
    logger.info(f'Indexed {len(index)} scatter clouds across {len(params.zones)} zones')
    print(f'Indexed {len(index)} scatter clouds')

    records, missing = [], []
    for position, (public_id, source) in enumerate(zip(df['publicId'], df['source']), 1):
        scat_path = index.get((source, public_id))
        if scat_path is None:
            missing.append(public_id)
            blank = {col: np.nan for col in METRIC_COLUMNS if col != 'ellipsoidVolume'}
            blank['dip_reject'] = False
            records.append(blank)
        else:
            records.append(event_metrics(scat_path, public_id))
        if position % 5000 == 0:
            print(f'  {position}/{len(df)} events')

    metrics = pd.DataFrame.from_records(records, index=df.index)
    for column in METRIC_COLUMNS:
        if column != 'ellipsoidVolume':
            df[column] = metrics[column]
    df['n_scat'] = df['n_scat'].astype('Int64')      # nullable: NaN where no .scat
    df['dip_reject'] = df['dip_reject'].astype(bool)

    output_path = params.output or params.result_csv
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f'{output_path}.tmp'
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, output_path)

    logger.info(f'Events            : {len(df)}')
    logger.info(f'Without a .scat   : {len(missing)}')
    for public_id in missing[:50]:
        logger.info(f'  MISSING {public_id}')
    logger.info(f'Output            : {output_path!r}')

    print(f'Metrics saved @ {output_path} ({len(df)} events, {len(missing)} without a .scat)')
    return {
        'output':    output_path,
        'log':       log_path,
        'n_events':  len(df),
        'n_missing': len(missing),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Append location-PDF quality metrics (J, Psi, C68, dip test) '
                    'to a merged NLLoc result CSV.')
    parser.add_argument('--run-name', default='ssst_run1',
                        help='SSST campaign name (default: ssst_run1)')
    parser.add_argument('--result-csv',
                        default=os.path.join(_PROJECT_ROOT, 'RESULT', 'SSST_result.csv'),
                        help='Merged catalog to annotate (default: RESULT/SSST_result.csv)')
    parser.add_argument('--ssst-root', default=os.path.join(_PROJECT_ROOT, 'run', 'ssst_loc'),
                        help='Root holding <run-name>/Pyrenees_<zone>_SSST/... (default: run/ssst_loc)')
    parser.add_argument('--zones', nargs='+', default=['1', '2', '3', '4', '5', '6'],
                        help='Zone keys to index (default: 1 2 3 4 5 6)')
    parser.add_argument('--output', default=None,
                        help='Output CSV path (default: rewrite --result-csv in place)')
    parser.add_argument('--log-dir', default=None,
                        help='Log directory (default: NLL_run/console_output/)')
    args = parser.parse_args()

    compute_metrics(PdfMetricsParams(
        result_csv = args.result_csv,
        ssst_root  = args.ssst_root,
        run_name   = args.run_name,
        zones      = args.zones,
        output     = args.output,
        log_dir    = args.log_dir,
    ))


if __name__ == '__main__':
    main()
