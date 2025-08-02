# -*- coding: utf-8 -*-
"""
Created on Mon Jun  3 10:05:40 2024

@author: scasny
"""
import pandas as pd
import scipy.stats as stats
import numpy as np

class level_distance():
    def __init__(self, buff_len):
        self.buff_len = buff_len
        self.buffer = []
        self.max_value = 0
        self.min_value = 9999
        
    def push(self, value):
        if value > self.max_value: self.max_value = value
        if value < self.min_value: self.min_value = value
        
        value = round(value,1)
        if len(self.buffer) < self.buff_len:
            self.buffer.append(value)
        else:
            self.buffer.pop(0)
            self.buffer.append(value)
    
    def get_bounds(self, bound:str, value):
        allowed_bounds = {'close', 'far'}
        if bound not in allowed_bounds:
            raise ValueError(f"Value must be one of {allowed_bounds}, but got '{bound}'")
        if bound == 'far':
            return self.min_value, self.max_value
        arr = pd.Series(self.buffer).apply(lambda x: round(x,1)).unique()
        try:
            low_bound = arr.min()
            up_bound = arr.max()
            if len(self.buffer) < self.buff_len:
                raise ValueError("buffer < n")
            return low_bound, up_bound
        except:
            return np.nan, np.nan
        
r = stats.norm.rvs(0, .1, size=1000)

r[0]=50.0

df = pd.DataFrame({'returns':pd.Series(r).cumsum()}, index=range(len(r)))

memory_class = level_mem(50)

def map_to_unit_interval(number, lower_bound=95, upper_bound=100):
    return max(min((number - lower_bound) / ((upper_bound - lower_bound)+0.001),1.0),0.0)

for i, x in enumerate(df.to_dict(orient='records')):
    trade = x['returns']
    memory_class.push(trade)
    close_low, close_up = memory_class.get_bounds('close', trade)
    far_low, far_up = memory_class.get_bounds('far', trade)
    df.loc[i, 'close_level'] = map_to_unit_interval(trade, close_low, close_up)
    df.loc[i, 'far_level'] = map_to_unit_interval(trade, far_low, far_up)
