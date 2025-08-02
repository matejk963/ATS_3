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
import xgboost as xgb
import math


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
                      'mark_ts', 'mark_bid', 'mark_ask', 'coef2']
        self.stats_dict = {k: [] for k in stats_list}

        self.position_dict = self.init_position_dict
        self.ba_max=ba_max

        self.trail_stop_flag = False

        self.closing_mode=closing_mode
        assert self.closing_mode in ['Simple', 'Action_closing', 'Martinovo_zatvaranie', 'Martinovo_zatvaranie_with_action_closing'], 'Closing mode is undefined!'

        # # Load the saved model
        # self.production_model_long = xgb.XGBClassifier()
        # self.production_model_long.load_model('xgboost_model_dem2_dem1_jan_feb_long.json')
        #
        # self.production_model_short = xgb.XGBClassifier()
        # self.production_model_short.load_model('xgboost_model_dem2_dem1_jan_feb_short.json')

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

    def add_fees(self, price, vol):
        if vol>0:
            return price + self.param_dict['br_fee']
        elif vol<0:
            return price - self.param_dict['br_fee']
        else:
            return price

    
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
    def process(self, price_dict, volm_class, trade_type):
        # Process one row of data
        self.timestamp_ = price_dict['timestamp']
        self.mid_p = price_dict['mid_price']
        self.bid_p = price_dict['bid_price']
        self.ask_p = price_dict['ask_price']
        self.trd_p = price_dict['trd_price']
        self.trd_s = price_dict['trd_side']
        self.time_diff=price_dict['time_diff']
        self.tag=price_dict['tag']


        self.MACD = price_dict['MACD']
        #self.trigger_datetime = price_dict['trigger_datetime']
        #self.trigger_action = price_dict['trigger_action']
        self.lag_price_predicted_datetime = price_dict['lag_price_predicted_datetime']
        self.lag_price_predicted = price_dict['lag_price_predicted']
        self.lag_price_tick = price_dict['lag_price_tick']
        self.lead_price_tick = price_dict['lead_price_tick']

        self.coef1 = price_dict['coef1']
        self.coef2 = price_dict['coef2']



        # Check if need to close position

        if self.timestamp_.hour>=12 and self.timestamp_.minute>=37 and self.timestamp_.day>=17 and self.timestamp_.month>=12 and self.tag=='lag':#and self.tag=='lead'
            pass

        if self.curr_position == 0: #execute lead opening logic when not in position
            price, vol = self.act_lead_order()

        else:                       #execute lift closing logic when already in position
            price, vol = self.act_lift_order()

        price = self.add_fees(price, vol) #add the fees for the opening or closing price

        return  price, vol


################################################################################################################
    #logic for opening the positions
    def act_lead_order(self):

        #make sure the trail_stop is off when not in position
        self.trail_stop_flag=False
        self.max_mtm=0

        #check for bid ask spread being tight enough
        ba_spread = self.ask_p - self.bid_p
        if  self.tag=='lead' and ba_spread <= self.param_dict['ba_max'] and not (self.timestamp_.hour==16 and self.timestamp_.minute>30):  #and self.timestamp_.hour<16
            #calculate what action to take at what price according to the lead trigger df
            price, vol = self.calculate_open_slot()
            return self.create_slot(price, vol)
        else:
            return self.remove_slot()

