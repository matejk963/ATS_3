# -*- coding: utf-8 -*-
"""
Created on Wed Oct 11 10:37:13 2023

@author: krajcovic
"""
import pandas as pd
import numpy as np
import datetime as dt
from Loaders.AvCapFetch_rel_class_v2 import AvCapFetch as ACF


# FTP details
FTP_SERVER = r'pointconnect.commodities.refinitiv.com'  # Replace with your FTP server
USERNAME = "krajcovic_matej@energytrading.sk"      # Replace with your FTP username
PASSWORD = "kmfT5Q$kw"     # Replace with your FTP password

FTP_DIRECTORY_hist = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
FTP_DIRECTORY_live = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/' 

#substring
substring = '5044791_Pwr_PCA_PRO_AvailCap_EEX_REMIT_E1_DEU_F'

# Choose asset_id
chosen_asset_id = 105269300  # or any other ID you want

# Define value_date range
value_start_date = pd.to_datetime("2023-07-01")
value_end_date = pd.to_datetime("2023-07-31")


# Define forecast_date range
forecast_start_date = "2020-01-01"
forecast_end_date = "2023-10-11"



# Specify the cut-off time and chosen asset ID
cut_off_time = '12:00:00'
cutoff_time = dt.datetime.strptime(cut_off_time, "%H:%M:%S").time()
chosen_asset_id = "105269300"  # example

manager = ACF(ftp_server=FTP_SERVER, 
                         username=USERNAME, 
                         password=PASSWORD)

# Set directories where the data is stored
manager.set_directories(directory_hist=FTP_DIRECTORY_hist, 
                        directory_live=FTP_DIRECTORY_live)

# Set substring to look for in live directory files
manager.set_substring(substring=substring)

# Set forecast date range and cut-off time
manager.set_forecast_dates(start_date=forecast_start_date, 
                           end_date=forecast_end_date,
                           cut_off_time=cut_off_time)

# Set value date range
# manager.set_value_dates(start_date=value_start_date, 
#                         end_date=value_end_date)

# Set asset ID if needed
manager.set_asset_id(asset_type='gas')

# manager.prepare_data()

hourly_series = manager.to_hourly_series(date_range_type='week_ahead')

# required_files = manager.determine_files()
# dfs, downloaded_files = manager.retrieve_data_from_ftp(required_files)

# df = pd.concat(dfs, ignore_index=True)
# df['ValueDate'] = pd.to_datetime(df['ValueDate'], dayfirst=True)
# df['ForecastDate'] = pd.to_datetime(df['ForecastDate'], dayfirst=True)
# df = df.sort_values(['ForecastDate', 'ValueDate'])
# df['ForecastDate'] = pd.to_datetime(df['ForecastDate'])
# df['ForecastDateOnly'] = pd.to_datetime(df['ForecastDate'].dt.date)
# df['ValueDateOnly'] = pd.to_datetime(df['ValueDate'].dt.date)
# df['ForecastMinutes'] = df['ForecastDate'].dt.hour * 60 + df['ForecastDate'].dt.minute
# df = df[df['ForecastMinutes']<=manager.cutoff_minutes].copy()

# max_values = df.groupby('ForecastDateOnly')['ForecastMinutes'].transform('max')
# test = df[df['ForecastMinutes']==max_values].copy()

# test['days'] = (test['ValueDateOnly']-test['ForecastDateOnly']).dt.days
# test['day_ahead'] = np.where(test['days']==1,1,0)
# test['weekend_ahead'] = np.where((((test['days']+
#                                 test['ForecastDateOnly'].dt.weekday)>=5)&
#                               ((test['days']+
#                                 test['ForecastDateOnly'].dt.weekday)<=6)),
#                               1,0)
# test['week_ahead'] = np.where((((test['days']+
#                                 test['ForecastDateOnly'].dt.weekday)>=7)&
#                               ((test['days']+
#                                 test['ForecastDateOnly'].dt.weekday)<=13)),
#                               1,0)

# date_range_type = 'week_ahead'
# test = manager.get_prepared_data()
# test['filter_value'] = np.where(((test[date_range_type]<
#                         test[date_range_type].shift(-1))|
#                               (test[date_range_type]==1)),test['Value'],np.nan)
# test['ForecastDate'] = pd.to_datetime(pd.to_datetime(test['ForecastDate']).dt.date)
# test.set_index('ValueDate', inplace=True)

# date = test['ForecastDate'].unique()[0]

# subset = test[test['ForecastDate'] == date].copy()
# subset = subset.dropna(subset=['filter_value'])
# subset = subset[['filter_value']].copy()
# subset.columns = [['Value']]
# hourly = subset.resample('s').ffill()
# value = hourly.resample('H').mean()
# manager.determine_value_date_range(pd.to_datetime(date))
# value = value.reindex(manager.value_date_range).ffill()



# processed_data = manager.get_prepared_data()
# # print(processed_data)

# hourly_series = manager.to_hourly_series(date_range_type='week_ahead')

# mean_list = []
# date_list = []
# for key in hourly_series.keys():
#     temp = hourly_series[key].copy()
#     mean_list.append(temp.mean())
#     date_list.append(key)

# mean_gas = pd.DataFrame({'date':date_list,
#               'mean': mean_list})
# mean_gas.set_index('date', inplace=True)