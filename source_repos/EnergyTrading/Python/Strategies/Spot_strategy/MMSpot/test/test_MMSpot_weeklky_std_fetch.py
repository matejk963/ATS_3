# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 12:01:12 2024

@author: Marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
import datetime as dt
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Spot_strategy.MMSpot.model_class import simple_model
from Strategies.Spot_strategy.MMSpot.backtest_class import BacktestMM
from Strategies.Spot_strategy.MMSpot.strategy_class import StrategyMM, VolumeClass
tol=(1e-1)/2


def grouped_series(data_series, idx_series):
    df_data = pd.DataFrame([])
    agg_dict = agg_dict = {'index': 'first', data_series.name: 'mean'}
    data_aux = pd.concat([data_series.reindex(idx_series.index), idx_series],
                         axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for data in data_dict.values():
        df_data = pd.concat([df_data, data])
    return df_data.dropna()


def tick_data(df_tr, tau, tau_ema):
    df_tr = df_tr.dropna()
    data_p = df_tr['price']

    # Expected size of candle
    ti_cls = TR_class(tau, tau_ema)
    idx_series = ti_cls.tick_imbalance_indices(data_p)

    # Calculate distribution of returns
    return grouped_series(data_p, idx_series)


def model_tr(data, tau, N, alpha=0.2, beta=1):
    X = data.iloc[:,0].values
    value0 = X[0]
    model_std = simple_model(MSTD(tau, N), [tau / 2, N, 2, value0],
                             'mstd', burn=tau)
    std = model_std.predict(X)
    df_out = pd.DataFrame(std, index=data.index)
    # Differential model
    model_dt = simple_model(DerivativeEMA(tau, N), [tau, 1, .5, value0],
                            'dt', burn=tau)
    dt = model_dt.predict(X)
    df_out = pd.concat([df_out, pd.Series(dt, index=data.index)], axis=1)
    # Mean reversion model
    y_df = pd.Series([x[0] for x in std], index=data.index)
    data_ = (y_df - data.iloc[:, 0]).dropna()
    X_data = data_.iloc[:-1].values.reshape(-1,1)
    y_data = data_.iloc[1:].values.reshape(-1,)

    out_dict_lm = ftrl_regression(X_data, y_data, 0, 0, alpha, beta, True, False)
    # Estimated parameters
    theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict_lm['coeff']]
    period_list = [(np.log(2) / x) for x in theta_list]
    df_out = pd.concat([df_out, pd.Series(period_list, index=data_.index[1:])], axis=1)
    df_model = df_out.iloc[:,0] + df_out.iloc[:,-2] * df_out.iloc[:,-1]
    return pd.concat([df_model, df_out.iloc[:,1]], axis=1)


def ftrl_regression(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LinearModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                      adaptive_l1=adaptive_l1, norm_g=False)
    yhat = []
    score = []
    param_list = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(clf.predict(x_train))
        score.append(clf.unc_score(x_train))
        clf.push(x_train, y_)
        param_list.append([x for x in clf.params])
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'score': score}
    return out_dict


def adjust_trds(df_tr, df_em):
    df_em = df_em[~df_em.index.duplicated(keep='first')]
    timestamp = df_tr.index
    ts_new = df_em.index.union(timestamp).drop_duplicates()
    df_em = df_em.reindex(ts_new).ffill().loc[timestamp, :]
    lb = df_em.iloc[:, 0]
    ub = df_em.iloc[:, 2]
    df_tr.loc[lb.isna()] = np.nan
    df_tr.loc[(df_tr['price'] > ub) & (df_tr['action'] == 1), :] = np.nan
    df_tr.loc[(df_tr['price'] < lb) & (df_tr['action'] == -1), :] = np.nan
    return df_tr.dropna(how='all')


