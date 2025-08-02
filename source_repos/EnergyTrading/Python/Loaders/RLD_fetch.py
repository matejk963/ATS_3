# -*- coding: utf-8 -*-
"""
Created on Fri Jun 30 12:53:36 2023

@author: krajcovic
"""


from ftplib import FTP
from io import BytesIO
import pandas as pd
import numpy as np
import datetime as dt
from dateutil.relativedelta import relativedelta
from Utilities.date_functions import date_dayahead, date_weekahead
import time

from Database.DB_reader import Database
from Enums import FTP as FTP_ENUM

class RLDFetch:
    def __init__(self, grid='de',
                 start_date=dt.date.today(),
                 end_date=None,
                 user = 'krajcovic_matej@energytrading.sk',
                 password = 'kmfT5Q$kw',
                 address = r'pointconnect.commodities.refinitiv.com',
                 live_demand = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Demand/',
                 hist_demand = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Demand/',
                 live_supply = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/',
                 hist_supply = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'):
        self.__grid = grid.upper()
        self.__start_date = pd.to_datetime(start_date)
        self.__end_date = pd.to_datetime(end_date)
        self.__user = user
        self.__password = password
        self.__address = address
        self.__live_demand = live_demand
        self.__hist_demand = hist_demand
        self.__live_supply = live_supply
        self.__hist_supply = hist_supply
        self._path = '/PCO_Energy_Trading/PCO_Energy_Trading/'
        self._live_path = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/'
        self._hist_filenames = {
            'dem_ens': "Demand/5010557_HIST_Pwr_PCA_CON_ECEns_AVG_DEU_F_{year}.CSV",
            'dem_op': "Demand/5011215_HIST_Pwr_PCA_CON_ECOP_DEU_F_{year}.CSV",
            'wind_ens': "Supply/5011254_HIST_Pwr_PCA_PRO_Wind_ECens_AVG_DEU_F_{year}.CSV",
            'wind_op': "Supply/5010503_HIST_Pwr_PCA_PRO_Wind_ECop_DEU_F_{year}.CSV",
            'solar_ens': "Supply/5018189_HIST_Pwr_PCA_PRO_Solar_ECens_AVG_DEU_F_{year}.CSV",
            'solar_op': "Supply/5011011_HIST_Pwr_PCA_PRO_Solar_ECop_DEU_F_{year}.CSV"
        }
        self._live_filenames = {
            'dem_ens': "Demand/5005429_Pwr_PCA_CON_ECEns_AVG_DEU_F_{date}.CSV",
            'dem_op': "Demand/5005430_Pwr_PCA_CON_ECOP_DEU_F_{date}.CSV",
            'wind_ens': "Supply/5007708_Pwr_PCA_PRO_Wind_ECens_AVG_DEU_F_{date}.CSV",
            'wind_op': "Supply/5007707_Pwr_PCA_PRO_Wind_ECop_DEU_F_{date}.CSV",
            'solar_ens': "Supply/5018188_Pwr_PCA_PRO_Solar_ECens_AVG_DEU_F_{date}.CSV",
            'solar_op': "Supply/5004202_Pwr_PCA_PRO_Solar_ECop_DEU_F_{date}.CSV"
        }
        self._hist_norm_filenames = {
            'solar': "Supply/5108391_HIST_Pwr_PCA_PRO_Solar_AVG_DEU_N_A_{year}.CSV",
            'wind': "Supply/5108383_HIST_Pwr_PCA_PRO_Wind_AVG_DEU_N_A_{year}.CSV",
            'con': "Normals/5022227_HIST_Pwr_PCA_CON_DEU_N_A_{year}.CSV"
        }
        
        self.__ftp = FTP(self.__address)
        self.__ftp.login(self.__user,
                         self.__password)
        
    
        
    @property
    def ftp(self):
        return self.__ftp
    
    @property
    def grid(self):
        grid_dict = {}
        grid_dict['DE'] = 'DEU'
        return self.__grid
    
    @property
    def date(self):
        return self.__start_date
    
    @property
    def end_date(self):
        return self.__end_date
    
    @property
    def user(self):
        return self.__user
    
    @property
    def password(self):
        return self.__password
    
    @property
    def address(self):
        return self.__address
    
    @property
    def live_demand(self):
        return self.__live_demand
    
    @property
    def hist_demand(self):
        return self.__hist_demand
    
    @property
    def live_supply(self):
        return self.__live_supply
    
    @property
    def hist_supply(self):
        return self.__hist_supply
    
    
    def fund_type(self,fund_type):
        if fund_type in ['con', 'cons', 'CON', 'CONS',
                         'consumption', 'Consumption', 'CONSUMPTION']:
            fund_type = 'CON'
        elif fund_type in ['wind', 'Wind', 'WIND']:
            fund_type = 'Wind'
        elif fund_type in ['solar', 'Solar', 'SOLAR', 'sol']:
            fund_type = 'Solar'
        else:
            raise ValueError('unknown fundamentals type')
        return fund_type
    
    def forecast_type(self, forecast_type, fund_type):
        if forecast_type in ['op', 'OP', 'Op',
                             'Operational', 'operational']:
            if fund_type == 'CON':
                forecast_type = 'OP'
            else:
                forecast_type = 'op'
        elif forecast_type in ['ens' , 'ENS', 'Ens',
                               'Ensamble', 'ensamble']:
            if fund_type == 'CON':
                forecast_type = 'Ens'
            else:
                forecast_type = 'ens'
        else:
            raise ValueError('unknown forecast type')
        return forecast_type
    
    def ftp_file_fetch(self, fund_type,
                       forecast_type, live_or_history):
        fund_type = self.fund_type(fund_type)
        
        forecast_type = self.forecast_type(forecast_type,
                                          fund_type)
            
                    

        #fundamentals type conversion dict
        fund_type_dict = {}
        fund_type_dict['CON'] = 'demand'
        fund_type_dict['Wind'] = 'supply'
        fund_type_dict['Solar'] = 'supply'
        fund_type_dict['RLD'] = 'demand'
        #ftp folders dict
        ftp_folders_dict = {}
        ftp_folders_dict['history'] = {}
        ftp_folders_dict['live'] = {}
        ftp_folders_dict['history']['demand'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Demand/'
        ftp_folders_dict['history']['supply'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
        ftp_folders_dict['live']['demand'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Demand/'
        ftp_folders_dict['live']['supply'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/'
        
        ftp_folder = ftp_folders_dict[live_or_history][fund_type_dict[fund_type]]
        #conect to ftp folder
        self.ftp.cwd(ftp_folder)
        #collect files
        files = []
        self.ftp.retrlines('NLST', files.append)
        file = list(filter(lambda x: (self.grid in x)
                           and (fund_type in x)
                           and (forecast_type in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        df = pd.read_csv(flo, sep='|').reset_index()
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
        df['FctDate'] = pd.to_datetime(df['ForecastDate'], dayfirst=True)
        df['ValueDate'] = pd.to_datetime(df['ValueDate'], dayfirst=True, utc=True)
        df['datetime'] = pd.DatetimeIndex(df['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        df[fund_type] = df['Value'].astype(float)
        df['Id'] = df['Id'].astype(float)
        df['FctHour'] = df['FctDate'].dt.hour
        df = df[['Id', 'FctDate', 'FctHour',
                     'datetime', fund_type]].copy()
        
        return df, last_update_date
        
    
    def get_live_data(self, fund_type):
        
        
        #adjust variables
        fund_type = self.fund_type(fund_type)
        live_or_history = 'live'
        
        
        #fetch the files for op and ens
        df_op, last_update_date_op = self.ftp_file_fetch(fund_type,'op',
                                              live_or_history)
        df_ens, last_update_date_ens = self.ftp_file_fetch(fund_type,'ens',
                                              live_or_history)
        #adjust the files
        if fund_type == 'Wind':
            df_op = df_op.loc[df_op['Id']==101658319].copy()
            df_ens = df_ens.loc[df_ens['Id']==101658339].copy()
        
        df_op['prod'] = 'op'
        df_ens['prod'] = 'ens'
        df_op = df_op[['FctDate', 'datetime', 'prod', fund_type]].copy()
        df_ens = df_ens[['FctDate', 'datetime', 'prod', fund_type]].copy()
        #merge dataframe and modify
        df = pd.concat([df_op, df_ens])
        df = pd.pivot_table(df, values=fund_type, index='datetime',
                            columns=['FctDate', 'prod'])
        df = df.sort_index(axis=1,
                           level=[0,1],
                           ascending=[True,False])
        df.columns = df.columns.to_flat_index()
        df = df.fillna(method='ffill', axis=1)
        df = df.iloc[:,[-1]].copy()
        df = df.rename(columns={df.columns[0]: fund_type})
        
        print('Latest ' + fund_type +' Op update date: ', last_update_date_op)
        print('Latest ' + fund_type +' Ens update date: ', last_update_date_ens)
        return df
    
    def get_live_rld(self):
        #get consumption
        cons = self.get_live_data('CON')
        #get wind
        wind = self.get_live_data('wind')
        #get solar
        solar = self.get_live_data('sol')
        #create rld
        rld = pd.concat([cons, wind, solar],axis=1)
        rld = rld.dropna()
        rld['rld'] = rld['CON']-rld['Wind']-rld['Solar']
        rld = rld[['rld']].copy()
        return rld
    
    def get_live_cons_op(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_demand)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('CON' in x)
                           and ('ECOP' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        cons = pd.read_csv(flo, sep='|').reset_index()
        cons.columns = cons.iloc[0]
        cons = cons.iloc[1:].copy()
        cons['FctDate'] = pd.to_datetime(cons['ForecastDate'], dayfirst=True)
        cons['ValueDate'] = pd.to_datetime(cons['ValueDate'], dayfirst=True, utc=True)
        cons['datetime'] = pd.DatetimeIndex(cons['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        cons['cons'] = cons['Value'].astype(float)
        cons['Id'] = cons['Id'].astype(float)
        cons['FctHour'] = cons['FctDate'].dt.hour
        cons = cons[['Id', 'FctDate', 'FctHour',
                     'datetime', 'cons']].copy()
        ser = sorted(cons['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            
            temp1 = cons.loc[cons['FctDate']==fct_date1].copy()
            temp2 = cons.loc[cons['FctDate']==fct_date2].copy()
            
            cons = temp1[['datetime', 'FctDate', 'cons']].merge(temp2[['datetime', 'cons']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            cons['cons'] = cons['cons'].fillna(cons['cons_remove'])
            cons = cons.drop(['cons_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            cons = cons.loc[cons['FctDate']==fct_date].copy()
            cons = cons[['datetime', 'FctDate', 'cons']].copy()           
            
            
        
        print('Latest Cons update date: ', last_update_date)
        return cons
    
    def get_live_cons_ens(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_demand)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('CON' in x)
                           and ('ECEns' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        cons = pd.read_csv(flo, sep='|').reset_index()
        cons.columns = cons.iloc[0]
        cons = cons.iloc[1:].copy()
        cons['FctDate'] = pd.to_datetime(cons['ForecastDate'], dayfirst=True)
        cons['ValueDate'] = pd.to_datetime(cons['ValueDate'], dayfirst=True, utc=True)
        cons['datetime'] = pd.DatetimeIndex(cons['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        cons['cons'] = cons['Value'].astype(float)
        cons['Id'] = cons['Id'].astype(float)
        cons['FctHour'] = cons['FctDate'].dt.hour
        cons = cons[['Id', 'FctDate', 'FctHour',
                     'datetime', 'cons']].copy()
        ser = sorted(cons['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            
            temp1 = cons.loc[cons['FctDate']==fct_date1].copy()
            temp2 = cons.loc[cons['FctDate']==fct_date2].copy()
            
            cons = temp1[['datetime', 'FctDate', 'cons']].merge(temp2[['datetime', 'cons']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            cons['cons'] = cons['cons'].fillna(cons['cons_remove'])
            cons = cons.drop(['cons_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            cons = cons.loc[cons['FctDate']==fct_date].copy()
            cons = cons[['datetime', 'FctDate', 'cons']].copy()           
            
            
        
        print('Latest Cons update date: ', last_update_date)
        return cons
    
    def get_live_wind_op(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_supply)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('Wind' in x)
                           and ('ECop' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        wind = pd.read_csv(flo, sep='|').reset_index()
        wind.columns = wind.iloc[0]
        wind = wind.iloc[1:].copy()
        wind['FctDate'] = pd.to_datetime(wind['ForecastDate'], dayfirst=True)
        wind['ValueDate'] = pd.to_datetime(wind['ValueDate'], dayfirst=True, utc=True)
        wind['datetime'] = pd.DatetimeIndex(wind['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        wind['wind'] = wind['Value'].astype(float)
        wind['Id'] = wind['Id'].astype(float)
        wind['FctHour'] = wind['FctDate'].dt.hour
        wind = wind[['Id', 'FctDate', 'FctHour',
                     'datetime', 'wind']].copy()
        wind = wind.loc[wind['Id']==101658339].copy()
        
        ser = sorted(wind['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            temp1 = wind.loc[wind['FctDate']==fct_date1].copy()
            temp2 = wind.loc[wind['FctDate']==fct_date2].copy()
            
            wind = temp1[['datetime', 'wind']].merge(temp2[['datetime', 'wind']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            wind['wind'] = wind['wind'].fillna(wind['wind_remove'])
            wind = wind.drop(['wind_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            wind = wind.loc[wind['FctDate']==fct_date].copy()
            wind = wind[['datetime', 'wind']].copy()           
            
        
        print('Latest wind update date: ', last_update_date)
        return wind
    
    def get_live_wind_ens(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_supply)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('Wind' in x)
                           and ('ECens' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        wind = pd.read_csv(flo, sep='|').reset_index()
        wind.columns = wind.iloc[0]
        wind = wind.iloc[1:].copy()
        wind['FctDate'] = pd.to_datetime(wind['ForecastDate'], dayfirst=True)
        wind['ValueDate'] = pd.to_datetime(wind['ValueDate'], dayfirst=True, utc=True)
        wind['datetime'] = pd.DatetimeIndex(wind['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        wind['wind'] = wind['Value'].astype(float)
        wind['Id'] = wind['Id'].astype(float)
        wind['FctHour'] = wind['FctDate'].dt.hour
        wind = wind[['Id', 'FctDate', 'FctHour',
                     'datetime', 'wind']].copy()
        wind = wind.loc[wind['Id']==101658339].copy()
        
        ser = sorted(wind['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            temp1 = wind.loc[wind['FctDate']==fct_date1].copy()
            temp2 = wind.loc[wind['FctDate']==fct_date2].copy()
            
            wind = temp1[['datetime', 'wind']].merge(temp2[['datetime', 'wind']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            wind['wind'] = wind['wind'].fillna(wind['wind_remove'])
            wind = wind.drop(['wind_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            wind = wind.loc[wind['FctDate']==fct_date].copy()
            wind = wind[['datetime', 'wind']].copy()           
            
        
        print('Latest wind update date: ', last_update_date)
        return wind
    
    def get_live_solar_op(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_supply)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('Solar' in x)
                           and ('ECop' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        solar = pd.read_csv(flo, sep='|').reset_index()
        solar.columns = solar.iloc[0]
        solar = solar.iloc[1:].copy()
        solar['FctDate'] = pd.to_datetime(solar['ForecastDate'], dayfirst=True)
        solar['ValueDate'] = pd.to_datetime(solar['ValueDate'], dayfirst=True, utc=True)
        solar['datetime'] = pd.DatetimeIndex(solar['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        solar['solar'] = solar['Value'].astype(float)
        solar['Id'] = solar['Id'].astype(float)
        solar['FctHour'] = solar['FctDate'].dt.hour
        solar = solar[['Id', 'FctDate', 'FctHour',
                     'datetime', 'solar']].copy()
        ser = sorted(solar['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            temp1 = solar.loc[solar['FctDate']==fct_date1].copy()
            temp2 = solar.loc[solar['FctDate']==fct_date2].copy()
            
            solar = temp1[['FctDate', 'datetime', 'solar']].merge(temp2[['datetime', 'solar']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            solar['solar'] = solar['solar'].fillna(solar['solar_remove'])
            solar = solar.drop(['solar_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            solar = solar.loc[solar['FctDate']==fct_date].copy()
            solar = solar[['datetime', 'solar']].copy()           
            
            
        
        print('Latest solar update date: ', last_update_date)
        return solar
    
    def get_live_solar_ens(self):
        
        #first connect live demand folder to ftp
        self.ftp.cwd(self.live_supply)
        #get files in ftp folder
        files = []
        self.ftp.retrlines('NLST ', files.append)
        file = list(filter(lambda x: (self.grid in x) and ('Solar' in x)
                           and ('ECens' in x), files))[-1]
        #get date of last update
        last_update_date = file[file.find('_F_')+len('_F_'):
                                file.rfind('.CSV')]
        #create bytesIO object
        flo = BytesIO()
        
        #fetch file from ftp
        self.ftp.retrbinary('RETR ' + file, flo.write)
        flo.seek(0)
        #create and adjust dataframe
        solar = pd.read_csv(flo, sep='|').reset_index()
        solar.columns = solar.iloc[0]
        solar = solar.iloc[1:].copy()
        solar['FctDate'] = pd.to_datetime(solar['ForecastDate'], dayfirst=True)
        solar['ValueDate'] = pd.to_datetime(solar['ValueDate'], dayfirst=True, utc=True)
        solar['datetime'] = pd.DatetimeIndex(solar['ValueDate']).tz_convert('Europe/Berlin').tz_localize(None)
        solar['solar'] = solar['Value'].astype(float)
        solar['Id'] = solar['Id'].astype(float)
        solar['FctHour'] = solar['FctDate'].dt.hour
        solar = solar[['Id', 'FctDate', 'FctHour',
                     'datetime', 'solar']].copy()
        ser = sorted(solar['FctDate'].drop_duplicates())
        if ser[-1].hour in [6,18] and len(ser)>1:            
            fct_date1 = ser[-1]
            fct_date2 = ser[-2]
            
            temp1 = solar.loc[solar['FctDate']==fct_date1].copy()
            temp2 = solar.loc[solar['FctDate']==fct_date2].copy()
            
            solar = temp1[['FctDate', 'datetime', 'solar']].merge(temp2[['datetime', 'solar']],
                                 on='datetime',
                                 how='outer', suffixes=('', '_remove'))
            
            solar['solar'] = solar['solar'].fillna(solar['solar_remove'])
            solar = solar.drop(['solar_remove'],axis=1)
            
        else:
            fct_date = ser[-1]
            
            solar = solar.loc[solar['FctDate']==fct_date].copy()
            solar = solar[['datetime', 'solar']].copy()           
            
            
        
        print('Latest solar update date: ', last_update_date)
        return solar

    def hist_to_dataframe(self, path: str
                         ) -> pd.DataFrame:
        max_retries = 3  # Maximum number of connection retries
        retries = 0

        while retries < max_retries:
            try:
                # Connect to the FTP server
                ftp = FTP(self.__address)
                ftp.login(self.__user, self.__password)
                df = pd.DataFrame()
                
                # Read the CSV file directly from the FTP server into a pandas DataFrame
                with BytesIO() as bio:
                    ftp.retrbinary('RETR ' + path, bio.write)
                    bio.seek(0)  # Move back to the beginning of the buffer
                    df = pd.read_csv(bio, delimiter='|', skiprows=1,
                                     parse_dates=['ForecastDate', 'ValueDate'],
                                     dtype={'Value': np.float64},
                                     date_format='%d.%m.%Y %H:%M:%S')
                
                # Close the FTP connection
                ftp.quit()

                if 'Wind_ECens' in path:
                    df = df.loc[df['Id'] == 101658339]

                df = df.loc[:,['ForecastDate', 'ValueDate', 'Value']]
                # df['ValueDate'] = pd.to_datetime(df['ValueDate'], dayfirst=True, utc=True).tz_convert('Europe/Berlin').tz_localize(None)
                df['ValueDate'] = pd.DatetimeIndex(pd.to_datetime(df['ValueDate'], dayfirst=True, utc=True)).tz_convert('Europe/Berlin').tz_localize(None)
                df.columns = ['forecast_date', 'value_date', 'value']
                df.drop_duplicates()
                return df

            except Exception as e:
                print(f"Error: {e}")
                retries += 1
                print(f"Retrying... (Attempt {retries}/{max_retries})")
                time.sleep(5)  # Wait for a few seconds before retrying
        
        # If all retries fail, raise an exception or return an empty DataFrame
        raise Exception("Failed to retrieve data from FTP server after multiple retries.")
    
        
        
class RLDDatabaseData:
    def __init__(self, path_name):
        self.__db = Database(path_name=path_name)
    @property
    def db(self):
        return self.__db
    
    @staticmethod
    def residual_update_mappings_history(opTrustDays:int, hour: int, minute: int):
        def subDates(date1, date2):
            date1 = dt.datetime.combine(dt.date.min, date1)
            date2 = dt.datetime.combine(dt.date.min, date2)
            return (date1 - date2).total_seconds() / 60
        
        result = ["ens" for x in range(14)]
        ens_start = dt.time(hour=8, minute=26)
        op_start = dt.time(hour=8, minute=0)
        current_time = dt.time(hour=hour, minute=minute)
        ens_delta = max(int(subDates(current_time, ens_start) / 5), 0)
        op_delta = min(max(int(subDates(current_time, op_start) / 5), 0), opTrustDays)
        if ens_delta < 14:
            for i in range(ens_delta,14):
                result[i] = "ens-12"
        if ens_delta < 5:
            for i in range(ens_delta,5):
                result[i] = "ens-6"
        if ens_delta < op_delta:
            for i in range(ens_delta,op_delta):
                result[i] = "op"
        return result
    
    def injectHistoryRldData(self, country, _from=2023, _to=dt.datetime.now().year, twoweeks=True, dbwrite=True):
        # check if _from and _to are datetime objects
        if not isinstance(_to, int):
            print("Error: _to must be an integer")
            return None
        if not isinstance(_from, int):
            print("Error: _from must be an integer")
            return None
        
        r = RLDFetch()
        df_result = pd.DataFrame()
        df_ens = pd.DataFrame()
        df_op = pd.DataFrame()
        for pred_type in ['ens', 'op']:

            for fund in [*FTP_ENUM]:
                df_current = pd.DataFrame()
                column_name = fund + '_' + pred_type
                for y in range(_from, _to+1):
                    path = r._path + FTP_ENUM[fund][f"hist_{pred_type}"].format_map({'year': y})
                    df_temp = r.hist_to_dataframe(path)
                    print(column_name)
                    df_temp.rename(columns={'value': column_name}, inplace=True)
                    if df_current.empty:
                        df_current = df_temp
                    else:
                        df_current = pd.concat([df_current, df_temp])

                if pred_type == 'ens':
                    if df_ens.empty:
                        df_ens = df_current
                        df_ens['merge_key'] = df_ens.groupby(['forecast_date', 'value_date']).cumcount()
                    else:
                        df_current['merge_key'] = df_current.groupby(['forecast_date', 'value_date']).cumcount()
                        df_ens = pd.merge(df_ens, df_current, on=['forecast_date', 'value_date', 'merge_key'], how='outer')
                else:
                    if df_op.empty:
                        df_op = df_current
                        df_op['merge_key'] = df_op.groupby(['forecast_date', 'value_date']).cumcount()
                    else:
                        df_current['merge_key'] = df_current.groupby(['forecast_date', 'value_date']).cumcount()
                        df_op = pd.merge(df_op, df_current, on=['forecast_date', 'value_date', 'merge_key'], how='outer')

        df_result = pd.merge(df_ens, df_op, on=['forecast_date', 'value_date', 'merge_key'], how='outer')

        # Drop the merge_key if it's no longer needed
        df_result = df_result.drop(columns='merge_key')
                
        if twoweeks:
            delta = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=14)
            df_result = df_result[df_result['forecast_date'] >= delta]
        if dbwrite:
            return df_result.to_sql(name="stage_" + country, schema='residual', con=self.db.connection_string, if_exists='replace', index=False)
        else:
            return df_result
        
    def _getHistoryUpdateDate(self, r, file_path, time=False):
        # Create an FTP connection
        ftp = FTP(r.address)
        ftp.login(user=r.user, passwd=r.password)

        # Use the MDTM command to get the last modified timestamp of the file
        timestamp_str = ftp.sendcmd(f"MDTM {file_path}")
        # Parse the timestamp string into a datetime object
        timestamp = dt.datetime.strptime(timestamp_str[4:], "%Y%m%d%H%M%S.%f")
        # Close the FTP connection
        ftp.quit()
        if time:
            return timestamp
        return timestamp.date()
    
    def injectLiveRldData(self, to, country, dbwrite=True):
        r = RLDFetch()
        df_result = pd.DataFrame()
        df_ens = pd.DataFrame()
        df_op = pd.DataFrame()
        to = to.date()
        history_update = self._getHistoryUpdateDate(
            r, r._path + FTP_ENUM['wind']['hist_ens'].format_map({'year': to.year}))

        for pred_type in ['ens', 'op']:

            for fund in [*FTP_ENUM]:
                column_name = fund + '_' + pred_type
                df_current = pd.DataFrame()
                for date in pd.date_range(history_update, to, freq='D'):
                    date = date.date()
                    print("Loading data for date", date)
                    path = r._path + FTP_ENUM[fund][f"live_{pred_type}"].format_map({'date': date})
                    df_temp = r.hist_to_dataframe(path)
                    df_temp.rename(columns={'value': column_name}, inplace=True)
                    # df_temp = df_temp[df_temp['forecast_date'].dt.date == date]
                    df_current = pd.concat([df_current, df_temp]) 

                if pred_type == 'ens':
                    if df_ens.empty:
                        df_ens = df_current
                        df_ens['merge_key'] = df_ens.groupby(['forecast_date', 'value_date']).cumcount()
                    else:
                        df_current['merge_key'] = df_current.groupby(['forecast_date', 'value_date']).cumcount()
                        df_ens = pd.merge(df_ens, df_current, on=['forecast_date', 'value_date', 'merge_key'], how='outer')
                else:
                    if df_op.empty:
                        df_op = df_current
                        df_op['merge_key'] = df_op.groupby(['forecast_date', 'value_date']).cumcount()
                    else:
                        df_current['merge_key'] = df_current.groupby(['forecast_date', 'value_date']).cumcount()
                        df_op = pd.merge(df_op, df_current, on=['forecast_date', 'value_date', 'merge_key'], how='outer')
        
        
        df_result = pd.merge(df_ens, df_op, on=['forecast_date', 'value_date', 'merge_key'], how='outer')
        # Filter out rows where mergekey is not equal to 0
        df_result = df_result[df_result['merge_key'] == 0]
        # Drop the merge_key if it's no longer needed
        df_result = df_result.drop(columns='merge_key')
        if dbwrite:
            return df_result.to_sql(name="stage_" + country, schema='residual', con=self.db.connection_string, if_exists='replace', index=False)
        else:
            return df_result

    def history_live_merge(self, from_: dt, to_: dt, country='de'):
        r = RLDFetch()
        history_update = self._getHistoryUpdateDate(
            r, r._path + FTP_ENUM['wind']['hist_ens'].format_map({'year': to_.year}))
        now_date = dt.datetime.now().date()
        if from_.date() >= history_update:
            return self.injectLiveRldData(to=to_, country=country, dbwrite=False).sort_values(['forecast_date', 'value_date'])
        elif to_.date() <= history_update:
            df = self.injectHistoryRldData(country=country, _from=from_.year, _to=to_.year, twoweeks=False, dbwrite=False)
            df_result = df.loc[(df['forecast_date'] < to_ + dt.timedelta(days=1)) &
                               (df['forecast_date'] >= from_)]
            return df_result.sort_values(['forecast_date', 'value_date'])
        else:
            df_a = self.injectHistoryRldData(country=country, _from=from_.year, twoweeks=False, dbwrite=False)
            df_b = self.injectLiveRldData(to=to_, country=country, dbwrite=False)
            # Identifying overlapping rows
            overlapping = df_a.merge(df_b, on=['forecast_date', 'value_date'])
            
            # Removing overlapping rows from df_a
            df_a_filtered = df_a[~df_a.isin(overlapping)]

            # Concatenating df_b (new data) with the remaining rows of df_a (old data)
            df_result = pd.concat([df_b, df_a_filtered])
            return df_result.sort_values(['forecast_date', 'value_date']).drop_duplicates(['forecast_date','value_date'])

    def injectHistoryNormalData(self, country, _from=2023, _to=dt.datetime.now().year):
        # check if _from and _to are datetime objects
        if not isinstance(_to, int):
            print("Error: _to must be an integer")
            return None
        if not isinstance(_from, int):
            print("Error: _from must be an integer")
            return None
        
        r = RLDFetch()
        df_result = pd.DataFrame()

        for fund in [*FTP_ENUM]:
            df_current = pd.DataFrame()
            for y in range(_from, _to+1):
                path = r._path + FTP_ENUM[fund][f"normal"].format_map({'year': y})
                df_temp = r.hist_to_dataframe(path)[['value_date', 'value']]
                df_temp.rename(columns={'value': fund.lower()}, inplace=True)

                if dt.datetime.now().year == y:
                    df_temp = df_temp.loc[df_temp['value_date'].dt.year <= _to]
                    df_current = pd.concat([df_current, df_temp])
                    break
                df_current = pd.concat([df_current, df_temp])

            if df_result.empty:
                df_result = df_current       
            else:    
                df_result = pd.merge(df_result, df_current,
                                        how='outer', on=['value_date'])
        return df_result.to_sql(name="stage_" + country, schema='normals', con=self.db.connection_string, if_exists='replace', index=False)
    
    def selectHistoryRldData(self, _from: dt.datetime,
                             _to: dt.datetime, hour: int):
        # check if _from and _to are datetime objects
        if not isinstance(_to, dt.datetime):
            print("Error: _to must be a datetime object")
            return None
        if not isinstance(_from, dt.datetime):
            print("Error: _from must be a datetime object")
            return None
        
        stmt = f"""
        SELECT forecast_date,value_date, dem_ens, wind_ens, solar_ens
        FROM residual
        WHERE forecast_date >= '{_from}' AND forecast_date <= '{_to}'
        AND EXTRACT(HOUR FROM forecast_date) = {hour};
        """
        df = self.db.execute(stmt)
        pd.read_sql_table
        return df.sort_values(['forecast_date', 'value_date'])
    
    @staticmethod
    def _getResidual(df, currentDate: dt.datetime, delta=1):
        dayahead = (currentDate + dt.timedelta(days=1)).date()
        l = df.loc[df['forecast_date'] == currentDate]
        if delta > 1:
            dfm = l.loc[[(x.date() >= dayahead) & (
                x.date() <= dayahead + dt.timedelta(days=delta))
                         for x in l['value_date']]]
        else:
            dfm = l.loc[[x.date() == dayahead for x in l['value_date']]]
        dfm = dfm.assign(res_ens = dfm['dem_ens'] - (dfm['wind_ens'] + dfm['solar_ens']).fillna(0))

        return dfm.set_index('value_date')['res_ens']

    def createRLDVector(self, _from, _to, hours=0, delta_h=7, delta_f=7):
        """
        Gives a vector of residual forecast and day ahead prediction for a given time period.
        Example:
            import RLDDatabaseData as rldd
            s = rldd.createRLDVector(_from=datetime, _to=datetime, hours=0, forecast=7)
        """
        df = self.selectHistoryRldData(_from, _to, hours)
        df_result = pd.DataFrame(columns=['forecast_date', 'mean','values'])
        def calc_cycle(df, curr_date, delta_h, delta_f):
            result = []
            date_range = df['forecast_date'].drop_duplicates()
            date_range = date_range.loc[(date_range <= curr_date) &
                                         (date_range >= curr_date - dt.timedelta(days=delta_h))]
            for unique_date in date_range:
                if unique_date < curr_date:
                    values = self._getResidual(df, unique_date)
                else:
                    values = self._getResidual(df, unique_date, delta_f)
                result.append(values)
            return pd.concat(result)
            
        for f_date in df['forecast_date'].drop_duplicates():
            series = calc_cycle(df, f_date, delta_h, delta_f)
            df_result = pd.concat([df_result, pd.DataFrame({'forecast_date': [f_date],
                                                             'mean': [series.mean()],
                                                             'values':[series.to_list()]})])
        return df_result
    
    def getResDayAhead(self, _from, _to):
        def getResidual(df, currentDate: dt.datetime):
            l = df.loc[df['forecast_date'] == currentDate]
            dfm = l.loc[[x.date() == date_dayahead(currentDate).date()
                        for x in l['value_date']]]
            dfm = dfm.assign(res_ens = dfm['dem_ens'] - (dfm['wind_ens'] + dfm['solar_ens']).fillna(0))
            return dfm.set_index('value_date')['res_ens']
        
        df = self.selectHistoryRldData(_from, _to, 0)
        df_result = pd.DataFrame(columns=['forecast_date', 'mean','values'])
        def calc_cycle(df, curr_date):
            result = []
            values = getResidual(df, curr_date)
            result.append(values)
            return pd.concat(result)
            
        for f_date in df['forecast_date'].drop_duplicates():
            series = calc_cycle(df, f_date)
            df_result = pd.concat([df_result, pd.DataFrame({'forecast_date': [f_date],
                                                             'mean': [series.mean()],
                                                             'values':[series.to_list()]})])
        return df_result.set_index('forecast_date')
    
    def getResWeekAhead(self, _from, _to, type='ens'):
        types = {'ens': 0, 'ens-6': 6, 'ens-12': 12, 'op': 0, 'ens-24': 24}
        def getResidual(df, currentDate: dt.datetime):
            l = df.loc[df['forecast_date'] == currentDate - dt.timedelta(hours=types[type])]
            dfm = l.loc[[(x.date() >= date_weekahead(currentDate).date()) & (
                x.date() <= date_weekahead(currentDate).date() + dt.timedelta(days=6))
                        for x in l['value_date']]]
            dfm = dfm.assign(res_ens = dfm['dem_ens'] - (dfm['wind_ens'] + dfm['solar_ens']).fillna(0))
            return dfm.set_index('value_date')['res_ens']
        
        def getData(_from, _to):
            stmt = f"""
            SELECT *
            FROM residual
            WHERE forecast_date >= '{_from - dt.timedelta(days=1)}' AND forecast_date <= '{_to}';
            """
            df = self.db.execute(stmt)
            return df.sort_values(['forecast_date', 'value_date'])
        
        df = getData(_from, _to)
        df_result = pd.DataFrame(columns=['forecast_date', 'mean','values'])
        def calc_cycle(df, curr_date):
            result = []
            values = getResidual(df, curr_date)
            result.append(values)
            return pd.concat(result)
            
        for f_date in df.loc[(df['forecast_date']>=_from) & (
            df['forecast_date'].dt.hour == 0)]['forecast_date'].drop_duplicates():
            series = calc_cycle(df, f_date)
            df_result = pd.concat([df_result, pd.DataFrame({'forecast_date': [f_date],
                                                             'mean': [series.mean()],
                                                             'values':[series.to_list()]})])
        return df_result.set_index('forecast_date')

    def getResAtMoment(self, _from, _to, hour=8,
                        minute=0):
        def getData(_from, _to):
            stmt = f"""
            SELECT *
            FROM residual
            WHERE forecast_date >= '{_from - dt.timedelta(days=1)}' AND forecast_date <= '{_to}';
            """
            df = self.db.execute(stmt)
            return df.sort_values(['forecast_date', 'value_date'])
        
        df = getData(_from, _to)
        map = self.residual_update_mappings_history(4, hour, minute)
        df_result = pd.DataFrame(columns=['forecast_date', 'mean','values'])
        
        def extractValues(df, forecastDate, map):
            df_res = pd.DataFrame(columns=['value_date', 'res_value'])
            for i,type in enumerate(map):
                if type == 'ens':
                    delta = 0
                elif type == 'ens-6':
                    delta = 6
                elif type == 'ens-12':
                    delta = 12
                elif type == 'op':
                    delta = 0
                ins = type.split('-')[0]
                temp = df.loc[df['forecast_date'] == forecastDate - dt.timedelta(hours=delta),
                                ['value_date', f"dem_{ins}",
                                  f"wind_{ins}", f"solar_{ins}"]]
                temp = temp.loc[temp['value_date'].dt.date == (forecastDate + dt.timedelta(days=i)).date()]
                df_res = pd.concat([df_res, temp.assign(res_value = temp[f"dem_{ins}"] - (
                    temp[f"wind_{ins}"] + temp[f"solar_{ins}"]).fillna(0))])
 
            return df_res.set_index('value_date')['res_value']
        

        def calc_cycle(df, curr_date):
            result = []
            values = extractValues(df, curr_date, map)
            result.append(values)
            return pd.concat(result)
        
        for f_date in df.loc[(df['forecast_date']>=_from) & (
            df['forecast_date'].dt.hour == 0)]['forecast_date'].drop_duplicates():
            series = calc_cycle(df, f_date)
            df_result = pd.concat([df_result, pd.DataFrame({'forecast_date': [f_date],
                                                             'mean': [series.mean()],
                                                             'values':[series.to_list()]})])
        return df_result.set_index('forecast_date')
    
    def getResNormals(self, _from, _to):
        stmt = f"""
        SELECT *
        FROM normals
        WHERE value_date >= '{_from}' AND value_date <= '{_to}';
        """
        df = self.db.execute(stmt)
        df = df.assign(res = df['con'] - (df['wind'] + df['solar']).fillna(0))
        return df.set_index('value_date')[['res']]
