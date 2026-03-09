'''
fusionBulletins_obs fusions all the OBS Bulletins into a single one, by matching events.
'''

import glob
import pandas as pd
import math
from scipy.spatial import KDTree
from scipy.stats import pearsonr, spearmanr
from numpy import mean
import seaborn as sns
import matplotlib.pyplot as plt

# CLASS
class Parameters:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        attrs = ', '.join(f"{k}={v}" for k, v in self.__dict__.items())
        return f"Parameters({attrs})"

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

# FUNCTION
def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two geographical points"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def generateGlobal(parameters):
    with open(parameters.mainBulletinPath, 'r') as f:
        lines = f.readlines()
    
    eventCount = 0
    for line in lines:
        if line.startswith('# '):
            eventCount += 1

    print(f"\n#######\n\n{eventCount} events from Catalog @ {parameters.mainBulletinPath} successfully retrieved")
    return lines

def retrieveEvents_fromLines(catLines):
    eventLines = []
    eventLinesID = []
    for ID,line in enumerate(catLines):
        if line.startswith('# '):
            eventLines.append(line.rstrip('\n').lstrip('# '))
            eventLinesID.append(ID)

    return eventLines,eventLinesID

def retrieveEvents_fromFile(fileName):
    with open(fileName, 'r', encoding='utf-8', errors='ignore') as f:
        catLines = f.readlines()

    eventLines = []
    eventLinesID = []
    for ID,line in enumerate(catLines):
        if line.startswith('# '):
            eventLines.append(line.rstrip('\n').lstrip('# '))
            eventLinesID.append(ID)

    print(f"{len(eventLines)} events from Catalog @ {fileName} successfully retrieved")
    return eventLines,eventLinesID,catLines

def get_firstNonNanValue(value):
    if isinstance(value, str):
        parts = value.split(':')
        for part in parts:
            if part.strip().lower() != 'nan':
                try:
                    return float(part)
                except ValueError:
                    continue
        return None 
    else:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

def get_catalogFrame(eventLines):
    # Extract all fields
    infos = [line.split() for line in eventLines]

    # Convert to DataFrame directly
    catalogFrame = pd.DataFrame({
        'year': [i[0] for i in infos],
        'month': [i[1] for i in infos],
        'day': [i[2] for i in infos],
        'hour': [i[3] for i in infos],
        'minute': [i[4] for i in infos],
        'second': [i[5] for i in infos],
        'latitude': [get_firstNonNanValue(i[6]) for i in infos],
        'longitude': [get_firstNonNanValue(i[7]) for i in infos],
        'depth': [get_firstNonNanValue(i[8]) for i in infos],
        'magnitude': [get_firstNonNanValue(i[9].split(':')[0]) for i in infos],
        'magType': [i[10] for i in infos],
        'magAuthor': [i[11] for i in infos],
        'phaseCount': [float(i[12]) if i[12] != 'None' else None for i in infos],
        'horUncer': [float(i[13]) if i[13] != 'None' else None for i in infos],
        'verUncer': [float(i[14]) if i[14] != 'None' else None for i in infos],
        'azGap': [float(i[15]) if i[15] != 'None' else None for i in infos],
        'rms': [float(i[16]) if i[16] != 'None' else None for i in infos],
    })

    # Pad 'second' column to 6 decimals
    catalogFrame['second'] = catalogFrame['second'].apply(lambda x: f"{float(x):.6f}")

    # Add 'time' column
    catalogFrame['time'] = pd.to_datetime(
        catalogFrame['year'] + '-' + catalogFrame['month'] + '-' + catalogFrame['day'] + 'T' +
        catalogFrame['hour'] + ':' + catalogFrame['minute'] + ':' + catalogFrame['second'] + 'Z'
    )

    return catalogFrame

