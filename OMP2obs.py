'''
OMP2obs reads an OMP MAG file and saves its data as an OBS file.
'''

import datetime
from obspy import UTCDateTime

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
def open_catalog(fileName):
    with open(fileName, 'r', encoding='utf-8', errors='ignore') as fR:
        lines = fR.readlines()

    print(f"\nEvents from Catalog @ {fileName} succesfully retrieved")
    return lines

def write_catalog_to_obs(parameters):
    #--- Retrieve catalog
    lines = open_catalog(parameters.fileName)

    with open(parameters.saveName, 'w') as f:
    #--- File informations
        f.write(f"### Catalog generated on the {UTCDateTime()}\n")
        f.write("### Year Month Day Hour Min Sec Lat Lon Dep Mag MagType MagAuthor PhaseCount HorUncer VerUncer AzGap RMS\n")
        f.write("### Code Ins Comp Onset Phase Dir Date HHMM S.MS Err ErrMag CodaDur P2PAmp PeriodAmp # RealPhase Channel PickOrigin PGV\n")
        f.write("\n")

    #---- Event
        for ind, line in enumerate(lines):
            # Find new event
            if line.startswith(' Localisation'):
                # Check if longitude is W
                eventHeaderLine = lines[ind+2]
                invertedLon = -1 if eventHeaderLine[35] == 'W' else 1

                #--- Retrieve event informations from 4th line after ' Localisation'
                eventInfoLine = lines[ind+4]
                
                year = int(eventInfoLine[0:3])
                month = int(eventInfoLine[3:5])
                day = int(eventInfoLine[5:7])
                hour = int(eventInfoLine[8:10])
                minute = int(eventInfoLine[10:12])
                second = float(eventInfoLine[13:18])
                latitudeTemp = int(eventInfoLine[19:21])
                latitudeSec = float(eventInfoLine[22:27])
                longitudeTemp = int(eventInfoLine[29:31])
                longitudeSec = float(eventInfoLine[32:37])
                depth = float(eventInfoLine[39:44])
                rms = float(eventInfoLine[45:50])
                magnitude = float(eventInfoLine[51:54])

                # Next if magnitude if under 0
                if magnitude < 0:
                    continue

                #--- Watch for exceptions
                # Update Lat/Lon
                latitude = latitudeTemp + latitudeSec/60
                longitude = invertedLon * (longitudeTemp + longitudeSec/60)

                # Update Year
                if year < 78: # then 21st century
                    year = 2000+year
                else: # then 20th century
                    year = 1900+year

                # Check for strange hours above 24 (probably 23 and day before)
                weirdHour = False
                if hour >= 24:
                    hour = 23
                    weirdHour = True

                # Update Seconds (no need for minutes check here !)
                if second >= 60:
                    second -= 60
                    minute += 1

                # Verify if the day exists
                try:
                    UTCDateTime(f'{year}-{month}-{day}T{hour}:{minute}:{second}Z')
                except:
                    continue

                # Keep date for Phases
                eventDate = datetime.datetime(year, month, day, 0, 0, 0)

                # Unknown info
                az_gap = None
                magnitude_type = 'ML'
                magnitude_author = 'OMP'

                phases_count = None
                H_uncertainty = None
                V_uncertainty = None

                # Don't use if mag is 9.9
                if magnitude == 9.9:
                    continue

                # Write event line
                f.write(
                    f"# {year} {month} {day} {hour} {minute}"
                    f" {second} {latitude} {longitude} {depth} {magnitude}"
                    f" {magnitude_type} {magnitude_author} {phases_count} {H_uncertainty} {V_uncertainty} {az_gap} {rms}\n"
                )

    #---- Phases
                # Phases : from 7th line after ' Localisation'
                phaseInd = ind+7
                while phaseInd < len(lines) and lines[phaseInd].strip():
                    # Reinitialize the doubleError tag before new phase
                    doubleError = False

                    #--- Retrieve current phase informations
                    phaseInfoLine = lines[phaseInd]

                    network = ''
                    station = phaseInfoLine[1:5].strip()
                    instrument = '?'
                    component = '?'
                    P_phase_onset = '?'
                    P_first_motion_dir = '?'
                    error_type = 'GAU'
                    coda_duration = '-1.00e+00'
                    max_p2p_amp = '-1.00e+00'
                    period_amp = '-1.00e+00'

                    # Lengths must match field length
                    code = (network + '.' + station).ljust(9)
                    instrument = instrument.ljust(4)
                    component = component.ljust(4)
                    P_phase_onset = P_phase_onset.ljust(1)
                    P_first_motion_dir = P_phase_onset.ljust(1)
                    error_type = error_type.ljust(3)
                    coda_duration = coda_duration.ljust(9)
                    max_p2p_amp = max_p2p_amp.ljust(9)
                    period_amp = period_amp.ljust(9)

                    #--- Check quality
                    if phaseInfoLine[23:24] == '4' or phaseInfoLine[102:103] == '0': # No data, don't use P or S pick
                        phaseInd += 1
                        continue

                    elif phaseInfoLine[23:24] == '9' or station == 'LARF': # Use S-P delay for code 9 or LARF station
                        instrument = '*'.ljust(4)

                    elif int(phaseInfoLine[23:24]) >= 2 or int(phaseInfoLine[102:103]) >= 3: # Double incertitude for bad P/S pick
                        doubleError = True

                    #--- Retrieve P-phase informations
                    phaseP = 'P'

                    # Get the timing right
                    hourP = int(phaseInfoLine[25:27])
                    if weirdHour:
                        hourP = 23
                    minuteP = int(phaseInfoLine[27:29])
                    secondP = phaseInfoLine[30:35].strip()
                    if secondP == '' or '*' in secondP:
                        continue
                    secondP = float(secondP)
                    if secondP < 0: # Strange format, - 1 minute
                        minuteP = minute -1
                        secondP = secondP + 60
                    totalSecondsP = hourP * 3600 + minuteP * 60 + secondP
                    arrivalP = eventDate + datetime.timedelta(seconds=totalSecondsP)
                    yearP = str(arrivalP.year)
                    monthP = str(arrivalP.month)
                    if len(monthP) == 1:
                        monthP = '0' + monthP
                    dayP = str(arrivalP.day)
                    if len(dayP) == 1:
                        dayP = '0' + dayP
                    hourP = str(arrivalP.hour)
                    if len(hourP) == 1 :
                        hourP = '0' + hourP
                    minuteP = str(arrivalP.minute)
                    if len(minuteP) == 1:
                        minuteP = '0' + minuteP
                    secondP = str(arrivalP.second)
                    if len(secondP) == 1:
                        secondP = '0' + secondP
                    microsecondP = str(arrivalP.microsecond)
                    if len(microsecondP) < 3:
                        microsecondP = microsecondP.zfill(3)
                    else:
                        microsecondP = microsecondP[:3]

                    # Verify if the day exists
                    try:
                        UTCDateTime(f'{yearP}-{monthP}-{dayP}T{hourP}:{minuteP}:{secondP}.{microsecondP}Z')
                    except:
                        phaseInd += 1
                        continue
                    
                    # Informations on P-phase
                    dateP = yearP + monthP + dayP
                    hoursP = hourP + minuteP
                    secondsP = secondP + '.' + microsecondP
                    errorMagP = '0.05' if not doubleError else '0.10'

                    # Lengths must match field length
                    phaseTypeP = phaseP.ljust(6)
                    errorMagP = errorMagP.ljust(9)

                    # Add informations
                    realPhaseP = phaseP.ljust(6)
                    channel = 'None'.ljust(4)
                    pick_origin = 'OMP'.ljust(9)
                    PGV = 'None'.ljust(4) # in mm/s

                    # Write phase
                    f.write(
                        f"{code} {instrument} {component} {P_phase_onset} {phaseTypeP} {P_first_motion_dir} {dateP} {hoursP} {secondsP} {error_type} {errorMagP} {coda_duration} {max_p2p_amp} {period_amp}"
                        f" # {realPhaseP} {channel} {pick_origin} {PGV}\n"
                    )

                    #--- Retrieve S-phase informations
                    phaseS = 'S'

                    # Get the timing right
                    hourS = int(phaseInfoLine[25:27])
                    if weirdHour:
                        hourS = 23
                    minuteS = int(phaseInfoLine[27:29])
                    secondS = phaseInfoLine[105:110].strip()
                    if secondS == '' or '*' in secondS:
                        continue
                    secondS = float(secondS)
                    if secondS < 0: # Strange format, - 1 minute
                        minuteS = minute -1
                        secondS = secondS + 60
                    totalSecondsS = hourS * 3600 + minuteS * 60 + secondS
                    arrivalS = eventDate + datetime.timedelta(seconds=totalSecondsS)
                    yearS = str(arrivalS.year)
                    monthS = str(arrivalS.month)
                    if len(monthS) == 1:
                        monthS = '0' + monthS
                    dayS = str(arrivalS.day)
                    if len(dayS) == 1:
                        dayS = '0' + dayS
                    hourS = str(arrivalS.hour)
                    if len(hourS) == 1 :
                        hourS = '0' + hourS
                    minuteS = str(arrivalS.minute)
                    if len(minuteS) == 1:
                        minuteS = '0' + minuteS
                    secondS = str(arrivalS.second)
                    if len(secondS) == 1:
                        secondS = '0' + secondS
                    microsecondS = str(arrivalS.microsecond)
                    if len(microsecondS) < 3:
                        microsecondS = microsecondS.zfill(3)
                    else:
                        microsecondS = microsecondS[:3]
                    
                    # Verify if the day exists
                    try:
                        UTCDateTime(f'{yearS}-{monthS}-{dayS}T{hourS}:{minuteS}:{secondS}.{microsecondS}Z')
                    except:
                        phaseInd += 1
                        continue

                    # Informations on S-phase
                    dateS = yearS + monthS + dayS
                    hoursS = hourS + minuteS
                    secondsS = secondS + '.' + microsecondS
                    errorMagS = '0.05' if not doubleError else '0.10'

                    # Lengths must match field length
                    phaseTypeS = phaseS.ljust(6)
                    errorMagS = errorMagS.ljust(9)

                    # Add informations
                    realPhaseS = phaseS.ljust(6)
                    channel = 'None'.ljust(4)
                    pick_origin = 'OMP'.ljust(9)
                    PGV = 'None'.ljust(4) # in mm/s

                    # Write phase
                    f.write(
                        f"{code} {instrument} {component} {P_phase_onset} {phaseTypeS} {P_first_motion_dir} {dateS} {hoursS} {secondsS} {error_type} {errorMagS} {coda_duration} {max_p2p_amp} {period_amp}"
                        f" # {realPhaseS} {channel} {pick_origin} {PGV}\n"
                    )

                    # Increment
                    phaseInd += 1

                # Line jump after the event
                f.write("\n")

    # Print
    print(f"Catalog succesfully written @ {parameters.saveName}\n")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileName = 'ORGCATALOGS/OMP_2016.mag',
        saveName = 'obs/OMP_2016.obs',
    )

    #---- Write OBS file
    write_catalog_to_obs(parameters)      
