# -*- coding: utf-8 -*-
"""
Created on Mon Nov 27 17:25:55 2023

@author: Marek
"""

import numpy as np
import pandas as pd
import datetime as dt
import matplotlib.pyplot as plt
from Math.accumfeatures import MSTD, MA, EMA
import abc
tol = 1e-6


class StrategyClass():
    __metaclass__ = abc.ABCMeta

    _position = 0
    market = ''
    instrument = ''
    strategy = ''
    param_dict = dict()
    state_vars = []
    contr_vars = []
    _actions = []
    _no_action = None
    _precision = np.nan
    stats_dict = dict()
    _is_overnight = False
    
    def __init__(self, strategy, market, instrument, actions, no_action,
                 precision, is_overnight):
        self.strategy = strategy
        self.market = market
        self.instrument = instrument
        self._actions = actions
        self._no_action = no_action
        self._precision = precision
        self._is_overnight = is_overnight

    @property
    def inst_key(self):
        return self.market + '_' + self.instrument

    @abc.abstractmethod
    def process(self):
        pass

    @abc.abstractmethod
    def process_action(self):
        pass

    def update_params(self, param_dict_):
        self.param_dict.update(param_dict_)
        if not self.param_dict['stop_loss_rat']:
            pass
        else:
            self.param_dict['stop_loss'] = -(self.param_dict['take_profit'] *
                                             self.param_dict['stop_loss_rat'])
        return 0

    @property
    def curr_position(self):
        return self._position

    @property
    def param_list(self):
        return list(self.param_dict.keys())

    @property
    def last_position(self):
        try:
            position_ = self.stats_dict['position'][-1]
        except(IndexError):
            position_ = 0
        return position_

    @property
    def last_status(self):
        try:
            status_ = self.stats_dict['status'][-1]
        except(IndexError):
            status_ = 0
        return status_

    @property
    def last_traded_ts(self):
        try:
            timestamp_ = self.stats_dict['curr_time'][-1]
        except(IndexError):
            timestamp_ = np.nan
        return timestamp_

    @property
    def last_traded_price(self):
        try:
            price_ = self.stats_dict['price_level'][-1]
        except(IndexError):
            price_ = np.nan
        return price_

    @property
    def last_traded_bid(self):
        try:
            price_ = self.stats_dict['price_bid'][-1]
        except(IndexError):
            price_ = np.nan
        return price_

    @property
    def last_traded_ask(self):
        try:
            price_ = self.stats_dict['price_ask'][-1]
        except(IndexError):
            price_ = np.nan
        return price_

    @property
    def plot_position(self):
        timestamp_ = self.stats_dict['timestamp']
        pos_series = pd.Series(self.stats_dict['position'], index=timestamp_)
        pos_series.plot()

    def plot_strategy(self, bid_series, ask_series, bT=None, eT=None):
        # Plot strategy with trade
        df_price = pd.concat([bid_series, ask_series], axis=1)
        if bT is None:
            bT = min(df_price.index)
        if eT is None:
            eT = max(df_price.index)
        # Long trades & their prices
        buy_dict = {t: p for t, p, v in zip(self.stats_dict['timestamp'],
                                            self.stats_dict['price_level'],
                                            self.stats_dict['position'])
                    if v > 0}
        sell_dict = {t: p for t, p, v in zip(self.stats_dict['timestamp'],
                                             self.stats_dict['price_level'],
                                             self.stats_dict['position'])
                    if v < 0}
        mark_dict = self.mark_dict
        # plt.figure()
        ax = df_price.loc[bT:eT].plot(grid=True, legend=True, figsize=(36, 24))
        if not buy_dict:
            pass
        else:
            buy_series = pd.Series(buy_dict)
            buy_series.loc[bT:eT].plot(style='o', c='green', ms=10, grid=True,
                                       ax=ax)
        if not sell_dict:
            pass
        else:
            sell_series = pd.Series(sell_dict)
            sell_series.loc[bT:eT].plot(style='o', c='red', ms=10, grid=True,
                                        ax=ax)
        if not mark_dict:
            pass
        else:
            df_mark = pd.DataFrame(mark_dict, index=['bid', 'ask']).T
            df_mark.loc[bT:eT].plot(grid=True, legend=True, ax=ax)
        plt.show()

    def reset(self):
        stats_keys = self.stats_dict.keys()
        self.stats_dict = {k: [] for k in stats_keys}
        self._position = 0


