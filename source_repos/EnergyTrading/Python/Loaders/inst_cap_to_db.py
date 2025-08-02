import os
import pandas as pd
from Database.DB_reader import Database
import datetime as dt
import re

inst_cap_path = r'C:\data\Data\Spot\Entso\InstCap\10YHU-MAVIR----U_inst_cap.parquet'

# Load the installed capacity DataFrame
inst_cap = pd.read_parquet(inst_cap_path)

inst_cap = inst_cap.drop_duplicates()
# Ensure last_date is present and resample as needed
last_date_list = [dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1), dt.datetime(2028, 1, 1)]
for last_date in last_date_list:
    if last_date not in inst_cap.index:
        inst_cap.loc[last_date] = None
        # inst_cap = inst_cap.resample('h').ffill().dropna()
inst_cap = inst_cap.ffill()

grid = 'HUN'
hour = '12'
fund = 'LtInstCap'
db = Database()

naming_dict = {
    'B01': 'Bio',
    'B02': 'Lig',
    'B04': 'Gas',
    'B05': 'Coal',
    'B06': 'Oil',
    'B14': 'Nuc'
}
fcst_date_list = pd.date_range(dt.datetime(2019,1,1,12), dt.datetime(2025,1,1,12))
for forecast_date in fcst_date_list:
    df = inst_cap.copy()
    
    # Rename columns based on naming_dict
    df.rename(columns=naming_dict, inplace=True)

    # Drop columns not in naming_dict
    df = df[[a for a in list(naming_dict.values()) if a in df.columns]]

    # Update column names to add suffix for Hungarian units
    df.columns = [f'{a}_hu' for a in df.columns]

    df = df.reset_index()
    df = df.rename(columns={'index': 'value_date'})

    # Set forecast_date column
    df['forecast_date'] = forecast_date
    # Save to SQL
    df.to_sql(name="stage_" + grid + "_" + hour,
                schema='FUND_'+fund,
                con=db.connection_string,
                if_exists='replace', index=False)
    db.merge_from_staging_to_prod('FUND_'+fund, f"{grid}_{hour}")