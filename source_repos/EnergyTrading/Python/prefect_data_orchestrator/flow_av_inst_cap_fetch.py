from prefect import flow, task
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import sys
import os

# Get the directory of the script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the directory of Utilities to sys.path
sys.path.append(os.path.join(current_dir, '..', 'Utilities', 'EntsoData', 'AvailCap'))

import time
import re
from Database.DB_reader import Database
import datetime as dt

# Constants
API_KEY = '0e829f02-4563-482b-8a57-802b1e685c67'
URL = "https://web-api.tp.entsoe.eu/api"
GRIDS_TO_SKIP = ["10Y1001A1001A82H", "10YFR-RTE------C",
                 "10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YAT-APG------L",
                 "10YBE----------2", "10YNL----------L"]
NAMING_DICT = {'B01': 'Bio', 'B02': 'Lig', 'B04': 'Gas', 'B05': 'Coal', 'B06': 'Oil', 'B14': 'Nuc', 'B10': 'Pump'}
GRID_MAPPING = {
    "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
    "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
    "10YCZ-CEPS-----N": {'column_suffix': '_cz', 'table_name': 'CZE'},
    "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
    "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"},
    "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
    "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},
    "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
}
INST_CAP_PATH = '//192.168.10.91/d/data/Data/Spot/Entso/InstCap'
os.makedirs(INST_CAP_PATH, exist_ok=True)
HOUR = '12'
FUNDS = ['InstCap', 'LtInstCap']

def get_fcst_date_range(schema_name, table_name):
    query = f"""
    SELECT MAX(forecast_date) AS last_forecast_date
    FROM \"{schema_name}\".\"{table_name}_12\";
    """
    try:
        with Database() as db:
            result = db.execute(query)
        start_date = result.iloc[0]['last_forecast_date'] - dt.timedelta(days=5) if not result.empty else dt.datetime(2019, 1, 1, 12)
    except:
        start_date = dt.datetime(2019, 1, 1, 12)
    return pd.date_range(start_date, datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=30), freq='12H')

@task(retries=3, retry_delay_seconds=10, timeout_seconds=600, log_prints=True)
def fetch_data(grid, start_date, end_date):
    summary_data = {}
    current_date = start_date
    while current_date <= end_date:
        period_start = current_date.strftime("%Y%m%d0000")
        period_end = (current_date + timedelta(days=1)).strftime("%Y%m%d0000")
        params = {
            "securityToken": API_KEY,
            "documentType": "A71",
            "processType": "A33",
            "in_Domain": grid,
            "periodStart": period_start,
            "periodEnd": period_end
        }
        try:
            response = requests.get(URL, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}
            for timeseries in root.findall(".//ns:TimeSeries", ns):
                psr_type = timeseries.find("ns:MktPSRType/ns:psrType", ns).text or "N/A"
                quantity = float(timeseries.find(".//ns:Point/ns:quantity", ns).text or "0")
                summary_data.setdefault(current_date, {}).setdefault(psr_type, 0.0)
                summary_data[current_date][psr_type] += quantity
        except requests.exceptions.RequestException as e:
            print(f"Error on {current_date.strftime('%Y-%m-%d')} for grid {grid}: {e}")
        current_date += timedelta(days=1)
        time.sleep(1)
    return summary_data

@flow
def entsoe_inst_cap_flow(grid_mapping: dict = None):
    if not grid_mapping:
        grid_mapping = GRID_MAPPING
    grids = list(grid_mapping.keys())
    end_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=365)
    # for grid in grids:
    #     if grid in GRIDS_TO_SKIP:
    #         continue
    #     inst_cap_filepath = os.path.join(INST_CAP_PATH, f"{grid}_inst_cap.parquet")
    #     start_date = datetime(2019, 1, 1)
    #     if os.path.exists(inst_cap_filepath):
    #         existing_data = pd.read_parquet(inst_cap_filepath)
    #         existing_data.index = pd.to_datetime(existing_data.index)
    #         last_date = existing_data.index.max()
    #         start_date = last_date - timedelta(days=1) if last_date <= datetime.now() else datetime.now() - timedelta(days=7)
        
    #     new_data = fetch_data(grid, start_date, end_date)
    #     new_data_df = pd.DataFrame.from_dict(new_data, orient='index').fillna(0)
    #     if os.path.exists(inst_cap_filepath):
    #         updated_data = pd.concat([existing_data, new_data_df]).sort_index().drop_duplicates()
    #         updated_data.to_parquet(inst_cap_filepath)
    #     else:
    #         new_data_df.to_parquet(inst_cap_filepath)
    
    for file_name in os.listdir(INST_CAP_PATH):
        if re.search(r'inst_cap', file_name, re.IGNORECASE) and file_name.endswith('.parquet'):
            grid_code = re.match(r'(.*)_inst_cap', file_name).group(1)
            if grid_code in GRIDS_TO_SKIP or grid_code not in GRID_MAPPING:
                continue
            column_suffix = GRID_MAPPING[grid_code]['column_suffix']
            table_name = f"{GRID_MAPPING[grid_code]['table_name']}"
            file_path = os.path.join(INST_CAP_PATH, file_name)
            inst_cap = pd.read_parquet(file_path).drop_duplicates()
            inst_cap.index = inst_cap.index.normalize()
            last_date_list = [dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1), dt.datetime(2028, 1, 1)]
            for last_date in last_date_list:
                if last_date not in inst_cap.index:
                    inst_cap.loc[last_date] = None
            inst_cap = inst_cap.ffill()
            for fund in FUNDS:
                schema_name = f"FUND_{fund}"
                fcst_date_list = get_fcst_date_range(schema_name, table_name)
                for forecast_date in fcst_date_list:
                    df = inst_cap.copy()
                    df.rename(columns=NAMING_DICT, inplace=True)
                    df = df[[a for a in NAMING_DICT.values() if a in df.columns]]
                    df.columns = [f'{a}{column_suffix}' for a in df.columns]
                    df = df.reset_index().rename(columns={'index': 'value_date'})
                    df['forecast_date'] = forecast_date
                    staging_table_name = f"stage_{table_name}_{HOUR}"
                    with Database() as db:
                        df.to_sql(name=staging_table_name, schema=schema_name, con=db.connection_string, if_exists='replace', index=False)
                        try:
                            db.merge_from_staging_to_prod(schema_name, f"{table_name}_{HOUR}")
                        except:
                            print(f"Error merging {staging_table_name} to production table.")

if __name__ == "__main__":
    entsoe_inst_cap_flow(grid_mapping=
            {"10YHU-MAVIR----U": {
                "column_suffix": "_hu", "table_name": "HUN"}})
