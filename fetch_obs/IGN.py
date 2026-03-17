from obspy import UTCDateTime

def safe_float(s):
    try:
        return float(s.strip())
    except Exception:
        return None
    
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

    #--- Event
        for ind, line in enumerate(lines):
            # Check for new event
            if line.startswith("DATA_TYPE"):
                # Informations on event : 4th line after DATA_TYPE
                event_info = lines[ind+4].rstrip('\n')
                year = event_info[0:4].strip()
                month = event_info[5:7].strip()
                day = event_info[8:10].strip()
                ev_hour = event_info[11:13].strip()
                minute = event_info[14:16].strip()
                second = event_info[17:22].strip()
                latitude = safe_float(event_info[36:44])
                longitude = safe_float(event_info[45:54])
                depth = safe_float(event_info[71:76])
                az_gap = safe_float(event_info[92:97])
                rms = safe_float(event_info[30:35])

                # Informations on magnitude : 11th line after DATA_TYPE
                mag_info = lines[ind+11].rstrip('\n')
                magnitude = safe_float(mag_info[7:10])
                magnitude_type = mag_info[0:6].strip()
                magnitude_author = mag_info[20:29].strip()

                phases_count = safe_float(event_info[89:93])
                H_uncertainty = None
                V_uncertainty = None

                # Write event line
                f.write(
                    f"# {year} {month.lstrip('0')} {day.lstrip('0')} {ev_hour.lstrip('0') if ev_hour != '00' else '0'} {minute.lstrip('0') if minute != '00' else '0'}"
                    f" {second[1:] if second.startswith('00') else second.lstrip('0')} {latitude} {longitude} {depth} {magnitude}"
                    f" {magnitude_type} {magnitude_author} {phases_count} {H_uncertainty} {V_uncertainty} {az_gap} {rms}\n"
                )

    #--- Phases
                # Phases : from 15th line after DATA_TYPE
                phase_ind = ind+15
                while phase_ind < len(lines) and lines[phase_ind].strip():
                    # Informations on phase
                    phase_info = lines[phase_ind].rstrip('\n')

                    # If not a P or S phase or not a manual phase
                    if (not phase_info[19:27].strip().lower().startswith('p')) and (not phase_info[19:27].strip().lower().startswith('s')):
                        phase_ind += 1
                        continue
                    elif phase_info[99:102] != 'm__':
                        phase_ind += 1
                        continue
                    
                    network = phase_info[114:116].strip()
                    station = phase_info[0:7].strip()
                    instrument = '?'
                    component = '?'
                    P_phase_onset = '?'
                    phase = phase_info[19:27].strip()
                    P_first_motion_dir = '?'
                    hour = phase_info[28:30].strip()
                    minute = phase_info[31:33].strip()
                    second = phase_info[34:36].strip()
                    microsecond = phase_info[37:41].strip()
                    error_type = 'GAU'
                    error_mag = '0.05' if phase.lower().startswith('p') else '0.15' # 0.05 pour P et 0.15 pour S
                    coda_duration = '-1.00e+00'
                    max_p2p_amp = '-1.00e+00'
                    period_amp = '-1.00e+00'

                    # Lengths must match field length
                    code = (network + '.' + station).ljust(9)
                    instrument = instrument.ljust(4)
                    component = component.ljust(4)
                    P_phase_onset = P_phase_onset.ljust(1)
                    phase_type = phase[0].ljust(6)
                    P_first_motion_dir = P_phase_onset.ljust(1)
                    if ev_hour == '23' and hour == '00': # if event hour is 23 and phase hour is 00, day must be ajusted
                        phase_day = str(int(day.lstrip('0')) + 1).ljust(2)
                        date = year + month + phase_day
                    else:
                        date = year + month + day
                    hours = hour + minute
                    seconds = second + '.' + microsecond
                    error_type = error_type.ljust(3)
                    error_mag = error_mag.ljust(9)
                    coda_duration = coda_duration.ljust(9)
                    max_p2p_amp = max_p2p_amp.ljust(9)
                    period_amp = period_amp.ljust(9)

                    # Add informations
                    real_phase = phase.ljust(6)
                    channel = phase_info[119:123].strip().ljust(4)
                    pick_origin = 'IGN'.ljust(9)
                    PGV = 'None'.ljust(4) # in mm/s

                    # Write phase line
                    f.write(
                        f"{code} {instrument} {component} {P_phase_onset} {phase_type} {P_first_motion_dir} {date} {hours} {seconds} {error_type} {error_mag} {coda_duration} {max_p2p_amp} {period_amp}"
                        f" # {real_phase} {channel} {pick_origin} {PGV}\n"
                    )

                    # Increment phase_ind
                    phase_ind += 1

                # Line jump after the event
                f.write("\n")
    
    # Print
    print(f"Catalog succesfully written @ {parameters.saveName}\n")
