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

from entsoe import EntsoePandasClient as Entsoe
from entsoe import EntsoeRawClient as Entsoe2
from entsoe.mappings import Area, NEIGHBOURS, lookup_area
from entsoe.exceptions import NoMatchingDataError

from Enums import GRID_TO_ENTSO_ZONE as GtEZ
from Enums import ENTSO_ZONE_TO_GRID as EZtG
from Enums import CHECK_LIST as check_list

PATH = r'S:\Algo\Database\configDB.json'
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
    table_name = f"{grid}_{hour}"
    sql_query = f"""
    SELECT MAX(forecast_date) AS latest_date
    FROM "{schema_name}"."{table_name}";
    """

    
    try:
        a = db.execute(sql_query)
        last_date = a.iloc[0].dt.date.values[0]
    except Exception as e:
        print(e, "Empty database")
        last_date = dt.datetime(2019,1,1).date()
    
    today = from_
    if 'normal' not in fund:
        files_list = [x for x in file_names['live'] if fund.split('_')[0] in x and grid in x]
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')
    
        # Extract dates using list comprehension
        live_dates = [dt.datetime.strptime(date_pattern.search(filename).group(), "%Y-%m-%d").date()
                      for filename in files_list]
        live_strings = [x.strftime("%Y-%m-%d") for x in live_dates if x > last_date]
        hist_strings = [str(x) for x in range(last_date.year, today.year+1) if last_date < live_dates[0]]
    else:
        live_strings = []
        hist_strings = [str(today.year)]
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
        temp1['Id'] = [CUR_CODES_grid[int(a)] for a in temp1['Id']]
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
            if cap_df.empty:
                temp2 = temp1.loc[((temp1['f_date']==f_date)&
                  (temp1['f_hour']<=hour))].copy()
                temp2 = temp2.loc[temp2['forecast_date']==temp2['forecast_date'].max()]
                cap_df = temp2.copy()
            else:
                temp2 = temp1.loc[((temp1['f_date']==f_date)&
                  (temp1['f_hour']<=hour))].copy()
                temp2 = temp2.loc[temp2['forecast_date']==temp2['forecast_date'].max()]
                cap_df = pd.concat([cap_df,temp2])
                
    if len(sel_files)==0:
        print("No update needed")
        return 0
    cap_df = cap_df.loc[cap_df['date']>=cap_df['f_date']].copy()
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
        temp1['value_date'] = pd.to_datetime(temp1['ValueDate'], dayfirst=True, utc=True)
        temp1['value_date'] = temp1['value_date'].dt.tz_convert('Europe/Berlin')
        temp1['value_date'] = temp1['value_date'].dt.tz_localize(None)
        if fund in ['ResidualDemand']:
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
            else:
                temp = temp1.loc[temp1['hour']==ec_type].copy()
        else:
            if grid == 'ITA' and fund == 'CON':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==112095370))].copy()
            elif grid == 'DEU' and fund == 'Wind':
                temp = temp1.loc[((temp1['hour']==ec_type)&(temp1['Id']==101658339))].copy()
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
    supply_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/'
    demand_folder_name['live'] = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Demand/'
    #first sort supply fundamentals
    supply_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
    demand_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Demand/'
    normal_folder_name['hist'] = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Normals/'
    
    supply_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + supply_folder_name['hist'], supply_file_names['hist'].append)
    ftp.retrlines('NLST ' + supply_folder_name['live'], supply_file_names['live'].append)
    demand_file_names = {'hist': [], 'live': []}
    ftp.retrlines('NLST ' + demand_folder_name['hist'], demand_file_names['hist'].append)
    ftp.retrlines('NLST ' + demand_folder_name['live'], demand_file_names['live'].append)
    normal_file_names = {'hist': []}
    ftp.retrlines('NLST ' + normal_folder_name['hist'], normal_file_names['hist'].append)

    
    result_dict = {k: "Success" for k in [f"{x}_{y}" for x in fund_list for y in grid_list]}
    
    
    for fund in fund_list:
        if 'normal' in fund:
            hour=''
        for grid in grid_list:
            if fund.lower() in ['availcap']:
                CUR_CODES_grid = dict((v,k) for k,v in CUR_CODES[grid].items())
            # sel_files = filter_files(fund, grid, hour)
            file_names = {}
            split_fund = fund.split('_')
            if 'mnd' in fund:
                
                if split_fund[0] in ['Wind', 'Solar', 'AvailCap']:
                    file_names['hist'] = [k for k in supply_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    file_names['live'] = [k for k in supply_file_names['live']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    folder_name = supply_folder_name
                elif split_fund[0] in ['ResidualDemand', 'CON']:
                    file_names['hist'] = [k for k in demand_file_names['hist']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    file_names['live'] = [k for k in demand_file_names['live']
                                          if (split_fund[0] in k) and (grid in k) and ('mnd' in k)]
                    folder_name = demand_folder_name
            elif 'normal' in fund:
                file_names['hist'] = [k for k in normal_file_names['hist']
                                      if (split_fund[0] in k) and (grid in k) and ('_N_' in k)]
                file_names['live'] = []
                folder_name = normal_folder_name

                
            else:
                if fund in ['Wind', 'Solar', 'AvailCap']:
                    file_names['hist'] = [k for k in supply_file_names['hist'] if (fund in k) and (grid in k)]
                    file_names['live'] = [k for k in supply_file_names['live'] if (fund in k) and (grid in k)]
                    folder_name = supply_folder_name
                elif fund in ['ResidualDemand', 'CON']:
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
            if 'normal' not in fund:
                l_append(file_names['live'], live_strings, folder_name['live'])
                                                                
            
            file = None

            ftp.close()
            ftp = FTP(host='pointconnect.commodities.refinitiv.com')
            ftp.login(user='krajcovic_matej@energytrading.sk',
                        passwd='kmfT5Q$kw')
            ftp.encoding = 'utf-8'
            
            if fund.lower() in ['availcap']:
                df = av_cap_processing(db, ftp, from_, sel_files, CUR_CODES_grid, hour, grid)
            elif split_fund[0].lower() in ['residualdemand', 'wind', 'solar', 'con']:
                df = mid_fund_processing(sel_files, folder_name, ftp, fund, grid, hour)
            
            if not isinstance(df, int):
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

                

client = Entsoe(api_key=config_entso['matej_api_key'])
                
def get_transmission_outage(grid_from, grid_to, start, end):
    start_tz = pd.Timestamp(start, tz='Europe/Brussels')
    end_tz = pd.Timestamp(end, tz='Europe/Brussels')
    
    # Example client query - you need to define this
    df = client.query_unavailability_transmission(grid_from,grid_to, start=start_tz, end=end_tz).reset_index()

    # Convert to datetime and handle timezone
    df['created_doc_time'] = pd.to_datetime(df['created_doc_time']).dt.tz_localize(None)
    df['start'] = pd.to_datetime(df['start']).dt.tz_localize(None)
    df['end'] = pd.to_datetime(df['end']).dt.tz_localize(None)
    
    timeseries = []
    for _, row in df.iterrows():
        timeseries.append((row['start'], row['avail_qty'], row['created_doc_time']))
        timeseries.append((row['end'], row['avail_qty'], row['created_doc_time']))

    # Convert to DataFrame for easier manipulation
    ts_df = pd.DataFrame(timeseries, columns=['time', 'qty', 'created_doc_time'])
    ts_df.sort_values(by=['time', 'created_doc_time'], inplace=True)

    # Drop duplicates, keeping the last occurrence to handle overlaps
    ts_df = ts_df.drop_duplicates(subset=['time'], keep='last')
    
    ts_df.set_index('time', inplace=True)
    ts_df.drop('created_doc_time',axis=1, inplace=True)
    ts_df['qty'] = ts_df['qty'].astype(float)
    
    hourly_series = ts_df.resample('min').ffill()
    hourly_series = hourly_series.resample('h').mean()
    hourly_series = hourly_series[start:end]
    return hourly_series

def fetch_fund_entso(from_=dt.datetime.now().date(),
                   fund_list: list = ['Export_NTC'],
                   grid_list: list = ['DEU'],
                   hour:str = '12',
                   end_date:dt.datetime = None):

    if end_date is None:
        end_date = dt.datetime(dt.date.today().year+2,
                               1,1)
    
    db = Database()

    
    for fund in fund_list:
        for grid_from in grid_list:
            grid_from_e = GtEZ[grid_from]
            # select from table
            schema_name = f"FUND_{fund}"
            table_name = f"{grid_from}"
            sql_query = f"""
            SELECT MAX(forecast_date) AS latest_date
            FROM "{schema_name}"."{table_name}";
            """
            try:
                a = db.execute(sql_query)
                last_date = pd.to_datetime(a.iloc[0].dt.date.values[0])
            except Exception as e:
                print(e, "Empty database")
                last_date = pd.to_datetime(dt.datetime(2019,1,1).date())
            export_data = pd.DataFrame()  
            
                
            for grid_to_e in NEIGHBOURS[grid_from_e]:
                if grid_to_e not in check_list:
                    continue
                if (end_date-last_date).days<=365:
                    aux = get_transmission_outage(grid_from_e,
                                                  grid_to_e,
                                                  last_date,
                                                  end_date)
                    aux = aux.rename(columns={'qty': grid_to_e})
                    if export_data.empty:
                        export_data = aux.copy()
                    else:
                        export_data = pd.concat([export_data, aux],axis=1)
                else:
                    grid_to_aux = pd.DataFrame()
                    range_end = last_date + dt.timedelta(days=365)
                    range_start = last_date
                    while range_end<=end_date:
                        try:
                            aux = get_transmission_outage(grid_from_e,
                                                          grid_to_e,
                                                          range_start,
                                                          range_end)
                            aux = aux.rename(columns={'qty': grid_to_e})
                        except NoMatchingDataError:
                            print("No matching data found for the specified parameters. Continuing with the next steps.")
                            break
                        if grid_to_aux.empty:
                            grid_to_aux = aux.copy()
                        else:
                            grid_to_aux = pd.concat([grid_to_aux, aux])
                        range_start = range_end + dt.timedelta(days=1)
                        range_end = range_start + dt.timedelta(days=365)
                    grid_to_aux = grid_to_aux[~grid_to_aux.index.duplicated(keep='first')]
                    if export_data.empty:
                        export_data = grid_to_aux.copy()
                    else:
                        export_data = pd.concat([export_data,
                                                 grid_to_aux],axis=1)
            export_data = export_data.reset_index()
            export_data = export_data.rename(columns={'time': 'value_date'})
            export_data.to_sql(name="stage_" + grid_from,
                              schema='FUND_'+fund,
                              con=db.connection_string,
                              if_exists='replace', index=False)
            db.merge_from_staging_to_prod('FUND_'+fund, f"{grid_from}")
                
                        
                    
    
    pass
    
                
# test = fetch_fund_ftp(fund_list=['AvailCap'],
#                       grid_list=['DEU', 'FRA'],
#                       hour='12')
# test = fetch_fund_entso(fund_list=['Export_NTC'],
#                       grid_list=['BEL', 'NLD', 'AUT'])
# test = fetch_fund_ftp(fund_list=['CON_mnd', 'Wind_mnd', 'Solar_mnd'],
#                       grid_list=['DEU', 'FRA', 'NLD', 'BEL', 'AUT'],
#                       hour='00')
# test = fetch_fund_ftp(fund_list=['CON_normal', 'Solar_normal', 'Wind_normal'],
#                       grid_list=['CZE', 'SVK', 'HUN'],
#                       hour='00')
test = fetch_fund_ftp(fund_list=['CON_normal', 'Wind_normal', 'Solar_normal'],
                      grid_list=['HUN', 'CZE', 'SVK'],
                      hour='')
