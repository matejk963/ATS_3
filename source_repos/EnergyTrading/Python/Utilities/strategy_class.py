import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
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

    def __init__(self, strategy, market, instrument, actions, no_action,
                 precision, is_overnight):
        self.strategy = strategy
        self.market = market
        self.instrument = instrument
        self._actions = actions
        self._no_action = no_action
        self._precision = precision
        self._is_overnight = is_overnight

    @property
    def inst_key(self):
        return self.market + '_' + self.instrument

    @abc.abstractmethod
    def process(self):
        pass

    @abc.abstractmethod
    def process_action(self):
        pass


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