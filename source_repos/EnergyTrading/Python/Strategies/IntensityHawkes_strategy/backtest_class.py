# -*- coding: utf-8 -*-
"""
Created on Thu Dec  7 17:37:56 2023

@author: Marek
"""

import numpy as np
import abc
import pandas as pd
from datetime import datetime, time

from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from OrderBook.OrderBook import OrderBookSnaps
from Utilities.data_functions import clean_data

tol = 1e-6  
trade_type_mm = {'open': 'MM', 'close': 'MID', 'trigg': 'MM'}


class BacktestClass():
    __metaclass__ = abc.ABCMeta
    
    current_t = 0
    nT = 0
    volm_class = None
    trade_type = []
    pnl_dict = {}
    prices_dict = {}
    
    def __init__(self, volm_class, trade_type):
        self.volm_class = volm_class
        self.trade_type = trade_type
        pnl_list = ['timestamp', 'pnl', 'mtm', 'vol']
        self.pnl_dict = {k: [] for k in pnl_list}

    @abc.abstractmethod
    def simulate_strategy(self):
        pass

    @property
    def is_active(self):
        if self.current_t + 1 <= self.nT:
            active = True
        else:
            active = False
        return active

    @property
    def curr_profit(self):
        val_pnl = sum(self.pnl_dict['pnl'])
        val_mtm = sum(self.mtm_dict['mtm'])
        return val_pnl + val_mtm

    @property
    def profit_series(self):
        # Cummulative profit series
        vol = self.volm_class.base_volume
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        profit_list = np.cumsum([(p + m) / vol for p, m in
                                 zip(pnl_list, mtm_list)])
        return pd.Series(profit_list, index=self.pnl_dict['timestamp'])
    
    

    @property
    def profit_active_series(self):
        # Cummulative profit series
        vol = self.volm_class.base_volume
        pos_list = self.pnl_dict['vol']
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        tst_list = self.pnl_dict['timestamp']
        profit_list = np.cumsum([(p + m) / vol for p, m, v in
                                 zip(pnl_list, mtm_list, pos_list)
                                 if abs(v) > 0])
        ts_list = [t for t, v in zip(tst_list, pos_list) if abs(v) > 0]
        return pd.Series(profit_list, index=ts_list)

    @property
    def profit_trade_series(self):
        vol = self.volm_class.base_volume
        pos_list = self.pnl_dict['vol']
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        tst_list = self.pnl_dict['timestamp']
        dpos_list = [0]
        dpos_list = [x - y for x, y in zip(pos_list[:-1], pos_list[1:])]
        cls_list = [True if abs(x) > 0  and v == 0 else False
                    for x, v in zip(dpos_list, pos_list)]
        prof_list = np.cumsum([(p + m) / vol for p, m in
                               zip(pnl_list, mtm_list)])
        ts_list = [t for t, a in zip(tst_list, cls_list) if a]
        profit_list = [p for p, a in zip(prof_list, cls_list) if a]
        return pd.Series(profit_list, index=ts_list)

    def trades_summary(self, freq):
        # Position summary
        pos_list = self.pnl_dict['vol']
        dpos_list = [x - y for x, y in zip(pos_list[:-1], pos_list[1:])]
        dpos_list.append(0)
        act_list = [0 if x == 0 else 1 for x in dpos_list]
        act_series = pd.Series(act_list, index=self.pnl_dict['timestamp'])
        return act_series.resample(freq).sum() / 2

    def execute(self, strategy_class, vol):
        if strategy_class.last_status in ['BID', 'ASK']:
            pass
        else:
            volume = vol
        return volume

    def save_trade(self, price_dict, price, vol, position):
        # Append profit from last trade
        timestamp_ = price_dict['timestamp']
        price_1 = price_dict['mid_price']
        price_0 = self.prices_dict['mid_price']
        # PNL
        val_pnl = -price * vol
        # MTM
        val_mtm = (price_1 - price_0) * (position - vol) + price_1 * vol
        self.pnl_dict['timestamp'].append(timestamp_)
        self.pnl_dict['pnl'].append(val_pnl)
        self.pnl_dict['mtm'].append(val_mtm)
        self.pnl_dict['vol'].append(position)

    def reset_time(self):
        self.current_t = 0
        self.nT = 0
        self.pnl_dict = {k: [] for k in self.pnl_dict.keys()}
        self.prices_dict = {k: [] for k in self.prices_dict.keys()}
        self.volm_class.reset()
        self.__LoB_num = 0

    def progress_time(self):
        self.current_t += 1


