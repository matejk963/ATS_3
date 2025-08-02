# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 12:01:12 2024

@author: Marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Market_making.model_class import simple_model
from Strategies.Market_making.backtest_class import BacktestMM
from Strategies.Market_making.strategy_class import StrategyMM, VolumeClass
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


def calc_ema_m_old(df_data, tau, margin, w, eql_p, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        model = EMA(tau, mid_list[0])
        ema_list = [model.push(x, dx) if abs(dx) > tol else np.nan
                    for x, dx in zip(mid_list, dif_list)]
        ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
        bands.extend([[x - margin, x, x + margin] for x in ema_list])
    return pd.DataFrame(bands, index=df_data.index).ffill()


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
        model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
                             'mstd', burn=0, time_model=False, tol=tol)
        model_list = model.predict(mid_list)
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        # model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
        #                      'mstd', burn=0, time_model=False, tol=tol)
        std_list = [model.push_mstd(x) for x in mid_list]
        ema_list = [x[0] for x in model_list]
        mrg_list = [m[1] * w_std for m in std_list]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()

def adjust_std_based_on_distance(df, model_price, scaling_factor=1.0):
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
    model_price = model_price.reindex(df.index)
    
    # Initialize a list to hold the adjusted data for each day
    adjusted_data = []
    
    # Loop through each day in the data
    for day, daily_df in df.groupby(df.index.date):
        # Get the corresponding model prices for the day
        daily_model_price = model_price.loc[daily_df.index]
        
        # Compute original standard deviation from the bands
        daily_df['std'] = (daily_df.iloc[:,2] - daily_df.iloc[:,0]) / 2
        
        # Calculate the distance between EMA and model price
        daily_df['distance'] = np.abs(daily_df.iloc[:,1] - daily_model_price.iloc[:, 0])
        
        # Adjust the standard deviation based on the distance
        daily_df['adjusted_std'] = daily_df['std'] * (1 + scaling_factor * daily_df['distance'] / daily_df['std'])
        
        # Recalculate the lower and upper bands with adjusted std
        daily_df['lower band adjusted'] = daily_model_price.iloc[:, 0] - daily_df['adjusted_std']
        daily_df['upper band adjusted'] = daily_model_price.iloc[:, 0] + daily_df['adjusted_std']
        
        # Append the adjusted data for this day
        adjusted_data.append(pd.DataFrame({
            'mean-sigma': daily_df['lower band adjusted'],
            'mean': daily_df.iloc[:,1],
            'mean+sigma': daily_df['upper band adjusted']
        }))
    
    # Combine all the adjusted data into a single DataFrame
    df_adjusted = pd.concat(adjusted_data)
    
    return df_adjusted


def calc_bands(ema_bands, df_model, df_data, tau, w_std, scaling_factor, N=30, tol=0):
    
    # Linear kernel for adjustment
    band_adj = adjust_std_based_on_distance(ema_bands, df_model.iloc[0],scaling_factor)
    return band_adj

    



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

