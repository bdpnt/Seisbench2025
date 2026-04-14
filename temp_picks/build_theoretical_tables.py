"""
build_theoretical_tables.py
============================
Compute theoretical P- and S-wave travel-time tables using Pyrocko's `cake` CLI.

For each combination of velocity model, source depth, and epicentral distance,
the script queries `cake arrivals` and extracts the first-arriving P and S times.
It then reduces the results across the "min" and "max" models to obtain envelopes
(lower/upper bounds) representing the travel-time uncertainty due to velocity
variation.

Outputs
-------
- CSV file  : columns [distance, tp_low, tp_high, ts_low, ts_high]
- PNG figure : two-panel plot of P-wave and S-wave arrival bands (seaborn style)

Requirements
------------
- Pyrocko must be installed and `cake` must be available on the system PATH.
- Velocity model files (.nd format) must exist at the paths given in models.
"""

from dataclasses import dataclass
import numpy as np
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


@dataclass
class BuildTablesParams:
    """
    Configuration for building theoretical travel-time tables.

    Attributes
    ----------
    models : dict
        Mapping of model role to .nd file path. Must contain at least the
        keys "min" and "max" (used to build the arrival-time envelope).
        The "ref" key (nominal model) is stored here for reference but is
        not used in the current computation.
    depths : list[float]
        Source depths in km. The envelope spans all provided depths.
    distances : list[float]
        Epicentral distances in km at which arrivals are computed.
    output : str
        Path for the output CSV file.
    figure_output : str
        Path for the output PNG figure.
    """
    models: dict
    depths: list[float]
    distances: list[float]
    output: str
    figure_output: str


