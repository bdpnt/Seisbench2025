'''
fetchICGC saves an ICGC-fetched Catalog to a TXT file.
'''

import requests
import os
import time

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
def iter_months(start_year, start_month, end_year, end_month):
    year, month = start_year, start_month

    while (year < end_year) or (year == end_year and month <= end_month):
        yield year, f"{month:02d}" 
        month += 1
        if month > 12:
            month = 1
            year += 1

def get_codes(year,month):
    url = f"https://sismocat.icgc.cat/siswebclient/index.php?seccio=llistat&area=locals&any={str(year).lstrip('0')}&mes={str(month).lstrip('0')}&idioma=ca"
    response = requests.get(url, timeout=15)

    if response.status_code == 200:
        html_content = response.text
        lines = html_content.split('<a class')[1:]

        codes = []
        for event in lines:
            code = event.split('>')[1].rstrip('</a')
            codes.append(code)
        return True,codes
    else:
        return False,response.status_code
    
def get_all_codes(parameters):
    with open(parameters.codeName, 'w') as f: # for codes
        with open(parameters.errorName, 'w') as fE: # for errors
            fE.write('### ERRORS DURING CODES FETCH\n')
            for year, month in iter_months(parameters.start_year, parameters.start_month, parameters.end_year, parameters.end_month):
                status,value = get_codes(year,month) # value is either the codes if True or the response status code if False
                if status:
                    for code in value:
                        f.write(f'{code}, {year}-{month}\n')
                else:
                    fE.write(f'{year}-{month} : error {value}\n')
    # Print
    print(f"Codes file succesfully written to {parameters.codeName}")
    print(f"Errors file succesfully written to {parameters.errorName}")



def fetch_catalog(parameters):
    if os.path.exists(parameters.fileName):
        os.remove(parameters.fileName)

    codes = []
    with open(parameters.codeName, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for line in lines:
            codes.append(line.split(',')[0])

    catalog_errors = []
    first_catalog_error = True
    for code in codes:
        if not code.strip():
            print(f"Skipping empty code: {code}")
            continue

        print(f"Processing code: {code}")
        url = f"http://sismocat.icgc.cat/siswebclient/index.php?seccio=gse&codi={code}"

        max_retries = 3
        for _ in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                break  # success, exit the retry loop
            except requests.exceptions.RequestException as e:
                print(f"Request failed, retrying... ({e})")
                time.sleep(2)  # wait before retrying
        else:
            print(f"Failed to fetch {url} after {max_retries} retries.")
            with open(parameters.errorName, 'a') as fE:
                if first_catalog_error:
                    first_catalog_error = False
                    fE.write('### ERRORS DURING EVENTS FETCH\n')
                fE.write(f'{code} : Failed after retries\n')
            continue

        if "S'ha produit un error" in response.text:
            print(f"Error page received for code: {code}")
            with open(parameters.errorName, 'a') as fE:
                if first_catalog_error:
                    first_catalog_error = False
                    fE.write('### ERRORS DURING EVENTS FETCH\n')
                fE.write(f'{code} : Error page received\n')
        else:
            with open(parameters.fileName, 'ab') as f:
                f.write(response.content)
            print(f"Successfully wrote code: {code}")

    # Catalog print
    print(f"Catalog successfully written to {parameters.fileName}")
    print(f"Errors file successfully written to {parameters.errorName}")


# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileName = 'ORGCATALOGS/ICGC_20-25.txt',
        codeName = 'ORGCATALOGS/CODES_ICGC_20-25.txt',
        errorName = 'ORGCATALOGS/ERR_ICGC_20-25.txt',
        start_year = 2020,
        start_month = 1,
        end_year = 2025,
        end_month = 12
    )

    #---- Write ICGC catalog
    get_all_codes(parameters)
    #fetch_catalog(parameters)
