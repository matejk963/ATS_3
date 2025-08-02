# -*- coding: utf-8 -*-
"""
Created on Wed Oct 11 09:51:22 2023

@author: krajcovic
"""

import ftplib
import pandas as pd
from io import BytesIO
import datetime as dt

class FTPDataManager:
    def __init__(self, ftp_server, username, password):
        self.ftp_server = ftp_server
        self.username = username
        self.password = password
        self.directory_hist = None
        self.directory_live = None
        self.substring = None
        self.forecast_start_date = None
        self.forecast_end_date = None
        self.cutoff_minutes = None
        self.value_start_date = None
        self.value_end_date = None
        self.value_date_range = None
        self.asset_id = None
        self.prepared_data = None
     
    @staticmethod
    def get_asset_id(asset_type):
        asset_dict = {}
        asset_dict['coal'] = 105269300
        asset_dict['gas'] = 105663406
        asset_dict['lig'] = 105269303
        asset_dict['nuc'] = 105269302
        asset_dict['pump'] = 111205650
        asset_dict['resrv'] = 111205651
        asset_dict['ror'] = 111205652
        return asset_dict[asset_type]
        
        
        
    def set_asset_id(self, asset_type):
        self.asset_id = self.get_asset_id(asset_type)
        
        
    
        
    def determine_files(self, start_forecast_date=None, end_forecast_date=None):
        if start_forecast_date is None:
            start_forecast_date = self.forecast_start_date
        if end_forecast_date is None:
            end_forecast_date = self.forecast_end_date
        start_date = pd.to_datetime(start_forecast_date)
        end_date = pd.to_datetime(end_forecast_date)
        
        print(f"Inside determine_files - Start Date: {start_date}")
        print(f"Inside determine_files - End Date: {end_date}")

        files = []
        current_date = start_date
        while current_date <= end_date:
            file_name = f"5044792_HIST_Pwr_PCA_PRO_AvailCap_EEX_REMIT_E1_DEU_F_{current_date.year}-{current_date.month:02}.CSV"
            files.append(file_name)
            current_date = current_date + pd.DateOffset(months=1)
        print(f"Generated files list: {files}")
        return files
    
    def retrieve_data_from_ftp(self, files, substring=None,
                               FTP_DIRECTORY_hist=None, FTP_DIRECTORY_live=None):
        if substring is None:
            substring = self.substring
        if FTP_DIRECTORY_hist is None:
            FTP_DIRECTORY_hist = self.directory_hist
        if FTP_DIRECTORY_live is None:
            FTP_DIRECTORY_live = self.directory_live
        dfs = []
        downloaded_files = []

        with ftplib.FTP(self.ftp_server) as ftp:
            ftp.login(self.username, self.password)
            ftp.cwd(FTP_DIRECTORY_hist)

            for file in files:
                if file in ftp.nlst():
                    print(f"Reading file: {file}")
                    with BytesIO() as bio:
                        ftp.retrbinary(f"RETR {file}", bio.write)
                        bio.seek(0)
                        try:
                            # Skipping the first row (copyright notice)
                            raw_data = pd.read_csv(bio, delimiter='|', skiprows=1)
                            dfs.append(raw_data)
                            downloaded_files.append(file)
                        except Exception as e:
                            print(f"Error reading {file} into dataframe: {e}")
                else:
                    print(f"File {file} not found in {FTP_DIRECTORY_hist} on FTP server.")

            # Switch to the other directory
            ftp.cwd(FTP_DIRECTORY_live)

            for file in ftp.nlst():
                if substring in file:
                    print(f"Reading file from other directory: {file}")
                    with BytesIO() as bio:
                        ftp.retrbinary(f"RETR {file}", bio.write)
                        bio.seek(0)
                        try:
                            # Skipping the first row (copyright notice)
                            raw_data = pd.read_csv(bio, delimiter='|', skiprows=1)
                            dfs.append(raw_data)
                            downloaded_files.append(file)
                        except Exception as e:
                            print(f"Error reading {file} from other directory into dataframe: {e}")
                    
        return dfs, downloaded_files


    def get_closest_to_cutoff(self, group):
        # Filter entries before the cutoff time
        before_cutoff = group[group['ForecastMinutes'] <= self.cutoff_minutes].copy()
        
        # If there's at least one entry before the cutoff, return the latest.
        # Otherwise, return an empty DataFrame (i.e., discard the whole group)
        if not before_cutoff.empty:
            return before_cutoff.nlargest(1, 'ForecastMinutes', 'all')
        else:
            return pd.DataFrame()
        
    def get_rows_within_range_and_one_before(self, df, start_value_date=None,
                                             end_value_date=None, asset_id=None):
        if start_value_date is None:
            start_value_date = self.value_start_date
        if end_value_date is None:
            end_value_date = self.value_end_date
        if asset_id is None:
            asset_id = self.asset_id
        """
        For each ForecastDate, return rows within the defined ValueDate range 
        and the first entry before the start of this range.
        """
        extended_df = pd.DataFrame()  # Initialize an empty DataFrame to store results
        df = df[df['Id']==int(asset_id)].copy()
        for forecast_date in df['ForecastDate'].unique():
            # Filter rows for the current ForecastDate that are within the defined range
            rows_within_range = df[
                (df['ForecastDate'] == forecast_date) &
                (df['ValueDate'] >= start_value_date) & 
                (df['ValueDate'] < (end_value_date+dt.timedelta(days=1)))
            ]
            
            # Find the first ValueDate entry before the defined start date
            row_before_start = df[
                (df['ForecastDate'] == forecast_date) & 
                (df['ValueDate'] < start_value_date)
            ].nlargest(1, 'ValueDate')

            # Concatenate results and add to the extended DataFrame
            extended_df = pd.concat([extended_df, row_before_start, rows_within_range])

        return extended_df.reset_index(drop=True)
    
    def time_string_to_minutes(self, time_str):
        hours, minutes, seconds = map(int, time_str.split(':'))
        return hours * 60 + minutes
    
    def set_directories(self, directory_hist, directory_live):
        self.directory_hist = directory_hist
        self.directory_live = directory_live

    def set_substring(self, substring):
        self.substring = substring
    
    def set_forecast_dates(self, start_date, end_date, cut_off_time):
        self.forecast_start_date = pd.to_datetime(start_date)
        self.forecast_end_date = pd.to_datetime(end_date)
        self.cutoff_minutes = self.time_string_to_minutes(cut_off_time)

    def set_value_dates(self, start_date, end_date):
        self.value_start_date = pd.to_datetime(start_date)
        self.value_end_date = pd.to_datetime(end_date)
        self.value_date_range = pd.date_range(start=self.value_start_date, 
                                 end=self.value_end_date.replace(hour=23), 
                                 freq='H')

    

    def prepare_data(self):
        required_files = self.determine_files()
        dfs, downloaded_files = self.retrieve_data_from_ftp(required_files)
        df_combined = pd.concat(dfs, ignore_index=True)
        df_combined['ValueDate'] = pd.to_datetime(df_combined['ValueDate'], dayfirst=True)
        df_combined['ForecastDate'] = pd.to_datetime(df_combined['ForecastDate'], dayfirst=True)
        df_combined = df_combined.sort_values(['ForecastDate', 'ValueDate'])
        df = df_combined.copy()
        df['ForecastDate'] = pd.to_datetime(df['ForecastDate'])
        df['ForecastDateOnly'] = pd.to_datetime(df['ForecastDate'].dt.date)
        df['ForecastMinutes'] = df['ForecastDate'].dt.hour * 60 + df['ForecastDate'].dt.minute
        result = df[df['Id']==int(self.asset_id)].groupby('ForecastDateOnly').apply(self.get_closest_to_cutoff).reset_index(drop=True)
        result = result.drop(columns=['ForecastDateOnly', 'ForecastMinutes'])
        self.prepared_data = self.get_rows_within_range_and_one_before(result)
        
    def get_prepared_data(self):
        if self.prepared_data is None:
            return self.prepare_data()
        else:
            return self.prepared_data

    def to_hourly_series(self):
        if self.prepared_data is None:
            df_prepared = self.prepare_data()
        else:
            df_prepared = self.prepared_data.copy()
        return self._to_hourly_series(df_prepared)

    def _to_hourly_series(self, df):
        df = df.copy()  # To ensure we don't modify the input dataframe
        df['ForecastDate'] = pd.to_datetime(df['ForecastDate']).dt.date  # Convert to datetime and then extract date
        df.set_index('ValueDate', inplace=True)
        
        hourly_series_dict = {}
        
        for date in df['ForecastDate'].unique():
            subset = df[df['ForecastDate'] == date].copy()
            subset = subset[~subset.index.duplicated(keep='last')]
            # Resample to hourly and forward fill
            hourly = subset.resample('s').ffill()
            value = hourly['Value'].resample('H').mean()
            value = value.reindex(self.value_date_range).ffill()
            hourly_series_dict[date] = value
        
        return hourly_series_dict
    
    
    