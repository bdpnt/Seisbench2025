"""
convert_picks.py
============================
Pick file format converter for the Seisbench2025 project.

Reads a pick file from Pyrocko/pick_files/, strips all non-pick lines (event
headers, blanks), maps station codes to the project's internal codes using
stations/GLOBAL_code_map.txt, and writes pick-only output in the obs/GLOBAL.obs
pick line format.

Usage
-----
    python temp_picks/convert_picks.py --input temp_picks/pick_files/viehla_final.obs --format TEMP_OBS

Supported formats
-----------------
    TEMP_OBS : OBS-style .obs file with short station names and floating-point
               year/month/day fields in event headers. Used by Viehla and similar
               generated pick files.

Adding a new format
-------------------
    1. Write a converter function: convert_<format>(line, code_map) -> str | None
       It receives a single non-header, non-blank pick line and the station code map.
       It must return the converted GLOBAL.obs pick line string, or None to skip.
    2. Register it in FORMAT_HANDLERS with a descriptive key string.
"""

import argparse
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger('convert_picks')


# ---------------------------------------------------------------------------
# Station code map
# ---------------------------------------------------------------------------

def load_code_map(codemap_path):
    """
    Parse GLOBAL_code_map.txt into a station lookup dict.

    The file maps project-internal codes (Alternate Code) to canonical
    NETWORK.CODE names (Station Code). This function inverts the lookup:
    given a short station name (the part after the '.' in the canonical code),
    return the list of matching project-internal codes with their validity windows.

    Parameters
    ----------
    codemap_path : str
        Path to stations/GLOBAL_code_map.txt.

    Returns
    -------
    dict[str, list[dict]]
        Keys are short station names (e.g. 'PYLU').
        Values are lists of dicts with keys:
            'internal_code' : str  — project internal code (e.g. 'RA.0012')
            'start'         : datetime or None
            'end'           : datetime or None
    """
    code_map = {}

    with open(codemap_path, 'r') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('Alternate Code:'):
            internal_code  = line.split(':', 1)[1].strip()
            canonical_code = None
            start_dt       = None
            end_dt         = None

            for j in range(1, 4):
                if i + j >= len(lines):
                    break
                sub = lines[i + j].strip()
                if sub.startswith('Station Code:'):
                    canonical_code = sub.split(':', 1)[1].strip()
                elif sub.startswith('Start Date:'):
                    start_dt = _parse_map_date(sub.split(':', 1)[1].strip())
                elif sub.startswith('End Date:'):
                    end_dt = _parse_map_date(sub.split(':', 1)[1].strip())

            if canonical_code:
                short_name = canonical_code.split('.')[-1]
                if short_name not in code_map:
                    code_map[short_name] = []
                code_map[short_name].append({
                    'internal_code': internal_code,
                    'start':         start_dt,
                    'end':           end_dt,
                })

        i += 1

    return code_map


