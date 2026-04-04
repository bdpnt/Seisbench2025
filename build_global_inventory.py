from fetch_inventory.merge_station_inventories import MergeInventoryParams
import fetch_inventory

# Merge into the global inventory
params_merge = MergeInventoryParams(
    folderPath = 'stations/*/*.xml',
    fileSaveInventory = 'stations/GLOBAL_inventory.xml',
    fileSaveMapping = 'stations/GLOBAL_code_mapping.txt',
    acceptedDistance = 20, # in m, accepted distance between two stations considered as similar
)

fetch_inventory.merge_station_inventories.mergeInventory(params_merge)