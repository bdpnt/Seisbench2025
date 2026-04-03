from dataclasses import dataclass
from obspy.clients.fdsn import Client
from obspy import UTCDateTime, read_events

@dataclass
class RESIFParams:
    client_name: str
    t1: UTCDateTime
    t2: UTCDateTime
    Lat_min: float
    Lat_max: float
    Lon_min: float
    Lon_max: float
    Mag_min: float
    Event_type: str
    fileName: str
    saveName: str
    magType: str

def generate_catalog(parameters):
    """Query the FDSN client year by year and accumulate events into a QuakeML catalog file."""
    #---- Initiate catalog
    print('\n')
    client = Client(parameters.client_name)
    catalog = None

    #---- Extract start and end times
    t1 = parameters.t1
    t2 = parameters.t2

    #---- Loop on years, including partial years at start/end if needed
    current_year = t1.year
    end_year = t2.year

    # First partial year (if t1 is not Jan 1)
    if t1.month != 1 or t1.day != 1 or t1.hour != 0 or t1.minute != 0 or t1.second != 0:
        year_start = t1
        year_end = UTCDateTime(f"{current_year + 1}-01-01T00:00:00")
        if year_end > t2:
            year_end = t2

        year_catalog = client.get_events(
            starttime=year_start, endtime=year_end,
            minlatitude=parameters.Lat_min, maxlatitude=parameters.Lat_max,
            minlongitude=parameters.Lon_min, maxlongitude=parameters.Lon_max,
            minmagnitude=parameters.Mag_min, eventtype=parameters.Event_type,
            includeallorigins=False, includeallmagnitudes=False,
            includearrivals=True, orderby="time-asc",
        )

        if catalog is None:
            catalog = year_catalog
        else:
            catalog += year_catalog

        print(f"Events from {year_start} to {year_end} written in Catalog")
        current_year += 1

    # Full years
    while current_year < end_year:
        year_start = UTCDateTime(f"{current_year}-01-01T00:00:00")
        year_end = UTCDateTime(f"{current_year + 1}-01-01T00:00:00")

        year_catalog = client.get_events(
            starttime=year_start, endtime=year_end,
            minlatitude=parameters.Lat_min, maxlatitude=parameters.Lat_max,
            minlongitude=parameters.Lon_min, maxlongitude=parameters.Lon_max,
            minmagnitude=parameters.Mag_min, eventtype=parameters.Event_type,
            includeallorigins=False, includeallmagnitudes=False,
            includearrivals=True, orderby="time-asc",
        )

        if catalog is None:
            catalog = year_catalog
        else:
            catalog += year_catalog

        print(f"Events from {current_year} written in Catalog")
        current_year += 1

    # Last partial year (if t2 is not Jan 1)
    if t2.month != 1 or t2.day != 1 or t2.hour != 0 or t2.minute != 0 or t2.second != 0:
        year_start = UTCDateTime(f"{end_year}-01-01T00:00:00")
        year_end = t2

        year_catalog = client.get_events(
            starttime=year_start, endtime=year_end,
            minlatitude=parameters.Lat_min, maxlatitude=parameters.Lat_max,
            minlongitude=parameters.Lon_min, maxlongitude=parameters.Lon_max,
            minmagnitude=parameters.Mag_min, eventtype=parameters.Event_type,
            includeallorigins=False, includeallmagnitudes=False,
            includearrivals=True, orderby="time-asc",
        )

        if catalog is None:
            catalog = year_catalog
        else:
            catalog += year_catalog

        print(f"Events from {year_start} to {year_end} written in Catalog")

def fetch_catalog(parameters):
    """Load an existing QuakeML catalog file and return it as an obspy Catalog object."""
    catalog = read_events(parameters.fileName, format="QUAKEML")
    return catalog

def find_bestMagnitude(event,magType):
    """Find the best available magnitude of a given type for an event.

    Returns (True, None) if a valid preferred magnitude is found, (False, index) if a
    manual magnitude is found by searching, or (False, None) if none is available.
    """
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
    """Convert a QuakeML catalog to the .obs bulletin format, keeping only manual P/S picks."""
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
            second = origin.time.second + origin.time.microsecond/1e6
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
                microsecond = str(int(pick.time.microsecond/1000)).zfill(3)
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

    # Save catalog as QUAKEML
    catalog.write(parameters.fileName, format="QUAKEML")
    print(f"Catalog succesfully written @ {parameters.fileName}\n")