def find_matchEvents(catalog1, catalog2, distThresh, looseDistThresh, timeThresh, looseTimeThresh, magThresh):
    #---- Convert time thrsholds to timedelta objetcs
    timeThresh = pd.Timedelta(seconds=timeThresh)
    looseTimeThresh = pd.Timedelta(seconds=looseTimeThresh)

    #---- Initialize the matches
    matchedPairs = []
    possibleMatch = []

    matchID_catalog1 = set()
    matchID_catalog2 = set()

    #---- Loop on all events in catalogue 1
    for idx1, row1 in catalog1.iterrows():
        #--- Check for events in catalog 2 in the loose time threshold
        idx2 = abs((catalog2.time - row1.time).dt.total_seconds()) < looseTimeThresh.total_seconds()
        idx2 = idx2[idx2].index.to_numpy()

        # If the length is more than 1, check for close events only
        if len(idx2) > 1:
            coords2 = catalog2.loc[idx2,['latitude', 'longitude']].to_numpy()
            coords_idx2 = KDTree(coords2).query_ball_point([row1['latitude'], row1['longitude']], r=looseDistThresh/111)
            idx2 = idx2[coords_idx2]
            
        #--- Check the distance and magnitude for each candidate
        bestMatch_idx = None
        bestMatch_distance = float('inf')
        bestMatch_time = float('inf')
        bestMatch_mag = float('inf')
        bestMatch_magTypeML = False

        for i in idx2:
            #-- Initialize the candidate
            candidate = catalog2.iloc[i]
            candidate_distance = haversine(row1.latitude,row1.longitude,candidate.latitude,candidate.longitude)
            candidate_timeDelta = abs((row1.time - candidate.time).total_seconds())
            candidate_magDelta = abs(row1.magnitude - candidate.magnitude)
            candidate_magTypeML = True if (row1.magType == 'ML' and candidate.magType == 'ML' 
                                           and (row1.magAuthor == 'LDG' or row1.magAuthor == 'OMP') 
                                           and (candidate.magAuthor == 'LDG' or candidate.magAuthor == 'OMP')) else False

            #-- First pass: strict time threshold and magnitude check
            if candidate_magTypeML:
                if candidate_magDelta > magThresh:
                    continue

            if candidate_timeDelta <= timeThresh.total_seconds():
                if candidate_distance <= distThresh:
                    if candidate_distance < bestMatch_distance or (candidate_distance == bestMatch_distance and candidate_timeDelta < bestMatch_time):
                        bestMatch_idx = i
                        bestMatch_distance = candidate_distance
                        bestMatch_time = candidate_timeDelta
                        bestMatch_mag = candidate_magDelta
                        bestMatch_magTypeML = True if candidate_magTypeML else False

        if bestMatch_idx is not None:
            matchID_catalog1.add(idx1)
            matchID_catalog2.add(bestMatch_idx)
            matchedPairs.append({
                'catalog1_idx': idx1,
                'catalog2_idx': bestMatch_idx,
                'distance_km': bestMatch_distance,
                'time_diff_seconds': bestMatch_time,
                'mag_diff': bestMatch_mag,
                'mag_type_ML': bestMatch_magTypeML,
                'threshold_used': 'strict'
            })

        else:
            #-- Best loose candidate
            bestLoose_idx = None
            bestLoose_distance = float('inf')
            bestLoose_time = float('inf')
            bestLoose_mag = float('inf')
            bestLoose_magTypeML = False

            for i in idx2:
                #- Verify if it is already strict matched
                if i in matchID_catalog2:
                    continue

                #- Initialize the candidate
                candidate = catalog2.iloc[i]
                candidate_distance = haversine(row1.latitude,row1.longitude,candidate.latitude,candidate.longitude)
                candidate_timeDelta = abs((row1.time - candidate.time).total_seconds())
                candidate_magDelta = abs(row1.magnitude - candidate.magnitude)
                candidate_magTypeML = True if (row1.magType == 'ML' and candidate.magType == 'ML' 
                                               and (row1.magAuthor == 'LDG' or row1.magAuthor == 'OMP') 
                                               and (candidate.magAuthor == 'LDG' or candidate.magAuthor == 'OMP')) else False

                #- Second pass: loose time threshold and no magnitude check
                if candidate_timeDelta <= looseTimeThresh.total_seconds():
                    bestLoose_idx = i
                    bestLoose_distance = candidate_distance
                    bestLoose_time = candidate_timeDelta
                    bestLoose_mag = candidate_magDelta
                    bestLoose_magTypeML = True if candidate_magTypeML else False
                
            if bestLoose_idx is not None:
                possibleMatch.append({
                    'catalog1_idx': idx1,
                    'catalog2_idx': bestLoose_idx,
                    'distance_km': bestLoose_distance,
                    'time_diff_seconds': bestLoose_time,
                    'mag_diff': bestLoose_mag,
                    'mag_type_ML': bestLoose_magTypeML,
                    'threshold_used': 'loose'
                })

    # Find unmatched events in Catalog 2 (including possible matches)
    unmatched_catalog2 = [item for item in catalog2.index if item not in matchID_catalog2]

    # Filter out possibleMatch for eventual events matched after in strictMatch
    possibleMatch = [
        match for match in possibleMatch
        if match['catalog2_idx'] not in matchID_catalog2
    ]

    # Print
    print(f'{len(matchedPairs)} ({len(possibleMatch)}) events strict match found')

    return pd.DataFrame(matchedPairs), pd.DataFrame(possibleMatch), unmatched_catalog2
                    


