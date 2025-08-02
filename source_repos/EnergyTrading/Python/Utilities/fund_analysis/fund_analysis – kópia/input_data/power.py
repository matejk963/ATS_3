"""
    Prices of fuels, power and euas
    
    Need to handle both fut curves and day ahead data
        for train and analysis
        
    Common methods will be:
        creating futures curve
        creating spot day ahead data
"""


import pandas as pd
import numpy as np
import datetime as dt
from copy import deepcopy
from fund_analysis.utils import ENUMS as enums
from .input_data import InputData as input_data
from Utilities.date_functions import start_date, end_date

class Power(input_data):

    da_data = {}
    da_data_history = {}
    
    def __init__(self, params_dict, power_markets=[]):
        super().__init__(params_dict=params_dict)
        self._power_markets = power_markets
        if len(self._power_markets)<1:
            self._power_markets = self.unique_markets
        
    @property
    def power_markets(self):
        return self._power_markets
        
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
        
    def reset_data(self):
        self.da_data = {}
        
                
                    
    def get_da_data(self):
        for market in self.power_markets:
            if not market in self.da_data_history:
                spot_table = market
                self.da_data_history[market] = self.data_loader.get_data_db(schema_name='spot',
                                                        table_name=spot_table,
                                                        datetime_col='datetime')
            da_temp = self.da_data_history[market].copy()
            da_temp.set_index('datetime',inplace=True)
            da_temp.rename(columns={'price': market}, inplace=True)
            da_temp = da_temp.sort_index().loc[:(self.pivot_date+dt.timedelta(hours=23))].copy()
            last_date = da_temp.index[-1] + pd.Timedelta(days=1)

            # Step 2: Add this new timestamp to the DataFrame
            # da_temp.loc[last_date] = da_temp.iloc[-1]
            self.da_data[market] = da_temp.reset_index().drop_duplicates(keep='last') \
                .set_index('datetime').loc[~da_temp.index.duplicated(keep='last')] \
                .sort_index().resample('h').ffill().copy()
