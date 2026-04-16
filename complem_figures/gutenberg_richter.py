"""
gutenberg_richter.py
============================
Plot the Gutenberg-Richter magnitude-frequency distribution.

Reads a GLOBAL.obs bulletin, converts ML to Mw using the piecewise law from
Cara et al. [2017] (optional), sorts magnitudes in descending order, computes
the cumulative event count above each magnitude, and saves a scatter plot on
a log scale.

Usage
-----
    python complem_figures/gutenberg_richter.py \\
        --bulletin  obs/GLOBAL.obs \\
        --output    complem_figures/gutenberg_richter/GLOBAL_Mw.png \\
        --mag-type  Mw
"""

import argparse
import os
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GutenbergRichterParams:
    file_bulletin: str
    fig_save:      str
    mag_type:      str = 'Mw'   # 'Mw' or 'ML'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ml_to_mw(mag):
    """
    Convert ML magnitude to Mw using the piecewise law from Cara et al. [2017].

    Parameters
    ----------
    mag : float — ML magnitude

    Returns
    -------
    float — Mw magnitude
    """
    if mag < 3.117:
        return 0.6642 * mag + 0.4467
    elif mag <= 4:
        return mag - 0.6
    else:
        return 1.4285 * mag - 2.0891


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_figure(parameters):
    """
    Compute and plot the Gutenberg-Richter distribution for the bulletin.

    Parameters
    ----------
    parameters : GutenbergRichterParams

    Returns
    -------
    dict with keys: output
    """
    sns.set_theme()

    with open(parameters.file_bulletin, 'r') as f:
        lines = f.readlines()

    bull = [line.lstrip('# ').rstrip('\n').split()
            for line in lines if line.startswith('# ')]
    bull_df = pd.DataFrame(bull, columns=[
        'Year', 'Month', 'Day', 'Hour', 'Min', 'Sec',
        'Lat', 'Lon', 'Dep', 'Mag', 'MagType', 'MagAuthor',
        'PhaseCount', 'HorUncer', 'VerUncer', 'AzGap', 'RMS',
    ])
    bull_df[['Year', 'Mag']] = bull_df[['Year', 'Mag']].apply(pd.to_numeric)

    if parameters.mag_type == 'Mw':
        bull_df['Mag'] = bull_df.Mag.apply(_ml_to_mw)

    sorted_mags      = np.sort(bull_df.Mag.unique())[::-1]
    cumulative_count = [len(bull_df[bull_df.Mag >= mag]) for mag in sorted_mags]

    fig = plt.figure(figsize=(5, 6))
    sns.scatterplot(x=sorted_mags, y=cumulative_count)
    plt.yscale('log')
    plt.xlabel(f'Magnitude {parameters.mag_type}')
    plt.ylabel('N')
    plt.title('Gutenberg-Richter law')
    plt.xlim(0, 6)
    plt.ylim(10**0, 10**5)
    plt.savefig(parameters.fig_save)
    plt.close(fig)

    print(f'Figure saved @ {parameters.fig_save}')
    return {'output': parameters.fig_save}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Plot the Gutenberg-Richter magnitude-frequency distribution.'
    )
    parser.add_argument('--bulletin',  default=os.path.join(_PROJECT_ROOT, 'obs', 'GLOBAL.obs'),
                        help='Input GLOBAL.obs bulletin')
    parser.add_argument('--output',
                        default=os.path.join(_MODULE_DIR, 'gutenberg_richter', 'GLOBAL_Mw.png'),
                        help='Output figure path')
    parser.add_argument('--mag-type', default='Mw', choices=['Mw', 'ML'],
                        help='Magnitude type for the x-axis label and conversion (default: Mw)')
    args = parser.parse_args()

    generate_figure(GutenbergRichterParams(
        file_bulletin = args.bulletin,
        fig_save      = args.output,
        mag_type      = args.mag_type,
    ))


if __name__ == '__main__':
    main()
