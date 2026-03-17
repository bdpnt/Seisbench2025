'''
gen_second_run_files generates the run.in file using the LOCDELAY from the first run
'''

import pandas as pd

def genRun(parameters):
    # Fetch stations corrections
    locStatCorr = parameters.locFolderName + '/last.stat_totcorr'
    with open(locStatCorr, 'r') as f:
        lines = f.readlines()

    statCorr = [line.split()[1:6] for line in lines if line.startswith('LOCDELAY')]
    statCorr_df = pd.DataFrame(
        statCorr,
        columns=['StationCode','PhaseType','PhaseNum','TotCorr','StdDev']
    )
    statCorr_df = statCorr_df.astype({
        'StationCode':'str',
        'PhaseType':'str',
        'PhaseNum':'int32',
        'TotCorr':'float64',
        'StdDev':'float64',
    })

    idx = statCorr_df[(statCorr_df.PhaseNum >= parameters.minPhases) & (statCorr_df.StdDev >= 0)].index
    statCorr_list =  [lines[i+3] for i in idx] 

    # Add stations corrections to the run file
    with open(parameters.fileRunName, 'r') as f:
        lines = f.readlines()
    
    lines.append('# Stations TotCorr\n')
    lines.extend(statCorr_list)

    with open(parameters.fileRunSave, 'w') as f:
        f.writelines(lines)
    
    print(f'\nSuccesfully saved run file @ {parameters.fileRunSave}')
    print(f'    - using parameters from run file @ {parameters.fileRunName}')
    print(f'    - using stations corrections from file @ {locStatCorr}\n')
    