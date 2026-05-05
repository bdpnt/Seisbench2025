"""
merge_station_inventories.py
============================
Merge all station XML inventories into a single unified inventory with
unique alternate station codes.

Networks are deduplicated, stations that are within accepted_distance metres
of each other receive the same alternate code, and an alternate-code mapping
file is written alongside the unified StationXML.

Usage
-----
    python fetch_inventory/merge_station_inventories.py \\
        --folder-path   "stations/*/*.xml" \\
        --save-inventory stations/GLOBAL_inventory.xml \\
        --save-mapping   stations/GLOBAL_code_map.txt \\
        --distance       20
"""

import argparse
import datetime
import logging
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime as dt

from obspy import UTCDateTime, read_inventory
from obspy.core.inventory import Inventory


logger = logging.getLogger('fetch_inventory')

_DEFAULT_LOG_DIR = 'fetch_inventory/console_output/'


def _setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    basename  = os.path.splitext(os.path.basename(__file__))[0]
    timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
    log_path  = os.path.join(log_dir, f"{basename}_{timestamp}.log")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)
    return log_path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MergeInventoryParams:
    """
    Configuration for merging station inventories.

    Attributes
    ----------
    folder_path        : str — glob pattern for input StationXML files
    file_save_inventory: str — output path for the unified StationXML
    file_save_mapping  : str — output path for the alternate-code mapping text file
    accepted_distance  : int — max distance (m) for two stations to be considered
                               the same physical site (default: 20)
    """
    folder_path:         str
    file_save_inventory: str
    file_save_mapping:   str
    accepted_distance:   int = 20


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """Return the great-circle distance in km between two lat/lon points."""
    R    = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------

def check_inventory(inventory):
    """
    Interactively prompt the user to remove duplicate stations that appear
    in multiple networks.

    Parameters
    ----------
    inventory : obspy.core.inventory.Inventory

    Returns
    -------
    obspy.core.inventory.Inventory
        Inventory with user-selected duplicates removed.
    """
    unique_sta = defaultdict(list)
    for net in inventory.networks:
        for sta in net.stations:
            unique_sta[sta.code.split('_')[0]].append(net.code)

    unique_sta = {
        sta: nets for sta, nets in unique_sta.items()
        if len(nets) >= 2 and any(net != nets[0] for net in nets)
    }

    for station, networks in unique_sta.items():
        print('\n' * 40)
        print(f"\nStation: {station}")
        for network in networks:
            current_inv = inventory.select(network=network, station=station)
            print(f"  In Network: {network}")
            for net in current_inv.networks:
                for sta in net.stations:
                    print(sta)
        print("____________________")

        remove_nets = input('Network(s) to remove, if any, separated by commas (e.g. > FR,RD): ')
        remove_nets = remove_nets.split(',')
        for network in remove_nets:
            inventory = inventory.remove(network=network, station=station)

    return inventory


def _add_alternate_code(inventory):
    """Assign a unique alternate code (NET.XXXX) to every station."""
    for network in inventory.networks:
        net_code = network.code
        sta_id   = 0
        for station in network:
            station.alternate_code = f'{net_code}.{str(sta_id).zfill(4)}'
            sta_id += 1
    return inventory


def _combine_close_stations(inventory, parameters):
    """
    Give the same alternate code to stations from different networks that
    are within accepted_distance metres of each other.
    """
    all_stations   = [(net.code, sta) for net in inventory.networks for sta in net.stations]
    threshold_km   = parameters.accepted_distance / 1000
    groups         = []

    for net_code, station in all_stations:
        target_group = next(
            (g for g in groups
             if any(haversine(station.latitude, station.longitude,
                              other.latitude, other.longitude) <= threshold_km
                    for _, other in g)),
            None,
        )
        if target_group is not None:
            target_group.append((net_code, station))
        else:
            groups.append([(net_code, station)])

    for group in groups:
        if len(group) > 1:
            oldest = min(group, key=lambda x: x[1].start_date or UTCDateTime(datetime.datetime.max))
            for _, station in group:
                if station is not oldest[1]:
                    station.alternate_code = oldest[1].alternate_code

    return inventory


