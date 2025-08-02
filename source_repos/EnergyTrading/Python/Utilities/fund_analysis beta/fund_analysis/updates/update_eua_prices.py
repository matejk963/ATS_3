"""
    Create/update coal data of contious contract from eikon
    
"""

import pandas as pd
import refinitiv.data as rd
import datetime as dt
import json
from Common.config_load import get_config_path as CONFIG_PATH
from Database.DB_reader import Database

PATH = CONFIG_PATH()
with open(PATH, 'r') as file:
    config_eex = json.load(file)['EEX_ftp']
    
def get_dates(db, grid, base_date=dt.datetime(2024, 7, 1)):
    def get_latest_business_date(reference_date=None):
        if reference_date is None:
            reference_date = dt.datetime.today()
        
        latest_date = reference_date - dt.timedelta(days=1)
    
        while latest_date.weekday() >= 5:  # 5 and 6 correspond to Saturday and Sunday
            latest_date -= dt.timedelta(days=1)
        
        return pd.to_datetime(latest_date.date())

    # Schema and table information
    schema_name = 'futures'
    table_name = f"{grid}"

    # Step 1: Delete the last 10 rows ordered by datetime descending
    delete_sql = f"""
    DELETE FROM "{schema_name}"."{table_name}"
    WHERE ctid IN (
        SELECT ctid
        FROM "{schema_name}"."{table_name}"
        ORDER BY datetime DESC
        LIMIT 10
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
    last_date = get_latest_business_date()

    try:
        a = db.execute(select_sql)
        first_date = pd.to_datetime(a.iloc[0].dt.date.values[0]) + dt.timedelta(days=1)
    except Exception as e:
        print(e, "Empty database")
        first_date = pd.to_datetime(base_date.date())

    # Ensure that the first date does not exceed the last date
    if first_date >= last_date:
        first_date = last_date

    return first_date, last_date

def eua_data_to_db(base_date=dt.datetime(2024,6,1),
                    fut_periods=12):
    db = Database()
    start_date, end_date = get_dates(db, 'cfi2', base_date)
    rics_list = [[f'CFI2Zc{str(a+1)}' for a in range(fut_periods-5,
                                                    fut_periods)]
            for fut_periods in range(5,6,5)]
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
        data.to_sql(name="stage_cfi2" ,
                    schema='futures',
                    con=db.connection_string,
                    if_exists='replace', index=False)
        db.merge_from_staging_to_prod('futures', "cfi2")
        
if __name__=='__main__':
    eua_data_to_db(base_date=dt.datetime(2019,1,1), fut_periods=60)