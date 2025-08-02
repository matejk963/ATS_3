# -*- coding: utf-8 -*-
"""
Created on Thu Apr  4 10:58:23 2024

@author: Marek
"""

import numpy as np
import pandas as pd
import abc
from Math.accumfeatures import DifferentialEMA, EMA, MA, MSTD, DerivativeEMA
from Math.tickclass import tick_class
from Math.ti_class import TI_class, TR_class
from bisect import bisect_left
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from scipy.stats import norm


class Attributes():
    __metaclass__ = abc.ABCMeta
    def __init__(self, feature_list, price_tick, vol_tick, verbose):
        self.feature_list = feature_list
        self.price_tick = price_tick
        self.vol_tick = vol_tick
        self.verbose = verbose

    @staticmethod
    def cloud_diff(mkt_str, pma_list, series_roll_mw):
        """
        Computes the logarithmic difference between pairs of rolling series 
        specified in `pma_list` and returns a dictionary of these differences.

        Args:
            mkt_str (str): A market string used as a prefix for feature names.
            pma_list (list of int): A list of periods for which rolling series 
                are computed. Each period is used to generate keys for the 
                `series_roll_mw` dictionary.
            series_roll_mw (dict): A dictionary where keys are strings 
                representing periods (e.g., '02', '05') and values are 
                corresponding rolling series.

        Returns:
            dict: A dictionary where keys are feature names constructed using 
            `mkt_str` and the periods from `pma_list`, and values are the 
            logarithmic differences between the rolling series for each pair 
            of periods.
        """
        variable_dict = {}
        for j, period1 in enumerate(pma_list):
            nS1 = '{:02}'.format(period1)
            for period2 in pma_list[j + 1:]:
                nS2 = '{:02}'.format(period2)
                f_str = mkt_str + '_' + nS1 + '_' + nS2
                feature = 'diff_mw' + f_str
                variable_dict[feature] = np.log(series_roll_mw[nS1] /
                                                series_roll_mw[nS2])
        return variable_dict

    @classmethod
    def unify_timestamp(cls, data_dict, gran, timestamp=None):
        for data_df in data_dict.values():
            ts_aux = data_df.index
            if gran is not None:
                ts_aux = ts_aux.resample(gran)
            if timestamp is None:
                timestamp = ts_aux
            else:
                timestamp = timestamp.union(ts_aux)
        # Drop duplicates
        timestamp = timestamp[~timestamp.duplicated(keep='first')]
        return timestamp