def addPhasesToLines(newLines,oldLines,ID):
    ID += 1
    line = oldLines[ID]
    while not line.startswith('\n'):
        newLines.append(line)

        # Update line
        ID += 1
        line = oldLines[ID]
    
    return newLines

def sortEventsChrono(lines):
    headers = [line for line in lines if line.startswith('###')]
    headers.append('\n')
    eventsLines = [line for line in lines if not line.startswith('###')]

    events = []
    current_event = None

    for line in eventsLines:
        if line.startswith('#'):
            # New event: save the previous one if it exists
            if current_event is not None:
                events.append(current_event)
            # Start a new event
            current_event = [line]
        elif line.strip() == '':
            # Empty line: end of current event
            if current_event is not None:
                events.append(current_event)
                current_event = None
        elif current_event is not None:
            # Add phase lines to the current event
            current_event.append(line)

    # Add the last event if it exists
    if current_event is not None:
        events.append(current_event)

    # Extract the timestamp from each event
    def get_timestamp(event):
        header = event[0]
        parts = header.split()
        # Extract year, month, day, hour, minute, second
        year, month, day, hour, minute, second = map(float, parts[1:7])
        return (year, month, day, hour, minute, second)

    # Sort events by timestamp
    events.sort(key=get_timestamp)

    # Flatten the sorted events back into a list of lines
    sortedLines = headers.copy()
    for event in events:
        sortedLines.extend(event)
        sortedLines.append('\n')  # Add empty line after each event

    return sortedLines

def find_pickLines(allLines,ID):
    allPicks = []
    end = False
    currID = ID
    while not end:
        currLine = allLines[currID]
        if currLine.startswith('\n'):
            end = True
        elif not currLine.startswith('#'):
            allPicks.append(currLine)
        currID += 1
    return allPicks

def check_similarPicks(mainLines,secondaryLines,mainID,secondaryID):
    # Find the picks lines for event in bulletin
    mainPicks = find_pickLines(mainLines,mainID)
    secondaryPicks = find_pickLines(secondaryLines,secondaryID)

    allPicks = mainPicks + secondaryPicks

    allPhases = {}
    allTimes = []
    
    # Find the similar picks
    for line in allPicks:
        phaseLine = line[:23]
        phaseTime = line[31:51]

        if line[22] == 'S':
            continue

        if phaseLine not in allPhases:
            allPhases[phaseLine] = 1
            allTimes.append(phaseTime)
        else:
            i = list(allPhases.keys()).index(phaseLine)
            dateStr = allTimes[i]
            date = pd.to_datetime(f"{dateStr[:8]} {dateStr[9:13]}{dateStr[14:]}", format="%Y%m%d %H%M%S.%f")
            dateNew = pd.to_datetime(f"{phaseTime[:8]} {phaseTime[9:13]}{phaseTime[14:]}", format="%Y%m%d %H%M%S.%f")
            if abs(date - dateNew) <= pd.Timedelta(seconds=1):
                allPhases[phaseLine] += 1

    # Count similar picks
    similarPhases = sum(1 for item in allPhases.values() if item > 1)
    return similarPhases

def addItemForStats(lineMain,lineSecondary,id,isNan=False):
    '''ID is 7 for Latitude, 8 for Longitude, 9 for Depth and 10 for Magnitude'''
    if isNan:
        toConcat = ":Nan"
    else:
        toConcat = ":" + lineSecondary.split()[id]
    newLine = lineMain.split()
    newLine[-1] += '\n'
    newLine[id] += toConcat
    return " ".join(newLine)

def addNansForStats(lineSecondary,id,loopNo):
    toReplace = "Nan:" * loopNo + lineSecondary.split()[id]
    newLine = lineSecondary.split()
    newLine[-1] += '\n'
    newLine[id] = toReplace
    return " ".join(newLine)