def _parse_map_date(date_str):
    """Parse ISO date string from GLOBAL_code_map.txt into a timezone-aware datetime."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def resolve_station(short_name, pick_date_str, code_map):
    """
    Return the project internal station code for a short station name.

    Uses the pick date to select the correct entry when multiple time windows
    exist for the same station. Falls back to the last entry with a warning
    if no date-matched entry is found.

    Parameters
    ----------
    short_name : str
        Short station name from the source pick file (e.g. 'PYLU').
    pick_date_str : str
        Pick date in YYYYMMDD format (e.g. '20201204').
    code_map : dict
        Lookup dict from load_code_map().

    Returns
    -------
    str or None
        Project internal code (e.g. 'RA.0012'), or None if station is unknown.
    """
    entries = code_map.get(short_name)
    if not entries:
        return None

    try:
        pick_dt = datetime.strptime(pick_date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
    except ValueError:
        pick_dt = None

    if pick_dt is not None:
        for entry in entries:
            start = entry['start']
            end   = entry['end']
            if start and end and start <= pick_dt <= end:
                return entry['internal_code']

    # Fallback: most recent entry
    logger.warning(f"No date-matched entry for '{short_name}' on {pick_date_str}. Using most recent.")
    return entries[-1]['internal_code']


# ---------------------------------------------------------------------------
# Output formatting helper
# ---------------------------------------------------------------------------

def _format_pick_line(internal_code, phase, date, hhmm, seconds_str, error_str, pick_origin):
    """
    Format a single pick line in GLOBAL.obs style.

    Field widths match the format used throughout the fetch_obs/ modules.

    Parameters
    ----------
    internal_code : str   — project internal station code (e.g. 'RA.0012')
    phase         : str   — 'P' or 'S'
    date          : str   — YYYYMMDD
    hhmm          : str   — HHMM (4 chars, zero-padded)
    seconds_str   : str   — arrival seconds as string (e.g. '29.8640')
    error_str     : str   — pick uncertainty in seconds (e.g. '0.05e+00')
    pick_origin   : str   — source label appended in trailer (e.g. 'TEMP_OBS')
    """
    code        = internal_code.ljust(9)
    instrument  = '?'.ljust(4)
    component   = '?'.ljust(4)
    onset       = '?'.ljust(1)
    phase_field = phase.ljust(6)
    direction   = '?'.ljust(1)
    error_type  = 'GAU'.ljust(3)
    seconds     = f"{float(seconds_str):06.3f}"
    error_mag   = f"{float(error_str):.2f}".ljust(9)
    coda_dur    = '-1.00e+00'.ljust(9)
    amp         = '-1.00e+00'.ljust(9)
    period      = '-1.00e+00'.ljust(9)
    real_phase  = phase.ljust(6)
    channel     = 'None'.ljust(4)
    origin      = pick_origin.ljust(9)
    pgv         = 'None'.ljust(4)

    return (
        f"{code} {instrument} {component} {onset} {phase_field} {direction} "
        f"{date} {hhmm} {seconds} {error_type} {error_mag} {coda_dur} {amp} {period}"
        f" # {real_phase} {channel} {origin} {pgv}"
    )


# ---------------------------------------------------------------------------
# Format handlers
# ---------------------------------------------------------------------------

def convert_temp_obs(line, code_map):
    """
    Convert a single pick line from TEMP_OBS format to GLOBAL.obs format.

    TEMP_OBS source format (space-delimited):
        STATION ? ? ? PHASE ? YYYYMMDD HHMM SS.SSSS GAU E.EEe+EE -1.00e+00 -1.00e+00 -1.00e+00

    Returns the converted line string, or None if the station cannot be resolved.
    """
    parts = line.split()
    if len(parts) < 11:
        return None

    short_name  = parts[0]
    phase       = parts[4]
    date        = parts[6]   # YYYYMMDD
    hhmm        = parts[7]   # HHMM
    seconds_str = parts[8]   # SS.SSSS
    error_str   = parts[10]  # E.EEe+EE (e.g. 0.05e+00)

    internal_code = resolve_station(short_name, date, code_map)
    if internal_code is None:
        logger.warning(f"Station '{short_name}' not found in code map. Skipping.")
        return None

    return _format_pick_line(internal_code, phase, date, hhmm, seconds_str, error_str, 'TEMP_OBS')


# ---------------------------------------------------------------------------
# Format dispatch table — register new format handlers here
# ---------------------------------------------------------------------------

FORMAT_HANDLERS = {
    'TEMP_OBS': convert_temp_obs,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MODULE_DIR      = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CODEMAP = os.path.join(_MODULE_DIR, '..', 'stations', 'GLOBAL_code_map.txt')
_DEFAULT_LOG_DIR = os.path.join(_MODULE_DIR, 'console_output')


def _setup_logger(log_dir, input_path):
    """
    Configure the module logger to write to a timestamped file in log_dir.

    The log file is named after the input file basename plus a timestamp,
    e.g. viehla_final_20260413_153042.log. Any existing handlers are removed
    so repeated calls (e.g. in a notebook) don't accumulate handlers.
    """
    os.makedirs(log_dir, exist_ok=True)

    basename   = os.path.splitext(os.path.basename(input_path))[0]
    timestamp  = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path   = os.path.join(log_dir, f"{basename}_{timestamp}.log")

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)

    return log_path


def convert_file(input_path, fmt, output_path=None, codemap_path=None, log_dir=None):
    """
    Convert a pick file to GLOBAL.obs pick line format.

    Parameters
    ----------
    input_path : str
        Path to the source pick file (e.g. 'temp_picks/pick_files/viehla_final.obs').
    fmt : str
        Source format type. Must be a key in FORMAT_HANDLERS (e.g. 'TEMP_OBS').
    output_path : str, optional
        Destination file path. Defaults to input path with '_converted.obs' suffix.
    codemap_path : str, optional
        Path to GLOBAL_code_map.txt. Defaults to stations/GLOBAL_code_map.txt
        relative to this module's location.
    log_dir : str, optional
        Directory where the log file is written. Defaults to temp_picks/console_output/.

    Returns
    -------
    dict
        Summary with keys: 'output', 'log', 'n_input', 'n_converted', 'n_skipped'.

    Raises
    ------
    ValueError
        If fmt is not a supported format.

    Examples
    --------
    >>> from temp_picks.convert_picks import convert_file
    >>> result = convert_file('temp_picks/pick_files/viehla_final.obs', 'TEMP_OBS')
    >>> print(result)
    """
    if fmt not in FORMAT_HANDLERS:
        raise ValueError(f"Unknown format '{fmt}'. Supported: {', '.join(FORMAT_HANDLERS)}")

    codemap_path = codemap_path or _DEFAULT_CODEMAP
    log_path     = _setup_logger(log_dir or _DEFAULT_LOG_DIR, input_path)

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + '_converted.obs'

    logger.info(f"Loading station code map: {codemap_path}")
    code_map = load_code_map(codemap_path)
    logger.info(f"{sum(len(v) for v in code_map.values())} entries for {len(code_map)} unique station names.")

    fmt_handler = FORMAT_HANDLERS[fmt]
    converted   = []
    n_input     = 0
    n_skipped   = 0

    with open(input_path, 'r') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            n_input += 1
            result = fmt_handler(line, code_map)
            if result is not None:
                converted.append(result)
            else:
                n_skipped += 1

    with open(output_path, 'w') as f:
        for line in converted:
            f.write(line + '\n')

    logger.info(f"Input pick lines : {n_input}")
    logger.info(f"Converted        : {len(converted)}")
    logger.info(f"Skipped          : {n_skipped}")
    logger.info(f"Output           : {output_path}")

    return {
        'output':      output_path,
        'log':         log_path,
        'n_input':     n_input,
        'n_converted': len(converted),
        'n_skipped':   n_skipped,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert pick files to GLOBAL.obs pick line format.'
    )
    parser.add_argument(
        '--input', required=True,
        help='Path to the input pick file (e.g. Pyrocko/pick_files/viehla_final.obs)'
    )
    parser.add_argument(
        '--format', required=True, choices=list(FORMAT_HANDLERS.keys()),
        help=f'Source format type. Supported: {", ".join(FORMAT_HANDLERS.keys())}'
    )
    parser.add_argument(
        '--output', default=None,
        help='Output file path. Default: input path with _converted.obs suffix.'
    )
    parser.add_argument(
        '--codemap', default=None,
        help='Path to GLOBAL_code_map.txt. Default: stations/GLOBAL_code_map.txt relative to project root.'
    )
    parser.add_argument(
        '--log-dir', default=None,
        help='Directory for log files. Default: temp_picks/console_output/.'
    )
    args = parser.parse_args()
    convert_file(args.input, args.format, output_path=args.output, codemap_path=args.codemap, log_dir=args.log_dir)


if __name__ == '__main__':
    main()
