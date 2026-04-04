import requests
import time
import pandas as pd

def get_elevation(lat, lng):
    """Query the Open-Elevation API and return the elevation in metres for a given coordinate."""
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


def check_elevation(file, file_save):
    """Fill in missing elevations (value 0) in a station CSV by querying the Open-Elevation API."""
    df = pd.read_csv(file, dtype={'latitude': 'float64', 'longitude': 'float64', 'elevation': 'float32'})

    for idx in df.index[df['elevation'] == 0]:
        df.at[idx, 'elevation'] = get_elevation(df.at[idx, 'latitude'], df.at[idx, 'longitude'])
        time.sleep(1)  # Avoid rate limiting

    df.to_csv(file_save, index=False)


if __name__ == '__main__':
    check_elevation(
        file='stations/OMP_stations_XML/ADDITIONAL_sta.csv',
        file_save='stations/OMP_stations_XML/TEST_ADD.csv',
    )
