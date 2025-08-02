# -*- coding: utf-8 -*-
"""
Created on Tue Jun 20 10:18:28 2023

@author: krajcovic
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
from time import sleep

import sys
sys.path.append('X:\\Utilities')
from Utilities.date_functions import start_date, end_date

#import refinitiv.dataplatform.eikon as ek
#ek.set_app_key('ce071eef39644b8584220361198bceb2cb24790d')

from refinitiv import data as rd


class EikonSpot:
    def __init__(self, grid, start_date,end_date):
        self.__grid = grid
        self.__start_date = pd.to_datetime(start_date)-dt.timedelta(days=2)
        self.__end_date = pd.to_datetime(end_date)
        
    @property
    def grid(self):
        return self.__grid
    @property
    def start_date(self):
        return self.__start_date
    @property
    def end_date(self):
        return self.__end_date
    
    @property
    def eua_spot_dict(self):
        my_dict = {'third': {'eu': 'EEX-EUA3EU-AUC',
                              'pl': 'EEX-EUA3PL-AUC',
                              'de': 'EEX-EUA3DE-AUC'},
                   'fourth': {'eu': 'EEX-EUA4EU-AUC',
                              'pl': 'EEX-EUA4PL-AUC',
                              'de': 'EEX-EUA4DE-AUC'}
                   }
    
    # 'third': {'eu': 'EEX-EUA3EU-AUC',
    #                      'pl': 'EEX-EUA3PL-AUC',
    #                      'de': 'EEX-EUA3DE-AUC'

        return my_dict
    
    @property
    def country_code(self):
        ric_dict = {}
        ric_dict['de'] = 'ehlde'
        ric_dict['fr'] = 'pnx'
        ric_dict['it'] = 'gmeit'
        ric_dict['it_nord'] = 'gmenrd'
        ric_dict['hu'] = 'hpxh'
        ric_dict['cz'] = 'oteczeur'
        ric_dict['sk'] = 'otesk'
        ric_dict['nord'] = 'fxsys=npx'
        ric_dict['ro'] = 'opcom'
        ric_dict['es'] = 'omeles'
        ric_dict['be'] = 'ehbe'
        ric_dict['nl'] = 'epxnlh'
        ric_dict['deat'] = 'ehldeat'
        ric_dict['pt'] = 'omelpt'
        ric_dict['gb'] = 'ehlgb'
        ric_dict['dkw'] = 'fxdkweur=npx'
        ric_dict['dke'] = 'fxdkeeur=npx'
        ric_dict['ch'] = 'swix'
        ric_dict['at'] = 'ehlat'
        ric_dict['si'] = 'sresq'
        ric_dict['bg'] = 'ibedambgn'
        ric_dict['hr'] = 'crxhr'
        ric_dict['gr'] = 'heegrauch'
        return ric_dict[self.grid]
     
    def ric_creator(self):
        if ((self.grid.upper() == 'NORD')|\
            (self.grid.upper() == 'DKW')\
                |(self.grid.upper() == 'DKE')):
           
            rics = [self.country_code.upper()[:-4]\
                    + '%02d'%+ a\
                        +self.country_code.upper()[-4:]\
                             for a in range(1,25)]
            
        else:
            rics = [self.country_code.upper()+ '%02d'% a for a in range(1,25)]
        return rics

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
        comm_dict['bg'] = 'fk'
        comm_dict['gr'] = 'ff'
        comm_dict['at'] = 'at'
        comm_dict['si'] = 'fv'
        comm_dict['gas'] = 'tfm'
        comm_dict['coal'] = 'atw'
        comm_dict['eua'] = 'feua'
        
        comm_dict['dk'] = 'eno'
        comm_dict['dkw'] = 'lcph'
        comm_dict['dke'] = 'larh'
        
        return comm_dict[market].upper()
    
    

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

    def tenor_date_code(self, start_date):
        return self.start_code(start_date.month) + str(start_date.year)[-1]

    def fwd_code_creator(self, market, start_date, period, delivery):
        out_string = self.fwd_mkt_code(market)
        if 'dk' in market.lower():
            if period in ['M', 'm']:
                out_string = self.fwd_mkt_code('dk') + 'M'
            elif period in ['Q', 'q']:
                out_string = self.fwd_mkt_code('dk') + 'Q'
            else:
                pass
            
            if delivery == 'base':
                out_string += 'B' + self.fwd_mkt_code(market)
            else:
                out_string += 'P' + self.fwd_mkt_code(market)
        else:
            if market.lower() == 'coal':
                pass
            else:
                if delivery == 'base':
                    out_string += 'B'
                else:
                    out_string += 'P'
            if period in ['M', 'm']:
                out_string += 'M'
            elif period in ['Q', 'q']:
                out_string += 'Q'
            else:
                pass
        out_string += self.tenor_date_code(start_date)
        if dt.datetime.today() > end_date(start_date, period):
            out_string += '^' + str(start_date.year)[-2]
        return out_string
        
    def fwd_rel_code_creator(self, market, period_code, delivery):
        period, rel_str = period_code.split('_')
        out_string = self.fwd_mkt_code(market)
        if 'dk' in market.lower():
            if period in ['M', 'm']:
                out_string = self.fwd_mkt_code('dk') + 'M'
                sys_string = 'ENOAFBL' + 'M'
            elif period in ['Q', 'q']:
                out_string = self.fwd_mkt_code('dk') + 'Q'
                sys_string = 'ENOAFBL' + 'Q'
            elif period in ['Y', 'y']:
                out_string = self.fwd_mkt_code('dk') + 'Y'
                sys_string = 'ENOFBL' + 'Y'
            else:
                pass
            
            if delivery == 'base':
                out_string += 'B' + self.fwd_mkt_code(market)
            else:
                out_string += 'P' + self.fwd_mkt_code(market)
            out_string += 'c' + str(int(rel_str) + 1)
            sys_string += 'c' + str(int(rel_str) + 1)
            out_list = [out_string, sys_string]
            return out_list
        elif self.grid == 'coal':
            if period in ['M', 'm']:
                out_string += 'M'
            elif period in ['Q', 'q']:
                out_string += 'Q'
            elif period in ['Y', 'y']:
                out_string += 'Y'
            else:
                pass
            out_string += 'c' + str(int(rel_str) + 1)
            return out_string
        else:
            if delivery == 'base':
                out_string += 'B'
            else:
                out_string += 'P'
            if period in ['M', 'm']:
                out_string += 'M'
            elif period in ['Q', 'q']:
                out_string += 'Q'
            elif period in ['Y', 'y']:
                out_string += 'Y'
            else:
                pass
            if period in ['M', 'm']:
                out_string += 'c' + str(int(rel_str) + 1)
            else:
                out_string += 'c' + str(int(rel_str))
            return out_string

    def prices_df(self):
        rd.open_session()
        df = pd.DataFrame()
        for ric in self.ric_creator():
            
            
            temp = rd.get_history(universe=ric,
                                fields=['TRDPRC_1'],
                                interval='1D',
                                start=self.start_date.\
                                    strftime('%Y%m%d'),
                                end=self.end_date.\
                                    strftime('%Y%m%d')).astype(float)
            temp = temp.rename(columns={'TRDPRC_1': ric})
                            
            if df.empty:
                df = temp.copy()
            else:
                df = pd.concat([df,temp],axis=1)
            sleep(0.1)
        rd.close_session()

        df = df.stack()
        df = df.reset_index().copy()
        if ((self.grid.upper() == 'NORD')|\
            (self.grid.upper() == 'DKW')\
                |(self.grid.upper() == 'DKE')):
            df['hour'] = [int(a[-6:-4])-1 for a in df['level_1']]
        else:
            df['hour'] = [int(a[-2:])-1 for a in df['level_1']]
        df['date'] = pd.to_datetime(df['Date']) + dt.timedelta(days=1)
        df['datetime'] = df['date'] + pd.to_timedelta(df['hour'],unit='h')
        #df[spot.grid] = df[0]
        df[self.grid] = df[0]
        df = df[['datetime', self.grid]].copy()
        df = df.set_index('datetime')
        rd.close_session()
        
        return df
    
    def volumes_df(self):
        rd.open_session()
        df = pd.DataFrame()
        for ric in self.ric_creator():
            
            
            temp = rd.get_history(universe=ric,
                                fields=['ACVOL_DEC'],
                                interval='1D',
                                start=self.start_date.\
                                    strftime('%Y%m%d'),
                                end=self.end_date.\
                                    strftime('%Y%m%d')).astype(float)
            temp = temp.rename(columns={'ACVOL_DEC': ric})
                            
            if df.empty:
                df = temp.copy()
            else:
                df = pd.concat([df,temp],axis=1)
            sleep(0.1)
        rd.close_session()

        df = df.stack()
        df = df.reset_index().copy()
        df['hour'] = [int(a[-2:])-1 for a in df['level_1']]
        df['date'] = pd.to_datetime(df['Date']) + dt.timedelta(days=1)
        df['datetime'] = df['date'] + pd.to_timedelta(df['hour'],unit='h')
        #df[spot.grid] = df[0]
        df[self.grid +'_v'] = df[0]
        df = df[['datetime', self.grid+'_v']].copy()
        df = df.set_index('datetime')
        
        return df
    
    def price_vol_merge(self):
        try:
            vols = self.volumes_df()
            prices = self.prices_df()
            
            df = pd.concat([vols,prices],axis=1)
            df[['b_volume', 's_volume']] = np.nan
            df = df[['b_volume', 's_volume',
                     self.grid +'_v',
                     self.grid]].copy()
            df.columns = ['b_volume', 's_volume',
                         'volume', 'price']
        except:
            df = self.prices_df()
            
            
            df[['volume', 'b_volume', 's_volume']] = np.nan
            df = df[['b_volume', 's_volume', 'volume',
                     self.grid]].copy()
            df.columns = ['b_volume', 's_volume',
                         'volume', 'price']
        return df
    
    def spot_data(self):
        
        df = self.price_vol_merge()
        return df

    def fwd_df_one(self, date, period_list, del_list):
        rd.open_session()
        ric_list = [self.fwd_code_creator(self.grid, start_date(date, p), p[0], d)
                    for p, d in zip(period_list, del_list)]
        temp = rd.get_history(universe=ric_list,
                              fields=['SETTLE'],
                              interval='1D',
                              start=(date - dt.timedelta(days=1)).strftime('%Y%m%d'),
                              end=date.strftime('%Y%m%d')).astype(float)
        rd.close_session()
        try:
            temp.columns = period_list
        except(ValueError):
            temp = pd.DataFrame([np.nan] * len(period_list), index=period_list).T
        temp.index = [date]
        return temp

    def fwd_df_old(self, date_range, period_list, del_list):
        data = pd.DataFrame()
        for d in date_range:
            data_aux = self.fwd_df_one(d, period_list, del_list)
            data = pd.concat([data, data_aux], axis=0)
        data.fillna(method='ffill', inplace=True)
        return data
    
    def fwd_df_abs(self, sD, eD, period_list, period_start_list,
                   delivery_list, weekend_on=False):
        ric_list = [self.fwd_code_creator(self.grid, period_start, period, delivery)
               for period_start, period, delivery in zip(period_start_list,
                                                         period_list,
                                                         delivery_list)]
        date_vec = pd.date_range(sD, eD, freq='D')
        rd.open_session()
        temp1 = rd.get_history(universe=ric_list,
                              fields=['SETTLE'],
                              interval='1D',
                              start=sD.strftime('%Y%m%d'),
                              end=eD.strftime('%Y%m%d')).astype(float)
        rd.close_session()
        temp1.columns = ric_list
        if weekend_on == True:
            temp1 = temp1.reindex(date_vec)
            temp1.fillna(method='ffill', inplace=True)
        return temp1

    def fwd_df_rel(self, sD, eD, period_list, del_list):
        if 'dk' in self.grid.lower():
            date_vec = pd.date_range(sD, eD, freq='D')
            rd.open_session()
            
            ric_list = [self.fwd_rel_code_creator(self.grid, p, d)
                        for p, d in zip(period_list, del_list)]
            
            market_list = [ric_list[a][0] for a in range(len(ric_list))]
            sys_list = [ric_list[a][1] for a in range(len(ric_list))]
            temp1 = rd.get_history(universe=market_list,
                                  fields=['SETTLE'],
                                  interval='1D',
                                  start=sD.strftime('%Y%m%d'),
                                  end=eD.strftime('%Y%m%d')).astype(float)
            #temp nordic sys price
            temp2 = rd.get_history(universe=sys_list,
                                  fields=['SETTLE'],
                                  interval='1D',
                                  start=sD.strftime('%Y%m%d'),
                                  end=eD.strftime('%Y%m%d')).astype(float)
            rd.close_session()
            temp1.columns = period_list
            temp2.columns = period_list
            temp1 = temp1.reindex(date_vec)
            temp2 = temp2.reindex(date_vec)
            temp1.fillna(method='ffill', inplace=True)
            temp2.fillna(method='ffill', inplace=True)
            return temp1+temp2
        else:
            date_vec = pd.date_range(sD, eD, freq='D')
            if self.grid.lower() == 'eua':
                ric_list = ['FEUAZ' + str(a)[-1] + "^" + str(a)[-2]
                            if a<dt.date.today().year else
                            'FEUAZ' + str(a)[-1]
                            for a in pd.date_range(start=sD,
                                                   end=eD,
                                                   freq='YS').year]
                if len(period_list)==len(ric_list):
                    pass
                else:
                    period_list = [period_list[0] for a in range(len(ric_list))]
            
            else:            
                ric_list = [self.fwd_rel_code_creator(self.grid, p, d)
                            for p, d in zip(period_list, del_list)]
            
            if self.grid.lower() == 'coal':
                rd.open_session()
                temp = rd.get_history(universe=ric_list,
                                      fields=['SETTLE'],
                                      interval='1D',
                                      start=sD.strftime('%Y%m%d'),
                                      end=eD.strftime('%Y%m%d')).astype(float)
                eur = rd.get_history(universe=['EUR='],
                                      fields=['MID_PRICE'],
                                      interval='1D',
                                      start=sD.strftime('%Y%m%d'),
                                      end=eD.strftime('%Y%m%d')).astype(float)
                temp = pd.concat([temp, eur], axis=1, join='inner')
                temp['SETTLE'] = temp['SETTLE']/temp['MID_PRICE']
                temp = temp[['SETTLE']].copy()
            else:
                rd.open_session()
                temp = rd.get_history(universe=ric_list,
                                      fields=['SETTLE'],
                                      interval='1D',
                                      start=sD.strftime('%Y%m%d'),
                                      end=eD.strftime('%Y%m%d')).astype(float)
            rd.close_session()
            if self.grid.lower() == 'eua':
                temp.columns = ric_list
                temp = temp.reindex(date_vec)
                temp = temp.T.fillna(method='bfill').T.\
                    fillna(method='ffill').copy()
                temp.columns = period_list
                temp = temp.iloc[:,[0]].copy()
            else:
                
                temp.columns = period_list
                
                temp = temp.reindex(date_vec)
                temp.fillna(method='ffill', inplace=True)
            
            
            return temp
        
    @property
    def eua_spot_list(self):
        return [item for sublist in [list(self.eua_spot_dict[a].values())
                    for a in self.eua_spot_dict.keys()] for item in sublist]
        
    def eua_auct_prices(self,sD,eD):
        assert self.grid == 'eua_spot'
        rd.open_session()
        df = rd.get_history(universe=self.eua_spot_list,
                            fields=['TRDPRC_1'],
                            start=sD.strftime('%Y%m%d'),
                            end=eD.strftime('%Y%m%d')).astype(float)
        df = df.fillna(method='ffill', axis=1).iloc[:,[-1]].copy()
        df = df.rename(columns={df.columns[0]:'eua_spot'})
        
        return df
    
if __name__ == '__main__':
    
    import Loaders.loader as ld
    
    
    start_date = dt.datetime(2025,7,3)
    end_date = dt.datetime(2027,7,6)
    
    spot_inst = EikonSpot('it', start_date, end_date)
    
    spot = spot_inst.spot_data()
    
    # es_o = EikonSpot('eua_spot', start_date, end_date)
    # # names_dict = es_o.eua_spot_dict

    # # ric_list = [item for sublist in [list(names_dict[a].values())
    # #             for a in names_dict.keys()] for item in sublist]
    # # eua_df = es_o.eua_auct_prices(start_date, end_date)
    
    # cz_spot = ld.spot_loader(country_list=['cz'],
    #                        bT=start_date,
    #                        eT=end_date)
    # cz_spot = cz_spot.resample('D').mean()
    
    # df = pd.concat([eua_df, cz_spot], axis=1, join='outer')
    # df['eua_spot'] = df['eua_spot'].fillna(method='ffill')
    # df = df.dropna(subset=['eua_spot'])
    # df.to_csv(r'C:\Users\krajcovic\Documents\Trading\EIF\eua_cz_spot.csv')
    
    

        

