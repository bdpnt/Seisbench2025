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
    file_name1  = 'obs/RESIF_20-25.obs',
    file_name2  = 'obs/LDG_20-25.obs',
    mag_type1   = 'MLv',
    mag_type2   = 'ML',
    mag_name1   = 'MLv RESIF',
    mag_name2   = 'ML LDG',
    dist_thresh = 10.0,
    time_thresh = 2.0,
    save_name   = 'MAGMODELS/MLv RESIF.joblib',
    save_figs   = 'MAGMODELS/FIGURES/',
)

global_obs.generate_magnitude_models.convert_magnitudes(params_magModel_RESIF, save_figs=True)

params_magModel_IGN = MagModelParams(
    file_name1  = 'obs/IGN_20-25.obs',
    file_name2  = 'obs/LDG_20-25.obs',
    mag_type1   = 'mb_Lg',
    mag_type2   = 'ML',
    mag_name1   = 'mb_Lg IGN',
    mag_name2   = 'ML LDG',
    dist_thresh = 10.0,
    time_thresh = 2.0,
    save_name   = 'MAGMODELS/MLv RESIF.joblib',
    save_figs   = 'MAGMODELS/FIGURES/',
)

global_obs.generate_magnitude_models.convert_magnitudes(params_magModel_IGN, save_figs=True)

params_magModel_ICGC = MagModelParams(
    file_name1  = 'obs/ICGC_20-25.obs',
    file_name2  = 'obs/LDG_20-25.obs',
    mag_type1   = 'ML',
    mag_type2   = 'ML',
    mag_name1   = 'ML ICGC',
    mag_name2   = 'ML LDG',
    dist_thresh = 10.0,
    time_thresh = 2.0,
    save_name   = 'MAGMODELS/MLv RESIF.joblib',
    save_figs   = 'MAGMODELS/FIGURES/',
)

global_obs.generate_magnitude_models.convert_magnitudes(params_magModel_ICGC, save_figs=True)

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