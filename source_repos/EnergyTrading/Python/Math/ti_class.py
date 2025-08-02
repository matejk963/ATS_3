# -*- coding: utf-8 -*-
"""
Created on Wed Aug 30 13:18:46 2023

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm
import mplfinance as mpf
from Math.accumfeatures import EMA
tol = 1e-5
PATH = '//etc-dc2k19/net/Algo/Models/Linear/tick_plot_relation/'


class ImbalancedBars_class():
    __metaclass__ = abc.ABCMeta
    def __init__(self, tau, tau_ema):
        self.tau = tau
        self.tau_ema = tau_ema
        self.reset()

    @property
    def param_keys(self):
        return ['tau', 'tau_ema']

    def update_params(self, params_dict):
        if 'tau' in params_dict.keys():
            self.tau = params_dict['tau']
        if 'tau_ema' in params_dict.keys():
            self.tau_ema = params_dict['tau_ema']

    @property
    def ewma_val(self):
        return self.ewma.value

    @property
    def is_burn(self):
        return self.tot_n < self.burn

    @abc.abstractmethod   
    def reset(self):
        pass

    @abc.abstractmethod
    def soft_reset(self):
        pass

    @abc.abstractmethod
    def push(self, value, volume):
        pass

    @abc.abstractmethod
    def tick_imbalance_params(self, price_series, volume_series):
        pass

    @abc.abstractmethod
    def tick_imbalance_single(self, df_data):
        pass

    def signed_tick_vals(self, diff_value):
        if abs(diff_value) < tol:
            bt = self.bt
        else:
            bt = np.sign(diff_value)
        return bt

    def plot_params(self, price_series, volume_series=None):
        param_dict = self.tick_imbalance_params(price_series, volume_series)
        param_dict['thres'] = [abs(x) for x in param_dict['thres']]
        param_dict['nthres'] = [-x for x in param_dict['thres']]
        param_names = ['phiT', 'thres', 'nthres']
        plt.figure()
        pd.Series(param_dict['bt']).plot(style='.')
        pd.Series(param_dict['ewma_val']).plot()
        plt.show()
        #plt.figure()
        pd.DataFrame({k: param_dict[k] for k in param_names}).plot()
        plt.show()
        return 0

    def tick_imbalance_indices(self, df_data):
        if isinstance(df_data, pd.Series):
            df_data = pd.DataFrame(df_data)
        self.reset()
        # Divide into individual dates
        grouped = df_data.groupby(df_data.index.date)
        data_dict = {date: group for date, group in grouped}
        index_series = pd.Series(dtype='float64')
        for data in data_dict.values():
            # index_series = pd.concat([index_series, self.tick_imbalance_single(data)])
            if index_series.empty:
                index_series = self.tick_imbalance_single(data).rename_axis('index')
            else:
                index_series = pd.concat([index_series, self.tick_imbalance_single(data)])
        return index_series

    def plot_candles(self, price_i_series, price_series,
                     volume_i_series=None, volume_series=None, mav=(14,65)):
        if volume_series is None:
            volume_series = pd.Series(0, index=price_series.index, name='Volume')
            vol_bool = False
        else:
            volume_series.name = 'Volume'
            vol_bool = True
        if volume_i_series is None:
            volume_i_series = pd.Series(0, index=price_i_series.index, name='Volume')
        df_data_idx = pd.concat([price_i_series, volume_i_series], axis=1)
        agg_dict = {'index': 'first'}
        agg_dict.update({price_series.name: ['first', 'last', 'min', 'max'],
                         volume_series.name: ['sum']})
        index_series = self.tick_imbalance_indices(df_data_idx).dropna()
        df_data = pd.concat([price_series.reindex(index_series.index),
                             volume_series.reindex(index_series.index), index_series],
                            axis=1).reset_index()
        df_group = df_data.groupby(0).agg(agg_dict)
        df_group.columns = ['Date', 'Open', 'Close', 'Low', 'High', 'Volume']
        df_group.set_index('Date', inplace=True)
        mpf.plot(df_group, type='candle', style='charles', title=price_series.name,
                 volume=vol_bool, mav=mav)
        return df_group
    
    def make_candles(self, price_series, price_i_series):
        index_series = self.tick_imbalance_indices(price_i_series['price']).dropna()
        df_data = price_series.reset_index().copy()

        def weighted_mean(data):
            price = data['price']
            volume = data['volume']
            weighted_price = (price * volume).sum() / volume.sum()
            return weighted_price

        # Use the index_series to create groups in df_data
        df_data['groups'] = df_data['datetime'].map(index_series)

        # Perform aggregation for each group, including the weighted mean
        agg_funcs = {'datetime': 'first',
                    'price': ['first', 'last', 'min', 'max'],
                    'volume': 'sum'}

        # Apply the custom aggregation function to calculate weighted mean
        df_group = df_data.groupby('groups').agg(agg_funcs)
        df_group['vwap'] = df_data.groupby('groups').apply(weighted_mean)

        # Rename columns
        df_group.columns = ['Date', 'Open', 'Close', 'Low', 'High', 'Volume', 'vwap']

        # Set the 'Date' column as the index
        df_group.set_index('Date', inplace=True)
        return df_group
    
    def make_candles_in(self, price_series):
        price_series = price_series.copy()

        def tick_imbalance_single(self, price_series):
            self.soft_reset()
            dt_index = price_series.index
            price_series = price_series.dropna()
            index_series = pd.Series([self.push(v) for v in price_series['price'].values],
                                    index=price_series.index)
            index_series = index_series.reindex(dt_index).fillna(method='ffill')
            return index_series

        def tick_imbalance_indices(self, price_series):
            self.reset()
            # Divide into individual dates
            grouped = price_series.groupby(price_series['datetime'].dt.date)
            data_dict = {date: group for date, group in grouped}
            index_series = pd.Series(dtype='float64')
            for data in data_dict.values():
                index_series = pd.concat([index_series, tick_imbalance_single(self,data)])
            return index_series

        index_series = tick_imbalance_indices(self, price_series[['datetime', 'price']]).dropna()
        df_data = price_series.copy()

        def weighted_mean(data):
            price = data['price']
            volume = data['volume']
            weighted_price = (price * volume).sum() / volume.sum()
            return weighted_price

        # Use the index_series to create groups in df_data
        df_data['groups'] = df_data.index.map(index_series)

        # Perform aggregation for each group, including the weighted mean
        agg_funcs = {'datetime': 'first',
                    'price': ['first', 'last', 'min', 'max'],
                    'volume': 'sum'}

        # Apply the custom aggregation function to calculate weighted mean
        df_group = df_data.groupby('groups').agg(agg_funcs)
        df_group['vwap'] = df_data.groupby('groups').apply(weighted_mean)

        # Rename columns
        df_group.columns = ['Date', 'Open', 'Close', 'Low', 'High', 'Volume', 'vwap']

        # Set the 'Date' column as the index
        df_group.set_index('Date', inplace=True)
        return df_group
  

    def heat_map(self, df_data, tau_list, tau_ema_list, shift=1):
        mkt_list = list(df_data.columns)
        #corr_dict = {t: {m: np.nan for m in mkt_list} for t in tau_list}
        corr_dict = {m: {t1: {t2: np.nan for t2 in tau_ema_list} for t1 in tau_list} for m in mkt_list}
        for t1 in tau_list:
            self.tau = t1
            for t2 in tau_ema_list:
                self.tau_ema = t2
                for m in mkt_list:
                    data_series = df_data.loc[:, m]
                    index_series = self.tick_imbalance_indices(data_series)
                    # Calculate autocorrelation
                    corr_dict[m][t1][t2] = self.corr_ticks(data_series, index_series,
                                                           shift)
        return corr_dict
        #return {m: pd.DataFrame(v) for k, v in corr_dict.items()}

    def heat_map_s(self, df_data, tau_list, shift=1):
        mkt_list = list(df_data.columns)
        corr_dict = {t: {m: np.nan for m in mkt_list} for t in tau_list}
        for t in tau_list:
            self.tau_ema = t
            for m in mkt_list:
                data_series = df_data.loc[:, m]
                index_series = self.tick_imbalance_indices(data_series)
                # Calculate autocorrelation
                corr_dict[t][m] = self.corr_ticks(data_series, index_series,
                                                  shift)
        return pd.DataFrame(corr_dict)

    def plot_relation(self, df_data, mkt_list=None, shift=1,
                      path=PATH, save=True, group=True):
        if mkt_list is None:
            mkt_list = list(df_data.columns)
        if group:
            fig = self.plot_relation_group(df_data, mkt_list, shift)
            if save:
                file_path = path + f'tauema_tau_{self.tau_ema}_{self.tau}.png'
                fig.savefig(file_path, bbox_inches='tight', pad_inches=0)
                plt.close(fig)
            return 0
        for m in mkt_list:
            price_series = df_data.loc[:, m]
            index_series = self.tick_imbalance_indices(price_series)
            fig = self.plot_relation_single(df_data, index_series, shift, m)
            if save:
                file_path = path + f'tauema_tau_{self.tau_ema}_{self.tau}_mkt_{m}.png'
                fig.savefig(file_path, bbox_inches='tight', pad_inches=0)
                plt.close(fig)
        return 0

    def plot_relation_single(self, df_data, index_series, shift=1, mkt=''):
        mkt_list = list(df_data.columns)
        idx_dict = {k: i for i, k in enumerate(mkt_list)}
        # Aggregation dict
        agg_dict = {'index': 'first'}
        agg_dict.update({k: 'mean' for k in mkt_list})
        # Group data according to index
        data_aux = pd.concat([df_data.reindex(index_series.index), index_series],
                             axis=1).reset_index()
        data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
        grouped = data_aux.groupby(data_aux.index.date)
        data_dict = {date: group for date, group in grouped}
        # Process data
        df_ret_dict = {k: pd.DataFrame([]) for k in mkt_list}
        for m in mkt_list:
            for data in data_dict.values():
                y_series = data.loc[:, m].shift(periods=-shift).dropna()
                data = data.reindex(y_series.index)
                data.loc[:, m] = y_series
                ret_aux = np.log(data.fillna(method='ffill')).diff()
                df_ret_dict[m] = pd.concat([df_ret_dict[m], ret_aux])
            df_ret_dict[m] = df_ret_dict[m].dropna()
        # Plot relation
        n_m = len(mkt_list)
        fig, axes = plt.subplots(n_m, n_m, figsize=(60, 40))
        for m in mkt_list:
            i = idx_dict[m]
            """
            # Primary market m
            df_ret = pd.DataFrame([])
            for data in data_dict.values():
                y_series = data.loc[:, m].shift(periods=-shift).dropna()
                data = data.reindex(y_series.index)
                data.loc[:, m] = y_series
                ret_aux = np.log(data.fillna(method='ffill')).diff()
                df_ret = pd.concat([df_ret, ret_aux])
            df_ret = df_ret.dropna()
            """
            data_series0 = df_ret_dict[m].loc[:, m]
            # Plot histigram as diagonal
            n_b = int(max(50, data_series0.size / 20))
            axes[i, i].hist(data_series0, bins=n_b, density=True,
                            alpha=0.6, color='g')
            # Calculate mean and standard deviation
            mu, std = data_series0.mean(), data_series0.std()
            x = np.linspace(data_series0.min() - std, data_series0.max() + std, 100)
            p = norm.pdf(x, mu, std)
            axes[i, i].plot(x, p, 'k', linewidth=2)
            axes[i, i].set_title(f'Histogram of {m} Returns')
            # Rest of markets
            regs_mkt = [x for x in mkt_list if x != m]
            for n in regs_mkt:
                j = idx_dict[n]
                data_series0 = df_ret_dict[n].loc[:, m]
                data_series1 = df_ret_dict[n].loc[:, n]
                axes[i, j].scatter(data_series0, data_series1)
                axes[i, j].set_xlabel(f'{m} Returns')
                axes[i, j].set_ylabel(f'{n} Returns')
                axes[i, j].set_title(f'{m} vs {n}')
        plt.suptitle(f'mkt: {mkt}, tau: {self.tau}, tau_ema: {self.tau_ema}',
                     fontsize=16)
        #plt.tight_layout()
        plt.show()
        return fig

    def plot_relation_group(self, df_data, mkt_tick_list, shift=1):
        mkt_list = list(df_data.columns)
        idx_dict = {k: i for i, k in enumerate(mkt_list)}
        # Plot relation
        n_m = len(mkt_tick_list)
        n_n = len(mkt_list)
        fig, axes = plt.subplots(n_m, n_n, figsize=(60, 40))
        # Aggregation dict
        agg_dict = {'index': 'first'}
        agg_dict.update({k: 'mean' for k in mkt_list})
        # Group data according to index
        for i, m in enumerate(mkt_tick_list):
            price_series = df_data.loc[:, m]
            index_series = self.tick_imbalance_indices(price_series)
            data_aux = pd.concat([df_data.reindex(index_series.index), index_series],
                                 axis=1).reset_index()
            data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
            grouped = data_aux.groupby(data_aux.index.date)
            data_dict = {date: group for date, group in grouped}
            df_ret = pd.DataFrame([])
            for data in data_dict.values():
                y_series = data.loc[:, m].shift(periods=-shift).dropna()
                data = data.reindex(y_series.index)
                data.loc[:, m] = y_series
                ret_aux = np.log(data.fillna(method='ffill')).diff()
                df_ret = pd.concat([df_ret, ret_aux])
            df_ret = df_ret.dropna()
            data_series0 = df_ret.loc[:, m]
            # Plot histigram as diagonal
            j = idx_dict[m]
            n_b = int(max(50, data_series0.size / 20))
            axes[i, j].hist(data_series0, bins=n_b, density=True,
                            alpha=0.6, color='g')
            # Calculate mean and standard deviation
            mu, std = data_series0.mean(), data_series0.std()
            skw, kur = data_series0.skew(), data_series0.kurtosis()
            x = np.linspace(data_series0.min() - std, data_series0.max() + std, 100)
            p = norm.pdf(x, mu, std)
            axes[i, j].plot(x, p, 'k', linewidth=2, label=f'skew={skw:.2f}, kurt={kur:.2f}')
            axes[i, j].legend()
            axes[i, i].set_title(f'Histogram of {m} Returns')
            # Rest of markets
            regs_mkt = [x for x in mkt_list if x != m]
            for n in regs_mkt:
                j = idx_dict[n]
                data_series1 = df_ret.loc[:, n]
                corr = data_series0.corr(data_series1)
                axes[i, j].scatter(data_series0, data_series1, label=f'corr={corr:.2f}')
                axes[i, j].set_xlabel(f'{m} Returns')
                axes[i, j].set_ylabel(f'{n} Returns')
                axes[i, j].legend()
                axes[i, j].set_title(f'{m} vs {n}')
        plt.suptitle(f'tau: {self.tau}, tau_ema: {self.tau_ema}', fontsize=16)      
        plt.tight_layout()
        plt.show()
        return fig

    @staticmethod
    def corr_ticks(data_series, index_series, shift):
        # Calculate returns
        m = data_series.name
        agg_dict = {'index': 'first', m: 'mean'}
        data_aux = pd.concat([data_series.reindex(index_series.index), index_series],
                             axis=1).reset_index()
        data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
        grouped = data_aux.groupby(data_aux.index.date)
        data_dict = {date: group for date, group in grouped}
        ret_series = pd.Series(dtype='object')
        for data in data_dict.values():
            ret_aux = np.log(data.loc[:, m].dropna()).diff(periods=shift)
            ret_series = pd.concat([ret_series, ret_aux])
        ret_series = ret_series.dropna()
        return ret_series.corr(ret_series.shift(shift))


class TI_class(ImbalancedBars_class):
    # Tick imbalanced bars
    def __init__(self, tau, tau_ema, burn=10):
        super(TI_class, self).__init__(tau, tau_ema)
        self.__burn = burn

    @property
    def old_value(self):
        return self.__old_value

    @property
    def bt(self):
        return self.__bt

    @property
    def burn(self):
        return self.__burn

    @property
    def tot_n(self):
        return self.__tot_n

    def reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.thres = 0
        self.index = 0
        self.__bt = 1
        self.__old_value = np.nan
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def soft_reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.thres = 0
        self.index += 1
        self.__bt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def initialize(self):
        self.ewma.value = self.__bt
        self.init = False

    def push(self, value, volume=None):
        if self.tot_n < 1:
            self.init = True
        else:
            diff_value = value - self.old_value
            bt = self.signed_tick_vals(diff_value)
            self.__bt = bt
            if self.init:
                self.initialize()
            else:
                self.ewma.push(bt)
            if self.is_burn:
                self.phiT += bt
                self.thres = abs(self.ewma.value) * self.tau
                self.__n += 1
            elif abs(self.phiT + bt) < self.thres:
                self.phiT += bt
                self.__n += 1
            else:
                self.phiT = 0
                self.thres = abs(self.ewma.value) * self.tau
                self.index += 1
                self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return np.nan if self.is_burn else self.index

    def tick_imbalance_params(self, price_series, volume_series=None):
        self.reset()
        price_series = price_series.dropna()
        param_names = ['bt', 'ewma_val', 'phiT', 'thres']
        param_dict = {k: [] for k in param_names}
        for v in price_series.values:
            self.push(v)
            [v.append(getattr(self, k)) for k, v in param_dict.items()]
        return param_dict

    def tick_imbalance_single(self, df_data):
        self.soft_reset()
        dt_index = df_data.index
        df_data = df_data.dropna()
        index_series = pd.Series([self.push(v[0]) for v in df_data.values],
                                 index=df_data.index)
        index_series = index_series.reindex(dt_index).fillna(method='ffill')
        return index_series


class VI_class(ImbalancedBars_class):
    # Volume Imbalanced bars
    def __init__(self, tau, tau_ema, burn=10):
        super(VI_class, self).__init__(tau, tau_ema)
        self.__burn = burn

    @property
    def old_value(self):
        return self.__old_value

    @property
    def bt(self):
        return self.__bt

    @property
    def vt(self):
        return self.__vt

    @property
    def bvt(self):
        return self.__bt * self.__vt

    @property
    def burn(self):
        return self.__burn

    @property
    def tot_n(self):
        return self.__tot_n    

    def reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.thres = 0
        self.index = 0
        self.__bt = 1
        self.__vt = 1
        self.__old_value = np.nan
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def soft_reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.thres = 0
        self.index += 1
        self.__bt = 1
        self.__vt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def initialize(self):
        self.ewma.value = self.__bt * self.__vt
        self.init = False

    def push(self, value, volume):
        self.__vt = volume
        if self.tot_n < 1:
            self.init = True
        else:
            diff_value = value - self.old_value
            bt = self.signed_tick_vals(diff_value)
            self.__bt = bt
            bvt = bt * volume
            if self.init:
                self.initialize()
            else:
                self.ewma.push(bvt)
            if self.is_burn:
                self.phiT += bvt
                self.thres = abs(self.ewma.value) * self.tau
                self.__n += 1
            elif abs(self.phiT + bvt) < self.thres:
                self.phiT += bvt
                self.__n += 1
            else:
                self.phiT = 0
                self.thres = abs(self.ewma.value) * self.tau
                self.index += 1
                self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return np.nan if self.is_burn else self.index

    def tick_imbalance_params(self, price_series, volume_series):
        self.reset()
        price_series = price_series.dropna()
        volume_series = volume_series.dropna()
        param_names = ['bvt', 'ewma_val', 'phiT', 'thres']
        param_dict = {k: [] for k in param_names}
        for p, v in zip(price_series.values, volume_series.values):
            self.push(p, v)
            [v.append(getattr(self, k)) for k, v in param_dict.items()]
        param_dict['bt'] = param_dict['bvt']
        return param_dict

    def tick_imbalance_single(self, df_data):
        self.soft_reset()
        dt_index = df_data.index
        df_data = df_data.dropna()
        index_series = pd.Series([self.push(v[0], v[1]) for v in df_data.values],
                                 index=df_data.index)
        index_series = index_series.reindex(dt_index).fillna(method='ffill')
        return index_series


class TR_class(ImbalancedBars_class):
    # Tick run bars
    def __init__(self, tau, tau_ema, burn=10):
        super(TR_class, self).__init__(tau, tau_ema)
        self.__burn = burn

    @property
    def min_tau(self):
        return self.tau // 3

    @property
    def old_value(self):
        return self.__old_value

    @property
    def bt(self):
        return self.__bt

    @property
    def burn(self):
        return self.__burn

    @property
    def tot_n(self):
        return self.__tot_n

    def reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index = 0
        self.__bt = 1
        self.__old_value = np.nan
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def soft_reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index += 1
        self.__bt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def initialize(self):
        self.ewma.value = .5
        self.ewma_T.value = self.tau
        self.init = False

    def push(self, value, volume=None):
        if self.tot_n < 1:
            self.init = True
        else:
            diff_value = value - self.old_value
            self.__bt = self.signed_tick_vals(diff_value)
            bt = max(self.__bt, 0)
            if self.init:
                self.initialize()
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
            if self.is_burn:
                self.phiT += bt
                self.__n += 1
            elif max(self.phiT, self.__n - self.phiT) < self.thres:
                self.phiT += bt
                self.__n += 1
            else:
                self.ewma.push(self.phiT / self.__n)
                self.ewma_T.push(self.__n)
                self.phiT = 0
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
                self.index += 1
                self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return np.nan if self.is_burn else self.index

    def tick_imbalance_single(self, df_data):
        self.soft_reset()
        dt_index = df_data.index
        df_data = df_data.dropna()
        index_series = pd.Series([self.push(v[0]) for v in df_data.values],
                                 index=df_data.index)
        index_series = index_series.reindex(dt_index).ffill()
        return index_series


class VPIN():
    def __init__(self, vol):
        self.vol_thres = vol
        self.reset()

    @property
    def bt(self):
        return self.__bt

    @property
    def old_value(self):
        return self.__old_value

    def reset(self):
        self.phiT = 0
        self.index = 0
        self.ma_list = []
        self.__bt = 1
        self.vol_count = 0
        self.__old_value = np.nan

    def signed_tick_vals(self, diff_value):
        if abs(diff_value) < tol:
            bt = self.bt
        else:
            bt = np.sign(diff_value)
        return bt

    def soft_reset(self):
        self.phiT = 0
        self.ma_list = []
        self.index += 1
        self.__bt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def push(self, value, volume):
        diff_value = value - self.old_value
        bt = self.signed_tick_vals(diff_value)
        self.__bt = bt
        if self.init:
            self.initialize()
        elif self.vol_count + volume <= self.vol_thres:
            vpin = np.nan
            self.phiT += bt * volume
            self.__n += 1
            self.vol_count += volume
        else:
            vol_diff = self.vol_thres - self.vol_count
            vpin = abs(self.phiT + bt * vol_diff) / self.vol_thres
            self.ma_list.append(vpin)
            self.phiT = bt * (volume - vol_diff)
            self.index += 1
            self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return (self.index, vpin)

    def calc_vpin_single(self, df_data):
        self.soft_reset()
        dt_index = df_data.index
        df_data = df_data.dropna()
        vpin_ser = pd.Series([self.push(*v)[1] for v in df_data.values],
                             index=df_data.index).reindex(dt_index)
        return vpin_ser.dropna()

    def vol_index_single(self, df_data):
        self.soft_reset()
        dt_index = df_data.index
        df_data = df_data.dropna()
        index_ser = pd.Series([self.push(*v)[0] for v in df_data.values],
                              index=df_data.index).reindex(dt_index).ffill()
        return index_ser

    def calc_vpin(self, df_data, window):
        if isinstance(df_data, pd.Series):
            df_data = pd.DataFrame(df_data)
        self.reset()
        # Divide into individual dates
        grouped = df_data.groupby(df_data.index.date)
        data_dict = {date: group for date, group in grouped}
        vpin_ser = pd.Series(dtype='float64')
        for data in data_dict.values():
            vpin_ser = pd.concat([vpin_ser, self.calc_vpin_single(data)])
        return vpin_ser.rolling(window).mean()

    def vol_index(self, df_data):
        if isinstance(df_data, pd.Series):
            df_data = pd.DataFrame(df_data)
        self.reset()
        # Divide into individual dates
        grouped = df_data.groupby(df_data.index.date)
        data_dict = {date: group for date, group in grouped}
        index_ser = pd.Series(dtype='float64')
        for data in data_dict.values():
            index_ser = pd.concat([index_ser, self.vol_index_single(data)])
        return index_ser
