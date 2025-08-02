#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat May  6 17:16:37 2023

@author: marek
"""

import abc
import numpy as np
import pandas as pd


class PositionManager(object):
    __metaclass__  = abc.ABCMeta
    
    def write(self):
        pass
    
    def read(self):
        pass
    
    @abc.abstractmethod
    def merge(self, other):
        pass

    @abc.abstractmethod
    def delta(self, date, fw_price_dict, freq):
        pass   

    def check(self):
        n = [len(self.asset_list), len(self.asset_volume), self.asset_activity.shape[1]]
        if all(ele == n[0] for ele in n):
            return 0
        else:
            raise('Elements in object are not the same size')

    def get_common_index(self, data_dict):
        common_indices = self.asset_activity.index
        for key, series in data_dict.items():
            common_indices = common_indices.intersection(series.index)
        return common_indices

    def truncate_assets(self, time_index):
        asset_activity = self.asset_activity.loc[time_index, :]
        idx = list((asset_activity.sum() != 0).values)
        return asset_activity.iloc[:, idx], idx

    def extend_activity(self, activity_series):
        activity_series.name = self.size - 1
        asset_activity = pd.concat([self.asset_activity,
                                    activity_series], axis=1)
        return asset_activity.fillna(0)

    def sum_(self, other, fw_curve_dict, freq='MS'):
        # Combine objects to get exposure position
        delta_cap = self.delta(fw_curve_dict, freq)
        delta_hdg = other.delta(fw_curve_dict, freq)
        delta_hdg = delta_hdg.T.groupby(delta_hdg.T.index).sum().T
        delta_out = delta_cap.add(delta_hdg, fill_value=0)
        return delta_out


class PositionManagerCapa(PositionManager):
    def __init__(self, capa_contract, volume):
        self.__asset_list = []
        self.__asset_volume = []
        self.__asset_activity = pd.DataFrame()

        self.__border_list = []
        
        self.type = 'capa'

        self.__add(capa_contract, volume)
        self.check()
    
    @property
    def asset_list(self):
        return self.__asset_list

    @property
    def asset_volume(self):
        return self.__asset_volume

    @property
    def asset_activity(self):
        return self.__asset_activity

    @property
    def border_list(self):
        return self.__border_list

    @property
    def market_list(self):
        mkt_list = []
        [mkt_list.extend(x.markets) for x in self.asset_list]
        return list(set(mkt_list))

    @property
    def size(self):
        return len(self.asset_list)

    def drop(self, idx):
        capa = self.__asset_list.pop(idx)
        volume = self.__asset_volume.pop(idx)
        self.__border_list.pop(idx)
        self.__asset_activity = self.__asset_activity.drop(columns=idx)
        if self.size == 0:
            self.__asset_activity = pd.DataFrame()
        else:
            self.__asset_activity.columns = list(range(self.size))
        self.check()
        return PositionManagerCapa(capa, volume)

    def cascade(self, idx, period, start_date=None):
        pm_aux = self.drop(idx)
        contract_list = pm_aux.asset_list[0].cascade_contract(period, start_date)
        volume = pm_aux.asset_volume[0]
        [self.merge(PositionManagerCapa(c, volume)) for c in contract_list]
        return 0

    def __extend_activity(self, activity_series):
        self.__asset_activity = self.extend_activity(activity_series)

    def __add(self, capa_contract, volume):
        self.__asset_list.append(capa_contract)
        self.__asset_volume.append(volume)
        self.__extend_activity(capa_contract.activity_series)
        self.__border_list.append(capa_contract.border)

    def merge(self, other):
        if self.type != other.type:
            raise TypeError('Class type missmatch %s, %s' % (self.type, other.type))
        for capa, vol in zip(other.asset_list, other.asset_volume):
            if capa.border in self.border_list:
                idx = [i for i, x in enumerate(self.border_list)
                       if x == capa.border]
                a_i = [i for i, k in enumerate(idx) if
                       capa.activity_mask(self.asset_list[k].activity).all() and
                       self.asset_list[k].activity_mask(capa.activity).all()]
                if not a_i:
                    self.__add(capa, vol)
                elif len(a_i) == 1:
                    self.__asset_volume[a_i[0]] += vol
                else:
                    raise IndexError('More assets have the same properties %s'
                                     % a_i)
            else:
                self.__add(capa, vol)
        return self.check()

    def delta(self, fw_curve_dict, freq='MS'):
        mkt_bool_list = [x in fw_curve_dict.keys() for x in self.market_list]
        if not all(mkt_bool_list):
            mkt_miss_list = [x for x, i in zip(self.market_list, mkt_bool_list)
                             if not i]
            raise KeyError('Markets %s are not found in price dictionary' %
                           mkt_miss_list)
        # Reindex curves based on object
        ts_index = self.get_common_index(fw_curve_dict)
        fw_curve_dict = {k: v.reindex(ts_index) for k, v in fw_curve_dict.items()}
        # Average curves based on month
        asset_activity, idx = self.truncate_assets(ts_index)
        asset_list = [c for c, i in zip(self.asset_list, idx) if i]
        asset_volume = [c for c, i in zip(self.asset_volume, idx) if i]
        M = asset_activity.values.T
        S_l = [[(M[i,:] @ fw_curve_dict[x].values / np.sum(M[i,:])).item()
                for x in c.border.split('_')] for i, c in enumerate(asset_list)]
        delta_vec = [c.delta(S[0], S[1]) for c, S in zip(asset_list, S_l)]
        # Create output dataframe with position in markets
        df_out = pd.DataFrame(0, index=pd.to_datetime(ts_index), columns=self.market_list)
        for i, (c, v, d) in enumerate(zip(asset_list, asset_volume, delta_vec)):
            df_out[c.markets[0]] += asset_activity.iloc[:, i] * v * d[0]
            df_out[c.markets[1]] += asset_activity.iloc[:, i] * v * d[1]
        return df_out.resample(freq).mean()


class PositionManagerHedge(PositionManager):
    def __init__(self, fwd_contract, volume):
        self.__asset_list = []
        self.__asset_volume = []
        self.__asset_activity = pd.DataFrame()

        self.__market_list = []
        
        self.type = 'hedge'

        self.__add(fwd_contract, volume)
        self.check()
    
    @property
    def asset_list(self):
        return self.__asset_list

    @property
    def asset_volume(self):
        return self.__asset_volume

    @property
    def asset_activity(self):
        return self.__asset_activity

    @property
    def market_list(self):
        return self.__market_list

    @property
    def size(self):
        return len(self.asset_list)

    def __extend_activity(self, activity_series):
        self.__asset_activity = self.extend_activity(activity_series)

    def __add(self, fwd_contract, volume):
        self.__asset_list.append(fwd_contract)
        self.__asset_volume.append(volume)
        self.__extend_activity(fwd_contract.activity_series)
        self.__market_list.append(fwd_contract.market)

    def merge(self, other):
        if self.type != other.type:
            raise TypeError('Class type missmatch %s, %s' % (self.type, other.type))
        for fwd, vol in zip(other.asset_list, other.asset_volume):
            if fwd.market in self.market_list:
                idx = [i for i, x in enumerate(self.market_list)
                       if x == fwd.market]
                a_i = [k for i, k in enumerate(idx) if
                       fwd.activity_mask(self.asset_list[k].activity).all() and
                       self.asset_list[k].activity_mask(fwd.activity).all()]
                if not a_i:
                    self.__add(fwd, vol)
                elif len(a_i) == 1:
                    self.__asset_volume[a_i[0]] += vol
                else:
                    raise IndexError('More assets have the same properties %s'
                                     % a_i)
            else:
                self.__add(fwd, vol)
        return self.check()

    def delta(self, fw_curve_dict, freq='MS'):
        mkt_bool_list = [x in fw_curve_dict.keys() for x in self.market_list]
        if not all(mkt_bool_list):
            mkt_miss_list = [x for x, i in zip(self.market_list, mkt_bool_list)
                             if not i]
            raise KeyError('Markets %s are not found in price dictionary' %
                           mkt_miss_list)
        # Reindex curves based on object
        ts_index = self.get_common_index(fw_curve_dict)
        fw_curve_dict = {k: v.reindex(ts_index) for k, v in fw_curve_dict.items()}
        # Create output dataframe with position in markets
        asset_activity = self.asset_activity.loc[ts_index, :]
        M = asset_activity.values
        df_out = pd.DataFrame(M, index=pd.to_datetime(ts_index), columns=self.market_list)
        df_out *= self.asset_volume
        return df_out.resample(freq).mean()
