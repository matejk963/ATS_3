"""
    Create/update coal data of contious contract from eikon
    
"""

import pandas as pd
import refinitiv.data as rd
import datetime as dt
import json
from Common.config_load import get_config_path as CONFIG_PATH
from Database.DB_reader import Database
from Loaders.EikonFut_class import EikonFut as EF

PATH = CONFIG_PATH()
with open(PATH, 'r') as file:
    config_eex = json.load(file)['EEX_ftp']
    
def check_updated_data(schema, grid):
    db = Database()
    schema_name = schema
    table_name = f"{grid}"
    select
    query = f"""
    SELECT datetime, M_1_SETTLE, M_2_SETTLE, M_3_SETTLE, M_4_SETTLE, M_5_SETTLE
    FROM "{schema_name}"."{table_name}';
    """

    df = pd.read_sql(query)
    # Identify datetimes with empty values
    # Step 1: Identify value columns (exclude 'datetime')
    value_columns = [col for col in df.columns if col != 'datetime']

    # Step 2: Check for NaN in any of the value columns
    nan_mask = df[value_columns].isna().any(axis=1)

    # Step 3: Filter datetimes where there is at least one NaN
    datetimes_with_nan = df.loc[nan_mask, 'datetime']

    for date in datetimes_with_nan:
        gas_data_to_db(start_date=date,
                       fut_periods=60)
    


def gas_data_to_db(start_date=None,
                    fut_periods=12):
    db = Database()
    start_date, end_date = get_dates(db, 'futures', 'tfm', base_date)
    if not start_date == end_date:
        rics_list = [[f'TFMBMc{str(a+1)}' for a in range(fut_periods-10,
                                                        fut_periods)]
                for fut_periods in range(10,61,10)]
        data_list = []
        for rics in rics_list:
            rd.open_session()
            temp = rd.get_history(universe=rics,
                                    fields=['SETTLE', 'CRT_MNTH'],
                                    start=start_date,
                                    end=end_date)
            rd.close_session()
            data_list.append(temp)
        data = pd.concat(data_list,axis=1)    
        data.columns = [f"{col1.split('c')[0][-1]}_{col1.split('c')[1]}_{col2}"
                        for (col1, col2) in data.columns]
        data.index = pd.to_datetime(data.index)
        # data = data.dropna(subset=['M_1_EXPIR_DATE']).copy()
        settle_columns = [a for a in data.columns if 'SETTLE' in a]
        crt_month_columns = [a for a in data.columns if 'CRT_MNTH' in a]
        data[settle_columns] = data[settle_columns].astype(float)
        # data[crt_month_columns].columns = [a.replace('EXPIR_DATE','EXPIRY')
        #                                     for a in crt_month_columns]
        # data[crt_month_columns] = data[crt_month_columns].astype(int)
        data = data.reset_index().copy()
        data = data.rename(columns={'Date': 'datetime'})
        if len(data)==0:
                print('No data to upload')
        else:
            data.to_sql(name="stage_tfm" ,
                        schema='futures',
                        con=db.connection_string,
                        if_exists='replace', index=False)
            db.merge_from_staging_to_prod('futures', "tfm")
            
def gas_da_df(base_date):
    db = Database()
    sD, eD = get_dates(db, 'spot', 'ttf', base_date)
    rd.open_session()
    da_df = rd.get_history(['TTFDA', 'TTFWE'],
                            start=sD.strftime('%Y-%m-%d'),
                            end=eD.strftime('%Y-%m-%d'),fields=['VWAP']).astype(float)
    
    rd.close_session()
    if len(da_df)>=1:        
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
        data = pd.DataFrame(pd.Series(sorted_prices),columns=['price']).reset_index()
        data = data.rename(columns={'index': 'datetime'})
        data['datetime'] = pd.to_datetime(data['datetime'])
        data['price'] = data['price'].astype(float)
        if len(data)==0:
            print('No data to upload')
        else:
            data.to_sql(name="stage_ttf" ,
                        schema='spot',
                        con=db.connection_string,
                        if_exists='replace', index=False)
            db.merge_from_staging_to_prod('spot', "ttf")

if __name__=='__main__':
    gas_data_to_db(base_date=dt.datetime(2019,1,1), fut_periods=60)
    gas_da_df(base_date=dt.datetime(2019,1,1))