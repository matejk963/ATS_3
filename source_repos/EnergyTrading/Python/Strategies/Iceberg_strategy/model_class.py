# -*- coding: utf-8 -*-
"""
Created on Tue Nov 21 13:00:12 2023

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
from Math.accumfeatures import MSTD, MA, EMA
from Math.lm_class import kalman
import json


class ModelClass():
    __metaclass__ = abc.ABCMeta

    def __init__(self, model_name, weight, burn):
        self.name = model_name
        self.weight = weight
        self._burn = burn

    @abc.abstractmethod
    def fit(self, X):
        raise "not implemented"
        pass

    @abc.abstractmethod    
    def predict(self, X):
        pass

    @abc.abstractmethod
    def score(self, X, y, sample_weight=None):
        raise "not implemented"
        pass

# Constants
BID_ = True
ASK_ = False

class Iceberg():
    def __init__(self, level, volume):
        self.level = level
        self.volume = volume
        self.active = True
    
    def __dict__(self):
        return {'level': self.level,
                'volume': self.volume,
                'active': self.active}
    @classmethod
    def empty(cls):
        o = cls.__new__(cls)
        o.level = np.nan
        o.volume = np.nan
        o.active = False
        return o
    
        
class IcebergModel(ModelClass):
    def __init__(self, dist_file='iceberg_div5_m_dist.json'):
        with open(dist_file, 'r') as f:
            self.dist_dict = json.load(f)
        self.dist = pd.DataFrame(self.dist_dict).T.reset_index().rename(columns={'index': 'size'})
        self.levels = {
            'ask': {},
            'bid': {}
            }
        self.dist['size'] = self.dist['size'].astype(int)
    
    @property
    def active_levels(self):
        ask = {price: data for price, data in self.levels['ask'].items() if data.active}
        bid = {price: data for price, data in self.levels['bid'].items() if data.active}
        return {'ask': ask,
                'bid': bid}

    @property
    def top_bid(self):
        try:
            return self.active_levels['bid'][max([*self.active_levels['bid']])]
        except:
            return Iceberg.empty()
    
    @property
    def top_ask(self):
        try:
            return self.active_levels['ask'][min([*self.active_levels['ask']])]
        except:
            return Iceberg.empty()
        
    def get_likelihood(self, current_vol, target):
        omega = self.dist.loc[self.dist['size'] >= current_vol]['count'].sum()
        A = self.dist.loc[self.dist['size'] >= (current_vol + target)]['count'].sum()
        return A/(omega+.0001)
            
    def add_trade(self, price, volume, direction):
        for _, x in self.active_levels['ask'].items():
            if price > x.level + .02:
                x.active = False
                
        for _, x in self.active_levels['bid'].items():
            if price < x.level - .02:
                x.active = False

        if price in self.active_levels['ask']:
            if direction == ASK_:
                self.active_levels['ask'][price].volume += volume
            else:
                former_volume = self.active_levels['ask'][price].volume
                self.levels['bid'][price] = Iceberg(price, volume+former_volume)
                self.active_levels['ask'][price].active = False

        elif price in self.active_levels['bid']:
            if direction == BID_:
                self.active_levels['bid'][price].volume += volume
            else:
                former_volume = self.active_levels['bid'][price].volume
                self.levels['ask'][price] = Iceberg(price, volume+former_volume)
                self.active_levels['bid'][price].active = False
        else:
            if price*100%5 == 0:
                obj = Iceberg(price, volume)
                if direction == BID_:
                    self.levels['bid'][price] = obj
                else:
                    self.levels['ask'][price] = obj
    
    def update_icebergs(self, bid, ask, trade, volume, direction):
        if not np.isnan(trade):
            d = BID_ if direction == 'sell' else ASK_
            self.add_trade(trade, volume, d)
        else:
            if bid < ask:
                for _, x in self.active_levels['ask'].items():
                    if bid > x.level + .1:
                        x.active = False
                    
                for _, x in self.active_levels['bid'].items():
                    if ask < x.level - .1:
                        x.active = False
        
    def predict(self, target_vol):
        ib_bid = Iceberg.empty()
        ib_ask = Iceberg.empty()
        bid, ask = .0, .0

        if len([*self.active_levels['bid']]) > 0:
            ib_bid = self.active_levels['bid'][max([*self.active_levels['bid']])]
            bid = self.get_likelihood(ib_bid.volume, target_vol)

        if len([*self.active_levels['ask']]) > 0:
            ib_ask = self.active_levels['ask'][min([*self.active_levels['ask']])]
            ask = self.get_likelihood(ib_ask.volume, target_vol)
            
        return {'bid': {'level': ib_bid.level, 'p': bid},
                'ask': {'level': ib_ask.level, 'p': ask}}
class IcebergBreakModel(ModelClass):
    def __init__(self, dist_file='iceberg_div5_m_dist.json'):
        with open(dist_file, 'r') as f:
            self.dist_dict = json.load(f)
        self.dist = pd.DataFrame(self.dist_dict).T.reset_index().rename(columns={'index': 'size'})
        self.levels = {}
        self.dist['size'] = self.dist['size'].astype(int)
    
    @property
    def active_levels(self):
        ask = {price: data for price, data in self.levels['ask'].items() if data.active}
        bid = {price: data for price, data in self.levels['bid'].items() if data.active}
        return {'ask': ask,
                'bid': bid}

    @property
    def top_bid(self):
        try:
            return self.active_levels['bid'][max([*self.active_levels['bid']])]
        except:
            return Iceberg.empty()
    
    @property
    def top_ask(self):
        try:
            return self.active_levels['ask'][min([*self.active_levels['ask']])]
        except:
            return Iceberg.empty()
        
    def get_likelihood(self, current_vol, target):
        omega = self.dist.loc[self.dist['size'] >= current_vol]['count'].sum()
        A = self.dist.loc[self.dist['size'] >= (current_vol + target)]['count'].sum()
        return A/(omega+.0001)
            
    def add_trade(self, price, volume, direction):
        for _, x in self.active_levels['ask'].items():
            if price > x.level + .02:
                x.active = False
                
        for _, x in self.active_levels['bid'].items():
            if price < x.level - .02:
                x.active = False

        if price in self.active_levels['ask']:
            if direction == ASK_:
                self.active_levels['ask'][price].volume += volume
            else:
                former_volume = self.active_levels['ask'][price].volume
                self.levels['bid'][price] = Iceberg(price, volume+former_volume)
                self.active_levels['ask'][price].active = False

        elif price in self.active_levels['bid']:
            if direction == BID_:
                self.active_levels['bid'][price].volume += volume
            else:
                former_volume = self.active_levels['bid'][price].volume
                self.levels['ask'][price] = Iceberg(price, volume+former_volume)
                self.active_levels['bid'][price].active = False
        else:
            if price*100%5 == 0:
                obj = Iceberg(price, volume)
                if direction == BID_:
                    self.levels['bid'][price] = obj
                else:
                    self.levels['ask'][price] = obj
    
    def update_icebergs(self, bid, ask, trade, volume, direction):
        if not np.isnan(trade):
            d = BID_ if direction == 'sell' else ASK_
            self.add_trade(trade, volume, d)
        else:
            if bid < ask:
                for _, x in self.active_levels['ask'].items():
                    if ask > x.level + .1:
                        x.active = False
                    
                for _, x in self.active_levels['bid'].items():
                    if bid < x.level - .1:
                        x.active = False
        
    def predict(self, target_vol):
        ib_bid = Iceberg.empty()
        ib_ask = Iceberg.empty()
        bid, ask = .0, .0

        if len([*self.active_levels['bid']]) > 0:
            ib_bid = self.active_levels['bid'][max([*self.active_levels['bid']])]
            bid = self.get_likelihood(ib_bid.volume, target_vol)

        if len([*self.active_levels['ask']]) > 0:
            ib_ask = self.active_levels['ask'][min([*self.active_levels['ask']])]
            ask = self.get_likelihood(ib_ask.volume, target_vol)
            
        return {'bid': {'level': ib_bid.level, 'p': bid},
                'ask': {'level': ib_ask.level, 'p': ask}}