def concatenateBulletin(
        mainLines, secondaryBulletinPath, 
        distThresh, looseDistThresh, timeThresh, looseTimeThresh, magThresh, simPickThresh,
        loopNo
    ):
    #---- Fetch Bulletins
    mainEventLines,mainIDs = retrieveEvents_fromLines(mainLines)
    secondaryEventLines,secondaryIDs,secondaryLines = retrieveEvents_fromFile(secondaryBulletinPath)

    mainBulletin = get_catalogFrame(mainEventLines)
    secondaryBulletin = get_catalogFrame(secondaryEventLines)

    #---- Initialize updated Bulletin
    newLines = [line for line in mainLines if line.startswith('###')]
    newLines.append('\n')

    #---- Find matches
    strictMatch, possibleMatch, notMatchedID_secondary = find_matchEvents(
        mainBulletin, secondaryBulletin,
        distThresh, looseDistThresh,
        timeThresh, looseTimeThresh,
        magThresh
    )

    #---- Initialize found matches during second process
    foundPossible = []

    #---- Combine picks for strict matches
    for event_idx1 in mainBulletin.index:
        #--- Check for matches
        if not (strictMatch.empty and possibleMatch.empty):
            #-- Find match in secondary Bulletin
            matchRow = strictMatch[strictMatch.catalog1_idx == event_idx1]
            possibleRow = possibleMatch[possibleMatch.catalog1_idx == event_idx1]
        else:
            matchRow = pd.DataFrame()
            possibleRow = pd.DataFrame()

        #-- Catch the event line in the main Bulletin
        eventLine_main = mainLines[mainIDs[event_idx1]]

        #-- Look for a strict match
        if not matchRow.empty:
            event_idx2 = matchRow['catalog2_idx'].iloc[0]
            eventLine_secondary = secondaryLines[secondaryIDs[event_idx2]]

            #- Add magnitude from secondary Bulletin if it is an ML (LDG) magnitude
            if matchRow.mag_type_ML.item():
                eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10)
            else:
                eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10,isNan=True)

            #- Add Latitude, Longitude, Depth from secondary Bulletin
            eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,7) # Latitude
            eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,8) # Longitude
            eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,9) # Depth
            
            #- Add event to the updated Bulletin
            newLines.append(eventLine_main)

            #- Add phases from both catalogs to the updated Bulletin
            newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
            newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
            newLines.append('\n')
        
        #-- Look for a possible match
        elif not possibleRow.empty:
            solutionFound = False
            #- Check for solution (if any) in possible match
            for _,row in possibleRow.iterrows():
                event_idx2 = row.catalog2_idx
                eventLine_secondary = secondaryLines[secondaryIDs[event_idx2]]

                # Check if event from secondary Bulletin hasn't been matched yet
                if event_idx2 not in notMatchedID_secondary:
                    continue

                # Check for the number of similar P-phase picks
                simPicks = check_similarPicks(mainLines,secondaryLines,mainIDs[event_idx1],secondaryIDs[event_idx2])

                # If inside loose thresholds and at least 1 similar pick (time threshold is already correct since the pick has made it to here)
                if simPicks >= 1 and row.distance_km <= parameters.looseDistThresh:
                    # Add magnitude from secondary Bulletin if it is an ML (LDG/OMP) magnitude
                    if row.mag_type_ML:
                        eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10)
                    else:
                        eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10,isNan=True)
                    
                    # Add Latitude, Longitude, Depth from secondary Bulletin
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,7) # Latitude
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,8) # Longitude
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,9) # Depth
                    
                    # Add event to the updated Bulletin
                    newLines.append(eventLine_main)

                    # Add phases from both catalogs to the updated Bulletin
                    newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                    newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
                    newLines.append('\n')

                    # Remove ID from notMatchedID_secondary
                    notMatchedID_secondary.remove(event_idx2)

                    # Found solution
                    solutionFound = True
                    foundPossible.append(possibleRow.index[0])

                    break
                
                # If outside some threshold but multiple similar picks
                elif simPicks >= simPickThresh:
                    # Add magnitude from secondary Bulletin if it is an ML (LDG/OMP) magnitude
                    if row.mag_type_ML:
                        eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10)
                    else:
                        eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,10,isNan=True)

                    #- Add Latitude, Longitude, Depth from secondary Bulletin
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,7) # Latitude
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,8) # Longitude
                    eventLine_main = addItemForStats(eventLine_main,eventLine_secondary,9) # Depth
                    
                    # Add event to the updated Bulletin
                    newLines.append(eventLine_main)

                    # Add phases from both catalogs to the updated Bulletin
                    newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                    newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
                    newLines.append('\n')

                    # Remove ID from notMatchedID_secondary
                    notMatchedID_secondary.remove(event_idx2)

                    # Found solution
                    solutionFound = True
                    foundPossible.append(possibleRow.index[0])

                    break
            
            #- If no solution found, add the event as in main Bulletin
            if not solutionFound:
                # Add Latitude, Longitude, Depth, Magnitude Nan
                eventLine_main = addItemForStats(eventLine_main,"",7,isNan=True) # Latitude
                eventLine_main = addItemForStats(eventLine_main,"",8,isNan=True) # Longitude
                eventLine_main = addItemForStats(eventLine_main,"",9,isNan=True) # Depth
                eventLine_main = addItemForStats(eventLine_main,"",10,isNan=True) # Magnitude

                # Append the line
                newLines.append(eventLine_main)
                newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                newLines.append('\n')

        #-- No match: add the event as in main Bulletin
        else:
            #- Add Latitude, Longitude, Depth, Magnitude Nan
            eventLine_main = addItemForStats(eventLine_main,"",7,isNan=True) # Latitude
            eventLine_main = addItemForStats(eventLine_main,"",8,isNan=True) # Longitude
            eventLine_main = addItemForStats(eventLine_main,"",9,isNan=True) # Depth
            eventLine_main = addItemForStats(eventLine_main,"",10,isNan=True) # Magnitude

            #- Append the line
            newLines.append(eventLine_main)
            newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
            newLines.append('\n')

    #---- Add unmatched events from secondary Bulletin
    for event_idx2 in notMatchedID_secondary:
        # Add event to the updated Bulletin
        eventLine_secondary = secondaryLines[secondaryIDs[event_idx2]]

        # Add Latitude, Longitude, Depth, Magnitude Nan (as a new, event, needs to know the number of the loop)
        eventLine_secondary = addNansForStats(eventLine_secondary,7,loopNo) # Latitude
        eventLine_secondary = addNansForStats(eventLine_secondary,8,loopNo) # Longitude
        eventLine_secondary = addNansForStats(eventLine_secondary,9,loopNo) # Depth
        eventLine_secondary = addNansForStats(eventLine_secondary,10,loopNo) # Magnitude

        # Append the line
        newLines.append(eventLine_secondary)

        # Add phases to the updated Bulletin
        newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
        newLines.append('\n')

    #---- Add events matched during second process to strictMatch
    strictMatch = pd.concat([strictMatch, possibleMatch.iloc[foundPossible]]).reset_index(drop=True)

    #---- Remove events matched during second process from possibleMatch
    possibleMatch = possibleMatch.drop(foundPossible)
    print(f'Found {len(foundPossible)} ({len(possibleMatch)}) event matches during P-phase picks matching process')

    #---- Rearrange events by date in the updated Bulletin
    newLines = sortEventsChrono(newLines)

    #---- Return the updated Bulletin and the possible matches
    return newLines, strictMatch, possibleMatch, mainBulletin, secondaryBulletin

