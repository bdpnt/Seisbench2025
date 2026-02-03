'''
RESIF2obs reads a FDSN QUAKEML file and saves its data as an OBS file.
'''

from obspy import UTCDateTime, read_events

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
def fetch_catalog(parameters):
    catalog = read_events(parameters.fileName, format="QUAKEML")
    return catalog

def find_bestMagnitude(event,magType):
    try: # look for a preferred magnitude
        if event.preferred_magnitude().magnitude_type == magType:
            if not event.preferred_magnitude().creation_info.author.__contains__('auto'):
                return True, None
            else:
                raise ValueError()
        else:
            raise ValueError()
    except: # if no preferred magnitude
        try: # look for the manual magnitude with the best uncertainty
            best_mag = ()
            for i_mag, mag in enumerate(event.magnitudes):
                if mag.magnitude_type == magType:
                    if not getattr(getattr(mag, 'creation_info', 'None'), 'author', 'None').__contains__('auto'):
                        uncertainty = mag.mag_errors.uncertainty
                        if not best_mag:
                            best_mag = (i_mag,uncertainty)
                        else:
                            if uncertainty < best_mag[1]:
                                best_mag = (i_mag,uncertainty)
            if not best_mag: # if no manual magnitude with uncertainty found
                for i_mag, mag in enumerate(event.magnitudes):
                    if mag.magnitude_type == magType:
                        if getattr(mag, 'evaluation_status', 'None') == 'confirmed':
                            best_mag = (i_mag, None)
            return False, best_mag[0]
        except:
            return False, None

def write_catalog_to_obs(parameters):
    catalog = fetch_catalog(parameters)
    print(f'\nEvents from Catalog @ {parameters.fileName} succesfully retrieved')

    with open(parameters.saveName,'w') as f:
    #--- File informations
        f.write(f"### Catalog generated on the {UTCDateTime()}\n")
        f.write("### Year Month Day Hour Min Sec Lat Lon Dep Mag MagType MagAuthor PhaseCount HorUncer VerUncer AzGap RMS\n")
        f.write("### Code Ins Comp Onset Phase Dir Date HHMM S.MS Err ErrMag CodaDur P2PAmp PeriodAmp # RealPhase Channel PickOrigin PGV\n")
        f.write("\n")

    #--- Event
        for event in catalog:
            origin = event.origins[0]
            year = origin.time.year
            month = origin.time.month
            day = origin.time.day
            hour = origin.time.hour
            minute = origin.time.minute
            second = origin.time.second
            latitude = origin.latitude
            longitude = origin.longitude
            depth = origin.depth / 1000.0  # in km
            try: # Find the best MLv magnitude, otherwise do not add the event
                i_val,i_mag = find_bestMagnitude(event,parameters.magType)
                if i_val:
                    magnitude = event.preferred_magnitude().mag
                    magnitude_type = event.preferred_magnitude().magnitude_type
                    magnitude_author = event.preferred_magnitude().creation_info.agency_id
                    pass
                elif i_mag:
                    magnitude = event.magnitudes[i_mag].mag
                    magnitude_type = event.magnitudes[i_mag].magnitude_type
                    magnitude_author = event.magnitudes[i_mag].magnitude().creation_info.agency_id
                else:
                    raise ValueError()
            except:
                continue
            phases_count = getattr(getattr(origin, 'quality', None), 'associated_phase_count', None)
            H_uncertainty = getattr(getattr(origin,'quality', None), 'horizontal_uncertainty', None)
            V_uncertainty = getattr(getattr(origin, 'quality', None), 'vertical_uncertainty', None)
            az_gap = getattr(getattr(origin, 'quality', None), 'azimuthal_gap', None)
            rms = getattr(getattr(origin, 'quality', None), 'standard_error', None)
            
            # Write event line
            f.write(f"# {year} {month} {day} {hour} {minute} {second} {latitude} {longitude} {depth} {magnitude} {magnitude_type} {magnitude_author} {phases_count} {H_uncertainty} {V_uncertainty} {az_gap} {rms}\n")

    #--- Phases
            picks = event.picks

            for pick in picks:
                # If not a P or S phase ; or not a manual phase
                if (not pick.phase_hint.lower().startswith('p')) and (not pick.phase_hint.lower().startswith('s')):
                    continue
                elif getattr(pick, 'evaluation_mode', None) != 'manual':
                    continue

                # Retrieve informations
                network = str(pick.waveform_id.network_code)
                station = str(pick.waveform_id.station_code)
                instrument = '?'
                component = '?'
                P_phase_onset = '?'
                phase = str(pick.phase_hint)
                P_first_motion_dir = '?'
                year = str(pick.time.year).zfill(4)
                month = str(pick.time.month).zfill(2)
                day = str(pick.time.day).zfill(2)
                hour = str(pick.time.hour).zfill(2)
                minute = str(pick.time.minute).zfill(2)
                second = str(pick.time.second).zfill(2)
                microsecond = str(int(pick.time.microsecond/100)).zfill(4)
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
                channel = str(pick.waveform_id.channel_code).ljust(4)
                pick_origin = 'FDSN'.ljust(9)
                PGV = 'None'.ljust(4) # in mm/s
                
                # Write phase line
                f.write(
                    f"{code} {instrument} {component} {P_phase_onset} {phase_type} {P_first_motion_dir} {date} {hours} {seconds} {error_type} {error_mag} {coda_duration} {max_p2p_amp} {period_amp}"
                    f" # {real_phase} {channel} {pick_origin} {PGV}\n"
                )
            
            # Line jump after the event
            f.write("\n")
    
    # Print
    print(f"Catalog succesfully written @ {parameters.saveName}\n")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileName = "ORGCATALOGS/RESIF_20-25.xml",
        saveName = "obs/RESIF_20-25.obs",
        magType = "MLv", # type of magnitude to extract (removes any event w/o this magnitude type)
    )

    #---- Write OBS file
    write_catalog_to_obs(parameters)
