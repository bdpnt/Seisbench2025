'''
convertMagnitudes_obs converts magnitudes from all files in obs/ folder to ML LDG,
by loading pre-computed regression models from MAGMODELS/ folder.
'''

from parameters import Parameters
import pandas as pd
import glob
import joblib

def fetchEvents(file):
    with open(file,'r',encoding='utf-8') as f:
        lines = f.readlines()

    eventIDs = []
    for id,line in enumerate(lines):
        if line.startswith('###'):
            continue
        elif line.startswith('#'):
            eventIDs.append(id)

    return lines,eventIDs

def updateMagnitudes(lines,orgMag):
    for _, row in orgMag.iterrows():
        line_idx = row['linesID']
        columns = lines[line_idx].split()
        columns[10] = f"{float(row['ldgMag']):.2f}" if row['ldgMag'] is not None else 'None'
        columns[11],columns[12] = 'ML','LDG'
        if columns[10] != 'None':
            lines[line_idx] = ' '.join(columns)
    return lines

def saveMagnitudes(lines,file):
    with open(file,'w') as f:
        for line in lines:
            if not line.endswith('\n'):
                line += '\n'
            f.write(line)
    
    print(f'\n    - Catalog succesfully saved @ {file}')

def updateAllFiles(parameters):
    print('\n#########') # opening line

    for folderFile in glob.glob(parameters.folderPath):
        # Get this folder's Author
        folderAuthor = folderFile.lstrip('obs/').split('_')[0]

        # Fetch event ids
        lines,linesID = fetchEvents(folderFile)

        # Create dataframe from original magnitudes
        orgMag = pd.DataFrame([line.split()[10:13] for line in [lines[id] for id in linesID]], columns=['Mag','MagType','MagAuthor'])

        # Mags to numeric
        orgMag['Mag'] = pd.to_numeric(orgMag['Mag'])
        
        # Add linesID column
        orgMag['linesID'] = linesID

        # Introduce empty new magnitude column
        orgMag['ldgMag'] = None

        # Keep count of magnitudes converted
        totalMags = len(orgMag)
        convertedMags = 0

        # Convert each type of magnitude in the folder
        print(f'\nAnalysing events @ {folderFile}:')
        for magType in orgMag.MagType.unique():
            # Select only magnitudes of the current type
            currentIDs = orgMag[orgMag.MagType == magType].index
            modelNameStart = f'{magType} {folderAuthor}'
            
            # Try to fetch the models
            try:
                fileModel = f'MAGMODELS/{modelNameStart}.joblib' #_2_ML LDG.joblib'
                models = joblib.load(fileModel)

                model_ge_2 = [model for _,model in models.items()][0] # model for magnitudes greater or equal to 2
                model_lt_2 = [model for _,model in models.items()][1] # model for magnitudes less than 2

                print(f'    - {modelNameStart} found @ {fileModel}')
            except:
                print(f'    - {modelNameStart} not accessible @ {fileModel}, trying next model...')
                continue
            
            # Compute new magnitudes
            mask_ge_2 = (orgMag.index.isin(currentIDs)) & (orgMag['Mag'] >= 2)
            mask_lt_2 = (orgMag.index.isin(currentIDs)) & (orgMag['Mag'] < 2)
            orgMag.loc[mask_ge_2, 'ldgMag'] = (model_ge_2['slope'] * orgMag.loc[mask_ge_2, 'Mag'] + model_ge_2['intercept'])
            orgMag.loc[mask_lt_2, 'ldgMag'] = (model_lt_2['slope'] * orgMag.loc[mask_lt_2, 'Mag'] + model_lt_2['intercept'])

            # Keep count of magnitudes converted
            convertedMags += len(currentIDs)

            # Print
            print(f'    - {modelNameStart}: magnitudes converted to ML LDG')
        
        # Save the converted magnitudes into the file
        if not orgMag['ldgMag'].isna().all():
            lines = updateMagnitudes(lines,orgMag)
            saveMagnitudes(lines,folderFile)
            print(f'    - Magnitudes converted: {convertedMags}/{totalMags}')
        else:
            print(f'\n    - No magnitudes converted')
    
    print('\n#########\n') # closing line
