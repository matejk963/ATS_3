# -*- coding: utf-8 -*-
"""
Created on Tue Jul 11 14:11:32 2023

@author: krajcovic
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
from time import sleep
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import BDay
import re
import os
from dateutil.relativedelta import relativedelta

from Utilities.date_functions import start_date

from Database.DB_reader import Database

from sqlalchemy import create_engine, text
import platform

import refinitiv.data as rd
def fwd_mkt_code(market):
    comm_dict = {}
    comm_dict['de'] = 'de'
    comm_dict['fr'] = 'f7'
    comm_dict['cz'] = 'fx'
    comm_dict['sk'] = 'fy'
    comm_dict['hu'] = 'f9'
    comm_dict['it'] = 'fd'
    comm_dict['nord'] = 'fb'
    comm_dict['be'] = 'q1'
    comm_dict['nl'] = 'q0'
    comm_dict['deat'] = 'f1'
    comm_dict['es'] = 'fe'
    comm_dict['ro'] = 'fh'
    comm_dict['bg'] = 'fh'
    comm_dict['at'] = 'at'
    comm_dict['si'] = 'fv'
    comm_dict['ttf'] = 'PTT'
    comm_dict['gas_da'] = ['ttfda']
    comm_dict['coal'] = 'atw'
    comm_dict['eua'] = 'feua'
    comm_dict['dk'] = 'eno'
    comm_dict['dkw'] = 'lcph'
    comm_dict['dke'] = 'larh'
    return comm_dict[market].upper()

def contracts_numbers_mapping(market):
    comm_dict = {}
    comm_dict['de'] = [5,11,8,5]
    comm_dict['fr'] = [5,11,8,4]
    comm_dict['cz'] = [3,5,4,4]
    comm_dict['sk'] = [3,4,4,None]
    comm_dict['hu'] = [3,4,4,4]
    comm_dict['it'] = [4,6,6,4]
    comm_dict['nord'] = [4,7,6,5]
    comm_dict['be'] = [4,7,6,None]
    comm_dict['nl'] = [4,7,6,3]
    comm_dict['deat'] = [4,7,6,5]
    comm_dict['es'] = [4,7,6,5]
    comm_dict['ro'] = [4,4,4, 4]
    comm_dict['bg'] = [4,7,6,None]
    comm_dict['at'] = [4,7,6,5]
    comm_dict['si'] = [4,7,6,None]
    comm_dict['ttf'] = [5,11,8, None]
    comm_dict['eua'] = [5] + [None] * 3
    comm_dict['dk'] = [4,7,6,None]
    comm_dict['dkw'] = [4,7,6,None]
    comm_dict['dke'] = [4,7,6,None]

    return comm_dict[market]

def start_code(month_num):
    ten_dict = {}
    ten_dict[1] = 'f'
    ten_dict[2] = 'g'
    ten_dict[3] = 'h'
    ten_dict[4] = 'j'
    ten_dict[5] = 'k'
    ten_dict[6] = 'm'
    ten_dict[7] = 'n'
    ten_dict[8] = 'q'
    ten_dict[9] = 'u'
    ten_dict[10] = 'v'
    ten_dict[11] = 'x'
    ten_dict[12] = 'z'
    return ten_dict[month_num].upper()

def from_code_to_month_number(month_code):
    ten_dict = {
        'f': 1,
        'g': 2,
        'h': 3,
        'j': 4,
        'k': 5,
        'm': 6,
        'n': 7,
        'q': 8,
        'u': 9,
        'v': 10,
        'x': 11,
        'z': 12
    }
    return ten_dict[month_code.lower()]

import datetime


COLUMNS_MAPPING = {
    "SETTLE": "settlement_price",
    # "First Delivery Day": "delivery_start",
    # "Last Delivery Day": "delivery_end",
    "OPEN_PRC": "open_price",
    "HIGH_1": "high_price",
    "LOW_1": "low_price",
    "TRDPRC_1": "last_price",
    "VOL": "traded_lots",
    "OPINT_1": "open_interest_lots",
    "Date": "datetime"
    # "Delivery": "delivery",
    # "Product": "product_type"
}

BASE_PEAK_MAPPING = {
    'B': 'Base',
    'F': 'Base',
    'Z': 'Base',
    'P': 'Peak'
}

PRODUCT_MAPPING = {
    'M': 'Month',
    'Q': 'Quarter',
    'Y': 'Year',
    'S': 'Season'
}

 
        
        
    
def last_fcst_date(country, db):    
    
    schema_name = "futures"
    table_name = str(country)
    sql_query = f"""
    SELECT MAX(datetime) AS latest_date
    FROM "{schema_name}"."{table_name}";
    """
    try:
        a = db.execute(sql_query)
        return pd.to_datetime(a.iloc[0].dt.date.values[0]), True
    except Exception as e:
        print(e, "Empty database")
        return None, False
    
def create_rics(country):
    market = fwd_mkt_code(country)
    rics_list = []
    for delivery in ['B', 'P', 'F', '']:

        if delivery in ['F']:
            if country not in ['ttf']:
                continue
            else:
                pass
        elif delivery in ['B', 'P']:
            if country in ['ttf', 'eua']:
                continue
        elif  delivery in ['']:
            if country in ['eua']:
                rics_list.extend([f"{market}c{str(a)}" for a in range(1, 24)])
                return rics_list
            else:
                continue
        year_range, quarter_range, month_range, week_range = contracts_numbers_mapping(country)
        if delivery in ['P']:
            if country in ['nl', 'cz']:
                week_range = None
            elif country in ['be', 'ro', 'es']:
                continue
        if delivery in ['P']:
            if country in ['it']:
                year_range = 1
                quarter_range = 4
                month_range = 4
                
        rics_list.extend([f"{market}{delivery}Yc{str(a)}" for a in range(1, year_range +1)])
        rics_list.extend([f"{market}{delivery}Qc{str(a)}" for a in range(1, quarter_range +1)])
        

        rics_list.extend([f"{market}{delivery}Mc{str(a)}" for a in range(1, month_range+1)])
        if week_range:
            if delivery in ['P']:
                if country in ['it']:
                    delivery = 'PP'
            rics_list.extend([f"{market}{delivery}c{str(a)}"
                        for a in range(1, week_range+1)])
            
    return rics_list
    
def get_first_del_date(date_series, freq_series):
    """
    Adjusts the dates based on the given frequency:
    - 'Month'   → First day of the same month
    - 'Quarter' → First day of the next month
    - 'Year'    → First day of the next month
    - 'Week'    → Monday of the previous week

    Parameters:
        date_series (pd.Series): Series of datetime dates (ensured conversion).
        freq_series (pd.Series): Series with values ('Month', 'Quarter', 'Year', 'Week').

    Returns:
        pd.Series: Adjusted dates.
    """
    # Ensure date_series is a Pandas Series and convert to datetime
    date_series = pd.to_datetime(date_series, errors='coerce')

    # Ensure freq_series is a Series (avoid TypeError when indexing)
    if not isinstance(freq_series, pd.Series):
        freq_series = pd.Series(freq_series)

    del_start = pd.Series(
        np.where(
            freq_series == 'Month', 
            pd.to_datetime(date_series.dt.strftime('%Y-%m-01')),  # First day of the same month
            
            np.where(freq_series.isin(['Quarter', 'Year']), 
                     pd.to_datetime((date_series + pd.DateOffset(months=1)).dt.strftime('%Y-%m-01')),  # First day of next month
                     
                     date_series - pd.to_timedelta(date_series.dt.weekday + 7, unit='D')  # 🔥 Monday of previous week
            )
        ),
        index=date_series.index  # Keep original index
    )
    del_end = pd.Series(
        np.where(
            freq_series == 'Month',
            del_start + pd.DateOffset(months=1, days=-1),
            np.where(
                freq_series == 'Quarter',
                del_start + pd.DateOffset(months=3, days=-1),
                np.where(
                    freq_series == 'Year',
                    del_start + pd.DateOffset(months=12, days=-1),
                    del_start + dt.timedelta(days=6)
                )
            )
        ),
        index=date_series.index  # Keep original index
    )

    return pd.concat([del_start, del_end],keys=['delivery_start', 'delivery_end'],
                     axis=1)


def fetch_fut_data(country_list):
    with Database() as db:
        for country in country_list:
            last_date, table_exists = last_fcst_date(country, db)
            data_end_date = dt.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

            # Create RICs list
            # 6 months/
            rics_list = create_rics(country=country)

            # Fetch data from refinitiv
            rd.open_session()

            last_date -= dt.timedelta(days=6)

            fields = ["EXPIR_DATE","SETTLE","HIGH_1",
                            "LOW_1","OPEN_PRC","TRDPRC_1",
                            "ACVOL_UNS","BLKVOLUM","OPINT_1"]
            if country in 'ttf':
                fields.remove("BLKVOLUM")

            df = rd.get_history(
                    universe=rics_list,
                    fields=fields,
                    start=last_date.strftime("%Y-%m-%d"),
                    end=data_end_date.strftime("%Y-%m-%d")
                ).infer_objects(copy=False).astype(float)
            
            
            
            df = df.sort_index(axis=1).stack(level=0, future_stack=True).reset_index().copy()
            df['EXPIR_DATE'] = pd.to_datetime(
                    pd.to_numeric(df['EXPIR_DATE'], errors='coerce').astype('Int64').astype(str),
                    format='%Y%m%d',
                    errors='coerce'
                )

            # Extract the product type
            # Aux extraction of product reference
            aux_extract = df['level_1'].str.split('c').str[0]
            if country in ['eua']:
                df['product_type'] = 'Dec'
                df['delivery'] = 'Base'
            else:
                df['product_type'] = np.where(aux_extract.str[-1].isin(['B', 'P']),
                                    'Week',
                                    aux_extract.str[-1].map(PRODUCT_MAPPING))
                mask = aux_extract.str.endswith(('M', 'Q', 'Y'))
                df['delivery'] = aux_extract.str[-2]
                df.loc[~mask, 'delivery'] = aux_extract.str[-1]
                df['delivery'] = df['delivery'].map(BASE_PEAK_MAPPING)
            
            df[['delivery_start',
                'delivery_end']] = get_first_del_date(date_series=df['EXPIR_DATE'],
                                                      freq_series=df['product_type'])
            # if country in ['eua']:
            #     df = df.loc[df['delivery_start'].dt.month == 12].copy()
            if "BLKVOLUM" not in fields:
                df["BLKVOLUM"] = 0
            df['VOL'] = df['ACVOL_UNS'] - df['BLKVOLUM']

            df = df.drop(['ACVOL_UNS', 'BLKVOLUM', 'EXPIR_DATE', 'level_1'],
                         axis=1).copy()

            df = df.rename(columns=COLUMNS_MAPPING)

            last_date += dt.timedelta(days=6)
            df = df.loc[df['datetime'] > last_date].copy()
            if country in ['ttf']:
                df = df.loc[df['datetime']<df['delivery_start']].copy()

            df.to_sql(
                name="stage_" + country,
                schema="futures",
                con=db.connection_string,
                if_exists='replace', index=False
            )
            db.merge_from_staging_to_prod("futures", country)

        # Drop all duplicates
        # Create the connection string using your function:
        conn_str = db.connection_string

        # Now define the DO block as a multi-line string.
        do_block = """
        DO $$
        DECLARE
            tbl TEXT;
            col_list TEXT;
            sql TEXT;
            tbl_list TEXT[] := ARRAY[
            'at','be','cz','de','es','eua','fr','hu','it','nl','ro','sk','ttf'
            ];
        BEGIN
        FOREACH tbl IN ARRAY tbl_list LOOP
            -- Retrieve a comma-separated list of all column names for the table, ordered by ordinal_position
            SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
            INTO col_list
            FROM information_schema.columns
            WHERE table_schema = 'futures'
            AND table_name = tbl;
            
            IF col_list IS NULL THEN
            RAISE NOTICE 'No columns found for table % in schema futures', tbl;
            ELSE
            -- Build the dynamic SQL: use col_list in the PARTITION BY clause
            sql := format($f$
                WITH duplicates AS (
                SELECT ctid,
                        ROW_NUMBER() OVER (PARTITION BY %s ORDER BY ctid) AS rn
                FROM futures.%I
                )
                DELETE FROM futures.%I t
                USING duplicates
                WHERE t.ctid = duplicates.ctid
                AND duplicates.rn > 1;
            $f$, col_list, tbl, tbl);
            
            RAISE NOTICE 'Executing: %', sql;
            EXECUTE sql;
            END IF;
        END LOOP;
        END $$;
        """

        # Create an SQLAlchemy engine using your connection string:
        engine = create_engine(conn_str)

        # Connect to the database and execute the DO block:
        with engine.begin() as conn:
            # The text() function ensures the DO block is treated as raw SQL text.
            conn.execute(text(do_block))


if __name__=='__main__':
    # Example usage
    country = "DE"
    start_date = datetime.date(2025, 4, 8)
    end_date = datetime.date(2025, 6, 30)

    fetch_fut_data(['ttf'])

    # contracts = fetch_fut_data(['de', 'fr', 'at', 'nl', 'be',
    #                             'it', 'hu', 'ro', 'es', 'cz', 'sk','ttf', 'eua'])
    # print(contracts)


