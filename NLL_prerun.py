from parameters import Parameters
import NLL_run

# Remove far picks
params_farpicks = Parameters(
    fileBulletin = 'obs/GLOBAL.obs',
    fileInventory = 'stations/GLOBAL_inventory.xml',
    maxDistance = 80, # max distance between event and station, in kilometers
)

NLL_run.remove_far_picks.removeFarPicks(params_farpicks)

# Generate run files
params_run_W = Parameters(
    fileBulletin = "obs/GLOBAL.obs", # GLOBAL OBS file to use
    fileInventory = 'stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
    fileMap = 'stations/GLOBAL_code_mapping.txt', # AlternateCodes map file to use
    fileBulletinIn = "obs/GLOBAL_W.obs", # child OBS events file to generate
    fileStations = 'stations/GTSRCE_W.txt', # GTSRCE stations file to generate
    fileRunSave = 'run/run_W.in', # run file to generate
    latMin_event = 42.6, # minimum latitude for the event box
    latMax_event = 43.3, # maximum latitude for the event box
    lonMin_event = -2.0, # minimum longitude for the event box
    lonMax_event = 0.5, # maximum longitude for the event box
    fileModel = 'model/Pyrenees_W/Pyrenees_W', # model file to generate
    fileTime = 'time/Pyrenees_W/Pyrenees_W', # time file to generate
    fileBulletinOut = 'loc/GLOBAL_W/GLOBAL_W.obs', # loc file to generate
    latMin_box = 42.15, # minimum latitude for the main box
    lonMin_box = -3.2, # minimum longitude for the main box
    VGGRID = [9000,800], # VGGRID h/v parameters
    LOCGRID = [8000,3500,800], # LOCGRID E/W ; N/S ; U/D parameters
)

NLL_run.gen_run_files.genRun(params_run_W) # Generate the run file

params_run_C = Parameters(
    fileBulletin = "obs/GLOBAL.obs", # GLOBAL OBS file to use
    fileInventory = 'stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
    fileMap = 'stations/GLOBAL_code_mapping.txt', # AlternateCodes map file to use
    fileBulletinIn = "obs/GLOBAL_C.obs", # child OBS events file to generate
    fileStations = 'stations/GTSRCE_C.txt', # GTSRCE stations file to generate
    fileRunSave = 'run/run_C.in', # run file to generate
    latMin_event = 42.0, # minimum latitude for the event box
    latMax_event = 43.3, # maximum latitude for the event box
    lonMin_event = 0.0, # minimum longitude for the event box
    lonMax_event = 2.0, # maximum longitude for the event box
    fileModel = 'model/Pyrenees_C/Pyrenees_C', # model file to generate
    fileTime = 'time/Pyrenees_C/Pyrenees_C', # time file to generate
    fileBulletinOut = 'loc/GLOBAL_C/GLOBAL_C.obs', # loc file to generate
    latMin_box = 41.55, # minimum latitude for the main box
    lonMin_box = -1.2, # minimum longitude for the main box
    VGGRID = [9000,800], # VGGRID h/v parameters
    LOCGRID = [7200,4800,800], # LOCGRID E/W ; N/S ; U/D parameters
)

NLL_run.gen_run_files.genRun(params_run_C) # Generate the run file

params_run_E = Parameters(
    fileBulletin = "obs/GLOBAL.obs", # GLOBAL OBS file to use
    fileInventory = 'stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
    fileMap = 'stations/GLOBAL_code_mapping.txt', # AlternateCodes map file to use
    fileBulletinIn = "obs/GLOBAL_E.obs", # child OBS events file to generate
    fileStations = 'stations/GTSRCE_E.txt', # GTSRCE stations file to generate
    fileRunSave = 'run/run_E.in', # run file to generate
    latMin_event = 42.0, # minimum latitude for the event box
    latMax_event = 43.25, # maximum latitude for the event box
    lonMin_event = 1.5, # minimum longitude for the event box
    lonMax_event = 3.25, # maximum longitude for the event box
    fileModel = 'model/Pyrenees_E/Pyrenees_E', # model file to generate
    fileTime = 'time/Pyrenees_E/Pyrenees_E', # time file to generate
    fileBulletinOut = 'loc/GLOBAL_E/GLOBAL_E.obs', # loc file to generate
    latMin_box = 41.55, # minimum latitude for the main box
    lonMin_box = 0.3, # minimum longitude for the main box
    VGGRID = [9000,800], # VGGRID h/v parameters
    LOCGRID = [6800,4500,800], # LOCGRID E/W ; N/S ; U/D parameters
)

NLL_run.gen_run_files.genRun(params_run_E) # Generate the run file