def calc_ema_m(df_data, tau, margin, w, eql_p, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        # Create model
        model_class = simple_model(EMA(tau), [tau, mid_list[0]],
                                   'ema', burn=0, time_model=False, tol=tol)
        # Calc model
        ema_list = model_class.predict(mid_list)
        ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
        bands.extend([[x - margin, x, x + margin] for x in ema_list])
    return pd.DataFrame(bands, index=df_data.index).ffill()


def calc_ema_m_std(df_data, tau, margin, w, w1, w_std, eql_p,N=30, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
                             'mstd', burn=0, time_model=False, tol=tol)
        model_list = model.predict(mid_list)
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        # model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
        #                      'mstd', burn=0, time_model=False, tol=tol)
        std_list = [model.push_mstd(x, dx) if abs(dx) > tol else [np.nan] * 2
                    for x, dx in zip(mid_list, dif_list)]
        ema_list = [w * eql_p + (1 - w) * x[0] for x in model_list]
        mrg_list = [w1 * margin + (1 - w1) * m[1] * w_std for m in std_list]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()

def calc_ema_std(df_data, tau, w_std, N=30, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        if len(group) == 0:
            continue
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        model = simple_model(MSTD(tau, N,2), [tau / 2, N, 2, mid_list[0], 2],
                             'mstd', burn=0, time_model=False, tol=tol)
        model_list = model.predict(mid_list)

        # model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
        #                      'mstd', burn=0, time_model=False, tol=tol)
        # std_list = [model.push_mstd(x) for x in mid_list]

        ema_list = [x[0] for x in model_list]
        mrg_list = [m[1] * w_std for m in model_list]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()

# def calc_ema_std_weekly(df_data, tau_fast, tau_slow, w_std, N=30, tol=0):
#     bands = []
#     bands_index = []
#     std_window = 5  # Rolling window of 5 days for std0
#     prev_model_second_col = pd.DataFrame()  # To store second column of model_list

#     for day, group in df_data.groupby(pd.Grouper(freq='B')):
#         if len(group) == 0:
#             continue

#         mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
#         mid_list = mid_ser.values
        
#         # Check if the DataFrame has a DateTime index and at least `std_window` unique days
#         if not prev_model_second_col.empty and hasattr(prev_model_second_col.index, 'date') and np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
#             # Calculate the rolling standard deviation over the last 5 days
#             std0 = prev_model_second_col.resample('D').last().dropna().rolling(std_window).mean().iloc[-1].values[0]
#         else:
#             # If we don't have enough data for 5 days yet, use a default value
#             std0 = 1  # You can adjust this based on how you'd like to handle early days

#         model_fast = simple_model(MSTD(tau_fast, N, std0), [tau / 2, N, 2, mid_list[0], std0],
#                              'mstd', burn=0, time_model=False, tol=tol)
#         model_fast_list = model_fast.predict(mid_list)
#         model_slow = simple_model(MSTD(tau_slow, N, std0), [tau / 2, N, 2, mid_list[0], std0],
#                              'mstd', burn=0, time_model=False, tol=tol)
#         model_slow_list = model_slow.predict(mid_list)

#         # Extract the first (ema) and second (mrg) elements from model_list
#         ema_fast_list = [x[0] for x in model_fast_list]
#         mrg_list = [m[1] * w_std for m in model_fast_list]
        
#         # Append the second column (m[1]) to prev_model_second_col for future rolling std calculation
#         new_data = pd.DataFrame([m[1] for m in model_list], index=group.index)
#         prev_model_second_col = pd.concat([prev_model_second_col, new_data])
        
#         # Ensure that we start adding bands after 5 days of data
#         if np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
#             bands_index.append(group.index.values)
#             bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])

#     return pd.DataFrame(bands, index=np.concatenate(bands_index)).ffill()

def calc_ema_std_weekly(df_data, tau, w_std, N=30, tol=0):
    bands = []
    bands_index = []
    std_window = 5  # Rolling window of 5 days for std0
    prev_model_second_col = pd.DataFrame()  # To store second column of model_list

    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        if len(group) == 0:
            continue

        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        
        # Check if the DataFrame has a DateTime index and at least `std_window` unique days
        if not prev_model_second_col.empty and hasattr(prev_model_second_col.index, 'date') and np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
            # Calculate the rolling standard deviation over the last 5 days
            std0 = prev_model_second_col.resample('D').last().dropna().rolling(std_window).mean().iloc[-1].values[0]
        else:
            # If we don't have enough data for 5 days yet, use a default value
            std0 = 1  # You can adjust this based on how you'd like to handle early days

        model = simple_model(MSTD(tau, N, std0), [tau / 2, N, 2, mid_list[0], std0],
                             'mstd', burn=0, time_model=False, tol=tol)
        model_list = model.predict(mid_list)

        # Extract the first (ema) and second (mrg) elements from model_list
        ema_list = [x[0] for x in model_list]
        mrg_list = [m[1] * w_std for m in model_list]
        
        # Append the second column (m[1]) to prev_model_second_col for future rolling std calculation
        new_data = pd.DataFrame([m[1] for m in model_list], index=group.index)
        prev_model_second_col = pd.concat([prev_model_second_col, new_data])
        
        # Ensure that we start adding bands after 5 days of data
        if np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
            bands_index.append(group.index.values)
            bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])

    return pd.DataFrame(bands, index=np.concatenate(bands_index)).ffill()




