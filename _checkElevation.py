import requests
import time

def get_elevation(lat, lng):
    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lng}"
    try:
        response = requests.get(url).json()
        if "results" in response:
            return int(response["results"][0]["elevation"])
        else:
            print(f"API Error for ({lat}, {lng}): {response}")
            return 0
    except Exception as e:
        print(f"Request failed for ({lat}, {lng}): {e}")
        return 0

# MAIN
file = 'stations/OMP_stations_XML/ADDITIONAL_sta.csv'
fileSave = 'stations/OMP_stations_XML/TEST_ADD.csv'

with open(file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

updated_lines = [lines[0]]  # Keep the header

for line in lines[1:]:
    if line == '\n':
        continue
    infos = line.strip().split(',')
    latitude = float(infos[2])
    longitude = float(infos[3])
    elevation = float(infos[4])

    if elevation != 0:
        updated_lines.append(line)
        continue
    else:
        new_elevation = get_elevation(latitude, longitude)
        infos[4] = str(new_elevation)
        updated_lines.append(','.join(infos) + '\n')
        time.sleep(1)  # Avoid rate limiting

with open(fileSave, 'w', encoding='utf-8') as f:
    f.writelines(updated_lines)
