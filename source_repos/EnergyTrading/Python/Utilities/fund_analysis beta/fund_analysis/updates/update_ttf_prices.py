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
    
def get_dates(db, schema, grid, base_date=dt.datetime(2024, 7, 1)):
    def get_latest_business_date(reference_date=None):
        if reference_date is None:
            reference_date = dt.datetime.today()

        latest_date = reference_date - dt.timedelta(days=1)

        while latest_date.weekday() >= 5:  # 5 and 6 correspond to Saturday and Sunday
            latest_date -= dt.timedelta(days=1)

        return pd.to_datetime(latest_date.date())

    # Schema and table information
    schema_name = schema
    table_name = f"{grid}"

    # Step 1: Delete the last 10 rows ordered by datetime descending
    delete_sql = f"""
    DELETE FROM "{schema_name}"."{table_name}"
    WHERE ctid IN (
        SELECT ctid
        FROM "{schema_name}"."{table_name}"
        ORDER BY datetime DESC
        LIMIT 100
    );
    """
    try:
        db.execute(delete_sql)
    except Exception as e:
        print(f"Error while deleting rows: {e}")

    # Step 2: Select the latest date from the remaining records
    select_sql = f"""
    SELECT MAX(datetime) AS latest_date
    FROM "{schema_name}"."{table_name}";
    """

    # Determine the last date based on the schema
    if schema in ['futures']:
        last_date = get_latest_business_date()
    elif schema in ['spot']:
        last_date = pd.to_datetime(dt.datetime.today().date())

    # Execute SQL query to find the first date
    try:
        a = db.execute(select_sql)
        if schema in ['futures']:
            first_date = pd.to_datetime(a.iloc[0].dt.date.values[0]) + dt.timedelta(days=1)
        elif schema in ['spot']:
            first_date = pd.to_datetime(a.iloc[0].dt.date.values[0])
    except Exception as e:
        print(e, "Empty database")
        first_date = pd.to_datetime(base_date.date())

    # Ensure first_date does not exceed last_date
    if first_date > last_date:
        first_date = last_date

    return first_date, last_date


def gas_data_to_db(base_date=dt.datetime(2024,6,1),
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