def adjust_std_based_on_distance(df, model_price, std_weights=[-3,-2.5, -2, -1, 0,
                                                               1, 2, 2.5, 3],
                                 scaling_factor=1.0, alpha=2, beta=0.05):
    """
    Adjust the EMA bands based on the distance from the model price by widening the std.
    This function processes data for multiple days, adjusting each day's bands separately.

    Parameters:
    - df: DataFrame with columns ['lower band', 'ema', 'upper band'], indexed by timestamp
        .iloc[:,1] = ema, .iloc[:,0] & .iloc[:,2] upper lower bands
    - model_price: DataFrame with a single column containing the model price, indexed by timestamp
    - scaling_factor: A factor to control the influence of the distance on std

    Returns:
    - df_adjusted: DataFrame with adjusted bands columns [mean-sigma, mean, mean+sigma] for each day
    """
    # Ensure the indices of df and model_price match
    df = df.copy()
    df.columns = ['lower', 'mean', 'upper']
    model_price = model_price.reindex(df.index).fillna(0)
    
    # Initialize a list to hold the adjusted data for each day
    adjusted_data = []
    
    # Loop through each day in the data
    for day, daily_df in df.groupby(df.index.date):
        # Get the corresponding model prices for the day
        daily_model_price = model_price.loc[daily_df.index]
        
        # Compute original standard deviation from the bands
        daily_df['std'] = (daily_df.iloc[:,2] - daily_df.iloc[:,0]) / 2
        daily_df['model_std'] = daily_model_price.iloc[:,1].copy()
        
        # Calculate the distance between EMA and model price
        daily_df['distance'] = np.abs(daily_df.iloc[:,1] - daily_model_price.iloc[:, 0])
        
        # Adjust the standard deviation based on the distance
        # daily_df['adjusted_std'] =  (1 + scaling_factor * daily_df['distance']/np.log(daily_df['model_std']/
        #                                   daily_df['std']))
        
        weights_series = np.e**(-beta*daily_df['distance'])
        daily_df['adjusted_std'] = weights_series * daily_df['std'] + (1 - weights_series) * daily_df['model_std']
        daily_df['adjusted_std'] = daily_df['std']
        daily_df['adjusted_price'] = weights_series * daily_df.iloc[:,1] + (1 - weights_series) * daily_model_price['pred']
        # daily_df['adjusted_std'] = daily_df['adjusted_std'] * (1 + daily_df['distance']/daily_df['adjusted_std'])
        
        name_list = []
        for i in std_weights:
            name = str(i) + '_sigma'
            name_list.append(name)
            sigma_model = daily_df['adjusted_price'] + i * daily_df['std']
            sigma_ema = daily_df['mean'] + i * daily_df['std']
            daily_df[name] = np.minimum(sigma_model, sigma_ema)
            # if i < 0:
            #     daily_df[name] = np.minimum(sigma_model, sigma_ema)
            # elif i > 0:
            #     daily_df[name] = np.maximum(sigma_model, sigma_ema)
        
        adjusted_data.append(pd.DataFrame({f'mean_{a}sigma':
                                           daily_df[name_list[int(i)]] for i,a in enumerate(std_weights)}))
        # adjusted_data.append(pd.DataFrame({
        #     'mean-3sigma': daily_df[name_list[0]],
        #     'mean-2sigma': daily_df[name_list[1]],
        #     'mean-sigma': daily_df[name_list[2]],
        #     'mean': daily_df['adjusted_price'],
        #     'mean+sigma': daily_df[name_list[4]],
        #     'mean+2sigma': daily_df[name_list[5]],
        #     'mean+3sigma': daily_df[name_list[6]]
        # }))
    
    # Combine all the adjusted data into a single DataFrame
    df_adjusted = pd.concat(adjusted_data).dropna()
    
    return df_adjusted