class OB_attributes(Attributes):
    def __init__(self, feature_list, price_tick=0.01, vol_tick=1, verbose=True):
        super().__init__(feature_list, price_tick, vol_tick, verbose)

    @classmethod
    def attr_list(cls, types=None):
        sp_list = ['sparsity', 'bid_sparsity', 'ask_sparsity']
        sp_list = ['sparsity']
        ob_list = ['ba_volrat', 'mid_priceW_d', 'diff_am_wm', 'diff_ema_am_wm', 'diff_ema_ba_mba']
        mv_list = ['delta_a', 'delta_b', 'delta_mid', 'delta_mw', 'delta_ba']
        mc_list = ['diff_mw', 'rat_mkt_mw']
        basic_list = ['b_price', 'a_price', 'b_vol', 'a_vol', 'ba_spread']
        all_attr_list = sp_list + ob_list + mv_list + mc_list + basic_list
        if types is None:
            return all_attr_list
        elif types == 'sparse':
            return sp_list
        elif types == 'ob':
            return ob_list
        elif types == 'mov':
            return mc_list
        elif types == 'cross':
            return mc_list
        else:
            raise ValueError('OB: Unknown type of regressor %s' % types)

    def mid_price(self, ob_class):
        return .5 * (self.bid_price(ob_class) + self.ask_price(ob_class))

    def ba_spread(self, ob_class):
        return self.ask_price(ob_class) - self.bid_price(ob_class)

    @staticmethod
    def bid_price(ob_class):
        try:
            return ob_class.best_bid_all.price_val
        except(AttributeError):
            return np.nan

    @staticmethod
    def ask_price(ob_class):
        try:
            return ob_class.best_ask_all.price_val
        except(AttributeError):
            return np.nan

    
    @staticmethod
    def bid_volume(ob_class):
        try:
            return ob_class.best_bid_all.volume_val
        except(AttributeError):
            return np.nan

    @staticmethod
    def ask_volume(ob_class):
        try:
            return ob_class.best_ask_all.volume_val
        except(AttributeError):
            return np.nan
        
    
    @staticmethod
    def bid_broker(ob_class):
        try:
            return ob_class.best_bid_all.venue_val
        except(AttributeError):
            return np.nan

    @staticmethod
    def ask_broker(ob_class):
        try:
            return ob_class.best_ask_all.venue_val
        except(AttributeError):
            return np.nan

    def bid_volumeV(self, ob_class, ord_list, p_depth):
        b_price = self.bid_price(ob_class)
        return sum([v for p, v in ord_list.items() if p >= b_price - p_depth])

    def ask_volumeV(self, ob_class, ord_list, p_depth):
        a_price = self.ask_price(ob_class)
        return sum([v for p, v in ord_list.items() if p <= a_price + p_depth])

    def bid_volumeP(self, ord_list, v_depth):
        vol = 0
        pW = 0
        for p, v in ord_list.items():
            if vol + v < v_depth:
                pW += p * v
                vol += v
            else:
                v_r = v_depth - vol
                pW += p * v_r
                break
        return pW / v_depth

    def ask_volumeP(self, ord_list, v_depth):
        vol = 0
        pW = 0
        for p, v in ord_list.items():
            if vol + v < v_depth:
                pW += p * v
                vol += v
            else:
                v_r = v_depth - vol
                pW += p * v_r
                break
        return pW / v_depth

    def mid_priceW(self, ob_class, ord_list_b, ord_list_a, p_depth):
        b_price = self.bid_price(ob_class)
        a_price = self.ask_price(ob_class)
        bid_vol = self.bid_volumeV(ob_class, ord_list_b, p_depth)
        ask_vol = self.ask_volumeV(ob_class, ord_list_a, p_depth)
        tot_vol = bid_vol + ask_vol
        if bid_vol * ask_vol == 0:
            return np.nan
        else:
            return (sum([p * v for p, v in ord_list_b.items()
                         if p >= b_price - p_depth]) +
                    sum([p * v for p, v in ord_list_a.items()
                         if p <= a_price + p_depth])) / tot_vol

    def vol_ratio(self, ob_class, ord_list_b, ord_list_a, p_depth):
        bid_vol = self.bid_volumeV(ob_class, ord_list_b, p_depth)
        ask_vol = self.ask_volumeV(ob_class, ord_list_a, p_depth)
        tot_vol = bid_vol + ask_vol
        if tot_vol == 0:
            return np.nan
        else:
            return (bid_vol - ask_vol) / tot_vol
        
    def sparsity_func(self, order_book): # 
        _MIN_N_ORDERS = 4
        diff = pd.Series(order_book).diff(1).shift(-1).dropna()
        length = len(diff)
        if length < _MIN_N_ORDERS:
            return 2.0
        
        sum_w_diff = []
        manual_kernel = [2, 1.5, 1.25, 1, 1]
        kernel_list =  pd.Series(manual_kernel)/2

        # Calculate weighted differences
        sum_w_diff = 0
        for i in range(min(4, length)):  # To handle cases where length is less than 5
            sum_w_diff += kernel_list[i] * abs(diff[i])

        return min(round(sum_w_diff, 2), 1)

    def bid_sparsity(self, ord_list, p_depth, price_tick=.01):
        b_vals = np.array(list(ord_list.keys()))
        b_price = b_vals[0]
        price_levels = np.arange(b_price - p_depth, b_price + price_tick - 1e-5, price_tick)
        price_levels = np.round(price_levels / 0.005) * 0.005
        
        # Using numpy's broadcasting and vectorized operations
        pix_list = np.any((b_vals[:, None] >= price_levels[:-1]) & (b_vals[:, None] < price_levels[1:]), axis=0)
        
        if len(pix_list) == 0:
            return np.nan
        else:
            return np.sum(pix_list) / len(pix_list)

    def ask_sparsity(self, ord_list, p_depth, price_tick=.01):
        a_vals = np.array(list(ord_list.keys()))
        a_price = a_vals[0]
        price_levels = np.arange(a_price, a_price + p_depth + price_tick - 1e-5, price_tick)
        price_levels = np.round(price_levels / 0.005) * 0.005
        
        # Using numpy's broadcasting and vectorized operations
        pix_list = np.any((a_vals[:, None] >= price_levels[:-1]) & (a_vals[:, None] < price_levels[1:]), axis=0)
        
        if len(pix_list) == 0:
            return np.nan
        else:
            return np.sum(pix_list) / len(pix_list)

    # def bid_sparsity_old(self, ord_list, p_depth, price_tick=.01):
    #     b_vals = [p for p in ord_list.keys()]
    #     b_price = b_vals[0]
    #     price_levels = np.arange(b_price - p_depth, b_price + price_tick, price_tick)
    #     # Using numpy's broadcasting and vectorized operations
    #     pix_list = np.any((b_vals[:, None] >= price_levels[:-1]) & (b_vals[:, None] < price_levels[1:]), axis=0)
    #     if len(pix_list) == 0:
    #         return np.nan
    #     else:
    #         return np.sum(pix_list) / len(pix_list)

    # def ask_sparsity_old(self, ord_list, p_depth, price_tick=.01):
    #     a_vals = [p for p in ord_list.keys()]
    #     a_price = a_vals[0]
    #     price_levels = np.arange(a_price, a_price + p_depth, price_tick)
    #     price_levels = np.append(price_levels, a_price + p_depth)
    #     pix_list = [np.any((a_vals >= x) & (a_vals < y))
    #                 for x, y in zip(price_levels[:-1], price_levels[1:])]
    #     if len(pix_list) == 0:
    #         return np.nan
    #     else:
    #         return sum(pix_list) / len(pix_list)
        

    def prepare_ob_data_basic(self, LoB_dict, depth_price):
        depth_list = [int(x) * 100 for x in depth_price]
        variable_dict = {k: [] for k in ['timestamp', 'b_price', 'a_price', 'b_vol', 'a_vol', 'mid_price', 'b_price_sparsity', 'a_price_sparsity']}
        price_tick = self.price_tick

        for LoB_ in LoB_dict.values():
            LoB = LoB_.filter_aonnimpl()
            # Time variables
            t = LoB.time_snapshot
            variable_dict['timestamp'].append(t)
            # Order book parameters
            b_price = self.bid_price(LoB)
            a_price = self.ask_price(LoB)
            b_vol, a_vol = self.bid_volume(LoB), self.ask_volume(LoB)
            mid = self.mid_price(LoB)

            # orders
            asks = sum([[x.price] for x in LoB.asks], [])
            bids = sum([[x.price] for x in LoB.bids], [])
            # Populate price related variables
            variable_dict['b_price'].append(b_price)
            variable_dict['a_price'].append(a_price)
            variable_dict['mid_price'].append(mid)

            # no depth features
            # feature = 'sparsity'
            # if feature in self.feature_list:
            b, a = self.sparsity_func(bids), self.sparsity_func(asks)
            variable_dict['b_price_sparsity'].append(b)
            variable_dict['a_price_sparsity'].append(a)
            variable_dict['b_vol'].append(b_vol)
            variable_dict['a_vol'].append(a_vol)

        return variable_dict

    def prepare_ob_data(self, LoB_dict, depth_price, price_tick=None, aonn=False):
        depth_list = [int(x * 100) for x in depth_price]
        if price_tick is None:
            price_tick = self.price_tick
        # Flag target variable & fill regressors
        var_list = ['timestamp', 'ba_spread', 'b_price', 'a_price',
                    'mid_price', 'b_vol', 'a_vol']
        var_list.extend(['mid_priceW' + '_' + '{:02}'.format(x) for x in depth_list])
        # Extend for bid/ask volume ratios
        feature = 'ba_volrat'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list])
        # Extend for volume weighted mid prices
        feature = 'mid_priceW_d'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list])
        feature = 'bid_sparsity'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list if x > price_tick])
        feature = 'ask_sparsity'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list if x > price_tick])


        # features without depth
        feature = 'sparsity'
        if feature in self.feature_list:
            var_list.extend(['b_price_sparsity', 'a_price_sparsity'])

        # aux vars
        last_mid = None
        #
        variable_dict = {k: [] for k in var_list}
        for LoB_ in LoB_dict.values():
            if aonn:
                LoB = LoB_.filter_aonnimpl()
            else:
                LoB = LoB_
                
            # Time variables
            t = LoB.time_snapshot
            variable_dict['timestamp'].append(t)
            # Order book parameters
            b_price = self.bid_price(LoB)
            a_price = self.ask_price(LoB)
            b_vol, a_vol = self.bid_volume(LoB), self.ask_volume(LoB)
            mid = self.mid_price(LoB)
            data_volB = LoB.volume_bids(depth_price[-1], firm_ven=False)
            data_volA = LoB.volume_asks(depth_price[-1], firm_ven=False)
            # orders
            asks = sum([[x.price] for x in LoB.asks], [])
            bids = sum([[x.price] for x in LoB.bids], [])
            # Populate price related variables
            variable_dict['b_price'].append(b_price)
            variable_dict['a_price'].append(a_price)
            variable_dict['mid_price'].append(mid)
            variable_dict['b_vol'].append(b_vol)
            variable_dict['a_vol'].append(a_vol)

            for depth, d_p in zip(depth_list, depth_price):
                # Populate volume related variables
                depth_str = '{:02}'.format(depth)
                # Weighted mid price
                price_w = self.mid_priceW(LoB, data_volB, data_volA, d_p)
                feature = 'mid_priceW'
                variable_dict[feature + '_' + depth_str].append(price_w)
                # Other features
                feature = 'ba_volrat'
                if feature in self.feature_list:
                    ba_volrat = self.vol_ratio(LoB, data_volB, data_volA, d_p)
                    variable_dict[feature + '_' + depth_str].append(ba_volrat)
                feature = 'mid_priceW_d'
                if feature in self.feature_list:
                    price_w = self.mid_priceW(LoB, data_volB, data_volA, d_p)
                    variable_dict[feature + '_' + depth_str].append(price_w - mid)
                feature = 'bid_sparsity'
                if feature in self.feature_list and d_p > price_tick:
                    bid_sp = self.bid_sparsity(data_volB, d_p, price_tick)
                    variable_dict[feature + '_' + depth_str].append(bid_sp)
                feature = 'ask_sparsity'
                if feature in self.feature_list and d_p > price_tick:
                    ask_sp = self.ask_sparsity(data_volA, d_p, price_tick)
                    variable_dict[feature + '_' + depth_str].append(ask_sp)


            # no depth features
            feature = 'sparsity'
            if feature in self.feature_list:
                b, a = self.sparsity_func(bids), self.sparsity_func(asks)
                variable_dict['b_price_sparsity'].append(b)
                variable_dict['a_price_sparsity'].append(a)

            last_mid = mid


        # Clean data
        variable_dict = self.clean_data(variable_dict, 'b_price', 'a_price',
                                        'mid_price', 'ba_spread')
        return variable_dict

    def prepare_reg_data_mkt(self, data_dict, timestamp, idx, p_list, d_list,
                             gran=None, ts_data=None, keep_ts=False):
        depth_list = [int(x * 100) for x in d_list]
        ### Prepare raw data ###
        data_raw = pd.DataFrame(data_dict)
        data_raw.set_index(keys='timestamp', inplace=True)
        data_raw = data_raw.dropna()
        data_raw = data_raw.sort_index()
        if ts_data is None:
            ts_data = data_raw.index
        data_raw = unify_time_pd(data_raw, ts_data)
        if not keep_ts:
            sum_list_all = []
            sum_list = [x for x in data_dict.keys() if x in sum_list_all]
            snp_list = [x for x in data_dict.keys() if x not in sum_list]
            snp_list.remove('timestamp')
            if gran is not None:
                data_snp = data_raw.loc[:, snp_list].resample(gran).ffill()
            else:
                data_snp = data_raw.loc[:, snp_list]
            idx_m = unify_time(timestamp, idx, data_snp.index)
            data_snp = group_index(data_snp, idx_m, 'mean')
            if not sum_list:
                data_pro = data_snp
            else:
                if gran is not None:
                    data_sum = data_raw.loc[:, sum_list].resample(gran).sum()
                else:
                    data_sum = data_raw.loc[:, sum_list]
                data_sum = group_index(data_sum, idx_m, 'sum')
                data_pro = pd.concat([data_snp, data_sum], axis=1)
                data_pro = data_pro.dropna()
                del data_sum
            del data_snp
        else:
            data_pro = data_raw.copy()
        ### Prepare regressors ###
        var_list = []
        # Time related
        feature = 'delta_a'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in p_list])
        feature = 'delta_b'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in p_list])
        feature = 'delta_mid'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in p_list])
        feature = 'delta_ba'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in p_list])
        # Depth related
        feature = 'ba_volrat'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list])
        feature = 'diff_am_wm'
        if feature in self.feature_list:
            var_list.extend([feature + '_' + '{:02}'.format(x) for x in depth_list])
        # Combined time & depth
        feature = 'delta_mw'
        if feature in self.feature_list:
            for period in p_list:
                nS = '{:02}'.format(period)
                for depth in depth_list:
                    d_s = '{:02}'.format(depth)
                    ndS = d_s + '_' + nS
                    var_list.append(feature + '_' + ndS)
                    
        # features without depth
        feature = 'sparsity'
        if feature in self.feature_list:
            var_list.extend(['b_price_sparsity', 'a_price_sparsity'])
        feature = 'b_price'
        if feature in self.feature_list:
            var_list.extend(['b_price'])
        feature = 'a_price'
        if feature in self.feature_list:
            var_list.extend(['a_price'])
        feature = 'ba_spread'
        if feature in self.feature_list:
            var_list.extend(['ba_spread'])
        # Calculate features
        variable_dict = {k: [] for k in var_list}
        ### Calculate regressors ###
        # Time related
        for period in p_list:
            nS = '{:02}'.format(period)
            feature = 'delta_a'
            if feature in self.feature_list:
                clmn = 'a_price'
                variable_dict[feature + '_' + nS] = diff(data_pro.loc[:, clmn], period, True)
            feature = 'delta_b'
            if feature in self.feature_list:
                clmn = 'b_price'
                variable_dict[feature + '_' + nS] = diff(data_pro.loc[:, clmn], period, True)
            feature = 'delta_mid'
            if feature in self.feature_list:
                clmn = 'mid_price'
                variable_dict[feature + '_' + nS] = diff(data_pro.loc[:, clmn], period, True)
            feature = 'delta_ba'
            if feature in self.feature_list:
                clmn = 'ba_spread'
                variable_dict[feature + '_' + nS] = diff(data_pro.loc[:, clmn], period, False)
            # Combined
            for depth in depth_list:
                d_s = '{:02}'.format(depth)
                ndS = d_s + '_' + nS
                feature = 'delta_mw'
                if feature in self.feature_list:
                    clmn = 'mid_priceW_' + d_s
                    variable_dict[feature + '_' + ndS] = diff(data_pro.loc[:, clmn], period, True)
        # Depth related
        clmn = 'mid_price'
        mid_price = data_pro.loc[:, clmn]
        mid_priceS = ema(data_pro.loc[:, clmn], p_list[-1])
        for depth in depth_list:
            d_s = '{:02}'.format(depth)
            feature = 'ba_volrat'
            if feature in self.feature_list:
                clmn = 'ba_volrat_' + d_s
                variable_dict[feature + '_' + d_s] = data_pro.loc[:, clmn]
            feature = 'diff_ema_am_wm'
            if feature in self.feature_list:
                clmn = 'mid_priceW_' + d_s
                mid_priceSW = ema(data_pro.loc[:, clmn], p_list[-1])
                variable_dict[feature + '_' + d_s] = np.log(mid_priceS / mid_priceSW)
            feature = 'diff_am_wm'
            if feature in self.feature_list:
                clmn = 'mid_priceW_' + d_s
                mid_priceW = data_pro.loc[:, clmn]
                variable_dict[feature + '_' + d_s] = np.log(mid_price / mid_priceW)
        # Bid Ask related
        feature = 'diff_ema_ba_mba'
        if feature in self.feature_list:
            clmn = 'ba_spread'
            ba_spreadS = ema(data_pro.loc[:, clmn], p_list[-1])
            variable_dict[feature] = data_pro.loc[:, clmn] - ba_spreadS

        feature = 'sparsity'
        if feature in self.feature_list:
            variable_dict['b_price_sparsity'] = data_pro['b_price_sparsity']
            variable_dict['a_price_sparsity'] = data_pro['a_price_sparsity']
            # TODO: create new name for pixel sparsity
            # Pixel sparsity
            # clmn_b = 'bid_sparsity'
            # clmn_a = 'ask_sparsity'
            # colb_list = [col for col in data_pro.columns if col.startswith(clmn_b)]
            # cola_list = [col for col in data_pro.columns if col.startswith(clmn_a)]
            # for colb, cola in zip(colb_list, cola_list):
            #     feature = 'diff_' + colb.split('_', 1)[-1]
            #     variable_dict[feature] = data_pro.loc[:, cola] - data_pro.loc[:, colb]
                
        # feature = 'bid_sparsity'
        # if feature in self.feature_list:
        #     col_list = [col for col in data_pro.columns if col.startswith(feature)]
        #     for col in col_list:
        #         variable_dict[col] = data_pro.loc[:, col]
        # feature = 'ask_sparsity'
        # if feature in self.feature_list:
        #     col_list = [col for col in data_pro.columns if col.startswith(feature)]
        #     for col in col_list:
        #         variable_dict[col] = data_pro.loc[:, col]

        feature = 'b_price'
        if feature in self.feature_list:
            variable_dict[feature] = data_pro.loc[:, feature]
        feature = 'a_price'
        if feature in self.feature_list:
            variable_dict[feature] = data_pro.loc[:, feature]
        feature = 'ba_spread'
        if feature in self.feature_list:
            variable_dict[feature] = data_pro.loc[:, feature]

        return pd.DataFrame(variable_dict, index=data_pro.index)

    def prepare_reg_data_cross(self, data_dict_mkt, timestamp, idx, pma_list,
                               p_list, ts_data=None, gran=None, smooth=True, keep_ts=False):
        # Market list
        mkt_list = list(data_dict_mkt.keys())
        ### Prepare data ###
        series_roll_mw = {}
        variable_dict = {}
        for i, data_dict in data_dict_mkt.items():
            data_raw = pd.DataFrame(data_dict)
            data_raw.set_index(keys='timestamp', inplace=True)
            data_raw = data_raw.dropna()
            data_raw = data_raw.sort_index()
            if gran is not None:
                data_pro = unify_time_pd(data_raw, ts_data).resample(gran).ffill()
            else:
                data_pro = unify_time_pd(data_raw, ts_data)
            idx_m = unify_time(timestamp, idx, data_pro.index)
            if not keep_ts:
                data_pro = group_index(data_pro, idx_m, 'mean')

            clmn = 'mid_price'
            if smooth:
                m_price = ema(data_pro.loc[:, clmn], p_list[-1])
            else:
                m_price = data_pro.loc[:, clmn]
            series_roll_mw[i] = {'{:02}'.format(k): mov_avg(m_price, k) for k in pma_list}
            series_roll_mw[i]['00'] = m_price
        # Cloud differences
        feature = 'diff_mw'
        if feature in self.feature_list:
            for i in mkt_list:
                mkt_str = '{:02}'.format(i)
                aux_dict = self.cloud_diff(mkt_str, pma_list, series_roll_mw[i])
                variable_dict = {**variable_dict, **aux_dict}
        # Cross market attributes
        feature = 'rat_mkt_mw'
        # AttributeError: 'OB_attributes' object has no attribute 'cross_diff'
        if False and feature in self.feature_list:
            # First market is main
            for j in mkt_list[1:]:
                mkt_str = '{:01}'.format(mkt_list[0]) + '_' + '{:01}'.format(j)
                aux_dict = self.cross_diff(mkt_str, pma_list, series_roll_mw[i])
                variable_dict = {**variable_dict, **aux_dict}
        return pd.DataFrame(variable_dict, index=data_pro.index)

    def prepare_class_data(self, data_dict, csum, idx_m, tick_val, cls_margin,
                           timestamp=None, gran=None):
        if self.verbose:
            print("Prepare class data, margin: ", cls_margin)
        pd_data = pd.DataFrame(data_dict)
        pd_data.set_index(keys='timestamp', inplace=True)
        pd_data = pd_data.dropna()
        pd_data = pd_data.sort_index()
        if timestamp is None:
            timestamp = pd_data.index
        if gran is not None:
            pd_data = pd_data.resample(gran).ffill()
        # Calc return
        ba_names = ['b_price', 'a_price']
        ba_ser = group_index(pd_data.loc[:, ['b_price', 'a_price']], idx_m, 'first')
        mid_series = .5 * (ba_ser['b_price'] + ba_ser['a_price'])
        ba_ser['ret_value'] = diff(mid_series, tick_val, True, None)
        ba_ser = unify_time_pd(ba_ser, pd_data.index)
        pd_data['ret_value'] = ba_ser['ret_value']
        del mid_series
        ts = pd_data.index
        pd_data.reset_index(drop=True, inplace=True)
        data_dict_ = pd_data.to_dict('list')
        data_dict_['timestamp'] = csum
        out_dict = {}
        out_dict['timestamp'] = [x for x in ts]
        out_dict['class'] = []
        # Main loop
        for i, t in enumerate(data_dict_['timestamp']):
            aux_dict = {k: v[:i + 1] for k, v in data_dict_.items()}
            aux_dict['timestamp'] = csum[:i + 1]
            bestB_price = data_dict_[ba_names[0]][i]
            bestA_price = data_dict_[ba_names[1]][i]
            c_f = self.class_label_e(t, i, tick_val, bestB_price, bestA_price,
                                     data_dict_, cls_margin)
            out_dict['class'].append(c_f)
            del c_f
        data_out = pd.DataFrame(out_dict).set_index('timestamp')
        return unify_time_pd(data_out, timestamp)
    
    def prepare_class_data_quick(self, data_dict, tick_period, cls_margin,
                           timestamp=None, gran=None):
        def class_label_quick(tick_period, b_price, a_price, variable_dict,
                    cls_margin, min_c=.5):
            # Forward looking class
            try:
                time_difference = pd.to_timedelta(variable_dict['timestamp'][-1] - variable_dict['timestamp'][0]).total_seconds()
            except IndexError:
                return np.nan

            if time_difference < tick_period*60/2:
                c = np.nan
            else:
                b_aux = variable_dict['b_price']
                a_aux = variable_dict['a_price']
                # Assuming t_aux is a list of datetime objects
                t_aux = variable_dict['timestamp']
                
                # Get the minimum and maximum times
                t_min, t_max = t_aux[0], t_aux[-1]
                try:
                # Calculate time difference in seconds
                    time_diff = (t_max - t_min).total_seconds()
                except:
                    time_diff = (t_max - t_min)

                
                # Rest of your code
                bool_bear = [1 if x < b_price - cls_margin else 0 for x in a_aux]
                bool_bull = [1 if x > a_price + cls_margin else 0 for x in b_aux]
                sign_list = [x - y for x, y in zip(bool_bull, bool_bear)]
                
                # Adjust based on the comparison to avoid issues with timedelta vs. float
                if abs(time_diff) < 1e-5:
                    wght_list = [1 for _ in sign_list]
                else:
                    try:
                        wght_list = [((1 - min_c) / time_diff) * (t_max - x).total_seconds() + min_c for x in t_aux]
                    except:
                        wght_list = [((1 - min_c) / time_diff) * (t_max - x) + min_c for x in t_aux]

                # Multiply weights with signs
                c = np.sign(sum([x * y for x, y in zip(sign_list, wght_list)]))
            return c
        print("Prepare class data quick, margin: ", cls_margin)
        pd_data = pd.DataFrame(data_dict)
        pd_data.set_index(keys='timestamp', inplace=True)
        pd_data = pd_data.dropna()
        pd_data = pd_data.sort_index()

        # auxiliary df with best orders in defined timestamps
        ba_ser = unify_time_pd(pd_data, timestamp).reindex(timestamp)
        ba_ser.reset_index(names='timestamp', inplace=True)
        pd_data.reset_index(names='timestamp', inplace=True)

        ba_names = ['timestamp', 'b_price', 'a_price']
        ba_ser = ba_ser.loc[:, ba_names].copy()

        out_dict = {}
        out_dict['timestamp'] = [x for x in timestamp]
        out_dict['class'] = []
        # loop by timestamps
        for row in ba_ser.to_dict(orient='records'):
            bestB_price = row['b_price']
            bestA_price = row['a_price']
            variable_dict = pd_data[(
                pd_data.timestamp >= row['timestamp'])
                & (pd_data.timestamp < row['timestamp'] + pd.to_timedelta(tick_period, unit='m'))
                ].to_dict('list')
            c_f = class_label_quick(tick_period, bestB_price, bestA_price,
                                     variable_dict, cls_margin)
            out_dict['class'].append(c_f)
            del c_f

        data_out = pd.DataFrame(out_dict).set_index('timestamp')
        return data_out

    @staticmethod
    def class_label(t, i, t_delta, b_price, a_price, variable_dict, cls_margin,
                    idx=[], min_c=0):
        # Forward looking class
        if variable_dict['timestamp'][-1] < t + t_delta:
            c = np.nan
        else:
            idx_s = bisect_left(variable_dict['timestamp'][i:], t + t_delta)
            ret_mid = variable_dict['ret_value'][i + idx_s - 1]
            ret_ba = np.log((a_price + .5 * cls_margin) / (b_price - .5 * cls_margin))
            if (abs(ret_mid) - ret_ba) > 0:
                c = np.sign(ret_mid)
            else:
                c = 0
            if ret_ba < 0:
                c = np.nan
        return c

    @staticmethod
    def class_label_e(t, i, t_delta, b_price, a_price, variable_dict,
                      cls_margin, idx=[], min_c=.5):
        # Forward looking class
        if variable_dict['timestamp'][-1] < t + t_delta:
            c = np.nan
        else:
            idx_s = bisect_left(variable_dict['timestamp'][i:], t + t_delta)
            if idx_s < 1:
                idx_s = 1
            b_aux = variable_dict['b_price'][i + 1:i + idx_s + 1]
            a_aux = variable_dict['a_price'][i + 1:i + idx_s + 1]
            t_aux = variable_dict['timestamp'][i + 1:i + idx_s + 1]
            if not idx:
                pass
            else:
                idx_aux = idx[i + 1:i + idx_s + 1]
                b_aux = [avg([x for (x, i) in zip(b_aux, idx_aux) if i == i_d]) for i_d in set(idx_aux)]
                a_aux = [avg([x for (x, i) in zip(a_aux, idx_aux) if i == i_d]) for i_d in set(idx_aux)]
                t_aux = [avg([x for (x, i) in zip(t_aux, idx_aux) if i == i_d]) for i_d in set(idx_aux)]
            t_min, t_max = t_aux[0], t_aux[-1]
            bool_bear = [1 if x < b_price - cls_margin else 0 for x in a_aux]
            bool_bull = [1 if x > a_price + cls_margin else 0 for x in b_aux]
            sign_list = [x - y for x, y in zip(bool_bull, bool_bear)]
            if abs(t_max - t_min) < 1e-5:
                wght_list = [1 for x in sign_list]
            else:
                wght_list = [((1 - min_c) / (t_max - t_min)) * (t_max - x) + min_c for x in t_aux]
            # Multiply weights with signs
            c = np.sign(sum([x * y for x, y in zip(sign_list, wght_list)]))
        return c

    def calc_tick_index(self, data_dict, timestamp, gran, tick_val, tick=0.01):
        pd_data = pd.DataFrame(data_dict)
        pd_data.set_index(keys='timestamp', inplace=True)
        pd_data = pd_data.dropna()
        pd_data = pd_data.sort_index()
        if timestamp is None:
            timestamp = pd_data.index
        if gran is not None:
            pd_data = pd_data.resample(gran).ffill()
        pd_data = pd_data.reindex(timestamp.union(pd_data.index)).ffill().loc[timestamp, :]
        return self.calc_tick_index_pd(pd_data, tick_val, tick)

    @staticmethod
    def calc_tick_index_pd(pd_data, tick_val, tick):
        t_class = tick_class(tick, tick_val)
        try:
            mid_list = pd_data.loc[:, 'mid_price'].values
        except(KeyError):
            mid_list = .5 * (pd_data.loc[:, 'b_price'] + pd_data.loc[:, 'a_price']).values
        [t_class(x) for x in mid_list]
        return t_class.idx_list, t_class.csum_list, pd_data.index

    @staticmethod
    def clean_data(variable_dict, bid_clmn, ask_clmn, mid_clmn, ba_clmn, factor=7):
        bid_list = [x if x > 0 else np.nan for x in variable_dict[bid_clmn]]
        ask_list = [x if x > 0 else np.nan for x in variable_dict[ask_clmn]]
        bid_series = pd.Series(bid_list)
        ask_series = pd.Series(ask_list)
        ba_series = ask_series - bid_series
        idx_nan = []
        # ba stats
        avg_s = ba_series.mean()
        std_s = ba_series.std()
        # Diff
        dbid_series = (bid_series).diff()
        dask_series = (ask_series).diff()
        # Bids
        stop_bool = False
        avg_o = dbid_series.mean()
        std_o = dbid_series.std()
        while not stop_bool:
            ba_series = ask_series - bid_series
            dbid_series = (bid_series).diff()
            idx = [i for i, (x, y) in enumerate(zip(dbid_series, ba_series))
                   if abs(x - avg_o) > std_o * factor and abs(y - avg_s) > std_s * factor]
            if not idx:
                stop_bool = True
            else:
                bid_series.iloc[idx[0]] = np.nan
                idx_nan.append(idx[0])
            bid_series.ffill(inplace=True)
        
        # Asks
        stop_bool = False
        avg_o = dask_series.mean()
        std_o = dask_series.std()
        while not stop_bool:
            dask_series = (ask_series).diff()
            ba_series = ask_series - bid_series
            #avg = dask_series.mean()
            #std = dask_series.std()
            idx = [i for i, (x, y) in enumerate(zip(dask_series, ba_series))
                   if abs(x - avg_o) > std_o * factor and abs(y - avg_s) > std_s * factor]
            if not idx:
                stop_bool = True
            else:
                ask_series.iloc[idx[0]] = np.nan
                idx_nan.append(idx[0])
            ask_series.ffill(inplace=True)
        # Remove negative ba spread
        stop_bool = False
        while not stop_bool:
            dbid_series = (bid_series).diff()
            dask_series = (ask_series).diff()
            ba_series = ask_series - bid_series
            avg_s = ba_series.mean()
            std_s = ba_series.std()
            idx = [i for i, y in enumerate(ba_series)
                   if abs(y - avg_s) > std_s and y < 0]
            if not idx:
                stop_bool = True
            else:
                if abs(dbid_series[idx[0]]) > abs(dask_series[idx[0]]):
                    bid_series.iloc[idx[0]] = np.nan
                    idx_nan.append(idx[0])
                    bid_series.ffill(inplace=True)
                else:
                    ask_series.iloc[idx[0]] = np.nan
                    idx_nan.append(idx[0])
                    ask_series.ffill(inplace=True)
        # Convert back to lists & add nans
        bid_list = [np.nan if i in idx_nan else x for i, x in enumerate(bid_series.tolist())]
        ask_list = [np.nan if i in idx_nan else x for i, x in enumerate(ask_series.tolist())]
        mid_list = [.5 * (a + b) for a, b in zip(ask_list, bid_list)]
        ba_list = [a - b for a, b in zip(ask_list, bid_list)]
        variable_dict[bid_clmn] = bid_list
        variable_dict[ask_clmn] = ask_list
        variable_dict[mid_clmn] = mid_list
        variable_dict[ba_clmn] = ba_list
        return variable_dict


