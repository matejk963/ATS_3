# -*- coding: utf-8 -*-
"""
Created on Thu May  2 10:04:33 2024

@author: scasny
"""

import pandas as pd
import numpy as np
import datetime as dt
from io import BytesIO
from ftplib import FTP
from Database.DB_reader import Database
import re
import json
from Common.config_load import get_config_path as CONFIG_PATH

import xml.etree.ElementTree as ET
import requests

from Enums import GRID_TO_ENTSO_ZONE as GtEZ
from Enums import ENTSO_ZONE_TO_GRID as EZtG
from Enums import CHECK_LIST as check_list
from Enums import normal_codes

PATH = CONFIG_PATH()
with open(PATH, 'r') as file:
    config_entso = json.load(file)['EntsoE']
with open(PATH, 'r') as file:
    config_pc = json.load(file)['PointConnectFTP']

def filter_files_by_year(file_list, years):
    # Ensure years is a list of strings, even if a single year or list of integers is provided
    if isinstance(years, int):
        years = [str(years)]
    else:
        years = [str(year) for year in years]
    
    # Filter the list by checking if any year string is in the filename
    filtered_files = [file for file in file_list if any(year in file for year in years)]
    return filtered_files

def filter_files(db, from_, file_names: dict, fund, grid, hour:str='00'):
    # select from table
    schema_name = f"FUND_{fund}"
    if 'normal' in fund:
        table_name = f"{grid}"
        sql_query = f"""
        SELECT MAX(value_date) AS latest_date
        FROM "{schema_name}"."{table_name}";
        """
    else:
        table_name = f"{grid}_{hour}"
        sql_query = f"""
        SELECT MAX(forecast_date) AS latest_date
        FROM "{schema_name}"."{table_name}";
        """
    today = from_
    
    try:
        a = db.execute(sql_query)
        last_date = a.iloc[0].dt.date.values[0]
    except Exception as e:
        print(e, "Empty database")
        last_date = dt.datetime(2019,1,1).date()

    
    
    if ('normal' not in fund) and (fund.lower() not in ['ltinstcap']):
        if fund.lower() not in ['ao', 'nao', 'ao_syn', 'nao_syn']:
            files_list = [x for x in file_names['live'] if fund.split('_')[0] in x and grid in x]
        else:
            files_list = [x for x in file_names['live'] if fund.split('_')[0] in x]
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')
    
        # Extract dates using list comprehension
        live_dates = [dt.datetime.strptime(date_pattern.search(filename).group(), "%Y-%m-%d").date()
                      for filename in files_list]
        live_strings = [x.strftime("%Y-%m-%d") for x in live_dates if x > last_date]
        if not live_dates:
            return [], live_strings
        hist_strings = [str(x) for x in range(last_date.year, today.year+1) if last_date < live_dates[0]]
    else:
        live_strings = []
        hist_strings = [str(x) for x in range(last_date.year, today.year+1)]
    return hist_strings, live_strings
    
    
    
    # compare with live
    # if gap then replace with hist
   
country_code_to_short = {'DEU': 'de',
                         'FRA': 'fr'}


    
#capacity types curve codes dictionary
CUR_CODES = {'DEU':{'Coal': 105269300,
                   'Lig': 105269303,
                   'Gas': 105663406,
                   'Pump': 111205650,
                   'RoR': 111205652,
                   'Res': 111205651,
                   'Nuc': 105269302,
                   'Oil': 106819498},
            'FRA': {'Coal': 106336320,
                  'Gas': 106336321,
                  'Hydro Res': 106336323,
                  'Hydro RoR': 106336324,
                  'Nuc': 106336319,
                  'Oil': 106336325,
                  'Pump': 106336322}}

INST_CODES ={
        'DEU':{
                'Coal': '112045851',
                'Gas': '111990521',
                'Lig': '111990426',
                'Nuc': '112058279',
                'Pump': '112045801',
                'Res': '112045849',
                'RoR': '112045847',
                'Oil': '112058278'
            },
        'FRA': {
                'Coal': '112045848',
                'Gas': '112045827',
                'Nuc': '112052134',
                'Oil': '112057969',
                'Pump': '111990427',
                'Hydro Res': '111990441',
                'Hydro RoR': '112058277'
            }
        }

LT_INST_CODES = {
    'DEU': {
        'Coal': 128403170,
        'Lig': 128403183,
        'Gas': 128403179,
        'Nuc': 128403182
        },
    'FRA': {
        'Nuc': 128403205,
        'Gas': 128403206,
        'Coal': 128403204,
        'Oil': 128403219
        }
    }

