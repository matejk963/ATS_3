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

from Utilities.date_functions import start_date

#import refinitiv.dataplatform.eikon as ek
#ek.set_app_key('ce071eef39644b8584220361198bceb2cb24790d')

from refinitiv import data as rd

class EikonFut:
    def __init__(self, market, reference_date = dt.datetime.today(), cont=False):
        
        self.__market = market
        self._reference_date = reference_date
        self._cont = cont
        
    @property
    def market(self):
        return self.__market
    
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
    def del_code(delivery):
        del_dict = {}
        del_dict['base'] = 'B'
        del_dict['peak'] = 'P'
        return del_dict[delivery].upper()
    
    @staticmethod
    def get_delimiter(product_list):
        return [re.findall(r'[^a-zA-Z0-9]', a)[0]
                          for a in product_list]
    
    @staticmethod
    def rel_abs_list(delimiter_list):
        
        return ['rel' if a == '_' else 'abs' for a in delimiter_list]
    @staticmethod
    def get_first_day_of_period(year, period):
        """
        Returns the first day of the specified period for a given year.
        
        :param year: The year as an integer.
        :param period: The period in the format 'M.x', 'Q.x', or 'Y.x'.
        :return: A tuple in the format (year, month, day).
        """
        if period.startswith('M.'):
            month = int(period.split('.')[1])
            return dt.datetime(year, month, 1)
        elif period.startswith('Q.'):
            quarter = int(period.split('.')[1])
            month = (quarter - 1) * 3 + 1
            return dt.datetime(year, month, 1)
        elif period.startswith('Y.'):
            return dt.datetime(year, 1, 1)
        else:
            raise ValueError("Invalid period format. Please use 'M.x', 'Q.x', or 'Y.x'.")
    
    def market_code_list(self,product_list,
                            year_list):
        return [self.fwd_mkt_code('deat') if self.market in ['de', 'DE'] and
                self.get_first_day_of_period(year, period) < dt.datetime(2018,10,1)  else
                self.fwd_mkt_code(self.market) for a, year, period in 
                zip(range(len(product_list)), year_list, product_list)]
        # return [self.fwd_mkt_code(self.market)
        #                for a in range(len(product_list))]
    
    @staticmethod
    def period_list(product_list, delimiter_list):
        return [a.split(b)[0]
                       for a,b in zip(product_list,
                                    delimiter_list)]    
    
    @staticmethod
    def get_tenor(product_list, delimiter_list):
        return [int(a.split(b)[1])
                       for a,b in zip(product_list,
                                    delimiter_list)]
    
    
    def transform_tenor(self, tenor_list, rel_abs_list, period_list):
        market = self.market
        today = self.reference_date
        return [a if b == 'abs' and c in ['M', 'm'] else 
                a*3 if b == 'abs' and c in ['Q','q'] and market in ['gas', 'coal'] else
                a*3-2 if b == 'abs' and c in ['Q','q'] and market not in ['eua', 'gas', 'coal'] else
                12 if b == 'abs' and market in ['eua'] else
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
                
                for a, b, c in zip(tenor_list, rel_abs_list, period_list)]
    
     
    
    def year_list_update(self, tenor_list,
                          rel_abs_list,
                          period_list, year_list):
        today = self.reference_date
        # return [a if b == 'abs' else
        #         today.year if b == 'rel' and (c+today.month)<=12 and d in ['M', 'm'] else
        #         today.year if b == 'rel' and (c*3+today.month)<=12 and d in ['Q', 'q'] else
        #         today.year + c if b == 'rel' and d in ['Y', 'y'] else
        
        return [a if b == 'abs' else
                 today.year + (c+today.month-1)//12 if b == 'rel' and d in ['M', 'm'] else
                 today.year + (c*3+today.month-1)//12 if b == 'rel' and d in ['Q' ,'q'] else
                 today.year + c if b =='rel' and d in ['Y', 'y'] else a
                
                
                for a, b, c, d in zip(year_list,
                                      rel_abs_list,
                                      tenor_list,
                                      period_list)]
    
    def year_str_list(self, updated_year_list, updated_tenor_list, period_list):
        market = self.market
        today = self.reference_date
        # today = dt.datetime.today()
        return [str(a)[-1] if dt.datetime(a,b,1)>today and market in ['gas'] else
                str(a)[-1] if (dt.datetime(a,b,1)+
                               relativedelta(months=1)-
                               dt.timedelta(days=1))>today and market not in ['eua', 'gas']
                                and c in ['M', 'm']else
                str(a)[-1]  if ((dt.datetime(a,b,1))>today) and (market not in ['eua', 'gas']) and (c not in ['M', 'm']) else
                str(a)[-1] if dt.datetime(a,12,1)>today and market in ['eua'] else
                str(a)[-1] + '^' + str(a)[-2]
                for a, b, c in zip(updated_year_list,
                                updated_tenor_list,
                                period_list)]
    
    # @staticmethod
    # def get_rel_period_number()
    
    def fwd_code_creator(self,
                         product_list,
                         delivery_list,
                         year_list):
        market = self.market
        delimiter_list = self.get_delimiter(product_list)
        
        market_code = self.market_code_list(product_list,
                                            year_list)
        
        period_list = self.period_list(product_list,
                                  delimiter_list)
        
        tenor_list = self.get_tenor(product_list,
                                    delimiter_list)
        
        rel_abs_list = self.rel_abs_list(delimiter_list)
        
        updated_tenor_list = self.transform_tenor(tenor_list, rel_abs_list, period_list)
        
        tenor_code_list = [self.start_code(a)
                           for a in updated_tenor_list]
        
        updated_year_list = self.year_list_update(tenor_list,
                                             rel_abs_list,
                                             period_list,
                                             year_list)
        
        year_str_list = self.year_str_list(updated_year_list,
                                           updated_tenor_list,
                                           period_list)
        
        updated_delivery_list = ['B' if a == 'base' else
                                 'P' if a == 'peak' else None
                                 for a in delivery_list]
        
        
        return [['ENOAF' + b + 'L' + c + d + e,'ENO' + c + b + a + d + e]
                if 'dk' in market else 
            a + b + c + d + e if market not in ['eua', 'coal'] else
         a + c + d + e if market in ['coal'] else
         'CFI2Z' + e
         for a, b, c, d, e in zip(market_code,
                                  updated_delivery_list,
                                  period_list,
                                  tenor_code_list,
                                  year_str_list)]
    
    def fwd_cont_code_creator(self,product_list,
                              delivery_list):
        if self.market not in ['coal' ,'eua']:
            return [self.fwd_mkt_code(self.market).upper() + self.del_code(b) + a.split('_')[0].upper()
                    + 'c' + a.split('_')[1] for a, b in zip(product_list,
                                                            delivery_list)]
        elif self.market in ['coal']:
            return [self.fwd_mkt_code(self.market).upper() + a.split('_')[0].upper()
                    + 'c' + a.split('_')[1] for a, b in zip(product_list,
                                                            delivery_list)]
        elif self.market in ['eua']:
            
            return [self.fwd_mkt_code(self.market).upper()
                    + 'c' + a.split('_')[1] for a, b in zip(product_list,
                                                            delivery_list)]
        
    def _fut_data_fetch(self,ric_list,
                           sD, eD, product_list):
        market = self.market
        # if market in ['gas']:
        #     rd.open_session()        
        #     temp = rd.get_history(universe=ric_list,
        #                         fields=['VWAP'],
        #                         interval='1D',
        #                         start=sD.\
        #                             strftime('%Y%m%d'),
        #                         end=eD.\
        #                             strftime('%Y%m%d')).astype(float)        
        #     rd.close_session()
        #     temp.columns = [market+'_'+a for a in product_list]
            
        if market in ['coal', 'eua', 'gas']:
            rd.open_session()        
            temp = rd.get_history(universe=ric_list,
                                fields=['TRDPRC_1', 'SETTLE',
                                        'OPEN_PRC', 'HIGH_1', 'LOW_1'],
                                interval='1D',
                                start=sD.\
                                    strftime('%Y%m%d'),
                                end=eD.\
                                    strftime('%Y%m%d')).astype(float)        
            
            if isinstance(temp.columns, pd.MultiIndex):
                temp = temp.groupby(axis=1, level=0).median()
            else:
                temp = temp.median(axis=1)
            if market in ['coal']:
                eur = rd.get_history(universe=['EUR='],
                                     fields=['MID_PRICE'],
                                     interval='1D',
                                     start=sD.\
                                         strftime('%Y%m%d'),
                                     end=eD.\
                                         strftime('%Y%m%d')).astype(float)
            
            
                temp = pd.concat([temp, eur],axis=1, join='inner')
                for col in temp.columns:
                    temp[col] = temp[col]/temp['MID_PRICE']
                temp = temp.drop(['MID_PRICE'],axis=1)
            rd.close_session()
            temp = pd.DataFrame(temp).copy()
            temp.columns=[market+'_'+a for a in product_list]
        
        else:
            
            rd.open_session()        
            temp = rd.get_history(universe=ric_list,
                                fields=['SETTLE'],
                                interval='1D',
                                start=sD.\
                                    strftime('%Y%m%d'),
                                end=eD.\
                                    strftime('%Y%m%d')).astype(float)        
            rd.close_session()
            # if isinstance(temp.columns, pd.MultiIndex):
            #     # temp = temp.groupby(axis=1, level=0).median()
            #     temp.columns = [market+'_'+a for a in product_list]
            # else:
            #     # temp = temp.median(axis=1)
            #     temp.name = [market+'_'+a for a in product_list][0]
            
            temp = pd.DataFrame(temp).copy()
            temp.columns=[market+'_'+a for a in product_list]
        
        temp.index = pd.to_datetime(temp.index)
        return temp
    
    def fwd_df(self, sD, eD, product_list,
               delivery_list,
               year_list):
        if self.cont:
            ric_list = self.fwd_cont_code_creator(product_list,
                                             delivery_list)
        else:        
            ric_list = self.fwd_code_creator(product_list,
                                             delivery_list,
                                             year_list)
        
        return self._fut_data_fetch(ric_list,
                               sD, eD, product_list)
        
    
    def fwd_cont_df(self, sD, eD, product_list,
               delivery_list,
               year_list):
        ric_list = self.fwd_cont_code_creator(product_list,
                                         delivery_list)
        
        return self._fut_data_fetch(ric_list,
                               sD, eD, product_list)
    
    def fwd_rel_df_count(self, count, product_list,
                         delivery_list,
                         year_list=None):
        if year_list is None:
            year_list = [None for a in product_list]
        if len(delivery_list)==1 and delivery_list[0]=='base':
            delivery_list = ['base' for a in product_list]
        ric_list = self.fwd_code_creator(product_list,
                                         delivery_list,
                                         year_list)
        
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
    
   
if __name__ == '__main__':
    pass
        
    test_o = EikonFut('gas')
    start_date = dt.datetime(2021,10,1)
    sD = dt.datetime(2017,12,1)
    eD = dt.datetime(2018,2,1)
    
    product_list = ['M.3']
    delivery_list = ['base']
    year_list = [2018]
    
    tenor_list = test_o.get_tenor(product_list, ['.'])

    test_o.transform_tenor(tenor_list, ['rel'], ['Y_1'])    
    # print(test_o.fwd_code_creator(product_list, delivery_list, year_list))
    test_df = test_o.fwd_df(sD, eD,
                            product_list,
                            delivery_list,
                            year_list)
    
# product_list = ['M_1', 'M.9', 'Q_2', 'Y_1', 'Q.4']
# # product_list = ['Y_1', 'Y_2', 'Y_3', 'Y.1', 'Y.1']
# delivery_list = ['base', 'base', 'base', 'base', 'base']
# year_list = [None, 2023, None, 2021, 2022]
    
    
# # test_code = test_o.get_delimiter(product_list)
# test_code = test_o.fwd_code_creator(product_list,
#                                     delivery_list,
#                                     year_list)
# test_df = test_o.fwd_df(sD, eD,
#                         product_list,
#                         delivery_list,
#                         year_list)

    
    
    
            
    
    
