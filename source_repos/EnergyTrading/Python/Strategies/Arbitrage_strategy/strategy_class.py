# -*- coding: utf-8 -*-
"""
Created on Tue Sep 17 11:36:30 2024

@author: Marek
"""

import numpy as np
import pandas as pd
import matplotlib as plt
tol = 1e-3


class StrategyArb():
    bid = None
    ask = None
    best_bid_l = None
    best_ask_l = None
    _position = 0
    state_vars = []
    contr_vars = []
    param_dict = dict()
    stats_dict = dict()
    mkt_depth_check = False
    cons_bid = False
    
    def __init__(self, market, instrument, tick_price, broker_list,
                 actions=['bid', 'ask'], time_exe=.1, time_del=.05,
                 filter_aonnimp=True, method='fix', p_depth=.25, min_lvl_cover=0):
        self.market = market
        self.instrument = instrument
        self.tick_price = tick_price
        self.broker_list = broker_list
        self.actions = actions
        self.time_exe = pd.to_timedelta(time_exe, unit='s')
        self.time_del = pd.to_timedelta(time_del, unit='s')
        self.filter_aonnimp = filter_aonnimp
        self.method = method
        self.p_depth = p_depth
        self.min_lvl_cover = min_lvl_cover
        param_list = ['margin', 'mkt_depth_check', 'stop_loss', 'br_fee',
                      'min_margin', 'max_margin', 'cons_level']
        param_dict = {k: np.nan for k in param_list}
        self.update_params(param_dict)
        # Stats
        stats_list = ['timestamp', 'position', 'price',
                      'price_bid', 'price_ask', 'status']
        self.stats_dict = {k: [] for k in stats_list}
        self.__ord_dict = {k: None for k in ['bid', 'ask']}
        self.timestamp_dict = {k: {a: None for a in ['ord', 'exe']}
                               for k in ['bid', 'ask']}

    @property
    def lead_brk(self):
        return self.broker_list[0]

    @property
    def lift_brk_list(self):
        return self.broker_list[1:]

    @property
    def inst_key(self):
        return self.market + '_' + self.instrument

    @property
    def curr_position(self):
        return self._position

    @property
    def is_bid(self):
        return self.bid != None

    @property
    def is_ask(self):
        return self.ask != None

    @property
    def cons_level(self):
        return self.param_dict['cons_level']

    @property
    def param_list(self):
        return list(self.param_dict.keys())

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

    def price_val(self, value):
        return round_to_tick(value, self.tick_price)

    def prop_ord(self, side):
        return self.__ord_dict[side]

    def set_prop_ord(self, timestamp, value, side):
        if self.prop_ord(side) is None:
            self.timestamp_dict[side]['ord'] = timestamp
            self.__ord_dict[side] = value

    def __del_prop_ord(self, side):
        self.timestamp_dict[side]['ord'] = None
        self.__ord_dict[side] = None

    def __set_side_ord(self, side):
        value = self.prop_ord(side)
        if side == 'bid':
            self.bid = value
        elif side == 'ask':
            self.ask = value
        else:
            raise ValueError(f'Strategy Arb: side not known {side}')

    @staticmethod
    def brk_fee(broker_id):
        out_dict = {1441: 0.03 / 2,     # EEX
                    5: 0.03 / 2 + 0.02,        # SPEC
                    10: 0.03 / 2 + 0.015}       # BGC
        try:
            return out_dict[broker_id]
        except(KeyError):
            return 0.03 / 2 + 0.01

    def exe_prop_ords(self, timestamp):
        for side in ['bid', 'ask']:
            timestamp_old = self.timestamp_dict[side]['ord']
            if timestamp_old != None:
                # Check if time passed
                if (timestamp - timestamp_old) >= self.time_del:
                    # Time has passed to execute update
                    self.__set_side_ord(side)
                    # Reset proposed order
                    self.__del_prop_ord(side)
            else:
                # Noting to execute
                pass

    def exe_prop_trds(self, timestamp, bid_best, ask_best, trd_mkt, trd_side, trd_brk):
        vol_list = []
        price_list = []
        for side in ['bid', 'ask']:
            timestamp_old = self.timestamp_dict[side]['exe']
            if timestamp_old != None:
                # Check if time passed
                if (timestamp - timestamp_old) >= self.time_exe:
                    # Time has passed to lift order
                    price, vol = self.__lift_order(timestamp, bid_best, ask_best, side,
                                                   trd_mkt, trd_side, trd_brk)
                    price_list.append(price)
                    vol_list.append(vol)
        return price_list, vol_list

    def update_params(self, param_dict):
        self.param_dict.update(param_dict)
        if 'mkt_depth_check' not in param_dict.keys():
            self.mkt_depth_check = False
        else:
            self.mkt_depth_check = param_dict['mkt_depth_check']
        if 'cons_level' not in param_dict.keys():
            self.cons_bid = False
        else:
            self.cons_bid = True

    @property
    def data_columns(self):
        cols_list = ['bid_price', 'ask_price', 'bid_lead', 'ask_lead']
        if self.mkt_depth_check:
            cols_list.extend(['bid_cls', 'ask_cls'])
        if self.cons_bid:
            cols_list.extend(['bid_other', 'ask_other'])
        return cols_list

    def get_attributes(self, LoB):
        if self.filter_aonnimp:
            LoB = LoB.filter_aonnimpl()
        # Order attributes
        try:
            bid_lead = LoB.best_bid_ven(self.lead_brk).price_val
        except(AttributeError):
            bid_lead = np.nan
        try:
            ask_lead = LoB.best_ask_ven(self.lead_brk).price_val
        except(AttributeError):
            ask_lead = np.nan
        if not self.lift_brk_list:
            try:
                bid_best = LoB.best_bid.price_val
            except(AttributeError):
                bid_best = np.nan
            try:
                ask_best = LoB.best_ask.price_val
            except(AttributeError):
                ask_best = np.nan
        else:
            try:
                bid_best = LoB.best_bid_vens(self.broker_list).price_val
            except(AttributeError):
                bid_best = np.nan
            try:
                ask_best = LoB.best_ask_vens(self.broker_list).price_val
            except(AttributeError):
                ask_best = np.nan
        out_list = [bid_best, ask_best, bid_lead, ask_lead]
        if self.mkt_depth_check:
            bid_dict = LoB.volume_bids(self.p_depth)
            ask_dict = LoB.volume_asks(self.p_depth)
            try:
                bid_lvl_list = list(bid_dict.keys())
                if self.min_lvl_cover > 0:
                    bid_cls = [x for x in bid_lvl_list if x <= bid_best - self.min_lvl_cover][0]
                else:
                    bid_cls = bid_lvl_list[-1]
            except(IndexError):
                bid_cls = np.nan
            try:
                ask_lvl_list = list(ask_dict.keys())
                if self.min_lvl_cover > 0:
                    ask_cls = [x for x in ask_lvl_list if x >= ask_best + self.min_lvl_cover][0]
                else:
                    ask_cls = ask_lvl_list[-1]
            except(IndexError):
                ask_cls = np.nan
            out_list.extend([bid_cls, ask_cls])
        if self.cons_bid:
            bid_dict = LoB.level_bids(2, ven_list=self.lift_brk_list)
            ask_dict = LoB.level_asks(2, ven_list=self.lift_brk_list)
            try:
                bid_other = list(bid_dict.keys())[-1]
            except(IndexError):
                bid_other = np.nan
            try:
                ask_other = list(ask_dict.keys())[-1]
            except(IndexError):
                ask_other = np.nan
            out_list.extend([bid_other, ask_other])
        return out_list

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

    # def __lift_order_old(self, bid_best, ask_best, side):
    #     if abs(self.curr_position) < tol:
    #         # We are balanced
    #         self.timestamp_dict[side]['exe'] = None
    #     elif self.curr_position > 0:
    #         # We are long, need to sell
    #         self._position -= 1
    #         price = bid_best
    #         if side == 'bid':
    #             self.stats_dict['price_bid'].append(price)
    #         else:
    #             self.stats_dict['price_ask'].append(price)
    #         self.timestamp_dict[side]['exe'] = None
    #     else:
    #         # We are short, need to buy
    #         self._position += 1
    #         price = ask_best
    #         if side == 'bid':
    #             self.stats_dict['price_bid'].append(price)
    #         else:
    #             self.stats_dict['price_ask'].append(price)
    #         self.timestamp_dict[side]['exe'] = None
    #     self.stats_dict['position'].append(self.curr_position)
    #     self.stats_dict['price'].append(price)

    def __lift_order(self, timestamp, bid_best, ask_best, side, trd_mkt,
                     trd_side, trd_brk):
        if side == 'bid':
            if trd_side == -1:
                trd_price = trd_mkt
            else:
                trd_price = np.nan
            return self.__lift_order_bid(timestamp, bid_best, ask_best,
                                         trd_price, trd_brk)
        else:
            if trd_side == 1:
                trd_price = trd_mkt
            else:
                trd_price = np.nan
            return self.__lift_order_ask(timestamp, bid_best, ask_best,
                                         trd_price, trd_brk)

    def __lift_order_bid(self, timestamp, bid_best, ask_best, trd_price, trd_brk):
        side = 'bid'
        if abs(self.curr_position) < tol:
            vol = 0
            price = None
            # We are balanced
            self.timestamp_dict[side]['exe'] = None
        elif self.curr_position > 0:
            brk_fee = self.brk_fee(trd_brk)
            # We are long, need to sell
            vol = -1
            self._position += vol
            if self.best_bid_l is None:
                pass
            else:
                bid_best = max(bid_best, self.best_bid_l)
            if np.isnan(trd_price):
                price = bid_best - brk_fee
            else:
                price = max(bid_best, trd_price) - brk_fee
            self.stats_dict['price_bid'].append(price)
            self.stats_dict['position'].append(self.curr_position)
            self.stats_dict['price'].append(price)
            self.stats_dict['timestamp'].append(timestamp)
            self.timestamp_dict[side]['exe'] = None
        else:
            # We are short, need to buy
            vol = 0
            price = None
        return price, vol

    def __lift_order_ask(self, timestamp, bid_best, ask_best, trd_price, trd_brk):
        side = 'ask'
        if abs(self.curr_position) < tol:
            vol = 0
            price = None
            # We are balanced
            self.timestamp_dict[side]['exe'] = None
        elif self.curr_position > 0:
            # We are long, need to sell
            vol = 0
            price = None
        else:
            brk_fee = self.brk_fee(trd_brk)
            # We are short, need to buy
            vol = 1
            self._position += vol
            if self.best_ask_l is None:
                pass
            else:
                ask_best = min(ask_best, self.best_ask_l)
            if np.isnan(trd_price):
                price = ask_best + brk_fee
            else:
                price = min(ask_best, trd_price) + brk_fee
            self.stats_dict['price_ask'].append(price)
            self.stats_dict['position'].append(self.curr_position)
            self.stats_dict['price'].append(price)
            self.stats_dict['timestamp'].append(timestamp)
            self.timestamp_dict[side]['exe'] = None
        return price, vol

    def is_change_ord(self, price, timestamp, side):
        if side == 'bid':
            is_side = self.is_bid
        else:
            is_side = self.is_ask
        if self.timestamp_dict[side]['ord'] is None:
            time_bool = False
        elif (timestamp - self.timestamp_dict[side]['ord']) < self.time_del:
            time_bool = False
        else:
            time_bool = True
        if price is None:
            if is_side:
                is_inddel = True
            else:
                is_inddel = False
        else:
            if is_side:
                is_inddel = False
            else:
                is_inddel = True
        if is_inddel:
            return True
        else:
            if time_bool:
                return True
            else:
                return False

    def process(self, input_dict, method):
        # Input data
        timestamp = input_dict['timestamp']
        # if self.filter_aonnimp:
        #     LoB = input_dict['LoB'].filter_aonnimpl()
        # else:
        #     LoB = input_dict['LoB']
        bid_best, ask_best = [input_dict[k] for k in self.data_columns[:2]]
        mid_price = .5 * (bid_best + ask_best)
        trd_mkt = input_dict['trd_price']
        trd_side = input_dict['trd_side']
        trd_brk = input_dict['broker_id'] 
        # Process
        self.exe_prop_ords(timestamp)
        # bid_best = LoB.best_bid.price_val
        # ask_best = LoB.best_ask.price_val
        price_list, vol_list = self.exe_prop_trds(timestamp, bid_best, ask_best,
                                                  trd_mkt, trd_side, trd_brk)
        if np.isnan(trd_mkt):
            # Only process orders
            # bid, ask = self.__process_ord(LoB, method)
            bid, ask = self.__process_ord(timestamp, input_dict, method)
        else:
            bid, ask = self.__process_ord(timestamp, input_dict, method)
            price, vol = self.__process_trd(timestamp, trd_mkt, trd_side,
                                            trd_brk, mid_price)
            price_list.append(price)
            vol_list.append(vol)
        self.best_bid_l, self.best_ask_l = bid_best, ask_best
        return price_list, vol_list

    def __process_ord(self, timestamp, input_dict, method):
        # Bids
        # bid_best = LoB.best_bid.price_val
        # bid_lead = LoB.best_bid_ven(self.lead_brk).price_val
        # ask_best = LoB.best_ask.price_val
        # ask_lead = LoB.best_ask_ven(self.lead_brk).price_val
        if abs(self._position) > tol:
            return self.bid, self.ask
        bid_best, ask_best, bid_lead, ask_lead = [input_dict[k] for k in self.data_columns[:4]]
        if self.mkt_depth_check:
            bid_cls, ask_cls = [input_dict[k] for k in ['bid_cls', 'ask_cls']]
        else:
            bid_cls, ask_cls = np.nan, np.nan
        if self.cons_bid:
            bid_other, ask_other = [input_dict[k] for k in ['bid_other', 'ask_other']]
        else:
            bid_other, ask_other = np.nan, np.nan
        prop_bid = self.__process_bid(bid_best, bid_lead, bid_cls, bid_other, timestamp, method)
        prop_ask = self.__process_ask(ask_best, ask_lead, ask_cls, ask_other, timestamp, method)
        self.set_prop_ord(timestamp, prop_bid, 'bid')
        self.set_prop_ord(timestamp, prop_ask, 'ask')
        return self.bid, self.ask
        
    def __process_bid(self, bid_best, bid_lead, bid_cls, bid_other, timestamp,
                      method):
        if np.isnan(bid_best) or np.isnan(bid_lead):
            price = None
        else:
            price_margin = self.price_val(bid_best - bid_lead)
            # Market depth check
            if not self.mkt_depth_check:
                mkt_depth_check = True
            elif np.isnan(bid_cls):
                mkt_depth_check = False
            else:
                if self.price_val(bid_best - bid_cls) < self.param_dict['margin'] + self.param_dict['stop_loss']:
                    mkt_depth_check = True
                else:
                    mkt_depth_check = False
            # Conservative check
            if not self.cons_bid:
                cons_bid = True
            elif np.isnan(bid_other):
                cons_bid = False
            else:
                margin = self.param_dict['margin'] + self.param_dict['cons_level']
                if self.price_val(bid_best - bid_other) <= margin:
                    cons_bid = True
                else:
                    cons_bid = False
            if not mkt_depth_check or not cons_bid:
                return None
            if method == 'fix':
                if price_margin >= self.param_dict['margin']:
                    # Place bid
                    price = self.price_val(bid_best - self.param_dict['margin'])
                else:
                    price = None
                # if self.is_change_ord(price, timestamp, 'bid'):
                #     # We want to change order
                #     self.set_prop_ord(timestamp, price, 'bid')
                #     return self.bid
                # else:
                #     return price
            elif method == 'float':
                if price_margin <= self.param_dict['min_margin']:
                    price = None
                elif price_margin < self.param_dict['margin']:
                    price = self.price_val(bid_best - price_margin + self.tick_price)
                else:
                    price = self.price_val(bid_best - self.param_dict['margin'])
            else:
                raise ValueError('Unknown method: %s' % method)
        return price

    def __process_ask(self, ask_best, ask_lead, ask_cls, ask_other, timestamp,
                      method):
        if np.isnan(ask_best) or np.isnan(ask_lead):
            price = None
        else:
            price_margin = self.price_val(-(ask_best - ask_lead))
            # Market depth check
            if not self.mkt_depth_check:
                mkt_depth_check = True
            elif np.isnan(ask_cls):
                mkt_depth_check = False
            else:
                if self.price_val(-(ask_best - ask_cls)) < self.param_dict['margin'] + self.param_dict['stop_loss']:
                    mkt_depth_check = True
                else:
                    mkt_depth_check = False
            # Conservative check
            if not self.cons_bid:
                cons_bid = True
            elif np.isnan(ask_other):
                cons_bid = False
            else:
                margin = self.param_dict['margin'] + self.param_dict['cons_level']
                if self.price_val(-(ask_best - ask_other)) <= margin:
                    cons_bid = True
                else:
                    cons_bid = False
            if not mkt_depth_check or not cons_bid:
                return None
            if method == 'fix':
                if price_margin >= self.param_dict['margin']:
                    # Place ask
                    price = self.price_val(ask_best + self.param_dict['margin'])
                else:
                    price = None
                # if self.is_change_ord(price, timestamp, 'ask'):
                #     # We want to change order
                #     self.set_prop_ord(timestamp, price, 'ask')
                #     return self.ask
                # else:
                #     return price
            elif method == 'float':
                if price_margin <= self.param_dict['min_margin']:
                    price = None
                elif price_margin < self.param_dict['margin']:
                    price = self.price_val(ask_best + price_margin - self.tick_price)
                else:
                    price = self.price_val(ask_best + self.param_dict['margin'])
            else:
                raise ValueError('Unknown method: %s' % method)
        return price

    def __process_trd(self, timestamp, trd_mkt, trd_side, trd_brk, mid_price):
        if trd_side > 0:
            # From ask
            return self.__process_trd_ask(timestamp, trd_mkt, trd_brk, mid_price)
        else:
            # From bid
            return self.__process_trd_bid(timestamp, trd_mkt, trd_brk, mid_price)

    def __process_trd_bid(self, timestamp, trd_mkt, trd_brk, mid_price):
        if self.is_bid:
            # Check if price is bigger than our price
            if trd_mkt <= self.bid:
                brk_fee = self.brk_fee(trd_brk)
                # We bought from lead
                price = self.bid + brk_fee
                vol = 1
                self._position += vol
                self.stats_dict['position'].append(self.curr_position)
                self.stats_dict['price_bid'].append(price)
                self.stats_dict['price'].append(price)
                self.stats_dict['timestamp'].append(timestamp)
                # Set ask to None as it got lifted
                self.bid = None
                self.__del_prop_ord('bid')
                # Mark timestamp of trade
                self.timestamp_dict['bid']['exe'] = timestamp
            else:
                price = mid_price
                vol = 0
            return price, vol
        else:
            return mid_price, 0

    def __process_trd_ask(self, timestamp, trd_mkt, trd_brk, mid_price):
        if self.is_ask:
            # Check if price is bigger than our price
            if trd_mkt >= self.ask:
                brk_fee = self.brk_fee(trd_brk)
                # We sold from lead
                price = self.ask - brk_fee
                vol = -1
                self._position += vol
                self.stats_dict['position'].append(self.curr_position)
                self.stats_dict['price_ask'].append(price)
                self.stats_dict['price'].append(price)
                self.stats_dict['timestamp'].append(timestamp)
                # Set ask to None as it got lifted
                self.ask = None
                self.__del_prop_ord('ask')
                # Mark timestamp of trade
                self.timestamp_dict['ask']['exe'] = timestamp
            else:
                price = mid_price
                vol = 0
            return price, vol
        else:
            return mid_price, 0


def round_to_tick(number, tick_size):
    # Step 1: Divide by tick size
    number_in_ticks = number / tick_size
    
    # Step 2: Round to nearest whole number
    rounded_ticks = round(number_in_ticks)

    # Step 3: Multiply back by tick size
    result = rounded_ticks * tick_size

    # Step 4: Round the final result to avoid floating-point precision issues
    return round(result, len(str(tick_size).split('.')[1]))
