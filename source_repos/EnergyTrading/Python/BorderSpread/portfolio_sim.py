#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jun 10 21:10:18 2023

@author: marek
"""

import abc
import numpy as np
import pandas as pd
from datetime import datetime
from Utilities.date_functions import start_date, end_date
from Curve.forwardCurve import rawCurve, forward
tol = 1e-2


class portfolioSim(object):
    __metaclass__  = abc.ABCMeta

    @property
    def contr_keys(self):
        contr_keys = []
        [contr_keys.append(c.contr_name) for k in self.keys for c in self.contr_dict[k]]
        return contr_keys

    @abc.abstractmethod
    def push(self):
        pass

    @abc.abstractmethod
    def simulate(self):
        pass

    def extend_activity(self, activity_series, name):
        activity_series.name = name
        asset_activity = pd.concat([self.asset_activity,
                                    activity_series], axis=1)
        return asset_activity.fillna(0)

    def pnl(self, contr_list):
        return sum([p for p, k in self.pnl_dict.items() if k in contr_list])

    def mtm(self, contr_list):
        return sum([p for p, k in self.mtm_dict.items() if k in contr_list])

    def last_pnl(self, contract_name):
        try:
            last_pnl = self.pnl_dict[contract_name][-1]
        except(IndexError):
            last_pnl = 0
        return last_pnl

    def last_mtm(self, contract_name):
        try:
            last_mtm = self.mtm_dict[contract_name][-1]
        except(IndexError):
            last_mtm = 0
        return last_mtm

    def last_alp(self, contract_name, idx=-1):
        try:
            last_alp = self.alp_dict[contract_name][idx]
        except(IndexError):
            last_alp = 0
        return last_alp

    def diff_alp(self, contract_name):
        try:
            diff_alp = self.last_alp(contract_name) - self.last_alp(contract_name, -2)
        except(IndexError):
            diff_alp = 1
        if diff_alp <= 0:
            diff_alp = 1
        return diff_alp
            

    def profit(self, contr_list=[]):
        if not contr_list:
            contr_list = self.contr_keys
        return self.pnl(contr_list) + self.mtm(contr_list)

    def reset(self):
        self.pnl_dict = {k: [] for k in self.contr_keys}
        self.mtm_dict = {k: [] for k in self.contr_keys}
        self.alp_dict = {k: [] for k in self.contr_keys}
        self.date_list = []


class capaStratSim(portfolioSim):
    def __init__(self):
        keys = ['capa', 'fwd']
        self.__contr_dict = {k: [] for k in keys}
        self.__coeff_dict = {k: [] for k in keys}
        self.__asset_activity = pd.DataFrame([], index=pd.to_datetime([]))

    @property
    def contr_dict(self):
        return self.__contr_dict

    @property
    def coeff_dict(self):
        return self.__coeff_dict

    @property
    def asset_activity(self):
        return self.__asset_activity

    @property
    def keys(self):
        return self.__contr_dict.keys()

    @property
    def market_list(self):
        mkt_list = []
        [mkt_list.append(c.markets) for c in self.contr_dict['fwd']]
        [mkt_list.extend(c.markets) for c in self.contr_dict['capa']]
        return list(set(mkt_list))

    def curtail_activity(self, bT, eT):
        self.__asset_activity = self.__asset_activity.loc[bT:eT, :]

    def contract_list(self, type_):
        if not self.__contr_dict[type_]:
            return []
        else:
            mkt_list = []
            [mkt_list.append(c.contr_name) for c in self.__contr_dict[type_]]
            return mkt_list

    def __extend_activity(self, activity_series, name):
        self.__asset_activity = self.extend_activity(activity_series, name)

    def __add(self, contract, coeff, type_):
        self.__contr_dict[type_].append(contract)
        self.__coeff_dict[type_].append(coeff)
        self.__extend_activity(contract.activity_series, contract.contr_name)

    def __append_dicts(self, date, pnl_dict, mtm_dict, alp_dict):
        self.date_list.append(date)
        [self.pnl_dict[k].append(v) for k, v in pnl_dict.items()]
        [self.mtm_dict[k].append(v) for k, v in mtm_dict.items()]
        [self.alp_dict[k].append(v) for k, v in alp_dict.items()]
        return 0

    def add_contract(self, contract, coeff=1):
        type_ = contract.type
        if type_ not in self.keys:
            raise TypeError('Unknown type of contract: %s' % type_)
        if contract.contr_name in self.contract_list(type_):
            # find index of contract and 
            idx = [i for i, x in enumerate(self.contract_list(type_))
                   if x == contract.contr_name]
            a_i = [i for i, k in enumerate(idx) if
                   contract.activity_mask(self.contr_dict[type_][k].activity).all() and
                   self.contr_dict[type_][k].activity_mask(contract.activity).all()]
            c_i = np.sign(coeff) in [self.coeff_dict[type_][i] for i in idx]
            if not a_i and c_i:
                self.__add(contract, coeff, type_)
            elif len(a_i) == 1:
                c = self.coeff_dict[type_][a_i[0]]
                p = self.contr_dict[type_][a_i[0]].price_val
                p_hat = (c * p + coeff * contract.price_val) / (c + coeff)
                self.__contr_dict[type_][a_i[0]].price_val = p_hat
                self.__coeff_dict[type_][a_i[0]] += coeff
            else:
                raise IndexError('More assets have the same properties %s'
                                 % a_i)
        else:
            self.__add(contract, coeff, type_)

    def mkt_check(self, data_dict):
        # Intersection of input markets
        in_mkt_list = list(data_dict.keys())
        # check if all markets are available
        mkt_bool_list = [x in in_mkt_list for x in self.market_list]
        if not all(mkt_bool_list):
            mkt_miss_list = [x for x, i in zip(self.market_list, mkt_bool_list)
                             if not i]
            raise KeyError('Markets %s are not found in price dictionary' %
                           mkt_miss_list)
        return 0

    def push_old(self, date, spot_dict, fwd_dict):
        # Intersection of input markets
        in_mkt_list = list(spot_dict.keys() & fwd_dict.keys())
        # check if all markets are available
        mkt_bool_list = [x in in_mkt_list for x in self.market_list]
        if not all(mkt_bool_list):
            mkt_miss_list = [x for x, i in zip(self.market_list, mkt_bool_list)
                             if not i]
            raise KeyError('Markets %s are not found in price dictionary' %
                           mkt_miss_list)
        # Activity array
        start_period = datetime(date.year, date.month, 1)
        asset_activity = self.asset_activity.loc[start_period:, :]
        idx_arr = asset_activity.index.date() == date.date()
        # PNL for contracts
        activity_df = asset_activity.iloc[idx_arr, :]
        for k in self.keys:
            for c, coeff in zip(self.contr_dict[k], self.coeff_dict[k].values()):
                act_arr = activity_df.loc[:, c.market].values
                if k == 'capa':
                    spot_val = (spot_dict[c.markets[1]].values - 
                                spot_dict[c.markets[0]].values).clip(min=0)
                else:
                    spot_val = spot_dict[c.market].values
                value = np.sum(spot_val * act_arr) / len(act_arr) - c.price_val
                self.pnl_dict[c.market].append(value * coeff)
        # MtM for contracts
        idx_fwd = np.max(np.where(idx_arr)) + 1
        activity_df = asset_activity.iloc[idx_fwd:, :]
        for k in self.keys:
            for c, coeff in zip(self.contr_dict[k], self.coeff_dict[k].values()):
                act_arr = activity_df.loc[:, c.market].values
                if activity_df.loc[:, c.market].sum() == 0:
                    continue
                if k == 'capa':
                    fwd_s1 = fwd_dict[c.markets[0]].values * act_arr
                    fwd_s2 = fwd_dict[c.markets[1]].values * act_arr
                    mtm_val = c.mtm_value(np.mean(fwd_s1), np.mean(fwd_s2))
                    mtm_val -= sum(self.pnl_dict[c.market])
                else:
                    fwd_s = fwd_dict[c.market].reindex(activity_df.index).values * act_arr
                    mtm_val = c.mtm_value(np.mean(fwd_s))
                self.mtm_dict[c.market].append(mtm_val * coeff)
        return 0

    def push(self, date, spot_dict, fwd_dict):
        pnl_dict = {}
        mtm_dict = {}
        alp_dict = {}
        # Activity array
        start_period = datetime(date.year, date.month, 1)
        asset_activity = self.asset_activity.loc[start_period:, :]
        # idx_arr = asset_activity.index.date == date.date()
        idx_arr = asset_activity.index.isin(spot_dict['timestamp'])
        # Adjust fwd_dict
        fwd_dict_aux = {k: v.loc[asset_activity.index] for k, v in fwd_dict.items()}
        # PNL & MtM for contracts
        activity_spot = asset_activity.iloc[idx_arr, :]
        #idx_fwd = np.max(np.where(idx_arr)) + 1
        for k in self.keys:
            for c in self.contr_dict[k]:
                if c.market in ['de_at']:
                    print('stop')
                act_spot = activity_spot.loc[:, c.contr_name]
                act_fwds = asset_activity.loc[:, c.contr_name]
                # Ratio of unsettlet forward
                fwd_ratio = self.fwd_ratio(c, date)
                spot_ratio = self.spot_ratio(c, date)
                #fwd_ratio = act_fwds.iloc[idx_fwd:].sum() / act_fwds.sum()
                pnl_val, mtm_val = self.push_one(c, act_spot, act_fwds, fwd_ratio,
                                                 spot_ratio, spot_dict, fwd_dict_aux)
                pnl_dict[c.contr_name] = pnl_val
                mtm_dict[c.contr_name] = mtm_val
                alp_dict[c.contr_name] = 1 - fwd_ratio
        return pnl_dict, mtm_dict, alp_dict

    def push_one(self, contract, activity_spot, activity_fwd, fwd_ratio,
                 spot_ratio, spot_dict, fwd_dict):
        act_spot = activity_spot.values
        act_fwd = activity_fwd.values
        # n = self.last_alp(contract.market) / self.diff_alp(contract.market)
        # Spot
        pnl_val = self.last_pnl(contract.contr_name)
        if np.sum(act_spot) < tol:
            pnl_diff = 0
        else:
            pnl_diff = self.calc_pnl(contract, act_spot, spot_dict)
        # pnl_val = (pnl_val * n + pnl_diff) / (n + 1)
        pnl_val = pnl_val + pnl_diff * spot_ratio
        # MtM
        if np.sum(act_fwd) < tol:
            mtm_val = 0
        else:
            tot_val = self.calc_tot(contract, act_fwd, fwd_dict)
            # mtm_val = (tot_val - (1 - fwd_ratio) * pnl_val) / fwd_ratio
            mtm_val = (tot_val - pnl_val) * self.mtm_factor(contract, fwd_ratio)
        return pnl_val, mtm_val

    def simulate(self, date_range, df_spot, df_fwd_dict):
        self.reset()
        in_mkt_list = list(df_spot.columns.to_list() & df_fwd_dict.keys())
        spot_dict = {k: [] for k in in_mkt_list}
        fwd_dict = {k: [] for k in in_mkt_list}
        self.mkt_check(spot_dict)
        self.mkt_check(fwd_dict)
        date_vec = df_spot.index
        for d in date_range:
            # Spot dict
            idx_s = date_vec.date == d.date()
            spot_dict = {k: df_spot.loc[idx_s, k] for k in in_mkt_list}
            spot_dict['timestamp'] = df_spot.index[idx_s]
            # Create fwd curve
            idx_fwd = np.max(np.where(idx_s)) + 1
            try:
                idx_sp = (date_vec.month == d.month) & (date_vec < date_vec[idx_fwd])
            except(IndexError):
                idx_sp = (date_vec.month == d.month)
            fwd_dict = {k: self.calc_curve(d, k, df_spot.loc[idx_sp, k],
                                           df_fwd_dict[k].loc[d, :])
                        for k in in_mkt_list}
            pnl_dict, mtm_dict, alp_dict = self.push(d, spot_dict, fwd_dict)
            self.__append_dicts(d, pnl_dict, mtm_dict, alp_dict)
        output_dict = {k: pd.DataFrame({'pnl': self.pnl_dict[k], 'mtm': self.mtm_dict[k]},
                                       index=self.date_list) for k in self.contr_keys}
        return output_dict

    def backtest_all(self, sD_range, df_spot, df_fwd_dict, df_auct_dict,
                     data_spot, fix_delta=False, delta_factor=1,
                     freq='MS', lookback=12, reg_list=[]):
        keys = ['date', 'capa', 'fwd', 'tot']
        self.reset()
        pnl_dict = {}
        reg_dict = {}
        reg_class = RegressorObj(reg_list)
        for c in self.contr_dict['capa']:
            reg_class.reset()
            data_dict = {'df_spot': df_spot}
            pnl_dict_aux = {k: [] for k in keys}
            reg_dict_aux = {k: [] for k in reg_list}
            for d in sD_range:
                d_auc = df_auct_dict[c.market].loc[d, 'auct_date']
                auc_price = df_auct_dict[c.market].loc[d, 'auct_price']
                c_capa = c.new_contract(auc_price, d)
                c_capa.capa_refit(data_spot, lookback, c.get_vol_scaling)
                S1 = df_fwd_dict[c.markets[0]].loc[d_auc, :].iloc[1]
                S2 = df_fwd_dict[c.markets[1]].loc[d_auc, :].iloc[1]
                aux_dict = self.backtest_push(c_capa, df_spot, S1, S2, data_spot,
                                              fix_delta, delta_factor)
                #[pnl_dict_aux[k].extend(aux_dict[k]) for k in keys]
                # PnL data
                [pnl_dict_aux[k].extend(aux_dict[k]) for k in keys]
                # Regressor data
                data_dict.update({'S1': S1, 'S2': S2, 'c_capa': c_capa})
                [reg_class.update(k, data_dict) for k in reg_list]
                [reg_dict_aux[k].append(getattr(reg_class, k)) for k in reg_list]
            # PnL data
            pnl_dict[c.market] = pd.DataFrame(pnl_dict_aux)
            pnl_dict[c.market].set_index('date', inplace=True)
            pnl_dict[c.market] = pnl_dict[c.market].resample(freq).mean()
            # Regressor data
            if not reg_list:
                reg_dict[c.market] = []
            else:
                reg_dict[c.market] = pd.DataFrame(reg_dict_aux, index=sD_range)
                reg_dict[c.market] = reg_dict[c.market].reindex(pnl_dict[c.market].index,
                                                                method='ffill')
        return pnl_dict, reg_dict

    def backtest_rlt(self, sD_range, df_spot, df_fwd_dict, df_auct_dict,
                     data_spot, fix_delta=False, delta_factor=1, val_factor=1,
                     freq='MS', lookback=12, reg_list=[]):
        keys = ['date', 'capa', 'fwd', 'tot']
        self.reset()
        pnl_dict = {}
        reg_dict = {}
        reg_class = RegressorObj(reg_list)
        for c in self.contr_dict['capa']:
            reg_class.reset()
            data_dict = {'df_spot': df_spot}
            pnl_dict_aux = {k: [] for k in keys}
            reg_dict_aux = {k: [] for k in reg_list}
            for d in sD_range:
                d_auc = df_auct_dict[c.market].loc[d, 'auct_date']
                auc_price = df_auct_dict[c.market].loc[d, 'auct_price']
                c_capa = c.new_contract(auc_price, d)
                c_capa.capa_refit(data_spot, lookback)
                S1 = df_fwd_dict[c.markets[0]].loc[d_auc, :].iloc[1]
                S2 = df_fwd_dict[c.markets[1]].loc[d_auc, :].iloc[1]
                aux_dict = self.backtest_push(c_capa, df_spot, S1, S2, data_spot,
                                              fix_delta, delta_factor)
                # Update regressor data
                data_dict.update({'S1': S1, 'S2': S2, 'c_capa': c_capa})
                [reg_class.update(k, data_dict) for k in reg_list]
                if reg_class.ext_fair * val_factor < reg_class.ext_auc:
                    # PnL data
                    n_aux = len(aux_dict['date'])
                    pnl_dict_aux['date'].extend(aux_dict['date'])
                    [pnl_dict_aux[k].extend([0] * n_aux) for k in keys[1:]]
                else:
                    # PnL data
                    [pnl_dict_aux[k].extend(aux_dict[k]) for k in keys]
                # Regressor data
                [reg_dict_aux[k].append(getattr(reg_class, k)) for k in reg_list]
            # PnL data
            pnl_dict[c.market] = pd.DataFrame(pnl_dict_aux)
            pnl_dict[c.market].set_index('date', inplace=True)
            pnl_dict[c.market] = pnl_dict[c.market].resample(freq).mean()
            # Regressor data
            if not reg_list:
                reg_dict[c.market] = []
            else:
                reg_dict[c.market] = pd.DataFrame(reg_dict_aux, index=sD_range)
                reg_dict[c.market] = reg_dict[c.market].reindex(pnl_dict[c.market].index,
                                                                method='ffill')
        return pnl_dict, reg_dict

    def backtest_push_old(self, c_capa, df_spot, S1, S2, data_spot,
                     fix_delta, delta_factor):
        if not fix_delta:
            delta = c_capa.delta(S1, S2)
        else:
            delta = [1, -1]
        delta = [d * delta_factor for d in delta]
        c_fwd = c_capa.delta_contracts([S1, S2])
        # Spot data
        act_ser_c = c_capa.activity_series
        act_ser_h = c_fwd[0].activity_series
        spot_dict = {k: df_spot.loc[act_ser_c.index, k] for k in c_capa.act_markets}
        # Adjust delta hedge based on activity of capacity
        mmult = np.sum(act_ser_c) / np.sum(act_ser_h)
        delta = [d * mmult for d in delta]
        pnl_cap = self.calc_pnl(c_capa, act_ser_c.values, spot_dict)
        # Calculate pnl hedge
        pnl_hdg = 0
        pnl_hdg -= self.calc_pnl(c_fwd[0], act_ser_h.values, spot_dict) * delta[0]
        pnl_hdg -= self.calc_pnl(c_fwd[1], act_ser_h.values, spot_dict) * delta[1]
        return {'capa': pnl_cap, 'fwd': pnl_hdg, 'tot': pnl_cap + pnl_hdg}

    def backtest_push(self, c_capa, df_spot, S1, S2, data_spot,
                     fix_delta, delta_factor):
        date_range = pd.date_range(c_capa.start_date, c_capa.end_date, freq='D')
        pnl_cap_list = []
        pnl_hdg_list = []
        date_list = []
        if not fix_delta:
            delta = c_capa.delta(S1, S2)
        else:
            delta = [1, -1]
        delta = [d * delta_factor for d in delta]
        c_fwd = c_capa.delta_contracts([S1, S2])
        # Activity of contracts
        act_ser_c_tot = c_capa.activity_series
        act_ser_h_tot = c_fwd[0].activity_series
        # Adjust delta hedge based on activity of capacity
        mmult = np.sum(act_ser_c_tot) / np.sum(act_ser_h_tot)
        delta = [d * mmult for d in delta]
        for d in date_range:
            # Spot data
            act_ser_c = act_ser_c_tot.loc[act_ser_c_tot.index.date == d.date()]
            act_ser_h = act_ser_h_tot.loc[act_ser_h_tot.index.date == d.date()]
            spot_dict = {k: df_spot.loc[act_ser_c.index, k] for k in c_capa.act_markets}
            # Calculte pnl + mtm
            pnl_cap, pnl_hdg = self.__push_oneBT(c_capa, c_fwd, delta, spot_dict,
                                                 act_ser_c.values, act_ser_h.values)
            date_list.append(d)
            pnl_cap_list.append(pnl_cap)
            pnl_hdg_list.append(pnl_hdg)
        out_dict = {'date': date_list, 'capa': pnl_cap_list, 'fwd': pnl_hdg_list,
                    'tot': [c + h for c, h in zip(pnl_cap_list, pnl_hdg_list)]}
        return out_dict

    def __push_oneBT(self, c_capa, c_fwd_list, delta, spot_dict,
                        c_act_arr, h_act_arr):
        # Calculate pnl capa
        pnl_cap = self.calc_pnl(c_capa, c_act_arr, spot_dict)
        # Calculate pnl hedge
        pnl_hdg = 0
        pnl_hdg -= self.calc_pnl(c_fwd_list[0], h_act_arr, spot_dict) * delta[0]
        pnl_hdg -= self.calc_pnl(c_fwd_list[1], h_act_arr, spot_dict) * delta[1]
        return pnl_cap, pnl_hdg

    @staticmethod    
    def calc_curve(date, market, spot_series, fwd_series):
        sD = datetime(date.year, date.month, 1)
        spot_series_aux = spot_series.loc[sD:end_date(date, 'D')]
        spot_index = spot_series_aux.index
        # Creating forward
        price_dict = {t: p for t, p in zip(fwd_series.index, fwd_series.values)}
        # PS change forward for spot
        t_vec = pd.date_range(sD, end_date(sD, 'M'), freq='H')
        fwd_ratio = 1 - len(spot_index) / len(t_vec)
        if fwd_ratio == 0:
            pass
        else:
            spot_avg = spot_series_aux.mean()
            price_dict['M_0'] = (price_dict['M_0'] - (1 - fwd_ratio) * spot_avg) / fwd_ratio
        fwd_list = [forward(market, p, start_date(date, t), t, 'base')
                    for t, p in price_dict.items()]
        # Create curve
        curve_class = rawCurve(fwd_list, step='H')
        curve_series = curve_class.create_curve_pd()
        curve_series.loc[spot_index] = spot_series_aux.values
        return curve_series

    @staticmethod
    def calc_pnl(contract, act_arr, price_dict):
        if contract.type == 'capa':
            value = (price_dict[contract.markets[1]].values -
                     price_dict[contract.markets[0]].values).clip(min=0)
        else:
            value = price_dict[contract.market].values
        return np.sum((value - contract.price_val) * act_arr) / len(act_arr)

    @staticmethod  
    def calc_mtm(contract, act_series, price_dict):
        act_arr = act_series.values
        sum_ = np.sum(act_arr)
        if contract.type == 'capa':
            fwd_s1 = price_dict[contract.markets[0]].values * act_arr
            fwd_s2 = price_dict[contract.markets[1]].values * act_arr
            contract.mtm_value = (np.sum(fwd_s1) / sum_, np.sum(fwd_s2) / sum_)
        else:
            fwd_s = price_dict[contract.market].reindex(act_series.index).values * act_arr
            contract.mtm_value = np.sum(fwd_s) / sum_
        return contract.mtm_value

    @staticmethod
    def calc_tot(contract, act_arr, price_dict):
        if contract.type == 'capa':
            fwd_s1 = price_dict[contract.markets[0]].values * act_arr
            fwd_s2 = price_dict[contract.markets[1]].values * act_arr
            contract.mtm_value = (np.mean(fwd_s1), np.mean(fwd_s2))
        else:
            fwd_s = price_dict[contract.market].values * act_arr
            contract.mtm_value = np.mean(fwd_s)
        return contract.mtm_value

    @staticmethod
    def mtm_factor(contract, fwd_ratio):
        mtm_factor = 1.
        if contract.type == 'capa':
            mtm_factor = fwd_ratio
        return mtm_factor

    @staticmethod    
    def fwd_ratio(contract, date):
        date_range = contract.activity_series.index
        idx_arr = date_range.date == date.date()
        try:
            idx_fwd = np.max(np.where(idx_arr)) + 1
        except(ValueError):
            idx_fwd = 0
        return 1 - idx_fwd / len(date_range)

    @staticmethod
    def spot_ratio(contract, date):
        date_range = contract.activity_series.index
        idx_arr = date_range.date == date.date()
        return np.sum(idx_arr) / len(date_range)


class RegressorObj():
    def __init__(self, var_list):
        self.var_list = var_list
        self.data_dict = {k: np.nan for k in var_list}

    def reset(self):
        self.data_dict = {k: np.nan for k in self.var_list}

    def update(self, var_name, var_dict):
        if var_name == 'capa_settl':
            update_dict = {k: var_dict[k] for k in ['df_spot', 'c_capa']}
        elif var_name == 'spread':
            update_dict = {k: var_dict[k] for k in ['S1', 'S2']}
        elif var_name in ['ext_fair', 'ext_auc']:
            update_dict = {k: var_dict[k] for k in ['c_capa', 'S1', 'S2']}
        elif var_name == 'impl_ratio':
            update_dict = {k: var_dict[k] for k in ['df_spot', 'c_capa']}
        else:
            KeyError('Unknown regressor %s' % var_name)
        self.data_dict.update(update_dict)
        return 0

    @property
    def spread(self):
        return self.data_dict['S2'] - self.data_dict['S1']

    @property
    def capa_settl(self):
        capa_class = self.data_dict['c_capa']
        df_data = self.data_dict['df_spot']
        return self.calc_settle(capa_class, df_data)

    @property
    def ext_fair(self):
        c_capa = self.data_dict['c_capa']
        S1 = self.data_dict['S1']
        S2 = self.data_dict['S2']
        return c_capa.price(S1, S2) - max(self.spread, 0)

    @property
    def ext_auc(self):
        c_capa = self.data_dict['c_capa']
        return c_capa.price_val - max(self.spread, 0)

    @staticmethod
    def calc_settle(contract, df_data):
        act_ser = contract.activity_series
        price_dict = {k: df_data.loc[act_ser.index, k] for k in contract.act_markets}
        if contract.type == 'capa':
            value = (price_dict[contract.markets[1]].values -
                     price_dict[contract.markets[0]].values).clip(min=0)
        else:
            value = price_dict[contract.market].values
        return np.sum(value * act_ser.values) / len(act_ser.values)


def avg(data_list):
    return sum(data_list) / len(data_list)
