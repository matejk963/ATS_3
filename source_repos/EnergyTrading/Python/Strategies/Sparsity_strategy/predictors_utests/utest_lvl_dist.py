# -*- coding: utf-8 -*-
"""
Created on Thu Nov  7 13:18:23 2024

@author: scasny
"""

from datetime import datetime, timedelta
from Utilities.mock_functions import Mock
import json
import math


from Strategies.Sparse_momentum.ob_attributes import TR_attributes
import pandas as pd
import numpy as np


tr_class = TR_attributes(feature_list=['scaled_sparsity'])

def predictor_feature_lvl_dist(variables, trade_dict):

    def push(x, value):
        if value > x['max_value']: x['max_value'] = value
        if value < x['min_value']: x['min_value'] = value

        value = round(value, 1)
        if len(x['buffer']) < x['buff_len']:
            x['buffer'].append(value)
        else:
            x['buffer'].pop(0)
            x['buffer'].append(value)

    def get_bounds(x, bound: str):
        allowed_bounds = {'close', 'far'}
        if bound not in allowed_bounds:
            # Default to 'far' if the bound is invalid
            bound = 'far'

        if bound == 'far':
            # Use x['min_value'] and x['max_value'] directly or fallback if missing
            min_value = x.get('min_value', np.nan)
            max_value = x.get('max_value', np.nan)
            return min_value, max_value

        # Handle 'close' bound
        arr = np.unique(np.round(x['buffer'], 1))
        low_bound = np.min(arr) if len(arr) > 0 else np.nan
        up_bound = np.max(arr) if len(arr) > 0 else np.nan

        # Check if buffer length is sufficient
        if len(x.get('buffer', [])) < x.get('buff_len', 0):
            return np.nan, np.nan

        return low_bound, up_bound

    def map_to_unit_interval(number, lower_bound, upper_bound):
        return max(min((number - lower_bound) / ((upper_bound - lower_bound) + 0.001), 1.0), 0.0)

    trade = trade_dict['price']
    push(variables, trade)
    close_low, close_up = get_bounds(variables, 'close')
    far_low, far_up = get_bounds(variables, 'far')
    close_level = map_to_unit_interval(trade, close_low, close_up)
    far_level = map_to_unit_interval(trade, far_low, far_up)

    return close_level, far_level

dt_moments = Mock.mock_datetime(timedelta(days=1))
trades = Mock.mock_trade_prices(dt_moments, 70)
df_trades = pd.DataFrame(trades, columns=['timestamp', 'price'])
org_lvl = tr_class.feature_lvl_dist(df_trades, "")

variables = {
    'buff_len': 30,
    'buffer': [],
    'max_value': 0,
    'min_value': 9999
}

prod_lvl_dict = {
    'prod_close_level': [],
    'prod_far_level': []
}
for trade in trades[:, 1]:
    close, far = predictor_feature_lvl_dist(variables, {'price': trade})
    prod_lvl_dict['prod_close_level'].append(close)
    prod_lvl_dict['prod_far_level'].append(far)


aa = pd.DataFrame({**org_lvl, **prod_lvl_dict})