class TR_attributes(Attributes):
    def __init__(self, feature_list, price_tick=0.01, vol_tick=1, verbose=True):
        super().__init__(feature_list, price_tick, vol_tick, verbose)

    @classmethod
    def attr_list(cls, types=None):
        in_list = ['lamb_tr']
        lvl_list = ['lvl_dist']
        basic_list = ['trd_price']
        aggregated_list = ['trd_gap', 'trd_side', 'last_trade_margin', 'p_movement']
        all_list = in_list + lvl_list + basic_list + aggregated_list
        if types is None:
            return all_list
        elif types == 'intensity':
            return in_list
        elif types == 'lvl_dist':
            return lvl_list
        else:
            raise ValueError('TR: Unknown type of regressor %s' % types)

    def prepare_tr_data(self, df_data, data_dict):
        mid_series = pd.Series(data_dict['mid_price'], index=data_dict['timestamp'])
        mid_series = unify_time_pd(mid_series, df_data.index)
        mid_list = mid_series.values
        trd_list = df_data.loc[:, 'price'].values
        act_list = [-1 if p >= m else 1 for p, m in zip(trd_list, mid_list)]
        df_data['trd_side'] = act_list
        return df_data

    def prepare_reg_data(self, df_data, timestamp, pma_list, p_list, gran=None):
        """
        Prepares regression data by processing and engineering features from the input data.

        Args:
            df_data (pd.DataFrame): Input data containing market information such as price, volume, etc.
            timestamp (pd.DatetimeIndex): Unified timestamps to align the data.
            pma_list (list): List of price moving averages.
            p_list (list): List of price levels for calculating trading intensity.
            gran (str, optional): Granularity for resampling the data (e.g., '1T' for 1-minute intervals). 
                                  If None, no resampling is performed. Defaults to None.

        Returns:
            pd.DataFrame: A DataFrame containing the engineered features with timestamps as the index.

        Notes:
            - The function processes the input data by aligning it with the provided timestamps.
            - If `gran` is specified, the data is resampled to the given granularity using nanmean.
            - Missing values for non-price columns are forward-filled.
            - Features such as trading intensity (`lamb_tr`), level distance (`lvl_dist`), and trade price (`trd_price`) 
              are calculated if they are present in `self.feature_list`.
            - The resulting DataFrame contains the calculated features indexed by the unified timestamps.
        """
        variable_dict = {}
        # agg_dict = {'vwp': 'sum', 'volume': 'sum', 'action': 'median',
        #             'broker_id': 'median'}
        # Unify timestamps
        # EDIT:
        #ts_new = df_data.index.union(ts_data)
        ts_new = timestamp
        # Prepare data
        if gran is not None:
            data_pro = df_data.reindex(ts_new).resample(gran).nanmean()
        else:
            data_pro = df_data.reindex(ts_new)
            data_pro.loc[:, data_pro.columns != 'price'] = data_pro.loc[:, data_pro.columns != 'price'].ffill()
        # EDIT: not needed
        # idx_m = unify_time(timestamp, idx, data_pro.index)
        # data_pro['vwp'] = data_pro['price'] * data_pro['volume']
        # data_pro = group_index(data_pro, idx_m, 'agg', columns=agg_dict.keys(),
        #                        agg_dict=agg_dict)
        # data_pro['vwp'] /= data_pro['volume']
        # Features engineering
        # Trading intensity
        feature = 'lamb_tr'
        if feature in self.feature_list:
            # Calculate number of trades from both sides
            lamb_dict = self.prepare_tr_lamb(data_pro, p_list)
            variable_dict = {**variable_dict, **lamb_dict}
        feature = 'lvl_dist'
        if feature in self.feature_list:
            lvl_dist_dict = self.feature_lvl_dist(data_pro, "")
            variable_dict = {**variable_dict, **lvl_dist_dict}
        # Momentum features
        feature = 'trd_momentum'
        if feature in self.feature_list:
            # Calculate momentum features
            trd_momentum_dict = self.feature_trd_momentum(data_pro, pma_list)
            variable_dict = {**variable_dict, **trd_momentum_dict}
        # basic attributes
        feature = 'trd_price'
        if feature in self.feature_list:
            feat_dict = {'trd_price': list(data_pro['trd_price'].values)}
            variable_dict = {**variable_dict, **feat_dict}

        return pd.DataFrame(variable_dict, index=ts_new)

    @staticmethod    
    def prepare_reg_fair(df_ba, df_tr, split_dict, model_data, model_single,
                         mkt_lag, mkt_leads, q):
        # Other data
        grouped = df_ba.groupby(df_ba.index.date)
        ba_dict = {date: group.dropna() for date, group in grouped
                   if date in model_data.run_dates}
        class_dict = {
            date: pd.DataFrame({'class': group.dropna().iloc[:, 0] * 0})
            for date, group in grouped
            if date in model_data.run_dates
        }
        # Loop for models
        pred_dict = {m: [] for m in mkt_leads}
        sigma_dict = {m: [] for m in mkt_leads}
        for m in mkt_leads:
            # Scale
            reg_data = model_data.scale_data_dict(split_dict[m])
            pred_dict[m], sigma_dict[m] = model_data.prepare_model_trds(df_tr, mkt_lag, model_single, reg_data)
        mdl_dict = model_data.process_model_mkt_n(ba_dict, class_dict, pred_dict)
        km_model = 'filter'
        return model_data.ensemble_models(mdl_dict, ba_dict, df_tr, mkt_leads, mkt_lag, sigma_dict, q, km_model)
    
    @staticmethod
    def fair_price_on_lagger(df_ba, tr_data_dict, dates, dates_out, ts_lead, n=16):
        from Strategies.Sparse_momentum.reg_kalman_functions \
            import data_process_single_ret_n, split_data, scale_data_dict, \
                prepare_model_trds_off, process_model_mkt, predict_labels
        df_ba = pd.DataFrame(df_ba).set_index('timestamp')
        d_t = 1
        date_range_dict = {k.date(): pd.date_range(k, periods=n, freq='B')
                        for k in dates[:-n+1] if k not in dates_out}
        data_p = pd.DataFrame({k: v['price'] for k, v in tr_data_dict.items()})
        
        # data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
        
        # Model
        tau = 10
        tau_ema = 10
        
        
        isScaled = True
        isEMA = False
        EMA_N_ = 16
        # Markets
        mkt = ts_lead
        # Process data
        data_dict = data_process_single_ret_n(data_p, mkt, tau, tau_ema, None, True, km_bool=True)
        split_dict = split_data(data_dict, date_range_dict, d_t)
        # Scale
        reg_data = scale_data_dict(split_dict[mkt], tau, EMA_N_ , isScaled, isEMA)
    
    
        model = LinearRegression(fit_intercept=False)
        pred_dict = prepare_model_trds_off(data_p, mkt, model, reg_data, split_dict[mkt]['train'], tau, n, isEMA)
    
        grouped = df_ba.groupby(df_ba.index.date)
        ba_dict = {date: group.dropna() for date, group in grouped if date in pred_dict.keys()}
        mdl_dict = process_model_mkt(ba_dict, pred_dict)
    
        result = predict_labels(mdl_dict, 0.08, 1.5).rename(columns={'ret': 'lag_return_hat'})[
            ['lag_return_hat', 'fair_margin']
        ]
        result.index = pd.to_datetime(result.index)
        return result

    @staticmethod
    def calculate_dti(df_tr, df_ba, n_trades):
        """
        Calculate Directional Trading Intensity (DTI) for bid and ask trades.

        Parameters:
            trades_df: pd.DataFrame with ['timestamp', 'trd_price']
            ba_df: pd.DataFrame with ['timestamp', 'b_price', 'a_price']
            n_trades: int, window size for DTI calculation

        Returns:
            pd.DataFrame with DTI_bid and DTI_ask columns.
        """

        def compute_time_window(df, group_col, window_size):
            """
            For each row, returns the start timestamp of the n-th last unique group in `group_col`.
            (E.g., for n=5, the group 'current - 5'.)
            """
            if window_size is None:
                start_time = df['timestamp'].iloc[0]
                start_times = pd.Series(start_time, index=df.index)
                df_out = (df['timestamp'] - start_times).dt.total_seconds()
                df_out = df_out.copy()
                df_out.iloc[0] = 1  # Set first value to 1 (no previous group)
                df_out /= df[group_col]
                df_out.index = df['timestamp']
                return df_out
            # Map group numbers to their first occurrence timestamp
            group_starts = df.groupby(group_col)['timestamp'].first()
            
            # For each row, get the (current group - n) number
            target_group = df[group_col] - window_size

            # Map to start timestamp (NaN if target_group < min group)
            start_times = target_group.map(group_starts)
            df_out = (df['timestamp'] - start_times).dt.total_seconds()
            df_out.index = df['timestamp']
            return df_out / window_size

        name = 'dti_' + str(n_trades)
        # Ensure df_tr and df_ba are aligned
        df_ba = df_ba.reindex(df_ba.index.union(df_tr.index)).loc[df_tr.index, :]
        df_ba['mid_price'] = 0.5 * (df_ba['b_price'] + df_ba['a_price'])
        df_tr['side'] = np.where(df_tr['trd_price'] >= df_ba['mid_price'], 1, -1)
        df_trades = df_tr.sort_values(by='timestamp').reset_index()
        grouped = df_trades.groupby(df_tr.index.date)
        df_dti = pd.DataFrame([])
        for date, df_tr_d in grouped:
            # Aggregate trades at identical consecutive prices (handles iceberg)
            df_tr_d['price_change'] = df_tr_d['trd_price'].ne(df_tr_d['trd_price'].shift()).astype(int)
            df_tr_d['bid_change'] = df_tr_d['price_change'] * (df_tr_d['side'] == -1)
            df_tr_d['ask_change'] = df_tr_d['price_change'] * (df_tr_d['side'] == 1)
            df_tr_d['price_groups'] = df_tr_d['price_change'].cumsum()
            df_tr_d['bid_groups'] = df_tr_d['bid_change'].cumsum()
            df_tr_d['ask_groups'] = df_tr_d['ask_change'].cumsum()
            # Calculate dti for bid and ask trades
            price_dti = compute_time_window(df_tr_d.reset_index(), 'price_groups', None)
            bid_dti = (price_dti / compute_time_window(df_tr_d.reset_index(), 'bid_groups', n_trades)).clip(upper=10)
            ask_dti = (price_dti / compute_time_window(df_tr_d.reset_index(), 'ask_groups', n_trades)).clip(upper=10)
            # Total DTI values
            dti_aux = pd.DataFrame({name: ask_dti - bid_dti})
            if df_dti.empty:
                df_dti = dti_aux
            else:
                df_dti = pd.concat([df_dti, dti_aux])
        return df_dti.sort_index()

    @staticmethod
    def calculate_dti_time(df_tr, interval='1T'):
        """
        Calculate time-based trade intensity, looping over days.

        Parameters:
            trades_df: pd.DataFrame with ['Timestamp', 'Price', 'Volume']
            interval: resample interval (e.g., '1T' for 1 minute bars)

        Returns:
            pd.DataFrame with time-based intensity indicator.
        """
        
        def compute_dti_window(df, interval):
             # Prepare storage
            name = 'dti_' + interval
            dti_list = []
            timestamp_list = []
            interval_seconds = pd.to_timedelta(interval).total_seconds()
            
            for idx, row in df.iterrows():
                t_end = row['timestamp']
                t_start = t_end - pd.to_timedelta(interval)
                window_df = df[(df['timestamp'] > t_start) & (df['timestamp'] <= t_end)]
                if len(window_df) < 2:
                    # Not enough data for DTI calculation
                    dti_list.append(np.nan)
                    timestamp_list.append(t_end)
                    continue
                
                open_price = window_df['trd_price'].iloc[0]
                close_price = window_df['trd_price'].iloc[-1]
                direction = np.sign(close_price - open_price)
                unique_prices = window_df['trd_price'].ne(window_df['trd_price'].shift()).sum()
                dti = direction * unique_prices / interval_seconds
                
                dti_list.append(dti)
                timestamp_list.append(t_end)
            return pd.DataFrame({name: dti_list, 'timestamp': timestamp_list}).set_index('timestamp')
        
        df_trades = df_tr.sort_values(by='timestamp').reset_index()
        grouped = df_trades.groupby(df_tr.index.date)
        df_dti = pd.DataFrame([])
        for date, df_tr_d in grouped:
            if df_dti.empty:
                df_dti = compute_dti_window(df_tr_d, interval)
            else:
                df_dti = pd.concat([df_dti, compute_dti_window(df_tr_d, interval)])
        return df_dti.sort_index()

    @staticmethod
    def vpin(df_data, bucket_volume, n_buckets, n_days=1):
        df_trades = df_data.sort_values(by='timestamp').reset_index()
        grouped = df_trades.groupby(df_data.index.date)
        df_bucket = pd.DataFrame([])
        date_list = []
        for date, df_tr_d in grouped:
            # Accumulate trades into volume buckets
            df_tr_d['cum_vol'] = df_tr_d['volume'].cumsum()
            df_tr_d['bucket'] = (df_tr_d['cum_vol'] // bucket_volume).astype(int)
            bucket_data = df_tr_d.groupby('bucket').agg(
                timestamp=('timestamp', 'last'),
                open_price=('price', 'first'),
                close_price=('price', 'last'),
                volume=('volume', 'sum')
            ).reset_index()
            # Calculate price changes (ΔP)
            bucket_data['price_change'] = bucket_data['close_price'].diff().fillna(0)
            bucket_data = bucket_data.iloc[:-1, :]
            if df_bucket.empty:
                df_bucket = bucket_data
            else:
                df_bucket = pd.concat([df_bucket, bucket_data])
            date_list.append(date)
        df_bucket = df_bucket.sort_values('timestamp').reset_index(drop=True)
        # Calculate rolling sigma_delta from past n_days (using only past values)
        df_bucket['date'] = pd.to_datetime(df_bucket['timestamp']).dt.date
        df_bucket['sigma_delta'] = np.nan
        for idx, row in df_bucket.iterrows():
            curr_time = row['timestamp']
            curr_date = row['date']
            # Find the index of curr_date in date_list
            idx_date = date_list.index(curr_date)
            # Find the index n_days before
            idx_n_days_before = max(0, idx_date - n_days)
            # Get all buckets from previous n_days (strictly before current bucket)
            mask = (df_bucket['timestamp'] < curr_time) & \
                   (df_bucket['date'] >= date_list[idx_n_days_before])
            past_changes = df_bucket.loc[mask, 'price_change']
            if len(past_changes) > 1:
                df_bucket.at[idx, 'sigma_delta'] = past_changes.std()
            else:
                df_bucket.at[idx, 'sigma_delta'] = np.nan
        # Bulk volume classification using standard normal CDF (Z-function)
        df_bucket['buy_volume'] = bucket_volume * norm.cdf(df_bucket['price_change'] / df_bucket['sigma_delta'])
        df_bucket['sell_volume'] = bucket_volume - df_bucket['buy_volume']
        # Calculate order imbalance
        df_bucket['OI'] = np.abs(df_bucket['buy_volume'] - df_bucket['sell_volume'])
        # Calculate VPIN as rolling average of OI normalized by bucket volume
        df_bucket['vpin'] = df_bucket['OI'].rolling(window=n_buckets).mean() / bucket_volume
        return df_bucket[['timestamp', 'vpin']].set_index('timestamp')

    def prepare_tr_lamb(self, df_data, p_list):
        data_dict = {}
        # Index
        data = pd.DataFrame(index=df_data.index)
        # Bid side
        lamb_b = (df_data.loc[:, 'trd_side'] == -1).astype(float)
        # Ask side
        lamb_a = (df_data.loc[:, 'trd_side'] == 1).astype(float)
        # Combine
        # data = pd.concat([data, lamb_b, lamb_a], axis=1).groupby(0).sum()
        data = pd.concat([data, lamb_b, lamb_a], axis=1)
        # Market intensity indicators
        for period in p_list:
            nS = '{:02}'.format(period)
            sum_lamb_b = data.iloc[:, 0].rolling(window=period).sum().shift(1)
            sum_lamb_a = data.iloc[:, 1].rolling(window=period).sum().shift(1)
            feature = 'lamb_tr_b'
            data_dict[feature + '_' + nS] = sum_lamb_b / period
            feature = 'lamb_tr_a'
            data_dict[feature + '_' + nS] = sum_lamb_a / period
        # Relative indicators
        nS1 = '{:02}'.format(p_list[0])
        for period in p_list[1:]:
            nS2 = '{:02}'.format(period)
            # From bids
            feature = 'ilamb_b'
            feat_aux = 'lamb_tr_b_'
            ilamb = data_dict[feat_aux + nS1] >= data_dict[feat_aux + nS2]
            data_dict[feature + '_' + nS2] = ilamb
            # From asks
            feature = 'ilamb_a'
            feat_aux = 'lamb_tr_a_'
            ilamb = data_dict[feat_aux + nS1] >= data_dict[feat_aux + nS2]
            data_dict[feature + '_' + nS2] = ilamb
        # Market acceleration
        feature = 'dlamb_b_'
        feat_aux = 'lamb_tr_b_'
        data_dict[feature + nS2] = diff(data_dict[feat_aux + nS1], p_list[-1], False)
        feature = 'dlamb_a_'
        feat_aux = 'lamb_tr_a_'
        data_dict[feature + nS2] = diff(data_dict[feat_aux + nS1], p_list[-1], False)
        return {k: list(unify_time_pd(pd.DataFrame(v), df_data.index).values.squeeze()) for k, v in data_dict.items()}

    @staticmethod
    def feature_trd_momentum(data_pro, pma_list):
        """
        Calculates momentum features for trade prices using diff and differential for each period in pma_list.
        Returns a dictionary with the results, keys formatted as in other feature methods.
        """
        variable_dict = {}
        variable_dict['timestamp'] = list(data_pro.index)
        # Calculate momentum features
        for period in pma_list:
            nS = '{:02}'.format(period)
            feature = 'trd_momentum'
            variable_dict[feature + '_' + nS] = list(diff(data_pro['price'], period, log_bool=True).values)
            feature = 'trd_momentum_acc'
            variable_dict[feature + '_' + nS] = list(differential(data_pro['price'], period, 2, log_bool=True).values)
        return variable_dict

    def feature_lvl_dist(self, df_trades, prefix):
        variables = {
            'buff_len': 30,
            'buffer': [],
            'max_value': 0,
            'min_value': 9999
        }

        def push(x, value):
            if value > x['max_value']: x['max_value'] = value
            if value < x['min_value']: x['min_value'] = value
            
            value = round(value,1)
            if len(x['buffer']) < x['buff_len']:
                x['buffer'].append(value)
            else:
                x['buffer'].pop(0)
                x['buffer'].append(value)
    
        def get_bounds(x, bound:str):
            allowed_bounds = {'close', 'far'}
            if bound not in allowed_bounds:
                raise ValueError(f"Value must be one of {allowed_bounds}, but got '{bound}'")
            if bound == 'far':
                return x['min_value'], x['max_value']
            arr = pd.Series(x['buffer']).apply(lambda x: round(x,1)).unique()
            try:
                low_bound = arr.min()
                up_bound = arr.max()
                if len(x['buffer']) < x['buff_len']:
                    raise ValueError("buffer < n")
                return low_bound, up_bound
            except:
                return np.nan, np.nan
        
        def map_to_unit_interval(number, lower_bound, upper_bound):
            return max(min((number - lower_bound) / ((upper_bound - lower_bound)+0.001),1.0),0.0)
        
        close_level, far_level = [], []
        for i, x in enumerate(df_trades.to_dict(orient='records')):
            trade = x['trd_price']
            push(variables, trade)
            close_low, close_up = get_bounds(variables, 'close')
            far_low, far_up = get_bounds(variables, 'far')
            close_level.append(map_to_unit_interval(trade, close_low, close_up))
            far_level.append( map_to_unit_interval(trade, far_low, far_up))
        
        return {
            f'{prefix}_close_level': close_level,
            f'{prefix}_far_level': far_level}

    def _feature_scaled_sparsity(self, df_data, train_days=1, prod=True):
        from scipy.stats import norm
        import math
        def df_days_tag(df):
            unique_dates = df['timestamp'].dt.date.unique()
            
            # Create a dictionary to map unique dates to tags
            date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
            
            # Add a new column for the tags
            df['day'] = df['timestamp'].dt.date.map(date_to_tag)
            
            return df.copy()

        df_data = df_days_tag(df_data).copy()

        # Function to insert missing values into the sorted array
        def insert_missing_values(sorted_array, full_range):
            updated_array = sorted_array.copy()  # Copy to avoid modifying the original array
            
            for value in full_range:
                if value not in updated_array:
                    # Find the indices of the closest values before and after `value`
                    index_prev = np.searchsorted(updated_array, value, side='left') - 1
                    index_next = index_prev + 1
                    
                    # Handle cases where index_prev or index_next is out of range
                    if index_prev < 0:
                        index_prev = 0
                    if index_next >= len(updated_array):
                        index_next = len(updated_array) - 1
                    
                    # Insert the missing value into the sorted array
                    updated_array = np.insert(updated_array, index_next, value)
            
            return updated_array

        for i in range(train_days, df_data['day'].max()+1):
            df_hist = df_data[(df_data['day'] >= i-train_days) & (df_data['day'] < i)]
            df_curr = df_data[df_data['day'] == i]
            
            sp = sorted(df_hist['a_price_sparsity'].values)
            # Create a full range with steps of 0.01
            full_range = np.round(np.arange(0.0, 1.01, 0.01), 2)
            full_range = np.concatenate([full_range, [2.0]])
            sp = np.round(sp, 2)
            
            # Step 3: Fill missing values
            filled_sp = insert_missing_values(sp, full_range)
            filled_sp = np.array(sorted(filled_sp))
            length = len(filled_sp)
            

            if prod:
                def approx_ppf(sparsity):
                    p = np.where(filled_sp == sparsity)[0][0] / length

                    tol = 1e-5
                    if p <= 0 or p >= 1:
                        # Handle the boundary cases for p = 0 and p = 1
                        if round(p, 2) <= 0:
                            return -np.inf  # Approximate negative infinity for p = 0
                        elif round(p, 2) >= 1:
                            return np.inf  # Approximate positive infinity for p = 1
                        else:
                            raise ValueError("p must be in the range (0, 1)")

                    # Constants for central approximation
                    a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
                    b = [-8.4735109309, 23.08336743743, -21.06224101826, 3.13082909833]

                    # Polynomial approximation for the central region (0.08 < p < 0.92)
                    if 0.08 < p < 0.92:
                        q = p - 0.5
                        r = q * q
                        return q * (((a[3] * r + a[2]) * r + a[1]) * r + a[0]) / \
                            ((((b[3] * r + b[2]) * r + b[1]) * r + b[0]) * r + 1.0)

                    # Tail approximation for values near 0 and 1
                    else:
                        if p < 0.5:
                            r = np.sqrt(-2.0 * np.log(p))
                            return -(r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) /
                                     (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3))
                        else:
                            r = np.sqrt(-2.0 * np.log(1.0 - p))
                            return r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) / \
                                (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3)
                func = approx_ppf
            else:
                func = lambda a: 0.0 if pd.isna(a) else norm.ppf(np.where(filled_sp == a)[0][0]/length)
            df_data.loc[df_data['day'] == i, 'scaled_sparsity'] = df_curr.apply(
                lambda row: math.erf((func(row['a_price_sparsity'])-func(row['b_price_sparsity']))/2), axis=1)
        return df_data['scaled_sparsity']
    
    
    def diff_reg(self, df, columns):
        for col in columns:
            if col in df.columns:
                df['diff_'+col] = df[col].diff()
        
    
    def aggregated_reg(self, df):
        dataframe = df.copy()
        feature_list = self.feature_list
        # print(feature_list)
        
        feature = 'trd_side'
        if feature in 'trd_side':
            if all([x in dataframe.columns for x in 
                    ['b_price', 'a_price', 'trd_price']]):
                dataframe['trd_side'] = dataframe.apply(self._trd_side_calc, axis=1)
            else:
                print("[ERROR]: Missing attributes for calculating regressor trd_side, needed columns",
                      "['b_price', 'a_price', 'trd_price']")
                
        feature = 'trd_gap'
        if feature in feature_list:
            if all([x in dataframe.columns for x in 
                    ['b_price', 'a_price', 'trd_price', 'trd_side']]):
                dataframe['trd_gap'] = dataframe.apply(self._trd_gap_calc, axis=1)
            else:
                print("[ERROR]: Missing attributes for calculating regressor trd_gap, needed columns",
                      "['b_price', 'a_price', 'trd_price', 'trd_side']")
                
        feature = 'last_trade_margin'        
        if feature in feature_list:
            if all([x in dataframe.columns for x in 
                    ['b_price', 'a_price', 'trd_price', 'trd_side']]):
                dataframe['last_trd_p'] = dataframe['trd_price']
                dataframe['last_trd_p'] = dataframe['last_trd_p'].ffill()
                dataframe['last_trade_margin'] = dataframe.apply(self._last_trd_margin_calc, axis=1)
                dataframe.drop(columns=['last_trd_p'], inplace=True)
            else:
                print("[ERROR]: Missing attributes for calculating regressor last_trade_margin, needed columns",
                      "['b_price', 'a_price', 'trd_price', 'trd_side']")
                
        feature = 'p_movement'   
        if feature in feature_list:
            if all([x in dataframe.columns for x in 
                    ['b_price', 'a_price']]):
                dataframe['mid'] = .5 * (dataframe['a_price'] + dataframe['b_price'])
                mid_diff_series = dataframe[~np.isnan(dataframe['trd_price'])]['mid'].diff(1)
                last_mid = None
                depth_list = [0.3, 0.5, 1.0]
                depth_string_list = ['0.3', '0.5', '1.0']
                result_dict = {
                    'index': mid_diff_series.index.to_list(),
                    f"{feature}_0.3": [],
                    f"{feature}_0.5": [],
                    f"{feature}_1.0": []
                }
                for price_diff in mid_diff_series:
                    if not last_mid:
                        last_mid = price_diff
                        for ds in depth_string_list:
                            result_dict[feature+"_"+ds].append(np.nan)
                    else:
                        for d, ds in zip(depth_list, depth_string_list):
                            self._pm_update(price_diff, d)
                            result_dict[feature+"_"+ds].append(
                                self._pm_evaluate(d)
                            )
                aux_df = pd.DataFrame(result_dict).set_index('index')
                dataframe = pd.concat([dataframe, aux_df], axis=1).copy()
            else:
                print("[ERROR]: Missing attributes for calculating regressor p_movement, needed columns",
                      "['b_price', 'a_price']")
        feature = 'intensity'   
        if feature in feature_list:
            if all([x in dataframe.columns for x in 
                    ['trd_price']]):
                dataframe['int'] = self._feature_intensity(dataframe.dropna(subset=['trd_price'])).copy()
            else:
                print("[ERROR]: Missing attributes for calculating regressor intensity, needed columns",
                      "['trd_price']")
        
        feature = 'scaled_sparsity'
        if feature in feature_list:
            if 'timestamp' not in dataframe.columns:
                dataframe = dataframe.reset_index(names='timestamp').copy()
            if all([x in dataframe.columns for x in 
                    ['timestamp', 'b_price_sparsity', 'a_price_sparsity']]):
                dataframe[feature] = self._feature_scaled_sparsity(dataframe)
            else:
                print("[ERROR]: Missing attributes for calculating regressor scaled sparsity, needed columns",
                      "['timestamp', 'b_price_sparsity', 'a_price_sparsity']")
                
        feature = 'interval_metrics'
        if feature in feature_list:
            if 'timestamp' not in dataframe.columns:
                dataframe = dataframe.reset_index(names='timestamp').copy()
            if all([x in dataframe.columns for x in 
                    ['timestamp', 'trd_price']]):
                result_df = pd.DataFrame(self._feature_interval_metrics(
                    dataframe[['timestamp', 'trd_price']].values, 5))
                dataframe = pd.concat([dataframe, result_df], axis=1)
            else:
                print("[ERROR]: Missing attributes for calculating regressor scaled sparsity, needed columns",
                      "['timestamp', 'trd_price']")
                
        return dataframe

    # Protected functions used in self.aggregated_reg() function
    # they are used like this dataframe.apply(func), where row represents row in dataframe
    def _trd_gap_calc(self, row):
        if bool((row['trd_price'] > (row['a_price'])) or (row['trd_price'] < (row['b_price']))):
            if row['trd_side'] > 0.5:
                return round(row['trd_price'] - row['a_price'], 2)
            else:
                return round(row['trd_price'] - row['b_price'], 2)
        else:
            return 0.0
    
    def _feature_interval_metrics(self, trades, interval_seconds):
        t_interval = interval_seconds
        
        def trades_in_interval(trades_arr):
            if trades_arr.shape[0] == 0:
                return np.array([[np.nan, np.nan]])
            
            last = trades_arr[0]
            trades_buffer = np.array([last])
            last_dt = last[0]
            
            for dt, price in trades_arr[1:]:
                # Stop counting interval if a NaN price is encountered within the interval
                if np.isnan(price):
                    return trades_buffer
                
                dt_diff = (last_dt - dt).total_seconds()
                if dt_diff > t_interval:
                    break
                
                trades_buffer = np.vstack([trades_buffer, [dt, price]])
            
            return trades_buffer
    
        result_dict = {
            'interval_int': [],
            'interval_pdiff': []
        }
        
        for i in range(0, len(trades)):
            # Check if the current price is NaN
            current_price = trades[i, 1]
            if np.isnan(current_price):
                intensity = np.nan
                p_diff = np.nan
            else:
                result = trades_in_interval(trades[:i][::-1])
                intensity = result.shape[0]
                if np.isnan(result[0, 1]) or np.isnan(result[-1, 1]):
                    p_diff = np.nan
                else:
                    p_diff = np.round(result[0, 1] - result[-1, 1], 2)
            
            result_dict['interval_int'].append(intensity)
            result_dict['interval_pdiff'].append(p_diff)
        
        return result_dict



    def _trd_side_calc(self, row):
        if abs(row['b_price'] - row['trd_price']) <  abs(row['a_price'] - row['trd_price']):
            return 0
        else:
            return 1
    
    def _last_trd_margin_calc(self, row):
        if row['trd_side'] > 0.5:
            return row['trd_price'] - row['a_price']
        else:
            return row['b_price'] - row['trd_price']
        
    def _pm_update(self, price_diff, depth):
        """_summary_
        Feature function that keeps memory of price movement for different depth
        Args:
            price_diff (float): should be difference of mid (t0-t1)
            depth (_type_): in eur format 0.3, 0.5, 0.9 recommended
            self.pm_value is dictionary that hold value of the operator for different depths
        """
        if not hasattr(self, 'pm_value'):
            self.pm_value = {}
        if not self.pm_value.get(depth, None):
            self.pm_value[depth] = 0
        
        if abs(price_diff) > 0.01:
            if self.pm_value[depth] > depth:
                if price_diff > 0:
                    self.pm_value[depth] += price_diff/2
                else:
                    self.pm_value[depth] += price_diff
            elif self.pm_value[depth] < -depth:
                if price_diff < 0:
                    self.pm_value[depth] += price_diff/2
                else:
                    self.pm_value[depth] += price_diff
            else:
                self.pm_value[depth] += price_diff

    def _pm_evaluate(self, depth):
        # https://www.desmos.com/calculator/cc7kcid1jk
        f = lambda x, b: (lambda y: 1 if y > 1 else y)((1/b**2)*x**2) if x > 0 else (lambda y: -1 if y < -1 else y)(-(1/b**2)*x**2)
        # return self.pm_value[depth] / depth
        return f(self.pm_value[depth], depth)
    
    def _feature_intensity(self, data, columns_dict={'trd_price': 'trd_price'},
                        train_lookback=3, retrain_gran='W'):
        def negative_log_likelihood(params, data):
            mu, alpha, beta = params
            if mu <= 0 or alpha <= 0 or beta <= 0:
                return np.inf  # Ensure parameters are positive

            # Convert data to numpy array for efficient computation
            data = np.array(data)

            # Initialize likelihood
            likelihood = 0

            # Calculate the contribution of each event to the likelihood
            for i, t in enumerate(data):
                # Compute sum of influences from all previous events
                # This avoids recomputing the exponential for all pairs of events
                prev_events = data[:i]  # Events before the current event
                time_diffs = t - prev_events  # Time differences to previous events
                intensity_contributions = alpha * np.exp(-beta * time_diffs)
                lambda_t = mu + np.sum(intensity_contributions)

                # Update the likelihood
                likelihood += np.log(lambda_t)

            # Subtract the integral of the base rate over the observation period
            likelihood -= mu * data[-1]

            # Subtract the integral of the triggered intensity
            # Instead of calculating for each pair, sum over all past event contributions
            # Note: The integral of each exponential term over the observation period
            for i, t in enumerate(data):
                # Only consider contributions from events that occurred before t
                if i > 0:
                    prev_events = data[:i]
                    time_diffs = t - prev_events
                    likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

            # Add contribution from the last event to the end of the observation window
            last_event = data[-1]
            time_diffs = last_event - data[:-1]
            likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

            return -likelihood  # Return the negative log-likelihood
        
        def get_initial_guess(time_differences):
            # Sample time differences data
            time_differences = np.array([time_differences])  # Replace with your actual time differences

            # Estimating mu (base intensity)
            # We'll use the entire duration to estimate the baseline rate of events
            total_time = np.sum(time_differences)
            total_events = len(time_differences)
            mu_estimate = total_events / total_time  # Events per unit time

            # Estimating alpha and beta (excitation and decay parameters)
            # This is more heuristic-based and will need adjustment based on your data

            # For alpha, let's assume the immediate increase in event rate is proportional to the initial peak
            # This is heuristic and requires you to analyze the specific behaviors in your data
            peak_rate = np.max(np.histogram(time_differences, bins=50)[0]) / (total_time / 50)  # Peak event rate in one of the bins
            alpha_estimate = (peak_rate - mu_estimate)  # Increase over baseline, simplistic approach

            # For beta, we need to estimate how quickly the rate decays back to baseline
            # This is a simplified approach, assuming exponential decay back to the baseline after the peak
            # Find where the event rate falls back to approximately the baseline rate
            # This could be refined with more sophisticated analysis
            decay_time_index = np.argmax(np.histogram(time_differences, bins=50)[0] < mu_estimate * (total_time / 50))
            decay_time = (total_time / 50) * decay_time_index  # Approximate time it takes to decay to baseline

            beta_estimate = 1 / decay_time  # Assuming exponential decay, beta is the inverse of decay time
            return [mu_estimate, alpha_estimate, beta_estimate]
    
        def exp_kernel(t, alpha, beta):
            return alpha * np.exp(-beta * t)
        
        data_columns = [a for a in columns_dict.values()]
        df_columns = [a for a in columns_dict.keys()]
        
        df = data[data_columns].copy()
        df.columns = df_columns
        
        trades = df.dropna(subset=['trd_price'])
        
        df['time_diff'] = df.index.to_series().diff().dt.total_seconds()
        trades['time_diff'] = trades.index.to_series().diff().dt.total_seconds()
        
        estimation_dates_total = np.unique(df.index.date)[train_lookback:]
        
        if retrain_gran.lower() in ['w']:
            estimation_dates = [a.isocalendar().week for a in estimation_dates_total]
        changes = np.zeros_like(estimation_dates, dtype=bool)
        changes[1:] = [element1 != element2 for element1, element2 in zip(estimation_dates[1:], estimation_dates[:-1])]

        changes[0] = True
        
        int_dict = {}
        bounds = [(0, None), (0, None), (0, None)]
        
        for date, est_bool in zip(estimation_dates_total, changes):
            if est_bool:
                df_train = trades.loc[:date].iloc[:-1].copy()
                unique_dates = np.unique(df_train.index.date)
                params_list = []
                for train_date in unique_dates:
                    aux_train = df_train[df_train.index.date==train_date].copy()
                    initial_params = get_initial_guess(aux_train['time_diff'].dropna())
                    aux_sum = aux_train['time_diff'].dropna().cumsum()
                    results = minimize(negative_log_likelihood,
                                        initial_params,
                                        args=(np.array(aux_sum),),
                                        bounds=bounds, method='L-BFGS-B',
                                        options={'gtol': 1e-6, 'ftol': 1e-6})
                    if results.success:
                        params_list.append(results.x)
                        
                params = np.nanmean(np.array(params_list),axis=0)
                
            df_test = df[df.index.date==date].copy()
            df_test['count_time'] = df_test.index
            df_test['event_time'] = pd.to_datetime(np.where(~df_test['trd_price'].isna(),
                                                            df_test.index,
                                                            None))
            df_test['event_time'] = df_test['event_time'].ffill()
            df_test.dropna(subset=['count_time'],inplace=True)
            
            mu, alpha, beta = params
            intensities_list = [mu + sum(exp_kernel((count_time - event_time).total_seconds(), alpha, beta)
                            for event_time in df_test['event_time'] if event_time<=count_time)
                        for count_time in df_test['count_time']]
            intensities = pd.Series(intensities_list, index=df_test.index)
            df_test['int'] = intensities
            int_dict[date] = df_test
            
        return pd.concat(int_dict.values())['int']

    @staticmethod
    def clean_data(df_trades, df_ba, factor=7, is_verbose=True):
        # Align time of trades with bid ask data
        ts_new = df_ba.index.union(df_trades.index)
        ts_new = ts_new[~ts_new.duplicated(keep='first')]
        df_ba_ = df_ba.reindex(ts_new).ffill().reindex(df_trades.index)
        # Make distribution of trades outside of bid ask
        mrg_b = (df_ba_.loc[:, 'b_price'] - df_trades.loc[:, 'price']).clip(lower=0)
        mrg_a = (df_trades.loc[:, 'price'] - df_ba_.loc[:, 'a_price']).clip(lower=0)
        mrg_df = mrg_a - mrg_b
        brk_df = df_trades.loc[:, 'broker_id']
        # Margin outlyers detection
        avg_o = mrg_df.mean()
        std_o = mrg_df.std()
        # idx = [i for i, (x, b) in enumerate(zip(mrg_df, brk_df))
        #        if abs(x - avg_o) > std_o * factor and b != 1441]
        idx = [True if abs(x - avg_o) > std_o * factor and b != 1441 else False
               for x, b in zip(mrg_df, brk_df)]
        if is_verbose:
            print('Deleting following trades \n')
            print(df_trades.iloc[idx, :])
            print('\n')
        return df_trades.loc[~np.array(idx), :]
    
    @staticmethod
    def instrument_action_features(df_trades, interval=[1]):
        for sec in interval:
            df_trades[f'action_sum_{sec}s'] = df_trades['trd_side'].rolling(f'{sec}s', closed='both').sum()
            df_trades[f'action_abs_sum_{sec}s'] = df_trades['trd_side'].abs().rolling(f'{sec}s', closed='both').sum()
        columns = [col for col in df_trades.columns if col.startswith('action')]    
        df_trades = df_trades[columns].reset_index().drop_duplicates(subset='index', keep='last').set_index('index')
        return df_trades
    
    @staticmethod
    def diff_metrics(df, columns, windows, suffix='_diff'):
        """
        Add deviation from rolling mean columns for specified columns and window sizes.
        
        Parameters:
        df (pd.DataFrame): Input dataframe
        columns (list): List of column names to process
        windows (list): List of window sizes (integers)
        suffix (str): Suffix for new column names
        
        Returns:
        pd.DataFrame: Dataframe with new deviation columns
        """
        df = df.copy()
        for col in columns:
            for window in windows:
                new_col = f"{col}{suffix}_{window}"
                df[new_col] = df[col] - df[col].rolling(window).mean()
        return df
    
    @staticmethod
    def trdgapcounter(df):
        series = df['trd_gap']
        signs = np.sign(series.values)
        # Where sign changes or zero, start new group
        mask = (signs != 0) & (np.roll(signs, 1) != signs)
        mask[0] = signs[0] != 0  # Handle first element correctly
        # Group id increases at each new sequence
        group_id = np.cumsum(mask * 1)
        # For zeros, set group_id to -1 so they are not counted
        group_id[signs == 0] = -1
        # Count occurrences within each group
        result = np.zeros_like(signs, dtype=int)
        # Only process nonzero groups
        nonzero = group_id != -1
        # Use pandas groupby for efficient counting
        result[nonzero] = (
            pd.Series(np.arange(len(series)))[nonzero]
            .groupby(group_id[nonzero])
            .cumcount() + 1
        )
        df['trd_gap_counter'] = result
        return df

    
    @staticmethod
    def level_metrics(df_data, n_components=5):
        trades = df_data[~pd.isna(df_data['trd_price'])]
        from sklearn.mixture import GaussianMixture
        start_day = 0
        day_levels = {}
        day_mean_distances = {}  # New dictionary for mean distances
        max_day = int(trades['day'].max())
        
        for end_day in range(2, max_day, 1):
            prices = trades[trades.eval(f'day >= {start_day} & day <= {end_day}')]['trd_price']

            X = prices.values.reshape(-1, 1)
            gmm = GaussianMixture(n_components=n_components)
            gmm.fit(X)

            means = gmm.means_
            levels = np.sort(np.round(means.flatten(), 1))
            
            if end_day+1 > max_day:
                break
                
            day_levels[end_day+1] = levels
            
            # Calculate mean distance between consecutive levels
            if len(levels) >= 2:
                level_distances = np.diff(levels)
                day_mean_distances[end_day+1] = np.mean(level_distances)
            else:
                day_mean_distances[end_day+1] = np.nan
                
            start_day += 1

        def find_closest_levels(row):
            day = row['day']
            mid = row['mid_price']
            
            if day not in day_levels:
                return pd.Series([np.nan, np.nan, np.nan, np.nan], 
                            index=['lvl_top', 'lvl_bot', 'price_level', 'level_volatility'])
            
            arr = day_levels[day]
            
            # Existing calculations
            upper = arr[arr > mid]
            lvl_top = upper.min() - mid if upper.size > 0 else np.nan
            
            lower = arr[arr < mid]
            lvl_bot = mid - lower.max() if lower.size > 0 else np.nan

            diffs = np.abs(arr - mid)
            
            # Add mean distance from precomputed dictionary
            mean_dist = day_mean_distances.get(day, np.nan)
            
            return pd.Series([lvl_top, lvl_bot, np.argmin(diffs)+1, mean_dist],
                        index=['lvl_top', 'lvl_bot', 'price_level', 'level_volatility'])

        # Apply updated function
        df_data[['lvl_top', 'lvl_bot', 'price_level', 'level_volatility']] = df_data.apply(find_closest_levels, axis=1)
        
        return df_data

    @staticmethod
    def trade_side(df_trd, df_ba, shift=1):
        """
        Calculate trade side based on bid and ask prices.
        Returns a Series with 1 for buy trades, -1 for sell trades.
        """
        if 'trd_price' not in df_trd.columns or 'b_price' not in df_ba.columns or 'a_price' not in df_ba.columns:
            raise ValueError("DataFrames must contain 'trd_price', 'b_price', and 'a_price' columns.")
        # Shift bid-ask data to align with trades
        df_ba = df_ba.copy()
        df_ba.index = df_ba.index + pd.Timedelta(microseconds=shift)
        df_ba = df_ba.reindex(df_ba.index.union(df_trd.index)).ffill().loc[df_trd.index, :]
        df_ba['mid_price'] = 0.5 * (df_ba['b_price'] + df_ba['a_price'])
        trd_side = np.where(df_trd['trd_price'] >= df_ba['mid_price'], 1, -1)
        return pd.Series(trd_side, index=df_trd.index, name='trd_side')