MID_PERC_CODES = {
        '10th': {
            'FRA': 104891550,
            'DEU': 104707264,
            'NLD': 110768598,
            'BEL': 104891382,
            'ESP': 104788408
            },
        '25th': {
            'FRA': 104891547,
            'DEU': 104707288,
            'NLD': 110768631,
            'BEL': 104891379,
            'ESP': 104788503
            },
        '75th': {
            'FRA': 104891541,
            'DEU': 104707172,
            'NLD': 110768611,
            'BEL': 104891373,
            'ESP': 104788453
            },
        '90th': {
            'FRA': 104891538,
            'DEU': 104707307,
            'NLD': 110768584,
            'BEL': 104891370,
            'ESP': 104788544
            }
    }


for country, plants in INST_CODES.items():
    INST_CODES[country] = {k: int(v) for k, v in plants.items()}

#CUR_CODES_de = dict((v,k) for k,v in CUR_CODES['DE'].items())
#CUR_CODES_fr = dict((v,k) for k,v in CUR_CODES['FR'].items())


def av_cap_processing(db, ftp, from_,
                      sel_files,
                      CUR_CODES_grid,
                      hour,
                      grid):
    hour = int(hour)
    cap_df = pd.DataFrame()
    for file in sel_files:
        print("processing file:", file)
        #if iteration%5 == 0:

                                   
        flo = BytesIO()
        ftp.retrbinary('RETR ' + file,flo.write)

        flo.seek(0)
        temp1 = pd.read_csv(flo, sep='|', low_memory=False).reset_index()

        # Your existing code setup
        temp1.columns = temp1.loc[0]
        temp1 = temp1.iloc[1:].copy()
        temp1['Id'] = [CUR_CODES_grid[int(a)] if int(a) in CUR_CODES_grid.keys()
                       else None for a in temp1['Id']]
        temp1 = temp1.loc[temp1['Id']!=None].copy()
        temp1['forecast_date'] = pd.to_datetime(temp1['ForecastDate'], dayfirst=True)
        temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True)
        temp1['Value'] = temp1['Value'].astype(float)
        
        # Convert UTC to Europe/Berlin and then remove timezone information
        temp1['forecast_date'] = pd.to_datetime(temp1['forecast_date'], utc=True).dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
        temp1['value_date'] = pd.to_datetime(temp1['value_date'], utc=True).dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
        
        # Continue processing
        temp1 = pd.pivot_table(data=temp1, columns='Id', index=['forecast_date', 'value_date'], values='Value').copy()
        temp1 = temp1.reset_index()
        
        # Ensure datetime objects are in local time (Europe/Berlin) without timezone info
        temp1['forecast_date'] = pd.to_datetime(temp1['forecast_date'], dayfirst=True)
        temp1['value_date'] = pd.to_datetime(temp1['value_date'], dayfirst=True)
        
        temp1['date'] = pd.to_datetime(temp1['value_date'].dt.date)
        temp1['hour'] = temp1['value_date'].dt.hour
        temp1['f_date'] = pd.to_datetime(temp1['forecast_date'].dt.date)
        temp1['f_hour'] = temp1['forecast_date'].dt.hour
        
        temp1 = temp1.sort_values(['value_date', 'forecast_date']).copy()
        temp1 = temp1.ffill().copy()
        
        
        
        for f_date in temp1['f_date'].drop_duplicates():
            if 'Cap_M1_Steam' in file:
                idx = temp1.groupby('f_date')['forecast_date'].idxmin()
                temp2 = temp1.loc[temp1['forecast_date'].isin(temp1['forecast_date'].loc[idx])]
                temp2 = temp2.sort_values(['forecast_date', 'value_date']).copy()
            else:
                temp2 = temp1.loc[((temp1['f_date']==f_date)&
                  (temp1['f_hour']<=hour))].copy()
                temp2 = temp2.loc[temp2['forecast_date']==temp2['forecast_date'].max()]
            if cap_df.empty:                
                cap_df = temp2.copy()
            else:
                # temp2 = temp1.loc[((temp1['f_date']==f_date)&
                #   (temp1['f_hour']<=hour))].copy()
                # temp2 = temp2.loc[temp2['forecast_date']==temp2['forecast_date'].max()]
                cap_df = pd.concat([cap_df,temp2])
                
    if len(sel_files)==0:
        print("No update needed")
        return 0
    # cap_df = cap_df.loc[cap_df['date']>=cap_df['f_date']].copy()
    cap_df = cap_df.sort_values(['value_date']).ffill().reset_index(drop=True).copy()
    max_fcst_date = cap_df.groupby('f_date')['forecast_date'].max()
    cap_df = cap_df[cap_df['forecast_date'].isin(max_fcst_date)].copy()
    cap_df = cap_df.drop(['date', 'hour', 'f_date', 'f_hour'],axis=1)
    cap_df = cap_df.sort_values(['forecast_date', 'value_date'])
    cap_df = cap_df.drop_duplicates(['forecast_date', 'value_date'])  
    cap_df.columns = [a + '_' + country_code_to_short[grid]
                      if a not in ['forecast_date', 'value_date']
                      else a
                      for a in cap_df.columns]
        
    return cap_df

