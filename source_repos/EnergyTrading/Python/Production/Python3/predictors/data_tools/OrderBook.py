# -*- coding: utf-8 -*-
"""
Created on Thu Nov 14 15:51:28 2019

@author: zelenaymar
"""

import datetime as dt
import numpy as np
import pandas as pd
import dateutil as dtu
import matplotlib.pyplot as plt
import os
import pickle
from copy import deepcopy, copy
from bisect import insort


tres_const = 0.15 - 0.0001
time_shift = dtu.relativedelta.relativedelta(seconds=1)


class OrderBookSnaps:
    def __init__(self, LoB_dict={}, time_list=[], verbose=False):
        self.err_dict = {k: {} for k in ['insert', 'update', 'remove', 'query',
                                         'viol', 'omit']}
        self.update_data(LoB_dict, time_list)
        self.__verbose = verbose

    @property
    def verbose(self):
        return self.__verbose

    @property
    def time_list(self):
        return self.__time_list

    @property
    def date_list(self):
        return self.__date_list

    @property
    def best_bid(self):
        try:
            val_list = [np.nan if x.best_bid is None else x.best_bid.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_bid_all(self):
        try:
            val_list = [np.nan if x.best_bid_all is None else x.best_bid_all.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_bid_any(self):
        try:
            val_list = [np.nan if x.best_bid_any is None else x.best_bid_any.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_bid_any_noi(self):
        try:
            val_list = [np.nan if x.best_bid_any_noi is None else x.best_bid_any_noi.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    def best_bid_ven(self, venue):
        try:
            val_list = [np.nan if x.best_bid_ven(venue) is None
                        else x.best_bid_ven(venue).price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_ask(self):
        try:
            val_list = [np.nan if x.best_ask is None else x.best_ask.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_ask_all(self):
        try:
            val_list = [np.nan if x.best_ask_all is None else x.best_ask_all.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_ask_any(self):
        try:
            val_list = [np.nan if x.best_ask_any is None else x.best_ask_any.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    @property
    def best_ask_any_noi(self):
        try:
            val_list = [np.nan if x.best_ask_any_noi is None else x.best_ask_any_noi.price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    def best_ask_ven(self, venue):
        try:
            val_list = [np.nan if x.best_ask_ven(venue) is None
                        else x.best_ask_ven(venue).price_val
                        for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    def price_vol_bid(self, volume):
        try:
            val_list = [x.price_vol_bid for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    def price_vol_ask(self, volume):
        try:
            val_list = [x.price_vol_ask for x in self.LoB_dict.values()]
        except(KeyError):
            val_list = []
        time_list = self.time_list
        return pd.Series(val_list, index=time_list)

    def export_data(self, file_path, file_name):
        data = [x.export for x in self.LoB_dict.values()]
        try:
            os.makedirs(file_path)
        except(OSError):
            pass
        pickle.dump(data, open(file_path + file_name, "wb"))
        return 0

    def import_data(self, file_path):
        ts_s = dt.datetime.now().timestamp()
        try:
            f_myfile = open(file_path, 'rb')
        except:
            f_myfile = open(file_path.replace('/', '\\').replace('\\\\', '\\'), 'rb')
        data = pickle.load(f_myfile)
        f_myfile.close()
        LoB_dict = {i: v.export for i, v in enumerate(data)}
        time_list = [x.time_snapshot for x in data]
        self.update_data(LoB_dict, time_list)
        ts_e = dt.datetime.now().timestamp()
        return ts_e - ts_s

    def import_from_tp(self, df_data):
        data_dict = df_data.to_dict(orient='split')
        LoB_dict = {}
        time_list = []
        i = 0
        for ts, ords in zip(data_dict['index'], data_dict['data']):
            order_book_single = OrderBookSingle()
            order_book_single.bids = [Order.from_tp_dict(x, 'bid').export
                                      for x in ords[0]]
            order_book_single.asks = [Order.from_tp_dict(x, 'ask').export
                                      for x in ords[1]]
            order_book_single.time_snapshot = ts
            try:
                if order_book_single == LoB_dict[i - 1]:
                    pass
                else:
                    LoB_dict[i] = order_book_single
                    time_list.append(ts)
                    i += 1
            except(KeyError):
                LoB_dict[i] = order_book_single
                time_list.append(ts)
                i += 1
        self.update_data(LoB_dict, time_list)

    def err_append(self, action, err_order):
        # Append error to error dictionary
        po_id = str(err_order.po_id)
        try:
            self.err_dict[action][po_id].append(err_order)
        except(KeyError):
            self.err_dict[action][po_id] = [err_order]

    def clear(self):
        self.LoB_dict = {}
        self.err_dict = {k: {} for k in ['insert', 'update', 'remove', 'query',
                                         'viol', 'omit']}
        self.__time_list = []

    def update_data(self, LoB_dict, time_list):
        self.LoB_dict = LoB_dict
        self.__time_list = time_list
        self.__date_list = sorted(set([x.date() for x in time_list]))

    def merge_data(self, LoB_class):
        # Must be distinct time
        time_list_o = self.time_list
        time_list_n = LoB_class.time_list
        try:
            if time_list_o[-1] < time_list_n[0]:
                time_list = time_list_o
                time_list.extend(time_list_n)
                LoB_dict = self.LoB_dict
                n = len(LoB_dict.keys())
                LoB_dict_aux = {k + n: v for k, v in LoB_class.LoB_dict.items()}
                LoB_dict.update(LoB_dict_aux)
                del LoB_dict_aux, n
                # LoB_dict = {**self.LoB_dict, **LoB_class.LoB_dict}
            elif time_list_n[-1] < time_list_o[0]:
                time_list = time_list_n
                time_list.extend(time_list_o)
                LoB_dict = LoB_class.LoB_dict
                n = len(LoB_dict.keys())
                LoB_dict_aux = {k + n: v for k, v in self.LoB_dict.items()}
                LoB_dict.update(LoB_dict_aux)
                del LoB_dict_aux, n
                # LoB_dict = {**LoB_class.LoB_dict, **self.LoB_dict}
            else:
                ValueError('Distinct time property violated.')
        except(IndexError):
            if not time_list_o:
                time_list = time_list_n
                LoB_dict = LoB_class.LoB_dict
            elif not time_list_n:
                time_list = time_list_o
                LoB_dict = self.LoB_dict
            else:
                time_list = []
                LoB_dict = {}
        self.update_data(LoB_dict, time_list)

    def __construct(self, data_df, s_time, e_time, p_thres):
        # Select and copy all events from day
        c = data_df.copy()

        # Sort by time
        c.sort_values(by=['unique_id', 'datetime', 'persistentorderid'],
                      inplace=True)

        # Turn dataframe into a list of dicts/records so that
        # each row of the dataframe is converted to a dict
        E = c.to_dict(orient='records')
        # List of orders
        order_list = [order_from_dict(d) for d in E]

        # Iter over data
        prev_time_shot = c['datetime'].loc[:10].min()
        n = len(self.time_list)
        skip_iter = False
        replace_bool = False
        action_dict = order_list[0].action_dict
        LoB_prev = OrderBookSingle(verbose=self.verbose)
        k = 0
        ts = 0
        for i in range(len(order_list)):
            # Create Order from x
            order_cur = order_list[i]
            # Combine order updates in same timestamp
            if ts == order_cur.timestamp.time():
                pass
            else:
                LoB_prev.next_iter()
            ts = order_cur.timestamp.time()
            if ts > e_time:
                continue
            elif ts >= s_time:
                if i == 0:
                    pass
                else:
                    k += 1
                replace_bool = False
            else:
                if len(self.__time_list) == 0:
                    replace_bool = False
                else:
                    replace_bool = True
            k = max(k, 0)
            # Patch for timestamp errors
            if prev_time_shot > order_cur.timestamp:
                price = order_cur.price
                volume = order_cur.volume
                order_cur.update_order(prev_time_shot, price, volume)
                del price, volume
            if order_cur.po_id[:3] == 'GPb':
                skip_iter = True
                self.err_append('omit', order_cur)
            # Skip iteration if needed
            if skip_iter:
                skip_iter = False
                self.LoB_dict[n + k] = copy(LoB_prev)
                action_bool = self.LoB_dict[n + k].truncate(p_thres)
                if action_bool:
                    if not replace_bool:
                        if i == 0:
                            pass
                        else:
                            self.LoB_dict.pop(n + k)
                            k -= 1
                    else:
                        pass
                    continue
                if not replace_bool:
                    self.__time_list.append(self.LoB_dict[n + k].time_snapshot)
                else:
                    self.__time_list[-1] = self.LoB_dict[n + k].time_snapshot
                continue
            # Process order depending on its action
            if order_cur.action == action_dict['Insert']:
                try:
                    order_nxt = order_list[i + 1]
                except(IndexError):
                    order_nxt = None
                err, skip_iter = LoB_prev.insert_order(order_cur, order_nxt,
                                                       order_list[i + 1:])
                if err is not None:
                    self.err_append('insert', err)
                # Check if exists in error lists
                if LoB_prev.check_errors(order_cur, self.err_dict):
                    LoB_prev.check_errors(order_cur, self.err_dict)
                    _, _ = LoB_prev.remove_order(order_cur, None)
            elif order_cur.action == action_dict['Update']:
                try:
                    order_nxt = order_list[i + 1]
                except(IndexError):
                    order_nxt = None
                err, skip_iter = LoB_prev.update_order(order_cur, order_nxt)
                if err is not None:
                    self.err_append('update', err)
            elif order_cur.action == action_dict['Remove']:
                try:
                    order_nxt = order_list[i + 1]
                except(IndexError):
                    order_nxt = None
                err, skip_iter = LoB_prev.remove_order(order_cur, order_nxt)
                if err is not None:
                    self.err_append('remove', err)
            elif order_cur.action == action_dict['Query']:
                try:
                    order_nxt = order_list[i + 1]
                except(IndexError):
                    order_nxt = None
                try:
                    order_prv = order_list[i - 1]
                except(IndexError):
                    order_prv = None
                err, skip_iter = LoB_prev.query_order(order_cur, order_nxt,
                                                      order_prv)
                if err is not None:
                    self.err_append('query', err)
            elif order_cur.action == action_dict['Delete_All']:
                LoB_prev.conn_lost()
            err = LoB_prev._sanity_check(self.err_dict)
            if err is None:
                pass
            else:
                self.err_append('viol', err)
            if LoB_prev.time_snapshot is None:
                LoB_prev.time_snapshot = prev_time_shot
            self.LoB_dict[n + k] = copy(LoB_prev)
            action_bool = self.LoB_dict[n + k].truncate(p_thres)
            if action_bool:
                if not replace_bool:
                    if i == 0:
                        pass
                    else:
                        self.LoB_dict.pop(n + k)
                        k -= 1
                else:
                    pass
                continue
            if not replace_bool:
                self.__time_list.append(self.LoB_dict[n + k].time_snapshot)
            else:
                self.__time_list[-1] = self.LoB_dict[n + k].time_snapshot
            prev_time_shot = self.__time_list[-1]
        return 0

    def construct_single_day(self, data_df, day=None,
                             s_time=dt.time.min, e_time=dt.time.max,
                             p_thres=None):
        # The processing is based on 'created_utc' rather than 'order_date_utc'
        if day is None:
            day = data_df['date_created'].iloc[-1].date()

        self.__construct(data_df[data_df['day_created'] == day], s_time, e_time,
                         p_thres)
        self.__date_list.append(day)
        return self.LoB_dict, self.err_dict

    def construct_data(self, data_df, day=None,
                       s_time=dt.time.min, e_time=dt.time.max,
                       p_thres=None):
        # The processing is based on 'created_utc' rather than 'order_date_utc'
        self.__construct(data_df, s_time, e_time, p_thres)
        self.__date_list.append(day)
        return self.LoB_dict, self.err_dict

    def construct_all(self, data_df, slice_bool=False, clear_bool=True,
                      max_date=None, s_time=dt.time.min, e_time=dt.time.max,
                      p_thres=None):
        # Clear class
        if clear_bool:
            self.clear()
        # Obtain List of dates for data collection
        date_list = sorted(set(data_df['day_created']))
        if max_date is not None:
            date_list = [d for d in date_list if d <= max_date.date()]
        if slice_bool:
            for d in date_list:
                _, _ = self.construct_single_day(data_df, d, s_time, e_time,
                                                 p_thres)
        else:
            self.__construct(data_df, s_time, e_time, p_thres)
            self.__date_list.extend(date_list)
        # Clean data of time duplicates
        start_date = min(self.time_list)
        end_date = max(self.time_list)
        LoB_dict, time_list = self.LoB_select(start_date, end_date, freq=None)
        self.update_data(LoB_dict, time_list)
        return self.LoB_dict, self.err_dict

    def LoB_select(self, start_date, end_date, start_time=None, end_time=None,
                   freq=None):
        # Define active time interval
        if start_time is None:
            start_time = dt.time.min
        if end_time is None:
            end_time = dt.time.max
        # Find indices between two timestamps
        index = [i for i, v in enumerate(self.time_list)
                 if v >= start_date and v <= end_date]
        if not index:
            # Set the last ts of change
            index = [i for i, v in enumerate(self.time_list) if v < start_date]
            index = [index[-1]]
        else:
            if index[0] > 0:
                index.insert(0, index[0] - 1)
            else:
                pass
        # out_dict = {self.time_list[n]: self.LoB_dict[n] for n in index}
        out_dict = {i: self.LoB_dict[n] for i, n in enumerate(index)}
        time_list = [self.time_list[n] for n in index]
        # Select only latest LoB for each time
        # Select Unique dates
        _, ind_unq = np.unique(time_list, return_index=True)
        ind_unq = np.concatenate((ind_unq[1:], np.ones(1,) * len(time_list)))
        # Select Last LoB
        index = [int(x) - 1 for x in np.unique(ind_unq)]
        out_dict = {i: out_dict[n] for i, n in enumerate(index)}
        time_list = [time_list[n] for n in index]
        if freq is None:
            # Truncate between time chosen
            ind = [i for i, v in enumerate(time_list)
                   if v.time() >= start_time and v.time() <= end_time]
            time_list = [time_list[n] for n in ind]
            out_dict = {i: out_dict[n] for i, n in enumerate(ind)}
        else:
            time_list = pd.to_datetime(time_list).ceil(freq)
            # date_list = sorted(set(time_list))
            # ind = [time_list.index(x) for x in date_list]
            ind = np.arange(0, len(time_list))
            ind_ser = pd.Series(ind, time_list).resample(freq).last()
            ind_ser.fillna(method='ffill', inplace=True)
            # Truncate between time chosen
            ind_ser = ind_ser.between_time(start_time, end_time)
            out_dict = {i: out_dict[n] for i, n in enumerate(ind_ser.values)}
            time_list = ind_ser.index.tolist()
        return out_dict, time_list

    def LoB_truncate(self, thres_val=None, thres_vol=None, tp_bool=False):
        LoB_dict = self.LoB_dict
        time_list = self.time_list
        if thres_val is None:
            pass
        else:
            idx = []
            for i, LoB in LoB_dict.items():
                if tp_bool:
                    LoB.truncate(thres_val)
                    try:
                        # Check if ob is the same as previous
                        action_bool = LoB == LoB_dict[i - 1]
                    except(KeyError):
                        action_bool = False
                else:
                    action_bool = LoB.truncate(thres_val)
                if not action_bool:
                    idx.append(i)
            LoB_dict = {i: LoB_dict[n] for i, n in enumerate(idx)}
            time_list = [time_list[n] for n in idx]
        if thres_vol is None:
            pass
        else:
            idx = []
            for i, LoB in LoB_dict.items():
                if tp_bool:
                    LoB.truncate_vol(thres_vol)
                    try:
                        # Check if ob is the same as previous
                        action_bool = LoB == LoB_dict[i - 1]
                    except(KeyError):
                        action_bool = False
                else:
                    action_bool = LoB.truncate_vol(thres_vol)
                if not action_bool:
                    idx.append(i)
            LoB_dict = {i: LoB_dict[n] for i, n in enumerate(idx)}
            time_list = [time_list[n] for n in idx]
        return LoB_dict, time_list

    def plot_period(self, start_date=None, end_date=None, freq=None,
                    y_lim=None):
        bool_t = True
        shift = dtu.relativedelta.relativedelta(seconds=1)
        if start_date is None:
            start_date = self.time_list[0]
            bool_t = False
        if end_date is None:
            end_date = self.time_list[-1]
            bool_t = False

        if bool_t is True:
            orders_dict, time_list = self.LoB_select(start_date, end_date)
        else:
            orders_dict = self.LoB_dict
            time_list = self.time_list

        if freq is None:
            date_list = sorted(set(time_list))
        else:
            time_list = pd.to_datetime(time_list).ceil(freq).tolist()
            date_list = sorted(set(time_list))
        ind = [time_list.index(x) for x in date_list]

        o_list = [orders_dict[n] for n in ind]
        time_list = [time_list[n] for n in ind]
        # Get Bid Orders from dictionary
        price_b = [[y.price_val for y in reversed(x.bids)] for x in o_list]
        volms_b = [[y.volume_val for y in reversed(x.bids)] for x in o_list]
        dates_b = [[t.to_pydatetime()] * len(x) for t, x in zip(time_list, price_b)]
        # Flatten out
        price_b = [y for s in price_b for y in s]
        volms_b = [y for s in volms_b for y in s]
        dates_b = [y for s in dates_b for y in s]
        # Get Ask Orders from dictionary
        price_a = [[y.price_val for y in reversed(x.asks)] for x in o_list]
        volms_a = [[y.volume_val for y in reversed(x.asks)] for x in o_list]
        dates_a = [[t.to_pydatetime()] * len(x) for t, x in zip(time_list, price_a)]
        # Flatten out
        price_a = [y for s in price_a for y in s]
        volms_a = [y for s in volms_a for y in s]
        dates_a = [y for s in dates_a for y in s]
        # Plot data
        plt.figure(figsize=(12, 10))
        plt.scatter(dates_b, price_b, s=volms_b, label='Bid')
        plt.scatter(dates_a, price_a, s=volms_a, label='Ask')
        plt.xlim(start_date - shift, end_date)
        if y_lim is not None:
            plt.ylim(y_lim[0], y_lim[1])
        plt.ylabel('Price EUR')
        plt.title('Order book development')
        plt.legend(loc='upper left')
        plt.show()


class OrderBookExp:
    def __init__(self, order_book_single):
        self.bids = [x.export for x in order_book_single.bids]
        self.asks = [x.export for x in order_book_single.asks]
        self.time_snapshot = order_book_single.time_snapshot
        diff_dict = order_book_single.diff_dict
        try:
            self.diff_bid_ins = [x.export for x in diff_dict['bid']['ins']]
        except(AttributeError):
            self.diff_bid_ins = []
        try:
            self.diff_bid_del = [x.export for x in diff_dict['bid']['del']]
        except(AttributeError):
            self.diff_bid_del = []
        try:
            self.diff_ask_ins = [x.export for x in diff_dict['ask']['ins']]
        except(AttributeError):
            self.diff_ask_ins = []
        try:
            self.diff_ask_del = [x.export for x in diff_dict['ask']['del']]
        except(AttributeError):
            self.diff_ask_del = []

    @property
    def export(self):
        order_book_single = OrderBookSingle()
        order_book_single.bids = self.bids
        order_book_single.asks = self.asks
        order_book_single.time_snapshot = self.time_snapshot
        diff_dict = {k: {o: [] for o in ['ins', 'del']}
                     for k in ['bid', 'ask']}
        diff_dict['bid']['ins'] = self.diff_bid_ins
        diff_dict['bid']['del'] = self.diff_bid_del
        diff_dict['ask']['ins'] = self.diff_ask_ins
        diff_dict['ask']['del'] = self.diff_ask_del
        order_book_single.diff_dict = diff_dict
        return order_book_single


class OrderBookSingle:
    def __init__(self, verbose=False):
        self.bids = []
        self.asks = []
        self.time_snapshot = None
        # Dictionary of changes in OB
        self.diff_dict = {k: {o: [] for o in ['ins', 'del']}
                          for k in ['bid', 'ask']}
        # Auxiliary variables
        self.__aux_dict = {}
        self.__aux_dict['prods_list'] = ['timestamp', 'po_id']
        self.__aux_dict['price_list'] = ['price', 'volume']
        self.__verbose = verbose

    def __copy__(self):
        newcopy = OrderBookSingle(self.verbose)
        newcopy.bids = [copy(x) for x in self.bids]
        newcopy.asks = [copy(x) for x in self.asks]
        newcopy.time_snapshot = self.time_snapshot
        # newcopy.diff_dict.update(self.diff_dict)
        newcopy.diff_dict = {k: {l: [copy(x) for x in self.diff_dict[k][l]]
                                 for l in ['ins', 'del']}
                             for k in ['bid', 'ask']}
        return newcopy

    def __eq__(self, other):
        bids_bool = all([t == o for t, o in zip(self.bids, other.bids)])
        asks_bool = all([t == o for t, o in zip(self.asks, other.asks)])
        return bids_bool and asks_bool

    def filter_aonn(self):
        new_instance = self.__copy__()
        new_instance.bids = [x for x in new_instance.bids if not x.aon]
        new_instance.asks = [x for x in new_instance.asks if not x.aon]
        return new_instance

    def filter_impl(self):
        new_instance = self.__copy__()
        new_instance.bids = [x for x in new_instance.bids if not x.is_iven]
        new_instance.asks = [x for x in new_instance.asks if not x.is_iven]
        return new_instance
    
    def filter_aonnimpl(self):
        new_instance = self.__copy__()
        new_instance.bids = [x for x in new_instance.bids if not x.is_iven and not x.aon]
        new_instance.asks = [x for x in new_instance.asks if not x.is_iven and not x.aon]
        return new_instance

    @property
    def export(self):
        return OrderBookExp(self)

    @property
    def best_bid(self):
        try:
            k = 0
            while self.bids[k].is_iven:
                k += 1
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    @property
    def best_bid_all(self):
        try:
            k = 0
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    @property
    def best_bid_any(self):
        try:
            k = 0
            while self.bids[k].aon:
                k += 1
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    @property
    def best_bid_any_noi(self):
        try:
            k = 0
            while self.bids[k].aon or self.bids[k].is_iven:
                k += 1
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    def best_bid_ven(self, venue):
        try:
            k = 0
            while self.bids[k].venue != venue:
                k += 1
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    def best_bid_vens(self, venue_list):
        try:
            k = 0
            while self.bids[k].venue not in venue_list:
                k += 1
            best_bid = self.bids[k]
        except(IndexError):
            best_bid = None
        return best_bid

    @property
    def best_ask(self):
        try:
            k = 0
            while self.asks[k].is_iven:
                k += 1
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    @property
    def best_ask_all(self):
        try:
            k = 0
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    @property
    def best_ask_any(self):
        try:
            k = 0
            while self.asks[k].aon:
                k += 1
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    @property
    def best_ask_any_noi(self):
        try:
            k = 0
            while self.asks[k].aon or self.asks[k].is_iven:
                k += 1
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    def best_ask_ven(self, venue):
        try:
            k = 0
            while self.asks[k].venue != venue:
                k += 1
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    def best_ask_vens(self, venue_list):
        try:
            k = 0
            while self.asks[k].venue not in venue_list:
                k += 1
            best_ask = self.asks[k]
        except(IndexError):
            best_ask = None
        return best_ask

    @property
    def mid_price(self):
        try:
            return .5 * (self.best_bid.price_val + self.best_ask.price_val)
        except(AttributeError):
            return None

    @property
    def prods_list(self):
        return self.__aux_dict['prods_list']

    @property
    def price_list(self):
        return self.__aux_dict['price_list']

    @property
    def check_list(self):
        return self.__aux_dict['prods_list'] + self.__aux_dict['price_list']

    @property
    def check_list_q(self):
        return ['timestamp_in', 'po_id'] + self.__aux_dict['price_list']

    @property
    def back_list(self):
        return self.check_list[1:]

    @property
    def time_string(self):
        return self.time_snapshot.strftime("%Y-%m-%d, %H:%M:%S")

    @property
    def verbose(self):
        return self.__verbose

    def print_err(self, msg, order):
        if self.verbose:
            print(msg, str(order))

    def next_iter(self):
        # Clear dictionary of changes
        self.diff_dict = {k: {o: [] for o in ['ins', 'del']}
                          for k in ['bid', 'ask']}


    """
    @property
    def volume_ask(self):
        # Cummulative volume series for Offers
        cols = ['volume', 'count']
        if not self.asks:
            vol_data = pd.DataFrame([], columns=cols, dtype=float)
            vol_data.index = vol_data.index.astype(float)
        else:
            price_list = [x.price_val for x in self.asks]
            volms_list = [x.volume for x in self.asks]
            count_list = [1.0] * len(self.asks)
            zip_list = list(zip(volms_list, count_list))
            vol_data = pd.DataFrame(zip_list, index=price_list, columns=cols)
            # Group by the price
            # vol_data = vol_data.groupby(level=0).sum()
        return vol_data
    """

    """
    @property
    def order_list(self):
        bids_list = [[x.price / 10000] * x.volume for x in self.bids]
        bids = [y for s in reversed(bids_list) for y in s]
        asks_list = [[x.price / 10000] * x.volume for x in self.asks]
        asks = [y for s in asks_list for y in s]
        return bids, asks
    """

    def price_vol_bid(self, volume):
        try:
            volume = min(sum([0 if x.is_iven else x.volume_val for x in self.bids]), volume)
            v = 0
            k = 0
            price_val = 0
            stop_bool = False
            while not stop_bool:
                if self.bids[k].is_iven:
                    k += 1
                    continue
                vol_bid = self.bids[k].volume_val
                if v + vol_bid >= volume:
                    vol_bid = volume - v
                    stop_bool = True
                price_val += self.bids[k].price_val * vol_bid
                v += vol_bid
                k += 1
            price_val /= v
        except(IndexError):
            price_val = np.nan
        return price_val

    def price_vol_ask(self, volume, firm_ven=True):
        try:
            if firm_ven:
                volume = min(sum([0 if x.is_iven else x.volume_val
                                  for x in self.asks]), volume)
            v = 0
            k = 0
            price_val = 0
            stop_bool = False
            while not stop_bool:
                if self.asks[k].is_iven and firm_ven:
                    k += 1
                    continue
                vol_bid = self.asks[k].volume_val
                if v + vol_bid >= volume:
                    vol_bid = volume - v
                    stop_bool = True
                price_val += self.asks[k].price_val * vol_bid
                v += vol_bid
                k += 1
            price_val /= v
        except(IndexError):
            price_val = np.nan
        return price_val

    def volume_bids(self, thres, firm_ven=True, aonn=False):
        # Returns list of touples price & volume
        if self.best_bid is None:
            out_dict = {}
        else:
            p_thres = self.best_bid.price_val - thres
            orders = [x for x in self.bids if x.price_val >= p_thres]
            price_list = [x.price_val for x in orders]
            volms_list = [x.volume_val for x in orders]
            ivens_list = [x.is_iven for x in orders]
            aon_list = [x.aon for x in orders]
            # out_dict = {k: v for k, v in zip(price_list, volms_list)}
            out_dict = {}
            for k, v, i, a in zip(price_list, volms_list, ivens_list, aon_list):
                if (i and firm_ven) or (a and aonn):
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def volume_asks(self, thres, firm_ven=True, aonn=False):
        # Returns list of touples price & volume
        if self.best_ask is None:
            out_dict = {}
        else:
            p_thres = self.best_ask.price_val + thres
            orders = [x for x in self.asks if x.price_val <= p_thres]
            price_list = [x.price_val for x in orders]
            volms_list = [x.volume_val for x in orders]
            ivens_list = [x.is_iven for x in orders]
            aon_list = [x.aon for x in orders]
            # out_dict = {k: v for k, v in zip(price_list, volms_list)}
            out_dict = {}
            for k, v, i, a in zip(price_list, volms_list, ivens_list, aon_list):
                if (i and firm_ven) or (a and aonn):
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def level_bids(self, num, ven_list=None, firm_ven=True, aonn=False):
        # Returns list of touples price & volume
        if self.best_ask is None:
            out_dict = {}
        else:
            if ven_list is None:
                ven_list = all_venues_list()
            aux_list = sorted(set([x.price_val for x in self.bids
                                   if x.venue in ven_list]), reverse=True)
            try:
                p_thres = aux_list[min(len(aux_list), num) - 1]
            except(IndexError):
                return {}
            orders = [x for x in self.bids
                      if (x.price_val >= p_thres) & (x.venue in ven_list)]
            price_list = [x.price_val for x in orders]
            volms_list = [x.volume_val for x in orders]
            ivens_list = [x.is_iven for x in orders]
            aon_list = [x.aon for x in orders]
            out_dict = {}
            for k, v, i, a in zip(price_list, volms_list, ivens_list, aon_list):
                if (i and firm_ven) or (a and aonn):
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def level_asks(self, num, ven_list=None, firm_ven=True, aonn=False):
        # Returns list of touples price & volume
        if self.best_ask is None:
            out_dict = {}
        else:
            if ven_list is None:
                ven_list = all_venues_list()
            aux_list = sorted(set([x.price_val for x in self.asks
                                   if x.venue in ven_list]), reverse=False)
            try:
                p_thres = aux_list[min(len(aux_list), num) - 1]
            except(IndexError):
                return {}
            orders = [x for x in self.asks
                      if (x.price_val <= p_thres) & (x.venue in ven_list)]
            price_list = [x.price_val for x in orders]
            volms_list = [x.volume_val for x in orders]
            ivens_list = [x.is_iven for x in orders]
            aon_list = [x.aon for x in orders]
            out_dict = {}
            for k, v, i, a in zip(price_list, volms_list, ivens_list, aon_list):
                if (i and firm_ven) or (a and aonn):
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def order_price_vol(self, side, thres):
        # Returns price of order by depth of volume
        if side == 'bid':
            orders = self.bids
        elif side == 'ask':
            orders = self.asks
        else:
            ValueError('Wrong side %s.' % side)
        ivens_list = [x.is_iven for x in orders]
        cum_vol = list(np.cumsum([x.volume_val for x in orders]))
        try:
            thres = [x for x in cum_vol if x >= thres][0]
        except(IndexError):
            pass
        orders_trunc = [x for x, v in zip(orders, cum_vol) if v <= thres]
        return orders_trunc[-1].price_val

    def change_bids(self, thres, act='ins', vol_bool=True):
        # Returns list of touples price & volume of the OB difference
        if not self.diff_dict['bid'][act]:
            out_dict = {}
        else:
            try:
                p_thres = self.best_bid.price_val - thres
            except(AttributeError):
                p_thres = -np.inf
            orders = [x for x in self.diff_dict['bid'][act]
                      if x.price_val >= p_thres]
            price_list = [x.price_val for x in orders]
            if vol_bool:
                volms_list = [x.volume_val for x in orders]
            else:
                volms_list = [1 for x in orders]
            ivens_list = [x.is_iven for x in orders]
            out_dict = {k: v for k, v in zip(price_list, volms_list)}
            out_dict = {}
            for k, v, i in zip(price_list, volms_list, ivens_list):
                if i:
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def change_asks(self, thres, act='ins', vol_bool=True):
        # Returns list of touples price & volume of the OB difference
        if not self.diff_dict['ask'][act]:
            out_dict = {}
        else:
            try:
                p_thres = self.best_ask.price_val + thres
            except(AttributeError):
                p_thres = np.inf
            orders = [x for x in self.diff_dict['ask'][act]
                      if x.price_val <= p_thres]
            price_list = [x.price_val for x in orders]
            if vol_bool:
                volms_list = [x.volume_val for x in orders]
            else:
                volms_list = [1 for x in orders]
            ivens_list = [x.is_iven for x in orders]
            out_dict = {k: v for k, v in zip(price_list, volms_list)}
            out_dict = {}
            for k, v, i in zip(price_list, volms_list, ivens_list):
                if i:
                    continue
                if k in out_dict.keys():
                    out_dict[k] += v
                else:
                    out_dict[k] = v
        return out_dict

    def truncate_old(self, thres_val=None):
        if thres_val is None:
            return 1
        try:
            thres_dict = {'bid': self.best_bid.price_val - thres_val,
                          'ask': self.best_ask.price_val + thres_val}
        except(AttributeError):
            return 0
        s = {'bid': 1, 'ask': -1}
        self.bids = [copy(x) for x in self.bids
                     if (x.price_val - thres_dict['bid']) * s['bid'] >= 0]
        self.asks = [copy(x) for x in self.asks
                     if (x.price_val - thres_dict['ask']) * s['ask'] >= 0]
        # newcopy.diff_dict.update(self.diff_dict)
        self.diff_dict = {k: {l: [copy(x) for x in self.diff_dict[k][l]
                                  if (x.price_val - thres_dict[k]) * s[k] >= 0]
                                 for l in ['ins', 'del']}
                             for k in ['bid', 'ask']}
        return 0

    def truncate_vol(self, thres_val=None):
        if thres_val is None:
            return False
        if not self.bids and not self.asks:
            return False
        try:
            b_t = self.best_bid.price_val - self.order_price_vol('bid', thres_val)
        except(AttributeError):
            b_t = 0.0
        try:
            a_t = self.order_price_vol('ask', thres_val) - self.best_ask.price_val
        except(AttributeError, IndexError):
            a_t = 0.0
        self.__truncate_bids(b_t)
        self.__truncate_asks(a_t)
        bool_array = [not self.diff_dict[k][l] for l in ['ins', 'del']
                      for k in ['bid', 'ask']]
        return all(bool_array)

    def truncate(self, thres_val=None):
        if thres_val is None:
            return False
        if not self.bids and not self.asks:
            return False
        self.__truncate_bids(thres_val)
        self.__truncate_asks(thres_val)
        bool_array = [not self.diff_dict[k][l] for l in ['ins', 'del']
                      for k in ['bid', 'ask']]
        return all(bool_array)

    def __truncate_bids(self, thres_val):
        try:
            p_thres = self.best_bid.price_val - thres_val
        except(AttributeError):
            p_thres = -np.inf
        self.bids = [copy(x) for x in self.bids if x.price_val >= p_thres]
        self.diff_dict['bid'] = {l: [copy(x) for x in self.diff_dict['bid'][l]
                                     if x.price_val >= p_thres]
                                 for l in ['ins', 'del']}
        return 0

    def __truncate_asks(self, thres_val):
        try:
            p_thres = self.best_ask.price_val + thres_val
        except(AttributeError):
            p_thres = np.inf
        self.asks = [copy(x) for x in self.asks if x.price_val <= p_thres]
        self.diff_dict['ask'] = {l: [copy(x) for x in self.diff_dict['ask'][l]
                                     if x.price_val <= p_thres]
                                 for l in ['ins', 'del']}
        return 0

    def _sanity_check(self, err_dict={}):
        errors = None
        try:
            threshold = self.best_bid_all.price_val - self.best_ask_all.price_val
        except(AttributeError):
            threshold = -np.inf

        # Delete order that violates order book construction
        if threshold > tres_const:
            # Determine whether to delete bid / ask
            bid_bool = self.check_errors(self.best_bid_all, err_dict)
            ask_bool = self.check_errors(self.best_ask_all, err_dict)
            # Patch for one order
            if len(self.bids) == 1:
                bid_diff = 0
            else:
                val_bids = np.mean(np.unique([x.price_val for x in self.bids[1:10]]))
                bid_diff = self.best_bid_all.price_val - val_bids
                del val_bids
            if len(self.asks) == 1:
                ask_diff = 0
            else:
                val_asks = np.mean(np.unique([x.price_val for x in self.asks[1:10]]))
                ask_diff = val_asks - self.best_ask_all.price_val
                del val_asks
            if bid_diff > ask_diff:
                ask_diff = 0
            elif bid_diff < ask_diff:
                bid_diff = 0
            else:
                ask_diff = 0
                bid_diff = 0
            # Delete incorrect order
            if bid_bool:
                # Delete best bid
                errors = self.best_bid_all
                self.__delete_bid(0)
            elif ask_bool:
                # Delete best ask
                errors = self.best_ask_all
                self.__delete_ask(0)
            elif bid_diff > tres_const:
                # Delete best bid
                errors = self.best_bid_all
                self.__delete_bid(0)
            elif ask_diff > tres_const:
                # Delete best ask
                errors = self.best_ask_all
                self.__delete_ask(0)
            else:
                pass
        else:
            pass
        return errors

    def check_errors(self, order, err_dict):
        # Returns True if order is en error dictionary
        bool_out = False
        po_id = str(order.po_id)
        # Check Removals
        try:
            list_rm = err_dict['remove'][po_id]
            time_rm = list_rm[-1].timestamp
        except(KeyError):
            list_rm = []
            time_rm = None
            return bool_out
        # Check Updates
        try:
            list_up = err_dict['update'][po_id]
            time_up = list_up[-1].timestamp
        except(KeyError):
            list_up = []
            time_up = None
        # Get error order
        try:
            if time_rm >= time_up:
                order_up = list_up[-1]
                order_rm = list_rm[-1]
                bool_out = all([order_up.cmp(order_rm, k)
                                for k in self.check_list[1:]])
                if bool_out:
                    bool_out = order.cmp(order_rm, self.check_list[0])
            else:
                bool_out = any([all([order.cmp(x, k) for k in
                                     self.check_list[0:]]) for x in list_rm])
        except(TypeError):
            bool_out = any([all([order.cmp(x, k) for k in
                                 self.check_list[0:]]) for x in list_rm])
        return bool_out

    def plot_order_book(self, tick=0.025):
        # Get Bid Orders list
        price_b = [x.price_val for x in self.bids]
        volms_b = [x.volume_val for x in self.bids]
        price_a = [x.price_val for x in self.asks]
        volms_a = [x.volume_val for x in self.asks]
        plt.bar(price_b, volms_b, width=tick, align='center', label='Bid')
        plt.bar(price_a, volms_a, width=tick, align='center', label='Ask')
        plt.ylabel('Volume')
        plt.xlabel('Price EUR')
        plt.title('Order book at %s' % self.time_string)
        plt.show()

    def __append_bid(self, order):
        if not self.bids:
            self.bids.append(order)
        else:
            reverse_insort(self.bids, order)
        self.diff_dict['bid']['ins'].append(order)

    def __append_ask(self, order):
        if not self.asks:
            self.asks.append(order)
        else:
            insort(self.asks, order)
        self.diff_dict['ask']['ins'].append(order)

    def __delete_bid(self, idx):
        if not self.diff_dict['bid']['del']:
            self.diff_dict['bid']['del'].append(copy(self.bids[idx]))
        else:
            reverse_insort(self.diff_dict['bid']['del'], copy(self.bids[idx]))
        del self.bids[idx]

    def __delete_ask(self, idx):
        if not self.diff_dict['ask']['del']:
            self.diff_dict['ask']['del'].append(copy(self.asks[idx]))
        else:
            insort(self.diff_dict['ask']['del'], copy(self.asks[idx]))
        del self.asks[idx]

    def __remove_orders(self):
        self.asks = []
        self.bids = []

    def get_order_index(self, idx, is_bid):
        if is_bid:
            return self.bids[idx]
        else:
            return self.asks[idx]

    def order_index(self, order):
        if order.is_bid:
            order_list = self.bids
        else:
            order_list = self.asks
        # If available, try to match by peristent_order_id
        if order.po_id != 0:
            field_name = 'po_id'
        else:
            field_name = 'o_id'
        idx_ord = [i for i, ords in enumerate(order_list)
                   if order.att(field_name) == ords.att(field_name)]
        return idx_ord

    def insert_order(self, order, order_nxt, order_list):
        # Outputs
        errors = None
        bool_skip = False
        # Check if order exists in OrderBook
        idx_ord = self.order_index(order)

        if len(idx_ord) > 1:
            msg = "Warning: trying to insert already existing id"
            # Filter from order list
            t_e = order.timestamp + time_shift
            idxL = bisect_left_order(order_list, t_e, 'timestamp')
            order_aux = [o for o in order_list[:idxL]
                         if order.cmp(o, 'po_id')]
            idxL = [i for i, o in enumerate(order_aux)
                    if all([order.cmp(o, k) for k in self.price_list])]
            try:
                # If no updates in time period add order
                bool_act = all([o.action in ['Insert', 'Remove']
                                for o in order_aux[:idxL[-1]]])
                if bool_act is True:
                    msg = "Warning: inserting already existing id"
                    self.print_err(msg, order)
                    self.__insert(order)
                    return errors, bool_skip
                else:
                    errors = order
                    self.print_err(msg, order)
                    # Update order with new parameters
                    self.__update(order, idx_ord[0])
                    return errors, bool_skip
            except(IndexError):
                errors = order
                self.print_err(msg, order)
                # Update order with new parameters
                self.__update(order, idx_ord[0])
                return errors, bool_skip
        elif len(idx_ord) == 1:
            # Check if it's a duplicate
            order_dup = self.get_order_index(idx_ord[0], order.is_bid)
            if all([order.cmp(order_dup, k) for k in self.check_list]):
                # Duplicates ignored
                return errors, bool_skip
            else:
                msg = "Warning: trying to insert already existing id"
                if order_nxt is None:
                    errors = order
                    self.print_err(msg, order)
                    # Update order with new parameters
                    self.__update(order, idx_ord[0])
                    return errors, bool_skip
                else:
                    pass
                # Patch for next order Remove
                if order_nxt.action in ['Remove'] and order.cmp(order_nxt, 'po_id'):
                    if all([order.cmp(order_nxt, k) for k in self.check_list_q]):
                        # Update Order and skip next Remove
                        bool_skip = False
                        msg = "Warning: inserting already existing id"
                        self.print_err(msg, order)
                        self.__insert(order)
                        # self.__update(order, idx_ord[0])
                        return errors, bool_skip
                    else:
                        errors = order
                        self.print_err(msg, order)
                        # Update order with new parameters
                        self.__update(order, idx_ord[0])
                        return errors, bool_skip
                elif order_nxt.action in ['Update'] and order.cmp(order_nxt, 'po_id'):
                    if all([order.cmp(order_nxt, k) for k in self.prods_list]):
                        # Skip Insert
                        return errors, bool_skip
                    else:
                        errors = order
                        self.print_err(msg, order)
                        # Update order with new parameters
                        self.__update(order, idx_ord[0])
                        return errors, bool_skip
                # Patch for next order Query
                elif order_nxt.action in ['Query']:
                    prods_list = ['timestamp_in', 'po_id']
                    if all([order.cmp(order_nxt, k) for k in prods_list]):
                        # Skip Insert
                        return errors, bool_skip
                    else:
                        errors = order
                        self.print_err(msg, order)
                        # Update order with new parameters
                        self.__update(order, idx_ord[0])
                        return errors, bool_skip
                else:
                    # Add another order #
                    # Filter from order list
                    t_e = order.timestamp + time_shift
                    idxL = bisect_left_order(order_list, t_e, 'timestamp')
                    order_aux = [o for o in order_list[:idxL]
                                 if order.cmp(o, 'po_id')]
                    idxL = [i for i, o in enumerate(order_aux)
                            if all([order.cmp(o, k) for k in self.price_list])]
                    try:
                        # If no updates in time period add order
                        bool_act = all([o.action in ['Insert', 'Remove']
                                        for o in order_aux[:idxL[-1] + 1]])
                        if bool_act is True:
                            msg = "Warning: inserting already existing id"
                            self.print_err(msg, order)
                            self.__insert(order)
                            return errors, bool_skip
                        else:
                            errors = order
                            self.print_err(msg, order)
                            # Update order with new parameters
                            self.__update(order, idx_ord[0])
                            return errors, bool_skip
                    except(IndexError):
                        errors = order
                        self.print_err(msg, order)
                        # Update order with new parameters
                        self.__update(order, idx_ord[0])
                        return errors, bool_skip
        else:
            # Insert Order
            self.__insert(order)
            return errors, bool_skip

    def update_order(self, order, order_nxt):
        # Outputs
        errors = None
        bool_skip = False
        # Check if order exists in OrderBook
        idx_ord = self.order_index(order)

        if len(idx_ord) == 0:
            # Could not find order to update
            msg = "Warning: trying to update non-existing id"
            # Patch if Update precedes Insert
            if order_nxt is None:
                errors = order
                self.print_err(msg, order)
                return errors, bool_skip
            else:
                pass
            if order_nxt.action in ['Insert']:
                if all([order.cmp(order_nxt, k) for k in self.prods_list]):
                    # Do Insert with Update parameters
                    bool_skip = True
                    self.__insert(order)
                    return errors, bool_skip
                else:
                    errors = order
                    self.print_err(msg, order)
                    return errors, bool_skip
            else:
                errors = order
                self.print_err(msg, order)
                return errors, bool_skip
        elif len(idx_ord) > 1:
            msg = ("OrderBook/Update: Order_id or persistent_order_id " +
                   "must be unique within current_state ")
            raise ValueError(msg, str(order))
        else:
            # Update order
            self.__update(order, idx_ord[0])
            return errors, bool_skip

    def remove_order(self, order, order_nxt):
        # Outputs
        errors = None
        bool_skip = False
        # Check if order exists in OrderBook
        idx_ord = self.order_index(order)

        if len(idx_ord) == 0:
            msg = "Warning: trying to delete non-existing id"
            # Patch if next order is Insert
            if order_nxt is None:
                errors = order
                self.print_err(msg, order)
                return errors, bool_skip
            else:
                pass
            if order_nxt.action in ['Insert']:
                if all([order.cmp(order_nxt, k) for k in self.check_list_q]):
                    # Skip next insert
                    bool_skip = True
                    return errors, bool_skip
                else:
                    errors = order
                    self.print_err(msg, order)
                    return errors, bool_skip
            else:
                errors = order
                self.print_err(msg, order)
                return errors, bool_skip
        elif len(idx_ord) > 1:
            msg = ("OrderBook/Remove: Order_id or persistent_order_id" +
                   "must be unique within current_state")
            # Remove Order
            order_ls = [self.get_order_index(i, order.is_bid) for i in idx_ord]
            idx_l = [i for i, o in enumerate(order_ls)
                     if all([order.cmp(o, k) for k in self.price_list])]
            try:
                self.__remove(order, idx_ord[idx_l[0]])
                return errors, bool_skip
            except(IndexError):
                msg = "Warning: trying to delete non-existing id"
                errors = order
                self.print_err(msg, order)
                return errors, bool_skip
        else:
            msg = "Warning: Remove order incorrect attributes "
            if order_nxt is None:
                order_nxt = order
            else:
                pass
            # Patch for following Query Order
            if order_nxt.action in ['Query']:
                prods_list = ['timestamp_in', 'po_id']
                if all([order.cmp(order_nxt, k) for k in prods_list]):
                    # Do NOT Delete Order
                    return errors, bool_skip
                else:
                    # Remove Order
                    self.__remove(order, idx_ord[0])
                    return errors, bool_skip
            else:
                order_rem = self.get_order_index(idx_ord[0], order.is_bid)
                if all([order.cmp(order_rem, k) for k in self.price_list]):
                    # Remove Order
                    self.__remove(order, idx_ord[0])
                    return errors, bool_skip
                else:
                    if order_nxt.action in ['Update']:
                        if all([order.cmp(order_nxt, k) for k in self.check_list_q]):
                            # Delete Order and skip Update
                            bool_skip = True
                            self.__remove(order, idx_ord[0])
                            return errors, bool_skip
                        else:
                            errors = order
                            self.print_err(msg, order)
                            return errors, bool_skip
                    else:
                        errors = order
                        self.print_err(msg, order)
                        return errors, bool_skip

    def query_order(self, order, order_nxt, order_prv):
        # Outputs
        errors = None
        bool_skip = False

        # Check if the next event the query has the same timestamp
        try:
            if order_nxt.action in ['Update', 'Remove']:
                if all([order.cmp(order_nxt, k) for k in self.check_list_q]):
                    bool_skip = True
                    return errors, bool_skip
            elif order_nxt.action in ['Insert']:
                if all([order.cmp(order_nxt, k) for k in self.check_list_q]):
                    return errors, bool_skip
        except(AttributeError):
            pass

        # Check if the next event the query has the same timestamp
        try:
            if order_prv.action in ['Update', 'Insert', 'Remove']:
                if all([order.cmp(order_prv, k) for k in self.check_list_q]):
                    return errors, bool_skip
        except(AttributeError):
            pass

        # Test if it's an update
        idx_ord = self.order_index(order)
        if len(idx_ord) < 1:
            msg = "Warning: Inserting Query order "
            errors = order
            self.print_err(msg, order)
            # self.__insert(order)
            return errors, bool_skip
        elif len(idx_ord) == 1:
            self.__update(order, idx_ord[0])
            return errors, bool_skip
        else:
            msg = "Warning: Query order incorrect attributes "
            errors = order
            self.print_err(msg, order)
            return errors, bool_skip

    def conn_lost(self):
        self.__remove_orders()

    def __insert(self, order):
        if order.is_bid:
            self.__append_bid(order)
        else:
            self.__append_ask(order)
        # Set Time of Snapshot
        self.time_snapshot = order.timestamp

    def __update(self, order, index):
        timestamp = order.timestamp
        price = order.price
        volume = order.volume
        if order.is_bid:
            order_up = self.bids[index]
            # del self.bids[index]
            self.__delete_bid(index)
            order_up.update_order(timestamp, price, volume)
            self.__append_bid(order_up)
        else:
            order_up = self.asks[index]
            # del self.asks[index]
            self.__delete_ask(index)
            order_up.update_order(timestamp, price, volume)
            self.__append_ask(order_up)
        # Set Time of Snapshot
        self.time_snapshot = timestamp

    def __remove(self, order, index):
        timestamp = order.timestamp
        if order.is_bid:
            self.__delete_bid(index)
        else:
            self.__delete_ask(index)
        # Set Time of Snapshot
        self.time_snapshot = timestamp


class OrderSim:
    def __init__(self, order):
        self.price = order.price
        self.volume = order.volume_val
        self.venue = order.venue
        self.imp_ven = order.is_iven
        self.__aon = order.aon

    @property
    def aon(self):
        try:
            return self.__aon
        except(AttributeError):
            return False

    @property
    def price_val(self):
        return self.price

    @property
    def volume_val(self):
        return self.volume

    @property
    def is_iven(self):
        try:
            iven = self.imp_ven
        except(AttributeError):
            iven = False
        return iven

    def __eq__(self, other):
        price_bool = self.price_val == other.price_val
        volume_bool = self.volume_val == other.volume_val
        venue_bool = self.venue == other.venue
        return price_bool and volume_bool and venue_bool

    def __repr__(self):
        if self.is_iven:
            status = 'Implied(Venue)'
        else:
            status = 'Firm'
        if self.aon:
            aon = 'AoN'
        else:
            aon = 'Any'
        return str((self.price_val, self.volume_val, venue_dict(self.venue),
                    aon, status))

    @property
    def venue_val(self):
        return venue_dict(self.venue)


class Order:
    def __init__(self, price, volume, side, po_id, action=None,
                 timestamp=None, status=1, imp_type='None', venue=-1,
                 owner=False, aon=False, price_level=1):
        self.price = price
        self.volume = volume
        self.is_bid = side == 2
        self.is_firm = status == 1
        self.is_iven = imp_type == 'Venue'
        self.is_query = action == 4
        self.po_id = po_id
        self.venue = venue
        self.owner = owner
        self.aon = aon
        if timestamp is None:
            self.timestamp_in = dt.datetime.now()
        else:
            self.timestamp_in = timestamp
        # Other attributes
        self.timestamp_up = None
        self.no_updates = 0

        self.__action = action
        self.__price_level = price_level
        if self.venue in [1441]:
            self.__agg_venue = True
        else:
            self.__agg_venue = False

    @classmethod
    def from_tp_dict(cls, data_dict, side_code):
        if side_code == 'bid':
            side = 2
        else:
            side = 1
        price = data_dict['price']
        volume = data_dict['quantity']
        venue = venue_code_dict(data_dict['venueCode'])
        return Order(price, volume, side, '', venue=venue)

    @property
    def timestamp(self):
        timestamp = None
        if self.timestamp_up is None:
            timestamp = self.timestamp_in
        else:
            timestamp = self.timestamp_up
        return timestamp

    @property
    def price_val(self):
        return self.price / self.__price_level

    @property
    def volume_val(self):
        if self.__agg_venue and self.owner:
            return 0
        else:
            return self.volume

    @property
    def venue_val(self):
        return venue_dict(self.venue)

    @property
    def side_dict(self):
        side_dict = {}
        side_dict[1] = 'Ask'
        side_dict[2] = 'Bid'
        return side_dict

    @property
    def action_dict(self):
        action_dict = {}
        action_dict['Remove'] = 1
        action_dict['Insert'] = 2
        action_dict['Update'] = 3
        action_dict['Query'] = 4
        action_dict['Delete_All'] = 0
        return action_dict

    @property
    def action(self):
        return self.__action

    @property
    def agg_venue(self):
        return self.__agg_venue

    @property
    def export(self):
        return OrderSim(self)

    def att(self, field_name):
        return getattr(self, field_name)

    def cmp(self, other, field_name):
        return self.att(field_name) == other.att(field_name)

    def update_order(self, timestamp, price_new, volume_new):
        self.price = price_new
        self.volume = volume_new
        self.timestamp_up = timestamp
        self.no_updates += 1

    def __copy__(self):
        price = self.price
        volume = self.volume
        if self.is_bid:
            order_type = 2
        else:
            order_type = 1
        po_id = self.po_id
        if self.is_firm:
            status = 'Firm'
        else:
            status = 'Implied'
        if self.is_iven:
            imp_type = 'Venue'
        else:
            imp_type = 'None'
        action = self.action
        timestamp = self.timestamp_in
        price_level = self.__price_level
        venue = self.venue
        owner = self.owner
        aon = self.aon
        newcopy = Order(price, volume, order_type, po_id, action, timestamp,
                        status, imp_type, venue, owner, aon, price_level)
        newcopy.timestamp_up = self.timestamp_up
        newcopy.no_updates = self.no_updates
        return newcopy

    def __eq__(self, other):
        price_bool = self.price_val == other.price_val
        volume_bool = self.volume_val == other.volume_val
        venue_bool = self.venue == other.venue
        return price_bool and volume_bool and venue_bool

    def __str__(self):
        if self.is_bid:
            side = 'Bid'
        else:
            side = 'Ask'
        timestamp_str = self.timestamp.strftime("%Y-%m-%d, %H:%M:%S.%f")
        return str((timestamp_str, side, self.po_id))

    def __repr__(self):
        if self.is_bid:
            side = 'Bid'
        else:
            side = 'Ask'
        if self.is_iven:
            status = 'Implied(Venue)'
        elif self.is_firm:
            status = 'Firm'
        else:
            status = 'None'
        if self.aon:
            aon = 'AoN'
        else:
            aon = 'Any'
        timestamp_str = self.timestamp.strftime("%Y-%m-%d, %H:%M:%S.%f")
        return str((timestamp_str, self.price_val, self.volume, side,
                    venue_dict(self.venue), self.owner, aon, status))

    def __lt__(self, other):
        return [self.price, self.timestamp] < [other.price, other.timestamp]

    def __le__(self, other):
        return [self.price, self.timestamp] <= [other.price, other.timestamp]

    def __gt__(self, other):
        return [self.price, other.timestamp] > [other.price, self.timestamp]

    def __ge__(self, other):
        return [self.price, other.timestamp] >= [other.price, self.timestamp]


def reverse_insort(a, x, lo=0, hi=None):
    """Insert item x in list a, and keep it reverse-sorted assuming a
    is reverse-sorted.

    If x is already in a, insert it to the right of the rightmost x.

    Optional args lo (default 0) and hi (default len(a)) bound the
    slice of a to be searched.
    """
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo+hi)//2
        if x > a[mid]:
            hi = mid
        else:
            lo = mid+1
    a.insert(lo, x)


def bisect_left_order(order_list, x, a, lo=0, hi=None):
    """Return the index where to insert item x in list a, assuming a is sorted.

    The return value i is such that all e in a[:i] have e < x, and all e in
    a[i:] have e >= x.  So if x already appears in the list, a.insert(x) will
    insert just before the leftmost x already there.

    Optional args lo (default 0) and hi (default len(a)) bound the
    slice of a to be searched.
    """

    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(order_list)
    while lo < hi:
        mid = (lo+hi)//2
        if order_list[mid].att(a) < x:
            lo = mid+1
        else:
            hi = mid
    return lo


def order_from_dict(order_dict):
    price = order_dict['price']
    volume = order_dict['volume']
    order_type = order_dict['side']
    po_id = order_dict['persistentorderid']
    action = order_dict['action']
    timestamp = order_dict['datetime']
    status = order_dict['status']
    imp_type = order_dict['impliedtype']
    owner = order_dict['companyid'] == 220
    venue = order_dict['brokerid']
    aon = order_dict['allornone'] == 1
    return Order(price, volume, order_type, po_id, action=action,
                 timestamp=timestamp, status=status, imp_type=imp_type,
                 venue=venue, owner=owner, aon=aon, price_level=1)


def venue_dict(venue_code):
    v_dict = {}
    v_dict[20] = 'EEX'
    v_dict[1441] = 'EEX'
    v_dict[28] = 'NASDAQ'
    v_dict[30] = 'ICE'
    v_dict[228] = 'CME'
    v_dict[7] = 'TFS'
    v_dict[2] = 'GFI'
    v_dict[5] = 'SPEC'
    v_dict[8] = '42FS'
    v_dict[3] = 'GRFN'
    v_dict[10] = 'BGC'
    try:
        venue = v_dict[venue_code]
    except(KeyError):
        venue = 'OTC'
    return venue


def action_dict():
    action_dict = {}
    action_dict['Remove'] = 1
    action_dict['Insert'] = 2
    action_dict['Update'] = 3
    action_dict['Query'] = 4
    action_dict['Delete_All'] = 0
    return action_dict


def side_dict():
    side_dict = {}
    side_dict[1] = 'Ask'
    side_dict[2] = 'Bid'
    return side_dict


def venue_code_dict(venue):
    my_dict = {}
    my_dict['EEX'] = 1441
    my_dict['GFI'] = 2
    my_dict['TFS'] = 7
    my_dict['42FS'] = 8
    my_dict['ICAP'] = 6
    my_dict['EEX7'] = 1441
    my_dict['SPEC'] = 5
    my_dict['GRFN'] = 3
    my_dict['BGC'] = 10
    return my_dict[venue]


def all_venues_list():
    v_dict = {}
    v_dict[20] = 'EEX'
    v_dict[1441] = 'EEX'
    v_dict[28] = 'NASDAQ'
    v_dict[30] = 'ICE'
    v_dict[228] = 'CME'
    v_dict[7] = 'TFS'
    v_dict[2] = 'GFI'
    v_dict[5] = 'SPEC'
    v_dict[8] = '42FS'
    v_dict[3] = 'GRFN'
    v_dict[10] = 'BGC'
    return list(v_dict.keys())
