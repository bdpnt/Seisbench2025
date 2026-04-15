from fetch_obs.RESIF import RESIFParams
from fetch_obs.ICGC import ICGCParams
from fetch_obs.IGN import IGNParams
from fetch_obs.LDG import LDGParams
from fetch_obs.OMP import OMPParams
import fetch_obs
from obspy import UTCDateTime

# RESIF
params_resif = RESIFParams(
    file_name   = 'ORGCATALOGS/RESIF_20-25.xml',
    save_name   = 'obs/RESIF_20-25.obs',
    client_name = 'RESIF',
    t1          = UTCDateTime('2020-01-01T00:00:00'),
    t2          = UTCDateTime('2026-01-01T00:00:00'),
    lat_min     = 41,
    lat_max     = 44,
    lon_min     = -3,
    lon_max     = 4,
    mag_min     = -5,
    event_type  = 'earthquake',
    mag_type    = 'MLv',
)

fetch_obs.RESIF.generate_catalog(params_resif)
fetch_obs.RESIF.write_catalog_to_obs(params_resif)

# ICGC
params_icgc = ICGCParams(
    file_name   = 'ORGCATALOGS/ICGC_20-25.txt',
    code_name   = 'ORGCATALOGS/CODES_ICGC_20-25.txt',
    error_name  = 'ORGCATALOGS/ERR_ICGC_20-25.txt',
    save_name   = 'obs/ICGC_20-25.obs',
    start_year  = 2020,
    start_month = 1,
    end_year    = 2025,
    end_month   = 12,
    mag_min     = 0,
)

fetch_obs.ICGC.get_all_codes(params_icgc)
fetch_obs.ICGC.fetch_catalog(params_icgc)
fetch_obs.ICGC.write_catalog_to_obs(params_icgc)

# IGN
params_ign = IGNParams(
    file_name = 'ORGCATALOGS/IGN_20-25.txt',
    save_name = 'obs/IGN_20-25.obs',
)

fetch_obs.IGN.write_catalog_to_obs(params_ign)

# LDG
params_ldg = LDGParams(
    catalog_file = 'ORGCATALOGS/LDG_20-25_catalog.txt',
    arrival_file = 'ORGCATALOGS/LDG_20-25_arrivals.txt',
    save_name    = 'obs/LDG_20-25.obs',
)

fetch_obs.LDG.write_catalog_to_obs(params_ldg)

# OMP
params_omp_1978 = OMPParams(
    file_name = 'ORGCATALOGS/OMP_78-19.mag',
    save_name = 'obs/OMP_78-19.obs',
)

fetch_obs.OMP.write_catalog_to_obs(params_omp_1978)

params_omp_2016 = OMPParams(
    file_name = 'ORGCATALOGS/OMP_2016.mag',
    save_name = 'obs/OMP_2016.obs',
)

fetch_obs.OMP.write_catalog_to_obs(params_omp_2016)
