from parameters import Parameters
import fetch_obs
from obspy import UTCDateTime

# RESIF
params_resif = Parameters(
    fileName = "ORGCATALOGS/RESIF_20-25.xml",
    saveName = "obs/RESIF_20-25.obs",
    client_name = "RESIF",
    t1 = UTCDateTime("2020-01-01T00:00:00"),
    t2 = UTCDateTime("2026-01-01T00:00:00"),
    Lat_min = 41,
    Lat_max = 44,
    Lon_min = -3,
    Lon_max = 4,
    Mag_min = 0,
    Event_type = "earthquake",
    magType = "MLv",
)

fetch_obs.RESIF.generate_catalog(params_resif)
fetch_obs.RESIF.write_catalog_to_obs(params_resif)

# ICGC
params_icgc = Parameters(
    fileName = 'ORGCATALOGS/ICGC_20-25.txt',
    codeName = 'ORGCATALOGS/CODES_ICGC_20-25.txt',
    errorName = 'ORGCATALOGS/ERR_ICGC_20-25.txt',
    saveName = 'obs/ICGC_20-25.obs',
    start_year = 2020,
    start_month = 1,
    end_year = 2025,
    end_month = 12,
    magMin = 0,
)

fetch_obs.ICGC.get_all_codes(params_icgc)
fetch_obs.ICGC.fetch_catalog(params_icgc)
fetch_obs.ICGC.write_catalog_to_obs(params_icgc)

# IGN
params_ign = Parameters(
    fileName = 'ORGCATALOGS/IGN_20-25.txt',
    saveName = 'obs/IGN_20-25.obs',
)

fetch_obs.IGN.write_catalog_to_obs(params_ign)

# LDG
params_ldg = Parameters(
    catalogFile = 'ORGCATALOGS/LDG_20-25_catalog.txt',
    arrivalFile = 'ORGCATALOGS/LDG_20-25_arrivals.txt',
    saveName = 'obs/LDG_20-25.obs',
)

fetch_obs.IGN.write_catalog_to_obs(params_ldg)

# OMP
params_omp_1978 = Parameters(
    fileName = 'ORGCATALOGS/OMP_78-19.mag',
    saveName = 'obs/OMP_78-19.obs',
)

fetch_obs.OMP.write_catalog_to_obs(params_omp_1978) 

params_omp_2016 = Parameters(
    fileName = 'ORGCATALOGS/OMP_2016.mag',
    saveName = 'obs/OMP_2016.obs',
)

fetch_obs.OMP.write_catalog_to_obs(params_omp_2016) 