def calc_ema_mstd(df_data, tau, margin, w, w1, df_model, tol=0, weekly_model_df=None):
    ts = df_data.index
    df_model = df_model.reindex(ts).ffill()
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        df_model_aux = df_model.loc[group.index, :]
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        model = EMA(tau, mid_list[0])
        ema_list = [model.push(x, dx) if abs(dx) > tol else np.nan
                    for x, dx in zip(mid_list, dif_list)]
        eql_list = df_model_aux.iloc[:, 0].values
        mrg_list = [w1 * margin + (1 - w1) * m for m in df_model_aux.iloc[:, 1].values]
        ema_list = [w * eq + (1 - w) * x for x, eq in zip(ema_list, eql_list)]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()

def get_last_trading_day_series(df):
    # Resample to weekly frequency (end of week is Sunday, so set it to Friday)
    last_friday = df.resample('W-FRI').last().index
    
    # Create a Series to hold the last trading date for each timestamp
    last_trading_date_series = pd.Series(index=df.index, dtype='datetime64[ns]')
    
    # For each week, determine the last trading day
    for week_ending in last_friday:
        if week_ending.date() in df.index.date:
            last_trading_day = pd.to_datetime(week_ending) + dt.timedelta(hours=16)
        else:
            # Get the last available day in the week
            week_data = df.loc[week_ending - pd.DateOffset(days=6):
                               (week_ending + dt.timedelta(days=1))].iloc[:-1].copy()
            last_trading_day = pd.to_datetime(week_data.index.date[-1]) + dt.timedelta(hours=16)
            
        
        # Assign this last trading day to all entries in that week
        last_trading_date_series.loc[week_ending - pd.DateOffset(days=6):
                                     (week_ending + dt.timedelta(days=1, milliseconds=-1))] = last_trading_day
    
    return last_trading_date_series


# Load input data

# import pickle
# file_path = r'Z:\Data\Spot\MM\Inputs\input_data_simple_mm_202400722_20240908.pickle'
# with open(file_path, 'rb') as f:
#     input_data_dict = pickle.load(f)

# df_ba_a, df_tr_a, df_ba, df_tr, ema_bands = input_data_dict.values()

n_s = 0
start_date = datetime(2024, 9, 16)
end_date = datetime(2024, 9, 16)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['de']*2
tenor = ['w']*2
tn1_list = [1, 2]
tn2_list = []
brk_list = ['eex']
mm_bool = [True, True]

start_time = time(8, 37, 0, 0)
end_time = time(17, 9, 0, 0)
gran = None
gran_t = '1s'
coeff_list = norm_coeff([1, -1], market)


ob_data = True
tp_data = True

df_ba = pd.DataFrame([])
df_tr = pd.DataFrame([])

spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
data_class = SpreadViewerData()
db_class = TPDataDa()
tenors_list = spread_class.tenors_list
if not ob_data:
    data_class.load_best_order_otc(market, tenors_list,
                                    spread_class.product_dates(dates, n_s),
                                    db_class,
                                    start_time=start_time, end_time=end_time)
else:
    if tp_data:
        data_class.load_best_ob_tp(market, tenors_list,
                                    spread_class.product_dates(dates, n_s),
                                    db_class,
                                    start_time=start_time, end_time=end_time)
    else:
        data_class.load_best_ob(market, tenors_list, dates, spread_class.product_dates(dates, n_s),
                                v_thres=.5, freq=gran)

data_class_tr = SpreadViewerData()
data_class_tr.load_trades_otc(market, tenors_list, db_class,
                              start_time=start_time, end_time=end_time)

for d in dates:
    d_range = pd.date_range(d, d)
    data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                            start_time=start_time, end_time=end_time)
    df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
    col_list=['bid', 'ask', 'volume']
    trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                              start_time=start_time, end_time=end_time,
                                              col_list=col_list, data_dict=data_dict)
    df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    
    df_ba = pd.concat([df_ba, df_ba_], axis=0)
    df_tr = pd.concat([df_tr, df_tr_], axis=0)



# Model
tau_t = 10
tau_ema = 22
data = tick_data(df_tr, tau_t, tau_ema)
N = 30
tau_m = 30
# model_data = model_tr(data, tau_m, N)

# Weekly model data
import pickle, os
folder_path = r'Z:\Data\Spot\Model\Backtest\ModelPrices\MMSpot'
file_name = 'de_w1_w3_model_prices_w_std.pickle'
file_path = os.path.join(folder_path, file_name)
with open(file_path, 'rb') as f:
    weekly_model_dict = pickle.load(f)
