import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from Strategies.Base.strategy_base import StrategyBase
from Strategies.Base.feature_interface import FeatureInterface
from Utilities.DataValidator import check_numeric

tol = 1e-6

# macros
TAKEPROFIT = 'TAKEPROFIT'
MAKEBEST = 'MAKEBEST'
AGGLOSS = 'AGGLOSS'
AGGPROFIT = 'AGGPROFIT'

class ModularStrategy(StrategyBase):
    def __init__(self, features_pool, strategy_data_columns, param_dict, max_position=1, actions=[-1, 0, 1],
                no_action=0, lead_closing=False, is_overnight=False):
        super().__init__(features_pool, strategy_data_columns, param_dict, actions, no_action, is_overnight)
        # Stats
        stats_list = ['timestamp', 'position', 'action', 'price_level',
                    'open_price']
        self.stats_dict = {k: [] for k in stats_list}
        self.monitoring_dict = {
            'timestamp': [],
            'making_price': []
        }
        self.lead_closing = lead_closing
        self.max_position = max_position
        self.hard_stoploss_flag = False
        self.position_dict = self.init_position_dict
        self.daily_profit = []
    
    @classmethod
    def get_from_copy(cls, param_dict):
        return cls(**param_dict)
    
    @property
    def init_position_dict(self):
        return {
            'open_price': None,
            'trailing_price': None,
            'open_time': None,
            'volume': 0,
            'takeprofit': None
        }
    
    @property
    def close_action(self):
        open_position = self.get_open_position()
        if open_position > 0:
            # Close by selling
            action = 'long'
        elif open_position < 0:
            # Close by buying
            action = 'short'
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

    # def load_params(self, param_dict, contr_vars):
    #     self.contr_vars = contr_vars
    #     self.state_vars = [v for v in self.param_list if v not in contr_vars]
    #     if 'ba_max' not in param_dict.keys():
    #         param_dict['ba_max'] = np.inf
    #     if 'br_fee' not in param_dict.keys():
    #         param_dict['br_fee'] = 0
    #     self.update_params(param_dict)

    @property
    def mark_dict(self):
        return {t: [b, a] for t, b, a in zip(self.stats_dict['mark_ts'],
                                            self.stats_dict['mark_bid'],
                                            self.stats_dict['mark_ask'])}
    

    # ====== Production syntax similar function mappings ======
    def remove_slot(self):
        # This method do nothing, use it as good practice for production
        return 0, 0
    
    def get_open_position(self):
        return self.position_dict['volume']
    
    # =========================================================

    def set_monitoring(self, data):
        self.monitoring_dict['making_price'].append(self.position_dict['making_price'])
        self.monitoring_dict['timestamp'].append(data['timestamp'])

    def change_date_profit(self, data):
        date = data['timestamp'].date()
        if len(self.daily_profit) < 1 or self.daily_profit[-1]['date'] < date:
            self.daily_profit.append({'date': date, 'pnl': 0.0})
            return False
        elif self.param_dict.get('hard_tp', None):
            hard_tp =  self.daily_profit[-1]['pnl'] >= self.param_dict['hard_tp']
            hard_sl = self.daily_profit[-1]['pnl'] <= -self.param_dict['hard_sl']

            return (hard_tp or hard_sl)
        else:
            return self.daily_profit[-1]['pnl'] <= -self.param_dict['hard_sl']
            
    def process(self, data):
        hard_sl = self.change_date_profit(data)

        if isinstance(data, dict):
            data_dict = data
        elif isinstance(data, np.ndarray):
            data_dict = {k: v for k, v in zip(self.columns, data)}
        else:
            raise ValueError(f"strategy process incorect data type ({type(data)})")
    
        if hard_sl:
            return self.remove_slot()

        is_trade = not np.isnan(data_dict['trd_price']) #TODO: in the future can be some other flag

        if is_trade:
            return self.on_public_trade_update(data_dict)
        else:
            return self.on_order_book_update(data_dict)
        
    def on_public_trade_update(self, data_dict):
        result = self.lead_act(data_dict)
        if result[0] == 0:
            return self.lift_act(data_dict)
        else:
            return result
    
    def on_order_book_update(self, data_dict):
        return self.lift_act(data_dict)

    def calculate_action(self, data_dict, long, short, open_position):
        a_price, b_price = data_dict['a_price'], data_dict['b_price']
        volume = 0
        if long and short:
            if open_position >= 0:
                volume = round(self.max_position - open_position)
            else:
                volume = -round(self.max_position + open_position)
        elif long:
            if open_position < 0:
                volume = abs(open_position)
            else:
                volume = round(self.max_position - open_position)
        elif short:
            if open_position > 0:
                volume = -open_position
            else:
                volume = -round(self.max_position + open_position)
        
        price = a_price if volume > 0 else b_price
        return price, volume

    def lead_act(self, data_dict):
        if self.hard_stoploss_flag:
            return self.remove_slot()
        if not self.lead_closing and self.get_open_position() != 0:
            return self.remove_slot()
        if not self._is_overnight:
            ts = data_dict['timestamp'].time()
            if ts >= self.param_dict['t_end']:
                return self.remove_slot()

        local_buy = data_dict['b_price']
        local_sell = data_dict['a_price']

        if not local_buy or not local_sell:
            return self.remove_slot()
        
        open_position = self.get_open_position()
        trade_price = data_dict['trd_price']

        long_bool = all([f.condition_long(data_dict) for f in self.features])
        short_bool = all([f.condition_short(data_dict) for f in self.features])

        price, volume = self.calculate_action(data_dict, long_bool, short_bool, open_position)

        if round(volume) != 0:
            return self.create_slot(
                volume, price, data_dict['timestamp'],
                local_buy, local_sell, trade_price, data_dict)
        else:
            # No action
            return self.remove_slot()

    def lift_act(self, data_dict):
        # Check if stop loss / take profit or close position overnight
        close_behavior = None
        open_position = self.get_open_position()
        open_time = self.position_dict['open_time']

        if abs(open_position) < tol:
            return self.remove_slot()
        self.update_open_price(data_dict)
        open_price = self.position_dict['trailing_price']

        if not self._is_overnight:
            ts = data_dict['timestamp'].time()
            if ts >= self.param_dict['t_end']:
                close_behavior = AGGLOSS
                return self.act_close(data_dict, self.close_action, close_behavior, open_price)
            

        burnout = (data_dict['timestamp']-open_time).total_seconds() > self.param_dict['burnout_period']*60
        
        close_behavior, direction, _ = self.calculate_close_behavior(data_dict['b_price'],
                                                        data_dict['a_price'],
                                                        data_dict['trd_price'],
                                                        open_position,
                                                        open_price,
                                                        burnout)

        return self.act_close(data_dict, direction, close_behavior, open_price)
    
    def act_close(self, data_dict, direction, close_behavior, open_price):
        tp = round(self.position_dict['takeprofit'], 2)
        b_price, a_price = data_dict['b_price'], data_dict['a_price']
        open_position = self.get_open_position()

        if close_behavior == "AGGLOSS":
            price = b_price if direction == 'long' else a_price
        elif close_behavior == "AGGPROFIT":
            price = b_price if direction == 'long' else a_price
        elif close_behavior == "MAKEBEST":
            price = a_price if direction == 'long' else b_price
            price = min(price, tp) if direction == 'long' else max(price, tp)
        elif close_behavior == "TAKEPROFIT":
            if direction == 'long':
                if a_price > tp:
                    price = tp
                elif a_price > round(tp - 0.05, 2):
                    price = round(a_price-0.01, 2)
                else:
                    price = tp
            else:
                if b_price < tp:
                    price = tp
                elif b_price < round(tp + 0.05, 2):
                    price = round(b_price + 0.01, 2)
                else:
                    price = tp
        else:
            raise ValueError("close_behavior has invalid value:", close_behavior)

        return self.create_slot(open_position*-1, round(price, 2), data_dict['timestamp'],
                                b_price, a_price, data_dict['trd_price'],
                                data_dict)

    def calculate_close_behavior(self, bid_price, ask_price, trd_price, open_position, open_price, burnout):
        diff = lambda x,y: round(y-x, 2)
        mode = self.param_dict['closing_mode']
        trade = check_numeric(trd_price)

        if open_position > 0:
            direction = 'long'
            if bid_price < round(open_price - self.param_dict['stop_loss'], 2):
                if ask_price < round(open_price-self.param_dict['stop_profit'], 2):  
                    # active close

                    make_agg_ratio = diff(ask_price, open_price)/diff(bid_price, open_price)
                    if self.param_dict.get('close_trade_info', None) and bool(trade) and (trade <= bid_price):
                        branch_flag = 30
                        close_behavior = AGGLOSS
                    elif make_agg_ratio > self.param_dict['makeagg_ratio']:
                        branch_flag = 1
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 2
                        close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 3
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 4
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if ask_price < round(open_price-self.param_dict['stop_profit'], 2):
                    branch_flag = 5
                    close_behavior = MAKEBEST
                else:
                    if bid_price >= open_price + round(self.param_dict['make_profit_margin']-0.05, 2):
                        branch_flag = 23
                        close_behavior = AGGPROFIT
                    elif burnout:
                        branch_flag = 6
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 7
                        close_behavior = TAKEPROFIT
        else:
            # short
            direction = 'short'
            if ask_price > open_price + self.param_dict['stop_loss']:
                if bid_price > open_price+self.param_dict['stop_profit']:  
                    # active close
                    make_agg_ratio = diff(bid_price, open_price)/diff(ask_price, open_price)
                    if self.param_dict.get('close_trade_info', None) and bool(trade) and (trade >= ask_price):
                        branch_flag = 31
                        close_behavior = AGGLOSS
                    elif make_agg_ratio > self.param_dict['makeagg_ratio']:
                        branch_flag = 8
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 9
                        close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 10
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 11
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if bid_price > open_price+self.param_dict['stop_profit']:
                    branch_flag = 12
                    close_behavior = MAKEBEST
                else:
                    if ask_price <= round(open_price - round(self.param_dict['make_profit_margin']+0.05, 2), 2):
                        branch_flag = 24
                        close_behavior = AGGPROFIT
                    elif burnout:
                        branch_flag = 13
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 14
                        close_behavior = TAKEPROFIT
        
        if mode != 'AGG':
            if branch_flag == 23 or branch_flag == 24:
                close_behavior = TAKEPROFIT
        
        return close_behavior, direction, branch_flag
    

    def create_slot(self, action , price, timestamp, bid_price, ask_price, trade_p, data_dict):
        # Based on action & trade type calculate volume & price traded
        executed_order = False
        available_volume = 0
        # make sure that price is .2f
        price = round(price, 2)
        ask_price = round(ask_price, 2)
        bid_price = round(bid_price, 2)
        trade_p = round(trade_p, 2)

        if action > 0:
            if price >= ask_price or price >= trade_p:
                executed_order = True
                if price >= ask_price:
                    available_volume = min(max(data_dict['a_vol'], 1), abs(action))
                else:
                    available_volume = min(max(data_dict['trd_vol'], 1), abs(action))
        elif action < 0:
            if price <= bid_price or price <= trade_p:
                executed_order = True
                if price <= bid_price:
                    available_volume = min(max(data_dict['b_vol'], 1), abs(action))
                else:
                    available_volume = min(max(data_dict['trd_vol'], 1), abs(action))
        if not executed_order or action == 0:
            # Placed order was not taken
            return self.remove_slot()
        
        volume = action/abs(action)*available_volume
        if round(volume) == 0:
            print('noo padlo to tam')
            print('action', action, 'available_volume', available_volume)
            print(data_dict)
        self.update_position(price, volume, timestamp)

        self.stats_dict['timestamp'].append(timestamp)
        self.stats_dict['position'].append(self.get_open_position())
        self.stats_dict['action'].append(volume)
        self.stats_dict['price_level'].append(price)
        self.stats_dict['open_price'].append(self.position_dict['open_price'])

        return price, volume


    def update_position(self, price, volume, timestamp):
        def calculate_profit(position, open_price, closing_price):
            if position > 0:
                return round(closing_price - open_price, 2)
            else:
                return round(open_price - closing_price, 2)
            
        # volume is negative for short position
        if self.position_dict['open_time'] is None:
            # There was no position -> open
            self.position_dict['open_price'] = price
            self.position_dict['trailing_price'] = price
            self.position_dict['open_time'] = timestamp
            self.position_dict['volume'] = volume
            tp = self.position_dict['open_price'] + self.param_dict['make_profit_margin'] if volume > 0 else self.position_dict['open_price'] - self.param_dict['make_profit_margin']
            self.position_dict['takeprofit'] = tp

        else:
            # update parameters for the existing postion
            # open_price has to be averaged when increasing position
            # reseting position dict when position is balanced
            # when position is decrease just add the volume, current volume should have inversed sign
            pos_direction = 'long' if round(self.position_dict['volume']) > 0 else 'short'
            curr_direction = 'long' if round(volume) > 0 else 'short'
            old_p, old_v = self.position_dict['open_price'], self.position_dict['volume']
            if pos_direction == curr_direction:
                try:
                    self.position_dict['open_price'] = round((old_p*old_v + price*volume)/(old_v+volume),2)
                except:
                    raise ValueError
                    
                self.position_dict['volume'] += volume
            else:
                if round(old_v + volume) == 0:
                    self.daily_profit[-1]['pnl'] += calculate_profit(old_v, old_p, price)
                    self.position_dict = self.init_position_dict
                else:
                    if pos_direction != curr_direction:
                        self.position_dict['volume'] += volume
    
    def update_open_price(self, data_dict):
        open_position = self.get_open_position()
        open_price = self.position_dict['trailing_price']
        if open_position > 0:
            if data_dict['b_price']  > open_price:
                self.position_dict['trailing_price'] = data_dict['b_price']
        elif open_position < 0:
            if data_dict['a_price'] < open_price:
                self.position_dict['trailing_price'] = data_dict['a_price']
        else:
            print('ERROR Unexpected position', data_dict)

    def simulate_position_short(self, np_arr):
        if isinstance(np_arr, np.ndarray):
            data_dict = {k: v for k, v in zip(self.columns, np_arr)}
        else:
            raise ValueError(f"cache return incorect data type ({type(np_arr)})")
            
        result = None
        t_end = data_dict['timestamp'].time() >= self.param_dict['t_end']
        self.change_date_profit(data_dict)
        if self.get_open_position() == 0 and not t_end:
            a_price, b_price = data_dict['a_price'], data_dict['b_price']
            volume = -round(self.max_position)
            price = a_price if volume > 0 else b_price
            self.create_slot(volume, price, data_dict['timestamp'],
                b_price, a_price, data_dict['trd_price'], data_dict)
        elif t_end and (self.get_open_position() == 0):
            return 0.0
        else:
            open_price = self.position_dict['open_price']
            price, volume = self.lift_act(data_dict)
            if volume != 0:
                result = round(open_price - price, 2)
        return result

    def simulate_position_long(self, np_arr):
        if isinstance(np_arr, np.ndarray):
            data_dict = {k: v for k, v in zip(self.columns, np_arr)}
        else:
            raise ValueError(f"cache return incorect data type ({type(np_arr)})")
            
        result = None
        t_end = data_dict['timestamp'].time() >= self.param_dict['t_end']
        self.change_date_profit(data_dict)
        if self.get_open_position() == 0 and not t_end:
            a_price, b_price = data_dict['a_price'], data_dict['b_price']
            volume = round(self.max_position)
            price = a_price if volume > 0 else b_price
            self.create_slot(volume, price, data_dict['timestamp'],
                b_price, a_price, data_dict['trd_price'], data_dict)
        elif t_end and (self.get_open_position() == 0):
            return 0.0
        else:
            open_price = self.position_dict['open_price']
            price, volume = self.lift_act(data_dict)
            if volume != 0:
                result = round(price - open_price, 2)
        return result