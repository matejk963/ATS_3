# -*- coding: utf-8 -*-
"""
Created on Thu Jul 18 11:28:46 2024

@author: krajcovic
"""
import requests
import pandas as pd
from io import StringIO
import re
import pickle

month_mapping = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12
}

# URL of the file
url = "https://ftp.cpc.ncep.noaa.gov/wd52dg/data/indices/tele_index.nh"

url = 'https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_ao_index/monthly.ao.index.b50.current.ascii.table'

# Fetch the content of the file
response = requests.get(url)

# Check if the request was successful
if response.status_code == 200:
    # Get the content of the file
    data = response.text

    # Insert a space before each occurrence of -99.90
    data = re.sub(r'(?<!\s)-99.90', ' -99.90', data)

    # Define column names
    columns = [
        "Year", "Month", "NAO", "EA", "WP", "EP/NP", "PNA", "EA/WR", "SCA", 
        "TNH", "POL", "PT", "Explained Variance"
    ]
    
    # Use StringIO to treat the response text as a file-like object
    df = pd.read_csv(StringIO(data), delim_whitespace=True)
    df = df.stack().reset_index()
    df.columns = ['Year', 'Month', 'AO']
    df['Month'] = df['Month'].map(month_mapping)
    # Display the DataFrame
    print(df)
else:
    print(f"Failed to retrieve the file. Status code: {response.status_code}")

file_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Weather\ao_indices.pickle'

with open(file_path, 'wb') as file:
    pickle.dump(df,file)



