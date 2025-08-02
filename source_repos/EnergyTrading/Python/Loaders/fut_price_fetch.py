# -*- coding: utf-8 -*-
"""
Created on Thu May  2 10:04:33 2024

@author: scasny
"""

import pandas as pd
import numpy as np
import datetime as dt
from io import BytesIO
from ftplib import FTP, all_errors
import paramiko
from paramiko.ssh_exception import SSHException
import json
from io import StringIO
from Common.config_load import get_config_path as CONFIG_PATH
from Database.DB_reader import Database


PATH = CONFIG_PATH()
with open(PATH, 'r') as file:
    config_eex = json.load(file)['EEX_ftp']
    
def get_dates(db, grid, base_date=dt.datetime(2024,7,1)):
    def get_latest_business_date(reference_date=None):
        if reference_date is None:
            reference_date = dt.datetime.today()
        
        latest_date = reference_date - dt.timedelta(days=1)
    
        while latest_date.weekday() >= 5:  # 5 and 6 correspond to Saturday and Sunday
            latest_date -= dt.timedelta(days=1)
        
        return pd.to_datetime(latest_date.date())
    # select from table
    schema_name = 'futures'
    
   
    table_name = f"{grid}"
    sql_query = f"""
    SELECT MAX(datetime) AS latest_date
    FROM "{schema_name}"."{table_name}";
    """
    last_date = get_latest_business_date()
    
    try:
        a = db.execute(sql_query)
        first_date = pd.to_datetime(a.iloc[0].dt.date.values[0]) + dt.timedelta(days=1)
    except Exception as e:
        print(e, "Empty database")
        first_date = pd.to_datetime(base_date.date())
        
    return first_date, last_date
    
def generate_file_paths(db, country, start_date_obj, end_date_obj, data_type='power'):
    """
    Generate file paths for the given country and date range.

    Args:
    country (str): The country code (e.g., 'de' for Germany).
    start_date (str): The start date in 'YYYY-MM-DD' format.
    end_date (str): The end date in 'YYYY-MM-DD' format.

    Returns:
    list: A list of file paths.
    """
    
    
    base_path = r'market_data/power'
    derivative_path = 'derivatives/csv'
    file_paths = []


    delta = dt.timedelta(days=1)

    current_date = start_date_obj
    while current_date <= end_date_obj:
        year = current_date.year
        date_str = current_date.strftime('%Y%m%d')
        file_name = 'PowerFutureResults_' + country.upper() + '_' + f"{date_str}.csv"
        file_path = f"{base_path}/{country}/{derivative_path}/{year}/{date_str}/" + file_name
        file_paths.append(file_path)
        current_date += delta

    return file_paths

