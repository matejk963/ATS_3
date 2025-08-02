import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import pickle
import xarray as xr

# Load regime strengths and times
# regimes_file = r'Z:\Data\Spot\Weather\Regimes\regime_probabilities_1000_PCs_7_clusters.pkl'
# with open(regimes_file, 'rb') as f:
#     regime_index = pickle.load(f)

file = r'Z:\Data\Spot\Weather\Regimes\regime_non_normalized_projection.nc'
ds = xr.open_dataset(file).to_array().squeeze('variable')
df = pd.DataFrame(ds)


for col in df.columns:
    mean = df[col].mean()
    std = df[col].std()
    df[col] = (df[col]-mean)/std


