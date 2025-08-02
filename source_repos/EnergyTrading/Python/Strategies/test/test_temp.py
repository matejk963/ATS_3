import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Market_making.model_class import simple_model
tol=(1e-1)/2

from Strategies.Strategy_base import Strategy_base
from Strategies.Backtester_class import BacktesterClass
from Strategies.Strategy_MeanR_NT import Strategy_MeanR_NT

import pickle
with open("de_m1q1_23.pkl", 'rb') as pickle_file:
    data_p = pickle.load(pickle_file)

from Strategies.Models.model_trend import Model_trend, Model_mstd

back_test = BacktesterClass('m', trade_type='mm')
model_t = Model_trend(20, 30)
model_m = Model_mstd(20, 30)
models = [model_m, model_t]
strat = Strategy_MeanR_NT([1, 1, .5, 1, 30, 30], models)
back_test.simulate_strategy(data_p, strat, models)


# n_s = 3
# start_date = datetime(2023, 7, 1)
# end_date = datetime(2023, 8, 28)
# dates = pd.date_range(start_date, end_date, freq='B')
# market = ['de', 'de']
# tenor = ['m', 'q']
# tn1_list = [1, 1]
# tn2_list = []
# brk_list = ['eex']
# mm_bool = [True, False]

# start_time = time(9, 0, 0, 0)
# end_time = time(17, 25, 0, 0)
# gran = None
# coeff_list = norm_coeff([1, -1], market)


# ob_data = False

# df_ba = pd.DataFrame([])
# df_tr = pd.DataFrame([])

# spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
# data_class = SpreadViewerData()
# db_class = TPData()
# tenors_list = spread_class.tenors_list
# if not ob_data:
#     data_class.load_best_order_otc(market, tenors_list,
#                                    spread_class.product_dates(dates, n_s),
#                                    db_class,
#                                    start_time=start_time, end_time=end_time)
# else:
#     data_class.load_best_ob(market, tenors_list, dates, spread_class.product_dates(dates, n_s),
#                             v_thres=5, freq=gran)

# data_class_tr = SpreadViewerData()
# data_class_tr.load_trades_otc(market, tenors_list, db_class,
#                               start_time=start_time, end_time=end_time)


# data_dict = spread_class.aggregate_data(data_class, dates, n_s, gran=gran,
#                                         start_time=start_time, end_time=end_time)
# df_ba = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb'])
# col_list=['bid', 'ask', 'volume']
# trade_dict = spread_class.aggregate_data(data_class_tr, dates, n_s, gran='1S',
#                                          start_time=start_time, end_time=end_time,
#                                          col_list=col_list, data_dict=data_dict)
# df_tr = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool)

# data_p = df_tr['price']


# import pickle
# with open('de_m1q1_23.pkl', 'wb') as f:
#     pickle.dump(data_p.dropna(), f)