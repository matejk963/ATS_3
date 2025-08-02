# -*- coding: utf-8 -*-
"""
Created on Tue Jul 11 14:11:32 2023

@author: krajcovic
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
from time import sleep
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import BDay
import re
import os

from Utilities.date_functions import start_date

#import refinitiv.dataplatform.eikon as ek
#ek.set_app_key('ce071eef39644b8584220361198bceb2cb24790d')

from refinitiv import data as rd

class EikonFut:
    def __init__(self, params_dict, reference_date = dt.datetime.today(), cont=False):
        
        self._params_dict = params_dict
        self._reference_date = reference_date
        self._cont = cont
        
    def udpate_params_dict(self, new_params_dict):
        self._params_dict = new_params_dict
    
    @property
    def market(self):
        return self._params_dict['market_list']
    
    def update_market_list(self, new_market_list):
        assert len(new_market_list) == len(self.product_list)
        self._params_dict['market_list'] = new_market_list
    
    @property
    def product_list(self):
        return self._params_dict['product_list']
    
    def update_product_list(self, new_product_list):
        assert len(new_product_list) == len(self.product_list)
        self._params_dict['product_list'] = new_product_list
        
    @property
    def delivery_list(self):
        return self._params_dict['delivery_list']
    
    def update_delivery_list(self, new_delivery_list):
        assert len(new_delivery_list) == len(self.product_list)
        self._params_dict['delivery_list'] = new_delivery_list
        
    @property
    def year_list(self):
        return self._params_dict['year_list']
    
    def update_year_list(self, new_year_list):
        assert len(new_year_list) == len(self.product_list)
        self._params_dict['year_list'] = new_year_list
    
    @property
    def reference_date(self):
        return self._reference_date
    
    @property
    def cont(self):
        return self._cont
    
    #dict for market code for ric creation
    @staticmethod
    def fwd_mkt_code(market):
        comm_dict = {}
        comm_dict['de'] = 'de'
        comm_dict['fr'] = 'f7'
        comm_dict['cz'] = 'fx'
        comm_dict['sk'] = 'fy'
        comm_dict['hu'] = 'f9'
        comm_dict['it'] = 'fd'
        comm_dict['nord'] = 'fb'
        comm_dict['be'] = 'q1'
        comm_dict['nl'] = 'q0'
        comm_dict['deat'] = 'f1'
        comm_dict['es'] = 'fe'
        comm_dict['ro'] = 'fh'
        comm_dict['bg'] = 'fh'
        comm_dict['at'] = 'at'
        comm_dict['si'] = 'fv'
        comm_dict['gas'] = 'tfm'
        comm_dict['gas_da'] = ['ttfda']
        comm_dict['coal'] = 'atw'
        comm_dict['eua'] = 'cfi2z'
        comm_dict['dk'] = 'eno'
        comm_dict['dkw'] = 'lcph'
        comm_dict['dke'] = 'larh'
        return comm_dict[market].upper()

    #futures months code dictionary
    @staticmethod
    def start_code(month_num):
        ten_dict = {}
        ten_dict[1] = 'f'
        ten_dict[2] = 'g'
        ten_dict[3] = 'h'
        ten_dict[4] = 'j'
        ten_dict[5] = 'k'
        ten_dict[6] = 'm'
        ten_dict[7] = 'n'
        ten_dict[8] = 'q'
        ten_dict[9] = 'u'
        ten_dict[10] = 'v'
        ten_dict[11] = 'x'
        ten_dict[12] = 'z'
        return ten_dict[month_num].upper()
    
    @staticmethod
    def from_code_to_month_number(month_code):
        ten_dict = {
            'f': 1,
            'g': 2,
            'h': 3,
            'j': 4,
            'k': 5,
            'm': 6,
            'n': 7,
            'q': 8,
            'u': 9,
            'v': 10,
            'x': 11,
            'z': 12
        }
        return ten_dict[month_code.lower()]
    
    @staticmethod
    def del_code(delivery):
        del_dict = {}
        del_dict['base'] = 'B'
        del_dict['peak'] = 'P'
        return del_dict[delivery].upper()
    
    
    def get_delimiter(self):
        return [re.findall(r'[^a-zA-Z0-9]', a)[0]
                          for a in self.product_list]
    
    @staticmethod
    def rel_abs_list(delimiter_list):
        
        return ['rel' if a == '_' else 'abs' for a in delimiter_list]

    @staticmethod
    def get_first_day_of_period(year, period):
        """
        Returns the first day of the specified period for a given year.
        
        :param year: The year as an integer.
        :param period: The period in the format 'M.x', 'Q.x', 'W.x', or 'Y.x'.
        :return: A tuple in the format (year, month, day).
        """
        if period.startswith('M.'):
            month = int(period.split('.')[1])
            return dt.datetime(year, month, 1)
        elif period.startswith('Q.'):
            quarter = int(period.split('.')[1])
            month = (quarter - 1) * 3 + 1
            return dt.datetime(year, month, 1)
        elif period.upper().startswith('W.') or period.startswith('WK'):
            week = int(period.split('.')[1])
            first_day_of_year = dt.datetime(year, 1, 1)
            days_to_add = (week - 1) * 7
            first_day_of_week = first_day_of_year + dt.timedelta(days=days_to_add - first_day_of_year.isoweekday() + 1)
            return first_day_of_week
        elif period.startswith('Y.'):
            return dt.datetime(year, 1, 1)
        else:
            raise ValueError("Invalid period format. Please use 'M.x', 'Q.x', 'W.x', or 'Y.x'.")
    
    def market_code_list(self):
        return [self.fwd_mkt_code('deat') if market in ['de', 'DE'] and
                self.get_first_day_of_period(year, period) < dt.datetime(2018,10,1)  else
                self.fwd_mkt_code(market) for a, year, period, market in 
                zip(range(len(self.product_list)), self.year_list, self.product_list, self.market)]
        # return [self.fwd_mkt_code(self.market)
        #                for a in range(len(self.product_list))]
    
    
    def period_list(self, delimiter_list):
        return [a.split(b)[0]
                       for a,b in zip(self.product_list,
                                    delimiter_list)]    
    
    
    def get_tenor(self, delimiter_list):
        return [int(a.split(b)[1])
                       for a,b in zip(self.product_list,
                                    delimiter_list)]
    
    
    def transform_tenor(self, tenor_list, rel_abs_list, period_list, year_list):
        # market = self.market
        today = self.reference_date
        return [self.week_to_month(d, a)+1 if( (b == 'abs') and (c.lower() in ['w', 'wk'])
                                            and (market in ['gas', 'coal', 'eua'])) else
                a if b == 'abs' and c in ['M', 'm'] else 
                a*3 if b == 'abs' and c in ['Q','q'] and market in ['gas', 'coal'] else
                a*3-2 if b == 'abs' and c in ['Q','q'] and market not in ['eua', 'gas', 'coal'] else
                12 if b == 'abs' and market in ['eua', 'gas', 'coal'] else
                1 if b == 'abs' and c in ['Y','y'] else
                (today+relativedelta(months=a)).month if b == 'rel' and c in ['M', 'm'] else
                (dt.datetime(today.year,
                            ((today.month-1)//3+1)*3,
                            1) + relativedelta(months=a*3)).month 
                if b == 'rel' and c in ['Q','q'] and market in ['gas','coal'] else
                (dt.datetime(today.year,
                            ((today.month-1)//3+1)*3-2,
                            1) + relativedelta(months=a*3)).month
                if b == 'rel' and c in ['Q','q'] and market not in ['eua','gas','coal'] else
                1 if b == 'rel' and c in ['Y', 'y'] and market not in ['eua', 'gas', 'coal'] else
                12 if b == 'rel' and c in ['Y', 'y'] and market in ['eua', 'gas', 'coal'] else None
                
                for a, b, c, d, market in zip(tenor_list, rel_abs_list,
                                              period_list, year_list,
                                              self.market)]
    
     
    
    def year_list_update(self, tenor_list,
                          rel_abs_list,
                          period_list):
        today = self.reference_date
        # return [a if b == 'abs' else
        #         today.year if b == 'rel' and (c+today.month)<=12 and d in ['M', 'm'] else
        #         today.year if b == 'rel' and (c*3+today.month)<=12 and d in ['Q', 'q'] else
        #         today.year + c if b == 'rel' and d in ['Y', 'y'] else
        
        return [a if b == 'abs' else
                 today.year + (c+today.month-1)//12 if b == 'rel' and d in ['M', 'm'] else
                 today.year + (c*3+today.month-1)//12 if b == 'rel' and d in ['Q' ,'q'] else
                 today.year + c if b =='rel' and d in ['Y', 'y'] else a
                
                
                for a, b, c, d in zip(self.year_list,
                                      rel_abs_list,
                                      tenor_list,
                                      period_list)]
    
    def year_str_list(self, updated_year_list, updated_tenor_list, period_list):
        # market = self.market
        today = self.reference_date
        # today = dt.datetime.today()
        # Update to 3rd day because of the gas
        return [str(a)[-1] if dt.datetime(a,b,3)>today and (market in ['gas', 'coal'])
                    and (c in ['m', 'M']) else
                str(a)[-1] if dt.datetime(a,max([b-2,1]),1)>today and (market in ['gas'])
                            and (c in ['q', 'Q']) and (b-2)>0 else
                str(a)[-1] if dt.datetime(a,b,1)>today and (market in [ 'coal'])
                            and (c in ['q', 'Q']) else
                str(a)[-1] if (dt.datetime(a,b,1)+
                               relativedelta(months=1)-
                               dt.timedelta(days=1))>today and market not in ['eua', 'gas']
                                and c in ['M', 'm']else
                str(a)[-1]  if ((dt.datetime(a,b,1))>today) and (market not in ['eua', 'gas', 'coal'])
                and (c not in ['M', 'm']) else
                str(a)[-1] if dt.datetime(a,12,1)>today and market in ['eua'] else
                str(a)[-1] + '^' + str(a)[-2]
                for a, b, c, market in zip(updated_year_list,
                                updated_tenor_list,
                                period_list,
                                self.market)]
    
    @staticmethod
    def week_to_month(year, week_number):
        # Calculate the start date of the given week number
        start_of_week = dt.datetime.strptime(f'{year} {week_number} 1', '%Y %W %w')
        
        # Dictionary to count occurrences of months
        month_count = {}
        
        # Iterate over each day of the week
        for i in range(7):
            day = start_of_week + dt.timedelta(days=i)
            month = day.month
            if month in month_count:
                month_count[month] += 1
            else:
                month_count[month] = 1
    
        # Find the month with the maximum count of days
        max_month = max(month_count, key=month_count.get)
        return max_month
    
    def get_tenor_code(self,period_list, updated_tenor_list, year_list):
        
        results = []
        for a, b, c, market in zip(updated_tenor_list, period_list, year_list, self.market):
            b_lower = b.lower()
            # results.append(self.start_code(a))
            if b_lower not in ['w']:
                # Call start_code normally
                results.append(self.start_code(a))
            
            elif b_lower in ['w'] and market in ['coal', 'gas', 'eua']:
                # Call start_code with week_to_month
                month = self.week_to_month(c, a)
                results.append(self.start_code(month))
            else:
                # Raise an error if conditions are not met
                raise ValueError('Trying to fetch spot for power futures')
        return results
    

    def update_period_list(self, period_list):
        return[a if a.lower() not in ['w', 'wk', 'wknd', 'd'] else
               'M' if a.lower() in ['w', 'wk', 'wknd', 'd'] else None
               for a in period_list]

        
    
    # @staticmethod
    # def get_rel_period_number()
    
    def fwd_code_creator(self):
        # market = self.market
        if 'coal' in self.market:
            print('246')
        delimiter_list = self.get_delimiter()
        
        market_code = self.market_code_list()
        
        period_list = self.period_list(delimiter_list)
        
        tenor_list = self.get_tenor(delimiter_list)
        
        rel_abs_list = self.rel_abs_list(delimiter_list)
        
        updated_year_list = self.year_list_update(tenor_list,
                                             rel_abs_list,
                                             period_list)
        
        updated_tenor_list = self.transform_tenor(tenor_list, rel_abs_list,
                                                  period_list, updated_year_list)
        
        tenor_code_list = self.get_tenor_code(period_list,
                                              updated_tenor_list,
                                              updated_year_list)
        
        
        updated_period_list = self.update_period_list(period_list)
        
        year_str_list = self.year_str_list(updated_year_list,
                                           updated_tenor_list,
                                           updated_period_list)
        
        updated_delivery_list = ['B' if a == 'base' else
                                 'P' if a == 'peak' else None
                                 for a in self.delivery_list]
        
        
        return [['ENOAF' + b + 'L' + c + d + e,'ENO' + c + b + a + d + e]
                if 'dk' in market else 
            a + b + c + d + e if market not in ['eua', 'coal'] else
         a + c + d + e if market in ['coal'] else
         'CFI2Z' + e
         for a, b, c, d, e, market in zip(market_code,
                                  updated_delivery_list,
                                  updated_period_list,
                                  tenor_code_list,
                                  year_str_list,
                                  self.market)]
    
    def fwd_cont_code_creator(self):
        
        return [self.fwd_mkt_code(market).upper() + self.del_code(b) + a.split('_')[0].upper()
                + 'c' + a.split('_')[1] if market not in ['coal', 'eua'] else
                self.fwd_mkt_code(market).upper() + a.split('_')[0].upper()
                + 'c' + a.split('_')[1] if market in ['coal'] else
                self.fwd_mkt_code(market).upper()
                + 'c' + a.split('_')[1]
                for a, b, market in zip(self.product_list, self.delivery_list, self.market)]
        
       
    @staticmethod
    def process_df(df, instructions):
        unique_level0_vals = df.columns.levels[0]
        # Ensure the length of instructions matches the number of unique level 0 values
        if len(instructions) != len(unique_level0_vals):
            raise ValueError("Length of instructions does not match the number of unique categories in level 0 of the DataFrame columns.")
        
        # Initialize a list to keep track of columns to keep
        cols_to_keep = []
    
        # Iterate over each unique level 0 value and its corresponding instruction
        for col_val, instruction in zip(unique_level0_vals, instructions):
            if instruction == 'all':
                # Keep all columns under this level 0 value
                cols_to_keep.extend([(col_val, sub_col) for sub_col in df[col_val].columns])
            elif instruction == 'settle':
                # Keep only 'SETTLE' column under this level 0 value, if it exists
                if 'SETTLE' in df[col_val].columns:
                    cols_to_keep.append((col_val, 'SETTLE'))
            elif instruction == 'close':
                # Keep only 'TRDPRC_1' column under this level 0 value, if it exists
                if 'TRDPRC_1' in df[col_val].columns:
                    cols_to_keep.append((col_val, 'TRDPRC_1'))
    
        # Select the columns to keep from the DataFrame
        processed_df = df.loc[:, cols_to_keep]
        return processed_df

    def _fut_data_fetch(self,ric_list,
                           sD, eD,
                           data_to_keep, fillna=True):
        # market = self.market
        rd.open_session()   
        # try:
        temp = rd.get_history(universe=ric_list,
                            fields=['TRDPRC_1', 'SETTLE',
                                    'OPEN_PRC', 'HIGH_1', 'LOW_1'],

                            interval='1D',
                            start=sD.\
                                strftime('%Y%m%d'),
                            end=eD.\
                                strftime('%Y%m%d'),
                            parameters={'Curn': 'EUR'}).astype(float)  
        # except:
        #     print('432')
        if 'ATWMc1' in ric_list:
            print('480 stop')
        
        if len(np.unique(ric_list)) == 1:
            temp.columns = pd.MultiIndex.from_product([[ric_list[0]], temp.columns])
        temp = self.process_df(temp, data_to_keep)
        if isinstance(temp.columns, pd.MultiIndex):
            temp_med = temp.groupby(axis=1, level=0).median()
            temp_mean = temp.groupby(axis=1, level=0).mean()
            temp = temp_med.add(temp_mean).divide(2)
        else:
            temp_med = temp.median(axis=1)
            temp_mean = temp.mean(axis=1)
            temp = temp_med.add(temp_mean).divide(2)
        rd.close_session()
        temp = pd.DataFrame(temp).copy()
        gas_columns = [True if 'TFM' in a else False for a in temp.columns]
        gas_values_list = [None for a in gas_columns]
        current_date = pd.to_datetime(dt.date.today())
        if not temp.index.max() == pd.to_datetime(dt.date.today()):
            file_path = r'T:\LiveScreen_v01.xlsx'  # Replace with the path to your file
            last_modified_time = os.path.getmtime(file_path)
            modification_time = pd.to_datetime(dt.date.fromtimestamp(last_modified_time))
            if eD == pd.to_datetime(dt.date.today()):
                if modification_time != pd.to_datetime(dt.date.today()):
                    raise Exception('File not updated')
                else:
                    gas_act = pd.read_excel(file_path, sheet_name='gas_main')
                    gas_act.columns = ['product', 'tenor', 'bid', 'offer']
                    gas_act = gas_act.iloc[1:].copy()
                    gas_act['product'] = gas_act['product'].ffill()
                    gas_act['mid'] = gas_act[['bid', 'offer']].mean(axis=1)
                    for col in temp.columns[gas_columns]:
                        if col:                        
                            long_product, fwd_tenor = self.get_prod_tenor_from_ric(col, current_date)
                            if fwd_tenor == 0:
                                continue
                            gas_select = gas_act.loc[((gas_act['product']==long_product)&
                                                       (gas_act['tenor']==fwd_tenor))].copy()
                            if not gas_select.empty:
                                gas_values_list[temp.columns.get_loc(col)] = gas_select['mid'].iloc[0]
                            
                    gas_values_df = pd.DataFrame(gas_values_list,columns=[current_date], index=temp.columns).T
                    
                    temp = pd.concat([temp, gas_values_df])
                    temp = temp.ffill()
                        
                        
        
        temp = temp[ric_list].copy()
        temp.columns=[a+'_'+b + '_' + str(c) + '_' + d
                      for a, b, c, d in zip(self.market, self.product_list,
                                            self.year_list, self.delivery_list)]
                
        temp.index = pd.to_datetime(temp.index)
        if fillna:
            temp = temp.ffill()
        return temp
    
    
    def get_prod_tenor_from_ric(self, ric, current_date):
        def calculate_periods_forward(product_type, period, year):
            today = dt.datetime.today()
            current_year = today.year
            current_month = today.month
        
            if product_type == 'M':
                target_month = period
                target_year = year
                months_forward = (target_year - current_year) * 12 + (target_month - current_month)
                return 'Months', months_forward
        
            elif product_type == 'Q':
                target_quarter = (period - 1) // 3 + 1
                target_year = year
                current_quarter = (current_month - 1) // 3 + 1
                quarters_forward = (target_year - current_year) * 4 + (target_quarter - current_quarter)
                return 'Quarters', quarters_forward
        
            elif product_type == 'Y':
                target_year = year
                years_forward = target_year - current_year
                return 'Years', years_forward + 1
        
            else:
                raise ValueError("Invalid product type. Use 'M' for month, 'Q' for quarter, or 'Y' for year.")
        def round_down_to_nearest_base(number, base):
            return (number // base) * base
        today_year = current_date.year
        year_base = round_down_to_nearest_base(today_year, 10)
        
        ric1 = ric.replace('TFMB','')
        prod_code = ric1[0]
        tenor_code = ric1[1]
        year_code = int(ric1[2])
        year = year_base + year_code
        
        tenor_fix = self.from_code_to_month_number(tenor_code)
        long_product, fwd_tenor = calculate_periods_forward(prod_code, tenor_fix, year)
        return long_product, fwd_tenor
    
    def fwd_df(self, sD, eD,
               data_to_keep=None,
               fillna=True):
        # if data_to_keep is None:
        #     data_to_keep=['all']*len(self.product_list)
        if self.cont:
            ric_list = self.fwd_cont_code_creator()
        else:        
            ric_list = self.fwd_code_creator()
        if data_to_keep is None:
            data_to_keep=['all']*len(np.unique(ric_list))
            
        if ((self.market == ['coal', 'coal']) and (self.product_list == ['M_0', 'M_1'])):
            ric_list = ['TRAPI2FVMc0', ric_list[1]]
            
        # unique_elements = {}
        # corresponding_elements = {}
        
        # # Iterate over both lists simultaneously
        # for elem1, elem2 in zip(ric_list,
        #                         data_to_keep):
        #     # If the element from list1 hasn't been added to the dictionary, add it
        #     if elem1 not in unique_elements:
        #         unique_elements[elem1] = True  # The value `True` is arbitrary here; we just need to mark the key as seen
        #         corresponding_elements[elem1] = elem2
        
        # # Now, extract the results back into list form if necessary
        # ric_list = list(unique_elements.keys())
        # data_to_keep = list(corresponding_elements.values())
        
        return self._fut_data_fetch(ric_list,
                               sD, eD, data_to_keep,
                               fillna=fillna)
        
    
    def fwd_cont_df(self, sD, eD, data_to_keep=None):
        ric_list = self.fwd_cont_code_creator()
        
        return self._fut_data_fetch(ric_list,
                               sD, eD, data_to_keep=None)
    
    def fwd_rel_df_count(self, count):
        
        ric_list = self.fwd_code_creator()
        
        pass
    
    def gas_da_df(self, sD, eD):
        rd.open_session()
        da_df = rd.get_history(['TTFDA', 'TTFWE'],
                               start=sD.strftime('%Y-%m-%d'),
                               end=eD.strftime('%Y-%m-%d'),fields=['VWAP']).astype(float)
        da_df.index = pd.to_datetime(da_df.reset_index()['Date'])
        
        df = da_df.copy()
        # Transform 'TTFDA' Prices
        ttfda_prices = {}
        for date, price in df['TTFDA'].dropna().items():
            target_date = date + pd.DateOffset(days=1)
            if target_date.weekday() == 5:  # If next day is Saturday
                target_date += pd.DateOffset(days=2)  # Move to Monday
            ttfda_prices[target_date] = price
        
        # Transform 'TTFWE' Prices
        ttfwe_prices = {}
        for date, price in df['TTFWE'].dropna().items():
            saturday = date + pd.DateOffset(days=(5 - date.weekday()))
            sunday = saturday + pd.DateOffset(days=1)
            ttfwe_prices[saturday] = price
            ttfwe_prices[sunday] = price
        
        # Combine and Sort the Prices
        all_prices = {**ttfda_prices, **ttfwe_prices}
        sorted_prices = dict(sorted(all_prices.items()))
        
        # Convert to Series
        out_df = pd.DataFrame(pd.Series(sorted_prices),columns=['ttf_da'])
        return out_df
    
    def gas_da_df_the(self, sD, eD):
        rd.open_session()
        da_df = rd.get_history(['PNCGDA', 'PNCGWE'],
                               start=sD.strftime('%Y-%m-%d'),
                               end=eD.strftime('%Y-%m-%d'),fields=['VWAP']).astype(float)
        da_df.index = pd.to_datetime(da_df.reset_index()['Date'])
        
        df = da_df.copy()
        # Transform 'TTFDA' Prices
        ttfda_prices = {}
        for date, price in df['PNCGDA'].dropna().items():
            target_date = date + pd.DateOffset(days=1)
            if target_date.weekday() == 5:  # If next day is Saturday
                target_date += pd.DateOffset(days=2)  # Move to Monday
            ttfda_prices[target_date] = price
        
        # Transform 'TTFWE' Prices
        ttfwe_prices = {}
        for date, price in df['PNCGWE'].dropna().items():
            saturday = date + pd.DateOffset(days=(5 - date.weekday()))
            sunday = saturday + pd.DateOffset(days=1)
            ttfwe_prices[saturday] = price
            ttfwe_prices[sunday] = price
        
        # Combine and Sort the Prices
        all_prices = {**ttfda_prices, **ttfwe_prices}
        sorted_prices = dict(sorted(all_prices.items()))
        
        # Convert to Series
        out_df = pd.DataFrame(pd.Series(sorted_prices),columns=['the_da'])
        return out_df
    
    def get_gas_matrix(self, fsD, feD, sD=None, eD=None, years_history=3):
        
        if eD is None:
            eD = pd.to_datetime(dt.datetime.today())
        if sD is None:
            sD = eD - dt.timedelta(days=365*years_history)
            
        first_contract_date = sD 
        last_contract_date = eD + relativedelta(months=16)
        
        months_range = pd.date_range(start=first_contract_date,
                                     end=last_contract_date,
                                     freq='MS')
        params_dict = {}
        

        params_dict['product_list'] = ['M.'+str(a.month) for a in months_range]
        params_dict['market_list'] = ['gas'] * len(params_dict['product_list'])
        params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
        params_dict['year_list'] = [a.year for a in months_range]
        self.udpate_params_dict(params_dict)
        
        df = self.fwd_df(sD, eD,fillna=False)
        df.columns = [dt.datetime(int(a.split('_')[2]),
                                   int(a.split('_')[1].split('.')[1]),1) for a in df.columns]
        columns_to_select = [a for a in df.columns
                             if ((a>=fsD)&(a<=feD))]
        df = df[columns_to_select]
        return df
        
        
    
   
if __name__ == '__main__':
    pass
    
    params_dict = {}
    

    params_dict['product_list'] = ['M.5']
    # params_dict['product_list'] = params_dict['product_list'] * 3
    params_dict['market_list'] = ['de'] * len(params_dict['product_list'])
    params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
    # base_len = len(params_dict['product_list'])//3
    # nested_year_list = [[a for b in range(base_len)] for a in range(2022,2025)]
    # params_dict['year_list'] = [a for b in nested_year_list for a in b]
    params_dict['year_list'] = [2024]
    
    
    test_o = EikonFut(params_dict)
    # start_date = dt.datetime(2021,10,1)
    sD = dt.datetime(2024,2,1)
    eD = dt.datetime(2024,4,20)
    test_o.fwd_df(sD, eD)
    
    
    # fsD = dt.datetime(2024,1,1)
    # feD = dt.datetime(2024,12,1)
    
    # test_df = test_o.get_gas_matrix(fsD, feD,
    #                                 sD=dt.datetime(2024,4,25),
    #                                 eD=dt.datetime(2024,4,30))
    
    
    # the = test_o.gas_da_df_the(sD, eD)
    # ttf = test_o.gas_da_df(sD, eD)
    
    # df = pd.concat([ttf, the],axis=1,join='inner')
    # df['spread'] = df['the_da']-df['ttf_da']
    
    # tenor_list = test_o.get_tenor(self.product_list, ['.'])

    # test_o.transform_tenor(tenor_list, ['rel'], ['Y_1'])    
    # print(test_o.fwd_code_creator(self.product_list, self.delivery_list, self.year_list))
    # test_df = test_o.fwd_df(sD, eD,
    #                         ['all', 'settle', 'settle'])
    
# self.product_list = ['M_1', 'M.9', 'Q_2', 'Y_1', 'Q.4']
# # self.product_list = ['Y_1', 'Y_2', 'Y_3', 'Y.1', 'Y.1']
# self.delivery_list = ['base', 'base', 'base', 'base', 'base']
# self.year_list = [None, 2023, None, 2021, 2022]
    
    
# # test_code = test_o.get_delimiter(self.product_list)
# test_code = test_o.fwd_code_creator(self.product_list,
#                                     self.delivery_list,
#                                     self.year_list)
# test_df = test_o.fwd_df(sD, eD,
#                         self.product_list,
#                         self.delivery_list,
#                         self.year_list)

    
    
    
            
    
    
