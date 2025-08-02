import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from Database.DB_reader import Database

from Utilities.fund_analysis.fund_analysis import input_data

db = Database()


# Params dict where base_products, market_list, delivery_dict and eD should be selected
# Feel free to set eD as fcst_date later in the code
base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'M_4', 'M_5',
                 'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7',
                 'Y_1', 'Y_2']
market_list = ['de', 'fr']
delivery_dict = ['base', 'peak']

# Generate the combinations
products = []
markets = []
delivery = []

for product in base_products:
    for market in market_list:
        for delivery_option in delivery_dict:
            products.append(product)
            markets.append(market)
            delivery.append(delivery_option)

params_dict = {}
params_dict['product_list'] = products
params_dict['market_list'] = markets
params_dict['delivery_list'] = delivery
params_dict['year_list'] = [None] * len(params_dict['market_list'])

params_dict['sD'] = dt.datetime(2020,1,1)
params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
params_dict['eD'] = dt.datetime(2025,3,12)
params_dict['ns'] = 2
params_dict['cont'] = False

id_inst = input_data.Gas(params_dict)

eua_inst = input_data.Eua(params_dict)


product_data = pd.DataFrame([ id_inst.original_params_dict['product_list'],
                    id_inst.params_dict['market_list'],
                        id_inst.params_dict['delivery_list'],
                        id_inst.start_date_list,
                        id_inst.end_date_list], index=['product', 'market', 'del_type',
                        'delivery_start', 'delivery_end']).T
product_data['delivery_start'] = pd.to_datetime(product_data['delivery_start'])
product_data['delivery_end'] = pd.to_datetime(product_data['delivery_end']) + dt.timedelta(hours=1, seconds=-1)

# Function for query creation for database
def create_query(df, query_cols=None, table='schema.table', additional_condition=""):
    # Use default columns if no specific columns are provided.
    if query_cols is None:
        if table.split('.')[0] == 'futures':
            query_cols = ['delivery', 'delivery_start', 'delivery_end']
        else:
            query_cols = ['market', 'del_type', 'delivery_start', 'delivery_end']
    
    # Extract the relevant columns and drop duplicates.
    unique_rows = df[query_cols].drop_duplicates()
    
    # Build a comma-separated list of tuple strings for the SQL IN clause.
    values_list = [
        "(" + ", ".join(f"'{row[col]}'" for col in query_cols) + ")"
        for _, row in unique_rows.iterrows()
    ]
    values_str = ", ".join(values_list)
    
    # Build the list of column names.
    columns_str = ", ".join(query_cols)
    
    # Construct the base SQL query.
    query = f"SELECT * FROM {table} WHERE ({columns_str}) IN ({values_str})"
    
    # Append additional condition if provided.
    if additional_condition:
        query += f" AND {additional_condition}"
    
    query += ";"
    return query

# Given model forecast date
fcst_date = '2025-03-24'

# Get query for model forecasts from database
query = create_query(product_data, table='"MODEL_forecast_prices"."xgboost_mean_nominal"',
                     additional_condition=f"scenario_type IN ('base_col') AND fcst_date = '{fcst_date}'")
# Query those furecasted data
df = pd.read_sql(query, con=db.connection_string)
df['delivery_end'] = df['delivery_end'].dt.normalize()

# Get futures data for parameters from params_dict
futures_df = []
for market in df['market'].unique():
    temp = df.loc[df['market']==market].copy()
    temp.rename(columns={'del_type': 'delivery'},inplace=True)
    # temp['delivery_end'] = temp['delivery_end'].dt.normalize()
    temp['delivery'] = temp['delivery'].str.capitalize()
    table_name = f"futures.{market}"
    query_temp = create_query(temp,['delivery', 'delivery_start', 'delivery_end'], table_name,
                              f"datetime <= '{fcst_date}'")
    temp_df = pd.read_sql(query_temp, con=db.connection_string)
    temp_df = temp_df[['datetime', 'delivery_start', 'delivery_end', 'settlement_price', 'delivery']].copy()
    temp_df = temp_df.loc[temp_df['datetime'] == temp_df['datetime'].max()].copy()
    temp_df['market'] = market
    futures_df.append(temp_df)

futures_df = pd.concat(futures_df,axis=0)
settle_date = futures_df['datetime'].unique()[0]
futures_df.rename(columns={'settlement_price': settle_date,
                           'delivery': 'del_type'}, inplace=True)