def clean_data(df, file_path):
    # Define a function to adjust the dates
    def adjust_dates(row):
        if pd.notna(row['delivery_start']) and pd.notna(row['delivery_end']):
            if row['delivery'] == 'Peak' and row['product_type'] in ['Month', 'Quarter', 'Season', 'Year']:
                row['delivery_start'] = row['delivery_start'].replace(day=1)  # First day of the month
                row['delivery_end'] = row['delivery_end'].replace(
                    day=row['delivery_end'].days_in_month)  # Last day of the month
        return row
    if '20211101' in file_path:
        pass
    # Drop rows 1, 2, 3, 5, 6
    df = df.drop(index=[0, 1, 2, 4, 5])
    
    # Reset index after dropping rows
    df.reset_index(drop=True, inplace=True)

    # Save the value in B8
    value_B8 = df.iloc[2, 1]  # B8 in the original CSV (considering header row now)
    
    # Convert value_B8 to datetime
    datetime_value = pd.to_datetime(value_B8, format='%Y-%m-%d')
    
    # Drop rows that don't have 'PR' in the first column, except header row
    df = df[df.iloc[:, 0].str.contains('PR', na=False)].copy()
    df = df = df[~df.iloc[:, 2].str.contains('OTF|Floor|Cap|Phelix', na=False)].copy()

    
    # Retain only the specified columns
    required_columns = ['Product', 'Long Name', 'Delivery Start', 'Delivery End',
                        'Settlement Price', 'Open Price', 'High Price',
                        'Low Price', 'Last Price',
                        'Traded Lots',
                        'Open Interest Lots']
    df.columns = df.iloc[0]  # Set the header row as the columns
    df = df[1:]  # Remove the header row from the data
    df = df[required_columns]
    
    # Insert the datetime column at the beginning
    df.insert(0, 'datetime', datetime_value)

    # Convert to numeric
    # Convert multiple columns to numeric (float)
    df[['Settlement Price', 'Open Price', 'High Price', 'Low Price', 'Last Price',
            'Traded Lots', 'Open Interest Lots']] = (
            df[['Settlement Price', 'Open Price', 'High Price', 'Low Price', 'Last Price',
                'Traded Lots', 'Open Interest Lots']]
            .replace(',', '.', regex=True)  # Convert comma to dot
            .apply(pd.to_numeric, errors='coerce')  # Convert to numeric
        )

    
    # Extract 'Base'/'Peak' and 'Day'/'Weekend'/'Week'/'Month'/'Quarter'/'Year' into separate columns
    df['delivery'] = df['Long Name'].str.extract(r'(Base|Peak)')
    df['product_type'] = df['Long Name'].str.extract(r'(Day|Weekend|Week|Month|Quarter|Year)')
    
    # Drop 'Product' and 'Long Name' columns
    df.drop(columns=['Product', 'Long Name'], inplace=True)
    
    # Rename columns to lower case with underscores
    df.columns = [col.lower().replace(' ', '_') for col in df.columns]
    
    # Convert to datetime
    df['delivery_start'] = pd.to_datetime(df['delivery_start'], errors='coerce')
    df['delivery_end'] = pd.to_datetime(df['delivery_end'], errors='coerce')

    
    df = df.apply(adjust_dates, axis=1)

    return df

def retrieve_and_clean_files_from_ftp(file_paths):
    combined_df = pd.DataFrame()

    try:
        transport = paramiko.Transport((config_eex['host'], config_eex['port']))
        transport.connect(username=config_eex['USERNAME'], password=config_eex['PASSWORD'])
        sftp = paramiko.SFTPClient.from_transport(transport)

        for file_path in file_paths:

            try:
                with sftp.open(file_path, 'r') as file:
                    raw_content = file.read()
                    raw_text = raw_content.decode('utf-8')

                    # Split the raw text into lines
                    lines = raw_text.split('\n')
                    
                    # Find the maximum number of columns
                    max_columns = max(len(line.split(';')) for line in lines)

                    # Create a DataFrame from the lines
                    df = pd.DataFrame([line.split(';') for line in lines], columns=range(max_columns))

                    # Clean the data
                    df = clean_data(df, file_path)

                    # Append to the combined_df DataFrame
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
            except (IOError, SSHException) as e:
                print(f"Error reading file {file_path}: {e}")
                continue

        # Close the SFTP connection
        sftp.close()
        transport.close()

    except SSHException as e:
        print(f"SFTP connection error: {e}")

    return combined_df


def insert_files_to_db(country, base_date=dt.datetime(2024,7,1)):
    db = Database()
    start_date, end_date = get_dates(db, country, base_date)
    file_paths = generate_file_paths(db, country, start_date, end_date)
    if len(file_paths)==0:
        print('No update needed')
    else:
        df = retrieve_and_clean_files_from_ftp(file_paths)
        if len(df)==0:
            print('No data to upload')
        else:
            df.to_sql(name="stage_" + country ,
                              schema='futures',
                              con=db.connection_string,
                              if_exists='replace', index=False)
            db.merge_from_staging_to_prod('futures', f"{country}")
        


           
if __name__ == "__main__":
    # file_paths = generate_file_paths('de', dt.datetime(2024,7,15), dt.datetime(2024,7,15))
    # df = retrieve_and_clean_files_from_ftp(file_paths)
    # 'at','de', 'fr', 'fr', 'hu','hu', 'cz', 'cz', 'sk', 'sk', 'it', 'it'
    base_date = dt.datetime(2019,1,1)
    for country in [country for country in ['de', 'fr', 'nl',
                                                          'be', 'cz', 'sk',
                                                          'at', 'hu', 'ro',
                                                           'it', 'es'] for _ in range(3)]:
        insert_files_to_db(country, base_date)