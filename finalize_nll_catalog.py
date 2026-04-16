from NLL_run.parse_nll_output import CleanPostRunParams
from NLL_run.match_pre_post_relocation import MatchCatalogsParams
import NLL_run
import subprocess

# Clean the files post-run
for key in range(1,7):
    params_clean = CleanPostRunParams(
        folderLoc = f'loc/GLOBAL_{key}',
        obsFile = f'GLOBAL_{key}.obs',
        fileBulletin = f'RESULT/GLOBAL_{key}_PR.txt',
    )

    NLL_run.parse_nll_output.write_events(params_clean)

# Generate the FINAL.txt file
result_files = [f"RESULT/GLOBAL_{key}_PR.txt" for key in range(1, 7)]
file_out = "RESULT/FINAL.txt"
log_file = "RESULT/FINAL.log"

with open(log_file, 'w') as f:
    command = [
        "conda", "run", "-n", "seisbench_env",
        "python", "NLL_run/merge_regional_results.py",
        *result_files,
        "-o", file_out,
    ]

    subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True)
    print(f'Bulletin succesfully saved @ {file_out}')
    print(f'Log succesfully saved @ {log_file}')

# Match events pre/post NLL
params_final = MatchCatalogsParams(
    file_obs = 'obs/GLOBAL.obs',
    file_final = 'RESULT/FINAL.txt',
    save_file = 'obs/FINAL.obs',
)

NLL_run.match_pre_post_relocation.save_bulletin(params_final)