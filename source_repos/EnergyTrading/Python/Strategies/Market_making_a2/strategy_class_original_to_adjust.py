# -*- coding: utf-8 -*-
"""
Created on Mon Nov 27 17:25:55 2023

@author: Marek
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
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


class StrategyMM(StrategyClass):
    bid = np.nan
    ask = np.nan
    def __init__(self, strategy, market, instrument, actions=[-1, 0, 1],
                 no_action=0, precision=3, is_overnight=True):
        super().__init__(strategy, market, instrument, actions, no_action,
                         precision, is_overnight)
        param_list = ['take_profit_rat', 'stop_loss_rat', 'ba_spread', 'ba_max',
                      'take_profit', 'stop_loss', 'br_fee', 't_end']          
        param_dict = {k: np.nan for k in param_list}
        self.update_params(param_dict)
        # Stats
        stats_list = ['timestamp', 'curr_time', 'position', 'price_level',
                      'price_bid', 'price_ask', 'status',
                      'mark_ts', 'mark_bid', 'mark_ask']
        self.stats_dict = {k: [] for k in stats_list}

    def get_constructor_params(self):
        return {
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
        self.update_params(param_dict)

    @property
    def mark_dict(self):
        return {t: [b, a] for t, b, a in zip(self.stats_dict['mark_ts'],
                                             self.stats_dict['mark_bid'],
                                             self.stats_dict['mark_ask'])}

    def process(self, price_dict, act_input, method, volm_class, trade_type):
        # Process data
        timestamp_ = price_dict['timestamp']
        mid_p = price_dict['mid_price']
        bid_p = price_dict['bid_price']
        ask_p = price_dict['ask_price']
        trd_p = price_dict['trd_price']
        trd_s = price_dict['trd_side']
        # Check if need to close position
        act, stop_bool = self.check_state(timestamp_, bid_p, ask_p, mid_p,
                                          trade_type, act_input)
        if stop_bool is not True:
            # Process output from prediction algorithm
            act, p = self.process_action(act_input, bid_p, ask_p, trd_p, trd_s,
                                         method)

        else:
            p = self.calc_close_price(act, bid_p, ask_p, trade_type)
                    # Check for volume constraints
        act = self.check_pending_position(timestamp_, act, volm_class)
        price, vol = self.take_position(act, p, timestamp_, bid_p, ask_p, mid_p,
                                        volm_class, trade_type, stop_bool)
        
        if volm_class.reset_bool:
            volm_class.reset()
        return price, vol

    def process_action(self, act_input, bid_mkt, ask_mkt, trd_mkt, trd_sid,
                       method):
        # Process action input
        if method == 'mstd':
            bid, ask = self.__process_mstd(act_input)
        elif method == 'simple':
            bid, ask = self.__process_simple(act_input)
        elif method == 'simple_mtm':
            mid_mkt = .5 * (bid_mkt + ask_mkt)
            bid, ask = self.__process_simple_mtm(act_input, mid_mkt)
        else:
            raise ValueError('Unknown method %s' % method)
        self.bid = bid
        self.ask = ask
        action = self.no_action
        price = np.nan
        if bid >= ask_mkt:
            action = 1
            price = bid
        elif ask <= bid_mkt:
            action = -1
            price = ask
        if not np.isnan(trd_mkt):
            if trd_mkt <= bid and trd_sid in ['buy', 'all']:
                action = 1
                price = bid
            elif trd_mkt >= ask and trd_sid in ['sell', 'all']:
                action = -1
                price = ask
        return action, price

    def check_state(self, timestamp, bid_price, ask_price, mid_price,
                    trade_type, act_input):
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
            return action, stop_bool
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
        if net_profit >= self.param_dict['take_profit'] * act_input[3]:
            action = self.close_action
            stop_bool = True
        elif net_profit <= self.param_dict['stop_loss'] * act_input[3]:
            action = self.close_action
            stop_bool = True
        # Close position overnight
        if ts >= self.param_dict['t_end']:
            action = self.close_action
            stop_bool = True
        return action, stop_bool

    def __process_simple(self, act_input):
        return act_input[0], act_input[2]

    def __process_simple_mtm(self, act_input, mid_mkt):
        if self.curr_position == 0:
            return act_input[0], act_input[2]
        else:
            fix_mrgn = act_input[2] - act_input[0]
            mid_mkt_ = act_input[1]
            #mid_mkt_ = mid_mkt
            tp = self.param_dict['take_profit'] * act_input[3]
            sl = abs(self.param_dict['stop_loss']) * act_input[3]
            mtm = (mid_mkt_ - self.last_traded_price) * np.sign(self.curr_position)
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
                      mid_price, volm_class, trade_type, stop_bool):
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
            ba_spread = ask_price - bid_price
            if ba_spread > self.param_dict['ba_max'] and open_bool:
                # Do not open position if B/A spread exceeds threshold
                write_bool = False
                trade_type_ = 'MID'
                vol = 0
            if trade_type_ == 'CMB':
                if ba_spread < self.param_dict['ba_spread']:
                    trade_type_ = 'MID'
                else:
                    trade_type_ = 'AGG'
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
