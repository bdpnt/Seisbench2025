'''
LDG2obs reads both catalog and arrivals LDG TXT files and saves their data as an OBS file.
'''

import pandas as pd
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
def write_catalog_to_obs(parameters):
    #---- Build Dataframes
    catalog = pd.read_csv(parameters.catalogFile,sep=';',header=0)
    arrivals = pd.read_csv(parameters.arrivalFile,sep=';',header=0)

    print(f'\nEvents from Catalog @ {parameters.catalogFile} succesfully retrieved')
    print(f'Picks from Bulletin @ {parameters.arrivalFile} succesfully retrieved')

    #---- Write OBS file
    with open(parameters.saveName, 'w') as f:
        #--- File informations
        f.write(f"### Catalog generated on the {UTCDateTime()}\n")
        f.write("### Year Month Day Hour Min Sec Lat Lon Dep Mag MagType MagAuthor PhaseCount HorUncer VerUncer AzGap RMS\n")
        f.write("### Code Ins Comp Onset Phase Dir Date HHMM S.MS Err ErrMag CodaDur P2PAmp PeriodAmp # RealPhase Channel PickOrigin PGV\n")
        f.write("\n")

        #--- Events
        for row in catalog.itertuples():
            # Informations on event
            year = row.datetime[6:10]
            month = row.datetime[3:5]
            day = row.datetime[0:2]
            hour = row.datetime[11:13]
            minute = row.datetime[14:16]
            second = row.datetime[17:19]
            latitude = row.lat
            longitude = row.lon
            depth = row.depth
            az_gap = row.gap1
            rms = row.rms

            # Informations on magnitude if it exists
            magnitude = row.ML if not row.ML==-999 else (row.MD if not row.MD==-999 else None)
            if not magnitude:
                continue
            magnitude_type = 'ML' if not row.ML==-999 else 'MD'
            magnitude_author = 'LDG'

            phases_count = row.nbmagML if not row.ML==-999 else row.nbmagMD
            H_uncertainty = None
            V_uncertainty = None

            # Write event line
            f.write(
                f"# {year} {month.lstrip('0')} {day.lstrip('0')} {hour.lstrip('0') if hour != '00' else '0'} {minute.lstrip('0') if minute != '00' else '0'}"
                f" {second[1:] if second.startswith('00') else second.lstrip('0')} {latitude} {longitude} {depth} {magnitude}"
                f" {magnitude_type} {magnitude_author} {phases_count} {H_uncertainty} {V_uncertainty} {az_gap} {rms}\n"
            )

        #--- Phases
            # Get event ID
            eventID = row.orid
            for rowP in arrivals[arrivals.orid==eventID].itertuples():
                # If not a P or S phase
                if (not rowP.phase.strip().lower().startswith('p')) and (not rowP.phase.strip().lower().startswith('s')):
                    continue

                # Informations on phase
                network = ''
                station = rowP.sta
                instrument = '?'
                component = '?' 
                P_phase_onset = '?'
                phase = rowP.phase
                P_first_motion_dir = '?'
                year = rowP.arrtime[6:10]
                month = rowP.arrtime[3:5]
                day = rowP.arrtime[0:2]
                hour = rowP.arrtime[11:13]
                minute = rowP.arrtime[14:16]
                second = rowP.arrtime[17:22]
                error_type = 'GAU'
                error_mag = '0.05' if rowP.phase.lower().startswith('p') else '0.15' # 0.05 pour P et 0.15 pour S
                coda_duration = '-1.00e+00' # actually rowP.duration gives coda duration in seconds
                max_p2p_amp = '-1.00e+00' # actually rowP.amp gives amplitude in nm
                period_amp = '-1.00e+00' # actually rowP.per gives period in seconds

                # Lengths must match field lengths
                code = (network + '.' + station).ljust(9)
                instrument = instrument.ljust(4)
                component = component.ljust(4)
                P_phase_onset = P_phase_onset.ljust(1)
                phase_type = phase[0].ljust(6)
                P_first_motion_dir = P_phase_onset.ljust(1)
                date = year + month + day
                hours = hour + minute
                error_type = error_type.ljust(3)
                error_mag = error_mag.ljust(9)
                coda_duration = coda_duration.ljust(9)
                max_p2p_amp = max_p2p_amp.ljust(9)
                period_amp = period_amp.ljust(9)

                # Add informations
                real_phase = phase.ljust(6)
                channel = 'None'.ljust(4)
                pick_origin = 'LDG'.ljust(9)
                PGV = 'None'.ljust(4) # in mm/s

                # Write phase line
                f.write(
                    f"{code} {instrument} {component} {P_phase_onset} {phase_type} {P_first_motion_dir} {date} {hours} {second} {error_type} {error_mag} {coda_duration} {max_p2p_amp} {period_amp}"
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
        catalogFile = 'ORGCATALOGS/LDG_20-25_catalog.txt',
        arrivalFile = 'ORGCATALOGS/LDG_20-25_arrivals.txt',
        saveName = 'obs/LDG_20-25.obs',
    )

    #---- Write OBS file
    write_catalog_to_obs(parameters)