def mid_fund_processing(sel_files, folder_name,
                       ftp, fund, grid, hour):
    ec_type = int(hour)
    split_fund = fund.split('_')
    ens = pd.DataFrame()
    if len(sel_files)==0:
        print("No update needed")
        return 0
    for file in sel_files:

        # file_dir = folder_name + file
        flo = BytesIO()
        ftp.retrbinary('RETR ' + file,flo.write)

        flo.seek(0)
        temp1 = pd.read_csv(flo, sep='|').reset_index()
        temp1.columns = temp1.loc[0]
        temp1 = temp1.iloc[1:].copy()
        temp1['forecast_date'] = pd.to_datetime(temp1['ForecastDate'], dayfirst=True)
        if not any(a in fund.lower() for a in ['inf']):
            temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True, utc=True)
            temp1['value_date'] = temp1['value_date'].dt.tz_convert('Europe/Berlin')
            temp1['value_date'] = temp1['value_date'].dt.tz_localize(None)
        else:
            temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True)
        if fund.split('_')[0] in ['ResidualDemand']:
            fund_name='rld'
        elif 'mnd' in fund:
            fund_name = fund.split('_')[0]
        else:
            fund_name = fund
        temp1[fund_name] = temp1['Value'].astype(float)
        temp1['hour'] = temp1['forecast_date'].dt.hour
        temp1['Id'] = temp1['Id'].astype(int)
        # Loop made just for one ec_type
        if 'mnd' in fund:
            if grid == 'NLD' and split_fund[0] == 'Wind':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==110764885))].copy()
            elif grid == 'DEU' and split_fund[0] == 'Wind':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==112476247))].copy()
            elif grid == 'DEU' and split_fund[0] == 'Solar':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==110251483))].copy()
            elif grid == 'ESP' and split_fund[0] == 'Solar':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==110252391))].copy()
            else:
                temp = temp1.loc[temp1['hour']==ec_type].copy()

        else:
            if grid == 'ITA' and fund == 'CON':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==112095370))].copy()
            elif grid == 'DEU' and fund == 'Wind':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==101658339))].copy()
            elif grid == 'ESP' and fund == 'Solar':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==104550167))].copy()
            elif grid == 'FRA' and fund == 'INF':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==124767))].copy()
            elif grid == 'AUT' and fund == 'INF':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==101609318))].copy()
            elif fund == 'NAO':
                temp = temp1.loc[((temp1['Id']==117469253))].copy()
            elif fund == 'AO':
                temp = temp1.loc[((temp1['Id']==117500737))].copy()
            elif fund.split('_')[0] in ['ResidualDemand'] and any(f"{a}th" in fund for a in [10, 25, 75, 90]):
                id_out = MID_PERC_CODES[fund.split('_')[1]][grid]
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==id_out))].copy()
            else:
                temp = temp1.loc[temp1['hour']==ec_type].copy()



        if ens.empty:
            ens = temp[['forecast_date', 'value_date',
                                       fund_name]].copy()
        else:
            ens = pd.concat([ens,temp[['forecast_date', 'value_date',
                                       fund_name]]], ignore_index=True)
    ens = ens.drop_duplicates(['forecast_date', 'value_date']).copy()
                    
    return ens

def normal_fund_processing(sel_files, folder_name,
                       ftp, fund, grid):
    split_fund = fund.split('_')
    ens = pd.DataFrame()
    if len(sel_files)==0:
        print("No update needed")
        return 0
    for file in sel_files:

        # file_dir = folder_name + file
        flo = BytesIO()
        ftp.retrbinary('RETR ' + file,flo.write)

        flo.seek(0)
        temp1 = pd.read_csv(flo, sep='|').reset_index()
        temp1.columns = temp1.loc[0]
        temp1 = temp1.iloc[1:].copy()
        if not any(a in fund.lower() for a in ['inf']):
            temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True, utc=True)
            temp1['value_date'] = temp1['value_date'].dt.tz_convert('Europe/Berlin')
            temp1['value_date'] = temp1['value_date'].dt.tz_localize(None)
        else:
            temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True)
        if fund in ['ResidualDemand']:
            fund_name='rld'
        else:
            fund_name = split_fund[0]
        temp1[fund_name] = temp1['Value'].astype(float)
        temp1['Id'] = temp1['Id'].astype(int)
        temp = temp1.loc[(temp1['Id']==normal_codes[grid][fund.split('_')[0]])].copy()
        # if grid == 'FRA' and fund.split('_')[0].lower() == 'inf':
        #     temp = temp1.loc[((temp1['Id']==125191))].copy()
        if grid == 'ESP' and fund == 'Wind_normal':
            temp = temp1.loc[(temp1['Id']==115102754)].copy()
        elif grid == 'ESP' and fund == 'CON_normal':
            temp = temp1.loc[(temp1['Id']==116249383)]
        # else:
        #     temp = temp1.loc[temp1['hour']==ec_type].copy()



        if ens.empty:
            ens = temp[['value_date',
                                       fund_name]].copy()
        else:
            ens = pd.concat([ens,temp[['value_date',
                                       fund_name]]], ignore_index=True)
    ens = ens.drop_duplicates(['value_date']).copy()
                    
    return ens
    

        


