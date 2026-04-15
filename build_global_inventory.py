from fetch_inventory.merge_station_inventories import MergeInventoryParams
import fetch_inventory

# Merge into the global inventory
params_merge = MergeInventoryParams(
    folder_path         = 'stations/*/*.xml',
    file_save_inventory = 'stations/GLOBAL_inventory.xml',
    file_save_mapping   = 'stations/GLOBAL_code_mapping.txt',
    accepted_distance   = 20,  # in metres
)

fetch_inventory.merge_station_inventories.merge_inventory(params_merge)