def get_arrivals(model, depth, distance):
    """
    Query `cake arrivals` for the first P and S arrival times.

    Runs the Pyrocko `cake` command-line tool as a subprocess and parses its
    fixed-width text output to extract arrival times.

    Parameters
    ----------
    model : str
        Path to the velocity model file (.nd format).
    depth : float
        Source depth in km.
    distance : float
        Epicentral distance in km.

    Returns
    -------
    arrP : float
        First P-wave arrival time in seconds, or np.nan if not found.
    arrS : float
        First S-wave arrival time in seconds, or np.nan if not found.

    Notes
    -----
    The `cake arrivals` output is a fixed-width table. The relevant columns are:
      - Characters 14–20 : arrival time in seconds
      - Character  41    : phase code (P/p or S/s)
    These positions were determined from the cake output format and must match
    the installed version of Pyrocko.
    """
    cmd = [
        "cake", "arrivals",
        "--sdepth", str(depth),
        "--distances", str(distance),
        "--model", model,
        "--phase", "p,s,P,S"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Warn if cake returned a non-zero exit code (e.g. model file not found)
    if result.returncode != 0:
        print(f"Warning: cake exited with code {result.returncode} "
              f"(model={model}, depth={depth}, dist={distance})")

    arrP = np.nan
    arrS = np.nan

    for line in result.stdout.splitlines():

        # Skip header lines and short lines that don't contain arrival data
        if len(line) < 50:
            continue

        # Column 41 holds the phase code character (fixed-width cake format)
        phase_char = line[41].lower()

        try:
            # Columns 14–20 hold the arrival time in seconds
            arrival_time = float(line[14:21])
        except (ValueError, IndexError):
            continue

        # Keep only the earliest arrival for each phase type
        if phase_char == 'p':
            if np.isnan(arrP) or arrival_time < arrP:
                arrP = arrival_time

        elif phase_char == 's':
            if np.isnan(arrS) or arrival_time < arrS:
                arrS = arrival_time

    return arrP, arrS


def get_times(models, depths, distances):
    """
    Compute P- and S-wave arrival times for all model/depth/distance combinations.

    Parameters
    ----------
    models : dict
        Mapping of model key to .nd file path (e.g. {"min": "...", "max": "..."}).
    depths : list[float]
        Source depths in km.
    distances : list[float]
        Epicentral distances in km.

    Returns
    -------
    TP : dict
        Nested dict of P-wave times: TP[model_key][depth] = np.array of times.
    TS : dict
        Nested dict of S-wave times: TS[model_key][depth] = np.array of times.
    """
    TP = {m: {} for m in models}
    TS = {m: {} for m in models}

    for m in models:
        for depth in depths:
            tp = []
            ts = []

            print(f"  Computing arrivals — model: {m:>4s}  depth: {depth:>5.1f} km")

            for dist in distances:
                p, s = get_arrivals(models[m], depth, dist)
                tp.append(p)
                ts.append(s)

            TP[m][depth] = np.array(tp)
            TS[m][depth] = np.array(ts)

    return TP, TS


def compute_min_max_times(models, depths, distances):
    """
    Build a DataFrame of P/S arrival-time envelopes across all models and depths.

    The envelope (low/high bounds) is the element-wise minimum and maximum of
    the "min" and "max" model arrivals, taken across all provided depths.

    Note: The "min" and "max" keys must be present in the models dict. Any
    additional keys (e.g. "ref") are computed by get_times but not used here.

    Parameters
    ----------
    models : dict
        Must contain at least "min" and "max" keys (see BuildTablesParams).
    depths : list[float]
        Source depths in km.
    distances : list[float]
        Epicentral distances in km.

    Returns
    -------
    pd.DataFrame
        Columns: distance, tp_low, tp_high, ts_low, ts_high.
    """
    TP, TS = get_times(models, depths, distances)

    # Initialize envelopes using the first depth
    tp_low  = TP["min"][depths[0]]
    tp_high = TP["max"][depths[0]]
    ts_low  = TS["min"][depths[0]]
    ts_high = TS["max"][depths[0]]

    # Expand envelopes across remaining depths
    for depth in depths[1:]:
        tp_low  = np.minimum(tp_low,  TP["min"][depth])
        tp_high = np.maximum(tp_high, TP["max"][depth])
        ts_low  = np.minimum(ts_low,  TS["min"][depth])
        ts_high = np.maximum(ts_high, TS["max"][depth])

    return pd.DataFrame({
        "distance": distances,
        "tp_low":   tp_low,
        "tp_high":  tp_high,
        "ts_low":   ts_low,
        "ts_high":  ts_high,
    })


def build_figure(time_tables, output):
    """
    Save a two-panel figure showing P-wave and S-wave travel-time bands.

    The shaded band represents the range of arrival times across the min/max
    velocity models and all source depths (±5% velocity variation).

    Parameters
    ----------
    time_tables : pd.DataFrame
        Output of compute_min_max_times(); must contain columns:
        distance, tp_low, tp_high, ts_low, ts_high.
    output : str
        File path for the saved PNG figure.
    """
    sns.set_theme(style="whitegrid")
    palette = sns.color_palette("tab10")

    fig, (ax_p, ax_s) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # --- Top panel: P-wave arrivals ---
    ax_p.fill_between(
        time_tables.distance, time_tables.tp_low, time_tables.tp_high,
        color=palette[0], alpha=0.4, label="P-wave band"
    )
    ax_p.set_ylim(0,30)
    ax_p.set_ylabel("Arrival Time (s)")
    ax_p.set_title("P-wave arrivals — ±5% velocity variation")

    # --- Bottom panel: S-wave arrivals ---
    ax_s.fill_between(
        time_tables.distance, time_tables.ts_low, time_tables.ts_high,
        color=palette[1], alpha=0.4, label="S-wave band"
    )
    ax_p.set_ylim(0,30)
    ax_s.set_xlabel("Distance (km)")
    ax_s.set_ylabel("Arrival Time (s)")
    ax_s.set_title("S-wave arrivals — ±5% velocity variation")

    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)


def save_theoretical_tables(parameters):
    """
    Main entry point: compute travel-time tables, save CSV, and generate figure.

    Parameters
    ----------
    parameters : BuildTablesParams
        Full configuration (models, depths, distances, output paths).
    """
    time_tables = compute_min_max_times(
        parameters.models, parameters.depths, parameters.distances
    )
    build_figure(time_tables, parameters.figure_output)
    time_tables.to_csv(parameters.output, index=False)


if __name__ == "__main__":
    params = BuildTablesParams(
        models={
            # "ref" is the nominal velocity model (100% of reference velocities).
            # It is stored here for future use (e.g. plotting a reference curve)
            # but is not currently used in the envelope computation.
            "ref": "models/model_Pyr_100.nd",
            # "min" and "max" bound the ±5% velocity uncertainty range
            "min": "models/model_Pyr_95.nd",
            "max": "models/model_Pyr_105.nd",
        },
        distances=list(np.arange(0, 100.5, 2)),
        depths=[0.0, 30.0],
        output="tables_Pyr.csv",
        figure_output="figures/tables_Pyr.png",
    )

    save_theoretical_tables(params)