def statsFigs(mainName,secondaryName,frame):
    useCols = ['latitude','longitude','depth','magnitude']
    useFrame = frame[useCols]

    # Create a figure with subplots (2 rows and 2 columns)
    _, axs = plt.subplots(nrows=2, ncols=2, figsize=(18, 12))

    # Flatten the axes array for easier indexing
    axs = axs.flatten()
    plt.rc('axes', labelsize=13) 

    plot_index = 0
    for col in useCols:
        ax = axs[plot_index]

        # Update Data
        col1,col2 = zip(*[(t[0], t[1]) for t in useFrame[col]])
        data = pd.DataFrame({mainName:col1, secondaryName:col2})

        # Calculate the percentiles for both columns
        lower_bound = 0.5  # 0.5th percentile
        upper_bound = 99.5  # 99.5th percentile

        # Filter the DataFrame from the 1%
        data_99 = data[
            (data[mainName] >= data[mainName].quantile(lower_bound / 100)) &
            (data[mainName] <= data[mainName].quantile(upper_bound / 100)) &
            (data[secondaryName] >= data[secondaryName].quantile(lower_bound / 100)) &
            (data[secondaryName] <= data[secondaryName].quantile(upper_bound / 100))
        ]

        # Create scatterplot
        sns.scatterplot(
            x=data_99[mainName],
            y=data_99[secondaryName],
            ax=ax,
            color='black',
            s=2,
            alpha=0.6,
            edgecolor=None,
        )

        # Create KDE plot
        sns.kdeplot(
            x=data_99[mainName],
            y=data_99[secondaryName],
            ax=ax,
            cmap='flare',
            fill=True,
            alpha=0.65,
            # thresh=0.05,
            # levels=20,
        )

        ax.set_xlabel(mainName)
        ax.set_ylabel(secondaryName)
        ax.grid(True)
        
        # Calculate Pearson correlation (linear) and p-value
        correlation_pearson, p_value_pearson = pearsonr(data_99[mainName], data_99[secondaryName])

        # Calculate Spearman correlation (non-linear) and p-value
        correlation_spearman, p_value_spearman = spearmanr(data_99[mainName], data_99[secondaryName])
        
        # Add text to the subplot showing the Pearson correlation and p-value
        text_str = f"Pearson: {correlation_pearson:.3f} - p-value: {p_value_pearson:.3f}\nSpearman: {correlation_spearman:.3f} - p-value: {p_value_spearman:.3f}"
        ax.text(0.5, 1.085, text_str, transform=ax.transAxes, fontsize=12, horizontalalignment='center', verticalalignment='top')
        label_str = f"{col}".capitalize()
        ax.text(1.02, 0.5, label_str, transform=ax.transAxes, fontsize=12, fontweight='bold', horizontalalignment='center', verticalalignment='center', rotation=90)
        
        plot_index += 1

    # Adjust the spacing between subplots and figure margins
    plt.subplots_adjust(top=0.88, bottom=0.1, wspace=0.3, hspace=0.25)

    # Title
    plt.suptitle(f"Correlations and KDE/Distributions ({mainName} vs {secondaryName}) - matched events", fontsize=16, fontweight='bold')
    plt.text(0.5, 0.95, "Analysis based on the central 99% of the dataset", 
            fontsize=14, ha='center', va='center', transform=plt.gcf().transFigure)
    plt.text(0.5, 0.93, "Pearson (linear) and Spearman (non-linear) correlation values are statistically significant for p-values under 0.05", 
            fontsize=14, ha='center', va='center', transform=plt.gcf().transFigure)
    
    # Save
    path = f"obs/STATS/{mainName}_{secondaryName}.pdf"
    plt.savefig(path)
    plt.close()

    print(f'Statistics figure succesfully saved @ {path}')

