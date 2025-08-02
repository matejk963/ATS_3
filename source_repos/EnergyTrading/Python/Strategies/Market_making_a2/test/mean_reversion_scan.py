# -*- coding: utf-8 -*-
"""
Created on Fri Oct  4 10:04:49 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
import datetime as dt
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
# from Math.ti_class import TI_class, VI_class, TR_class
# from Math.lm_class import kalman, LinearModel
# from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
# from Strategies.Spot_strategy.MMSpot.model_class import simple_model
# from Strategies.Spot_strategy.MMSpot.backtest_class import BacktestMM
# from Strategies.Spot_strategy.MMSpot.strategy_class import StrategyMM, VolumeClass
# ADF test
from statsmodels.tsa.stattools import adfuller


from itertools import product

markets = ['de', 'fr']
products = ['m', 'q']
tenors = [1, 2, 3]

# Store the valid combinations
valid_combinations = []

# Generate combinations for markets and products
for (market1, product1), (market2, product2) in product(product(markets, products), repeat=2):
    for tenor1, tenor2 in product(tenors, repeat=2):
        # Allow same tenor only if market1, product1 pair is not the same as market2, product2
        if (market1 == market2 and product1 == product2 and tenor1 != tenor2) or (market1 != market2 or product1 != product2):
            # Create the two combinations
            combo1 = ((market1, product1, tenor1), (market2, product2, tenor2))
            combo2 = ((market2, product2, tenor2), (market1, product1, tenor1))
            # Only add if combo1 is not already in valid_combinations (to avoid reverse duplicates)
            if combo1 not in valid_combinations and combo2 not in valid_combinations:
                valid_combinations.append(combo1)



ba_dict = {}
tr_dict = {}
results_dict = {}

for comb in valid_combinations:
    comb1, comb2 = comb
    market_pair = [comb1[0], comb2[0]]
    product_pair = [comb1[1], comb2[1]]
    tenor_pair = [comb1[2], comb2[2]]


    n_s = 0
    start_date = datetime(2024, 9, 1)
    end_date = datetime(2024, 9, 30)
    dates = pd.date_range(start_date, end_date, freq='B')
    market = market_pair
    tenor = product_pair
    tn1_list = tenor_pair
    tn2_list = []
    brk_list = ['eex']
    mm_bool = [True, True]
    
    start_time = time(9, 0, 0, 0)
    end_time = time(17, 0, 0, 0)
    gran = None
    gran_t = '1s'
    coeff_list = norm_coeff([1, -1], market)
    
    
    ob_data = True
    tp_data = False
    
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
        
        
        
    mid_series = df_ba.mean(axis=1)
    
    

    
    # X = mid_series.loc[mid_series.index.date==np.unique(mid_series.index.date)[:2]].copy()
X = mid_series.copy()

dates = np.unique(X.index.date)

results_df = pd.DataFrame()
for date in dates:
    result = adfuller(X.loc[X.index.date==date])
    temp_df = pd.DataFrame(result[:2],index=['adf_stat', 'p_val'], columns=[date]).T
    results_df = pd.concat([results_df, temp_df])
    # ADF Test
results_dict[(comb1, comb2)] = results_df



    
    
    
    
    
    