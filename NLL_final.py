from parameters import Parameters
import NLL_run
import subprocess

# # Clean the files post-run
# for key in range(1,7):
#     params_clean = Parameters(
#         folderLoc = f'loc/GLOBAL_{key}',
#         obsFile = f'GLOBAL_{key}.obs',
#         fileBulletin = f'RESULT/GLOBAL_{key}_PR.txt',
#     )

#     NLL_run.clean_post_run.writeEvents(params_clean)

# # Generate the FINAL.txt file
# params_merge = Parameters(
#     file1="RESULT/GLOBAL_1_PR.txt",
#     file2="RESULT/GLOBAL_2_PR.txt",
#     file3="RESULT/GLOBAL_3_PR.txt",
#     file4="RESULT/GLOBAL_4_PR.txt",
#     file5="RESULT/GLOBAL_5_PR.txt",
#     file6="RESULT/GLOBAL_6_PR.txt",
#     file_out="RESULT/FINAL.txt",
#     log_file="RESULT/FINAL.log"
# )

# with open(params_merge.log_file, 'w') as f:
#     command = [
#         "conda",
#         "run",
#         "-n",
#         "seisbench_env",
#         "python",
#         "NLL_run/merge_catalogs.py",
#         params_merge.file1,
#         params_merge.file2,
#         params_merge.file3,
#         params_merge.file4,
#         params_merge.file5,
#         params_merge.file6,
#         "-o",
#         params_merge.file_out,
#     ]

#     subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True)
#     print(f'Bulletin succesfully saved @ {params_merge.file_out}')
#     print(f'Log succesfully saved @ {params_merge.log_file}')

# # Match events pre/post NLL
# params_final = Parameters(
#     file_obs = 'obs/GLOBAL.obs',
#     file_final = 'RESULT/FINAL.txt',
#     save_file = 'obs/FINAL.obs',
# )

# NLL_run.match_catalogs.save_bulletin(params_final)

# Generate the maps
subprocess.run(["conda", "run", "-n", "pygmt_env", "python", "NLL_run/map_post_run.py"], check=True)