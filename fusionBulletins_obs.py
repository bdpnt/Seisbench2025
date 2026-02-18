'''
fusionBulletins_obs fusions all the OBS Bulletins into a single one, by matching events.
'''

import glob
import pandas as pd
import math
from scipy.spatial import KDTree
from numpy import mean

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
        'latitude': [float(i[6]) for i in infos],
        'longitude': [float(i[7]) for i in infos],
        'depth': [float(i[8]) for i in infos],
        'magnitude': [float(i[9].split(':')[0]) for i in infos],
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

def concatenateBulletin(
        mainLines, secondaryBulletinPath, 
        distThresh, looseDistThresh, timeThresh, looseTimeThresh, magThresh, simPickThresh
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
    strictMatch, possibleMatch, notStrictMatchID_secondary = find_matchEvents(
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
                magToConcat = ":" + eventLine_secondary.split()[10]
                newEventLine = eventLine_main.split()
                newEventLine[-1] += '\n'
                newEventLine[10] += magToConcat
                eventLine_main = " ".join(newEventLine)
            
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
                if event_idx2 not in notStrictMatchID_secondary:
                    continue

                # Check for the number of similar P-phase picks
                simPicks = check_similarPicks(mainLines,secondaryLines,mainIDs[event_idx1],secondaryIDs[event_idx2])

                # If inside loose thresholds and at least 1 similar pick (time threshold is already correct since the pick has made it to here)
                if simPicks >= 1 and row.distance_km <= parameters.looseDistThresh:
                    # Add magnitude from secondary Bulletin if it is an ML (LDG/OMP) magnitude
                    if row.mag_type_ML:
                        magToConcat = ":" + eventLine_secondary.split()[10]
                        newEventLine = eventLine_main.split()
                        newEventLine[-1] += '\n'
                        newEventLine[10] += magToConcat
                        eventLine_main = " ".join(newEventLine)
                    
                    # Add event to the updated Bulletin
                    newLines.append(eventLine_main)

                    # Add phases from both catalogs to the updated Bulletin
                    newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                    newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
                    newLines.append('\n')

                    # Remove ID from notStrictMatchID_secondary
                    notStrictMatchID_secondary.remove(event_idx2)

                    # Found solution
                    solutionFound = True
                    foundPossible.append(possibleRow.index[0])

                    break
                
                # If outside some threshold but multiple similar picks
                elif simPicks >= simPickThresh:
                    # Add magnitude from secondary Bulletin if it is an ML (LDG/OMP) magnitude
                    if row.mag_type_ML:
                        magToConcat = ":" + eventLine_secondary.split()[10]
                        newEventLine = eventLine_main.split()
                        newEventLine[-1] += '\n'
                        newEventLine[10] += magToConcat
                        eventLine_main = " ".join(newEventLine)
                    
                    # Add event to the updated Bulletin
                    newLines.append(eventLine_main)

                    # Add phases from both catalogs to the updated Bulletin
                    newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                    newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
                    newLines.append('\n')

                    # Remove ID from notStrictMatchID_secondary
                    notStrictMatchID_secondary.remove(event_idx2)

                    # Found solution
                    solutionFound = True
                    foundPossible.append(possibleRow.index[0])

                    break
            
            #- If no solution found, add the event as in main Bulletin
            if not solutionFound:
                newLines.append(eventLine_main)
                newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
                newLines.append('\n')

        #-- No match: add the event as in main Bulletin
        else:
            newLines.append(eventLine_main)
            newLines = addPhasesToLines(newLines,mainLines,mainIDs[event_idx1])
            newLines.append('\n')

    #---- Add unmatched events from secondary Bulletin
    for event_idx2 in notStrictMatchID_secondary:
        # Add event to the updated Bulletin
        eventLine_secondary = secondaryLines[secondaryIDs[event_idx2]]
        newLines.append(eventLine_secondary)

        # Add phases to the updated Bulletin
        newLines = addPhasesToLines(newLines,secondaryLines,secondaryIDs[event_idx2])
        newLines.append('\n')

    #---- Remove events matched during second process from possibleMatch
    possibleMatch = possibleMatch.drop(foundPossible)
    print(f'Found {len(foundPossible)} ({len(possibleMatch)}) event matches during P-phase picks matching process')

    #---- Rearrange events by date in the updated Bulletin
    newLines = sortEventsChrono(newLines)

    #---- Return the updated Bulletin
    return newLines

def replaceMeanMagnitudes(lines):
    for id,line in enumerate(lines):
        if line.startswith('# '):
            newLine = line.split()
            mags = newLine[10].split(':')
            mags = [float(mag) for mag in mags]
            newLine[10] = f"{mean(mags):.2f}"
            newLine[-1] += '\n'
            lines[id] = " ".join(newLine)
    
    print('Magnitudes succesfully replaced by mean magnitudes')
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

def removeMagnitudes(lines):
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
    for filePath in allPath:
        print('\n#######\n')
        mainLines = concatenateBulletin(
            mainLines,
            filePath,
            parameters.distThresh,
            parameters.looseDistThresh,
            parameters.timeThresh,
            parameters.looseTimeThresh,
            parameters.magThresh,
            parameters.simPickThresh,
        )
    print('\n#######\n')

    #---- Update magnitudes and remove events under ML 1
    mainLines = replaceMeanMagnitudes(mainLines)
    mainLines = removeMagnitudes(mainLines)

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
