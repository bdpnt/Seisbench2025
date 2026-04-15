"""
export_locdelay_info.py
============================
Extract LOCDELAY station corrections from NLL second-pass run files and
annotate each entry with its station metadata from the code map.

For each zone (run_<N>_PR.in), the output file contains one block per
station: the code-map entry (Alternate Code, Station Code, Start/End Date)
followed by the LOCDELAY line(s) (P and/or S) from that zone's run file.

Stations not found in the code map are included with a warning comment.

Usage
-----
    # All defaults
    python NLL_run/export_locdelay_info.py

    # Custom paths
    python NLL_run/export_locdelay_info.py \\
        --run-dir   run/ \\
        --codemap   stations/GLOBAL_code_map.txt \\
        --output    run/locdelays/locdelay_summary.txt
"""

import argparse
import glob
import os
import re

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

_DEFAULT_RUN_DIR = os.path.join(_PROJECT_ROOT, 'run')
_DEFAULT_CODEMAP = os.path.join(_PROJECT_ROOT, 'stations', 'GLOBAL_code_map.txt')
_DEFAULT_OUTPUT  = os.path.join(_PROJECT_ROOT, 'run', 'locdelays', 'locdelay_summary.txt')


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_code_map(path):
    """
    Parse the station code map into a lookup dict.

    Each block in the file contains four lines:
      Alternate Code: <code>
        Station Code: <canonical>
        Start Date:   <ISO>
        End Date:     <ISO>

    Parameters
    ----------
    path : str — path to GLOBAL_code_map.txt

    Returns
    -------
    dict[str, list[str]]
        Maps alternate code → list of the raw block lines (without trailing
        newlines), in their original order.
    """
    code_map = {}
    with open(path, 'r') as f:
        lines = [l.rstrip('\n') for l in f]

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('Alternate Code:'):
            alt_code = line.split(':', 1)[1].strip()
            block = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != '':
                block.append(lines[i])
                i += 1
            code_map[alt_code] = block
        i += 1

    return code_map


def load_locdelay(path):
    """
    Extract all LOCDELAY entries from a NLL run file.

    Parameters
    ----------
    path : str — path to a NLL .in run file

    Returns
    -------
    dict[str, list[str]]
        Maps alternate code → list of raw LOCDELAY line strings (stripped),
        in file order (P typically before S).
    """
    entries = {}
    with open(path, 'r') as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith('LOCDELAY'):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            alt_code = parts[1]
            entries.setdefault(alt_code, []).append(line)
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_locdelay_info(run_dir, codemap_path, output_path):
    """
    Build the annotated LOCDELAY summary and write it to output_path.

    Parameters
    ----------
    run_dir      : str — directory containing run_<N>_PR.in files
    codemap_path : str — path to GLOBAL_code_map.txt
    output_path  : str — path for the output text file

    Returns
    -------
    dict with keys: output, n_zones, n_stations_total, n_missing
    """
    # --- Load code map ---
    code_map = load_code_map(codemap_path)

    # --- Find and sort PR run files by zone number ---
    pattern   = os.path.join(run_dir, 'run_*_PR.in')
    run_files = sorted(glob.glob(pattern),
                       key=lambda p: int(re.search(r'run_(\d+)_PR', p).group(1)))

    if not run_files:
        raise FileNotFoundError(f"No run_*_PR.in files found in: {run_dir}")

    n_stations_total = 0
    n_missing        = 0
    output_lines     = []

    for run_path in run_files:
        zone_num = re.search(r'run_(\d+)_PR', run_path).group(1)
        rel_path = os.path.relpath(run_path, _PROJECT_ROOT)

        output_lines.append(
            f"# {'=' * 77}\n"
            f"# Zone {zone_num}  —  {rel_path}\n"
            f"# {'=' * 77}\n"
            "\n"
        )

        locdelay = load_locdelay(run_path)

        for alt_code, delay_lines in locdelay.items():
            n_stations_total += 1
            block = code_map.get(alt_code)

            if block is None:
                n_missing += 1
                output_lines.append(f"# WARNING: '{alt_code}' not found in code map\n")
                for dl in delay_lines:
                    output_lines.append(f"  {dl}\n")
            else:
                for b_line in block:
                    output_lines.append(b_line + '\n')
                for dl in delay_lines:
                    output_lines.append(f"  {dl}\n")

            output_lines.append('\n')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.writelines(output_lines)

    return {
        'output':            output_path,
        'n_zones':           len(run_files),
        'n_stations_total':  n_stations_total,
        'n_missing':         n_missing,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Annotate NLL LOCDELAY corrections with station metadata from the code map.'
    )
    parser.add_argument('--run-dir',  default=_DEFAULT_RUN_DIR,
                        help='Directory containing run_*_PR.in files')
    parser.add_argument('--codemap',  default=_DEFAULT_CODEMAP,
                        help='Path to GLOBAL_code_map.txt')
    parser.add_argument('--output',   default=_DEFAULT_OUTPUT,
                        help='Output text file path (default: run/locdelays/locdelay_summary.txt)')
    args = parser.parse_args()

    result = export_locdelay_info(args.run_dir, args.codemap, args.output)
    print(f"Zones processed    : {result['n_zones']}")
    print(f"Station entries    : {result['n_stations_total']}")
    print(f"Missing in codemap : {result['n_missing']}")
    print(f"Output written to  : {result['output']}")


if __name__ == '__main__':
    main()