def _create_alternate_code_mapping(inventory, parameters):
    """Write the alternate-code → station-code mapping file."""
    mapping = defaultdict(list)

    for network in inventory.networks:
        for station in network.stations:
            mapping[station.alternate_code].append({
                'station_code': f'{network.code}.{station.code}',
                'start_date':   station.start_date,
                'end_date':     station.end_date,
            })

    with open(parameters.file_save_mapping, 'w') as f:
        for alt_code, stations in mapping.items():
            f.write(f'Alternate Code: {alt_code}\n')
            for sta in stations:
                f.write(f"  Station Code: {sta['station_code']}\n")
                f.write(f"  Start Date: {sta['start_date']}\n")
                f.write(f"  End Date: {sta['end_date']}\n")
            f.write('\n')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_inventory(parameters, log_dir=None):
    """
    Merge all station XML inventories into a single unified inventory.

    Steps: load all XMLs → merge duplicate networks → merge duplicate
    stations within each network → interactive duplicate check →
    assign unique alternate codes → combine co-located stations →
    write unified StationXML and mapping file.

    Parameters
    ----------
    parameters : MergeInventoryParams
    log_dir    : str, optional — log directory; default: fetch_inventory/console_output/

    Returns
    -------
    dict with keys: output (inventory path), mapping (mapping path)
    """
    import glob

    log_path = _setup_logger(log_dir or _DEFAULT_LOG_DIR)
    logger.info(f"Log file             : {log_path}")
    logger.info(f"Input glob           : {parameters.folder_path}")
    logger.info(f"Co-location threshold: {parameters.accepted_distance} m")

    inventory    = Inventory()
    loaded_files = glob.glob(parameters.folder_path)
    for folder_file in loaded_files:
        inventory.extend(read_inventory(folder_file, format='STATIONXML'))

    logger.info(f"Inventory files loaded: {len(loaded_files)}")
    logger.info(f"Networks before merge : {len(inventory.networks)}")

    # --- Merge duplicate networks ---
    all_networks       = [net.code for net in inventory.networks]
    duplicate_networks = [code for code, count in Counter(all_networks).items() if count > 1]

    if duplicate_networks:
        logger.info(f"Duplicate networks to merge: {duplicate_networks}")
    for net_code in duplicate_networks:
        found = [net for net in inventory.networks if net.code == net_code]
        main  = found[0]
        n_merged = 0
        for sub in found[1:]:
            for station in sub:
                main.stations.append(station)
                n_merged += 1
            inventory.networks.remove(sub)
        logger.info(f"  Network {net_code}: merged {n_merged} station(s) from {len(found) - 1} duplicate(s)")

    # --- Merge duplicate stations within each network ---
    total_stations_dropped = 0
    for network in inventory.networks:
        station_groups = defaultdict(list)
        for sta in network.stations:
            station_groups[sta.code].append(sta)

        for _, same_code_stations in station_groups.items():
            if len(same_code_stations) <= 1:
                continue

            same_code_stations.sort(
                key=lambda s: getattr(s, 'start_date', None) or UTCDateTime(datetime.datetime.max)
            )

            n     = len(same_code_stations)
            graph = defaultdict(list)
            for i in range(n):
                for j in range(i + 1, n):
                    s1, s2 = same_code_stations[i], same_code_stations[j]
                    if haversine(s1.latitude, s1.longitude,
                                 s2.latitude, s2.longitude) <= parameters.accepted_distance / 1000:
                        graph[i].append(j)
                        graph[j].append(i)

            visited  = [False] * n
            clusters = []
            for i in range(n):
                if not visited[i]:
                    cluster_idx = []
                    stack = [i]
                    visited[i] = True
                    while stack:
                        node = stack.pop()
                        cluster_idx.append(node)
                        for nb in graph.get(node, []):
                            if not visited[nb]:
                                visited[nb] = True
                                stack.append(nb)
                    clusters.append([same_code_stations[k] for k in cluster_idx])

            for it, cluster in enumerate(clusters):
                if len(cluster) <= 1:
                    cluster[0].code = f'{cluster[0].code}_{it}'
                    continue

                main_sta   = min(cluster, key=lambda s: getattr(s, 'start_date', None) or UTCDateTime(datetime.datetime.max))
                main_index = cluster.index(main_sta)

                if len(clusters) > 1:
                    main_sta.code = f'{main_sta.code}_{it}'

                to_remove = [s for i, s in enumerate(cluster) if i != main_index]

                logger.info(
                    f"  {network.code}.{main_sta.code}: merged cluster of {len(cluster)}, "
                    f"dropped {len(to_remove)} duplicate(s)"
                )

                for sta in to_remove:
                    if (main_sta.elevation == 0 or main_sta.elevation is None) and sta.elevation:
                        main_sta.elevation = sta.elevation
                    if hasattr(sta, 'start_date') and sta.start_date is not None:
                        current = getattr(main_sta, 'start_date', None)
                        if current is None or sta.start_date < current:
                            main_sta.start_date = sta.start_date
                    if hasattr(sta, 'end_date'):
                        current = getattr(main_sta, 'end_date', None)
                        if sta.end_date is None:
                            main_sta.end_date = None
                        elif current is not None and sta.end_date > current:
                            main_sta.end_date = sta.end_date
                    for channel in sta.channels:
                        if channel not in main_sta.channels:
                            main_sta.channels.append(channel)

                for sta in to_remove:
                    if sta in network.stations:
                        network.stations.remove(sta)
                total_stations_dropped += len(to_remove)

    logger.info(f"Station deduplication: {total_stations_dropped} station(s) dropped total")

    inventory = check_inventory(inventory)
    inventory = _add_alternate_code(inventory)
    inventory = _combine_close_stations(inventory, parameters)

    n_total_stations = sum(len(net.stations) for net in inventory.networks)
    inventory.write(parameters.file_save_inventory, format='STATIONXML')
    logger.info(f"Inventory saved: {parameters.file_save_inventory}")
    logger.info(f"  Networks : {len(inventory.networks)}")
    logger.info(f"  Stations : {n_total_stations}")

    _create_alternate_code_mapping(inventory, parameters)
    logger.info(f"Alternate code mapping saved: {parameters.file_save_mapping}")

    return {
        'output':  parameters.file_save_inventory,
        'mapping': parameters.file_save_mapping,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Merge all station XML inventories into a single unified inventory.'
    )
    parser.add_argument('--folder-path',    required=True, help='Glob pattern for input StationXML files')
    parser.add_argument('--save-inventory', required=True, help='Output unified StationXML path')
    parser.add_argument('--save-mapping',   required=True, help='Output alternate-code mapping path')
    parser.add_argument('--distance',       type=int, default=20,
                        help='Max distance (m) for co-location (default: 20)')
    args = parser.parse_args()

    params = MergeInventoryParams(
        folder_path         = args.folder_path,
        file_save_inventory = args.save_inventory,
        file_save_mapping   = args.save_mapping,
        accepted_distance   = args.distance,
    )
    merge_inventory(params)


if __name__ == '__main__':
    main()