def group_index(df_data, idx, method, columns=None, agg_dict={}):
    if columns is None:
        columns = df_data.columns
    all_columns = ['intrinsic_time']
    all_columns.extend(columns)
    df_data['intrinsic_time'] = idx
    df_data.reset_index(inplace=True)
    df_group = df_data.loc[:, all_columns].groupby(by='intrinsic_time')
    time_groupby = df_data.groupby(by='intrinsic_time')['timestamp']
    if method == 'sum':
        df_out = df_group.sum()
    elif method == 'mean':
        df_out = df_group.mean()
    elif method == 'last':
        df_out = df_group.last()
    elif method == 'first':
        df_out = df_group.first()
        df_out.index = time_groupby.first()
        return df_out.loc[:, columns]
    elif method == 'agg':
        df_out = df_group.agg(agg_dict)
    else:
        pass
    df_out.index = time_groupby.last()
    return df_out.loc[:, columns]


def unify_time(ts, idx, timestamp):
    pd_data = pd.DataFrame({'idx': idx}, index=ts)
    pd_data = unify_time_pd(pd_data, timestamp)
    out_dict = pd_data.to_dict('list')
    return out_dict['idx']


def unify_time_pd(pd_data, timestamp):
    index_name = pd_data.index.name
    ts_new = timestamp.union(pd_data.index)
    # Drop duplicates
    ts_new = ts_new[~ts_new.duplicated(keep='first')]
    pd_data = pd_data.reindex(ts_new)
    pd_data.ffill(inplace=True)
    pd_data.bfill(inplace=True)
    return pd_data.loc[timestamp, :].rename_axis(index_name)


