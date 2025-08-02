# -*- coding: utf-8 -*-
"""
Created on Fri Sep 20 11:06:37 2024

@author: Marek
"""

import pandas as pd
import numpy as np
from Strategies.Market_making.backtest_class import BacktestClass

tol = 1e-6
trade_type_arb = {'open': 'MM', 'close': 'AGG'}


class BacktestArb(BacktestClass):
    def __init__(self, volm_class=None, trade_type=trade_type_arb):
        super().__init__(volm_class, trade_type)
        price_list = ['timestamp', 'mid_price', 'bid_price', 'ask_price',
                      'trd_price', 'trd_side', 'trd_broker_id']
        self.prices_dict = {k: [] for k in price_list}

    @staticmethod
    def pnl_series(pnl_dict):
        pnl = 0
        pos_diff = 0
        pnl_list, time_list = [], []
        for pos, p, t in zip(pnl_dict['position'], pnl_dict['price'], pnl_dict['timestamp']):
            pos_diff = pos - pos_diff
            pnl -= pos_diff * p
            if abs(pos) < tol:
                pos_diff = 0
                pnl_list.append(pnl)
                time_list.append(t)
        return pd.Series(pnl_list, index=time_list)

    @staticmethod
    def prepare_order_data(LoB_class):
        LoB_dict = {k: v.filter_aonnimpl() for k, v in LoB_class.LoB_dict.items()}
        LoB_class.update_data(LoB_dict, LoB_class.time_list)
        df_orders = pd.concat([LoB_class.best_bid_all, LoB_class.best_ask_all],
                              axis=1)
        df_orders.columns = ['bidbestprice', 'askbestprice']
        return df_orders

    @staticmethod
    def merge_data(df_orders, df_trades, adj_action=True):
        # Merge time of orders & trades
        timestamp = df_orders.index.union(df_trades.index).drop_duplicates()
        df_orders = df_orders.reindex(timestamp).ffill()
        # Prepare orders data
        mid_ser = .5 * (df_orders.loc[:, 'bidbestprice'] + df_orders.loc[:, 'askbestprice'])
        col_dict = {'bidbestprice': 'bid_price', 'askbestprice': 'ask_price'}
        df_orders = df_orders.rename(columns=col_dict)
        # Prepare trades data
        val_list = df_trades['price'].values.tolist()
        brk_list = df_trades['broker_id'].values.tolist()
        if adj_action:
            mid_list = mid_ser.loc[df_trades.index].values.tolist()
            act_list = [1 if p >= m else -1
                        for p, m in zip(val_list, mid_list)]
        else:
            aux_list = df_trades['action'].values.tolist()
            act_list = [1 if a < 0 else -1 for a in aux_list]
        df_trades = pd.DataFrame({'trd_price': val_list, 'trd_side': act_list,
                                  'broker_id': brk_list},
                                 index=df_trades.index).reindex(timestamp)
        return pd.concat([df_orders, df_trades], axis=1)

    # def merge_data_backtest(self, LoB_dict, df_trades, strategy_class,
    #                         adj_action=True):
    #     input_dict = self.merge_data_struct(LoB_dict, df_trades, adj_action)
    #     LoB_dict, df_trades = input_dict['LoB_dict'], input_dict['df_trades']
    #     timestamp = df_trades.index
    #     data_columns = strategy_class.data_columns
    #     data_dict = {t: strategy_class.get_attributes(LoB) for t, LoB in
    #                  zip(timestamp, LoB_dict.values())}
    #     df_orders = pd.DataFrame(data_dict, index=data_columns).T
    #     return pd.concat([df_orders, df_trades], axis=1)

    # @staticmethod
    # def merge_data_struct(LoB_dict, df_trades, adj_action=True):
    #     time_list = [x.time_snapshot for x in LoB_dict.values() if x.mid_price is not None]
    #     LoB_dict = {k: v for k, v in LoB_dict.items() if v.mid_price is not None}
    #     df_idx = pd.Series((LoB_dict.keys()), index=time_list)
    #     timestamp = df_idx.index.union(df_trades.index)
    #     timestamp = timestamp[~timestamp.duplicated(keep='first')]
    #     df_idx = df_idx.reindex(timestamp).ffill().dropna()
    #     df_trades = df_trades.reindex(df_idx.index)
    #     LoB_dict_new = {k: LoB_dict[i] for k, i in enumerate(df_idx.values)}
    #     # Prepare trades data
    #     val_list = df_trades['price'].values.tolist()
    #     brk_list = df_trades['broker_id'].values.tolist()
    #     mid_list = [x.mid_price for x in LoB_dict_new.values()]
    #     aux_list = df_trades['action'].values.tolist()
    #     # Change action based on mid
    #     if adj_action:
    #         act_list = [a if m is None else (1 if p >= m else -1)
    #                     for p, m, a in zip(val_list, mid_list, aux_list)]
    #     else:
    #         act_list = [1 if a < 0 else -1 for a in aux_list]
    #     df_trades = pd.DataFrame({'trd_price': val_list, 'trd_side': act_list,
    #                               'broker_id': brk_list},
    #                              index=df_trades.index).reindex(timestamp)
    #     return {'LoB_dict': LoB_dict_new, 'df_trades': df_trades}

    def merge_data_backtest(self, LoB_dict, df_trades, strategy_class,
                            adj_action=True):
        data_columns = strategy_class.data_columns
        data_dict = {LoB.time_snapshot: strategy_class.get_attributes(LoB)
                     for LoB in LoB_dict.values()}
        cols_to_check = strategy_class.data_columns[:4]
        df_orders = pd.DataFrame(data_dict, index=data_columns).T.dropna(subset=cols_to_check)
        mid_ser = .5 * (df_orders.loc[:, 'bid_price'] + df_orders.loc[:, 'ask_price'])
        df_orders = df_orders[mid_ser != mid_ser.shift()]
        return self.merge_data_struct(df_orders, df_trades, adj_action)

    @staticmethod
    def merge_data_struct(df_orders, df_trades, adj_action=True):
        # Merge time of orders & trades
        timestamp = df_orders.index.union(df_trades.index).drop_duplicates()
        df_orders = df_orders.reindex(timestamp).ffill()
        # Prepare orders data
        mid_ser = .5 * (df_orders.loc[:, 'bid_price'] + df_orders.loc[:, 'ask_price'])
        # Prepare trades data
        val_list = df_trades['price'].values.tolist()
        brk_list = df_trades['broker_id'].values.tolist()
        aux_list = df_trades['action'].values.tolist()
        # Change action based on mid
        if adj_action:
            mid_list = mid_ser.loc[df_trades.index].values.tolist()
            mid_list_l = mid_ser.shift().loc[df_trades.index].values.tolist()
            act_list = [a if m is None else (1 if p >= m else -1)
                        for p, m, a in zip(val_list, mid_list, aux_list)]
            act_list[1:] = [(1 if p >= m else -1) if b != 1441 else a
                            for p, m, a, b in zip(val_list[1:], mid_list_l,
                                                  act_list[1:], brk_list[1:])]
        else:
            act_list = [1 if a > 0 else -1 for a in aux_list]
        df_trades = pd.DataFrame({'trd_price': val_list, 'trd_side': act_list,
                                  'broker_id': brk_list},
                                 index=df_trades.index).reindex(timestamp)
        return pd.concat([df_orders, df_trades], axis=1)

    @staticmethod
    def prepare_data(data_dict):
        # time_list = [x.time_snapshot for x in data_dict['LoB_dict'].values()]
        # df_idx = pd.Series(list(data_dict['LoB_dict'].keys()), index=time_list)
        # # LoB_dict = {x.filter_aonnimpl() for x in data_dict['LoB_dict'].values()}
        # timestamp = df_idx.index.union(data_dict['df_trades'])
        # timestamp = timestamp[~timestamp.duplicated(keep='first')]
        # df_idx = df_idx.reindex(timestamp).ffill()
        # df_trades = data_dict['df_trades'].reindex(timestamp)
        # LoB_dict = {i: data_dict['LoB_dict'][i] for i in df_idx.values}
        df_trades = data_dict['df_trades']
        LoB_dict = data_dict['LoB_dict']
        out_dict = df_trades.reset_index().to_dict()
        if 'timestamp' not in out_dict.keys():
            out_dict['timestamp'] = out_dict['index']
        out_dict.pop('index', None)
        out_dict['LoB'] = [x for x in LoB_dict.values()]
        return out_dict

    # @staticmethod
    # def get_price_dict(input_dict):
    #     out_dict = {}
    #     timestamp = input_dict['timestamp']
    #     LoB = input_dict['LoB']
    #     bid_price = LoB.best_bid.price_val
    #     ask_price = LoB.best_ask.price_val
    #     mid_price = LoB.mid_price
    #     trd_price = input_dict['trd_price']
    #     trd_side = input_dict['trd_side']
    #     out_dict['timestamp'] = timestamp
    #     out_dict['bid_price'] = bid_price
    #     out_dict['ask_price'] = ask_price
    #     out_dict['mid_price'] = mid_price
    #     out_dict['trd_mkt'] = trd_price
    #     out_dict['trd_side'] = trd_side
    #     return out_dict

    def get_price_dict(self, input_dict):
        input_dict['mid_price'] = .5 * (input_dict['bid_price'] + input_dict['ask_price'])
        return {k: input_dict[k] for k in self.prices_dict.keys() if k in input_dict.keys()}

    def simulate_strategy(self, strategy_class, method, instr, data_dict):
        # Simulate strategy defined by strategy class
       # Prepare data
        df_data = data_dict[instr].reset_index()
        struct_dict = df_data.to_dict('list')
        if 'timestamp' not in struct_dict.keys():
            struct_dict['timestamp'] = struct_dict['index']
        struct_dict.pop('index', None)
        del df_data
        # Reset class
        self.reset_time()
        self.nT = len(struct_dict['timestamp'])
        # Run strategy on data
        aux_dict = {k: v[self.current_t] for k, v in struct_dict.items()}
        self.prices_dict.update(self.get_price_dict(aux_dict))
        while self.is_active:
            aux_dict = {k: v[self.current_t] for k, v in struct_dict.items()}
            price_dict = self.get_price_dict(aux_dict)
            # Update price dict after night
            if price_dict['timestamp'].date() != self.prices_dict['timestamp'].date():
                self.prices_dict.update(price_dict)
            price_list, vol_list = strategy_class.process(aux_dict, method)
            position = strategy_class.curr_position - sum(vol_list)
            for p, v in zip(price_list, vol_list):
                if p is None:
                    pass
                else:
                    self.save_trade(price_dict, p, v, position)
                    position += v
            # Update last prices
            self.prices_dict.update(price_dict)
            self.progress_time()
        return self.pnl_series(strategy_class.stats_dict)

    def arb_stat(self, df_orders, df_trades, brk_ids, side='all'):
        df_trades = df_trades[df_trades['broker_id'].isin(brk_ids)]
        df_data = self.merge_data(df_orders, df_trades)
        df_data = df_data.dropna()
        # Arbitrage opportunities
        if 'bid' == side:
            mrg_ser = (df_data.loc[:, 'bid_price'] - df_data.loc[:, 'trd_price']).clip(lower=0)
        elif 'ask' == side:
            mrg_ser = (df_data.loc[:, 'trd_price'] - df_data.loc[:, 'ask_price']).clip(lower=0)
        elif 'all' == side:
            mrg_bid_ser = (df_data.loc[:, 'bid_price'] - df_data.loc[:, 'trd_price']).clip(lower=0)
            mrg_ask_ser = (df_data.loc[:, 'trd_price'] - df_data.loc[:, 'ask_price']).clip(lower=0)
            mrg_ser = mrg_bid_ser + mrg_ask_ser
        else:
            raise ValueError('arb_stat: Unknown side %s' & side)
        mrg_ser.name = 'mrg'
        return mrg_ser.round(2)

    def trd_arb(self, df_orders, df_trades, brk_ids, side='all', n_sec=3):
        df_lead = df_trades[df_trades['broker_id'].isin(brk_ids)]
        df_lift = df_trades[~df_trades['broker_id'].isin(brk_ids)]
        df_comb = pd.concat([df_lead.loc[:, 'price'], df_lift.loc[:, ['price', 'broker_id']]], axis=1)
        df_comb.columns = ['lead_price', 'lift_price', 'broker_id']
        col_list = ['mrg', 'time_diff']
        if df_orders is None:
            col_list.append('broker_id')
            df_data = calculate_lead_lift_difference(df_comb, n_sec)
            idx_b = df_data['side'] < 0
            idx_a = df_data['side'] > 0
            if side == 'bid':
                df_mrgs = df_data.loc[idx_b, col_list]
            elif side == 'ask':
                df_mrgs = df_data.loc[idx_a, col_list]
            else:
                df_mrgs = df_data.loc[:, col_list]
        else:
            mrg_ser = self.arb_stat(df_orders, df_trades, brk_ids, side)
            df_data = self.merge_data(df_orders, df_trades)
            # Bids
            idx_b = df_data.dropna()['trd_side'] == -1
            # Asks
            idx_a = df_data.dropna()['trd_side'] == 1
            if side == 'bid':
                df_bids = pd.concat([df_data.iloc[:, :2], df_comb.loc[idx_b],
                                     mrg_ser.loc[idx_b]], axis=1)
                df_bids = select_rows_based_on_conditions(df_bids, 'bid')
                df_mrgs = df_bids.loc[:, col_list].dropna()
            elif side == 'ask':
                df_asks = pd.concat([df_data.iloc[:, :2], df_comb.loc[idx_a],
                                     mrg_ser.loc[idx_a]], axis=1)
                df_asks = select_rows_based_on_conditions(df_asks, 'ask')
                df_mrgs = df_asks.loc[:, col_list].dropna()
            elif side == 'all':
                # Bids
                df_bids = pd.concat([df_data.iloc[:, :2], df_comb.loc[idx_b],
                                     mrg_ser.loc[idx_b]], axis=1)
                df_bids = select_rows_based_on_conditions(df_bids, 'bid')
                # Asks
                df_asks = pd.concat([df_data.iloc[:, :2], df_comb.loc[idx_a],
                                     mrg_ser.loc[idx_a]], axis=1)
                df_asks = select_rows_based_on_conditions(df_asks, 'ask')
                # Merge
                df_mrgs = pd.concat([df_bids.loc[:, col_list].dropna(),
                                     df_asks.loc[:, col_list].dropna()], axis=0)
                df_mrgs = df_mrgs.sort_index()
            df_mrgs = df_mrgs.astype(float)
        return df_mrgs


