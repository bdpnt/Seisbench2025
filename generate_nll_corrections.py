from NLL_run.parse_nll_output import CleanPostRunParams
from NLL_run.append_station_delays import SecondRunParams
from NLL_run.export_locdelay_info import export_locdelay_info
import NLL_run

# For all areas
for key in range(1,7):
    # Clean the files post-run
    params_clean = CleanPostRunParams(
        folderLoc = f'loc/GLOBAL_{key}',
        obsFile = f'GLOBAL_{key}.obs',
        fileBulletin = f'RESULT/GLOBAL_{key}.txt',
    )

    NLL_run.parse_nll_output.write_events(params_clean)

    # Generate the second-pass run file
    params_ssst_W = SecondRunParams(
        locFolderName = f'loc/GLOBAL_{key}', # loc folder to use
        fileRunName = f'run/run_{key}.in', # run file to use
        fileRunSave = f'run/run_{key}_PR.in', # run file to generate
        # newObsFile = f'obs/GLOBAL_{key}_temp.obs', # new obs file to use (updated with temporary networks phase picks)
        minPhases = 100, # minimal number of phases for the delay to be used
    )

    NLL_run.append_station_delays.append_station_delays(params_ssst_W)

# Export the locdelays
export_locdelay_info(
    run_dir      = 'run',
    codemap_path = 'stations/GLOBAL_code_map.txt',
    output_path  = 'run/locdelays/locdelay_summary.txt',
)