futures_df.drop(['datetime'],axis=1,inplace=True)
futures_df['del_type'] = futures_df['del_type'].str.lower()

# Function for computing average price for period from fuel curves
def get_average_values(price_curve, start_dates, end_dates):
    """
    Calculate the average value from a price curve for each start/end date pair.
    
    Parameters:
        price_curve (pd.Series): A pandas Series with datetime index representing the price curve.
        start_dates (list-like): A list (or array) of start dates (as strings or datetime objects).
        end_dates (list-like): A list (or array) of end dates (as strings or datetime objects).
        
    Returns:
        list: A list of average values for each start/end date period.
    """
    # Convert start_dates and end_dates to datetime if they aren't already
    start_dates = pd.to_datetime(start_dates)
    end_dates = pd.to_datetime(end_dates)
    
    averages = []
    for start, end in zip(start_dates, end_dates):
        # Select the subset of the price curve for the period and compute its mean
        subset = price_curve.loc[start:end]
        avg_value = round(subset.mean().iloc[0],2)
        averages.append(avg_value)
        
    return averages

# Create fuels curve
# Eua futures data
eua_inst.set_pivot_date(settle_date)
eua_inst.get_curve(date_shift=0)
eua_list = get_average_values(eua_inst.data_curve['eua'],
                            id_inst.start_date_list,
                            id_inst.end_date_list)
eua_df =pd.DataFrame([id_inst.start_date_list,
                      id_inst.end_date_list,
                      eua_list], index=['delivery_start', 'delivery_end', 'eua']).T
eua_df['delivery_start'] = pd.to_datetime(eua_df['delivery_start'])
eua_df['delivery_end']   = pd.to_datetime(eua_df['delivery_end']).dt.normalize()


#Gas futures data
id_inst.set_pivot_date(settle_date)
id_inst.get_curve(date_shift=0)
gas_list = get_average_values(id_inst.data_curve['ttf'],
                            id_inst.start_date_list,
                            id_inst.end_date_list)
gas_df =pd.DataFrame([id_inst.start_date_list,
                      id_inst.end_date_list,
                      gas_list], index=['delivery_start', 'delivery_end', 'gas']).T
gas_df['delivery_start'] = pd.to_datetime(gas_df['delivery_start'])
gas_df['delivery_end']   = pd.to_datetime(gas_df['delivery_end']).dt.normalize()

# Merge futures data with gas and eua
futures_df = futures_df.merge(gas_df, on=['delivery_start', 'delivery_end'],
                               how='left')
futures_df = futures_df.merge(eua_df, on=['delivery_start', 'delivery_end'],
                               how='left')
# Compute gas heat rate and clean spark spread from futures data
futures_df['ghr'] = futures_df[settle_date]/(futures_df['gas']+futures_df['eua']*0.2)
futures_df['css'] = futures_df[settle_date] - (futures_df['gas']*2 + futures_df['eua']*0.4)


# Put together forecasted values and futures data
df = df.merge(futures_df, on=['delivery_start', 'delivery_end', 'del_type', 'market'], how='left')

# Function to create pivot table for individual markets
def get_pivot_table(df, value_col):
    pivot_df = df.pivot_table(
        index=['rel_product', 'delivery_start', 'delivery_end'],
        columns=['market', 'del_type'],
        values=value_col,
        aggfunc='first'
    )

    # Flatten the MultiIndex columns, e.g. 'de_base', 'fr_peak'
    pivot_df.columns = [f"{market}_{del_type}" for market, del_type in pivot_df.columns]

    # Reset the index so that rel_product and delivery dates become columns.
    pivot_df = pivot_df.reset_index()

    # Calculate the duration (in days) as the difference between delivery_end and delivery_start.
    pivot_df['duration'] = (pivot_df['delivery_end'] - pivot_df['delivery_start']).dt.days

    # Now sort the DataFrame: first by the duration and then by the delivery_start date.
    pivot_df = pivot_df.sort_values(by=['duration', 'delivery_start']).reset_index(drop=True)

    # Optionally, drop the temporary duration column if you don't need it in the final output.
    pivot_df = pivot_df.drop(columns=['duration'])

    return pivot_df

# Get df for value, ghr, css
value_df = get_pivot_table(df, 'value').set_index(['rel_product', 'delivery_start', 'delivery_end'])
ghr_df = get_pivot_table(df, 'ghr').set_index(['rel_product', 'delivery_start', 'delivery_end'])





