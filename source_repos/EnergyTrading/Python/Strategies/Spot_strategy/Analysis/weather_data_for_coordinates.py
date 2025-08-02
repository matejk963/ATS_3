# -*- coding: utf-8 -*-
"""
Created on Wed Jul 17 14:05:10 2024

@author: krajcovic
"""

import pandas as pd
import requests
import requests_cache
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import openmeteo_requests
import time
from pyproj import Transformer

import pickle

file_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Weather\spacial_coordinates.pickle'
with open(file_path, 'rb') as file:
    final_df = pickle.load(file)
    
# Convert projected coordinates to geographic coordinates
transformer = Transformer.from_crs("epsg:3395", "epsg:4326", always_xy=True)
final_df[['longitude', 'latitude']] = final_df.apply(
    lambda row: pd.Series(transformer.transform(row['longitude'], row['latitude'])),
    axis=1
)

# Function to retry the request on failure
def retry(session, retries, backoff_factor):
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Function to fetch weather data for given coordinates and time range with backoff
def fetch_weather_data_for_country(latitudes, longitudes, start_date, end_date):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ["pressure_msl", "wind_speed_10m", "wind_speed_100m", "direct_radiation"],
        "wind_speed_unit": "ms",
        "timezone": "Europe/Berlin"
    }
    attempt = 0
    max_attempts = 5
    while attempt < max_attempts:
        try:
            responses = openmeteo.weather_api(url, params=params)
            return responses
        except requests.exceptions.RequestException as e:
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
                # Wait and retry
                wait_time = (2 ** attempt) * 60  # exponential backoff: 1, 2, 4, 8, 16 minutes
                print(f"Rate limit exceeded. Waiting for {wait_time // 60} minutes before retrying...")
                time.sleep(wait_time)
                attempt += 1
            else:
                raise
    raise Exception("Failed to fetch weather data after multiple attempts due to rate limiting.")

# Assuming final_df is already defined and contains 'longitude', 'latitude', and 'country' columns
# final_df = ...

# Group data by country and prepare to fetch weather data
weather_data_by_country = {}

for country, group in final_df.groupby('country'):
    latitudes = group['latitude'].tolist()
    longitudes = group['longitude'].tolist()
    responses = fetch_weather_data_for_country(latitudes, longitudes, "2000-01-01", "2024-07-15")
    weather_data_by_country[country] = responses

# Process and print weather data for each country
for country, responses in weather_data_by_country.items():
    print(f"Weather data for {country}:")
    for i, response in enumerate(responses):
        print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
        print(f"Elevation {response.Elevation()} m asl")
        print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
        print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")
        
        # Process hourly data
        hourly = response.Hourly()
        hourly_pressure_msl = hourly.Variables(0).ValuesAsNumpy()
        hourly_wind_speed_10m = hourly.Variables(1).ValuesAsNumpy()
        hourly_wind_speed_100m = hourly.Variables(2).ValuesAsNumpy()
        hourly_direct_radiation = hourly.Variables(3).ValuesAsNumpy()
        
        hourly_data = {"date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        )}
        hourly_data["pressure_msl"] = hourly_pressure_msl
        hourly_data["wind_speed_10m"] = hourly_wind_speed_10m
        hourly_data["wind_speed_100m"] = hourly_wind_speed_100m
        hourly_data["direct_radiation"] = hourly_direct_radiation
        
        hourly_dataframe = pd.DataFrame(data=hourly_data)
        print(f"Hourly data for {country} at point {i}:")
        print(hourly_dataframe)
# You can store weather_data_by_cou

# You can store weather_data_by_country in a file or further process as needed
