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

        # Load the saved model
        #self.production_model_long = xgb.XGBClassifier()
        #self.production_model_long.load_model('xgboost_model_dem2_dem1_jan_feb_long.json')

        #self.production_model_short = xgb.XGBClassifier()
        #self.production_model_short.load_model('xgboost_model_dem2_dem1_jan_feb_short.json')

        import datetime

        self.high_volumes =[datetime.date(2024, 1, 31),
                    datetime.date(2024, 2, 1),
                    datetime.date(2024, 2, 7),
                    datetime.date(2024, 2, 8),
                    datetime.date(2024, 2, 9),
                    datetime.date(2024, 2, 14),
                    datetime.date(2024, 2, 15),
                    datetime.date(2024, 2, 20),
                    datetime.date(2024, 2, 26),
                    datetime.date(2024, 2, 27),
                    datetime.date(2024, 2, 28),
                    datetime.date(2024, 2, 29),
                    datetime.date(2024, 3, 1),
                    datetime.date(2024, 3, 4),
                    datetime.date(2024, 3, 5),
                    datetime.date(2024, 3, 6),
                    datetime.date(2024, 3, 7),
                    datetime.date(2024, 3, 14),
                    datetime.date(2024, 3, 15),
                    datetime.date(2024, 3, 20),
                    datetime.date(2024, 3, 22),
                    datetime.date(2024, 3, 26),
                    datetime.date(2024, 3, 27),
                    datetime.date(2024, 3, 28),
                    datetime.date(2024, 4, 4),
                    datetime.date(2024, 4, 5),
                    datetime.date(2024, 4, 10),
                    datetime.date(2024, 4, 11),
                    datetime.date(2024, 4, 12),
                    datetime.date(2024, 4, 15),
                    datetime.date(2024, 4, 17),
                    datetime.date(2024, 4, 18),
                    datetime.date(2024, 4, 22),
                    datetime.date(2024, 4, 23),
                    datetime.date(2024, 4, 25),
                    datetime.date(2024, 4, 30),
                    datetime.date(2024, 5, 2),
                    datetime.date(2024, 5, 3),
                    datetime.date(2024, 5, 6),
                    datetime.date(2024, 5, 7),
                    datetime.date(2024, 5, 9),
                    datetime.date(2024, 5, 17),
                    datetime.date(2024, 5, 20),
                    datetime.date(2024, 5, 21),
                    datetime.date(2024, 5, 22),
                    datetime.date(2024, 5, 29),
                    datetime.date(2024, 5, 31),
                    datetime.date(2024, 6, 3),
                    datetime.date(2024, 6, 11),
                    datetime.date(2024, 6, 14),
                    datetime.date(2024, 6, 20),
                    datetime.date(2024, 6, 27),
                    datetime.date(2024, 7, 1),
                    datetime.date(2024, 7, 2),
                    datetime.date(2024, 7, 4),
                    datetime.date(2024, 7, 8),
                    datetime.date(2024, 7, 11),
                    datetime.date(2024, 7, 12),
                    datetime.date(2024, 7, 15),
                    datetime.date(2024, 7, 17),
                    datetime.date(2024, 7, 18),
                    datetime.date(2024, 7, 29),
                    datetime.date(2024, 7, 31),
                    datetime.date(2024, 8, 5),
                    datetime.date(2024, 8, 7),
                    datetime.date(2024, 8, 8),
                    datetime.date(2024, 8, 12),
                    datetime.date(2024, 8, 13),
                    datetime.date(2024, 8, 14),
                    datetime.date(2024, 8, 15),
                    datetime.date(2024, 8, 21),
                    datetime.date(2024, 8, 22),
                    datetime.date(2024, 8, 23),
                    datetime.date(2024, 8, 26),
                    datetime.date(2024, 8, 27),
                    datetime.date(2024, 8, 28),
                    datetime.date(2024, 8, 29),
                    datetime.date(2024, 8, 30),
                    datetime.date(2024, 9, 5),
                    datetime.date(2024, 9, 6),
                    datetime.date(2024, 9, 10),
                    datetime.date(2024, 9, 11),
                    datetime.date(2024, 9, 16),
                    datetime.date(2024, 9, 17),
                    datetime.date(2024, 9, 18),
                    datetime.date(2024, 9, 19),
                    datetime.date(2024, 9, 20),
                    datetime.date(2024, 9, 23),
                    datetime.date(2024, 9, 26),
                    datetime.date(2024, 9, 27),
                    datetime.date(2024, 10, 1),
                    datetime.date(2024, 10, 2),
                    datetime.date(2024, 10, 8),
                    datetime.date(2024, 10, 9),
                    datetime.date(2024, 10, 10),
                    datetime.date(2024, 10, 14),
                    datetime.date(2024, 10, 21),
                    datetime.date(2024, 10, 24),
                    datetime.date(2024, 10, 25),
                    datetime.date(2024, 10, 28),
                    datetime.date(2024, 10, 29),
                    datetime.date(2024, 10, 31),
                    datetime.date(2024, 11, 1),
                    datetime.date(2024, 11, 4),
                    datetime.date(2024, 11, 6)]

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
        self.mid_p = float(price_dict['mid_price'])
        self.bid_p = float(price_dict['bid_price'])
        self.ask_p = float(price_dict['ask_price'])
        self.trd_p = float(price_dict['trd_price'])
        self.trd_s =price_dict['trd_side']

        self.ba_spread= price_dict['ba_spread']

        self.diff_vwap_auction=price_dict['diff_vwap_auction']

        # Check if need to close position
        if self.timestamp_.hour==16 and self.timestamp_.minute==8 and self.timestamp_.day>=7 and self.timestamp_.month==3:#and self.tag=='lead'
            pass #print("Jozko")

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
        if  ba_spread <= self.param_dict['ba_max']: #and self.timestamp_.hour<16 and self.timestamp_.date() not in self.high_volumes  and self.coef2>=1  and self.coef2<=0.725
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
        if (ba_spread <= self.param_dict['ba_max'] or self.timestamp_.time() >= self.param_dict['t_end']):
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
        #self.stats_dict['coef2'].append(self.coef2)

        self.position_dict['open_price'] = price
        self.position_dict['volume'] = vol
        self.position_dict['open_time'] = self.timestamp_

        self._position += vol

    #function that calculates whether to buy, sell or do nothing acc. to lead market's trigger_df
    def calculate_open_slot(self):
        mid_price = (self.ask_p - self.bid_p) / 2.0

        action = self.no_action
        price = mid_price


        if self.timestamp_.time() <= self.param_dict['t_end'] and self.timestamp_.hour==12 and self.timestamp_.minute==47 and self.timestamp_.second<=20\
                :


            if self.diff_vwap_auction < -1*self.param_dict['long_threshold']: # and self.lag_price_predicted>self.lag_price_tick
                action = 1
                price = self.ask_p

            if self.diff_vwap_auction > self.param_dict['short_threshold']: # and self.lag_price_predicted>self.lag_price_tick
                action = -1
                price = self.bid_p


        return price, action

    def calculate_close_slot(self):

        #check whether to activate trail_stop
        open_price, open_time, *_ = self.position_dict.values()
        if self.curr_position > 0:
            # long
            if (self.bid_p+self.ask_p)/2 -open_price >=  self.param_dict['trail_stop']:
                self.trail_stop_flag = True
                if math.floor(((self.bid_p+self.ask_p)/2 -open_price) * 10) / 10 >self.max_mtm:
                    self.max_mtm=math.floor(((self.bid_p+self.ask_p)/2 -open_price) * 10)/10

        else:
        # short
            if open_price-(self.bid_p+self.ask_p)/2 >= self.param_dict['trail_stop']:
                self.trail_stop_flag = True
                if math.floor((open_price-(self.bid_p+self.ask_p)/2) * 10) / 10>self.max_mtm:
                    self.max_mtm=math.floor((open_price-(self.bid_p+self.ask_p)/2) * 10)/10


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
            if self.curr_position > 0:
                mtm=(self.bid_p+self.ask_p)/2 -open_price
                if self.bid_p < open_price + self.trail_stop_adjustment + self.param_dict['stop_loss']:
                    if self.ask_p < open_price + self.trail_stop_adjustment - self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.ask_p, open_price+ self.trail_stop_adjustment) / diff(self.bid_p, open_price+ self.trail_stop_adjustment)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS

                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                            if (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                else:
                    # profit
                    if self.ask_p < open_price+self.trail_stop_adjustment - self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                        if self.ask_p - self.bid_p <= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread):  # +seconds_since_burnout*(0.01/60):
                            close_behavior = AGGLOSS
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                            if (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
            else:
                mtm=open_price-(self.bid_p+self.ask_p)/2
                # short
                if self.ask_p > open_price-self.trail_stop_adjustment - self.param_dict['stop_loss']:
                    if self.bid_p > open_price-self.trail_stop_adjustment + self.param_dict['stop_profit']:
                        # active close
                        make_agg_ratio = diff(self.bid_p, open_price-self.trail_stop_adjustment) / diff(self.ask_p, open_price-self.trail_stop_adjustment)
                        if make_agg_ratio > self.param_dict['makeagg_ratio']:
                            close_behavior = AGGLOSS
                        else:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                            if (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                else:
                    # profit
                    if self.bid_p > open_price-self.trail_stop_adjustment + self.param_dict['stop_profit']:
                        close_behavior = MAKEBEST
                        if self.ask_p - self.bid_p <= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread):  # +seconds_since_burnout*(0.01/60):
                            close_behavior = AGGLOSS
                    else:
                        if burnout:
                            close_behavior = MAKEBEST
                            if self.ask_p-self.bid_p<= self.param_dict['aggloss_thres'] or (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS
                        else:
                            close_behavior = TAKEPROFIT
                            if (mtm>=self.param_dict['trail_stop'] and 0.07*mtm*2>self.ba_spread): #+seconds_since_burnout*(0.01/60):
                                close_behavior = AGGLOSS

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