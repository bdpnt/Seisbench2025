from parameters import Parameters
import fetch_inventory

# Merge into the global inventory
params_merge = Parameters(
    folderPath = 'stations/*/*.xml',
    fileSaveInventory = 'stations/GLOBAL_inventory.xml',
    fileSaveMapping = 'stations/GLOBAL_code_mapping.txt',
    acceptedDistance = 20, # in m, accepted distance between two stations considered as similar
)

fetch_inventory.fusion.mergeInventory(params_merge)