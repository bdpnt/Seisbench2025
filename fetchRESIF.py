'''
fetchRESIF saves a FDSN-fetched Catalog to a QUAKEML file.
'''

from obspy.clients.fdsn import Client
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

# FUNCTION
def generate_catalog(parameters):
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
            includeallorigins=True, includeallmagnitudes=True,
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
            includeallorigins=True, includeallmagnitudes=True,
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
            includeallorigins=True, includeallmagnitudes=True,
            includearrivals=True, orderby="time-asc",
        )

        if catalog is None:
            catalog = year_catalog
        else:
            catalog += year_catalog

        print(f"Events from {year_start} to {year_end} written in Catalog")

    # Save catalog as QUAKEML
    catalog.write(parameters.fileName, format="QUAKEML")
    print(f"Catalog succesfully written @ {parameters.fileName}\n")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileName = "ORGCATALOGS/RESIF_20-25.xml",
        client_name = "RESIF",
        t1 = UTCDateTime("2020-01-01T00:00:00"),
        t2 = UTCDateTime("2026-01-01T00:00:00"),
        Lat_min = 41,
        Lat_max = 44,
        Lon_min = -3,
        Lon_max = 4,
        Mag_min = 0,
        Event_type = "earthquake,induced or triggered event",
    )

    #---- Write QUAKEML file
    catalog = generate_catalog(parameters)
