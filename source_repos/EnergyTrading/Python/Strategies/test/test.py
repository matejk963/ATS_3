from RiskPremium.RP_Tools import TP_trades_data
import pandas as pd
from datetime import datetime, time
import cx_Oracle
from Database.TPData import TPData
import pickle
# try:
#     cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
# except:
#     pass

# data_class = TPData()

# mkt_list = ['de']
# tenor_list = ['m']
# tn_list = [1]
# prod = 'base'
# venue_list = ['eex']
# start_date = datetime(2019, 1, 1)
# end_date = datetime(2023, 9, 1)
# n_s = 2

# dates = pd.date_range(start_date, end_date, freq='B')
# product_date = [dates.shift(1, freq='B') if t == 'da' else
#                 dates.shift(1, freq='D') if t == 'd' else
#                 dates.shift(tn, freq='W-MON') if t == 'w' else
#                 (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
#                 (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
#                 (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
#                 for t, tn in zip(tenor_list, tn_list)]


# start_time = time(8, 0, 0)
# end_time = time(18, 0, 0)

# tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
# agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}

# for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
#     df_tr = pd.DataFrame([])
#     series = pd.Series(p_dates, index=dates)
#     for p_d, ds in series.groupby(series).groups.items():
#         bT = datetime.combine(ds[0], start_time)
#         eT = datetime.combine(ds[-1], end_time)
#         # Trades
#         data_class.create_connection('OracleSQL')
#         df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
#         try:
#             df_tr_aux = df_tr_aux.between_time(start_time, end_time)
#         except(TypeError):
#             pass
#         #df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
#         df_tr = pd.concat([df_tr, df_tr_aux])
#     df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
#     df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
#     tr_data_dict[m + t + str(n)]       = df_tr

# with open('m1_trades_2019-2023.pickle', 'rb') as pickle_file:
#     tr_data_dict = pickle.load(pickle_file)['dem1'].reset_index()
#     tr_data_dict = {'dem1': tr_data_dict}


from Strategies.Models.Model_trades import TradesModel, TradesModelRaw
from Math.ti_class import TI_class
from Strategies.Backtester_class import BacktesterClass
from Strategies.Strategy_class import StrategyVolatility1, StrategyMeanReversion
import plotly_express as px
from Strategies.Calibration_class import Calibration
import numpy as np
from Database.TPData import TPData
from Utilities.plotUtils import bokehPlot

# df = pd.read_excel(r'S:\Algo\Database\Backups\TTF_sample.xlsx',
#                     usecols=[0, 4, 5, 6],
#                     parse_dates=[0])
# df = df.iloc[:574410].copy()
# df.columns = ['datetime', 'price', 'volume', 'type']
# trades = df.loc[df['type'] == 'TRADE', ['datetime', 'price', 'volume']]
# trades = trades.sort_values(by='datetime')
# trades.reset_index(drop=True, inplace=True)
# std = trades['price'].std()
# avg = trades['price'].mean()
# mask = trades['price'] - avg < 2.5*std
# mask[0] = True
# filtered = trades.loc[mask].dropna().copy()
# filtered = filtered.loc[filtered['volume'] > 0]
# tr_data_dict = {'dem1': filtered}
# with open('ttf_sample.pkl', 'wb') as f:
#     pickle.dump(tr_data_dict, f)
with open(r'X:\Strategies\test\ttf_sample.pkl', 'rb') as pickle_file:
    tr_data_dict = pickle.load(pickle_file)['dem1'].reset_index()
    tr_data_dict = {'dem1': tr_data_dict}
def run_backTest_w_params(param_val):
    back_test = BacktesterClass()
    model = TradesModelRaw(params=param_val)
    strat = StrategyVolatility1(trade_col='price', comp_col='price',params=param_val)
    output_series = back_test.simulate_strategy(tr_data_dict, model, strat)

    return strat.data_df, output_series, pd.DataFrame(back_test.pnl_dict), strat.stats_dict
# [47.58733037,  6.36511507,  1.57869689,  0.64894976,  9.85709273]
# [20,  20,  2,  0.6,  15]
# [30,  10,  1.3,  0.65,  9] reversed 0.01 mean
df_data, returns, trades_data, strat = run_backTest_w_params(np.array([40, 3, 3.5, 10,  1.3,  0.7,  12]))
trades_data.set_index('index',inplace=True)
df_data.set_index('index',inplace=True)
df_data.reset_index(drop=True,inplace=True)
df= pd.concat([df_data, trades_data[['pnl', 'm_diff', 'take_profit', 'stop_loss']]], axis=1)
bokehPlot(df, title="strategy sl/tp fixed by position",
           col_list=[['price', 'ema', 'take_profit', 'stop_loss', 'openUp', 'openDown', 'emalong']],
           scatter=['take_profit', 'stop_loss'], sub=1)
returns.cumsum().plot()
print('pnl ratio', len(returns[returns > 0])/len(returns))
print('profit mean/ loss mean', returns[returns > 0].mean(), returns[returns < 0].mean())


opt_param = {
    'reaction_window': {
        'min': 10,
        'max': 100
    },
    'volume_thresh': {
        'min': 2,
        'max': 10
    },
    'open_thresh': {
        'min': 1.0,
        'max': 2.5
    },
    'close_thresh': {
        'min': 0.1,
        'max': 0.9
    },
    'tau_ema': {
        'min': 5,
        'max': 30
    }
}
# cal = Calibration(opt_param=opt_param, method='avg')
# result, best_values, o = cal.calibrate_np(tr_data_dict, TradesModelRaw, StrategyVolatility1)
# print(result)


