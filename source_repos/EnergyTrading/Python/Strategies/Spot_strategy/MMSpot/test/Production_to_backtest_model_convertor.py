# -*- coding: utf-8 -*-
"""
Created on Tue Sep 17 10:25:22 2024

@author: krajcovic
"""

# -*- coding: utf-8 -*-
"""
Created on Fri Jan 26 14:39:45 2024

@author: Marek
"""

import json
import pandas as pd
import numpy as np
from dateutil import parser
import pytz
from Math.accumfeatures import MSTD
from Strategies.Spot_strategy.MMSpot.model_class import simple_model
import matplotlib.pyplot as plt


def model_mstd_x(mid_ser, param_list, tm):
    mid_list = mid_ser.to_list()
    # Create model
    N = 30
    tau = param_list[0]
    tol = param_list[1]
    std0 = param_list[2]
    model = simple_model(MSTD(tau, N, std0), [tau / 2, N, 2, mid_list[0], std0],
                         'mstd', burn=0, time_model=tm, tol=tol)
    return pd.DataFrame(model.predict(mid_list), index=mid_ser.index)


def calibrate(model_ser, mid_list, ts, tau_range):
    score_dict = {t: np.nan for t in tau_range}
    for t in tau_range:
        df_pmodel = model_mstd_x(mid_list, [t, 0.025, 2], False)
        df_pmodel = df_pmodel.reindex(ts).ffill().loc[model_ser.index, :]
        score_dict[t] = (model_ser - df_pmodel.iloc[:, 0]).abs().sum()
    return score_dict


# Path to your JSON file
file_path = r'Z:\Algo_data\algo_prod_mm_de_w12_v_a1_2024-09-23.json'

# Load the JSON data
with open(file_path, 'r') as file:
    json_data = json.load(file)


cet_zone = pytz.timezone('CET')
ts_list = []
spread_list = []
std_list = []
mid_list = []

for entry in json_data:
    # Each entry is a dictionary with one key (timestamp) and a value (another dictionary)
    new_dict = {entry['fields']['timestamp'][0]: entry['fields']}
    for timestamp, data in new_dict.items():
        # Extract model_dict.spread and model_dict.std
        spread = data.get('model_dict.spread', [None])[0]  # Default to None if not found
        std = data.get('model_dict.std', [None])[0]      # Default to None if not found
        mid = (.5 * (data.get('price_leg_dict.10641710_10000102_1187.buy', [None])[0] +
                     data.get('price_leg_dict.10641710_10000102_1187.sell', [None])[0]) -
               .5 * (data.get('price_leg_dict.10641710_10000102_1188.buy', [None])[0] +
                     data.get('price_leg_dict.10641710_10000102_1188.sell', [None])[0]))
        utc_dt = parser.parse(timestamp)
        
        ts_list.append(utc_dt.astimezone(cet_zone).replace(tzinfo=None))
        spread_list.append(spread)
        std_list.append(std)
        mid_list.append(mid)

pd_data = pd.DataFrame({'spread': spread_list, 'std': std_list, 'mid': mid_list}, index=ts_list)


specific_date = pd.to_datetime('2024-09-23')

# Filter the DataFrame to include only rows with the specific date
pd_data_n = pd_data[pd_data.index.date == specific_date.date()].sort_index()

# Load data from our sample
df_ba = pd.read_csv(r'Z:\Data\Spot\MM\Inputs\df_ba_de_w1w2_20240916.csv')
df_ba.set_index('timestamp', inplace=True)
df_ba.index = pd.to_datetime(df_ba.index)

ts = pd_data_n.index.union(df_ba.index).drop_duplicates()
pd_data_ = pd_data_n.reindex(ts).ffill().loc[df_ba.index, :]

data_prod = pd_data_.dropna(how='all')
df_ba_ = df_ba.loc[data_prod.index[0]:, :]
mid_ = .5 * (df_ba_.iloc[:, 0] + df_ba_.iloc[:, 1])

data_model = model_mstd_x(mid_, [10, 0.025,2], False) #2.01
# data_model2 = model_mstd_x(mid_2, [72, 0.025,2], False) #2.01

df_ba_s = df_ba.reindex(ts).ffill().loc[pd_data_n.index, :]
mid_s = .5 * (df_ba_s.iloc[:, 0] + df_ba_s.iloc[:, 1])

data_model_ = data_model.reindex(ts).ffill().loc[pd_data_n.index, :]
# data_model_2 = data_model2.reindex(ts).ffill().loc[pd_data_n.index, :]

pd.concat([data_model_.iloc[:, 0], pd_data_n.iloc[:, 0]], axis=1).plot()
# pd.concat([data_model_2.iloc[:, 0], pd_data_n.iloc[:, 0]], axis=1).plot()
pd.concat([data_model_.iloc[:, 1], pd_data_n.iloc[:, 1]], axis=1).plot()

# tau = calibrate(pd_data_n.iloc[:, 0], mid_, ts, np.arange(10,100, 1))
