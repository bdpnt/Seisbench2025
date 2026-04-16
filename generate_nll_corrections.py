from NLL_run.parse_nll_output import CleanPostRunParams
from NLL_run.append_station_delays import SecondRunParams
import NLL_run
# from global_obs.add_temporary_picks import RemapStationCodesParams,MergeExternalPicksParams
# from global_obs.add_temporary_picks import remapStationCodes,mergeExternalPicks

# # Add phase picks from temporary networks
# params_remap = RemapStationCodesParams(
#     inputPath='obs/viehla_picks.obs',
#     outputPath='obs/viehla_picks_updated.obs',
#     inventoryPath='stations/GLOBAL_inventory.xml'
# )

# remapStationCodes(params_remap)

# params_merge = MergeExternalPicksParams(
#     globalPath='obs/GLOBAL.obs',
#     temporaryPath='obs/viehla_picks_updated.obs',
#     outputPath='obs/GLOBAL_&temporary.obs'
# )

# mergeExternalPicks(params_merge)

# Clean the files post-run
for key in range(1,7):
    params_clean = CleanPostRunParams(
        folderLoc = f'loc/GLOBAL_{key}',
        obsFile = f'GLOBAL_{key}.obs',
        fileBulletin = f'RESULT/GLOBAL_{key}.txt',
    )

    NLL_run.parse_nll_output.write_events(params_clean)

    # Generate the SSST run files (for now, only second normal NLL run)
    params_ssst_W = SecondRunParams(
        locFolderName = f'loc/GLOBAL_{key}', # loc folder to use
        fileRunName = f'run/run_{key}.in', # run file to use
        fileRunSave = f'run/run_{key}_PR.in', # run file to generate
        # newObsFile = f'obs/GLOBAL_{key}_temp.obs', # new obs file to use (updated with temporary networks phase picks)
        minPhases = 100, # minimal number of phases for the delay to be used
    )

    NLL_run.append_station_delays.append_station_delays(params_ssst_W)