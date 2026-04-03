from NLL_run.clean_post_run import CleanPostRunParams
from NLL_run.gen_second_run_files import SecondRunParams
import NLL_run

# Clean the files post-run
for key in range(1,7):
    params_clean = CleanPostRunParams(
        folderLoc = f'loc/GLOBAL_{key}',
        obsFile = f'GLOBAL_{key}.obs',
        fileBulletin = f'RESULT/GLOBAL_{key}.txt',
    )

    NLL_run.clean_post_run.writeEvents(params_clean)

    # Generate the SSST run files (for now, only second normal NLL run)
    params_ssst_W = SecondRunParams(
        locFolderName = f'loc/GLOBAL_{key}', # loc folder to use
        fileRunName = f'run/run_{key}.in', # run file to use
        fileRunSave = f'run/run_{key}_PR.in', # run file to generate
        minPhases = 100, # minimal number of phases for the delay to be used
    )

    NLL_run.gen_second_run_files.genRun(params_ssst_W)