################################################################################################################
    #logic for closing the positions
    def act_lift_order(self):

        #check for bid ask spread being tight enough
        ba_spread = self.ask_p - self.bid_p
        if self.tag=='lag' and (ba_spread <= self.param_dict['ba_max'] or self.timestamp_.time() >= self.param_dict['t_end']):
            price, vol = self.calculate_close_slot()
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
        self.stats_dict['coef2'].append(self.coef2)

        self.position_dict['open_price'] = price
        self.position_dict['volume'] = vol
        self.position_dict['open_time'] = self.timestamp_

        self._position += vol

    #function that calculates whether to buy, sell or do nothing acc. to lead market's trigger_df
    def calculate_open_slot(self):
        mid_price = (self.ask_p - self.bid_p) / 2.0

        action = self.no_action
        price = mid_price

        #time_since_action_trigger=(self.timestamp_-self.trigger_datetime).total_seconds()
        time_since_predicted_price=(self.timestamp_-self.lag_price_predicted_datetime).total_seconds()
        #direction=self.trigger_action


        if self.timestamp_.time() <= self.param_dict['t_end']:

            if not self.param_dict['combined_mode']:
                if self.MACD > self.param_dict['MACD_long_threshold']  and (self.lag_price_predicted - self.ask_p) > self.param_dict['price_diff_long_threshold'] and self.lag_price_predicted>self.lag_price_tick: # and self.lag_price_predicted>self.lag_price_tick
                    action = 1
                    price = self.ask_p
                elif self.MACD <= self.param_dict['MACD_short_threshold'] and (self.lag_price_predicted - self.bid_p) < self.param_dict['price_diff_short_threshold'] and self.lag_price_predicted<self.lag_price_tick: # and self.lag_price_predicted<self.lag_price_tick
                    action = -1
                    price = self.bid_p

            else:
                if self.MACD and self.lag_price_predicted and (self.MACD + (
                        self.lag_price_predicted - self.ask_p)) >self.param_dict['combined_long_threshold']:# and self.lag_price_predicted>self.lag_price_tick:  # not production_data_long.isnull().values.any() and production_prediction_long>self.param_dict['long_threshold']:
                    action = 1
                    price = self.ask_p
                elif self.MACD and self.lag_price_predicted and (-self.MACD - (
                        self.lag_price_predicted - self.bid_p)) > self.param_dict['combined_short_threshold']:# and self.lag_price_predicted<self.lag_price_tick:  # not production_data_short.isnull().values.any() and production_prediction_short>self.param_dict['short_threshold']:
                    action = -1
                    price = self.bid_p

            # #XGB model logic
            # # Example production data
            # production_data_long = pd.DataFrame({
            #     'MACD': [self.MACD],
            #     'price_diff': [(self.lag_price_predicted-self.ask_p)],
            #     'trigger_action': [self.trigger_action]
            # })
            #
            # # Example production data
            # production_data_short = pd.DataFrame({
            #     'MACD': [self.MACD],
            #     'price_diff': [(self.lag_price_predicted-self.bid_p)],
            #     'trigger_action': [self.trigger_action]
            # })
            #
            # # Make predictions
            # production_prediction_long = self.production_model_long.predict_proba(production_data_long)[:, 1][0]
            # production_prediction_short = self.production_model_short.predict_proba(production_data_short)[:, 1][0]
            #
            # if production_prediction_long>0.573:
            #     action = 1
            #     price = self.ask_p
            # elif  None and production_prediction_short>0.419:
            #     action = -1
            #     price = self.bid_p

            # deq1_dem1 good model:
            # if self.MACD > 0.084 and (self.lag_price_predicted - self.ask_p) > 0.04:
            #     action = 1
            #     price = self.ask_p
            # elif self.MACD <= -0.0839 and (self.lag_price_predicted - self.bid_p) < -0.05:
            #     action = -1
            #     price = self.bid_p




        pass

        return price, action

    def calculate_close_slot(self):

        #check whether to activate trail_stop
        open_price, open_time, *_ = self.position_dict.values()
        if self.curr_position > 0:
            # long
            if (self.bid_p + self.ask_p) / 2 - open_price >= self.param_dict['trail_stop']:
                self.trail_stop_flag = True
                if math.floor(((self.bid_p + self.ask_p) / 2 - open_price) * 10) / 10 > self.max_mtm:
                    self.max_mtm = math.floor(((self.bid_p + self.ask_p) / 2 - open_price) * 10)/10

        else:
            # short
            if open_price - (self.bid_p + self.ask_p) / 2 >= self.param_dict['trail_stop']:
                self.trail_stop_flag = True
                if math.floor((open_price - (self.bid_p + self.ask_p) / 2) * 10) / 10 > self.max_mtm:
                    self.max_mtm = math.floor((open_price - (self.bid_p + self.ask_p) / 2) * 10)/10

        self.calculate_close_behavior()
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

    def calculate_close_behavior(self):

        self.trail_stop_adjustment=int(self.trail_stop_flag)*self.max_mtm

        if self.timestamp_.time() >= self.param_dict['t_end']:
            close_behavior = AGGLOSS
            self.position_dict['close_behavior'] = close_behavior
            return close_behavior
        def simple_closing():
            open_price, open_time, *_ = self.position_dict.values()

            if self.curr_position > 0:
                #long
                if self.bid_p < open_price + self.param_dict['stop_loss']+self.trail_stop_adjustment:
                    close_behavior = AGGLOSS

                else:
                    close_behavior = TAKEPROFIT

            else:
                #short
                if self.ask_p > open_price - self.param_dict['stop_loss']-self.trail_stop_adjustment:
                    close_behavior = AGGLOSS

                else:
                    close_behavior = TAKEPROFIT

            return close_behavior


        def action_closing():
            _, open_action = self.calculate_open_slot()
            if open_action*self.curr_position<0:
                close_behavior = AGGLOSS
            else:
                close_behavior = simple_closing()

            return close_behavior

        def martinovo_zatvaranie():
            open_price, open_time, *_ = self.position_dict.values()
            diff = lambda x, y: y - x
            burnout = (self.timestamp_ - open_time).total_seconds() > self.param_dict['burnout_period'] * 60
            seconds_since_burnout=(self.timestamp_ - open_time).total_seconds()-self.param_dict['burnout_period'] * 60
            if self.curr_position > 0:
                if self.bid_p < open_price + self.trail_stop_adjustment + self.param_dict['stop_loss']:
                    if self.ask_p < open_price + self.trail_stop_adjustment - self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.ask_p, open_price+ self.trail_stop_adjustment) / diff(self.bid_p, open_price+ self.trail_stop_adjustment)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<=0.04: #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                else:
                    # profit
                    if self.ask_p < open_price+self.trail_stop_adjustment - self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= 0.04: #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
            else:
                # short
                if self.ask_p > open_price-self.trail_stop_adjustment - self.param_dict['stop_loss']:
                    if self.bid_p > open_price-self.trail_stop_adjustment + self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.bid_p, open_price-self.trail_stop_adjustment) / diff(self.ask_p, open_price-self.trail_stop_adjustment)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<=0.04: #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                else:
                    # profit
                    if self.bid_p > open_price-self.trail_stop_adjustment + self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<=0.04: #+seconds_since_burnout*(0.01/60):
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
            _, open_action = self.calculate_open_slot()
            self.position_dict['close_behavior'] = action_closing()
            return

        ### Martinovo_zatvaranie closing mechanism
        elif self.closing_mode=='Martinovo_zatvaranie':
            self.position_dict['close_behavior'] = martinovo_zatvaranie()
            return



        elif self.closing_mode=='Martinovo_zatvaranie_with_action_closing':
            action_closing=action_closing()
            if action_closing!=AGGLOSS:
                self.position_dict['close_behavior'] = martinovo_zatvaranie()
            else:
                self.position_dict['close_behavior'] = action_closing
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