def getStatistics(mainLines, parameters, filePath, fileNo):
    #--- Generate the correct lines
    lines = [line.lstrip('# ').rstrip('\n').split() for line in mainLines if line.startswith('# ')]
    
    removeLines = []
    for id,line in enumerate(lines):
        for idC,category in enumerate(line):
            items = category.split(':')
            if len(items) > 1:
                category = items[0] + ":" + items[fileNo]
                if category.__contains__('Nan'):
                    removeLines.append(id)
                    continue
                else:
                    lines[id][idC] = category

    lines = [line for id,line in enumerate(lines) if id not in removeLines]

    if not lines:
        print(f'Not enough matches for a statistical analysis for Bulletin @ {filePath}')
        return

    #--- Generate the frame
    df = pd.DataFrame(lines)
    df = df.iloc[:, [6,7,8,9]]
    df.columns = ['latitude','longitude','depth','magnitude']
    def split_to_floats(s):
        try:
            a, b = map(float, s.split(':'))
            return [a, b]
        except:
            return [None, None]

    df = df.map(split_to_floats)

    #--- Get the main and secondary names
    mainName = parameters.mainBulletinPath.split('/')[1].split('.')[0]
    secondaryName = filePath.split('/')[1].split('.')[0]

    #--- Stats on the frame
    if len(df) >= 10:
        statsFigs(mainName,secondaryName,df)
    else:
        print(f'Not enough matches for a statistical analysis for Bulletin @ {filePath}')

def replaceMeanMagnitudes(lines):
    for id,line in enumerate(lines):
        if line.startswith('# '):
            newLine = line.split()
            mags = newLine[10].split(':')
            mags = [float(mag) for mag in mags if mag != "Nan"]
            newLine[10] = f"{mean(mags):.2f}"
            newLine[-1] += '\n'
            lines[id] = " ".join(newLine)
    
    print('Magnitudes succesfully replaced by mean magnitudes')
    return lines