weekly_model_df2 = weekly_model_dict['w1'][['pred', 'std']].resample('D').mean().copy()

# Pure model sigma
df_model_bounds = weekly_model_df2.copy()
name_list = []
for sig in range(-3,4):
    name = str(sig) + '_sigma'
    df_model_bounds[name] = df_model_bounds['pred'] + sig * df_model_bounds['std']
    name_list.append(name)
    
df_model_bounds = df_model_bounds[name_list[:3] + ['pred'] + name_list[3:]].dropna().copy()



# Assign common datetime to model prices
# Convert the datetime index of df_data to date for alignment
df_ba['date'] = pd.to_datetime(df_ba.index.date)
# Merge df_data with weekly_model_df on the date column
model_price_df = df_ba.join(weekly_model_df2, on='date')
# Optionally, drop the 'date' column if it's no longer needed
model_price_df = model_price_df.drop(columns=['date', 'bid', 'ask'])



method = 'position_mtm'

tau = 100
margin = 0.7
eql_p = -6.25
# Percent weight for model
w = 0
# Percent weight for margin
w1 = 1
w_std = 2
scaling_factor = 1


df_ba.to_csv(r'Z:\Data\Spot\MM\Inputs\df_ba_de_w1w2_20240923.csv')

# df_ba2 = pd.read_excel(r'Z:\Data\Spot\MM\Inputs\input_data_from_production_20240912.xlsx')

# emabands
ema_bands = calc_ema_std(df_ba, tau, w_std,N=30, tol=0.025)

df_mid = df_ba[['bid', 'ask']].mean(axis=1)

df_mid_sel = df_mid.loc[df_mid.index.date==np.unique(df_mid.index.date)[10]]


def robust_bollinger_bands(prices, fast_window=100, slow_window=150, regression_window=10, std_factor=2, kernel='sigmoid'):
    # Calculate fast and slow moving averages
    fast_ma = prices.rolling(window=fast_window).mean()
    slow_ma = prices.rolling(window=slow_window).mean()
    
    # # Fit rolling linear regression to calculate slopes and betas (intercepts)
    # fast_slope, fast_beta = rolling_regression(prices, fast_window)
    # slow_slope, slow_beta = rolling_regression(prices, slow_window)
    
    # # Calculate the absolute difference between the slopes of fast and slow moving averages
    # slope_diff = np.abs(fast_slope - slow_slope)
    slope_diff = fast_ma - slow_ma
    # Calculate the standard deviation of prices over the fast window
    rolling_std = (prices-fast_ma).rolling(window=fast_window).std()
    
    # Apply a kernel to the slope difference to normalize adjustments
    if kernel == 'log':
        # Logarithmic scaling, with a small constant to avoid log(0)
        adjustment_factor = np.sign(slope_diff)*np.log1p(abs(slope_diff)/rolling_std)
    elif kernel == 'tanh':
        # Hyperbolic tangent scaling, maps difference to range (-1, 1)
        adjustment_factor = np.tanh(slope_diff/rolling_std)
    elif kernel == 'sigmoid':
        # Sigmoid scaling, maps difference to range (0, 1)
        adjustment_factor = 1 / (1 + np.exp(-slope_diff))
    else:
        raise ValueError("Unsupported kernel. Choose 'log', 'tanh', or 'sigmoid'.")
    
    # Calculate the standard deviation of prices over the fast window
    # rolling_std = prices.rolling(window=fast_window).std()
    
    # Adjust the standard deviation multiplier for the bands based on the adjustment factor
    upper_band = fast_ma + (std_factor + std_factor * adjustment_factor) * rolling_std  # Expand upper band in uptrend
    lower_band = fast_ma - (std_factor - std_factor * adjustment_factor) * rolling_std # Expand lower band in downtrend
    
    # return fast_ma, slow_ma, upper_band, lower_band, fast_slope, fast_beta, slow_slope, slow_beta
    return fast_ma, slow_ma, upper_band, lower_band


# You can now visualize or analyze the output


# Sample usage with some price data (e.g., a pandas Series of close prices)
prices = df_mid_sel

# Call the function to get robust dynamic Bollinger Bands
moving_avg,ma2, upper_band, lower_band = robust_bollinger_bands(prices,fast_window=200, slow_window=1000,
                                                            kernel='log')

# You can now visualize or analyze the output
pd.concat([df_mid_sel, moving_avg,ma2, upper_band, lower_band],axis=1).plot()




