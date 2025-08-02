# -*- coding: utf-8 -*-
"""
Created on Fri Jan  5 13:12:42 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, time
import datetime as dt
import seaborn as sns
from Database.TPData import TPDataAssembly as TDA
from Strategies.IceBergOrders_class import IceBergOrders as IBO
from Math.accumfeatures import EMA
from Strategies.Intensity_class import TradeIntensity as TI
from Strategies.Intensity_class import adjust_datetime_precision
from lifetimes.datasets import load_transaction_data
from lifetimes.utils import summary_data_from_transaction_data
from lifetimes.utils import calibration_and_holdout_data
from lifetimes import BetaGeoFitter
from lifetimes.plotting import plot_frequency_recency_matrix
from lifetimes.plotting import plot_probability_alive_matrix
from lifetimes.plotting import plot_history_alive, plot_history_prediction
from lifetimes.plotting import plot_period_transactions



   
assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 10, 1)
params_dict['end_date'] = datetime(2023, 11, 25)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TDA(source='trayport')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')

assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"

# Go key by key(product by product) in dictionaries and process through Intensity Class
# together to get proper trade side
# Concat the porcessed products to one df
data = pd.DataFrame()
for key in trades_dict.keys():
    trades_aux = trades_dict[key].loc[trades_dict[key]['broker_id']==14].copy()
    ba_aux = ba_dict[key]
    # iInitalize IntClass with each key
    int_inst = TI(trades_aux, ba_aux)
    int_inst.set_conditions()
    data_aux = int_inst.data
    data_aux['id'] = key
    if data.empty:
        data = data_aux.copy()
    else:
        data = pd.concat([data, data_aux])

        

data['bid_ask'] = (data['bidbestprice']-data['askbestprice'])/data['bidbestprice']
data['ba_perc'] = pd.qcut(data['bid_ask'], q=10, labels=False)

test_date = np.unique(data.index.date)[-1]
test_data = data[test_date:].copy()
train_data = data[:test_date].copy()


# Defined function for bucketing the data to desired freq
# Output is basically creating multiple "products" where each freq is separted product
# so that bg/nbd model can fit distribution of trades incomming to the market
# Input should be series/df with datetime index where each row is trade comming to either bid or ask
# the value can be anything basically the timestamps of the trades in series/df format in index are neccesary

def data_time_bucketing(df, freq):
    time_buckets = df.resample(freq).size()

    id_mapping = time_buckets.reset_index().reset_index().rename(columns={'index': 'ID',
                                                                          'datetime': 'floor'})
    id_mapping = id_mapping[['floor', 'ID']]
    df = df.reset_index()


    df['floor'] = df['datetime'].dt.floor(freq)
    df = df.merge(id_mapping, on='floor', how='left')

    df['datetime'] = df['datetime'].dt.floor('S')
    df['time'] = df['datetime'] - df['floor']
    # df['time'] = df['time'].apply(lambda x: "{:02d}:{:02d}".format(x.seconds // 60, x.seconds % 60))
    df['datetime'] = dt.datetime(2024,1,1) + df['time']
    df = df[['datetime', 'ID']].copy()
    return df

"""
Function to calculate conditional predicted trades in t future periods
each timestamp needs to have its own frequency, recency and age(T)
this version computes that from nearest minute
future versions will be more nuanced
"""

def calculate_prediction_path(
    models_dict,
    transactions,
    datetime_col,
    perc_col,
    t,
    freq="D"
):
    """
    Calculate forecast path of the expected number of trades.
    
    This function uses model/fitted distribution based on chosen percentile column and
        prior fitting of the condition of 

    Uses the ``conditional_expected_number_of_purchases_up_to_time()`` method of the model to achieve the path.

    Parameters
    ----------
    model:
        A fitted lifetimes model
    transactions: DataFrame
        a Pandas DataFrame containing the transactions history of the customer_id
    datetime_col: string
        the column in the transactions that denotes the datetime the purchase was made
    t: array_like
        periods to the future for which to compute the expected number of trades
    freq: string, optional
        Default: 'D' for days. Possible values listed here:
        https://numpy.org/devdocs/reference/arrays.datetime.html#datetime-units

    Returns
    -------
    :obj: Series
        A pandas Series containing the p_alive as a function of T (age of the customer)
    """

    customer_history = transactions[[datetime_col, perc_col]].copy()
    customer_history[datetime_col] = customer_history[datetime_col].dt.strftime('%Y-%m-%d %H:%M:%S')
    customer_history[datetime_col] = pd.to_datetime(customer_history[datetime_col])
    customer_history = customer_history.set_index(datetime_col)
    
    # Add transactions column
    customer_history["transactions"] = 1    
    
    # Determine the range of seconds for each minute
    customer_history = customer_history.reset_index()
    min_time = customer_history[datetime_col].min().round('S')
    max_time = customer_history[datetime_col].max().round('S')
    
    # Create a new DataFrame for every second
    all_seconds = pd.date_range(start=min_time, end=max_time, freq='S')
    df_all_seconds = pd.DataFrame(all_seconds, columns=[datetime_col])
    
    # Merge the new DataFrame with the original DataFrame
    
    customer_history = df_all_seconds.merge(customer_history, on=datetime_col, how='left')
    
    # Set datetime as index for resampling
    customer_history = customer_history.set_index(datetime_col)
    
    # Determine the earliest date in your DataFrame
    earliest_date = customer_history.index.date.min()
    
    # Create a new start datetime (e.g., 08:00 AM on the earliest date)
    start_datetime = pd.Timestamp(f'{earliest_date} 08:00')
    
    # Create a new row with 0s and the index of start_datetime
    new_row = pd.DataFrame({'data': [0]}, index=[start_datetime])
    
    # Append the new row to the DataFrame and sort by index
    customer_history = pd.concat([new_row, customer_history]).sort_index()
    
    # Resample and calculate sum of transactions and average of quantile
    resampled_data = customer_history.resample('S').agg({
        'transactions': 'sum', 
        perc_col: lambda x: round(np.nanmean(x)) if not x.isnull().all() else np.nan
    })
    
    # Replace NaN with 0 for transactions and quantile
    resampled_data = resampled_data.fillna({'transactions': 0, perc_col: 0}).astype({perc_col: int})
    
    # Method for applying the bg/nbd model based on quantile
    def apply_model(row, model_dict, t):
        model = model_dict.get(row[perc_col], None)
        if model:
            return model.conditional_expected_number_of_purchases_up_to_time(t, row["frequency"], row["recency"], row["T"])
        else:
            return np.nan
    # Obtaining the characterics for model
    # The logic is that age, recency and frequency are calculated on rolling time window
    # For now it is rolling 60 seconds
    # Age
    resampled_data['T'] = np.arange(resampled_data.shape[0])
    resampled_data['T'] = np.where(resampled_data['T']<60,
                                   resampled_data['T'],
                                   59)
    # Frequency    
    resampled_data['frequency'] = resampled_data['transactions'].rolling(window=60,
                                                                         min_periods=1).sum()
    
    # Recency
    # Add recency column
    def index_difference(x):
        # Get indices of non-zero values
        non_zero_indices = x.to_numpy().nonzero()[0]
        
        # Check if there are at least two non-zero values to compute a difference
        if len(non_zero_indices) >= 2:
            return non_zero_indices[-1] - non_zero_indices[0]
        else:
            return 0
    
    # Apply the custom function over a rolling window
    resampled_data['recency'] = resampled_data['transactions'].rolling(window=60,
                                                                         min_periods=1).apply(index_difference, raw=False)
    # group["recency"] = group["recency"].fillna(method="ffill").fillna(0)
    
    # Apply model, conditioned to qunatiles
    resampled_data['model_output'] = resampled_data.apply(apply_model, args=(model_dict['bid_trade'], t), axis=1)
    
    
    
        
    return resampled_data

freq = '1T'
penalty = 0
train_data_dict = {}
test_data_dict = {}
model_dict = {}   
for side in ['bid_trade', 'ask_trade']:
    aux = train_data.loc[train_data[side]==1][['id', 'ba_perc']].copy()
    train_data_dict[side] = {}
    test_data_dict[side] = test_data.loc[test_data[side]==1][['id', 'ba_perc']].copy()
    model_dict[side] = {}
    for perc in range(10):
        aux_perc = aux.loc[aux['ba_perc']==perc]['id'].copy()
        aux_buckets = data_time_bucketing(aux_perc, freq)
        summary = summary_data_from_transaction_data(aux_buckets, 'ID', 'datetime', freq='s')
        for penalty in range(0,11):
            try:
                bgf = BetaGeoFitter(penalizer_coef=penalty/10)
                bgf.fit(summary['frequency'], summary['recency'], summary['T'])
                break
            except:
                continue
        train_data_dict[side][perc] = aux_perc
        model_dict[side][perc] = bgf
        
test = calculate_prediction_path(model_dict['bid_trade'],
                                 test_data_dict['bid_trade'].reset_index(),
                                 'datetime', 'ba_perc', 1)
         
"""
bid_trades = data.loc[data['bid_trade']==1]['id'].copy()
# bid_trades = bid_trades.reset_index()
freq = '1T'
time_buckets = bid_trades.resample(freq).size()

