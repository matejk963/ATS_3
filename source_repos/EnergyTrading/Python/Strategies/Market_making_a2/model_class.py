# -*- coding: utf-8 -*-
"""
Created on Tue Nov 21 13:00:12 2023

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
from Math.accumfeatures import MSTD, MA, EMA, DifferentialEMA, DerivativeEMA
from Math.lm_class import kalman
tol = 0.001


class ModelClass():
    __metaclass__ = abc.ABCMeta

    def __init__(self, model_name, weight, burn):
        self.name = model_name
        self.weight = weight
        self._burn = burn

    @abc.abstractmethod
    def fit(self, X):
        pass

    @abc.abstractmethod    
    def predict(self, X):
        pass

    @abc.abstractmethod
    def score(self, X, y, sample_weight=None):
        pass


class simple_model(ModelClass):
    def __init__(self, model, param_list, model_name, weight=1, burn=50,
                 time_model=True, tol=0):
        super().__init__(model_name, weight, burn)
        self.__param_list = param_list
        self.model = model
        self.reset()
        if time_model:
            self.dt = self.dt_1
        else:
            self.dt = self.dt_x
        if isinstance(model, MSTD):
            self.push = self.push_mstd
        elif isinstance(model, kalman):
            self.push = self.push_kalman
        else:
            self.push = self.push
        self._time_model = time_model
        self._tol = tol
        self.inst = ''

    def reset(self):
        self.model = self.model.__class__(*self.__param_list)
        self.z = 0
        self.__init = True
        self.__n = 0

    @property
    def param_list(self):
        if isinstance(self.model, (MSTD, MA)):
            return [x * 2 if k == 'tau' else x for x, k in zip(self.__param_list,
                                                               self.param_keys)]
        else:
            return self.__param_list

    @param_list.setter
    def param_list(self, param_list):
        if isinstance(self.model, (MSTD, MA)):
            self.__param_list = [x / 2 if k == 'tau' else x for x, k in zip(param_list, self.param_keys)]
        else:
            self.__param_list = param_list

    @property
    def param_keys(self):
        if isinstance(self.model, EMA):
            return ['tau', 'value0']
        elif isinstance(self.model, MA):
            return ['tau', 'N', 'value0']
        elif isinstance(self.model, MSTD):
            if self.name == '3band_std':
                return ['tau', 'N', 'p', 'value0', 'w_std']
            else:
                return ['tau', 'N', 'p', 'value0']
        elif isinstance(self.model, DifferentialEMA):
            return ['tau', 'value0']
        elif isinstance(self.model, DerivativeEMA):
            return ['tau', 'n', 'gamma', 'value0']
        elif isinstance(self.model, kalman):
            return []
        else:
            raise ValueError('Unknown model %s' % self.model)

    def update_params(self, param_dict):
        self.param_list = [param_dict[k] if k in param_dict.keys() else v
                           for k, v in zip(self.param_keys, self.param_list)]

    @property
    def classifier(self):
        return False

    @staticmethod    
    def dt_1(dx):
        return 1

    @staticmethod    
    def dt_x(dx):
        return abs(dx)

    def push(self, z):
        if self.__init:
            self.z = z
            self.__init = False
            dt = self.dt(self._tol)
        else:
            dt = self.dt(z - self.z)
        if dt > self._tol:
            value = self.model.push(z, dt)
            self.z = z
            self.__n += 1
        else:
            value = self.model.value
        if self.__n < self._burn:
            return np.nan
        else:
            return value

    def push_mstd(self, z):
        if self.__init:
            self.z = z
            self.__init = False
            dt = .0001
            tol = 0
        else:
            dt = self.dt(z - self.z)
            tol = self._tol
        if dt > tol:
            std = self.model.push(z, dt)
            mean = self.model.mean.value
            self.z = z
            self.__n += 1
        else:
            std = self.model.value
            mean = self.model.mean.value
        if self.__n < self._burn:
            return [np.nan, np.nan]
        else:
            return [mean, std]

    def push_kalman(self, z, dt=None):
        pass

    def fit(self, X, y=None, z=None):
        pass

    def predict(self, X):
        return np.asarray([self.push(x) for x in X])

    def score(self, X, y, sample_weight=None):
        pass

    def mm_model(self, df_data, params_dict, raw_bool=True):
        if self.name == 'ema':
            margin = params_dict['margin']
            w = params_dict['w']
            eql_p = params_dict['eql_p']
            return self.__model_ema(df_data, margin, w, eql_p, raw_bool)
        elif self.name in ['3band_std']:
            w_std = params_dict['w_std']
            return self.__model_ema_3band_std(df_data, w_std, raw_bool)
        elif self.name == 'mstd':
            margin = params_dict['margin']
            w = params_dict['w']
            w1 = params_dict['w1']
            w_std = params_dict['w_std']
            eql_p = params_dict['eql_p']
            return self.__model_mstd(df_data, margin, w, w1, w_std, eql_p, raw_bool)
        elif self.name == 'ema_mstd':
            margin = params_dict['margin']
            w = params_dict['w']
            w1 = params_dict['w1']
            w_std = params_dict['w_std']
            df_model = params_dict['df_model'][self.inst]
            return self.__model_ema_mstd(df_data, margin, w, w1, w_std, df_model, raw_bool)
        elif self.name == 'ema_hist':
            w = params_dict['w']
            w1 = params_dict['w1']
            w_std = params_dict['w_std']
            df_model = params_dict['df_model'][self.inst]
            return self.__model_ema_hist(df_data, w, w1, w_std, df_model, raw_bool)
        else:
            raise ValueError('Unknown market making model type %s' % self.name)

    def mm_model_raw(self, df_data, reset_bool=True):
        if self.name in ['ema', 'mstd', 'ma', 'dt', 'ema_mstd', 'ema_hist']:
            return pd.DataFrame(self.__model_from_data(df_data, reset_bool), index=df_data.index).ffill()
        

        else:
            raise ValueError('Unknown market making model type %s' % self.name)

    def __model_ema_old(self, df_data, margin, w, eql_p):
        bands = []
        for day, group in df_data.groupby(pd.Grouper(freq='B')):
            mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
            mid_list = mid_ser.values
            # Reset model
            self.update_params({'value0': mid_list[0]})
            self.reset()
            # Calc model
            ema_list = self.predict(mid_list)
            ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
            bands.extend([[x - margin, x, x + margin] for x in ema_list])
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_mstd_old(self, df_data, margin, w, w1, w_std, eql_p):
        bands = []
        for day, group in df_data.groupby(pd.Grouper(freq='B')):
            mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
            mid_list = mid_ser.values
            # Reset model
            self.update_params({'value0': mid_list[0]})
            self.reset()
            # Calc model
            std_list = self.predict(mid_list)
            ema_list = [w * eql_p + (1 - w) * x[0] for x in std_list]
            mrg_list = [w1 * margin + (1 - w1) * m[1] * w_std for m in std_list]
            bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_ema(self, df_data, margin, w, eql_p, raw_bool):
        if raw_bool:
            ema_list = self.__model_from_data(df_data, True)
        else:
            ema_list = [x[0] for x in df_data.values]
        ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
        bands = [[x - margin, x, x + margin] for x in ema_list]
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_mstd(self, df_data, margin, w, w1, w_std, eql_p, raw_bool):
        if raw_bool:
            std_list = self.__model_from_data(df_data, True)
        else:
            std_list = df_data.values
        ema_list = [w * eql_p + (1 - w) * x[0] for x in std_list]
        mrg_list = [w1 * margin + (1 - w1) * m[1] * w_std for m in std_list]
        bands = [[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)]
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_ema_3band_std(self, df_data, w_std, raw_bool,
                              std_weights=[-3,-2.5,-2,-1,0,1,2,2.5,3]):
        # ts = df_data.index
        mid_ser = .5 * (df_data.loc[:, 'bid'] + df_data.loc[:, 'ask'])
        mid_list = mid_ser.values
        if raw_bool:
            ema_list = self.__model_from_data(df_data, True)
        else:
            ema_list = [x[0] for x in df_data.values]
        
        ema_list = [x[0] for x in ema_list]
        std_list = [self.push_mstd(x) for x in mid_list]
        mrg_list = [m[1] * w_std for m in std_list]
        
        bands = [[a*s + m for a in std_weights] for m,s in zip(ema_list, mrg_list)]
        
        # bands = [[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)]
        return pd.DataFrame(bands, index=df_data.index).ffill()
    
    def __model_ema_mstd(self, df_data, margin, w, w1, w_std, df_model, raw_bool):
        ts = df_data.index
        df_model_aux = df_model.reindex(ts).ffill()
        if raw_bool:
            ema_list = self.__model_from_data(df_data, True)
        else:
            ema_list = [x[0] for x in df_data.values]
        mdl_list = df_model_aux.loc[df_data.index, :].values
        ema_list = [w * m[0] + (1 - w) * x for x, m in zip(ema_list, mdl_list)]
        mrg_list = [w1 * margin + (1 - w1) * m[1] * w_std for m in mdl_list]
        bands = [[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)]
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_ema_hist(self, df_data, w, w1, w_std, df_model, raw_bool):
        ts = df_data.index
        df_model_aux = df_model.reindex(ts.union(df_model.index)).ffill().reindex(ts)
        if raw_bool:
            ema_list = self.__model_from_data(df_data, True)
        else:
            ema_list = [x[0] for x in df_data.values]
        mdl_list = df_model_aux.loc[df_data.index, :].values
        ema_list = [w * m[0] + (1 - w) * x for x, m in zip(ema_list, mdl_list)]
        mrg_list = [(w1 * m[2] + (1 - w1) * m[1]) * w_std for m in mdl_list]
        bands = [[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)]
        return pd.DataFrame(bands, index=df_data.index).ffill()

    def __model_from_data(self, df_data, reset_bool):
        model_list = []
        reset_bool_ = True
        for day, group in df_data.groupby(pd.Grouper(freq='B')):
            if len(group.index) == 0:
                continue
            try:
                mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
            except(KeyError):
                mid_ser = group.iloc[:, 0]
            mid_list = mid_ser.values
            # Reset model
            if reset_bool_:
                self.update_params({'value0': mid_list[0]})
                self.reset()
                reset_bool_ = reset_bool
            # Calc model
            model_list.extend(self.predict(mid_list))
        return model_list
    
    def __model_bands_from_data(self, df_data, reset_bool):
        model_list = []
        
        reset_bool_ = True
        for day, group in df_data.groupby(pd.Grouper(freq='B')):
            if len(group.index) == 0:
                continue
            try:
                mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
            except(KeyError):
                mid_ser = group.iloc[:, 0]
            mid_list = mid_ser.values
            # Reset model
            if reset_bool_:
                self.update_params({'value0': mid_list[0]})
                self.reset()
                reset_bool_ = reset_bool
            # Calc model
            model_pred = self.predict(mid_list)
            # Add bands
            std_list = [self.push_mstd(x) for x in mid_list]
            ema_list = [x[0] for x in model_list]
            model_list.extend(model_pred)
            # Add bands
            std_list = [self.push_mstd(x) for x in mid_list]
        return model_list


class kalman_reg(ModelClass):
    def __init__(self, model, param_list, model_name, weight=1, burn=50,
                 init_dict={}):
        super().__init__(model_name, weight, burn)
        self.model = model
        self.param_list = param_list
        if not init_dict:
            d = self.model.dim
            self.__x_init = np.zeros((d, 1))
            self.__P_init = np.eye(d)
        else:
            self.__x_init = init_dict['x']
            self.__P_init = init_dict['P']
        self.reset()

    def reset(self):
        self.model = self.model.__class__(*self.__param_list)
        self._x = self.__x_init
        self._P = self.__P_init
        self.__n = 0

    def soft_reset(self):
        self.model = self.model.__class__(*self.__param_list)

    @property
    def param_list(self):
        if self.model.name in ['UKF', 'EKF', 'KF']:
            q, r = self.__param_list[:2]
            sigma = np.sqrt(q[0][0])
            par_sigma = np.sqrt(r)
            param_list_n = [sigma, par_sigma]
            param_list_n.extend(self.__param_list[2:])
            return param_list_n
        else:
            return self.__param_list

    @param_list.setter
    def param_list(self, param_list):
        if self.model.name in ['UKF', 'EKF', 'KF']:
            r = param_list[1] ** 2
            q = np.eye(self.model.dim) * r
            q[0][0] = param_list[0] ** 2
            param_list_n = [q, r]
            param_list_n.extend(param_list[2:])
            self.__param_list = param_list_n
        else:
            self.__param_list = param_list

    @property
    def param_keys(self):
        if self.model.name == 'KF':
            return ['sigma', 'par_sigma']
        elif self.model.name == 'EKF':
            return ['sigma', 'par_sigma', 'dt']
        elif self.model.name == 'UKF':
            return ['sigma', 'par_sigma', 'dt', 'alpha', 'kappa', 'beta']
        else:
            raise ValueError('Unknown model %s' % self.model)

    def update_params(self, param_dict):
        self.param_list = [param_dict[k] if k in param_dict.keys() else v
                           for k, v in zip(self.param_keys, self.param_list)]

    def fit(self, Z):
        x = self._x
        P = self._P
        for z in Z:
            x, P = self.model.step(z, x, P)
            self.__n += 1
        self._x, self._P = x, P
        return x, P

    def calc_period(self, Z):
        x = self._x
        P = self._P
        period_list = []
        for z in Z:
            x, P = self.model.step(z, x, P)
            period_list.append(np.log(2) / x[1][0] if x[1][0] > tol else np.log(2) / tol)
            self.__n += 1
        self._x, self._P = x, P
        return period_list

    def score(self, u_vec=None, v_vec=None, idx_score=None):
        if u_vec is None:
            u_vec = self.model._u
        if v_vec is None:
            v_vec = self.model._v
        if idx_score is None:
            pass
        else:
            u_vec = [x for x, i in zip(u_vec[1:], idx_score) if i]
            v_vec = [x for x, i in zip(v_vec[1:], idx_score) if i]
        return self.model.score(u_vec, v_vec)


class DualModelMM():
    def __init__(self, model_reg, model_ema, model_diff, factor=1):
        self.model_reg = model_reg
        self.model_ema = model_ema
        self.model_diff = model_diff
        self.factor = factor

    def reset(self):
        self.model_reg.reset()
        self.model_ema.reset()
        self.model_diff.reset()

    @property
    def param_keys(self):
        param_keys = ['factor']
        param_keys.extend(self.model_ema.param_keys)
        param_keys.extend([k for k in self.model_diff.param_keys if k not in param_keys])
        return param_keys

    def update_params(self, param_dict):
        if 'factor' in param_dict.keys():
            self.factor = param_dict['factor']
        self.model_ema.update_params({k: param_dict[k] for k in self.model_ema.param_keys})
        self.model_diff.update_params({k: param_dict[k] * self.factor for k in self.model_diff.param_keys if k == 'tau'})

    def mm_model(self, df_data, params_dict, raw_bool=True):
        if self.name == 'ema':
            margin = params_dict['margin']
            w = params_dict['w']
            eql_p = params_dict['eql_p']
            return self.__model_ema(df_data, margin, w, eql_p, raw_bool)
        elif self.name == 'mstd':
            margin = params_dict['margin']
            w = params_dict['w']
            w1 = params_dict['w1']
            w_std = params_dict['w_std']
            eql_p = params_dict['eql_p']
            return self.__model_mstd(df_data, margin, w, w1, w_std, eql_p, raw_bool)
        elif self.name == 'ema_mstd':
            margin = params_dict['margin']
            w = params_dict['w']
            w1 = params_dict['w1']
            w_std = params_dict['w_std']
            df_model = params_dict['df_model'][self.inst]
            return self.__model_ema_mstd(df_data, margin, w, w1, w_std, df_model, raw_bool)
        else:
            raise ValueError('Unknown market making model type %s' % self.name)

    def mm_model_raw(self, df_data):
        # Calculate ema model on data
        df_ema = self.model_ema.mm_model_raw(df_data)
        X_data = (df_data.iloc[:, 0] - df_ema.iloc[:, 0]).values.reshape(-1, )
        df_period = pd.Series(self.model.calc_period(X_data), index=df_data.index)
        # Calculate derivation model on data
        # df_dt = self.model_diff.mm_model_raw(df_data)
        # Unify models
        return pd.concat([df_ema.iloc[:, 0], df_period], axis=1)