def fetch_fund_ftp(from_=dt.datetime.now().date(),
                   fund_list: list = ['AvailCap'],
                   grid_list: list = ['DEU', 'FRA'],
                   hour:str = '12'):
    
    #connect to ftp folder
    db = Database()
    ftp = FTP(host='pointconnect.commodities.refinitiv.com')
    ftp.login(user=config_pc['USERNAME'],
             passwd=config_pc['PASSWORD'])
    ftp.encoding = 'utf-8'
    supply_folder_name, demand_folder_name, normal_folder_name = {}, {}, {}
    hydro_folder_name, normal_hydro_folder_name, weather_folder_name = {}, {}, {}
    normal_weather_folder_name, oscilations_folder_name, eur_power_folder_name = {}, {}, {}
    supply_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/'
    demand_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Demand/'
    hydro_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Hydrology/'
    weather_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Weather/Temp/Forecast/'
    oscilations_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Weather/'
    eur_power_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/'
    #first sort supply fundamentals
    supply_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
    demand_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Demand/'
    normal_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Normals/'
    hydro_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Hydrology/'
    normal_hydro_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Hydrology/Normals/'
    weather_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Weather/Temp/Forecast/'
    normal_weather_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Weather/Temp/Timeseries/'
    oscilations_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Weather/'
    eur_power_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/'
    
    
    supply_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + supply_folder_name['hist'], supply_file_names['hist'].append)
    ftp.retrlines('NLST ' + supply_folder_name['live'], supply_file_names['live'].append)
    demand_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + demand_folder_name['hist'], demand_file_names['hist'].append)
    ftp.retrlines('NLST ' + demand_folder_name['live'], demand_file_names['live'].append)
    normal_file_names = {'hist': []}
    ftp.retrlines('NLST ' + normal_folder_name['hist'], normal_file_names['hist'].append)
    hydro_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + hydro_folder_name['hist'], hydro_file_names['hist'].append)
    ftp.retrlines('NLST ' + hydro_folder_name['live'], hydro_file_names['live'].append)
    normal_hydro_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + normal_hydro_folder_name['hist'], normal_hydro_file_names['hist'].append)
    weather_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + weather_folder_name['hist'], weather_file_names['hist'].append)
    ftp.retrlines('NLST ' + weather_folder_name['live'], weather_file_names['live'].append)
    normal_weather_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + normal_weather_folder_name['hist'], normal_weather_file_names['hist'].append)
    oscilations_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + oscilations_folder_name['hist'], oscilations_file_names['hist'].append)
    ftp.retrlines('NLST ' + oscilations_folder_name['live'], oscilations_file_names['live'].append)
    eur_power_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + eur_power_folder_name['hist'], eur_power_file_names['hist'].append)
    ftp.retrlines('NLST ' + eur_power_folder_name['live'], eur_power_file_names['live'].append)

    
    result_dict = {k: "Success" for k in [f"{x}_{y}" for x in fund_list for y in grid_list]}
    
    
    for fund in fund_list:
        if 'normal' in fund:
            hour=''
        for grid in grid_list:
            if fund.lower() in ['availcap']:
                CUR_CODES_grid = dict((v,k) for k,v in CUR_CODES[grid].items())
            elif fund.lower() in ['instcap']:
                CUR_CODES_grid = dict((v,k) for k,v in INST_CODES[grid].items())
            elif fund.lower() in ['ltinstcap']:
                CUR_CODES_grid = dict((v,k) for k,v in LT_INST_CODES[grid].items())
            # sel_files = filter_files(fund, grid, hour)
            file_names = {}
            split_fund = fund.split('_')
            if ('mnd' in fund) and ('temp' not in fund.lower()):
                
                if split_fund[0] in ['Wind', 'Solar', 'AvailCap']:
                    if (grid.lower() not in ['aut']) and (split_fund[0] not in ['Solar']):
                        file_names['hist'] = [k for k in supply_file_names['hist']
                                              if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                        file_names['live'] = [k for k in supply_file_names['live']
                                              if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    else:
                        file_names['hist'] = [k for k in supply_file_names['hist']
                                              if (split_fund[0] in k) and (grid in k)]
                        file_names['live'] = [k for k in supply_file_names['live']
                                              if (split_fund[0] in k) and (grid in k)]
                    folder_name = supply_folder_name
                elif split_fund[0] in ['ResidualDemand', 'CON']:
                    file_names['hist'] = [k for k in demand_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    file_names['live'] = [k for k in demand_file_names['live']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    folder_name = demand_folder_name
            elif fund.lower() in ['inf', 'inf_normal']:
                if 'normal' not in fund:
                    file_names['hist'] = [k for k in hydro_file_names['hist']
                                          if (split_fund[0] in k) and
                                          (grid in k) and
                                          ('_Hyd_' in k) and
                                          ('_AVG_' in k)]
                    file_names['live'] = [k for k in hydro_file_names['live']
                                          if (split_fund[0] in k) and
                                          (grid in k) and
                                          ('_Hyd_' in k) and
                                          ('_AVG_' in k)]
                    folder_name = hydro_folder_name
                else:
                    file_names['hist'] = [k for k in normal_hydro_file_names['hist']
                                          if (split_fund[0] in k) and
                                          (grid in k) and
                                          ('_Hyd_' in k) and
                                          ('_N_A_' in k)]
                    folder_name = normal_hydro_folder_name
            elif fund.lower() in ['temp', 'temp_normal', 'temp_mnd']:
                if 'normal' not in fund:
                    if 'mnd' not in fund.lower():
                        file_names['hist'] = [k for k in weather_file_names['hist']
                                              if (split_fund[0] in k) and
                                              (grid in k) and
                                              ('_Temp_' in k) and
                                              ('_AVG_' in k)]
                        file_names['live'] = [k for k in weather_file_names['live']
                                              if (split_fund[0] in k) and
                                              (grid in k) and
                                              ('_Temp_' in k) and
                                              ('_AVG_' in k)]
                        folder_name = weather_folder_name
                    else:
                        file_names['hist'] = [k for k in weather_file_names['hist']
                                              if (split_fund[0] in k) and
                                              (grid in k) and
                                              ('_Temp_' in k) and
                                              ('_AVG_' in k) and
                                              ('ECMND' in k)]
                        file_names['live'] = [k for k in weather_file_names['live']
                                              if (split_fund[0] in k) and
                                              (grid in k) and
                                              ('_Temp_' in k) and
                                              ('_AVG_' in k) and
                                              ('ECMND' in k)]
                        folder_name = weather_folder_name
                else:
                    file_names['hist'] = [k for k in normal_weather_file_names['hist']
                                          if (split_fund[0] in k) and
                                          (grid in k) and
                                          ('_Temp_' in k) and
                                          ('_N_A_' in k)]
                    folder_name = normal_weather_folder_name
                    
            elif fund.lower() in ['ao', 'nao', 'ao_syn', 'nao_syn']:
                
                if fund.lower() in ['nao', 'nao_syn']:
                    fund_name = '_NAO'
                else:
                    fund_name = ''
                
                file_names['hist'] = [k for k in oscilations_file_names['hist']
                                      if (('_Index' + fund_name + '_WOR') in k) and
                                      ('-N_A' in k)]
                file_names['live'] = [k for k in oscilations_file_names['live']
                                      if ('_Index' + fund_name + '_' in k) and
                                      ('-N_A' in k)]
                folder_name = oscilations_folder_name
            elif 'normal' in fund:
                if grid in ['ROU'] and ('CON' in fund):
                    file_names['hist'] = [k for k in demand_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k)
                                          and ('_A_' in k) and ('ens' not in k)]
                    file_names['live'] = []
                    folder_name = demand_folder_name
                elif grid in ['ROU'] and (split_fund[0] in ['Wind', 'Solar']):
                    file_names['hist'] = [k for k in supply_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k) and ('_N_' in k)]
                    file_names['live'] = []
                    folder_name = supply_folder_name

                else:
                    file_names['hist'] = [k for k in normal_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k) and ('_N_' in k)]
                    file_names['live'] = []
                    folder_name = normal_folder_name
            elif any(percentile in fund.lower()
                     for percentile in ['10th', '25th', '75th', '90th']):
                if split_fund[0] in ['ResidualDemand']:
                    if grid in ['DEU']:
                        file_names['hist'] = [k for k in eur_power_file_names['hist'] if (split_fund[0] in k) and (grid in k)]
                        file_names['live'] = [k for k in eur_power_file_names['live'] if (split_fund[0] in k) and (grid in k)]
                        folder_name = eur_power_folder_name
                    elif grid in ['ESP']:
                        file_names['hist'] = [k for k in demand_file_names['hist'] if
                                              (split_fund[0] in k) and (grid in k) and ('_avg_' not in k.lower())]
                        file_names['live'] = [k for k in demand_file_names['live'] if
                                              (split_fund[0] in k) and (grid in k) and ('_avg_' not in k.lower())]
                        folder_name = demand_folder_name
                    else:
                        file_names['hist'] = [k for k in demand_file_names['hist'] if
                                              (split_fund[0] in k) and (grid in k) and ('_perc_' in k.lower())]
                        file_names['live'] = [k for k in demand_file_names['live'] if
                                              (split_fund[0] in k) and (grid in k) and ('_perc_' in k.lower())]
                        folder_name = demand_folder_name
                    
            else:
                if split_fund[0] in ['Wind', 'Solar', 'AvailCap', 'InstCap']:
                    if grid.lower() not in ['aut']:
                        file_names['hist'] = [k for k in supply_file_names['hist'] if (fund in k) and (grid in k)]
                        file_names['live'] = [k for k in supply_file_names['live'] if (fund in k) and (grid in k)]
                    else:
                        file_names['hist'] = [k for k in supply_file_names['hist'] if (fund in k)
                                              and (grid in k) and ('ECens' in k)]
                        file_names['live'] = [k for k in supply_file_names['live'] if (fund in k)
                                              and (grid in k) and ('ECens' in k)]
                    folder_name = supply_folder_name
                elif split_fund[0] in ['LtInstCap']:
                    file_names['hist'] = [k for k in eur_power_file_names['hist'] if 'Cap_M1_Steam_EUR' in k]
                    folder_name = eur_power_folder_name
                elif split_fund[0] in ['ResidualDemand', 'CON']:
                    file_names['hist'] = [k for k in demand_file_names['hist'] if (fund in k) and (grid in k)]
                    file_names['live'] = [k for k in demand_file_names['live'] if (fund in k) and (grid in k)]
                    folder_name = demand_folder_name
            if len(file_names['hist']) == 0:
                print('NO FILES FOR: ', fund, grid)
                result_dict[f"{fund}_{grid}"] = 'NO FILES'
                continue
            hist_strings, live_strings = filter_files(db, from_, file_names, fund, grid, hour)
            
            sel_files = []
            l_append = lambda files, strings, folder: [sel_files.append(folder+file)
                                               for file in files if any([s in file for s in strings])]
            # append filenames for missing dates in db
            l_append(file_names['hist'], hist_strings, folder_name['hist'])
            if ('normal' not in fund) and (fund.lower() not in ['ltinstcap']):
                l_append(file_names['live'], live_strings, folder_name['live'])
                                                                
            
            file = None

            ftp.close()
            ftp = FTP(host='pointconnect.commodities.refinitiv.com')
            ftp.login(user='krajcovic_matej@energytrading.sk',
                        passwd='kmfT5Q$kw')
            ftp.encoding = 'utf-8'
            
            if fund.lower() in ['availcap', 'instcap', 'ltinstcap']:
                df = av_cap_processing(db, ftp, from_, sel_files, CUR_CODES_grid, hour, grid)
            elif ('normal' in fund.lower()) or (grid.lower() in ['osc']):
                df = normal_fund_processing(sel_files, folder_name, ftp, fund, grid)
            elif split_fund[0].lower() in ['residualdemand', 'wind', 'solar',
                                           'con', 'inf', 'temp']:
                df = mid_fund_processing(sel_files, folder_name, ftp, fund, grid, hour)
            
            
            if not isinstance(df, int):
                if 'normal' in fund:
                    df.to_sql(name="stage_" + grid ,
                                      schema='FUND_'+fund,
                                      con=db.connection_string,
                                      if_exists='replace', index=False)
                    db.merge_from_staging_to_prod('FUND_'+fund, f"{grid}")
                else:
                    df.to_sql(name="stage_" + grid + "_" + hour,
                                      schema='FUND_'+fund,
                                      con=db.connection_string,
                                      if_exists='replace', index=False)
                    db.merge_from_staging_to_prod('FUND_'+fund, f"{grid}_{hour}")


                if df.isna().any().any():
                    result_dict[f"{fund}_{grid}"] = "MISSING DATA: Some NaN values were merged into table"
                if df.empty:
                    result_dict[f"{fund}_{grid}"] = "MISSING DATA: Empty dataframe!"
            else:
                if df == 0:
                    result_dict[f"{fund}_{grid}"] = "No update needed"
    return result_dict

                


def fetch_and_process_data(from_date, to_date):
    # Define the API endpoints and headers
    publication_api_endpoint = "https://publicationtool.jao.eu/core/api/data/maxExchanges"
    utility_api_endpoint = "https://utilitytool.jao.eu/CascUtilityWebService.asmx/GetTradingDataForAPeriod"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "86e20d1e-c0fc-406d-95b6-bc8ae625f3c0"  # Replace with your actual API key if required
    }
    
    # Define the query parameters for publication API
    publication_params = {
        "FromUtc": from_date.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        "ToUtc": to_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    }
    
    # Function to remove namespace from XML tags
    def remove_namespace(tag):
        if '}' in tag:
            return tag.split('}', 1)[1]
        else:
            return tag
    
    # Function to fetch data from the Utility Tool
    def fetch_utility_data(start_date, end_date):
        utility_params = {
            "dateFrom": start_date.strftime('%Y-%m-%d'),
            "dateTo": end_date.strftime('%Y-%m-%d'),
            "maxExchange": "true",
            "netPosition": "false",
            "ptdf": "false"
        }
        utility_response = requests.get(utility_api_endpoint, params=utility_params)
        if utility_response.status_code == 200:
            root = ET.fromstring(utility_response.content)
            namespace = {'ns': 'http://tempuri.org/'}
            
            max_exchanges = []
            for max_exchange in root.findall('.//ns:MaxExchange', namespace):
                data = {remove_namespace(child.tag): child.text for child in max_exchange}
                max_exchanges.append(data)
            
            utility_df = pd.DataFrame(max_exchanges)
            utility_df['CalendarHour'] = utility_df['CalendarHour'].astype(int) - 1
            utility_df['CalendarHour'] = utility_df['CalendarHour'].astype(str)
            utility_df['DateTime'] = pd.to_datetime(utility_df['Date'] + ' ' + utility_df['CalendarHour'].str.zfill(2) + ':00:00', errors='coerce')
            utility_df.dropna(subset=['DateTime'], inplace=True)
            utility_df['DateTime'] = utility_df['DateTime'].dt.tz_localize('UTC').dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
            utility_df.drop(columns=['Date', 'CalendarHour'], inplace=True)
            utility_df.set_index('DateTime', inplace=True)
            
            column_mapping = {col: f"border_{col.replace('Max_', '').replace('_to_', '_')}" for col in utility_df.columns}
            utility_df.rename(columns=column_mapping, inplace=True)
            utility_df = utility_df[~((utility_df.index.month == 10) & (utility_df.index.hour == 2) & (utility_df.index.duplicated(keep='last')))]
            
            return utility_df
        else:
            print(f"Utility Tool Error: {utility_response.status_code}")
            print(utility_response.text)
            return pd.DataFrame()
    
    # Define neighboring countries
    neighboring_countries = [
        'border_DE_AT', 'border_AT_DE',
        'border_DE_BE', 'border_BE_DE',
        'border_DE_CZ', 'border_CZ_DE',
        'border_DE_DK', 'border_DK_DE',
        'border_DE_FR', 'border_FR_DE',
        'border_DE_LU', 'border_LU_DE',
        'border_DE_NL', 'border_NL_DE',
        'border_DE_PL', 'border_PL_DE',
        'border_DE_CH', 'border_CH_DE',
        'border_AT_CZ', 'border_CZ_AT',
        'border_AT_HU', 'border_HU_AT',
        'border_AT_IT', 'border_IT_AT',
        'border_AT_LI', 'border_LI_AT',
        'border_AT_SK', 'border_SK_AT',
        'border_AT_SI', 'border_SI_AT',
        'border_FR_BE', 'border_BE_FR',
        'border_FR_LU', 'border_LU_FR',
        'border_FR_CH', 'border_CH_FR',
        'border_FR_IT', 'border_IT_FR',
        'border_FR_ES', 'border_ES_FR',
        'border_NL_BE', 'border_BE_NL',
        'border_CZ_SK', 'border_SK_CZ',
        'border_CZ_PL', 'border_PL_CZ',
        'border_CZ_AT', 'border_AT_CZ',
        'border_SK_HU', 'border_HU_SK',
        'border_SK_PL', 'border_PL_SK',
        'border_SK_AT', 'border_AT_SK',
        'border_HU_RO', 'border_RO_HU',
        'border_HU_SK', 'border_SK_HU',
        'border_HU_AT', 'border_AT_HU',
        'border_HU_SI', 'border_SI_HU',
        'border_HU_RS', 'border_RS_HU',
        'border_HU_UA', 'border_UA_HU',
        'border_RO_HU', 'border_HU_RO',
        'border_RO_BG', 'border_BG_RO',
        'border_RO_MD', 'border_MD_RO',
        'border_RO_UA', 'border_UA_RO',
        'border_RO_RS', 'border_RS_RO'
    ]
    
    response = requests.get(publication_api_endpoint, headers=headers, params=publication_params)
    if response.status_code == 200:
        publication_data = response.json()["data"]
        publication_df = pd.DataFrame(publication_data)
        publication_df['dateTimeUtc'] = pd.to_datetime(publication_df['dateTimeUtc']).dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
        publication_df.set_index('dateTimeUtc', inplace=True)
        
        # Select only the columns that exist in the DataFrame
        existing_columns = [col for col in neighboring_countries if col in publication_df.columns]
        publication_df = publication_df[existing_columns]
        
        

        # oldest_date = publication_df.index.min()
        # from_date = pd.to_datetime(publication_params['FromUtc']).tz_convert('Europe/Berlin').tz_localize(None)
        
        # if oldest_date > from_date:
        #     missing_period_start = from_date
        #     missing_period_end = oldest_date - pd.Timedelta(hours=1)
        #     utility_df_list = []
            
        #     while missing_period_start <= missing_period_end:
        #         chunk_end_date = min(missing_period_start + pd.DateOffset(years=1) - pd.Timedelta(days=1), missing_period_end)
        #         print(f"Fetching data from {missing_period_start} to {chunk_end_date}")
        #         utility_df = fetch_utility_data(missing_period_start, chunk_end_date)
        #         utility_df_list.append(utility_df)
        #         missing_period_start = chunk_end_date + pd.Timedelta(days=1)
            
        #     utility_df_combined = pd.concat(utility_df_list)
        #     utility_df_combined = utility_df_combined[neighboring_countries]
            
        #     combined_df = pd.concat([utility_df_combined, publication_df])
        #     combined_df.sort_index(inplace=True)
            
        #     print("Combined Data:")
        #     print(combined_df)
        #     combined_df.to_csv("jao_combined_data.csv")
        # else:
        print("No missing data to fetch. Using only Publication Tool Data.")
        return publication_df
    else:
        print(f"Publication Tool Error: {response.status_code}")
        print(response.text)
    
