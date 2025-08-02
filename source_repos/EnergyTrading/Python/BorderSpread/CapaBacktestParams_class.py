# -*- coding: utf-8 -*-
"""
Created on Mon Jul 17 09:05:20 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
import os
import requests
from dateutil.relativedelta import relativedelta
import sys

sys.path.append('X:\\Loaders')
sys.path.append('X:\\BorderSpread')
from EikonSpot_class import EikonSpot
from border_class import DataBorderClass
import capacity_class as capa
import CapaBacktestParams_class as CapaParams
from pandas.tseries.offsets import BDay



class CapaParams:
    
    def __init__(self, borders, start_date, end_date, token='86e20d1e-c0fc-406d-95b6-bc8ae625f3c0'):
        if type(borders) == list:
            self.__borders = borders
        else:
            self.__borders = [borders]
        
        self.__start_date = pd.to_datetime(start_date)
        self.__end_date = pd.to_datetime(end_date)
        self.__token = token
        
    @property
    def token(self):
        return self.__token
        
    @property
    def borders(self):
        return self.__borders
    
    
    
    @property
    def start_month(self):
        return self.__start_date.month    
    @property
    def end_month(self):
        return self.__end_date.month
    @property
    def start_year(self):
        return self.__start_date.year
    @property
    def end_year(self):
        return self.__end_date.year
    
    @property
    def start_date(self):
        start_date = self.__start_date
        start_date = dt.date(self.start_year,
                             self.start_month,
                             1)
        return start_date
    
    @property
    def end_date(self):
        
        end_date = dt.date(self.end_year,
                           self.end_month,
                           1) + relativedelta(months=1, days=-1)
        return end_date
    
    
    #get list of months and years of capacities
    @property
    def period_list(self):
        date_range = pd.date_range(start=self.start_date,
                                   end=self.end_date,
                                   freq='m')
        return [(date_range.month[i],
                 date_range.year[i]) for i in range(0,len(date_range))]
        
    
    def JaoAuctRes(self):
        borders = []
        auctions = []
        auct_dates = []
        months = []
        years = []
        for border in self.borders:
            
            border = border.upper().replace('_','-')
            if ('DE' in border) and ('CZ' in border):
                border = border.replace('DE', 'DE(TenneT)')
            for month, year in self.period_list:
                months.append(month)
                years.append(year)
                #borders.append(border.lower().replace('-','_'))
                date = dt.date(year,month,1) - relativedelta(months=1)
                date_str = date.strftime('%Y-%m-%d')
                url1 = 'https://api.jao.eu/OWSMP/getauctions?horizon=monthly&corridor='
                url2 = '&fromdate='
                url = url1 + border + url2 + date_str
                if 'DE(TenneT)' in border:
                    borders.append(border.replace('DE(TenneT)','DE').replace('-','_').lower())
                else:
                    borders.append(border.replace('-','_').lower())
                print(url)
                response = requests.get(url,
                                        headers={'AUTH_API_KEY': self.token})
                if response.status_code==200:
                    response = response.json()[0]
                    auct_date = response['bidGateClosure'].split('T')[0]
                    auct_dates.append(auct_date)
                    if response['results'] == []:
                        auctions.append(None)
                    else:
                        auct_price = response['results'][0]['auctionPrice']
                        #try:
                           # auct_price = response['results'][0]['auctionPrice']
                        #except:
                            #auct_price = None
                        auctions.append(auct_price)
                        
                else:
                    auct_dates.append(dt.date(year, month,20)-relativedelta(months=1)+BDay(2))
                    auctions.append(None)
                    print('error')
                    continue
              
        df = pd.DataFrame(np.array([borders,
                                 auctions,
                                 auct_dates]).T,
                                index=[months, years],
                                columns=['border', 'auct_price', 'auct_date'])
        df.index.names = ['month', 'year']
        df = df.set_index(['border'], append=True)
        return df
    
    def BordersLiq(self):
        grids = list(dict.fromkeys(sum([[self.borders[i].split('_')[0],
                                         self.borders[i].split('_')[1]]
                                        for i in range(len(self.borders))],[])))
        df = pd.DataFrame()
        for grid in grids:
            spot = EikonSpot(grid,self.start_date,self.end_date)
            temp = spot.prices_df()
            if df.empty:
                df = temp.copy()
            else:
                df = pd.concat([df,temp],axis=1)
        df = df.loc[((df.index.date>=self.start_date)&
                     (df.index.date<=self.end_date))].copy()
        for border in self.borders:
            c1 = border.split('_')[0]
            c2 = border.split('_')[1]
            df[border] = np.where(df[c1]>df[c2],
                                  0,
                                  df[c2]-df[c1])
        df = df.resample('m').mean()
        df['month'] = df.index.month
        df['year'] = df.index.year
        df = df.set_index(['month', 'year'])
        df = df.loc[:,~df.columns.isin(grids)].copy()
        #df.columns = [a + '_liq' for a in df.columns]
        df = df.stack().sort_index(level=[2,0,1])
        df.index.names = ['month', 'year', 'border']
        df = df.rename('settle')
        return df
    
    def AuctPrice_Liq_merge(self):
        auctions = self.JaoAuctRes()
        liq = self.BordersLiq()
        df = pd.concat([auctions, liq],axis=1)
        return df
    
    def AddFutPrice(self):
        df_temp = self.AuctPrice_Liq_merge()
        #df_temp = ext_df.copy()
        fut_start_date = pd.to_datetime(df_temp['auct_date'].dropna().min())
        fut_end_date = pd.to_datetime(df_temp['auct_date'].dropna().max())
        
        grids = list(dict.fromkeys(sum([[self.borders[i].split('_')[0],
                                         self.borders[i].split('_')[1]]
                                        for i in range(len(self.borders))],[])))
        
        futs = pd.DataFrame()
        for grid in grids:
            obj = EikonSpot(grid,self.start_date,self.end_date)
            temp = obj.fwd_df_rel(fut_start_date,
                                  fut_end_date,
                                  ['M_1'],
                                  ['base'])
            temp.columns = [grid]
            if futs.empty:
                futs = temp.copy()
            else:
                futs = pd.concat([futs, temp], axis=1)
                
        borders = []
        auct_dates = []
        fut_spreads = []
        c1_list = []
        c2_list = []
        for border, auct_date in zip(df_temp.index.get_level_values(level=2),
                                     df_temp['auct_date']):
            if 'de(tennet)' in border:
                border = border.replace('de(tennet)','de')
            c1 = border.split('_')[0]
            c2 = border.split('_')[1]
            temp = futs[[c1,c2]].copy()
            temp['border'] = temp[c1]-temp[c2]
            temp = temp.loc[temp.index==auct_date].copy()
            borders.append(border)
            auct_dates.append(auct_date)
            try:
                c1_list.append(temp[c1].item())
                c2_list.append(temp[c2].item())
                fut_spreads.append(temp['border'].item())
            except:
                c1_list.append(None)
                c2_list.append(None)
                fut_spreads.append(None)
        
        df = pd.DataFrame(np.array([borders,
                                 auct_dates,
                                 c1_list,
                                 c2_list,
                                 fut_spreads]).T,
                                columns=['border', 'auct_date',
                                         'c1', 'c2', 'fut_spread'])
        
        df = df.set_index(['border', 'auct_date'])
        df_temp = df_temp.set_index(['auct_date'], append=True)
        df = pd.concat([df_temp.reset_index(['month','year']),df],axis=1)
        df = df.reset_index()
        df = df.set_index(['month','year'])
        return df
    
    def ParamsData(self,delivery=['base'], lookback=12):
        
        fv_list = []
        delta_list = []
        borders = []
        auct_dates = []
        
        df_temp = self.AddFutPrice()
        df_temp[['auct_price', 'c1', 'c2', 'fut_spread']] = df_temp[['auct_price', 'c1', 'c2', 'fut_spread']].astype(float)
        
        for border, auct_date,c1,c2 in zip(df_temp['border'],
                                     df_temp['auct_date'],
                                     df_temp['c1'],
                                     df_temp['c2']):
            border = [border]
            if type(auct_date) is pd.Timestamp:
                auct_date = dt.datetime.strptime(auct_date.strftime('%Y-%m-%d'), '%Y-%m-%d')
            elif type(auct_date) is str:
                auct_date = dt.datetime.strptime(auct_date, '%Y-%m-%d')
            else:
                fv_list.append(None)
                delta_list.append(None)
                borders.append(border[0])
                auct_dates.append(None)
                print(border + ' has auct_date variable error, whatever the type, but not str or timestamp')
        
            bs_class = DataBorderClass(border, ['implicit'],
                                     auct_date-relativedelta(months=lookback), 
                                     auct_date)
            bs_class.load_data(path_spot=r'C:\Users\krajcovic\Documents\Trading\Data\Price\EEX\Spot\spot.txt')
            data = {}
            for del_ in delivery:
                data[del_] = bs_class.aggregate_data('M', delivery=del_)
            capacity = capa.ImplicitCapacity(border, delivery)
            
            capacity.capa_fit(data[del_], del_)
            
            capa_fv = capacity.capa_price(c1,c2,'base')[0]
            delta = capacity.capa_delta(c1,c2,'base')[0]
            
            fv_list.append(capa_fv)
            delta_list.append(delta)
            borders.append(border[0])
            auct_dates.append(auct_date.strftime('%Y-%m-%d'))
        df = pd.DataFrame(np.array([borders,
                                 auct_dates,
                                 fv_list,
                                 delta_list]).T,
                                columns=['border', 'auct_date',
                                         'capa_fv', 'capa_delta'])
        df['auct_date'] = pd.to_datetime(df['auct_date'])
        df_temp['auct_date'] = pd.to_datetime(df_temp['auct_date'])
        df = df.set_index([ 'auct_date','border'])
        df_temp = df_temp.set_index(['auct_date', 'border'], append=True)
        df = pd.concat([df_temp.reset_index(['month','year']),df],axis=1)
        df = df.reset_index()
        df = df.set_index(['month','year'])
        df[['capa_fv', 'capa_delta']] = df[['capa_fv', 'capa_delta']].astype(float)
        df.loc[:,'auct_price':] = round(df.loc[:,'auct_price':],2)
            
        
        return df
        
        

            
        
