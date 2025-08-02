# -*- coding: utf-8 -*-
"""
Created on Tue Nov 28 15:52:26 2023

@author: Marek
"""

import numpy as np
import pandas as pd


def clean_data(variable_dict, bid_clmn, ask_clmn, mid_clmn, ba_clmn, factor=7):
    bid_list = [x if x > 0 else np.nan for x in variable_dict[bid_clmn]]
    ask_list = [x if x > 0 else np.nan for x in variable_dict[ask_clmn]]
    bid_series = pd.Series(bid_list)
    ask_series = pd.Series(ask_list)
    ba_series = ask_series - bid_series
    idx_nan = []
    # ba stats
    avg_s = ba_series.mean()
    std_s = ba_series.std()
    # Diff
    dbid_series = (bid_series).diff()
    dask_series = (ask_series).diff()
    # Bids
    stop_bool = False
    avg_o = dbid_series.mean()
    std_o = dbid_series.std()
    while not stop_bool:
        ba_series = ask_series - bid_series
        dbid_series = (bid_series).diff()
        idx = [i for i, (x, y) in enumerate(zip(dbid_series, ba_series))
               if abs(x - avg_o) > std_o * factor and abs(y - avg_s) > std_s * factor]
        if not idx:
            stop_bool = True
        else:
            bid_series.iloc[idx[0]] = np.nan
            idx_nan.append(idx[0])
        bid_series.fillna(method='ffill', inplace=True)
    
    # Asks
    stop_bool = False
    avg_o = dask_series.mean()
    std_o = dask_series.std()
    while not stop_bool:
        dask_series = (ask_series).diff()
        ba_series = ask_series - bid_series
        #avg = dask_series.mean()
        #std = dask_series.std()
        idx = [i for i, (x, y) in enumerate(zip(dask_series, ba_series))
               if abs(x - avg_o) > std_o * factor and abs(y - avg_s) > std_s * factor]
        if not idx:
            stop_bool = True
        else:
            ask_series.iloc[idx[0]] = np.nan
            idx_nan.append(idx[0])
        ask_series.fillna(method='ffill', inplace=True)
    # Remove negative ba spread
    stop_bool = False
    while not stop_bool:
        dbid_series = (bid_series).diff()
        dask_series = (ask_series).diff()
        ba_series = ask_series - bid_series
        avg_s = ba_series.mean()
        std_s = ba_series.std()
        idx = [i for i, y in enumerate(ba_series)
               if abs(y - avg_s) > std_s and y < 0]
        if not idx:
            stop_bool = True
        else:
            if abs(dbid_series[idx[0]]) > abs(dask_series[idx[0]]):
                bid_series.iloc[idx[0]] = np.nan
                idx_nan.append(idx[0])
                bid_series.fillna(method='ffill', inplace=True)
            else:
                ask_series.iloc[idx[0]] = np.nan
                idx_nan.append(idx[0])
                ask_series.fillna(method='ffill', inplace=True)
    # Convert back to lists & add nans
    bid_list = [np.nan if i in idx_nan else x for i, x in enumerate(bid_series.tolist())]
    ask_list = [np.nan if i in idx_nan else x for i, x in enumerate(ask_series.tolist())]
    mid_list = [.5 * (a + b) for a, b in zip(ask_list, bid_list)]
    ba_list = [a - b for a, b in zip(ask_list, bid_list)]
    variable_dict[bid_clmn] = bid_list
    variable_dict[ask_clmn] = ask_list
    variable_dict[mid_clmn] = mid_list
    variable_dict[ba_clmn] = ba_list
    return variable_dict