from parameters import Parameters
import NLL_run

# Clean the files post-run
params_clean_W = Parameters(
    folderLoc = 'loc/GLOBAL_W',
    obsFile = 'GLOBAL_W.obs',
    fileBulletin = 'RESULT/GLOBAL_W.txt',
    figSave = 'RESULT/MAPS/GLOBAL_W.pdf',
)

NLL_run.clean_post_run.writeEvents(params_clean_W)
NLL_run.clean_post_run.genFigure(params_clean_W)

params_clean_C = Parameters(
    folderLoc = 'loc/GLOBAL_C',
    obsFile = 'GLOBAL_C.obs',
    fileBulletin = 'RESULT/GLOBAL_C.txt',
    figSave = 'RESULT/MAPS/GLOBAL_C.pdf',
)

NLL_run.clean_post_run.writeEvents(params_clean_C)
NLL_run.clean_post_run.genFigure(params_clean_C)

params_clean_E = Parameters(
    folderLoc = 'loc/GLOBAL_E',
    obsFile = 'GLOBAL_E.obs',
    fileBulletin = 'RESULT/GLOBAL_E.txt',
    figSave = 'RESULT/MAPS/GLOBAL_E.pdf',
)

NLL_run.clean_post_run.writeEvents(params_clean_E)
NLL_run.clean_post_run.genFigure(params_clean_E)

# Generate the SSST run files
params_ssst_W = Parameters(
    locFolderName = 'loc/GLOBAL_W', # loc folder to use
    fileRunName = 'run/run_W.in', # run file to use
    fileRunSave = 'run/run2_W.in', # run file to generate
    minPhases = 100
)

NLL_run.gen_second_run_files.genRun(params_ssst_W)

params_ssst_C = Parameters(
    locFolderName = 'loc/GLOBAL_C', # loc folder to use
    fileRunName = 'run/run_C.in', # run file to use
    fileRunSave = 'run/run2_C.in', # run file to generate
    minPhases = 100
)

NLL_run.gen_second_run_files.genRun(params_ssst_C)

params_ssst_E = Parameters(
    locFolderName = 'loc/GLOBAL_E', # loc folder to use
    fileRunName = 'run/run_E.in', # run file to use
    fileRunSave = 'run/run2_E.in', # run file to generate
    minPhases = 100
)

NLL_run.gen_second_run_files.genRun(params_ssst_E)