'''
updateBulletinPicks_obs searches the global Inventory for the Network associated
with every pick in an OBS Catalog. If the Network is not found, removes the pick.
It also updates the codes for any duplicate station in a Network.
'''

from obspy import read_inventory, UTCDateTime
import pandas as pd

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

# FUNCTIONS
def findUniqueStations(inventory):
    uniqueSta = pd.DataFrame(columns=['Network','Code','AlternateCode','StartDate','EndDate'])
    for net in inventory.networks:
        for sta in net.stations:
            newRow = {
                'Network': net.code,
                'Code': sta.code.split('_')[0],
                'AlternateCode': sta.alternate_code,
                'StartDate': sta.start_date,
                'EndDate': sta.end_date
            }
            uniqueSta = pd.concat([uniqueSta, pd.DataFrame([newRow])], ignore_index=True)
    return uniqueSta


def findCode(line,uniqueSta):
    stationLine = line[:9].lstrip('.').strip() if line.startswith('.') else line[:9].split('.')[1].strip() # works both with or without Network
    alternateStationLine = None
    matchingIndices = uniqueSta.index[uniqueSta.Code == stationLine].tolist()

    if len(matchingIndices) >= 1:
        # Fetch the Date for this line
        year = line[31:35]
        month = line[35:37]
        day = line[37:39]
        hour = line[40:42]
        minute = line[42:44]
        second = line[45:47]

        # Make sure there is no date error from bulletin
        try:
            dateLine = UTCDateTime(f'{year}-{month}-{day}T{hour}:{minute}:{second}Z')
        except:
            return False
        
        if len(matchingIndices) == 1:
            alternateStationLine = uniqueSta.AlternateCode.loc[matchingIndices[0]]

        # Compare to the available timeframes
        workingIndices = []
        for i,(startDate,endDate) in enumerate(zip(uniqueSta.StartDate.loc[matchingIndices],uniqueSta.EndDate.loc[matchingIndices])):
            if startDate is None:
                continue
            elif endDate is None:
                endDate = UTCDateTime(2500, 12, 31)
                
            if startDate <= dateLine <= endDate:
                workingIndices.append(i)
        
        # Get the date only if there is exactly one
        if len(workingIndices) == 1:
            alternateStationLine = uniqueSta.AlternateCode.loc[matchingIndices[workingIndices[0]]]

    if alternateStationLine is None: # no match or too many matches
        return None

    return alternateStationLine.ljust(9)

def associatePicks(parameters):
    #--- Load Inventory and Bulletin
    inventory = read_inventory(parameters.fileInventory,format='STATIONXML')
    print(f"\nStations from Inventory @ {parameters.fileInventory} succesfully retrieved")

    with open(parameters.fileBulletin,'r',encoding='utf-8') as f:
        linesBulletin = f.readlines()
    print(f"Picks from Bulletin @ {parameters.fileBulletin} succesfully retrieved\n")

    # Initiate Bulletin picks length
    orgBulletinLength = 0
    newBulletinLength = 0

    #--- Find unique stations in Inventory
    uniqueSta = findUniqueStations(inventory)

    #--- Find the right network for every line
    newBulletin = []
    for line in linesBulletin:
        if not line.startswith('#') and not line == '\n':
            # Update original Bulletin picks length
            orgBulletinLength += 1

            # Find associated Network
            codeLine = findCode(line,uniqueSta)

            if codeLine not in (None, False):
                newBulletin.append(codeLine + line[9:])

                # Update new Bulletin picks length
                newBulletinLength += 1
        else:
            newBulletin.append(line)

    # Print the stats about removed events
    picksRemoved = orgBulletinLength - newBulletinLength
    picksRemovedPercent = picksRemoved/orgBulletinLength * 100

    
    print(f"Picks removed: {picksRemoved}/{orgBulletinLength} ({picksRemovedPercent:.3f} %)\n")

    #--- Save the Bulletin
    with open(parameters.fileBulletin, 'w') as f:
        f.writelines(newBulletin)
    
    # Print
    print(f"Bulletin succesfully saved @ {parameters.fileBulletin}\n")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileInventory = 'stations/GLOBAL_inventory.xml',
        fileBulletin = 'obs/RESIF_20-25.obs',
    )

    #---- Write OBS file
    associatePicks(parameters)