def select_rows_based_on_conditions(df_data, side):
    if side == 'bid':
        side_column = 'bid_price'
    elif side == 'ask':
        side_column = 'ask_price'
    selected_rows = []
    it_skip_list = []
    k = 0
    # Iterate through the rows of the dataframe
    for i, (t, row) in enumerate(df_data.iterrows()):
        if pd.notna(row['lead_price']) and row['mrg'] > 0:  # If lead_price is not None
            lead_bid_price = row[side_column]
            if i not in it_skip_list:
                next_row = df_data.iloc[i, :].copy()
                next_row['count'] = k
                selected_rows.append(next_row)
            else:
                continue
            # Look for subsequent rows
            next_bool = True
            next_step = True
            place_bool = False
            for j in range(i+1, len(df_data)):
                next_row = df_data.iloc[j, :].copy()
                it_skip_list.append(j)
                if next_row['mrg'] > 0:
                    next_row['count'] = k
                    selected_rows.append(next_row)
                    place_bool = True
                # Check conditions for subsequent rows
                if next_row[side_column] == lead_bid_price or pd.notna(next_row['lift_price']):
                    next_step = False
                    if pd.notna(next_row['lift_price']):
                        if not place_bool:
                            next_row['count'] = k
                            selected_rows.append(next_row)
                    else:
                        other_row = df_data.iloc[j+1, :].copy()
                        if other_row[side_column] == lead_bid_price:
                            next_bool = True
                        else:
                            next_bool = False
                            other_row['count'] = k
                            selected_rows.append(other_row)
                            it_skip_list.append(j+1)
                else:
                    if next_step:
                        if not place_bool:
                            next_row['count'] = k
                            selected_rows.append(next_row)
                    next_bool = False
                if not next_bool:
                    k += 1
                    break

    return calculate_time_diff(pd.DataFrame(selected_rows))