class BacktestIB(BacktestClass):
    def __init__(self, volm_class, trade_type=trade_type_mm):
        super().__init__(volm_class, trade_type)
        price_list = ['timestamp', 'mid_price', 'bid_price', 'ask_price',
                      'trd_price', 'trd_side']
        self.prices_dict = {k: [] for k in price_list}

    @staticmethod
    def merge_data(df_orders, df_trades, adj_action=True):
        # Merge time of orders & trades
        df_orders = df_orders[~df_orders.index.duplicated(keep='first')]
        timestamp = df_orders.index.union(df_trades.index).drop_duplicates()
        df_orders = df_orders.reindex(timestamp).ffill()
        # Prepare orders data
        df_orders['mid'] = .5 * (df_orders.loc[:, 'bid'] + df_orders.loc[:, 'ask'])
        col_dict = {'bid': 'bid_price', 'ask': 'ask_price', 'mid': 'mid_price'}
        df_orders = df_orders.rename(columns=col_dict)
        # Prepare trades data
        val_list = df_trades['price'].values.tolist()
        vol_list = df_trades['volume'].values.tolist()
        if adj_action:
            df_aux = df_orders.loc[df_trades.index]
            mid_list = df_aux.loc[:, 'mid_price'].values.tolist()
            act_list = ['sell' if p >= m else 'buy'
                        for p, m in zip(val_list, mid_list)]
        else:
            aux_list = df_trades['action'].values.tolist()
            act_list = ['sell' if a < 0 else 'buy' for a in aux_list]
        df_trades = pd.DataFrame({'trd_price': val_list, 'trd_side': act_list, 'volume': vol_list},
                                 index=df_trades.index)
        return pd.merge(df_orders, df_trades, left_index=True, right_index=True,
                        how='left').dropna(how='all')

       
    
    def simulate_strategy(self, strategy_class, instr, df_data):
        # Simulate strategy defined by strategy class
        # Prepare data
        # df_data = data_dict[instr].reset_index()
        # self.strategy_class.model.train_model()
        # df_data = self.return_data_dict[self.strategy_class.model.products[0]]
        price_dict = df_data.to_dict('list')
        price_dict['datetime'] = pd.to_datetime(price_dict['datetime'])
        if 'timestamp' not in price_dict.keys():
            price_dict['timestamp'] = price_dict['datetime']
        price_dict.pop('index', None)
        del df_data
        # Reset class
        self.reset_time()
        self.nT = len(price_dict['timestamp'])
  
        aux_dict = {k: v[self.current_t] for k, v in price_dict.items()}
        last_timestamp = None
        self.prices_dict.update(aux_dict)
        start_time = aux_dict['timestamp'].date()
        bid_event_times = []
        ask_event_times = []
        recalc_cluster = True
        while self.is_active:
            aux_dict = {k: v[self.current_t] for k, v in price_dict.items()}
            # Update price dict after night
            if aux_dict['timestamp'].date() != self.prices_dict['timestamp'].date():
                self.prices_dict.update(aux_dict)
                
            if last_timestamp is not None:
                if last_timestamp.date() != aux_dict['timestamp'].date():                    
                    start_time = aux_dict['timestamp'].date()
                    bid_event_times = []
                    ask_event_times = []
                    recalc_cluster = True
            if not np.isnan(aux_dict['trd_price']):
                if aux_dict['trd_side'] == 1:
                    ask_event_times.append(aux_dict['timestamp'])
                elif aux_dict['trd_side'] == -1:
                    bid_event_times.append(aux_dict['timestamp'])
                
            price, vol = strategy_class.process(aux_dict, start_time,
                                                bid_event_times,
                                                ask_event_times,
                                                self.volm_class, self.trade_type,
                                                recalc_cluster)
            
            vol = self.execute(strategy_class, vol)
            position = strategy_class.curr_position
            self.save_trade(aux_dict, price, vol, position)
            # Update last prices
            self.prices_dict.update(aux_dict)
            last_timestamp = aux_dict['timestamp']
            self.progress_time()
            recalc_cluster = False
        if not self.is_active:
            print('stop')
        self.bid_event_times = bid_event_times
        self.ask_event_times = ask_event_times
        return self.profit_series

    def update_params(self, param_dict):
        pass

    def cost_function(self, output_series, method):
        # Process output from calibration
        ret = np.diff(output_series.values, n=1)
        if method == 'avg':
            output_val = -np.mean(ret)
        elif method == 'std':
            output_val = np.std(ret)
        elif method == 'sharp':
            output_val = -np.mean(ret) / np.std(ret)
        else:
            ValueError('backtest_class: cost function unknown method :', method)
        return output_val