def mkt_comp_rel(data_dict, mkt1, mkt2, p1, p2):
    rel_ret = (np.log(data_dict[mkt1][p1] / data_dict[mkt1][p2]) -
               np.log(data_dict[mkt2][p1] / data_dict[mkt2][p2]))
    rel_ret.replace([np.inf, -np.inf], np.nan, inplace=True)
    return rel_ret


def diff(data_series, period, log_bool, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    vals = []
    if log_bool:
        value0 = np.log(value0)
    diffEMA_class = DifferentialEMA(period, value0=value0)
    if log_bool:
        [vals.append(diffEMA_class.push(np.log(x))) for x in data_series.values]
    else:
        [vals.append(diffEMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


def differential(data_series, period, n, log_bool, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    gamma = .5
    vals = []
    if log_bool:
        value0 = np.log(value0)
    diffEMA_class = DerivativeEMA(period, n, gamma, value0=value0)
    if log_bool:
        [vals.append(diffEMA_class.push(np.log(x))) for x in data_series.values]
    else:
        [vals.append(diffEMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


def mov_avg(data_series, period, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    vals = []
    maEMA_class = MA(period, 5, value0)
    [vals.append(maEMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


def ema(data_series, period, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    vals = []
    EMA_class = EMA(period, value0=value0)
    [vals.append(EMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


def avg(val_list):
    return sum(val_list) / len(val_list)