class StrategyHI(StrategyClass):
    bid = np.nan
    ask = np.nan
    def __init__(self, model_class, trades, ba, products,
                 strategy, market, instrument, actions=[-1, 0, 1],
                 no_action=0, precision=3, is_overnight=False, trailing_takeprofit=False):
        super().__init__(strategy, market, instrument, actions, no_action,
                         precision, is_overnight)
        self.model = model_class(trades, ba, products)
        # param_list = ['take_profit_rat', 'stop_loss_rat', 'ba_spread', 'ba_max',
        #               'take_profit', 'stop_loss', 'iceberg_target', 'iceberg_prob', 'br_fee', 't_end']
        param_list = ['bid_threshold', 'ask_threshold',
                        'take_profit', 'stop_loss_rat',
                    'train_lookback', 't_end', 'br_fee']
        param_dict = {k: np.nan for k in param_list}
        self.update_params(param_dict)
        # Stats
        stats_list = ['timestamp', 'curr_time', 'position', 'price_level',
                      'price_bid', 'price_ask', 'status',
                      'mark_ts', 'mark_bid', 'mark_ask', 'bid_int', 'ask_int',
                      'tp', 'sl', 'trail_tp']

        self.stats_dict = {k: [] for k in stats_list}
        self.monitoring_dict = {
            'timestamp': [],
            'bid_int': [],
            'ask_int': [],
            'tp': [],
            'sl': [],
            'trail_tp': []
        }
        self.trades = trades
        self.ba = ba
        self.products = products
        
        self.trailing_takeprofit = trailing_takeprofit
        self.takeprofit_ema = None
        
        self.cluster_price = []
        self.cluster_time  = []
        self.cluster_statistics = None
    
    

    def get_constructor_params(self):
        return {
        'trades': self.trades,
        'ba': self.ba,
        'products': self.products,
        'strategy': self.strategy,
        'market': self.market,
        'instrument': self.instrument,
        'actions': self._actions,
        'no_action': self._no_action,
        'precision': self._precision,
        'is_overnight': self._is_overnight,
        }
    
    @classmethod
    def get_from_copy(cls, param_dict):
        return cls(**param_dict)
    
    @property
    def close_action(self):
        if self.curr_position > 0:
            # Close by selling
            action = -1
        elif self.curr_position < 0:
            # Close by buying
            action = 1
        else:
            # No position no closing
            action = self.no_action
        return action

    @property
    def actions(self):
        return self._actions

    @property
    def no_action(self):
        return self._no_action

    def load_params(self, param_dict, contr_vars):
        self.contr_vars = contr_vars
        self.state_vars = [v for v in self.param_list if v not in contr_vars]
        if 'ba_max' not in param_dict.keys():
            param_dict['ba_max'] = np.inf
        if 'br_fee' not in param_dict.keys():
            param_dict['br_fee'] = 0
        if 'trail_sl_bool' in param_dict.keys():
            self.trailing_takeprofit = param_dict['trail_sl_bool']
        self.update_params(param_dict)

    @property
    def mark_dict(self):
        return {t: [b, a] for t, b, a in zip(self.stats_dict['mark_ts'],
                                             self.stats_dict['mark_bid'],
                                             self.stats_dict['mark_ask'])}
    
    def set_monitoring(self, timestamp, ask_int, bid_int, tp, sl, trail_tp):
        self.monitoring_dict['timestamp'].append(timestamp)
        self.monitoring_dict['ask_int'].append(ask_int)
        self.monitoring_dict['bid_int'].append(bid_int)
        self.monitoring_dict['tp'].append(tp)
        self.monitoring_dict['sl'].append(sl)
        self.monitoring_dict['trail_tp'].append(trail_tp)
        
    def train_model(self):
        # if not hasattr(self.model, 'major_dict'):
        #     self.model.prepare_data()
        #     self.model.set_conditions()
        #     self.model.create_train_test_dict()
        #     self.model.estimate_params(train_lookback=self.param_dict['train_lookback'])
        pass
            
    def get_int_params(self, timestamp):
        date = pd.to_datetime(timestamp.date())
        if not hasattr(self.model, 'params_dict'):
            self.model.estimate_params()
        if date in self.model.params_dict.keys():
            bid_params = self.model.params_dict[date][self.model.products[0]]['bid_params']
            ask_params = self.model.params_dict[date][self.model.products[0]]['ask_params']
            
            return True, bid_params, ask_params
        else:
            return False, [], []
        
    
    def update_timestamps(self, new_timestamp, x_seconds):
        # Append the new timestamp
        self.cluster_time.append(new_timestamp)    
        # Determine the cutoff time
        cutoff_time = new_timestamp - pd.Timedelta(seconds=x_seconds)    
        # Remove timestamps older than the cutoff time
        self.cluster_time = [timestamp for timestamp in self.cluster_time if timestamp > cutoff_time]
    
        

    def reset_cluster(self):  
        self.cluster_price = [] 
        self.cluster_time = []
    def calc_cluster(self, cluster_span, trd_p, timestamp):
        # if len(self.cluster_price) == 0:
        # if trn_p is not None:
        self.cluster_price.append(trd_p)
        self.update_timestamps(timestamp,cluster_span)
        self.cluster_price = self.cluster_price[-len(self.cluster_time):]
        cluster_median = np.nanmedian(self.cluster_price)
        cluster_min = np.nanmin(self.cluster_price)
        cluster_max = np.nanmax(self.cluster_price)
        cluster_max_timestamp = self.cluster_time[self.cluster_price.index(cluster_max)]
        cluster_min_timestamp = self.cluster_time[self.cluster_price.index(cluster_min)]
        self.cluster_statistics = [cluster_median, cluster_max, cluster_min,
                                   cluster_max_timestamp,
                                   cluster_min_timestamp]
        
        
            
        pass

    def process(self, price_dict, start_time,
                bid_event_times,
                ask_event_times,
                volm_class, trade_type,
                recalc_cluster:bool):
        # Process data
        timestamp_ = price_dict['timestamp']
        mid_p = round(price_dict['mid_price'], 2)
        bid_p = round(price_dict['bid_price'], 2)
        ask_p = round(price_dict['ask_price'], 2)
        trd_p = round(price_dict['trd_price'], 2)
        trd_s = price_dict['trd_side']
        trd_v = price_dict['volume']
        if (timestamp_.date == pd.Timestamp('20231218')) and not np.isnan(trd_p):
            print('stop')
        if recalc_cluster:
            self.reset_cluster()
        
        params_bool, bid_params, ask_params = self.get_int_params(timestamp_)
        # print('timestamp: ', timestamp_)
        # print('bid_params: ', bid_params)
        # print('ask_params: ', ask_params)
        # if trd_s is not None:
        #     trade_time
        p = np.nan
        
        # Check if need to close position
        # if not np.isnan(trd_p):
        #     print('stop')
        act, stop_bool, tp, sl, trail_tp = self.check_state(timestamp_, bid_p, ask_p, mid_p,
                                          trade_type)
        bid_int = np.nan
        ask_int = np.nan
        if stop_bool is not True:
            # Process output from prediction algorithm
            if (self.curr_position == 0) and (params_bool is True):
                act, p, bid_int, ask_int = self.process_action(bid_p, ask_p, trd_p, trd_s, timestamp_, bid_event_times,
                                             ask_event_times, bid_params, ask_params, tp, sl, trail_tp)
            # Check for volume constraints
        else:
            p = self.calc_close_price(act, bid_p, ask_p, trade_type)
        
        act = self.check_pending_position(timestamp_, act, volm_class)
        price, vol = self.take_position(act, p, timestamp_, bid_p, ask_p, mid_p,
                                        volm_class, trade_type, stop_bool, bid_int, ask_int,
                                        tp, sl, trail_tp)
        if volm_class.reset_bool:
            volm_class.reset()
            
        if not np.isnan(trd_p):
            self.set_monitoring(timestamp_,
                                ask_int,
                                bid_int,
                                tp,
                                sl,
                                trail_tp)
        
        return price, vol

    def process_action(self, bid_p, ask_p, trd_p, trd_s, timestamp_, bid_event_times,
                                 ask_event_times, bid_params, ask_params, tp, sl, trail_tp):
        
        if bid_event_times:
            self.model.update_event_times(bid_event_times, 'bid')
            bid_intensity = self.model.hawkes_intensity(timestamp_,
                                                    bid_params[0],
                                                    bid_params[1],
                                                    bid_params[2],
                                                    'bid')
        else:
            bid_intensity = None
        if ask_event_times:
            self.model.update_event_times(ask_event_times, 'ask')
            ask_intensity = self.model.hawkes_intensity(timestamp_,
                                                    ask_params[0],
                                                    ask_params[1],
                                                    ask_params[2],
                                                    'ask')
        else:
            ask_intensity = None
        # print('bid_int: ', bid_intensity, ' ',
        #       'ask_int: ', ask_intensity)
        action = self.no_action
        price = np.nan
        
        
        
        if not np.isnan(trd_p):
            self.calc_cluster(30, trd_p, timestamp_)
            c_median, c_max, c_min, c_max_time, c_min_time = self.cluster_statistics
            if (not bid_intensity) and (not ask_intensity):
                pass
            elif bid_intensity and not ask_intensity:
                if bid_intensity>self.param_dict['bid_threshold']:
                    if c_max_time < c_min_time:
                        if c_min != c_median:
                            if bid_p>(trd_p*0.99825):
                                 price = bid_p
                                 action = -1
                        
            elif ask_intensity and not bid_intensity:
                if ask_intensity>self.param_dict['bid_threshold']:
                    if c_max_time > c_min_time:
                        if c_max != c_median:
                            if ask_p<(trd_p*1.00175):
                                price = ask_p
                                action = 1

            elif ask_intensity and bid_intensity:            
                         
                if bid_intensity<ask_intensity:
                    if ask_intensity>self.param_dict['bid_threshold']:
                        if c_max_time > c_min_time:
                            if c_max != c_median:
                                if ask_p<(trd_p*1.00175):
                                    price = ask_p
                                    action = 1

                elif bid_intensity>ask_intensity:
                    if bid_intensity>self.param_dict['bid_threshold']:
                        if c_max_time < c_min_time:
                            if c_min != c_median:
                                if bid_p>(trd_p*0.99825):
                                     price = bid_p
                                     action = -1

        if (timestamp_.date() == dt.date(2024,12,18)) and (not np.nan(price)):
            print('stop')
        return action, price, bid_intensity, ask_intensity
    
    def trailing_takeprofit_action(self, net_profit, bid_ask):
        if not self.takeprofit_ema:
            self.takeprofit_ema = EMA(self.param_dict['trailing_tp_tau'], 0.2)
            print('EMA')
        self.takeprofit_ema.push(net_profit)
        if net_profit <= (self.takeprofit_ema.value-bid_ask/2):
            self.takeprofit_ema = None
            return self.close_action, True, np.nan
        else:
            return self.no_action, False, self.takeprofit_ema.value

    def check_state(self, timestamp, bid_price, ask_price, mid_price,
                    trade_type):
        # Check if stop loss / take profit or close position overnight
        if self._is_overnight:
            ts = timestamp
        else:
            ts = timestamp.time()
        if ts >= self.param_dict['t_end']:
            # No overnight position
            stop_bool = True
        else:
            stop_bool = False
        action = self.no_action
        if abs(self.curr_position) < tol:
            tp, sl, trail_tp = [np.nan] * 3
            return action, stop_bool, tp, sl, trail_tp
        # Stop loss / Take profit check
        if trade_type['trigg'] == 'AGG':
            # Aggressive close position
            if self.curr_position > 0:
                # Need to sell position
                net_profit = bid_price - self.last_traded_price
            else:
                # Need to buy position
                net_profit = self.last_traded_price - ask_price
        elif trade_type['trigg'] == 'MM':
            # MM close position
            if self.curr_position > 0:
                # Need to sell position
                net_profit = ask_price - self.last_traded_price
            else:
                # Need to buy position
                net_profit = self.last_traded_price - bid_price
        elif trade_type['trigg'] == 'MID':
            if self.curr_position > 0:
                # Need to sell position
                net_profit = mid_price - self.last_traded_price
            else:
                # Need to buy position
                net_profit = self.last_traded_price - mid_price
        elif trade_type['trigg'] == 'CMB':
            if self.curr_position > 0:
                # Need to sell position
                net_profit_L = ask_price - self.last_traded_bid
                net_profit_G = bid_price - self.last_traded_ask
                if net_profit_L < 0:
                    net_profit = net_profit_L
                elif net_profit_G > 0:
                    net_profit = net_profit_G
                else:
                    net_profit = 0
            else:
                # Need to sell position
                net_profit_L = self.last_traded_ask - bid_price 
                net_profit_G = self.last_traded_bid - ask_price
                if net_profit_L < 0:
                    net_profit = net_profit_L
                elif net_profit_G > 0:
                    net_profit = net_profit_G
                else:
                    net_profit = 0
        else:
            msg = 'Unknown trade type %s, choose between AGG/MM/MID/CMB'
            raise TypeError(msg % trade_type['trigg'])
        
        # Old version with absolute TP and SL
        # if net_profit >= self.param_dict['take_profit']:
        #     action = self.close_action
        #     stop_bool = True
        # elif net_profit <= self.param_dict['stop_loss']:
        #     action = self.close_action
        #     stop_bool = True
        # udpated TP and SL based on last traded price
        tp = (self.param_dict['take_profit']) * self.last_traded_price
        sl = (self.param_dict['stop_loss']) * self.last_traded_price
        trail_tp = np.nan
        if net_profit >= tp:
            if self.trailing_takeprofit:
                action, stop_bool, trail_tp = self.trailing_takeprofit_action(net_profit, abs(ask_price-bid_price))
            else:
                action = self.close_action
                stop_bool = True
        elif net_profit <= sl:
            action = self.close_action
            stop_bool = True
        # Close position overnight
        if ts >= self.param_dict['t_end']:
            action = self.close_action
            stop_bool = True
        return action, stop_bool, tp, sl, trail_tp

    def __process_simple(self, act_input):
        return act_input[0], act_input[2]

    def __process_simple_mtm(self, act_input, mid_mkt):
        if self.curr_position == 0:
            return act_input[0], act_input[2]
        else:
            fix_mrgn = act_input[2] - act_input[0]
            tp = self.param_dict['take_profit']
            sl = abs(self.param_dict['stop_loss'])
           
            mtm = (mid_mkt - self.last_traded_price) * np.sign(self.curr_position)
            ratio = min(max(mtm + sl, 0) / sl - 1, max(tp - mtm, 0) / (2 * tp) - .5)
            if self.curr_position > 0:
                return act_input[0], act_input[2] + (fix_mrgn * ratio)
            else:
                return act_input[0] - (fix_mrgn * ratio), act_input[2]

    def __process_mstd(self, act_input):
        pass

    def check_pending_position(self, timestamp, action, volm_class):
        # Check if we can add proposed position
        vol = volm_class.push(action)
        if abs(self.curr_position) < tol:
            # Do nothing
            return action
        else:
            if abs(vol) < tol:
                # Do not increase position
                action = self.no_action
        return action

    def take_position(self, action, our_price, timestamp, bid_price, ask_price,
                      mid_price, volm_class, trade_type, stop_bool, bid_int, ask_int,
                      tp, sl, trail_tp):
        # Based on action & trade type calculate volume & price traded
        br_fee = self.param_dict['br_fee']
        if self.is_open_action(action) or not stop_bool:
            # Opening position
            trade_type_ = trade_type['open']
            msg = 'Unknown ENTER trade type %s, choose between AGG/MM/MID/CMB'
            open_bool = True
        else:
            # Closing position
            trade_type_ = trade_type['close']
            msg = 'Unknown EXIT trade type %s, choose between AGG/MM/MID/CMB'
            open_bool = False
        # Creating position
        if action == self.no_action:
            # Do nothing
            vol = 0
            price = mid_price
        else:
            write_bool = True
            # Trade to make position
            vol = volm_class.volume * action
            # Check for large bid/ask spreads
            # Choose price and status based on trading type
            if trade_type_ == 'AGG':
                if action > 0:
                    price = ask_price + br_fee
                else:
                    price = bid_price - br_fee
                status = 'DONE'
            elif trade_type_ == 'MM':
                if action > 0:
                    price = our_price + br_fee
                    status = 'DONE'
                else:
                    price = our_price - br_fee
                    status = 'DONE'
                # Add here probability of getting done
            elif trade_type_ == 'MID':
                if action > 0:
                    price = mid_price + br_fee
                else:
                    price = mid_price - br_fee
                status = 'DONE'
            else:
                raise ValueError(msg % trade_type_)
            # Write next trade or update order
            if write_bool:
                self.stats_dict['timestamp'].append(timestamp)
                self.stats_dict['curr_time'].append(timestamp)
                self.stats_dict['position'].append(vol)
                self.stats_dict['price_level'].append(price)
                self.stats_dict['price_bid'].append(bid_price)
                self.stats_dict['price_ask'].append(ask_price)
                self.stats_dict['status'].append(status)
                self.stats_dict['bid_int'].append(bid_int)
                self.stats_dict['ask_int'].append(ask_int)
                self.stats_dict['tp'].append(tp)
                self.stats_dict['sl'].append(sl)
                self.stats_dict['trail_tp'].append(trail_tp)
            # If MM volume has not been traded
            if status in ['BID', 'ASK']:
                vol = 0
            self._position += vol
        self.stats_dict['mark_ts'].append(timestamp)
        self.stats_dict['mark_bid'].append(self.bid)
        self.stats_dict['mark_ask'].append(self.ask)
        return price, vol

    def is_open_action(self, action):
        if abs(self.curr_position) < tol:
            return True
        else:
            if action == self.close_action:
                return False
            else:
                return True

    def calc_close_price(self, action, bid_mkt, ask_mkt, trade_type):
        price = np.nan
        if trade_type['close'] == 'AGG':
            if action < 0:
                price = bid_mkt
            else:
                price = ask_mkt
        elif trade_type['close'] == 'MM':
            if action < 0:
                price = ask_mkt
            else:
                price = bid_mkt
        elif trade_type['close'] in ['MID', 'CMB']:
            price = .5 * (bid_mkt + ask_mkt)
        else:
            msg = 'Unknown EXIT trade type %s, choose between AGG/MM/MID/CMB'
            raise ValueError(msg % trade_type['close'])
        return price


class VolumeClass:
    _reset_bool = False
    _state_diff = 1
    state = 0
    
    def __init__(self, volume, struct_dict={}):
        self.base_volume = volume
        # Take profit increase state & Stop loss reduce
        try:
            self._state_max = struct_dict['max_clips']
        except(KeyError):
            self._state_max = 1

    @property
    def reset_bool(self):
        return self._reset_bool

    @property
    def max_position(self):
        return self.base_volume * self._state_max

    @property
    def volume(self):
        volume_ = self.base_volume * abs(self._state_diff)
        return volume_

    def close(self, type_, class_):
        pass

    def push(self, vol_diff):
        next_state = abs(self.state + vol_diff)
        if next_state > self._state_max:
            self._state_diff = 0
        else:
            self._state_diff = vol_diff
            self.state += vol_diff
        return self.volume

    def reset(self):
        self.state = 0
        self._state_diff = 1