if __name__ == "__main__":
    from_ = dt.datetime.now().date()
    fetch_fund_ftp(from_= from_, fund_list=[f"ResidualDemand_{a}th" for a in [10,25,75,90]],
                        grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'ESP'],
                        hour='00')
    # fetch_fund_ftp(from_= from_, fund_list=['Solar_mnd', 'Wind_mnd', 'CON_mnd'],
    #                     grid_list=['ESP'],
    #                     hour='00')
    # fetch_fund_ftp(from_= from_, fund_list=['Solar', 'Wind', 'CON'],
    #                     grid_list=['ESP'],
    #                     hour='00')
    # fetch_fund_ftp(from_= from_, fund_list=['AvailCap','InstCap', 'LtInstCap'],
    #                   grid_list=['DEU', 'FRA'],
    #                   hour='12'),
    # fetch_fund_ftp(from_= from_, fund_list=['ResidualDemand'],
    #                     grid_list=['DEU', 'AUT', 'FRA', 'BEL', 'NLD', 'ESP'],
    #                     hour='00'),
    # fetch_fund_ftp(from_= from_, fund_list=['CON_normal'],
    #                     grid_list=['ESP'],
    #                     hour='00'),
    # fetch_fund_ftp(from_= from_, fund_list=['INF'],
    #               grid_list=['AUT', 'FRA'],
    #               hour='00')
    # fetch_fund_ftp(from_ = from_, fund_list=['Wind', 'Wind_mnd'],
    #                   grid_list= ['ROU', 'DEU'],
    #                 hour='00')     
    # fetch_fund_ftp(fund_list=['AvailCap', 'InstCap', 'LtInstCap'],
    #                       grid_list=['DEU', 'FRA'],
    #                       hour='12')
    # fetch_fund_ftp(from_= from_, fund_list=['Temp', 'Temp_mnd'],
    #               grid_list=['HUN', 'DEU', 'FRA'],
    #               hour='00')

    # test = fetch_fund_ftp(fund_list=['CON_mnd', 'Wind_mnd', 'Solar_mnd'],
    #                       grid_list=['DEU', 'AUT', 'FRA', 'BEL', 'NLD'],
    #                       hour='00')

    # test = fetch_fund_ftp(fund_list=['CON'],
    #                       grid_list=['DEU', 'NLD', 'BEL', 'FRA'],
    #                       hour='00')
    # test = fetch_fund_ftp(fund_list=['INF_normal'],
    #                       grid_list=['AUT', 'FRA'],
    #                       hour='00')
    # test = fetch_fund_ftp(fund_list=['NAO_syn', 'AO_syn'],
    #                       grid_list=['OSC'],
    #                       hour='00')
