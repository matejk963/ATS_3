# -*- coding: utf-8 -*-
"""
Created on Mon Nov 27 17:25:55 2023

@author: Marek
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
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
    _range_bool = False
    
    def __init__(self, strategy, market, instrument, actions, no_action,
                 precision, is_overnight):
        self.strategy = strategy
        self.market = market
        self.instrument = instrument
        self._actions = actions
        self._no_action = no_action
        self._precision = precision
        self._is_overnight = is_overnight
        self._range_bool = False

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
    def range_bool(self):
        return self._range_bool
    
    def update_range_bool(self, new_range_bool):
        self._range_bool = new_range_bool

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
                      'mark_ts', 'mark_bid', 'mark_ask', 'range_bool',
                      'vol_state']
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
        # Get max position of strategy
        vol_increments = [(volm_class.state_max//3)*i for i in range(1,4)]
        
        if abs(self.curr_position) >0:
            pass
        
        # Process data
        timestamp_ = price_dict['timestamp']
        mid_p = price_dict['mid_price']
        bid_p = price_dict['bid_price']
        ask_p = price_dict['ask_price']
        trd_p = price_dict['trd_price']
        trd_s = price_dict['trd_side']
        if 'lt_date' in list(price_dict):
            lt_date = price_dict['lt_date']
        else:
            lt_date = np.nan
        
        if timestamp_ >= dt.datetime(2024,2,15):
            pass
        # Check if need to close position
        act, stop_bool = self.check_state_new(timestamp_, bid_p, ask_p, mid_p,
                                          trade_type, act_input, lt_date, vol_increments)
        if stop_bool is not True:
            # Process output from prediction algorithm
            act, p = self.process_action(act_input, bid_p, ask_p, trd_p, trd_s,
                                         method, volm_class, timestamp_, vol_increments)

        else:
            p = self.calc_close_price(act, bid_p, ask_p, trade_type)
                    # Check for volume constraints
        act = self.check_pending_position(timestamp_, act, volm_class, bid_p, ask_p, act_input)
        price, vol = self.take_position(act, p, timestamp_, bid_p, ask_p, mid_p,
                                        volm_class, trade_type, stop_bool)
        
        if volm_class.state != self.curr_position:
            pass
        
        if volm_class.reset_bool:
            volm_class.reset()
        return price, vol

    def process_action(self, act_input, bid_mkt, ask_mkt, trd_mkt, trd_sid,
                       method,volm_class, timestamp_, vol_increments):

        

        # Process action input
        if method == 'position_mtm':

            max_bid, min_ask = self.__process_position_mtm(act_input, vol_increments,
                                                           bid_mkt, ask_mkt)


        else:
            raise ValueError('Unknown method %s' % method)
        self.bid = max_bid
        self.ask = min_ask
        action = self.no_action
        price = np.nan
        
        
        # Check for price in trading range
        # Price in range
        if (act_input[0] < ask_mkt) and (act_input[-1] > bid_mkt):
            self.update_range_bool(True)
            action, price = self.__basic_process_action(action, price,
                                                        max_bid, min_ask,
                                                        bid_mkt, ask_mkt,
                                                        trd_mkt, trd_sid)
            return action, price
            
        # Price out of range
        else:
            self.update_range_bool(False)
            
            return action ,price
            
            
        return action, price
    
    def __basic_process_action(self, action, price,
                               bid, ask,
                               bid_mkt, ask_mkt,
                               trd_mkt, trd_sid):
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
        
    
    def __process_position_mtm(self, act_input, vol_increments, bid_mkt, ask_mkt):
        #scale the bids and asks based on current position
        
        def filter_list_based_on_value(var, list1, list2):
            # Ensure list2 has an odd number of elements
            if len(list2) % 2 == 0:
                raise ValueError("list2 should have an odd number of elements.")
            
            # Calculate the middle index of list2
            mid_idx = len(list2) // 2
            
            # Iterate over list1 and compare with var
            for i, threshold in enumerate(list1):
                if var < threshold:
                    # If it's the first element, remove the middle element
                    if i == 0:
                        return np.concatenate((list2[:mid_idx], list2[mid_idx+1:]))
                    # If it's the second element, remove the middle element and its adjacent elements
                    elif i == 1:
                        return np.concatenate((list2[:mid_idx-1], list2[mid_idx+2:]))
                    # Continue similarly for other elements in list1
                    else:
                        return np.concatenate((list2[:mid_idx-i], list2[mid_idx+i+1:]))
            
            # If var is greater than or equal to all elements in list1, return list2 unchanged
            return list2
        def select_symmetric_elements(filtered_list, var1, var2):
            # Calculate the mean of the filtered list
            mean_value = np.mean(filtered_list)
            
            # Determine the higher and lower of the two variables
            higher_value = max(var1, var2)
            lower_value = min(var1, var2)
            
            # Symmetric selection
            for i in range(len(filtered_list) // 2):
                symmetric_pair = (filtered_list[i], filtered_list[-(i+1)])
                
                # Check conditions based on the criteria
                if higher_value < mean_value:
                    if symmetric_pair[0] > higher_value:
                        return symmetric_pair
                elif lower_value > mean_value:
                    if symmetric_pair[1] < lower_value:
                        return symmetric_pair
        
            # If no pairs are selected, return the closest values to the mean from both sides
            closest_left = min(filtered_list[:len(filtered_list) // 2 + 1], key=lambda x: abs(x - mean_value))
            closest_left_index = np.where(filtered_list == closest_left)[0][0]
        
            # Ensure symmetric selection
            closest_right = filtered_list[-(closest_left_index + 1)]
            
            return tuple(np.sort([closest_left, closest_right]))
            
            
        
        if abs(self.curr_position)< vol_increments[2]:
            filtered_list = filter_list_based_on_value(abs(self.curr_position),
                                                       vol_increments,
                                                       act_input)
            selected_pair = select_symmetric_elements(filtered_list,
                                                      bid_mkt, ask_mkt)
            return selected_pair[0], selected_pair[1]
        else:
            return -np.inf, np.inf
        
       
        
        # # If no position/first increment not done return first order as threshold
        # if abs(self.curr_position) < vol_increments[0]:
        #     return act_input[3], act_input[5]            
        # # If first increment done/second not
        # # Return as threshold mid 1st/2nd order 
        # elif abs(self.curr_position) < vol_increments[1]:
        #     return act_input[1].mean(), act_input[5].mean()
        # # If the last increment is filling insert second order
        # elif abs(self.curr_position) < vol_increments[2]:
        #     return act_input[:1].mean(), act_input[-2:].mean()
        # else:
        #     return -np.inf, np.inf
    
    
    # Custom check_state for stopping out of position after critical bound
    def check_state_new(self, timestamp, bid_price, ask_price, mid_price,
                    trade_type, act_input, lt_date, vol_increments):
        # Default action
        action = self.no_action
        # Default bool
        stop_bool = False
        
        
        
        
        
        # Check if stop loss / take profit or close position overnight
        if self._is_overnight:
            ts = timestamp
            if ts >= lt_date:
                stop_bool = True
                if abs(self.curr_position) < tol:                    
                    return action, stop_bool
                else:
                    # No overnight position
                    action = self.close_action
                    return action, stop_bool
            else:
                if abs(self.curr_position) < tol:                    
                    return action, stop_bool
                
        elif not self._is_overnight:
            ts = timestamp.time()
            if ts >= self.param_dict['t_end']:
                stop_bool = True
                if abs(self.curr_position) < tol:                    
                    return action, stop_bool
                else:
                    # No overnight position
                    action = self.close_action
                    return action, stop_bool
            else:
                if abs(self.curr_position) < tol:                    
                    return action, stop_bool
        
        else:
            stop_bool = False        
        
        # Check for price in trading range
        # Price out of range
        if (act_input[0] > ask_price) or (act_input[-1] < bid_price):
            action = self.close_action
            stop_bool = True
            self.update_range_bool(False)
        else:     
            action, stop_bool = self.__process_scaling_out(action, stop_bool,
                                                           bid_price, ask_price,
                                                           act_input, vol_increments)
            
        return action, stop_bool
    
    # Logic for scaling out of position
    def __process_scaling_out(self, action, stop_bool,
                              bid_price, ask_price, act_input, vol_increments):
        """
            Basic logic is to cut the position based on the price
        location relativ to bands
        0th position between first bands/ no scaling out
        1st position between first and frist 'n half bands
        2nd position between  first 'n half and second bands
        3rd position between second and third bands
        
            After 3rd band is stop/ no position
        """
        # 1st position
        # Stop when ema is reached
        if abs(self.curr_position) <=vol_increments[0]:
            # Long position
            if np.sign(self.curr_position)>0:
                # Price crosses mean/ema:
                if bid_price > np.mean(act_input[4]):
                    action = self.close_action
                    stop_bool = True
            else:
                # Price crosses mean/ema:
                if ask_price < np.mean(act_input[4]):
                    action = self.close_action
                    stop_bool = True
        # 2nd position
        # Stop when ema is reached
        elif abs(self.curr_position) <=vol_increments[1]:
            # Long position
            if np.sign(self.curr_position)>0:
                # Price crosses mean/ema:
                if bid_price > act_input[3]:
                    action = self.close_action
                    stop_bool = True
            else:
                # Price crosses mean/ema:
                if ask_price < act_input[5]:
                    action = self.close_action
                    stop_bool = True
        # 3rd position
        # Stop when ema is reached
        elif abs(self.curr_position) <=vol_increments[2]:
            # Long position
            if np.sign(self.curr_position)>0:
                # Price crosses mean/ema:
                if bid_price > act_input[2]:
                    action = self.close_action
                    stop_bool = True
            else:
                # Price crosses mean/ema:
                if ask_price < act_input[6]:
                    action = self.close_action
                    stop_bool = True
        else:
            raise Exception("Position above max_clip")
            
        return action ,stop_bool                
                    



    def check_pending_position(self, timestamp, action, volm_class,
                               bid_price, ask_price, act_input):
        # Check if we can add proposed position
        if timestamp == dt.datetime(2024,2,16,10,27,54):
            if action !=0:
                pass
        
        if abs(self.curr_position) < tol:
            vol = volm_class.push(action)
            # Do nothing
            return action
        # Situation when not in full position but within 2nd-3rd bound
        elif  abs(self.curr_position) < 3:

            if ((act_input[-2]<=ask_price) or 
                (act_input[1]>=bid_price)):
                last_true_index = next((i for i in reversed(range(len(self.stats_dict['range_bool'])))
                                        if self.stats_dict['range_bool'][i]), None)
                last_beyond_range_timestamp = self.stats_dict['timestamp'][last_true_index]
                diff_from_beyond_range = (timestamp - last_beyond_range_timestamp).total_seconds()
                if diff_from_beyond_range <= 3600:
                    
                    action = self.no_action
                    return action
        vol = volm_class.push(action)
        if abs(vol) < tol:
            # Do not increase position
            action = self.no_action
            return action
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
                dummy = volm_class.push(-vol)
                vol = -vol
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
                self.stats_dict['range_bool'].append(self.range_bool)
                self.stats_dict['vol_state'].append(volm_class.state)
            # If MM volume has not been traded
            if status in ['BID', 'ASK']:
                vol = 0
            self._position = volm_class.state
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
    def state_max(self):
        return self._state_max

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
