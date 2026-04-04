'''
availableMagTypes_obs searches for all available magnitude types in a .obs Catalog
and lists them.
'''

def retrieveEvents_fromFile(fileName):
    """Read an .obs file and return a list of event header lines (stripped of the leading '# ')."""
    with open(fileName, 'r', encoding='utf-8', errors='ignore') as fR:
        catLines = fR.readlines()

    eventLines = []
    for line in catLines:
        if line.startswith('###'):
            continue
        elif line.startswith('#'):
            eventLines.append(line.rstrip('\n').lstrip('# '))
    
    print(f"Events from Catalog @ {fileName} succesfully retrieved")
    return eventLines

def findMagnitudeTypes(parameters):
    """Print all magnitude types and their counts found in an .obs bulletin file."""
    #--- Get events informations
    eventLines = retrieveEvents_fromFile(parameters.fileName)

    #--- Find all magnitude types available
    magTypes = {}
    for line in eventLines:
        magType = line.split()[10] + ' ' + line.split()[11]
        if magType not in list(magTypes):
            magTypes[magType] = 1
        else:
            magTypes[magType] +=1
    
    #--- Print
    print(f'Magnitude types available in Catalog @ {parameters.fileName}:')
    for magType in magTypes:
        print(f'    - {magType} ({magTypes[magType]})')