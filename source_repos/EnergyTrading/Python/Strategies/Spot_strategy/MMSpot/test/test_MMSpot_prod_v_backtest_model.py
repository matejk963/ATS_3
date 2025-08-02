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
        # ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
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


prod_data = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\mm_de_w1w2_model_20241105.csv',
                        index_col=0)
prod_data.columns = ['timestamp', 'bid', 'ask', 'mid',
                     'model_p', 'model_v', 'model_count',
                      'leg1_bid', 'leg1_ask', 'leg2_bid', 'leg2_ask']
prod_data['datetime'] = pd.to_datetime(prod_data['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
prod_data.set_index('datetime', inplace=True)

# df_ba = prod_data.set_index('datetime')[['bid', 'ask']].copy()

n_s = 0
start_date = datetime(2024, 11, 5)
end_date = datetime(2024, 11, 5)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['de']*2
tenor = ['w'] * 2
tn1_list = [1, 2]
tn2_list = []
brk_list = ['eex']
mm_bool = [True, True]

start_time = time(11, 20, 0, 0)
end_time = time(17, 36, 3, 0)
# start_time = time(15, 9, 1, 0)
# end_time = time(16, 1, 36, 0)
gran = None
gran_t = '1s'
coeff_list = norm_coeff([1, -1], market)


ob_data = True
tp_data = False

df_ba = pd.DataFrame([])
df_tr = pd.DataFrame([])

spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
data_class = SpreadViewerData()
db_class = TPData()
db_class.create_connection('PostgreSQL')
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
# data = tick_data(df_tr, tau_t, tau_ema)
N = 30
tau_m = 30
# model_data = model_tr(data, tau_m, N)

# # Weekly model data
# import pickle, os
# folder_path = r'Z:\Data\Spot\Model\Backtest\ModelPrices\MMSpot'
# file_name = 'de_w1_w3_model_prices_w_std.pickle'
# file_path = os.path.join(folder_path, file_name)
# with open(file_path, 'rb') as f:
#     weekly_model_dict = pickle.load(f)
# weekly_model_df2 = weekly_model_dict['w1'][['pred', 'std']].resample('D').mean().copy()

# # Pure model sigma
# df_model_bounds = weekly_model_df2.copy()
# name_list = []
# for sig in range(-3,4):
#     name = str(sig) + '_sigma'
#     df_model_bounds[name] = df_model_bounds['pred'] + sig * df_model_bounds['std']
#     name_list.append(name)
    
# df_model_bounds = df_model_bounds[name_list[:3] + ['pred'] + name_list[3:]].dropna().copy()



# # Assign common datetime to model prices
# # Convert the datetime index of df_data to date for alignment
# df_ba['date'] = pd.to_datetime(df_ba.index.date)
# # Merge df_data with weekly_model_df on the date column
# model_price_df = df_ba.join(weekly_model_df2, on='date')
# # Optionally, drop the 'date' column if it's no longer needed
# model_price_df = model_price_df.drop(columns=['date', 'bid', 'ask'])



method = 'position_mtm'

tau = 5
margin = 0.7
eql_p = -6.25
# Percent weight for model
w = 0
# Percent weight for margin
w1 = 1
w_std = 2
scaling_factor = 1


# df_ba.to_csv(r'Z:\Data\Spot\MM\Inputs\df_ba_de_w1w2_20240916.csv')

# df_ba2 = pd.read_excel(r'Z:\Data\Spot\MM\Inputs\input_data_from_production_20240912.xlsx')

df_ba = df_ba.loc[df_ba.index.time>=time(11, 32, 20, 0)].copy()
# emabands
ema_bands = calc_ema_std(df_ba, tau, w_std,N=30, tol=0.024)

df = pd.merge_asof(df_ba, prod_data[['bid', 'ask']],left_index=True, right_index=True, direction='nearest')
df_ba2 = df_ba.copy()
df_ba2.columns = ['bid_x','ask_x']
df = pd.concat([df_ba2,prod_data[['bid','ask']]],join='outer').sort_index().ffill()

df['mid_x'] = df[['bid_x', 'ask_x']].mean(axis=1)
df['mid_y'] = df[['bid', 'ask']].mean(axis=1)

ema_bands_prod = calc_ema_std(prod_data[['bid', 'ask']], tau, w_std,N=30, tol=0.024)

de = data_dict['de']
# Outer merge bid and ask for w1 on index
w1_merged = pd.merge(de['w_1']['bid'], de['w_1']['ask'], left_index=True, right_index=True, how='outer', suffixes=('_bid_w1', '_ask_w1'))

# Outer merge bid and ask for w2 on index
w2_merged = pd.merge(de['w_2']['bid'], de['w_2']['ask'], left_index=True, right_index=True, how='outer', suffixes=('_bid_w2', '_ask_w2'))

# Outer merge w1 and w2 DataFrames on index
final_merged = pd.merge(w1_merged, w2_merged, left_index=True, right_index=True, how='outer')
final_merged.columns = ['db_leg1_bid', 'db_leg1_ask', 'db_leg2_bid', 'db_leg2_ask']

df_legs = pd.concat([final_merged,
                prod_data[['leg1_bid', 'leg1_ask', 'leg2_bid', 'leg2_ask']]],
                    join='outer').sort_index()
df_legs = df_legs.loc[df_legs.index.time>=time(11, 41, 0, 0)].copy()

df_spread = df_legs.copy()
df_spread['db_bid'] = (df_spread['db_leg1_bid'] - df_spread['db_leg2_ask']).ffill()
df_spread['db_ask'] = (df_spread['db_leg1_ask'] - df_spread['db_leg2_bid']).ffill()
df_spread['bid'] = (df_spread['leg1_bid'] - df_spread['leg2_ask'])
df_spread['ask'] = df_spread['leg1_ask'] - df_spread['leg2_bid']
df_spread['db_mid'] = ((df_spread['db_bid'] + df_spread['db_ask'])/2)
df_spread['mid'] = ((df_spread['bid'] + df_spread['ask'])/2)
df_spread['w2_mid'] = (df_spread['leg2_bid'] + df_spread['leg2_ask'])/2
df_spread['db_w2_mid'] = (df_spread['db_leg2_bid'] + df_spread['db_leg2_ask'])/2
df_spread['w2_diff'] = df_spread['w2_mid'].ffill() - df_spread['db_w2_mid'].ffill()

df_spread['db_mid_diff'] = df_spread['db_mid'].diff()
df_spread['mid_diff'] = df_spread['mid'].diff()
df_spread['diff'] = df_spread['db_mid'] - df_spread['mid']

df_level = df_spread[['db_bid', 'db_ask', 'bid', 'ask', 'mid', 'db_mid']].copy()
df_level[['db_bid', 'db_ask','db_mid']] = df_level[['db_bid', 'db_ask','db_mid']].bfill()
df_level = df_level.dropna(subset=['bid']).dropna().copy()
df_level['noise'] = np.random.normal(0,1,size=len(df_level))
df_level['noise'] = np.where(abs(df_level['noise'])<1,0,df_level['noise'])
df_level['bid_noised'] = np.where(df_level['noise']<0,
                                  df_level['bid']+df_level['noise'],
                                  df_level['bid'])
df_level['ask_noised'] = np.where(df_level['noise']>0,
                                  df_level['ask']+df_level['noise'],
                                  df_level['ask'])
df_level['mid_noised'] = (df_level['bid_noised'] + df_level['ask_noised'])/2



ema_bands = calc_ema_std(df_level[['db_bid', 'db_ask']].rename(columns={'db_bid': 'bid',
                                                                         'db_ask': 'ask'}), tau, w_std,N=30, tol=0.024)

ema_bands_prod = calc_ema_std(df_level[['bid', 'ask']], tau, w_std,N=30, tol=0.024)

ema_bands_noised = calc_ema_std(df_level[['bid_noised', 'ask_noised']].rename(columns={'bid_noised': 'bid',
                                                                         'ask_noised': 'ask'}), tau, w_std,N=30, tol=0.024)

ema_bands_simple_noised = calc_ema_m(df_level[['bid_noised', 'ask_noised']].rename(columns={'bid_noised': 'bid',
                                                                         'ask_noised': 'ask'}),
                             tau, 1, 0, 1, tol=0.024)
ema_bands_simple = calc_ema_m(df_level[['bid', 'ask']],
                             tau, 1, 0, 1, tol=0.024)

ema_bands.columns=['lower', 'ema_model', 'upper']
ema_bands_prod.columns=['lower', 'ema_model', 'upper']
ema_bands_noised.columns=['lower', 'ema_model_noised', 'upper']
ema_bands_simple.columns=['lower', 'ema_model_simple', 'upper']
ema_bands_simple_noised.columns=['lower', 'ema_model_simple_noised', 'upper']

model_data = pd.concat([prod_data[['model_p']],ema_bands[['ema_model']]],axis=1).sort_index()
model_data_prod = pd.concat([prod_data[['model_p']],ema_bands_prod[['ema_model']]],axis=1).sort_index()
model_data_simple = pd.concat([ema_bands_simple[['ema_model_simple']],ema_bands_simple_noised[['ema_model_simple_noised']]],axis=1).sort_index()
model_data_noised = pd.concat([ema_bands_noised[['ema_model_noised']],ema_bands_prod[['ema_model']]],axis=1).sort_index()
model_data_filled = model_data.ffill().copy()
