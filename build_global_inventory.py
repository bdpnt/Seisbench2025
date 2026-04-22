"""
build_global_inventory.py
============================
Merge all source station inventories into a single unified StationXML.

Reads all per-network XML files from stations/*/, assigns each station a
unique internal code, and writes the merged inventory and code mapping to
stations/.

Usage
-----
    python build_global_inventory.py
"""

import os

from fetch_inventory.merge_station_inventories import MergeInventoryParams
import fetch_inventory

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_STATIONS = os.path.join(_PROJECT_ROOT, 'stations')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline():
    """Merge all source station inventories into stations/GLOBAL_inventory.xml."""
    params_merge = MergeInventoryParams(
        folder_path         = os.path.join(_STATIONS, '*', '*.xml'),
        file_save_inventory = os.path.join(_STATIONS, 'GLOBAL_inventory.xml'),
        file_save_mapping   = os.path.join(_STATIONS, 'GLOBAL_code_map.txt'),
        accepted_distance   = 20,  # in metres
    )

    fetch_inventory.merge_station_inventories.merge_inventory(params_merge)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    run_pipeline()


if __name__ == '__main__':
    main()
