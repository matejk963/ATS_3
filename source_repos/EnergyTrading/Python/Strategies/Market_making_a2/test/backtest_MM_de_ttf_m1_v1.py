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
from Strategies.Market_making_a2.model_class import simple_model
from Strategies.Market_making_a2.backtest_class import BacktestMM
from Strategies.Market_making_a2.strategy_class_original_to_adjust import StrategyMM, VolumeClass
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








def calc_ema_std_kernel_weekly(df_data, tau_fast, tau_slow,
                               w_std, kernel='tanh',
                               std_weights=[-1,0,1],
                               N=30, tol=0, burn=0):
    def kernel_func(diff, std, kernel='tanh'):
        if kernel == 'log':
            # Logarithmic scaling, with a small constant to avoid log(0)
            adjustment_factor = np.sign(diff)*np.log1p(abs(diff)/std)
        elif kernel == 'tanh':
            # Hyperbolic tangent scaling, maps difference to range (-1, 1)
            adjustment_factor = np.tanh(diff/std)
        elif kernel == 'sigmoid':
            # Sigmoid scaling, maps difference to range (0, 1)
            adjustment_factor = (1 / (1 + np.exp(-diff)))*2 -1
        else:
            raise ValueError("Unsupported kernel. Choose 'log', 'tanh', or 'sigmoid'.")
        return adjustment_factor
    bands = pd.DataFrame()
    bands_index = []
    std_window = 5  # Rolling window of 5 days for std0
    prev_model_second_col = pd.DataFrame()
    macd_hist_col = pd.DataFrame() # To store second column of model_list

    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        if len(group) == 0:
            continue

        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        
        # Check if the DataFrame has a DateTime index and at least `std_window` unique days
        if not prev_model_second_col.empty and hasattr(prev_model_second_col.index, 'date') and np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
            # Calculate the rolling standard deviation over the last 5 days
            std0 = prev_model_second_col.resample('D').last().dropna().rolling(std_window).mean().iloc[-1].values[0]
            macd_std0 = macd_hist_col.resample('D').std().mean().iloc[-1]
            band_bool = True
        else:
            # If we don't have enough data for 5 days yet, use a default value
            std0 = 1
            band_bool = False# You can adjust this based on how you'd like to handle early days
            
        model_list = []
        for tau in [tau_fast, tau_slow]:
            # if tau == tau_fast:
            model = simple_model(MSTD(tau, N, std0), [tau / 2, N, 2, mid_list[0], std0],
                                 'mstd', burn=burn, time_model=False, tol=tol)
            # else:
            #     model = simple_model(MA(tau, N), [tau/2,N, mid_list[0]],
            #                                'ema', burn=burn, time_model=False, tol=tol)
            model_predict = model.predict(mid_list)
            model_list.append(model_predict)
            
        macd = np.nan_to_num(x=model_list[0][:,0],nan=model_list[0][burn+1, 0])\
            - np.nan_to_num(x=model_list[1][:,0],nan=model_list[1][burn+1,0])
        # model = simple_model(MA(tau_fast//2, n=3), [tau_fast//2/2,3, macd[0]],
        #                            'ema', burn=burn, time_model=False, tol=tol)
        model = simple_model(MSTD(tau_fast//2, 3, std0), [tau_fast//2 / 2, 3, 2, macd[0], 0],
                             'mstd', burn=0, time_model=False, tol=0)
        signal_line = model.predict(macd)
        
        macd_hist = (macd - np.nan_to_num(x=signal_line[:,0],nan=signal_line[1,0]))
            
        
        
        # Append the second column (m[1]) to prev_model_second_col for future rolling std calculation
        new_data = pd.DataFrame([m for m in model_list[1][:,1]], index=group.index, columns=['std'])        
        prev_model_second_col = pd.concat([prev_model_second_col, new_data])
        macd_hist_data = pd.DataFrame([m for m in macd_hist], index=group.index, columns=['std'])  
        macd_hist_col = pd.concat([macd_hist_col, macd_hist_data])
        
        # Ensure that we start adding bands after 5 days of data
        # if np.unique(prev_model_second_col.index.date).shape[0] >= std_window:
        if band_bool:
            
            macd_hist_norm = macd_hist/macd_std0
            
            # Extract the first (ema) and second (mrg) elements from model_list
            ema_list = [x[0] for x in model_list[1]]
            factor_list = [kernel_func(diff, std, kernel='sigmoid') for std, diff in zip(model_list[0][:, 1],
                                                                                        macd_hist_norm)]
            
            
            bands_index.append(group.index.values)
            bands_group = []
            for std_weight in std_weights:
                bands_group.append([price + 2*(std_weight + factor)*std if std_weight != 0
                                    else price
                                   for price, factor, std
                                   in zip(ema_list, factor_list,
                                          model_list[1][:,1])])
            bands_group.append(list(model_list[1][:,1]))
                
            bands_group_df = pd.DataFrame(bands_group).T
            
            if bands.empty:
                bands = bands_group_df.copy()
            else:
                bands = pd.concat([bands, bands_group_df])
                
    bands.index = np.concatenate(bands_index)

    return pd.DataFrame(bands, index=np.concatenate(bands_index)).ffill()

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

import pickle
file_path = r'Z:\Data\Spot\MM\Inputs\input_data_simple_mm_de_ttf_m1_20240801_20240901.pickle'
with open(file_path, 'rb') as f:
    input_data_dict = pickle.load(f)
try:
    df_ba_a, df_tr_a, df_ba, df_tr, ema_bands, ema_bands2 = input_data_dict.values()
except:
    df_ba_a, df_tr_a, df_ba, df_tr, ema_bands = input_data_dict.values()

# n_s = 0
# start_date = datetime(2024, 9, 1)
# end_date = datetime(2024, 9, 10)
# dates = pd.date_range(start_date, end_date, freq='B')
# market = ['de', 'ttf']
# tenor = ['m']*2
# tn1_list = [1, 1]
# tn2_list = []
# brk_list = ['eex']
# mm_bool = [True, True]

# start_time = time(9, 0, 0, 0)
# end_time = time(17, 0, 0, 0)
# gran = None
# gran_t = '1s'
# coeff_list = norm_coeff([1, -2], market)


# ob_data = True
# tp_data = True

# df_ba = pd.DataFrame([])
# df_tr = pd.DataFrame([])

# spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
# data_class = SpreadViewerData()
# db_class = TPDataDa()
# tenors_list = spread_class.tenors_list
# if not ob_data:
#     data_class.load_best_order_otc(market, tenors_list,
#                                     spread_class.product_dates(dates, n_s),
#                                     db_class,
#                                     start_time=start_time, end_time=end_time)
# else:
#     if tp_data:
#         data_class.load_best_ob_tp(market, tenors_list,
#                                     spread_class.product_dates(dates, n_s),
#                                     db_class,
#                                     start_time=start_time, end_time=end_time)
#     else:
#         data_class.load_best_ob(market, tenors_list, dates, spread_class.product_dates(dates, n_s),
#                                 v_thres=.5, freq=gran)

# data_class_tr = SpreadViewerData()
# data_class_tr.load_trades_otc(market, tenors_list, db_class,
#                               start_time=start_time, end_time=end_time)

# for d in dates:
#     d_range = pd.date_range(d, d)
#     data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
#                                             start_time=start_time, end_time=end_time)
#     df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
#     col_list=['bid', 'ask', 'volume']
#     trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
#                                               start_time=start_time, end_time=end_time,
#                                               col_list=col_list, data_dict=data_dict)
#     df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    
#     df_ba = pd.concat([df_ba, df_ba_], axis=0)
#     df_tr = pd.concat([df_tr, df_tr_], axis=0)



# Model
tau_t = 10
tau_ema = 22
data = tick_data(df_tr, tau_t, tau_ema)
N = 30
tau_m = 30



# # Assign common datetime to model prices
# # Convert the datetime index of df_data to date for alignment
df_ba['date'] = pd.to_datetime(df_ba.index.date)



method = 'simple_mtm'

for tau_fast in [20]:
    tau_slow = 50
    for w_std in [1]:
        
        title = f'tau: {tau_fast} & w_std: {w_std}'       
        
        # tau = 50
        margin = 0.7
        eql_p = -6.25
        # Percent weight for model
        w = 0
        # Percent weight for margin
        w1 = 1
        # w_std = 2
        scaling_factor = 1
        
        # emabands
        ema_bands = calc_ema_std_kernel_weekly(df_ba,tau_fast, tau_slow, w_std,N=30, tol=0.024).bfill()
        # Adjust trades
        # df_em = adjust_std_based_on_distance(ema_bands.copy(), model_price_df, scaling_factor=scaling_factor, beta=0.)
        df_em = ema_bands.copy()
        
        df_ba_a = df_ba.loc[df_em.index, :]
        df_tr_a = adjust_trds(df_tr.copy(), ema_bands.copy()).loc[:df_ba_a.index[-1]]
        # df_em = model_input.copy()
        
        # model_input = df_model_bounds.reset_index().copy()
        # model_input = pd.merge(df_ba_a[['date']], model_input, left_on='date', right_on='datetime',
        #                        how='left').drop(['date', 'datetime'], axis=1)
        # model_input.index = df_ba_a.index
        
        
        # input_data_dict = {
        #     'df_ba_a': df_ba_a,
        #     'df_tr_a': df_tr_a,
        #     'df_ba': df_ba,
        #     'df_tr': df_tr,
        #     'ema_bands': ema_bands
        #     # 'ema_bands2': ema_bands2
        #     }
        
        # # Sotore input data
        # file_path = r'Z:\Data\Spot\MM\Inputs\input_data_simple_mm_de_ttf_m1_20240901_20240910.pickle'
        # with open(file_path, 'wb') as f:
        #     pickle.dump(input_data_dict, f)
        
        
        instr = 'w1x2'
        data_dict = {}
        data_dict[instr] = BacktestMM.merge_data(df_ba_a, df_tr_a, False)
        # Get last trading date of contract
        data_dict[instr]['lt_date'] = get_last_trading_day_series(data_dict[instr])
        
        ts = data_dict[instr].index
        df_em = df_em[~df_em.index.duplicated(keep='first')]
        df_em = df_em.reindex(ts.drop_duplicates()).ffill()
        data_dict['output'] = df_em.loc[ts,:]
        
        param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
        contr_vars = ['threshold']
        param_dict = {k: [] for k in param_list}
        param_dict['t_end'] = time(16,0,0)
        param_dict['take_profit'] = 3
        param_dict['stop_loss_rat'] = 1
        param_dict['ba_spread'] = 0.5
        param_dict['ba_max'] = 0.2
        param_dict['br_fee'] = 0.07
        # param_dict['take_profit'] = 1
        # param_dict['stop_loss'] = 1
        
        vol_class = VolumeClass(1, {'max_clips': 1})
        backtest_class = BacktestMM(vol_class)
        strategy_class = StrategyMM('MM', 'de', instr, is_overnight=False)
        strategy_class.load_params(param_dict, contr_vars)
        
        
        
        xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)
        
        # Create stats df
        stat_dict = strategy_class.stats_dict
        stats_dict = {a:b for a, b in stat_dict.items() if a not in ['mark_ask', 'mark_bid', 'mark_ts']}
        stats_df = pd.DataFrame(stats_dict)
        
        # Plot xx on a separate chart
        plt.figure(figsize=(14, 7))
        xx.plot(grid=True, legend=True, figsize=(12, 8))  # Adjust the figsize as needed
        plt.title(title)
        plt.show()
        
        # If 'timestamp' is a column and not the index, set it as the index
        if 'timestamp' in stats_df.columns:
            stats_df.set_index('timestamp', inplace=True)
        
        # Plot the rest of the data with missing dates skipped (smooth charts)
        fig, ax = plt.subplots(figsize=(14, 7))  # Create a figure and axis for the combined plot
        
        # Plot the first two columns of 'w1x2' DataFrame
        data_dict[instr].iloc[:, :2].dropna().plot(ax=ax, grid=True, legend=True)
        
        # Plot the third column of 'w1x2' with dots
        data_dict[instr].iloc[:, 4].dropna().plot(ax=ax, grid=True, legend=True, style='.', color='black')
        
        # Plot the 'output' DataFrame
        data_dict['output'].dropna().plot(ax=ax, grid=True, legend=True)
        
        # Now, plot the price_level with red or green dots based on the position
        positive_points = stats_df[stats_df['position'] > 0]
        negative_points = stats_df[stats_df['position'] < 0]
        
        # Plot positive points in green (scatter plot)
        ax.scatter(positive_points.index, positive_points['price_level'], color='green', label='Positive Position', s=50)
        
        # Plot negative points in red (scatter plot)
        ax.scatter(negative_points.index, negative_points['price_level'], color='red', label='Negative Position', s=50)
        
        # Now, add vertical dashed lines for each point with 50% opacity
        for pos_index in positive_points.index:
            ax.axvline(x=pos_index, color='green', linestyle='--', alpha=0.5)
        
        for neg_index in negative_points.index:
            ax.axvline(x=neg_index, color='red', linestyle='--', alpha=0.5)
        
        # Add legend and grid
        ax.legend()
        ax.grid(True)
        plt.title(title)
        
        # Show the plot
        plt.show()
