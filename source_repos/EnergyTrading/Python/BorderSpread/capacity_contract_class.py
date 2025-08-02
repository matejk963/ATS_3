#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun May 14 16:17:50 2023

@author: marek
"""

import pandas as pd
from Utilities.delivery_class import Delivery
from BorderSpread.capacity_class import Capacity
from Utilities.date_functions import end_date
from dateutil.relativedelta import relativedelta
from Curve.forwardCurve import forward
tol = 1e-5


class CapacityContr:
    def __init__(self, capacity_class, price, delivery, start_date, period,
                 hedge_markets=[], maintenance=[], pos=1):
        self.__capacity = capacity_class
        self.__price = price
        self.__delivery = delivery
        self.__period = period
        self.__mtm_value = 0
        self.__hedge_markets = hedge_markets
        self.__pos = pos
        

        self.__check()
        self.__calc_activity(start_date, period, delivery, maintenance)

    @property
    def type(self):
        return 'capa'

    @property
    def capacity(self):
        return self.__capacity

    @property
    def price_val(self):
        return self.__price

    @price_val.setter
    def price_val(self, value):
        self.__price = value

    @property
    def mtm_value(self):
        return self.__mtm_value

    @mtm_value.setter
    def mtm_value(self, value_tuple):
        self.__mtm_value = self.price(value_tuple[0], value_tuple[1]) - self.price_val

    @property
    def delivery(self):
        return self.__delivery

    @property
    def period(self):
        return self.__period
    
    @property
    def activity(self):
        return self.__activity

    @property
    def activity_series(self):
        return self.__activity_series
    
    @property
    def border(self):
        return self.capacity.border[0]
    
    
    @property
    def get_vol_scaling(self):
        scale_dict = {}
        scale_dict['M'] = 1
        scale_dict['Q'] = 3
        scale_dict['Y'] = 12
        return scale_dict[self.period]

    @property
    def contr_name(self):
        market = self.market
        tenor = self.period
        delivery = self.delivery
        if tenor in ['m', 'q', 's', 'y']:
            date_format = '%y%m'
        else:
            date_format = '%y%m%d'
        date_str = self.__start_date.strftime(date_format)
        return market

    @property
    def market(self):
        return self.border

    @property    
    def markets(self):
        return self.capacity.markets

    @property
    def hedge_markets(self):
        if not self.__hedge_markets:
            return self.markets
        else:
            return self.__hedge_markets

    @property
    def act_markets(self):
        markets = []
        markets.extend(self.markets)
        markets.extend(self.hedge_markets)
        return list(set(markets))

    @property
    def start_date(self):
        return self.__start_date

    @property
    def end_date(self):
        return self.__end_date

    def cascade_contract(self, period, start_date=None):
        if period_size_dict(self.period) < period_size_dict(period):
            raise ValueError('Cascade of contract for larger period %s than contract %s'
                             % (period, self.period))
        if start_date is None:
            start_date = self.start_date
        freq = period.upper() + 'S'
        date_range = pd.date_range(start_date, self.end_date, freq=freq)
        return [self.new_contract(self.price_val, d, period=period) for d in date_range]

    def new_contract(self, price, start_date, period=None, capacity_class=None):
        if capacity_class is None:
            capa = self.capacity
        else:
            capa = capacity_class
        if period is None:
            period = self.period
        delivery = self.delivery
        return CapacityContr(capa, price, delivery, start_date, period)

    def delta_contracts(self, S_list):
        return [FwdContract(forward(m, S, self.start_date, self.period, self.delivery))
                for m, S in zip(self.hedge_markets, S_list)]
        

    def __calc_activity(self, start_date, period, delivery, maintenance):
        self.__start_date = start_date
        self.__end_date = end_date(start_date, period)
        date_range = pd.date_range(self.start_date, self.end_date, freq='h')
        idx = getattr(Delivery(date_range), delivery)
        self.__activity = date_range[idx]
        activity_series = pd.Series(idx.astype(int), index=date_range)
        # Maintenance
        for m_dict in maintenance:
            if m_dict['red'] < tol:
                m_dict['red'] = tol
            activity_series.loc[m_dict['start']:m_dict['end']] *= m_dict['red']
        self.__activity_series = activity_series
        
    def __check(self):
        # Check if delivery is fitted
        try:
            self.capacity.delivery[self.delivery]
        except(KeyError):
            raise('Capacity for border %s has not been fit for delivery %s'
                  % self.capacity.border[0] % self.delivery)

    def activity_mask(self, activity_range):
        return pd.Series(activity_range.isin(self.activity), index=activity_range)

    def capa_refit(self, data, lookback, scaling=1):
        # Adjust data
        eT = self.start_date
        bT = eT - relativedelta(months=lookback)
        _data = {self.delivery: {k: v.loc[bT:eT, :] for k, v in data[self.delivery].items()}}
        self.capacity.capa_fit(_data[self.delivery], self.delivery, scaling)
        return self.capacity._state

    def delta(self, S1, S2):
        return self.capacity.capa_delta(S1, S2, self.delivery)

    def price(self, S1, S2):
        return self.capacity.capa_price_mid(S1, S2, self.delivery)


class FwdContract():
    def __init__(self, fwd_class, pos=1):
        self.__fwd = fwd_class
        self.__calc_activity(fwd_class.start_date, fwd_class.period, fwd_class.delivery)
        self.__pos = pos

        self.__mtm_value = 0

    @property
    def type(self):
        return 'fwd'

    @property
    def contr_name(self):
        market = self.__fwd.market.lower()
        tenor = self.__fwd.period.lower()
        delivery = self.__fwd.delivery.lower()[0]
        if tenor in ['m', 'q', 's', 'y']:
            date_format = '%y%m'
        else:
            date_format = '%y%m%d'
        date_str = self.__start_date.strftime(date_format)
        if self.__pos >= 0:
            p_str = 'l'
        else:
            p_str = 's'
        return market + tenor + delivery + date_str + p_str

    @property
    def market(self):
        return self.__fwd.market

    @property
    def markets(self):
        return self.__fwd.market

    @property
    def price_val(self):
        return self.__fwd.price

    @price_val.setter
    def price_val(self, value):
        self.__fwd.price = value

    @property
    def mtm_value(self):
        return self.__mtm_value

    @mtm_value.setter
    def mtm_value(self, value):
        self.__mtm_value = value - self.price_val

    @property
    def delivery(self):
        return self.__fwd.delivery

    @property
    def period(self):
        return self.__fwd.period

    @property
    def activity(self):
        return self.__activity

    @property
    def activity_series(self):
        return self.__activity_series

    @property
    def start_date(self):
        return self.__start_date

    @property
    def end_date(self):
        return self.__end_date

    def __calc_activity(self, start_date, period, delivery):
        self.__start_date = start_date
        self.__end_date = end_date(start_date, period)
        date_range = pd.date_range(self.start_date, self.end_date, freq='H')
        idx = getattr(Delivery(date_range), delivery)
        self.__activity = date_range[idx]
        self.__activity_series = pd.Series(idx.astype(int), index=date_range)

    def activity_mask(self, activity_range):
        return pd.Series(activity_range.isin(self.activity), index=activity_range)

    def delta(self, S1, S2):
        return 1.0

    def __str__(self):
        return str((self.market, self.period, self.delivery, self.price_val))


def period_size_dict(period):
    out_dict = {}
    out_dict['d'] = 1
    out_dict['w'] = 7
    out_dict['m'] = 30
    out_dict['q'] = 90
    out_dict['y'] = 365
    return out_dict[period.lower()]
