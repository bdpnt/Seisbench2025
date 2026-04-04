from global_obs.remap_picks_to_unified_codes import AssociatePicksParams
from global_obs.generate_magnitude_models import MagModelParams
from global_obs.apply_magnitude_models import UpdateMagFilesParams
from global_obs.fuse_bulletins import FusionParams, MergeDoublesParams
import global_obs
import subprocess

# Associate picks
params_association = AssociatePicksParams(
    fileInventory = 'stations/GLOBAL_inventory.xml',
    folderBulletin = 'obs/*.obs',
)

global_obs.remap_picks_to_unified_codes.associatePicks(params_association)

# Generate magnitude models
params_magModel_RESIF = MagModelParams(
    fileName1 = 'obs/RESIF_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'MLv', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'MLv RESIF', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
    saveName = 'MAGMODELS/MLv RESIF.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_magnitude_models.convertMagnitudes(params_magModel_RESIF, printFigs=True)

params_magModel_IGN = MagModelParams(
    fileName1 = 'obs/IGN_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'mb_Lg', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'mb_Lg IGN', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
    saveName = 'MAGMODELS/MLv RESIF.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_magnitude_models.convertMagnitudes(params_magModel_IGN, printFigs=True)

params_magModel_ICGC = MagModelParams(
    fileName1 = 'obs/ICGC_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'ML', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'ML ICGC', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
    saveName = 'MAGMODELS/MLv RESIF.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_magnitude_models.convertMagnitudes(params_magModel_ICGC, printFigs=True)

# Use magnitude models
parameters_magModels = UpdateMagFilesParams(
    folderPath = 'obs/*_20-25.obs', # use model for those files
)

global_obs.apply_magnitude_models.updateAllFiles(parameters_magModels)

# Update bulletins AOI
subprocess.run(["conda", "run", "-n", "pygmt_env", "python", "global_obs/filter_events_by_aoi.py"], check=True)

# Fusion all bulletins
params_fusion = FusionParams(
    globalBulletinPath = 'obs/GLOBAL.obs',
    mainBulletinPath = 'obs/RESIF_20-25.obs',
    folderPath = 'obs/*.obs',
    distThresh = 15, # in km
    looseDistThresh = 50, # in km
    timeThresh = 2, # in seconds
    looseTimeThresh = 30, # in seconds
    magThresh = 1.5, # magnitude
    simPickThresh = 2, # minimal number of picks to confirm match from possible matches if no thresholds
)

global_obs.fuse_bulletins.fusionAll(params_fusion)
subprocess.run(["conda", "run", "-n", "pygmt_env", "python", "global_obs/plot_global_catalog_map.py"], check=True)

# Check for potential doubles that came from the same Bulletin
params_merge_doubles = MergeDoublesParams(
    globalBulletinPath = 'obs/GLOBAL.obs',
    max_dt_seconds = 1.0,
    max_dist_km = 50.0,
)

global_obs.fuse_bulletins.find_and_merge_doubles(params_merge_doubles)