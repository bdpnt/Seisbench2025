'''
gen_second_run_files generates the run.in file using the LOCDELAY from the first run
'''

import pandas as pd

# def getClusters(parameters):
#     with open(parameters.fileMapping,'r') as f:
#         lines = f.readlines()

#     station_clusters = {}
#     for idx, line in enumerate(lines):
#         if line.startswith('Alt'):
#             code = line.split(': ')[1].rstrip('\n')
#             if lines[idx + 4].startswith('\n'):
#                 isCluster = False
#             else:
#                 isCluster = True
#             station_clusters[code] = isCluster

#     return station_clusters

# def isCluster(code,station_clusters):
#     return station_clusters.get(code)

# def dealWithClusters(df,parameters):
#     # Add isCluster column
#     station_clusters = getClusters(parameters)
#     df['isCluster'] = df.StationCode.apply(lambda code: isCluster(code, station_clusters))

#     # Get the idx of non-cluster stations
#     nonClusters_idx = set(df[df.isCluster == False].index)

#     # Change cluster stations so they use S-P delay (*)
#     with open(parameters.fileObs,'r') as f:
#         lines = f.readlines()
#     for idx,line in enumerate(lines):
#         if any(line.startswith(code) for code in df['StationCode']):
#             lines[idx] = line[:10] + '*' + line[11:]

#     with open(parameters.fileObs,'w') as f:
#         f.writelines(lines)

#     return nonClusters_idx

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

    # # Check for stations that are part of a "cluster"
    # idx_notCluster = dealWithClusters(statCorr_df, parameters)

    # # Remove indexes from clusters and from badly constrained delays
    # idx_keep = set(statCorr_df[(statCorr_df.PhaseNum >= parameters.minPhases) & (statCorr_df.StdDev >= 0)].index)
    # idx = idx_notCluster & idx_keep

    idx = set(statCorr_df[(statCorr_df.PhaseNum >= parameters.minPhases) & (statCorr_df.StdDev >= 0)].index)
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
    