id_mapping = time_buckets.reset_index().reset_index().rename(columns={'index': 'ID',
                                                                      'datetime': 'floor'})
id_mapping = id_mapping[['floor', 'ID']]
bid_trades = bid_trades.reset_index()


bid_trades['floor'] = bid_trades['datetime'].dt.floor(freq)
bid_trades = bid_trades.merge(id_mapping, on='floor', how='left')

bid_trades['datetime'] = bid_trades['datetime'].dt.floor('S')
bid_trades['time'] = bid_trades['datetime'] - bid_trades['floor']
# bid_trades['time'] = bid_trades['time'].apply(lambda x: "{:02d}:{:02d}".format(x.seconds // 60, x.seconds % 60))
bid_trades['datetime'] = dt.datetime(2024,1,1) + bid_trades['time']
bid_trades = bid_trades[['datetime', 'ID']].copy()

summary = summary_data_from_transaction_data(bid_trades, 'ID', 'datetime', freq='s')    


bgf = BetaGeoFitter(penalizer_coef=0)


bgf.fit(summary['frequency'], summary['recency'], summary['T'])

print(bgf)

plot_frequency_recency_matrix(bgf)
# plot_probability_alive_matrix(bgf)


   
days_since_birth = 1
max_summary = summary['frequency'].idxmax()
sp_trans = bid_trades.loc[bid_trades['ID']==3371].copy()

sp_trans['datetime'] = sp_trans['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

# plot_history_alive(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
# plt.show()

# plot_period_transactions(bgf)

plot_history_prediction(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
"""