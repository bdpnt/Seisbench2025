from parameters import Parameters
import NLL_run
import subprocess

# Clean the files post-run
params_clean_W = Parameters(
    folderLoc = 'loc/GLOBAL_W',
    obsFile = 'GLOBAL_W.obs',
    fileBulletin = 'RESULT/GLOBAL_PR_W.txt',
)

NLL_run.clean_post_run.writeEvents(params_clean_W)

params_clean_C = Parameters(
    folderLoc = 'loc/GLOBAL_C',
    obsFile = 'GLOBAL_C.obs',
    fileBulletin = 'RESULT/GLOBAL_PR_C.txt',
)

NLL_run.clean_post_run.writeEvents(params_clean_C)

params_clean_E = Parameters(
    folderLoc = 'loc/GLOBAL_E',
    obsFile = 'GLOBAL_E.obs',
    fileBulletin = 'RESULT/GLOBAL_PR_E.txt',
)

NLL_run.clean_post_run.writeEvents(params_clean_E)

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

# Generate the FINAL.txt file
params_merge = Parameters(
    file1="RESULT/GLOBAL_PR_W.txt",
    file2="RESULT/GLOBAL_PR_C.txt",
    file3="RESULT/GLOBAL_PR_E.txt",
    file_out="RESULT/FINAL.txt",
    log_file="RESULT/FINAL.log"
)

with open(params_merge.log_file, 'w') as f:
    command = [
        "conda",
        "run",
        "-n",
        "seisbench_env",
        "python",
        "NLL_run/merge_catalogs.py",
        params_merge.file1,
        params_merge.file2,
        params_merge.file3,
        "-o",
        params_merge.file_out,
    ]

    subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True)

# Generate the maps
subprocess.run(["conda", "run", "-n", "pygmt_env", "python", "NLL_run/map_post_run.py"], check=True)