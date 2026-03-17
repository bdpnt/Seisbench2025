'''
postRunClean removes unnecessary files after an NLL run, and generates the
final NLL result file.
'''

import os
import numpy as np
import pandas as pd

def preWork(parameters):
    # Remember current folder
    currentFolder = os.getcwd()

    #---- Remove .hdr files
    os.chdir(parameters.folderLoc)

    for f in os.listdir():
        if f.endswith('.hdr'):
            os.remove(f)
    
    #---- Read .hypo_71 file
    hypoFile = f'{parameters.obsFile}.sum.grid0.loc.hypo_71'

    data = []
    with open(hypoFile, 'r') as f:
        f.readline() # Skip header 1
        f.readline() # Skip header 2

        for line in f:
            #--- Initiate the row
            row = {}
            
            try:
                row['date'] = line[1:7].strip()
                row['heuremin'] = float(line[7:12])
                row['ssss'] = float(line[12:18])
                row['lat'] = float(line[18:21])
                row['latmin'] = float(line[21:27])
                row['lon'] = float(line[27:31])
                row['lonmin'] = float(line[31:38])
                row['prof'] = float(line[38:45])
                row['mag'] = float(line[47:51])
            except:
                continue

            try:
                row['no'] = float(line[52:55])
                row['dm'] = float(line[55:58])
                row['gap'] = float(line[58:62])
                row['m'] = float(line[62:64])
                row['rms'] = float(line[64:69])
                row['erh'] = float(line[70:74])
                row['erv'] = float(line[75:79])
            except:
                row['no'] = np.nan
                row['dm'] = np.nan
                row['gap'] = np.nan
                row['m'] = np.nan
                row['rms'] = np.nan
                row['erh'] = np.nan
                row['erv'] = np.nan

            #--- Save the row
            data.append(row)

    #---- Save hypo_71 file content as a DataFrame
    df = pd.DataFrame(data)

    # Go back to current folder
    os.chdir(currentFolder)

    # Return Dataframe
    return df

def writeEvents(parameters):
    #---- Remove unnecessary files and fetch the events data
    events = preWork(parameters)

    #---- Write final file
    with open(parameters.fileBulletin, 'w') as f:
        for _, row in events.iterrows():
            datestr1 = row['date']
            heuremin1 = f"{row['heuremin']:4.0f}"

            if len(heuremin1.strip()) == 1:
                heure1 = 0
                min1 = int(heuremin1)
            elif len(heuremin1.strip()) == 2:
                heure1 = 0
                min1 = int(heuremin1)
            else:
                heure1 = int(heuremin1[:-2])
                min1 = int(heuremin1[-2:])

            if len(datestr1) == 5:
                datestr1 = '0' + datestr1
            if len(datestr1) == 4:
                datestr1 = '00' + datestr1

            year = int(datestr1[0:2])
            month = int(datestr1[2:4])
            day = int(datestr1[4:6])

            latitude = row['lat'] + row['latmin'] / 60.0
            longitude = row['lon'] + row['lonmin'] / 60.0

            f.write(
                f"{year} {month} {day} "
                f"{heure1} {min1} {row['ssss']} "
                f"{latitude} {longitude} {row['prof']} {row['mag']} "
                f"{row['rms']} {row['no']} {row['erh']} {row['erv']} {row['gap']}\n"
            )

    print(f'\nNLL result file succesfully read @ {parameters.fileBulletin}')
    
    #---- Statistics
    rms_arr = events['rms'].to_numpy()
    erh_arr = events['erh'].to_numpy()
    erv_arr = events['erv'].to_numpy()

    print(f'    - mean RMS : {np.nanmean(rms_arr)}')
    print(f'    - median RMS : {np.nanmedian(rms_arr)}')
    print(f'    - mean ERH : {np.nanmean(erh_arr)}')
    print(f'    - mean ERV : {np.nanmean(erv_arr)}\n')
