from parameters import Parameters
import NLL_run

# Remove far picks
params_farpicks = Parameters(
    fileBulletin = 'obs/GLOBAL.obs',
    fileInventory = 'stations/GLOBAL_inventory.xml',
    maxDistance = 80, # max distance between event and station, in kilometers
)

# NLL_run.remove_far_picks.removeFarPicks(params_farpicks)

# Generate run files
all_runs = {
    "1": ((42.50, -2.00), (43.50, -0.75)),
    "2": ((42.50, -1.00), (43.25, 0.50)),
    "3": ((42.00, 0.25), (43.25, 1.00)),
    "4": ((42.00, 0.75), (43.00, 2.25)),
    "5": ((42.00, 2.00), (43.00, 3.50)),
    "6": ((42.75, 2.25), (43.75, 3.50)),
}

for key,item in all_runs.items():
    params_run = Parameters(
        fileBulletin = "obs/GLOBAL.obs", # GLOBAL OBS file to use
        fileInventory = 'stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
        fileMap = 'stations/GLOBAL_code_map.txt', # AlternateCodes map file to use
        fileBulletinIn = f'obs/GLOBAL_{key}.obs', # child OBS events file to generate
        fileStations = f'stations/GTSRCE_{key}.txt', # GTSRCE stations file to generate
        fileRunSave = f'run/run_{key}.in', # run file to generate
        latMin_event = item[0][0], # minimum latitude for the event box
        latMax_event = item[1][0], # maximum latitude for the event box
        lonMin_event = item[0][1], # minimum longitude for the event box
        lonMax_event = item[1][1], # maximum longitude for the event box
        fileModel = f'model/Pyrenees_{key}/Pyrenees_{key}', # model file to generate
        fileTime = f'time/Pyrenees_{key}/Pyrenees_{key}', # time file to generate
        fileBulletinOut = f'loc/GLOBAL_{key}/GLOBAL_{key}.obs', # loc file to generate
        VGGRID = [9000,800], # VGGRID h/v parameters
    )

    NLL_run.gen_run_files.genRun(params_run) # Generate the run file

    print()