def removeStatsValues(lines):
    for id,line in enumerate(lines):
        if line.startswith('# '):
            newLine = ""
            for category in line.split():
                items = category.split(':')
                if len(items) > 1:
                    category = str(get_firstNonNanValue(category))
                newLine += category + " "
            if newLine.endswith(' '):
                newLine = newLine[:-1]
            newLine += '\n'
            lines[id] = newLine

    return lines
                

def removeDuplicatePicks(lines):
    picksToRemove = set()
    for id,line in enumerate(lines):
        if line.startswith('# '):
            i, end = id+1, False
            uniquePicks = set()
            while not end and i <= len(lines):
                pickLine = lines[i]
                if pickLine.startswith('\n'):
                    end = True
                    continue

                pick = (pickLine[:10],pickLine[22])
                if pick not in uniquePicks:
                    uniquePicks.add(pick)
                else:
                    picksToRemove.add(i)
                i += 1
    
    newLines = [line for id,line in enumerate(lines) if id not in picksToRemove]
    
    print(f'Succesfully removed {len(picksToRemove)} duplicate picks from the Bulletin')
    return newLines

def removeMagnitudesUnder1(lines):
    removeLines = set()
    removedEvents = 0
    
    for id,line in enumerate(lines):
        if line.startswith('# '):
            magnitude = float(line.split()[10])
            if magnitude < 1:
                removeLines.add(id)
                removedEvents += 1
                i, end = id+1, False
                while not end and i <= len(lines):
                    pickLine = lines[i]
                    if pickLine.startswith('\n'):
                        end = True
                        continue
                    removeLines.add(i)
                    i += 1
    newLines = [line for id,line in enumerate(lines) if id not in removeLines]

    print(f'Succesfully removed {removedEvents} events with magnitudes under ML 1')
    return newLines

def saveBulletin(lines,parameters):
    with open(parameters.globalBulletinPath, 'w') as f:
        f.writelines(lines)
    
    nbEQ = 0
    for line in lines:
        if line.startswith('#') and not line.startswith('###'):
            nbEQ += 1

    print(f'{nbEQ} events succesfully saved in Catalog @ {parameters.globalBulletinPath}\n\n#######\n')

def fusionAll(parameters):
    #---- Remove main Bulletin from all paths and start with it
    allPath = [filePath for filePath in glob.glob(parameters.folderPath) 
               if (filePath != parameters.mainBulletinPath and filePath != parameters.globalBulletinPath)]

    #---- Generate Global file from Main file
    mainLines = generateGlobal(parameters)

    #---- Loop on all paths
    for fileNo,filePath in enumerate(allPath):
        print('\n#######\n')
        mainLines, _, _, _, _ = concatenateBulletin(
            mainLines,
            filePath,
            parameters.distThresh,
            parameters.looseDistThresh,
            parameters.timeThresh,
            parameters.looseTimeThresh,
            parameters.magThresh,
            parameters.simPickThresh,
            fileNo+1,
        )

    print('\n#######\n')

    #---- Statistics
    for fileNo,filePath in enumerate(allPath):
        getStatistics(mainLines, parameters, filePath, fileNo+1)
    
    print('\n#######\n')

    #---- Update magnitudes, remove statistics values and remove events under ML 1
    mainLines = replaceMeanMagnitudes(mainLines)
    mainLines = removeStatsValues(mainLines)
    mainLines = removeMagnitudesUnder1(mainLines)

    #---- Check for unwanted/duplicate phases
    mainLines = removeDuplicatePicks(mainLines)

    #---- Save Global Bulletin
    saveBulletin(mainLines,parameters)

# MAIN
if __name__ == '__main__':
    parameters = Parameters(
        globalBulletinPath = 'obs/GLOBAL.obs',
        mainBulletinPath = 'obs/RESIF_20-25.obs',
        folderPath = 'obs/*.obs',
        distThresh = 15, # in km
        looseDistThresh = 50, # in km
        timeThresh = 2, # in seconds
        looseTimeThresh = 30, # in seconds
        magThresh = 1.5, # magnitude
        simPickThresh = 2, # minimal number of picks to confirm match from possible matches if no thresholds
    )

    fusionAll(parameters)
