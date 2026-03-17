from parameters import Parameters
import global_obs

# Associate picks
params_association= Parameters(
    fileInventory = 'stations/GLOBAL_inventory.xml',
    folderBulletin = 'obs/*.obs',
)

global_obs.update_picks.associatePicks(params_association)

# Generate magnitude models
params_magModel_RESIF = Parameters(
    fileName1 = 'obs/RESIF_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'MLv', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'MLv RESIF', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
)

params_magModel_RESIF.update(
    saveName = f'MAGMODELS/{params_magModel_RESIF.magName1}.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_mag_model.convertMagnitudes(params_magModel_RESIF, printFigs=True)

params_magModel_IGN = Parameters(
    fileName1 = 'obs/IGN_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'mb_Lg', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'mb_Lg IGN', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
)

params_magModel_IGN.update(
    saveName = f'MAGMODELS/{params_magModel_RESIF.magName1}.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_mag_model.convertMagnitudes(params_magModel_IGN, printFigs=True)

params_magModel_ICGC = Parameters(
    fileName1 = 'obs/ICGC_20-25.obs', # magnitudes to convert
    fileName2 = 'obs/LDG_20-25.obs', # magnitudes to keep
    magType1 = 'ML', # magnitude type to convert from (in fileName1) ; e.g. 'mb_Lg' (without origin 'IGN')
    magType2 = 'ML', # magnitude type to convert to (in fileName2) ; e.g. 'ML' (without origin 'LDG')
    magName1 = 'ML ICGC', # magnitude name to convert from (in fileName1), for printing/model name only ; e.g. 'mb_Lg IGN' (with origin if needed)
    magName2 = 'ML LDG', # magnitude name to convert to (in fileName2), for printing/model name only ; e.g. 'ML LDG' (with origin if needed)
    distThresh = 10.0, # distance threshold between events in km
    timeThresh = 2.0, # time threshold between events in s
)

params_magModel_ICGC.update(
    saveName = f'MAGMODELS/{params_magModel_RESIF.magName1}.joblib', # model name
    saveFigs = 'MAGMODELS/FIGURES/', # figures folder
)

global_obs.generate_mag_model.convertMagnitudes(params_magModel_ICGC, printFigs=True)

# Use magnitude models
parameters_magModels = Parameters(
    folderPath = 'obs/*_20-25.obs', # use model for those files
)

global_obs.use_mag_models.updateAllFiles(parameters_magModels)

# Update bulletins AOI
params_AOI = Parameters(
    fileNames = ['obs/RESIF_20-25.obs','obs/IGN_20-25.obs','obs/ICGC_20-25.obs','obs/LDG_20-25.obs','obs/OMP_2016.obs','obs/OMP_78-19.obs'],
    figSaves = ['obs/MAPS/RESIF_20-25.pdf','obs/MAPS/IGN_20-25.pdf','obs/MAPS/ICGC_20-25.pdf','obs/MAPS/LDG_20-25.pdf','obs/MAPS/OMP_2016.pdf',
                'obs/MAPS/OMP_78-19.pdf'],
)

global_obs.update_AOI.updateBulletins(params_AOI)

# Fusion all bulletins
params_fusion = Parameters(
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

params_figure = Parameters(
    fileName = 'obs/GLOBAL.obs',
    figSave = 'obs/MAPS/GLOBAL.pdf',
)

global_obs.fusion.fusionAll(params_fusion)
global_obs.map_global.genGlobalFigure(params_figure)