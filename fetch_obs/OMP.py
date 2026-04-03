from dataclasses import dataclass
import datetime
from obspy import UTCDateTime

@dataclass
class OMPParams:
    fileName: str
    saveName: str

def open_catalog(fileName):
    """Read a catalog file and return its lines as a list of strings."""
    with open(fileName, 'r', encoding='utf-8', errors='ignore') as fR:
        lines = fR.readlines()

    print(f"\nEvents from Catalog @ {fileName} succesfully retrieved")
    return lines

def _format_arrival_datetime(arrival):
    """Return (date, hours, seconds) strings formatted for the .obs bulletin."""
    microsecond_str = str(arrival.microsecond)
    microsecond_str = microsecond_str.zfill(3) if len(microsecond_str) < 3 else microsecond_str[:3]
    date = f"{arrival.year:04d}{arrival.month:02d}{arrival.day:02d}"
    hours = f"{arrival.hour:02d}{arrival.minute:02d}"
    seconds = f"{arrival.second:02d}.{microsecond_str}"
    return date, hours, seconds

def write_catalog_to_obs(parameters):
    """Convert the OMP .mag catalog to the .obs bulletin format, extracting P and S picks."""
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
                except Exception:
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
                        phaseInd += 1
                        continue
                    secondP = float(secondP)
                    if secondP < 0: # Strange format, - 1 minute
                        minuteP = minute -1
                        secondP = secondP + 60
                    totalSecondsP = hourP * 3600 + minuteP * 60 + secondP
                    arrivalP = eventDate + datetime.timedelta(seconds=totalSecondsP)

                    # Verify if the day exists
                    try:
                        UTCDateTime(f'{arrivalP.year}-{arrivalP.month}-{arrivalP.day}T{arrivalP.hour}:{arrivalP.minute}:{arrivalP.second}.{arrivalP.microsecond}Z')
                    except Exception:
                        phaseInd += 1
                        continue

                    # Informations on P-phase
                    dateP, hoursP, secondsP = _format_arrival_datetime(arrivalP)
                    errorMagP = ('0.05' if not doubleError else '0.10').ljust(9)

                    # Lengths must match field length
                    phaseTypeP = phaseP.ljust(6)

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
                        phaseInd += 1
                        continue
                    secondS = float(secondS)
                    if secondS < 0: # Strange format, - 1 minute
                        minuteS = minute -1
                        secondS = secondS + 60
                    totalSecondsS = hourS * 3600 + minuteS * 60 + secondS
                    arrivalS = eventDate + datetime.timedelta(seconds=totalSecondsS)

                    # Verify if the day exists
                    try:
                        UTCDateTime(f'{arrivalS.year}-{arrivalS.month}-{arrivalS.day}T{arrivalS.hour}:{arrivalS.minute}:{arrivalS.second}.{arrivalS.microsecond}Z')
                    except Exception:
                        phaseInd += 1
                        continue

                    # Informations on S-phase
                    dateS, hoursS, secondsS = _format_arrival_datetime(arrivalS)
                    errorMagS = ('0.05' if not doubleError else '0.10').ljust(9)

                    # Lengths must match field length
                    phaseTypeS = phaseS.ljust(6)

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
