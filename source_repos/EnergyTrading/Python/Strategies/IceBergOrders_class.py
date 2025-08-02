# -*- coding: utf-8 -*-
"""
Created on Thu Jan  4 14:31:40 2024

@author: krajcovic
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Database.TPData import TPDataDa
from scipy.stats import skew, kurtosis
import matplotlib.pyplot as plt
import seaborn as sns

class IceBergOrders:
    
    def __init__(self, best_orders, all_trades):
        self.best_orders = best_orders
        self.all_trades = all_trades

    def prepare_data(self):
        # Ensure datetime_seconds is in the correct datetime format
        self.best_orders['datetime_seconds'] = pd.to_datetime(self.best_orders.index)

        # Set the index and resample
        df_ba_aux = self.best_orders.set_index('datetime_seconds').resample('S').ffill()

        trades_aux = self.all_trades[['price', 'volume', 'datetime_seconds']].copy()
        trades_aux['datetime_seconds'] = pd.to_datetime(trades_aux['datetime_seconds'])
        trades_aux = trades_aux.set_index('datetime_seconds')

        self.data = trades_aux[['price', 'volume']].reset_index().merge(df_ba_aux.reset_index(),
                                                                        on='datetime_seconds', how='left')
        self.data = self.data.set_index('datetime_seconds')
        self.data['trade_side'] = np.where(self.data['mid'] > self.data['price'], 0, 1)
        self.data = self.data.reset_index()
        
    def group_and_analyze(self):
        # Define the new grouping condition and perform calculations
        condition = (
            (self.data['price'] != self.data['price'].shift()) |
            (self.data['trade_side'] != self.data['trade_side'].shift()) |
            (self.data['datetime_seconds'].dt.date != self.data['datetime_seconds'].shift().dt.date)
        )
        self.data['group'] = condition.cumsum()
        self.data['cumulative_volume'] = self.data.groupby('group')['volume'].cumsum()
        self.data['average_action'] = self.data.groupby('group')['trade_side'].cumsum() / \
            (self.data.groupby('group')['trade_side'].cumcount() + 1)

        self.grouped_data = self.data.groupby('group').last()
        self.grouped_data['date'] = self.grouped_data['datetime_seconds'].dt.date
        
    def analyze_orders(self):
        # Initialize dictionaries
        ob_dict = {'active': {}, 'passive': {}}

        # Process each date
        for date, group_data in self.grouped_data.groupby('date'):
            active_dict = {0: {}, 1: {}}
            passive_dict = {0: {}, 1: {}}

            for _, row in group_data.iterrows():
                trade_side = row['trade_side']
                price = row['price']
                cum_volume = row['cumulative_volume']

                # Update active orders
                self.update_order_dict(active_dict[trade_side], price, cum_volume)

                # Check for passive order conditions
                self.check_passive_orders(active_dict, passive_dict, row)

            ob_dict['active'][date] = active_dict
            ob_dict['passive'][date] = passive_dict

        self.ob_dict = ob_dict
        self.calculate_iceberg_volumes()

    def update_order_dict(self, order_dict, price, volume):
        if price in order_dict:
            order_dict[price].append(volume)
        else:
            order_dict[price] = [volume]

    def check_passive_orders(self, active_dict, passive_dict, row):
        trade_side = row['trade_side']
        price = row['price']
        opposite_side = 1 - trade_side

        for stored_price in list(active_dict[opposite_side].keys()):
            if (trade_side == 0 and price < stored_price) or (trade_side == 1 and price > stored_price):
                if stored_price not in passive_dict[opposite_side]:
                    passive_dict[opposite_side][stored_price] = []

                passive_dict[opposite_side][stored_price].extend(active_dict[opposite_side].pop(stored_price))

    # @staticmethod
    # def update_order_dict( order_dict, price, volume, trade_side, date,i):
    #     if price in order_dict:
    #         order_dict[price]['volume'].append(volume)
    #     else:
    #         order_dict[price] = {'volume': [volume], 'after_prices': []}
    #         print(order_dict[price])
    #     return order_dict
    # def update_order_dict(self, order_dict, price, volume):
    #     if price in order_dict:
    #         order_dict[price].append(volume)
    #     else:
    #         order_dict[price] = [volume]
    # @staticmethod
    # def add_trade_to_dict(active_dict, passive_dict, price):
    #     for which_dict, cur_dict in enumerate([passive_dict, active_dict]):
    #         for trade_side in cur_dict.keys():
    #             for key in cur_dict[trade_side].keys():
                    
    #                 cur_dict[trade_side][key]['after_prices'].append(price)
    #     return active_dict, passive_dict
    
    # @staticmethod
    # def check_passive_orders(active_dict, passive_dict, row):
    #     trade_side = row['trade_side']
    #     price = row['price']
    #     opposite_side = 1 - trade_side

    #     for stored_price in list(active_dict[opposite_side].keys()):
    #         if (trade_side == 0 and price < stored_price) or (trade_side == 1 and price > stored_price):
    #             if stored_price not in passive_dict[opposite_side]:
    #                 passive_dict[opposite_side][stored_price] = []

    #             passive_dict[opposite_side][stored_price].extend(active_dict[opposite_side].pop(stored_price))
                
    #     return active_dict, passive_dict

    def calculate_iceberg_volumes(self):
        iceberg_list = []
        for a_p in self.ob_dict.keys():
            for date in self.ob_dict[a_p].keys():
                for side in self.ob_dict[a_p][date].keys():
                    for price, volumes in self.ob_dict[a_p][date][side].items():
                        iceberg_list.extend(volumes)

        self.iceberg_volumes = pd.Series(iceberg_list)
        
# if __name__ == '__main__':
#     analyzer = TradeAnalyzer(best_orders, all_trades)
#     analyzer.prepare_data()
#     analyzer.calculate_price_within()
#     analyzer.group_and_analyze()
#     analyzer.analyze_orders()
        
def process_trades_w_orders(trades:pd.DataFrame, orders:pd.DataFrame):
    result = []
    last_ts = None
    for index in range(len(all_trades)):
        row = all_trades.reset_index().iloc[index]
        curr_ts = row['datetime']
        if index > 0:
            top_bid = best_orders.loc[last_ts:curr_ts]['bidbestprice'].max()
            top_ask = best_orders.loc[last_ts:curr_ts]['askbestprice'].min()
            try:
                last_mid = best_orders.loc[last_ts:curr_ts]['mid'][-1]
                result.append({
                    'datetime': row['datetime'],
                    'price': row['price'],
                    'volume': row['volume'],
                    'top_bid_between': top_bid,
                    'top_ask_between': top_ask,
                    'direction': row['price'] > last_mid
                })
            except:
                result.append({
                    'datetime': row['datetime'],
                    'price': row['price'],
                    'volume': row['volume'],
                    'top_bid_between': np.nan,
                    'top_ask_between': np.nan,
                    'direction': np.nan
                })


            last_ts = row['datetime']
        else:
            last_mid = best_orders.loc[:curr_ts]['mid'][-1]
            result.append({
                'datetime': row['datetime'],
                'price': row['price'],
                'volume': row['volume'],
                'top_bid_between': np.nan,
                'top_ask_between': np.nan,
                'direction': 0 if row['price'] > last_mid else 1
            })
            last_ts = row['datetime']
    return result

# Constants
BID_ = True
ASK_ = False   

class IcebergStorage():
    def __init__(self) -> None:
        self.data_list = []
        self.icebergs = {}

    @property
    def active_levels(self) -> list():
        try:
            return [i for i, v in enumerate(self.data_list) if v['active']]
        except:
            return False
        
    def active_check(self, price):
        counter = 0
        active_indices = self.active_levels
        for i in active_indices:
            ptr_level_dict = self.data_list[i]
            level = [k for k, _ in ptr_level_dict[0].items()][0]
            data_dict = [v for k, v in ptr_level_dict[0].items()][0]
            price_diff = abs(abs(price) - abs(level))
            if data_dict['direction'] == BID_:
                if price < level:
                    ptr_level_dict['active'] = False
                    data_dict['break_price'] = price_diff
                    counter += 1
            else:
                if price > level:
                    ptr_level_dict['active'] = False
                    data_dict['break_price'] = price_diff
                    counter += 1
            
            data_dict['max_diff_price'] = price_diff if price_diff > data_dict['max_delta_price'] else data_dict['max_diff_price']
        
        return counter

    def group_icebergs(self):
        for i, dict_object in enumerate(self.data_list):
            level = [k for k, _ in dict_object[0].items()][0]
            volume = dict_object[level]['volume']
            if volume in self.icebergs:
                self.icebergs[volume]['count'] += 1
                self.icebergs[volume]['break_price'].append(dict_object[level]['break_price'])
                self.icebergs[volume]['max_diff_price'].append(dict_object[level]['max_diff_price'])
            else:
                self.icebergs.update({
                    volume: {
                        'count': 1,
                        'break_price': [dict_object[level]['break_price']],
                        'max_diff_price': [dict_object[level]['max_diff_price']]
                    }
                })

    def get_iceberg_data(self, trade_ord_dict):
        trade_ord_df = pd.DataFrame(trade_ord_dict)
        iceberg_data = {}
        for ts in pd.date_range(start=trade_ord_dict[0]['datetime'],
                                end=trade_ord_dict[-1]['datetime'], freq='D'):
            day_data = trade_ord_df.loc[trade_ord_df['datetime'] == ts.date()].copy()
            # loop through day_data 
            for row in day_data.iterrows():
                level = row['price']
                if self.active_levels != None:
                    for index in self.active_levels:
                        if level in self.data_list[index]:
                            self.data_list[index][level]['volume'] += row['volume']
                else:
                    self.data_list.append({
                        level: {**row.to_dict(),
                                'max_diff_price': .0,
                                'break_price': .0,},
                        'active': True
                    })
                if self.active_levels == None:
                    continue
                
                print("Number of deactivated levels: ", self.active_check(level))

        # ulozit na export
        self.group_icebergs()
        self.data_list = []
            # Step:
            # go through every active iceberg level
            # --- increase volume, check for deactivation, keep top delta price
            # close active levels and update result data
            # output: dictionary (keys-> volume, value-> {price_delta: list(), })
            #active_levels check dat hore nejak

