import sys
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from NLL_run.parse_nll_output import CleanPostRunParams
# from global_obs import fuse_bulletins as fusion_obs
from NLL_run import filter_distant_picks as removeFarPicks_nll
from NLL_run import generate_regional_runfiles as genRunFiles_nll
from NLL_run import parse_nll_output as cleanPost_nll
# import subprocess

# # Fusion all bulletins
# params_fusion = Parameters(
#     globalBulletinPath = 'obs/GLOBAL.obs',
#     mainBulletinPath = '../obs/RESIF_20-25.obs',
#     folderPath = '../obs/*.obs',
#     distThresh = 15, # in km
#     looseDistThresh = 50, # in km
#     timeThresh = 2, # in seconds
#     looseTimeThresh = 30, # in seconds
#     magThresh = 1.5, # magnitude
#     simPickThresh = 2, # minimal number of picks to confirm match from possible matches if no thresholds
# )

# fusion_obs.fusionAll(params_fusion)

# # Remove far picks
# params_farpicks = Parameters(
#     fileBulletin = 'obs/GLOBAL_200.obs',
#     fileInventory = '../stations/GLOBAL_inventory.xml',
#     maxDistance = 200, # max distance between event and station, in kilometers
# )

# removeFarPicks_nll.removeFarPicks(params_farpicks)

# # Generate run file
# params_run_W = Parameters(
#     fileBulletin = "obs/GLOBAL_200.obs", # GLOBAL OBS file to use
#     fileInventory = '../stations/GLOBAL_inventory.xml', # GLOBAL inventory file to use
#     fileMap = '../stations/GLOBAL_code_mapping.txt', # AlternateCodes map file to use
#     fileBulletinIn = "obs/GLOBAL_W_200.obs", # child OBS events file to generate
#     fileStations = 'stations/GTSRCE_W_200.txt', # GTSRCE stations file to generate
#     fileRunSave = 'run/run_W_200.in', # run file to generate
#     latMin_event = 42.6, # minimum latitude for the event box
#     latMax_event = 43.3, # maximum latitude for the event box
#     lonMin_event = -2.0, # minimum longitude for the event box
#     lonMax_event = 0.5, # maximum longitude for the event box
#     fileModel = 'model/Pyrenees_W_200/Pyrenees_W_200', # model file to generate
#     fileTime = 'time/Pyrenees_W_200/Pyrenees_W_200', # time file to generate
#     fileBulletinOut = 'loc/GLOBAL_W_200/GLOBAL_W_200.obs', # loc file to generate
#     latMin_box = 42.15, # minimum latitude for the main box
#     lonMin_box = -3.2, # minimum longitude for the main box
#     VGGRID = [9000,800], # VGGRID h/v parameters
#     LOCGRID = [8000,3500,800], # LOCGRID E/W ; N/S ; U/D parameters
# )

# genRunFiles_nll.genRun(params_run_W) # Generate the run file

# Clean the files post-run
params_clean_W = CleanPostRunParams(
    folderLoc = 'loc/GLOBAL_W_200',
    obsFile = 'GLOBAL_W_200.obs',
    fileBulletin = 'RESULT/GLOBAL_W_200.txt',
)

cleanPost_nll.writeEvents(params_clean_W)