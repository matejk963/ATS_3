# -*- coding: utf-8 -*-
"""
Created on Mon Nov 27 17:25:55 2023

@author: Marek
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import abc
from Math.accumfeatures import MSTD, MA, EMA
tol = 1e-6

from Utilities.strategy_class import StrategyClass, VolumeClass
# macros
TAKEPROFIT = 'make_takeprofit'
MAKEBEST = 'make_best'
AGGLOSS = 'agg_loss'


class StrategyLL(StrategyClass):
    bid = np.nan
    ask = np.nan
    def __init__(self, strategy, market, instrument, actions=[-1, 0, 1],
                 no_action=0, precision=3, is_overnight=True, ba_max=0.3, closing_mode='Simple'):
        super().__init__(strategy, market, instrument, actions, no_action,
                         precision, is_overnight)
        # Stats
        stats_list = ['timestamp', 'curr_time', 'position', 'price_level',
                      'price_bid', 'price_ask', 'status',
                      'mark_ts', 'mark_bid', 'mark_ask']
        self.stats_dict = {k: [] for k in stats_list}

        self.position_dict = self.init_position_dict
        self.ba_max=ba_max

        self.closing_mode=closing_mode
        assert self.closing_mode in ['Simple', 'Action_closing', 'Martinovo_zatvaranie'], 'Closing mode is undefined!'

    def get_constructor_params(self):
        return {
        'strategy': self.strategy,
        'market': self.market,
        'instrument': self.instrument,
        'actions': self._actions,
        'no_action': self._no_action,
        'precision': self._precision,
        'is_overnight': self._is_overnight

        }

    def load_params(self, param_dict, contr_vars):
        self.contr_vars = contr_vars
        self.state_vars = [v for v in self.param_list if v not in contr_vars]
        if 'ba_max' not in param_dict.keys():
            param_dict['ba_max'] = np.inf
        if 'br_fee' not in param_dict.keys():
            param_dict['br_fee'] = 0
        self.param_dict.update(param_dict)

    
    @classmethod
    def get_from_copy(cls, param_dict):
        return cls(**param_dict)

    @property
    def init_position_dict(self):
        return {
            'open_price': None,
            'open_time': None,
            'volume': 0,
            'close_behavior': None,
            'making_price': None
        }

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

    @property
    def mark_dict(self):
        return {t: [b, a] for t, b, a in zip(self.stats_dict['mark_ts'],
                                             self.stats_dict['mark_bid'],
                                             self.stats_dict['mark_ask'])}

    ################################################################################################################
    # equivalent of on orderbook update or on trade update in production
    def process(self, price_dict, volm_class, trade_type, trigger_df):
        # Process one row of data
        self.timestamp_ = price_dict['timestamp']
        self.mid_p = price_dict['mid_price']
        self.bid_p = price_dict['bid_price']
        self.ask_p = price_dict['ask_price']
        self.trd_p = price_dict['trd_price']
        self.trd_s = price_dict['trd_side']
        self.time_diff=price_dict['time_diff']
        self.MACD = price_dict['MACD']
        # Check if need to close position

        if self.timestamp_.hour>=10 and self.timestamp_.minute>=1:
            pass

        if self.curr_position == 0: #execute lead opening logic when not in position
            price, vol = self.act_lead_order(trigger_df)

        else:                       #execute lift closing logic when already in position
            price, vol = self.act_lift_order(trigger_df)

        return  price, vol


################################################################################################################
    #logic for opening the positions
    def act_lead_order(self, trigger_df):

        #check for bid ask spread being tight enough
        ba_spread = self.ask_p - self.bid_p
        if ba_spread <= self.param_dict['ba_max']:
            #calculate what action to take at what price according to the lead trigger df
            price, vol = self.calculate_open_slot(trigger_df)
            return self.create_slot(price, vol)
        else:
            return self.remove_slot()

################################################################################################################
    #logic for closing the positions
    def act_lift_order(self, trigger_df):

        #check for bid ask spread being tight enough
        ba_spread = self.ask_p - self.bid_p
        if ba_spread <= self.param_dict['ba_max'] or self.timestamp_.time() >= self.param_dict['t_end']:
            price, vol = self.calculate_close_slot(trigger_df)
            return self.create_slot(price, vol)
        else:
            return self.remove_slot()

################################################################################################################
    ### Auxilliary functions
    def create_slot(self, price, vol):
        if abs(vol)>0:
            self.log_trade(price, vol)
        return price, vol

    def remove_slot(self):
        mid_price=(self.ask_p - self.bid_p)/2.0
        return self.create_slot(mid_price, 0)

    def log_trade(self, price, vol):
        self.stats_dict['timestamp'].append(self.timestamp_)
        self.stats_dict['curr_time'].append(self.timestamp_)
        self.stats_dict['position'].append(vol)
        self.stats_dict['price_level'].append(price+self.param_dict['br_fee'] if vol > 0 else price-self.param_dict['br_fee'])
        self.stats_dict['price_bid'].append(self.bid_p)
        self.stats_dict['price_ask'].append(self.ask_p)
        self.stats_dict['status'].append('DONE')

        self.position_dict['open_price'] = price
        self.position_dict['volume'] = vol
        self.position_dict['open_time'] = self.timestamp_

        self._position += vol

    #function that calculates whether to buy, sell or do nothing acc. to lead market's trigger_df
    def calculate_open_slot(self, trigger_df):
        mid_price = (self.ask_p - self.bid_p) / 2.0

        action = self.no_action
        price = mid_price

        time_diff_timedelta = pd.to_timedelta(self.time_diff, unit='s')

        # Filter the DataFrame to include only rows before the specific datetime
        filtered_df = trigger_df[(trigger_df['trigger_datetime'] < self.timestamp_)&(trigger_df['trigger_datetime'] >= self.timestamp_-time_diff_timedelta)]

        # Select the last row after the specific datetime
        try:
            last_row_before_datetime = filtered_df.iloc[0]
            time_since_trigger=(self.timestamp_-last_row_before_datetime['trigger_datetime']).total_seconds()
            direction=last_row_before_datetime['direction']

            if time_since_trigger < self.time_diff:
                if direction == 1 and self.MACD and self.MACD>0:
                    action = 1
                    price = self.ask_p
                elif direction == -1 and self.MACD and self.MACD<0:
                    action = -1
                    price = self.bid_p
        except:
            pass

        return price, action


    def calculate_close_slot(self, trigger_df):

        self.calculate_close_behavior(trigger_df)
        self.calculate_close_price()

        if self.position_dict['making_price']:
            price, vol = self.position_dict['making_price'], self.close_action
            if vol > 0:
                if price >= self.ask_p or price >= self.trd_p:
                    self.position_dict = self.init_position_dict
                    return price, vol

            else:

                if price <= self.bid_p or price <= self.trd_p:
                    self.position_dict = self.init_position_dict
                    return price, vol
            return 0, 0

    def calculate_close_behavior(self, trigger_df):

        if self.timestamp_.time() >= self.param_dict['t_end']:
            close_behavior = AGGLOSS
            self.position_dict['close_behavior'] = close_behavior
            return close_behavior
        def simple_closing():
            open_price, open_time, *_ = self.position_dict.values()
            if self.curr_position > 0:
                #long
                if self.bid_p < open_price + self.param_dict['stop_loss']:
                    close_behavior = AGGLOSS

                else:
                    close_behavior = TAKEPROFIT

            else:
                #short
                if self.ask_p > open_price - self.param_dict['stop_loss']:
                    close_behavior = AGGLOSS

                else:
                    close_behavior = TAKEPROFIT

            return close_behavior

        ### Simple closing mechanism
        if self.closing_mode=='Simple':
            self.position_dict['close_behavior'] = simple_closing()
            return

        ### Action closing mechanism -> closing according to open triggers
        elif self.closing_mode=='Action_closing':
            _, open_action = self.calculate_open_slot(trigger_df)
            if open_action*self.curr_position<0:
                self.position_dict['close_behavior'] = AGGLOSS
            else:
                self.position_dict['close_behavior'] = simple_closing()
            return

        ### Martinovo_zatvaranie closing mechanism
        elif self.closing_mode=='Martinovo_zatvaranie':
            open_price, open_time, *_ = self.position_dict.values()
            diff = lambda x, y: y - x
            burnout = (self.timestamp_ - open_time).total_seconds() > self.param_dict['burnout_period'] * 60
            if self.curr_position > 0:
                if self.bid_p < open_price + self.param_dict['stop_loss']:
                    if self.ask_p < open_price - self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.ask_p, open_price) / diff(self.bid_p, open_price)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                        else:
                            close_behavior = TAKEPROFIT
                else:
                    # profit
                    if self.ask_p < open_price - self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                        else:
                            close_behavior = TAKEPROFIT
            else:
                # short
                if self.ask_p > open_price - self.param_dict['stop_loss']:
                    if self.bid_p > open_price + self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.bid_p, open_price) / diff(self.ask_p, open_price)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                        else:
                            close_behavior = TAKEPROFIT
                else:
                    # profit
                    if self.bid_p > open_price + self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                        else:
                            close_behavior = TAKEPROFIT

            self.position_dict['close_behavior'] = close_behavior
            return


    def calculate_close_price(self):

        price = np.nan
        close_behavior = self.position_dict['close_behavior']
        open_price = self.position_dict['open_price']
        volume = self.position_dict['volume']
        long_tp = open_price + self.param_dict['take_profit']
        short_tp = open_price - self.param_dict['take_profit']

        if close_behavior == AGGLOSS:
            if volume > 0:
                price = self.bid_p
            else:
                price = self.ask_p

        elif close_behavior == MAKEBEST:
            if volume > 0:
                price = self.ask_p-0.01
                price = min(price, long_tp)
            else:
                price = self.bid_p+0.01
                price = max(price, short_tp)

        elif close_behavior == TAKEPROFIT:
            if volume > 0:
                price = long_tp
            else:
                price = short_tp
        else:
            return -1
        self.position_dict['making_price'] =  price
        return 0