def calculate_time_diff(df_data):
    # Ensure timestamp is in datetime format if not already
    df_data.index = pd.to_datetime(df_data.index)
    
    # Create a new column to store the time difference
    df_data['time_diff'] = None

    # Group by count
    for count_group, group in df_data.groupby('count'):
        # Find the timestamp of the last row in the group
        last_timestamp = group.index.max()
        
        # For rows where mrg is not NaN (has a value), calculate the time difference
        mask = pd.notna(group['mrg'])  # Find rows where mrg has a value
        df_data.loc[group[mask].index, 'time_diff'] = (last_timestamp - group[mask].index).total_seconds()

    df_data.loc[:, 'time_diff'] = df_data.loc[:, 'time_diff'].astype(float)
    return df_data


def calculate_lead_lift_difference(df, n_seconds):
    results = []
    
    for i, row in df.iterrows():
        if pd.notna(row['lead_price']):  # If there is a lead_price
            lead_price = row['lead_price']
            lead_time = i  # Get the timestamp of the lead_price
            
            # Search for a lift_price within n seconds in subsequent rows
            for j, future_row in df.loc[i:].iterrows():
                time_diff = (j - lead_time).total_seconds()  # Time difference in seconds
                
                if time_diff <= n_seconds and pd.notna(future_row['lift_price']):  # If lift_price is within n seconds
                    lift_price = future_row['lift_price']
                    lift_brk = future_row['broker_id']
                    price_diff = lift_price - lead_price  # Calculate the price difference
                    try:
                        time_diff = float((j - lead_time).total_seconds())
                    except(TypeError):
                        time_diff = np.nan
                    if price_diff > 0:
                        side = 1
                    elif price_diff < 0:
                        side = -1
                    else:
                        side = 0
                    results.append({'Index': lead_time, 'side': side, 'mrg': abs(price_diff), 'time_diff': time_diff, 'broker_id': lift_brk})
                    break  # Stop searching once the first lift_price is found

    return pd.DataFrame(results).set_index('Index')