def calc_ema_mstd_spot(df_data, tau, margin, w, w1, df_model, tol=0):
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
        lower_bound_list = df_model_aux.iloc[:, 1].values
        upper_bound_list = df_model_aux.iloc[:, 2].values
        lower_mrg_list = [w1 * margin + (1 - w1) * abs(x - m) for m, x in zip(lower_bound_list, eql_list)]
        upper_mrg_list = [w1 * margin + (1 - w1) * abs(m - x) for m, x in zip(upper_bound_list, eql_list)]
        ema_list = [w * eq + (1 - w) * x for x, eq in zip(ema_list, eql_list)]
        bands.extend([[x - ml, x, x + mu] for x, ml, mu in zip(ema_list, lower_mrg_list, upper_mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()


n_s = 2
start_date = datetime(2024, 2, 1)
end_date = datetime(2024, 4, 30)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['de']*2
tenor = ['w']*2
tn1_list = [1, 2]
tn2_list = []
brk_list = ['eex']
mm_bool = [True, True]

start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)
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
model_data = model_tr(data, tau_m, N)

# Weekly model data
import pickle, os
folder_path = r'Z:\Data\Spot\Model\Backtest\ModelPrices\MMSpot'
file_name = 'de_w1_w3_model_prices.pickle'
file_path = os.path.join(folder_path, file_name)
with open(file_path, 'rb') as f:
    weekly_model_dict = pickle.load(f)
weekly_model_df2 = weekly_model_dict['w1'][['pred']].resample('D').mean().copy()
weekly_model_df2['lower'] = -100
weekly_model_df2['upper'] = 100

# Assign common datetime to model prices
# Convert the datetime index of df_data to date for alignment
df_ba['date'] = pd.to_datetime(df_ba.index.date)
# Merge df_data with weekly_model_df on the date column
model_price_df = df_ba.join(weekly_model_df2, on='date')
# Optionally, drop the 'date' column if it's no longer needed
model_price_df.drop(columns=['date', 'bid', 'ask'], inplace=True)



method = 'simple_mtm'
# EMA
# tau = 8
# margin = .20
# eql_p = -6.25
# w = 0.0 #0.4
# w1 = .5
# MSTD
if tp_data:
    tau = 12.6
else:
    tau = 19.4
tau = 50
margin = 1.5
eql_p = -6.25
# Percent weight for model
w = 0
# Percent weight for margin
w1 = 1
w_std = 1.32
scaling_factor = 1

# emabands
ema_bands = calc_ema_std(df_ba, tau, w_std,N=30, tol=0)
# Adjust trades
df_em = adjust_std_based_on_distance(ema_bands.copy(), model_price_df, scaling_factor=scaling_factor)
# df_em = calc_ema_mstd(df_ba, tau, margin, w, w1, model_data).dropna()
# df_em = calc_ema_m(df_ba, tau, margin, w, eql_p, tol=.024)
#df_em = calc_ema_m_std(df_ba, tau, margin, w, w1, w_std, eql_p, tol=0.024)
df_ba_a = df_ba.loc[df_em.index, :]
df_tr_a = adjust_trds(df_tr.copy(), df_em)

input_data_dict = {
    'df_ba_a': df_ba_a,
    'df_tr_a': df_tr_a,
    'df_ba': df_ba,
    'df_tr': df_tr,
    'ema_bands': ema_bands
    }

# Sotore input data
file_path = r'Z:\Data\Spot\MM\Inputs\input_data_simple_mm_20230801_20241031.pickle'
with open(file_path, 'wb') as f:
    pickle.dump(input_data_dict, f)


instr = 'w1x2'
data_dict = {}
data_dict[instr] = BacktestMM.merge_data(df_ba_a, df_tr_a, False)

# data_dict['output'] = calc_ema_m(data_dict[instr], tau, margin, w, eql_p)
ts = data_dict[instr].index
df_em = df_em[~df_em.index.duplicated(keep='first')]
df_em = df_em.reindex(ts.drop_duplicates()).ffill()
data_dict['output'] = df_em.loc[ts, :]

param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = datetime(2024, 11, 28)
param_dict['take_profit'] = 1
param_dict['stop_loss_rat'] = 2
param_dict['ba_spread'] = 0.25
param_dict['ba_max'] = 1.5
param_dict['br_fee'] = 0.035

vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestMM(vol_class)
strategy_class = StrategyMM('MM', 'de', instr)
strategy_class.load_params(param_dict, contr_vars)

xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)

# Plot xx on a separate chart
xx.plot(grid=True, legend=True, figsize=(12, 8))  # Adjust the figsize as needed
plt.show()

# Plot the rest of the data with missing dates skipped (smooth charts)
fig, ax = plt.subplots(figsize=(14,7))  # Create a figure and axis for the combined plot
# Plot the first two columns of 'w1x2' DataFrame
data_dict['w1x2'].iloc[:, :2].dropna().plot(ax=ax, grid=True, legend=True)
# Plot the third column of 'w1x2' with dots
data_dict['w1x2'].iloc[:, 4].dropna().plot(ax=ax, grid=True, legend=True, style='.')
# Plot the 'output' DataFrame
data_dict['output'].dropna().plot(ax=ax, grid=True, legend=True)
plt.show()