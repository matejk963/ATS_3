# -*- coding: utf-8 -*-
"""
Created on Thu Sep 28 08:26:51 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from datetime import time
import os
from dateutil.relativedelta import relativedelta

from scipy.stats import skew, kurtosis

from RiskPremium.RP_Tools import TP_trades_data as TPT, vwap_from_tp_trades, ttf_settle_data
from Loaders.EikonFut_class import EikonFut as EF
from Loaders.RLD_fetch import RLDDatabaseData as RLDD
from Database import DB_reader as dbr
from Loaders.AvCapFetch_rel_class import AvCapFetch as ACF

import refinitiv.data as rd

from Database.TPData import TPData
import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass


"""
get index range for model data
"""
index_range = pd.read_csv(r's:\Algo\Database\Model Data\wa_model_date_index.csv',
                          index_col=0).index

"""
get weekly trades
"""

mkt_list = ['de']
tenor_list = ['w']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = dt.datetime(2020, 1, 1)
end_date = dt.datetime(2023, 9, 15)
n_s = 2

tr_data_dict = TPT(mkt_list=mkt_list,
                              tenor_list=tenor_list,
                              tn_list=tn_list,
                              prod=prod,
                              start_date=start_date,
                              venue_list=venue_list,
                              end_date=end_date,
                              n_s=n_s)

vwap_dict = vwap_from_tp_trades(tr_data_dict,
                                from_time=time(9,30,0))
vwap = vwap_dict['dew1']

database = dbr.Database()
spot = database.getSpotPriceData(['de'], _from=start_date.strftime('%Y-%m-%d'),
                                 _to=(end_date+
                                      dt.timedelta(days=10)).strftime('%Y-%m-%d'))

df1 = vwap.copy()
df2 = spot.copy()

result = []

for sd in df1.index:
    # Define the week ahead start and end dates based on sd
    wa_sd = sd + pd.Timedelta(days=7 - sd.weekday())
    wa_ed = wa_sd + pd.Timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    # Get average for the week ahead from df2
    week_values = df2.loc[wa_sd:wa_ed]
    avg_value = week_values.mean().values[0]

    result.append(avg_value)

spot_wa = pd.DataFrame(result, index=df1.index, columns=['week_ahead_avg'])

print(spot_wa.tail(10))

wa_prices = pd.concat([vwap, spot_wa],axis=1, join='inner')
wa_prices.columns = ['vwap_wa', 'spot_wa']
wa_prices['long'] = np.where(wa_prices['vwap_wa']<wa_prices['spot_wa'],
                             1,0)

date_range = pd.date_range(start=start_date,
                           end=end_date,
                           freq='MS', inclusive='neither')

month_list = date_range.month.to_list()
month_list.append((date_range[-1]+relativedelta(months=1)).month)

year_list = date_range.year.to_list()
year_list.append((date_range[-1]+relativedelta(months=1)).year)

month_list2 = month_list
month_list2.insert(0,1)
year_list2 = year_list
year_list2.insert(0,2020)

# 'de','coal', 'gas',
avg_months = {}
for market in [ 'de','coal', 'gas','eua']:
    obj = EF(market)
    gen_list = []
    for month, year in zip(month_list2,
                           year_list2):
        month_start = dt.datetime(year,month,1)
        temp = pd.DataFrame(obj.fwd_df(sD=month_start-relativedelta(months=3),
                            eD=month_start,
                            product_list=['M.'+str(month)],
                            delivery_list=['base'],
                            year_list=[year]))
        price_name = 'M.'+str(month) + '_' + str(year)
        
        gen_list.append(temp.expanding().mean().iloc[-1].item())
    avg_months[market] = gen_list
    
avg_prices_df = pd.DataFrame(avg_months)
avg_prices_df['month'] = month_list
avg_prices_df['year'] = year_list
    
def fetch_and_average(row, df1):
    start_date = row.name + pd.DateOffset(days=5)
    end_date = start_date + pd.DateOffset(days=6)
    
    # List to store prices from multiple days
    prices = []
    
    current_date = start_date
    while current_date <= end_date:
        mask = (df1['year'] == current_date.year) & (df1['month'] == current_date.month)
        relevant_data = df1[mask]
        prices.append(relevant_data[['de', 'coal', 'gas', 'eua']])
        current_date += pd.DateOffset(days=1)
    
    # Concatenate the prices and then take the average
    all_prices = pd.concat(prices)
    return all_prices.mean()

# Apply function to df2
averaged_data = wa_prices.apply(fetch_and_average,df1 = avg_prices_df, axis=1)

# Merge the averaged data into df2
df2 = pd.concat([wa_prices, averaged_data], axis=1)

print(df2)  
    
ttf_week_settle = ttf_settle_data(sD=df2.index[0],
                                  eD=df2.index[-1])
rd.open_session()
eua_cont = rd.get_history(universe=['CFI2Zc1'],
                          fields=['TRDPRC_1', 'SETTLE',
                                  'OPEN_PRC', 'HIGH_1', 'LOW_1'],
                          interval='1D',
                          start=df2.index[0].strftime('%Y%m%d'),
                          end=df2.index[-1].strftime('%Y%m%d')).astype(float)
eua_cont = eua_cont.median(axis=1)
eua_cont.name = 'eua_cont'
rd.close_session()

df_prices = pd.concat([df2, ttf_week_settle['ttf'], eua_cont], axis=1,join='inner')

df_prices['ghr_wa'] = df_prices['vwap_wa']/(df_prices['ttf']+df_prices['eua_cont']*0.2)
df_prices['ghr_ma'] = df_prices['de']/(df_prices['gas']+df_prices['eua']*0.2)

"""
monthly vwap
"""

"""
get fuels and euas
"""




# obj.fwd_df(sD=month_start-relativedelta(months=2),
#                     eD=month_start,
#                     product_list=['M.'+str(month)],
#                     delivery_list=['base'],
#                     year_list=[year])

fuels_dict = {}
for market in ['coal', 'gas', 'eua']:
    obj = EF(market)
    market_df = pd.DataFrame()
    if market not in ['eua']:
        for month, year in zip(month_list,
                               year_list):
            month_start = dt.datetime(year,month,1)
            temp = obj.fwd_df(sD=month_start-relativedelta(months=2),
                                eD=month_start,
                                product_list=['M.'+str(month)],
                                delivery_list=['base'],
                                year_list=[year])
            price_name = 'M.'+str(month) + '_' + str(year)
            temp.columns = [price_name]
            if market_df.empty:
                market_df = temp.copy()
            else:
                market_df = pd.concat([market_df, temp], axis=1)
        fuels_dict[market] = market_df.copy()
    else:
        for year in year_list:
            month_start = dt.datetime(year,12,1)
            temp = obj.fwd_df(sD=month_start-relativedelta(months=12),
                                eD=month_start,
                                product_list=['M.12'],
                                delivery_list=['base'],
                                year_list=[year])
            price_name = 'M.12_' + str(year)
            temp.columns = [price_name]
            if market_df.empty:
                market_df = temp.copy()
            else:
                market_df = pd.concat([market_df, temp], axis=1)
            
        fuels_dict[market] = market_df.copy()
        

updated_fuels_dict = {}
for market in fuels_dict.keys():
    temp = fuels_dict[market].copy()
    temp = temp.fillna(method='bfill', axis=1)
    temp = temp.iloc[:,:2].copy()
    temp.columns = ['F1', 'F2']
    updated_fuels_dict[market] = temp.copy()
    


def fetch_values(date, df, x=7):
    # Check if the date is less than 5 days from the end of the month
    last_date_of_month = pd.Timestamp(date.year, date.month, 1) + pd.DateOffset(months=1) - pd.DateOffset(days=1)
    if (last_date_of_month - date).days < 5:
        col = 'F2'
    else:
        col = 'F1'
        
    # Extract a window of data up to the provided date
    window = df[col].loc[:date].tail(x).tolist()
    # If there are fewer than x values available, we'll fill the rest with NaN
    while len(window) < x:
        window.insert(0, float('nan'))
    
    return window

days = 7
fuels_train_dict = {}
for market in updated_fuels_dict.keys():
    temp = updated_fuels_dict[market].copy()
    # Fetch values for each date in the date range and store in a list
    data_list = [fetch_values(date,temp, x=days) for date in vwap.index]
    
    # Convert the list to a DataFrame
    result_df = pd.DataFrame(data_list, index=vwap.index,
                             columns=[f'Day-{i}' for i in range(days, 0, -1)])
    fuels_train_dict[market] = result_df.copy()

fuels_train_dict


def fetch_values(date, df, column, x=7):
    # Extract a window of data from the given column up to the provided date
    window = df[column].loc[:date].tail(x).tolist()
    # If there are fewer than x values available, we'll fill the rest with NaN
    while len(window) < x:
        window.insert(0, float('nan'))
    
    return window

days = 7
ghr_dict = {}
columns_to_process = ['ghr_wa', 'ghr_ma']  # specify the columns you want to process

for col in columns_to_process:
    # Fetch values for each date in the date range and store in a list
    data_list = [fetch_values(date, df_prices, col, x=days) for date in df_prices.index]
    
    # Convert the list to a DataFrame
    result_df = pd.DataFrame(data_list, index=df_prices.index,
                             columns=[f'{col}_Day-{i}' for i in range(days, 0, -1)])
    ghr_dict[col] = result_df.dropna().copy()





"""
get rld data
"""

rld_data = RLDD()
rld_df = rld_data.getResWeekAhead(start_date, end_date)
# Expand the lists into columns
rld_train = rld_df['values'].apply(pd.Series)
rld_norm = rld_data.getResNormals(start_date, end_date)

# Rename the columns
rld_train.columns = [f"Value_{i+1}" for i in range(rld_train.shape[1])]

rld_da = rld_data.getResDayAhead(start_date, end_date)

"""
get day ahead rld forecast for week ahead forecast to compare the change in rld
"""

rld_wa_mean = rld_train.mean(axis=1)
rld_wa_mean.name = 'rld_wa_mean'
df1 = rld_da
df2 = pd.DataFrame(rld_wa_mean)

# For each date in df2, get week ahead values from df1
for date in df2.index:
    week_ahead_end_date = date + pd.DateOffset(days=6)
    week_values = df1.loc[date:week_ahead_end_date]['values'].tolist()
    
    # Flatten the lists to get all values for the week
    week_values_flat = [val for sublist in week_values for val in sublist]
    
    # Compute the mean and add to df2
    df2.at[date, 'Mean_Values'] = sum(week_values_flat)/len(week_values_flat)

df2.columns = ['rld_wa_mean', 'real_rld_wa_mean']
rld_wa_w_real = df2.copy()

"""
get week ahead normals df
"""
def extract_week_ahead(base_date, df2):
    base_date = pd.Timestamp(base_date.date())
    
    # Calculate the days to the next Monday. If today is Monday, we start from today.
    days_to_next_monday = (7 - base_date.weekday())
    
    start_date = base_date + pd.DateOffset(days=days_to_next_monday)
    end_date = start_date + pd.DateOffset(days=7)
    
    mask = (df2.index >= start_date) & (df2.index < end_date)
    return df2[mask].T

week_ahead_data = []

for date in rld_train.index:
    week_ahead = extract_week_ahead(date, rld_norm)
    week_ahead_data.append(week_ahead.values.tolist()[0])

rld_wa_normal = pd.DataFrame(week_ahead_data, index=rld_train.index).dropna()


def roll_and_concat(df, column_name, window_size):
    """
    Rolls over a DataFrame column containing lists and concatenates them based on the window size.

    Parameters:
    - df: The input DataFrame
    - column_name: The name of the column containing lists
    - window_size: The rolling window size

    Returns:
    - A new DataFrame with rolled and concatenated lists split into separate columns
    """

    # This function will be applied to the rolling windows
    def concat_lists(sub_df):
        # Concatenate the lists within the window
        return sum(sub_df[column_name].tolist(), [])

    concatenated_lists = []

    # Iterate over the DataFrame in steps of 1, applying the rolling operation manually
    for start in range(0, len(df) - window_size + 1):
        end = start + window_size
        concatenated_lists.append(concat_lists(df.iloc[start:end]))

    # Convert concatenated lists to a DataFrame and split each list into separate columns
    result_df = pd.DataFrame(concatenated_lists)

    # Adjust the index to align with the original DataFrame's index offset by window_size - 1
    result_df.index = df.index[window_size - 1:]

    return result_df


rld_da_roll = roll_and_concat(rld_da,'values', 7)

df1 = rld_da_roll.copy()
df2 = rld_norm.copy()

def extract_past_week(base_date, df2):
    end_date = pd.Timestamp(base_date) + pd.DateOffset(hours=23)
    start_date = end_date - pd.DateOffset(days=6, hours=23)
    mask = (df2.index >= start_date) & (df2.index <= end_date)
    return df2[mask].T

past_week_data = []

for date in df1.index:
    past_week = extract_past_week(date, df2)
    past_week_data.append(past_week.values.tolist()[0])

rld_da_norm = pd.DataFrame(past_week_data, index=df1.index).dropna()

"""
get rld to norm data
"""

def act_to_norm(df1, df2):
    #df1 should be actual value
    #df2 should be normal value
    common_indices = df1.index.intersection(df2.index)
    
    df1_filtered = df1.loc[common_indices]
    df1_filtered.columns = [a for a in range(len(df1_filtered.columns))]
    df2_filtered = df2.loc[common_indices]
    df2_filtered.columns = [a for a in range(len(df2_filtered.columns))]
    
    return df1_filtered/df2_filtered


wa_rld_to_norm = act_to_norm(rld_train,rld_wa_normal)
da_rld_to_norm = act_to_norm(rld_da_roll,rld_da_norm)


"""
Getting statistcal moments from rld predictions
"""

def compute_moments(df):
    """
    Compute the 1st to 4th moments for each row in a DataFrame.
    
    Parameters:
    - df: Input DataFrame.

    Returns:
    - DataFrame with computed moments for each row.
    """
    
    moments = pd.DataFrame()
    
    # 1st moment: Mean
    moments['Mean'] = df.mean(axis=1)
    
    # 2nd moment: Variance
    moments['Variance'] = df.var(axis=1)
    
    # 3rd moment: Skewness
    moments['Skewness'] = df.apply(lambda x: skew(x.dropna()), axis=1)
    
    # 4th moment: Kurtosis
    moments['Kurtosis'] = df.apply(lambda x: kurtosis(x.dropna()), axis=1)

    return moments

wa_moments = compute_moments(wa_rld_to_norm)
da_moments = compute_moments(da_rld_to_norm)


"""
get av capacity for germany
"""

# FTP details
FTP_SERVER = r'pointconnect.commodities.refinitiv.com'  # Replace with your FTP server
USERNAME = "krajcovic_matej@energytrading.sk"      # Replace with your FTP username
PASSWORD = "kmfT5Q$kw"     # Replace with your FTP password

FTP_DIRECTORY_hist = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
FTP_DIRECTORY_live = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/' 

#substring
substring = '5044791_Pwr_PCA_PRO_AvailCap_EEX_REMIT_E1_DEU_F'

forecast_start_date = index_range[0]
forecast_end_date = index_range[-1]

manager = ACF(ftp_server=FTP_SERVER, 
                         username=USERNAME, 
                         password=PASSWORD)

# Set directories where the data is stored
manager.set_directories(directory_hist=FTP_DIRECTORY_hist, 
                        directory_live=FTP_DIRECTORY_live)

# Set substring to look for in live directory files
manager.set_substring(substring=substring)

cut_off_time = '12:00:00'

# Set forecast date range and cut-off time
manager.set_forecast_dates(start_date=forecast_start_date, 
                           end_date=forecast_end_date,
                           cut_off_time=cut_off_time)



av_cap_dict = {}
for date_range_type in ['day_ahead', 'week_ahead']:
    av_cap_dict[date_range_type] = {}
    for asset in ['gas', 'coal', 'lig']:
        manager.set_asset_id(asset)
        av_cap_dict[date_range_type][asset] = manager.to_hourly_series(date_range_type=date_range_type)
    

        
av_cap_df_dict = {}
for date_range_type in ['day_ahead', 'week_ahead']:
    av_cap_df_dict[date_range_type] = {}
    for asset in ['gas', 'coal']:
        data_dict = av_cap_dict[date_range_type][asset]
        dfs = [pd.DataFrame(data.T.values, index=[key]) for key, data in data_dict.items()]

        # Concatenate all single-row DataFrames
        temp = pd.concat(dfs)
        temp.fillna(method='ffill', axis=1, inplace=True)
        temp.fillna(method='bfill', axis=1, inplace=True)
        temp.fillna(method='ffill', axis=0, inplace=True)
        av_cap_df_dict[date_range_type][asset] = temp.copy()

av_cap_wa_hist = {}
for asset in ['gas','coal']:
    print(asset)
    df = av_cap_df_dict['day_ahead'][asset].copy()
    # Iterate over the DataFrame's index, starting from the 8th date
    rows = []
    dates = df.index
    for i in range(7, len(dates)):
        # Extract rows for the current date and the 7 previous days
        last_8_days_data = df.loc[dates[i-7:i]].values.flatten()
        rows.append(last_8_days_data)
    
    # Convert the list of new rows into a new DataFrame
    av_cap_wa_hist[asset] = pd.DataFrame(rows, index=dates[7:])
    

av_cap_wa_hist_df = pd.concat(av_cap_wa_hist.values(), axis=1, join='inner')

av_cap_wa_hist_df.index = pd.to_datetime(av_cap_wa_hist_df.index)

av_gas_wa_fct_df = av_cap_df_dict['week_ahead']['gas']
av_gas_wa_fct_df.index = pd.to_datetime(av_gas_wa_fct_df.index)

av_coal_wa_fct_df = av_cap_df_dict['week_ahead']['coal']
av_coal_wa_fct_df.index = pd.to_datetime(av_coal_wa_fct_df.index)

av_cap_wa_fct_df = pd.concat(av_cap_df_dict['week_ahead'].values(), axis=1, join='inner')
av_cap_wa_fct_df.index = pd.to_datetime(av_cap_wa_fct_df.index)

av_cap_fct_moments = compute_moments(av_cap_wa_fct_df)
av_cap_hist_moments = compute_moments(av_cap_wa_hist_df)
            

"""
putting all data together and creating single matrices
"""

insp_df = pd.concat([df_prices, rld_wa_w_real],axis=1,join='inner')

all_df = pd.concat([wa_prices, fuels_train_dict['gas'],
                    fuels_train_dict['coal'],
                    fuels_train_dict['eua'],
                    rld_train, rld_da_roll,
                    df_prices[ 'ghr_ma'],
                    ghr_dict['ghr_wa'],
                    rld_wa_w_real,
                    wa_moments,
                    da_moments,
                    wa_rld_to_norm,
                    da_rld_to_norm,
                    av_gas_wa_fct_df,
                    av_coal_wa_fct_df],axis=1,join='inner')

all_df = pd.read_csv(r's:\Algo\Database\Model Data\wa_model_date_index.csv',
                          index_col=0, parse_dates=True)
all_df = pd.concat([all_df,
                    av_cap_wa_hist_df,
                    av_cap_wa_fct_df,
                    av_cap_fct_moments,
                    av_cap_hist_moments,
                    av_gas_wa_fct_df,
                    av_coal_wa_fct_df],axis=1,join='inner')

all_df.replace([np.inf, -np.inf], np.nan, inplace=True)
all_df.dropna(inplace=True)

wa_prices.replace([np.inf, -np.inf], np.nan, inplace=True)
wa_prices.dropna(inplace=True)

# long_arr = np.array(wa_prices['long'].loc[all_df.index])
long_arr = np.array(all_df['long'].loc[all_df.index])
pnl_arr = np.array(abs(wa_prices['vwap_wa']/wa_prices['spot_wa']-1).loc[all_df.index])
long_half_std_arr = np.where(pnl_arr>0.1,
                             long_arr,0.5)

conditions = [long_half_std_arr == 0,
              long_half_std_arr== 0.5,
              long_half_std_arr== 1]

choices = [-1,0,1]

long_half_std_arr = np.select(conditions, choices)

wa_prices_arr = np.array(wa_prices['vwap_wa'].loc[all_df.index])
wa_spot_arr = np.array(wa_prices['spot_wa'].loc[all_df.index])

wa_ghr_arr = np.array(ghr_dict['ghr_wa'].loc[all_df.index])
ma_ghr_arr = np.array(df_prices['ghr_ma'].loc[all_df.index])

gas_arr = np.array(fuels_train_dict['gas'].loc[all_df.index])
coal_arr = np.array(fuels_train_dict['coal'].loc[all_df.index])
eua_arr = np.array(fuels_train_dict['eua'].loc[all_df.index])
wa_rld_arr = np.array(rld_train.loc[all_df.index])
da_rld_arr = np.array(rld_da_roll.loc[all_df.index])

wa_moments_arr = np.array(wa_moments.loc[all_df.index])
da_moments_arr = np.array(da_moments.loc[all_df.index])

wa_rld_to_norm_arr = np.array(wa_rld_to_norm.loc[all_df.index])
da_rld_to_norm_arr = np.array(da_rld_to_norm.loc[all_df.index])

av_gas_wa_fct_df_arr = np.array(av_gas_wa_fct_df.loc[all_df.index])
av_coal_wa_fct_df_arr = np.array(av_coal_wa_fct_df.loc[all_df.index])

av_cap_wa_hist_df_arr = np.array(av_cap_wa_hist_df.loc[all_df.index])
av_cap_wa_fct_df_arr = np.array(av_cap_wa_fct_df.loc[all_df.index])

av_cap_fct_moments_arr = np.array(av_cap_fct_moments.loc[all_df.index])
av_cap_hist_moments_arr = np.array(av_cap_hist_moments.loc[all_df.index])

gas_to_rld_av_cap_arr = av_gas_wa_fct_df_arr/wa_rld_arr
coal_to_rld_av_cap_arr = av_coal_wa_fct_df_arr/wa_rld_arr


gas_mc_arr = gas_arr + eua_arr*0.2
coal_mc_arr = coal_arr/8.14 + eua_arr*0.32

mcr_arr = gas_mc_arr/coal_mc_arr


arrays = [long_arr, wa_prices_arr,wa_spot_arr,
          gas_arr, eua_arr,long_half_std_arr,
          wa_rld_arr,
          da_rld_arr,
          wa_ghr_arr,
          ma_ghr_arr,
          mcr_arr,
          wa_moments_arr,
          da_moments_arr,
          wa_rld_to_norm_arr,
          da_rld_to_norm_arr]
arrays = [long_arr,
          wa_moments_arr,
          da_moments_arr,
          wa_rld_to_norm_arr,
          da_rld_to_norm_arr,
          av_cap_wa_hist_df_arr,
            av_cap_wa_fct_df_arr,
            av_cap_fct_moments_arr,
            av_cap_hist_moments_arr]

arrays = [gas_to_rld_av_cap_arr]

arrays = [gas_to_rld_av_cap_arr,
          coal_to_rld_av_cap_arr,
          av_gas_wa_fct_df_arr,
          av_coal_wa_fct_df_arr]


# arrays = [long_arr]
path = "s:/Algo/Database/Model Data/"
# Create a copy of the global dictionary
global_items = list(globals().items())

# IDs of arrays in the list for comparison
array_ids = [id(arr) for arr in arrays]

# Loop through the copied global dictionary
for name, array in global_items:
    # Compare using id
    if id(array) in array_ids:
        filename = f"{path}{name}.txt"
        np.savetxt(filename, array)
        
all_df.to_csv(r's:\Algo\Database\Model Data\wa_model_date_index.csv', index=True)



