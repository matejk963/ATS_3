# -*- coding: utf-8 -*-
"""
Created on Fri Aug 30 13:52:43 2024

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.linear_model import RidgeCV, LassoCV
from sklearn.metrics import confusion_matrix
from Math.lm_class import LinearModel, LogisticModel, kalman1d, kalman
from filterpy.kalman import KalmanFilter
from Math.ti_class import TI_class, TR_class
from Math.accumfeatures import MSTD
from Strategies.Sparse_momentum.ob_attributes import OB_attributes


class LLEnsamble():
    def __init__(self):
        self.model_list = []

    @property
    def n(self):
        return len(self.model_list)

    def append(self, ll_model):
        if isinstance(ll_model, LLM):
            self.model_list.append(ll_model)
        else:
            raise ValueError("")


class LLM():
    __metaclass__ = abc.ABCMeta

    def __init__(self, model_name, weight):
        self.model_name = model_name
        self.weight = weight

    @abc.abstractmethod
    def fit(self, X, y):
        pass

    @abc.abstractmethod
    def predict(self, X, y):
        pass

    @staticmethod
    def score(pred_dict, score_class):
        score_dict = {d: [] for d in pred_dict.keys()}
        for d, data in pred_dict.items():
            score_class.reset()
            y_pred = data['y_pred']
            y_true = data['y_true']
            score_dict[d].extend([score_class.score(y_p, y_t)
                                  for y_p, y_t in zip(y_pred, y_true)])
        return score_dict

    @staticmethod
    def calc_sigma_res(y_pred, y_true):
        # Residuals
        residuals = y_true - y_pred
        # Estimate of sigma (standard deviation of residuals)
        return np.std(residuals, ddof=1)

    def eval_model_data(self, data_dict):
        out_dict = {d: {} for d in data_dict['keys']}
        for d in data_dict['keys']:
            # Data
            X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
            X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
            # Training
            self.fit(X_train, y_train)
            # Testing
            y_pred = self.predict(X_tests, y_tests)
            # Save data
            out_dict[d]['y_pred'] = y_pred
            out_dict[d]['y_true'] = y_tests
        return out_dict


class LMOnline(LLM):
    def __init__(self, n, intercept, l1, l2, a, b, adaptive_l1=False,
                 norm_g=True):
        self.model = LinearModel(n, intercept, lambda1=l1, lambda2=l2, alpha=a,
                                 beta=b, adaptive_l1=adaptive_l1, norm_g=norm_g)

    @property
    def intercept(self):
        return self.model.intercept

    def fit(self, X_train, y_train):
        self.model.reset()
        y_pred = []
        for x_, y in zip(X_train, y_train):
            if self.intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            self.model.push(x, y)
            y_pred.append(self.model.predict(x))
        return self.calc_sigma_res(np.asarray(y_pred), y_train)

    def predict(self, X_tests, y_tests):
        # Model is training itself and predicting next outcome
        y_pred = []
        for x_, y in zip(X_tests, y_tests):
            if self.intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            self.model.push(x, y)
            y_pred.append(self.model.predict(x))
        return np.asarray(y_pred)

    def predict_live(self, df_data_sample):
        x_cols = [x for x in df_data_sample.columns if x[0] == 'X']
        trd_cols = [x for x in df_data_sample.columns if x[:3] == 'trd']
        data_X = df_data_sample.loc[:, x_cols].values
        data_y = df_data_sample.loc[:, 'y'].values
        data_trd = df_data_sample.loc[:, trd_cols].values
        # Model is training itself and predicting next outcome
        y_pred = []
        for x_, y, trd in zip(data_X, data_y, data_trd):
            if not np.isnan(x_).any():
                # Retrain model
                if self.intercept:
                    x = np.concatenate([[1], x_])
                else:
                    x = x_
                if np.asarray(x).size < 2:
                    self.model.push(np.array(x).reshape(1,), y)
                else:
                    self.model.push(x, y)
            if not np.isnan(trd).any():
                # Predict
                if np.asarray(trd).size < 2:
                    y_pred.append(self.model.predict(np.array(trd).reshape(1,)))
                else:
                    y_pred.append(self.model.predict(trd))
        return np.asarray(y_pred)


class LGOnline(LLM):
    def __init__(self, n, intercept, l1, l2, a, b, adaptive_l1=False,
                 norm_g=True):
        self.model = LogisticModel(n, intercept, lambda1=l1, lambda2=l2, alpha=a,
                                   beta=b, adaptive_l1=adaptive_l1, norm_g=norm_g)

    @property
    def intercept(self):
        return self.model.intercept

    def fit(self, X_train, y_train):
        self.model.reset()
        for x_, y in zip(X_train, y_train):
            if self.intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            self.model.push(x, y)

    def predict(self, X_tests, y_tests):
        # Model is training itself and predicting next outcome
        y_pred = []
        for x_, y in zip(X_tests, y_tests):
            if self.intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            self.model.push(x, y)
            y_pred.append(self.model.predict(x))
        return np.asarray(y_pred)

    def predict_live(self, df_data_sample):
        x_cols = [x for x in df_data_sample.columns if x[0] == 'X']
        trd_cols = [x for x in df_data_sample.columns if x[:3] == 'trd']
        data_X = df_data_sample.loc[:, x_cols].values
        data_y = df_data_sample.loc[:, 'y'].values
        data_trd = df_data_sample.loc[:, trd_cols].values
        # Model is training itself and predicting next outcome
        y_pred = []
        for x_, y, trd in zip(data_X, data_y, data_trd):
            if not np.isnan(x_).any():
                # Retrain model
                if self.intercept:
                    x = np.concatenate([[1], x_])
                else:
                    x = x_
                if np.asarray(x).size < 2:
                    self.model.push(np.array(x).reshape(1,), y)
                else:
                    self.model.push(x, y)
            if not np.isnan(trd).any():
                # Predict
                if np.asarray(trd).size < 2:
                    y_pred.append(self.model.predict(np.array(trd).reshape(1,)))
                else:
                    y_pred.append(self.model.predict(trd))
        return np.asarray(y_pred)


class LMOffline(LLM):
    def __init__(self, intercept, model_type='linear', alpha=1.0,
                 cv_bool=False, cv=5):
        if model_type == 'linear':
            self.model = LinearRegression(fit_intercept=intercept)
        elif model_type == 'ridge':
            self.model = Ridge(alpha=alpha, fit_intercept=intercept)
        elif model_type == 'lasso':
            self.model = Lasso(alpha=alpha, fit_intercept=intercept)
        else:
            raise ValueError('LMOffline: unknown model {model_type}')
        self.model_type = model_type
        self.alpha = alpha
        self.cv_bool = cv_bool
        self.cv = cv
        self.intercept = intercept

    def fit(self, X_train, y_train):
        if self.cv_bool:
            if self.model_type == 'ridge':
                ridge_cv = RidgeCV(alphas=self.alpha, cv=self.cv)
                ridge_cv.fit(X_train, y_train)
                optimal_alpha = ridge_cv.alpha_
                self.model = Ridge(alpha=optimal_alpha, fit_intercept=self.intercept)
            elif self.model_type == 'lasso':
                lasso_cv = LassoCV(alphas=self.alpha, cv=self.cv)
                lasso_cv.fit(X_train, y_train)
                optimal_alpha = lasso_cv.alpha_
                self.model = Lasso(alpha=optimal_alpha, fit_intercept=self.intercept)
        self.model.fit(X_train, y_train)
        return self.calc_sigma_res(self.model.predict(X_train), y_train)

    def predict(self, X_tests, y_tests):
        return self.model.predict(X_tests)

    def predict_live(self, df_data_sample):
        trd_cols = [x for x in df_data_sample.columns if x[:3] == 'trd']
        if len(trd_cols) < 2:
            X_tests = df_data_sample.loc[:, trd_cols].dropna().values.reshape(-1,1)
        else:
            X_tests = df_data_sample.loc[:, trd_cols].dropna().values
        return self.model.predict(X_tests)


class DataClass():
    def __init__(self, mkt, tau, tau_ema, diff_bool=True, vol_bool=False,
                 scale_bool=True, isEma=False, n_ema=15):
        self.mkt = mkt
        self.tau = tau
        self.tau_ema = tau_ema
        self.diff_bool = diff_bool
        self.vol_bool = vol_bool
        self.scale_bool = scale_bool
        self.isEMA = isEma
        self.n_ema = n_ema
        self.__scale_params_dict = {}
        self.__run_dates = []

    @property
    def scale_params_dict(self):
        return self.__scale_params_dict

    @property
    def run_dates(self):
        return self.__run_dates

    def split_data(self, data_dict, date_range_dict, n_test):
        out_dict = {k: {'train': {}, 'tests': {}, 'keys': []} for k in data_dict.keys()}
        date_s = {k: (v[-n_test], v[-1]) for k, v in date_range_dict.items()}
        for m, data in data_dict.items():
            y_ser = pd.Series(data['y'], index=data['ts'])
            X_df = pd.DataFrame(data['X'], index=data['ts'])
            if data['X_p']['x'].shape[1] < 2:
                cols_x = ['x']
            else:
                cols_x = ['x_' + str(i) for i in range(data['X_p']['x'].shape[1])]
            Xpx_df = pd.DataFrame(data['X_p']['x'], index=data['X_p']['index'], columns=cols_x)
            Xpy_df = pd.DataFrame({k: v for k, v in data['X_p'].items() if k != 'x'}).set_index('index')
            Xp_df = pd.concat([Xpx_df, Xpy_df], axis=1)
            del Xpx_df, Xpy_df, cols_x
            for d, date_tuple in date_s.items():
                date_test, date_end = date_tuple
                date_end += pd.Timedelta(hours=24)
                date = date_test.date()
                out_dict[m]['train'][date] = {}
                out_dict[m]['tests'][date] = {}
                y_train, y_tests = y_ser.loc[:date_test], y_ser.loc[date_test:date_end]
                X_train, X_tests = X_df.loc[:date_test, :], X_df.loc[date_test:date_end, :]
                # Prices
                Xp_tests = Xp_df.loc[date_test:date_end, :]
                # Train
                out_dict[m]['train'][date]['y'] = y_train.values
                out_dict[m]['train'][date]['X'] = X_train.values
                out_dict[m]['train'][date]['ts'] = y_train.index
                # Tests
                out_dict[m]['tests'][date]['y'] = y_tests.values
                out_dict[m]['tests'][date]['X'] = X_tests.values
                out_dict[m]['tests'][date]['X_p'] = self.to_dict_xp(Xp_tests)
                out_dict[m]['tests'][date]['ts'] = y_tests.index
                # Keys
                out_dict[m]['keys'].append(date)
                self.__run_dates.append(date)
        return out_dict

    def scale_data_dict(self, data_dict):
        if not self.scale_bool:
            return data_dict
        scaled_dict = {'keys': [], 'train': {}, 'tests': {}}
        for d in data_dict['keys']:
            scaled_dict['train'][d] = {}
            scaled_dict['tests'][d] = {}
            # Data
            X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
            X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
            # yp_tests, Xp_tests = [data_dict['tests'][d][k] for k in ['y_p', 'X_p']]
            Xp_dict = data_dict['tests'][d]['X_p']
            Xp_tests = data_dict['tests'][d]['X_p']['x']
            # Scale
            try:
                X_train_s, y_train_s, X_tests_s, y_tests_s = self.scale_data_reg(X_train, y_train, X_tests, y_tests, d)
            except:
                print(d)
            # Scale trades output
            _, _, Xp_s, _ = self.scale_data_reg(X_train, y_train, Xp_tests, y_tests, d)
            # Write to dictionary
            scaled_dict['train'][d]['X'], scaled_dict['train'][d]['y'] = X_train_s, y_train_s
            scaled_dict['tests'][d]['X'], scaled_dict['tests'][d]['y'] = X_tests_s, y_tests_s
            scaled_dict['tests'][d]['X_p'] = {'index': Xp_dict['index'], 'x': Xp_s, 't_y': Xp_dict['t_y']}
            scaled_dict['train'][d]['ts'] = data_dict['train'][d]['ts']
            scaled_dict['tests'][d]['ts'] = data_dict['tests'][d]['ts']
            scaled_dict['keys'].append(d)
        return scaled_dict

    def rescale_out_dict(self, scaled_out_dict):
        if not self.scale_bool:
            return scaled_out_dict
        rescaled_dict = {k: {} for k in scaled_out_dict.keys()}
        for d, dct in scaled_out_dict.items():
            y_scaled = dct['y_pred']
            y_true_s = dct['y_true']
            y_pred_rs = self.rescale_data_reg(y_scaled, d)
            y_true_rs = self.rescale_data_reg(y_true_s, d)
            rescaled_dict[d]['y_pred'] = y_pred_rs
            rescaled_dict[d]['y_true'] = y_true_rs
        return rescaled_dict

    def data_process(self, df_data_p, df_data_v, km_bool):
        if df_data_v is None:
            df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
            df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
        preds_var = [x for x in df_data_p.columns]
        # Output dictionary
        out_dict = {k: {} for k in preds_var}
        # Ticks
        data_aux = self.tick_data(df_data_p, df_data_v, self.mkt,
                                  self.tau, self.tau_ema)
        vol_cols = [k + '_v' for k in df_data_v.columns]
        df_vol = data_aux.loc[:, vol_cols]
        data_aux = data_aux.loc[:, df_data_p.columns]
        grouped = data_aux.groupby(data_aux.index.date)
        data_dict = {date: group for date, group in grouped}
        trds_dict = {date: group for date, group in df_data_p.groupby(df_data_p.index.date)}
        for n in preds_var:
            pred_var = [x for x in df_data_p.columns if x == n]
            regs_var = [x for x in df_data_p.columns if x != n]
            df_ret = pd.DataFrame([])
            df_price = pd.DataFrame([])
            for date, data in data_dict.items():
                if km_bool:
                    data_s, data_p = self.price_process_km(data)
                else:
                    data_s, data_p = data, None
                df_aux = self.data_process_mdl(trds_dict[date], data, data_s, data_p,
                                               pred_var, regs_var, km_bool)
                # Differentiate
                y_series = data_s.loc[:, n].dropna()
                data_s = data_s.reindex(y_series.index)
                data_s.loc[:, n] = y_series
                if self.diff_bool:
                    ret_aux = np.log(data_s.ffill()).diff()
                else:
                    ret_aux = data_s.dropna()
                df_ret = pd.concat([df_ret, ret_aux])
                df_price = pd.concat([df_price, df_aux])
            df_ret = df_ret.dropna()
            df_price = df_price.dropna()
            if self.vol_bool:
                df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
                regs_var.extend([x for x in df_vol.columns])
            else:
                df_data = df_ret
            # Model
            y = df_data.loc[:, pred_var].values.reshape(-1,)
            X = df_data.loc[:, regs_var].values.reshape(-1,len(regs_var))
            # X, y = KFSmoother(X, y)
            out_dict[n]['y'] = y
            out_dict[n]['X'] = X
            out_dict[n]['X_p'] = self.to_dict_xp(df_price)
            out_dict[n]['ts'] = df_ret.index
        return out_dict

    def data_process_2(self, df_data_p, df_data_v, km_bool):
        if df_data_v is None:
            df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
            df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
        pred_var = [x for x in df_data_p.columns if x == self.mkt]
        regs_var = [x for x in df_data_p.columns if x != self.mkt]
        # Output dictionary
        out_dict = {k: {} for k in regs_var}
        # Ticks
        data_aux = self.tick_data(df_data_p, df_data_v, self.mkt,
                                  self.tau, self.tau_ema)
        vol_cols = [k + '_v' for k in df_data_v.columns]
        df_vol = data_aux.loc[:, vol_cols]
        data_aux = data_aux.loc[:, df_data_p.columns]
        grouped = data_aux.groupby(data_aux.index.date)
        data_dict = {date: group for date, group in grouped}
        trds_dict = {date: group for date, group in df_data_p.groupby(df_data_p.index.date)}
        for n in regs_var:
            df_ret = pd.DataFrame([])
            df_price = pd.DataFrame([])
            pair_l = [pred_var[0], n]
            reg_l = [n]
            for date, data_ in data_dict.items():
                data = data_.loc[:, pair_l]
                if km_bool:
                    data_s, data_p = self.price_process_km(data)
                else:
                    data_s, data_p = data, None
                df_aux = self.data_process_mdl(trds_dict[date], data, data_s, data_p,
                                               pred_var, reg_l, km_bool)
                # Differentiate
                y_series = data_s.loc[:, self.mkt].dropna()
                data_s = data_s.reindex(y_series.index)
                data_s.loc[:, self.mkt] = y_series
                if self.diff_bool:
                    ret_aux = np.log(data_s.ffill()).diff()
                else:
                    ret_aux = data_s.dropna()
                df_ret = pd.concat([df_ret, ret_aux])
                df_price = pd.concat([df_price, df_aux])
            df_ret = df_ret.dropna()
            df_price = df_price.dropna()
            if self.vol_bool:
                df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
                reg_l.extend([x for x in df_vol.columns])
            else:
                df_data = df_ret
            # Model
            y = df_data.loc[:, pred_var].values.reshape(-1,)
            X = df_data.loc[:, reg_l].values.reshape(-1,len(reg_l))
            # X, y = KFSmoother(X, y)
            out_dict[n]['y'] = y
            out_dict[n]['X'] = X
            out_dict[n]['X_p'] = self.to_dict_xp(df_price)
            out_dict[n]['ts'] = df_ret.index
        return out_dict

    def data_process_3(self, df_data_p, df_data_v, km_bool, reg_aux=[]):
        if reg_aux:
            return self.data_process_4(df_data_p, df_data_v, km_bool, reg_aux)
        trd_clmns = [x for x in df_data_p.columns if x[-3:] != 'aux']
        if df_data_v is None:
            df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
            df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
        pred_var = [x for x in trd_clmns if x == self.mkt]
        regs_var = [x for x in trd_clmns if x != self.mkt]
        # Output dictionary
        out_dict = {k: {} for k in regs_var}
        # Ticks
        data_aux = self.tick_data(df_data_p, df_data_v, self.mkt,
                                  self.tau, self.tau_ema)
        vol_cols = [k + '_v' for k in trd_clmns]
        df_vol = data_aux.loc[:, vol_cols]
        data_aux = data_aux.loc[:, df_data_p.columns]
        grouped = data_aux.groupby(data_aux.index.date)
        data_dict = {date: group for date, group in grouped}
        trds_dict = {date: group for date, group in df_data_p.groupby(df_data_p.index.date)}
        for n in regs_var:
            df_ret = pd.DataFrame([])
            df_price = pd.DataFrame([])
            pair_l = [pred_var[0], n]
            reg_l = [n]
            for date, data_ in data_dict.items():
                data = data_.loc[:, pair_l]
                if km_bool:
                    data_s, data_p = self.price_process_km(data)
                else:
                    data_s, data_p = data, None
                df_aux = self.data_process_mdl(trds_dict[date], data, data_s, data_p,
                                               pred_var, reg_l, km_bool)
                # Differentiate
                # y_series = data_s.loc[:, self.mkt].dropna()
                # data_s = data_s.reindex(y_series.index)
                # data_s.loc[:, self.mkt] = y_series
                if self.diff_bool:
                    # ret_aux = np.log(data_s.ffill()).diff()
                    ret_aux = np.log(data_s.dropna()).diff()
                else:
                    ret_aux = data_s.dropna()
                df_ret = pd.concat([df_ret, ret_aux])
                df_price = pd.concat([df_price, df_aux])
            df_ret = df_ret.dropna()
            df_price = df_price.dropna()
            if self.vol_bool:
                df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
                reg_l.extend([x for x in df_vol.columns])
            else:
                df_data = df_ret
            # Model
            y = df_data.loc[:, pred_var].values.reshape(-1,)
            X = df_data.loc[:, reg_l].values.reshape(-1,len(reg_l))
            # X, y = KFSmoother(X, y)
            out_dict[n]['y'] = y
            out_dict[n]['X'] = X
            out_dict[n]['X_p'] = self.to_dict_xp(df_price)
            out_dict[n]['ts'] = df_ret.index
        return out_dict

    def data_process_4(self, df_data_p, df_data_v, km_bool, reg_aux):
        trd_clmns = [x for x in df_data_p.columns if x[-3:] != 'aux']
        if df_data_v is None:
            df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
            df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
        pred_var = [x for x in trd_clmns if x == self.mkt]
        regs_var = [x for x in trd_clmns if x != self.mkt]
        # Output dictionary
        out_dict = {k: {} for k in regs_var}
        for n in regs_var:
            pair_l = [pred_var[0], n]
            pair_l.extend(reg_aux)
            reg_l = pair_l[1:]
            # Ticks
            df_data_p_, df_data_v_ = df_data_p.loc[:, pair_l], df_data_v.loc[:, pair_l]
            if reg_aux:
                # Set nan for mids when lead is not traded
                df_data_p_.loc[df_data_p_.loc[:, n].isna(), reg_aux] = np.nan
                df_data_v_.loc[df_data_v_.loc[:, n].isna(), reg_aux] = np.nan
            data_aux = self.tick_data(df_data_p_, df_data_v_, self.mkt,
                                      self.tau, self.tau_ema)
            vol_cols = [k + '_v' for k in pair_l[:2]]
            df_vol = data_aux.loc[:, vol_cols]
            data_aux = data_aux.loc[:, df_data_p_.columns]
            grouped = data_aux.groupby(data_aux.index.date)
            data_dict = {date: group for date, group in grouped}
            trds_dict = {date: group for date, group in df_data_p_.groupby(df_data_p_.index.date)}
            
            df_ret = pd.DataFrame([])
            df_price = pd.DataFrame([])
            
            for date, data_ in data_dict.items():
                data = data_.loc[:, pair_l]
                
                if km_bool:
                    data_s, data_p = self.price_process_km(data)
                else:
                    data_s, data_p = data, None
                df_aux = self.data_process_mdl(trds_dict[date], data, data_s, data_p,
                                               pred_var, reg_l, km_bool)
                # Differentiate
                # y_series = data_s.loc[:, self.mkt].dropna()
                # data_s = data_s.reindex(y_series.index)
                # data_s.loc[:, self.mkt] = y_series
                if self.diff_bool:
                    # ret_aux = np.log(data_s.ffill()).diff()
                    ret_aux = np.log(data_s.dropna()).diff()
                else:
                    ret_aux = data_s.dropna()
                df_ret = pd.concat([df_ret, ret_aux])
                df_price = pd.concat([df_price, df_aux])
            df_ret = df_ret.dropna()
            df_price = df_price.dropna()
            if self.vol_bool:
                df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
                reg_l.extend([x for x in df_vol.columns])
            else:
                df_data = df_ret
            # Model
            y = df_data.loc[:, pred_var].values.reshape(-1,)
            X = df_data.loc[:, reg_l].values.reshape(-1,len(reg_l))
            # X, y = KFSmoother(X, y)
            out_dict[n]['y'] = y
            out_dict[n]['X'] = X
            out_dict[n]['X_p'] = self.to_dict_xp(df_price)
            out_dict[n]['ts'] = df_ret.index
        return out_dict

    def prepare_model_trds(self, df_data_p, mkt, model_class, data_dict):
        df_data_lag = df_data_p.loc[:, mkt]
        df_data_all = df_data_p.dropna(how='all')
        grouped = df_data_lag.groupby(df_data_lag.index.date)
        price_dict = {date: group.dropna() for date, group in grouped if date in data_dict['keys']}
        grouped_all = df_data_all.groupby(df_data_all.index.date)
        out_dict = {k: [] for k in data_dict['keys']}
        sigma_dict = {k: [] for k in data_dict['keys']}
        for dt, price_ser in price_dict.items():
            sigma_dict[dt] = {}
            # Train model
            X_train, y_train = [data_dict['train'][dt][k] for k in ['X', 'y']]
            sigma = model_class.fit(X_train, y_train)
            sigma_dict[dt]['sigma'] = self.rescale_sigma_reg(sigma, dt)
            # Std of trades
            st = data_dict['train'][dt]['ts'][0].date()
            sigma_dict[dt]['std'] = np.mean([group.diff().std() for date, group in grouped if dt > date >= st])
            avg_dt = np.mean([group.index.to_series().diff().dropna().mean().total_seconds()
                              for date, group in grouped_all if dt > date >= st])
            sigma_dict[dt]['avg_dt'] = avg_dt
            # Data
            # Data trades
            Xp_dict = data_dict['tests'][dt]['X_p']
            # Adjust trades and ticks
            X_tests, y_tests, ts_tests = [data_dict['tests'][dt][k] for k in ['X', 'y', 'ts']]
            columns_list = ['X_' + str(i) for i in range(X_tests.shape[1])]
            columns_list.append('y')
            df_test = pd.DataFrame(np.concatenate([X_tests, y_tests.reshape(-1,1)], axis=1),
                                   index=ts_tests, columns=columns_list)
            trd_col_list = ['trd_' + str(i) for i in range(Xp_dict['x'].shape[1])]
            df_xtest = pd.DataFrame(Xp_dict['x'], index=Xp_dict['index'], columns=trd_col_list)
            data_mat = pd.concat([df_test, df_xtest], axis=1)
            # Testing and rescale
            y_pred_s = model_class.predict_live(data_mat)
            y_pred = self.rescale_data_reg(y_pred_s, dt)
            # Transform to prices
            price_pred = np.exp(y_pred) * Xp_dict['t_y']
            # Write to out_dict
            out_dict[dt] = {'index': Xp_dict['index'], 'price': price_pred, 'ret': y_pred_s}
        return out_dict, sigma_dict

    def prepare_class_data(self, df_ba, tick_val, cls_margin):
        grouped = df_ba.groupby(df_ba.index.date)
        ba_dict = {date: group.dropna() for date, group in grouped
                   if date in self.run_dates}
        cls_dict = {k: [] for k in ba_dict.keys()}
        for dt, df_ba_aux in ba_dict.items():
            # Class
            cls_dict[dt] = self.calc_class_data(df_ba_aux, None, cls_margin,
                                                tick_val, None)
        return ba_dict, cls_dict

    def scale_data_reg(self, X_train, y_train, X_tests, y_tests, d):
        if self.isEMA:
            tau = len(y_train)
            X_params = [z_score_params(X_train[:, i], tau, n=self.n_ema)
                        for i in range(X_train.shape[1])]
            y_params = z_score_params(y_train, tau, n=self.n_ema)
            X_train_s = np.column_stack([(X_train[:, i] - s.mean.value) / s.value
                                         for i, s in enumerate(X_params)])
            y_train_s = (y_train - y_params.mean.value) / y_params.value
            X_tests_s = np.column_stack([(X_tests[:, i] - s.mean.value) / s.value
                                         for i, s in enumerate(X_params)])
            y_tests_s = (y_tests - y_params.mean.value) / y_params.value
            self.__scale_params_dict[d] = {'X': X_params, 'y': y_params}
        else:
            scaler_x = StandardScaler()
            X_train_s = scaler_x.fit_transform(X_train)
            X_tests_s = scaler_x.transform(X_tests)
            scaler_y = StandardScaler()
            y_train_s = scaler_y.fit_transform(y_train.reshape(-1, 1)).reshape(-1,)
            y_tests_s = scaler_y.transform(y_tests.reshape(-1, 1)).reshape(-1,)
            self.__scale_params_dict[d] = {'X': scaler_x, 'y': scaler_y}
        return X_train_s, y_train_s, X_tests_s, y_tests_s

    def rescale_data_reg(self, y_scaled, d):
        if self.isEMA:
            y_params = self.scale_params_dict[d]['y']
            y_new = y_scaled * y_params.value + y_params.mean.value
        else:
            scaler = self.scale_params_dict[d]['y']
            y_new = scaler.inverse_transform(y_scaled.reshape(-1, 1)).reshape(-1,)
        return y_new

    def rescale_sigma_reg(self, sigma_scaled, d):
        if self.isEMA:
            y_params = self.scale_params_dict[d]['y']
            sigma = sigma_scaled * y_params.value
        else:
            scaler = self.scale_params_dict[d]['y']
            sigma = scaler.scale_[0] * sigma_scaled
        return sigma

    @staticmethod
    def tick_data(df_data_p, df_data_v, mkt, tau, tau_ema):
        agg_dict = {'index': 'first'}
        agg_dict.update({k: 'sum' for k in df_data_p.columns})
        agg_dict.update({k + '_v': 'sum' for k in df_data_p.columns})
        ti_cls = TR_class(tau, tau_ema)
        # Indices based on ticks
        idx_series = ti_cls.tick_imbalance_indices(df_data_p.loc[:, mkt])
        # Create returns
        data_vw = pd.concat([df_data_p * df_data_v, df_data_v], axis=1)
        data_vw.columns = list(agg_dict.keys())[1:]
        data_aux = pd.concat([data_vw.reindex(idx_series.index), idx_series], axis=1).reset_index()
        data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
        # Back to vwp
        for col in df_data_p.columns:
            data_aux.loc[:, col] /= data_aux.loc[:, col + '_v']
        return data_aux

    @staticmethod
    def price_process_km(df_data_p):
        grouped = df_data_p.groupby(df_data_p.index.date)
        data_dict = {date: group for date, group in grouped}
        data_sm = pd.DataFrame([])
        data_st = pd.DataFrame([])
        for data in data_dict.values():
            data_b = pd.DataFrame([])
            data_p = pd.DataFrame([])
            for m in data.columns:
                b_ser, p_ser = [x.reindex(data.index) for x in KFSmootherS(data.loc[:, m].dropna())]
                data_b = pd.concat([data_b, b_ser], axis=1)
                data_p = pd.concat([data_p, p_ser], axis=1)
            data_b.columns = data.columns
            data_sm = pd.concat([data_sm, data_b])
            data_p.columns = data.columns
            data_st = pd.concat([data_st, data_p])
        return data_sm, data_st

    @staticmethod
    def data_process_mdl(df_trds, data_, data_s, data_p, pred_var, regs_var, km_bool):
        # Unify timestamp
        data_cols = ['x_' + str(i) for i, x in enumerate(regs_var)]
        data_cols.append('t_y')
        ts = data_.index.union(df_trds.index)
        data_s = data_s.shift(1).reindex(ts).ffill().reindex(df_trds.index)
        data_ = data_.shift(1).reindex(ts).ffill().reindex(df_trds.index)
        df_trds = df_trds.loc[:, regs_var]
        if km_bool:
            # Smooth trades based on ticks
            data_p = data_p.shift(1).reindex(ts).ffill().reindex(df_trds.index)
            for reg in regs_var:
                trd_ser = df_trds[reg]
                trd_ser = KFSmoothTrades(trd_ser, data_s.loc[:, reg], data_p.loc[:, reg])
                df_trds.loc[:, reg] = trd_ser
        df_x = np.log(df_trds) - np.log(data_s.loc[:, regs_var])
        df_out = pd.concat([df_x, data_.loc[:, pred_var]], axis=1)
        df_out.columns = data_cols
        return df_out

    @staticmethod
    def calc_class_data(df_ba, timestamp, cls_margin, tick_val, gran=None):
        variable_dict = df_ba.to_dict(orient='list')
        variable_dict['timestamp'] = df_ba.index
        obSim = OB_attributes([], verbose=False)
        # Prepare main market
        idx, csum, ts = obSim.calc_tick_index(variable_dict, None, None, 1)
        data_cl = obSim.prepare_class_data(variable_dict, csum, idx, tick_val,
                                           cls_margin, timestamp, gran)
        return data_cl

    @staticmethod
    def to_dict_xp(df_price):
        regs_var = [x for x in df_price.columns if x[0] == 'x']
        X_p = df_price.loc[:, regs_var].values
        y_t = df_price.loc[:, 't_y'].values.reshape(-1,)
        return {'index': df_price.index, 'x': X_p, 't_y': y_t}

    @staticmethod
    def process_model_db_n(pred_dict, trd_dict):
        df_out = pd.DataFrame([])
        for m, mkt_dict in pred_dict.items():
            df_mdl = pd.DataFrame([])
            df_trd_all = trd_dict[m]
            for date, data_dict in mkt_dict.items():
                data_new = pd.DataFrame(data_dict).set_index('index')
                data_new.columns = ['price_hat_' + m, 'ret_' + m]
                # Merge trades
                mask = pd.Series(df_trd_all.index.date, index=df_trd_all.index).isin([date])
                df_trd_aux = df_trd_all[mask]
                df_trd_aux = df_trd_aux.loc[data_new.index, 'tradeid']
                data_new = pd.concat([df_trd_aux, data_new], axis=1)
                if df_mdl.empty:
                    df_mdl = data_new
                else:
                    df_mdl = pd.concat([df_mdl, data_new])
            # Merge with df_out
            if df_out.empty:
                df_out = df_mdl
            else:
                df_out = pd.concat([df_out, df_mdl])
        return df_out.sort_index()

    @staticmethod
    def process_model_db_ens(pred_dict, trd_dict, filtered_dict):
        df_out = pd.DataFrame([])
        for m, mkt_dict in pred_dict.items():
            df_mdl = pd.DataFrame([])
            df_trd_all = trd_dict[m]
            for date, data_dict in mkt_dict.items():
                data_new = pd.DataFrame(data_dict).set_index('index')
                data_new.columns = ['price_hat_' + m, 'ret_' + m]
                # Merge trades
                mask = pd.Series(df_trd_all.index.date, index=df_trd_all.index).isin([date])
                df_trd_aux = df_trd_all[mask]
                df_trd_aux = df_trd_aux.loc[data_new.index, 'tradeid']
                data_new = pd.concat([df_trd_aux, data_new], axis=1)
                if df_mdl.empty:
                    df_mdl = data_new
                else:
                    df_mdl = pd.concat([df_mdl, data_new])
            # Merge with df_out
            if df_out.empty:
                df_out = df_mdl
            else:
                df_out = pd.concat([df_out, df_mdl])
        # Add Ensemble model
        for mkt, flt_dict in filtered_dict.items():
            df_mdl = pd.DataFrame([])
            df_trd_all = trd_dict[mkt]
            for date, data_dict in flt_dict.items():
                df_ens = pd.DataFrame(data_dict).set_index('index')
                df_ens.columns = ['price_hat_ens', 'ret_ens']
                # Merge trades
                mask = pd.Series(df_trd_all.index.date, index=df_trd_all.index).isin([date])
                df_trd_aux = df_trd_all[mask]
                ts = df_ens.index.union(df_trd_aux.index)
                df_trd_id = df_trd_aux.reindex(ts).loc[df_ens.index, 'tradeid']
                # Other trades
                mask = pd.Series(df_out.index.date, index=df_out.index).isin([date])
                df_out_aux = df_out[mask]
                df_out_aux = df_out_aux[~df_out_aux.index.duplicated(keep='first')]
                df_trd_id = df_trd_id.fillna(df_out_aux.loc[:, 'tradeid'])
                df_ens = pd.concat([df_trd_id, df_ens], axis=1)
                if df_mdl.empty:
                    df_mdl = df_ens
                else:
                    df_mdl = pd.concat([df_mdl, df_ens])
        # Merge all data
        df_out_idx = df_out.set_index([df_out.index, df_out['tradeid']])
        df_mdl_idx = df_mdl.set_index([df_mdl.index, df_mdl['tradeid']])
        # Drop the 'tradeid' column (it's already part of the index)
        df_out_idx = df_out_idx.drop(columns='tradeid')
        df_mdl_idx = df_mdl_idx.drop(columns='tradeid')
        return df_out_idx.join(df_mdl_idx, how='outer').sort_index()

    @staticmethod
    def ensemble_models(mdl_dict, ba_dict, data_p, m_lead_list, m_lag, sigma_dict,
                        q=1e-8, km_model='filter'):
        # Prepare data
        cols_list = ['ret_' + m for m in m_lead_list]
        trd_lag_ser = data_p.loc[:, m_lag].dropna()
        grouped = trd_lag_ser.groupby(trd_lag_ser.index.date)
        data_lag_dict = {date: group for date, group in grouped}
        data_dict = {}
        for day, df_model in mdl_dict.items():
            # Sigma
            sigma_list = [sigma_dict[m][day]['sigma'] for m in m_lead_list]
            df_ba = ba_dict[day]
            ts = df_ba.index.union(data_lag_dict[day].index)
            df_ba = df_ba.reindex(ts).ffill().loc[data_lag_dict[day].index, :]
            ser_aux = (df_ba['a_price'] - df_ba['b_price']).abs() / 2
            ser_ret = pd.Series(0, index=data_lag_dict[day].index)
            df_lag_aux = pd.concat([data_lag_dict[day], ser_aux, ser_ret], axis=1)
            df_lag_aux.columns = ['price', 'sigma', 'ret']
            # Find which was traded on
            idx_l = df_model.loc[:, cols_list].notna().values.argmax(axis=1)
            ret_act = df_model[cols_list].to_numpy()[np.arange(len(df_model)), idx_l]
            ser_ret = pd.Series(ret_act, index=df_model.index)
            ser_sigma = pd.Series([sigma_list[i] for i in idx_l], index=df_model.index)
            # Calc error
            ser_diff = pd.Series(ser_sigma.values, index=df_model.index)
            ser_errs = (1 - np.exp(-ser_diff)) * df_model.loc[:, 'price_hat']
            df_mdl_aux = pd.concat([df_model.loc[:, 'price_hat'], ser_errs, ser_ret], axis=1)
            df_mdl_aux.columns = ['price', 'sigma', 'ret']
            # Merge model with lag trades
            df_data = pd.concat([df_lag_aux, df_mdl_aux]).sort_values(by=['sigma'])
            # Drop duplicated index
            data_dict[day] = df_data[~df_data.index.duplicated(keep='first')].sort_index()
        # Compute ensemble
        out_dict = {}
        for day, df_model in data_dict.items():
            std_ = sigma_dict[m_lead_list[0]][day]['std']
            avg_dt = sigma_dict[m_lead_list[0]][day]['avg_dt']
            if km_model == 'filter':
                P_init = std_
            elif km_model == 'cvm':
                P_init = np.array([[std_ ** 2, 0], [0, (std_ / avg_dt) ** 2]])
                max_velocity = 2 * std_ / avg_dt
            else:
                raise ValueError('ensemble_models: unknown km_model {km_model}.')
            # Group by date
            grouped = df_model.groupby(df_model.index.date)
            grouped_dict = {date: group for date, group in grouped}
            df_out = pd.DataFrame([])
            for dt, data_m in grouped_dict.items():
                df_ba = ba_dict[day]
                ts = df_ba.index.union(data_m.index)
                df_ba = df_ba.reindex(ts).ffill().loc[data_m.index, :]
                p_init = .5 * (df_ba.iloc[0, 0] + df_ba.iloc[0, 1])
                if km_model == 'filter':
                    series_aux = KFEnsModel(data_m.iloc[:, :2], q, p_init, P_init)
                elif km_model == 'cvm':
                    series_aux = KFEnsModelVel(data_m.iloc[:, :2], q, p_init, P_init, max_velocity)
                df_aux = pd.concat([series_aux, data_m.iloc[:, -1]], axis=1)
                df_aux.columns = ['price', 'ret']
                if df_out.empty:
                    df_out = df_aux
                else:
                    df_out = pd.concat([df_out, df_aux])
            out_dict[day] = {'index': df_out.index}
            out_dict[day].update({col: df_out[col].values for col in df_out.columns})
        return out_dict

    @staticmethod
    def process_model_mkt(ba_dict, cls_dict, pred_dict):
        out_dict = {k: [] for k in ba_dict.keys()}
        for dt, df_ba_aux in ba_dict.items():
            df_pred = pd.DataFrame(pred_dict[dt]).set_index('index')
            ts = df_ba_aux.index.union(df_pred.index)
            ba_aux = df_ba_aux.reindex(ts).ffill().loc[df_pred.index, :]
            # Class
            df_cls = cls_dict[dt].reindex(ts).ffill().loc[df_pred.index, :]
            df_cl_count = (df_cls != df_cls.shift(1)).cumsum()
            df_cl_count.columns = ['counter']
            # Bid Ask margin
            # Bid margin
            bmrg_ser = ba_aux.loc[:, 'b_price'] - df_pred.loc[:, 'price']
            amrg_ser = df_pred.loc[:, 'price'] - ba_aux.loc[:, 'a_price']
            mrg_ser = amrg_ser.clip(lower=0) - bmrg_ser.clip(lower=0)
            mrg_ser.name = 'fair_margin'
            out_dict[dt] = pd.concat([ba_aux, df_pred, mrg_ser, df_cls, df_cl_count], axis=1)
        return out_dict

    @staticmethod
    def process_model_mkt_n(ba_dict, cls_dict, pred_dict):
        out_dict = {k: [] for k in ba_dict.keys()}
        for dt, df_ba_aux in ba_dict.items():
            df_aux = pd.DataFrame([])
            df_phat = pd.DataFrame([])
            for m, p_dict in pred_dict.items():
                df_pred = pd.DataFrame(p_dict[dt]).set_index('index')
                ts = df_ba_aux.index.union(df_pred.index)
                ba_aux = df_ba_aux.reindex(ts).ffill().loc[df_pred.index, :]
                # Bid Ask margin
                # Bid margin
                bmrg_ser = ba_aux.loc[:, 'b_price'] - df_pred.loc[:, 'price']
                amrg_ser = df_pred.loc[:, 'price'] - ba_aux.loc[:, 'a_price']
                mrg_ser = amrg_ser.clip(lower=0) - bmrg_ser.clip(lower=0)
                mrg_ser.name = 'fair_margin_' + m
                # Returns
                ret_ser = df_pred.loc[:, 'ret']
                ret_ser.name = 'ret_' + m
                # Predicted price
                phat_ser = df_pred.loc[:, 'price']
                phat_ser.name = 'price_' + m
                if df_aux.empty:
                    df_aux = pd.concat([ret_ser, mrg_ser], axis=1)
                else:
                    df_aux = pd.concat([df_aux, ret_ser, mrg_ser], axis=1)
                if df_phat.empty:
                    df_phat = phat_ser
                else:
                    df_phat = pd.concat([df_phat, phat_ser], axis=1)
            ts = df_ba_aux.index.union(df_aux.index)
            # Bid Ask
            ba_aux = df_ba_aux.reindex(ts).ffill().loc[df_aux.index, :]
            # Combination of models
            df_phat = df_phat.mean(axis=1, skipna=True)
            df_phat.name = 'price_hat'
            # Class
            df_cls = cls_dict[dt].reindex(ts).ffill().loc[df_aux.index, :]
            df_cl_count = (df_cls != df_cls.shift(1)).cumsum()
            df_cl_count.columns = ['counter']
            out_dict[dt] = pd.concat([ba_aux, df_aux, df_phat, df_cls,
                                      df_cl_count], axis=1)
        return out_dict

    @staticmethod
    def process_model_supp_n(pred_dict):
        dates = [list(v.keys()) for v in pred_dict.values()]
        dates = list(sorted(set(dates[0]).intersection(*dates[1:])))
        out_dict = {k: [] for k in dates}
        for dt in dates:
            df_phat = pd.DataFrame([])
            # for m, p_dict in pred_dict.items():
            #     df_pred = pd.DataFrame(p_dict[dt]).set_index('index')
            #     # Predicted price
            #     phat_ser = df_pred.loc[:, 'price']
            #     phat_ser.name = 'price_' + m
            #     # Returns
            #     ret_ser = df_pred.loc[:, 'ret']
            #     ret_ser.name = 'ret_' + m
            #     if df_aux.empty:
            #         df_aux = ret_ser
            #     else:
            #         df_aux = pd.concat([df_aux, ret_ser], axis=1)
            #     if df_phat.empty:
            #         df_phat = phat_ser
            #     else:
            #         df_phat = pd.concat([df_phat, phat_ser], axis=1)
            for m, p_dict in pred_dict.items():
                df_pred = pd.DataFrame(p_dict[dt]).set_index('index')
                # Predicted price
                phat_ser = df_pred.loc[:, 'price']
                phat_ser.name = 'fair_price'
                # Returns
                ret_ser = df_pred.loc[:, 'ret']
                ret_ser.name = 'ret'
                tag_ser = pd.Series('lag_' + m, index=df_pred.index)
                tag_ser.name = 'tag'
                df_aux = pd.concat([phat_ser, ret_ser, tag_ser], axis=1)
                if df_phat.empty:
                    df_phat = df_aux
                else:
                    df_phat = pd.concat([df_phat, df_aux])
            out_dict[dt] = df_phat.sort_values(by=['index', 'tag'], axis=0, ascending=[True, True])
        return out_dict

    @staticmethod
    def conf_matrix(processed_dict, thres_mrg, thres_ret, grouped=False,
                    start_time=None, end_time=None):
        agg_dict = {'index': 'first', 'class': 'mean', 'pred': 'median'}
        df_cls = pd.DataFrame([])
        mat_dict = {}
        for dt, df_data in processed_dict.items():
            # Select
            pred_cls_aux = pd.Series(0, index=df_data.index, name='pred')
            idx_l = ((df_data['ret'] > thres_ret) & (df_data['fair_margin'] > thres_mrg) &
                     (df_data['ret'] * df_data['fair_margin'] > 0))
            idx_s = ((df_data['ret'] < -thres_ret) & (df_data['fair_margin'] < -thres_mrg) &
                     (df_data['ret'] * df_data['fair_margin'] > 0))
            pred_cls_aux[idx_l] = 1
            pred_cls_aux[idx_s] = -1
            df_cls_aux = pd.concat([pred_cls_aux, df_data['class']], axis=1)
            df_cls_aux = df_cls_aux[df_cls_aux.loc[:, 'pred'] != 0]
            if grouped:
                df_cls_aux = pd.concat([df_cls_aux, df_data['counter'].reindex(df_cls_aux.index)], axis=1)
                df_cls_aux = df_cls_aux.reset_index().groupby('counter').agg(agg_dict).set_index('index')
                idx_l, idx_s = df_cls_aux['pred'] > 0, df_cls_aux['pred'] < 0
                df_cls_aux.loc[idx_l, 'pred'] = 1
                df_cls_aux.loc[idx_s, 'pred'] = -1
            if start_time is None:
                pass
            else:
                df_cls_aux = df_cls_aux.between_time(start_time, end_time)
            if df_cls.empty:
                df_cls = df_cls_aux
            else:
                df_cls = pd.concat([df_cls, df_cls_aux], axis=0)
            y_pred = df_cls_aux.loc[:, 'pred']
            y_true = df_cls_aux.loc[:, 'class']
            mat_dict[dt] = confusion_matrix(y_true, y_pred, labels=[-1, 0, 1])
        y_pred = df_cls.loc[:, 'pred']
        y_true = df_cls.loc[:, 'class']
        tot_mat = confusion_matrix(y_true, y_pred, labels=[-1, 0, 1])
        return tot_mat, mat_dict

    @staticmethod
    def process_conf_matrix(tot_mat, mat_dict):
        def accuracy(mat):
            TN, FP = mat[0, 0], mat[1, 0] + mat[2, 0]
            FN, TP = mat[0, 2] + mat[1, 2], mat[2, 2]
            if (TP + TN + FP + FN) == 0:
                return np.nan
            else:
                return (TP + TN) / (TP + TN + FP + FN)
        return accuracy(tot_mat), {k: accuracy(m) for k, m in mat_dict.items()}


def KFSmootherS(data_ser):
    x_, P_ = KFSmootherSingle(data_ser.values)
    return pd.Series(x_, index=data_ser.index), pd.Series(P_, index=data_ser.index)


def KFSmootherDF(df_data):
    X = df_data.values
    X_ = np.empty(X.shape, dtype=np.float64)
    for n in range(X.shape[1]):
        x_ = X[:, n]
        X_[:, n], _ = KFSmootherSingle(x_)
    return pd.DataFrame(X_, index=df_data.index, columns=df_data.columns)


def KFSmoother(X, y):
    y_, _ = KFSmootherSingle(y)
    X_ = np.empty(X.shape, dtype=np.float64)
    for n in range(X.shape[1]):
        x_ = X[:, n]
        X_[:, n] = KFSmootherSingle(x_)
    return X_, y_


def KFSmootherSingle(x):
    q = .05
    r = 1.
    clf = kalman1d(q, r)
    beta = x[0]
    P = 1
    beta_list = []
    P_list = []
    for x_ in x:
        beta, P = clf.step(x_, 1, beta, P)
        beta_list.append(beta)
        P_list.append(P)
    return np.array(beta_list), np.array(P_list)


def KFSmoothTrades(trd_ser, data_s, data_p):
    ts = trd_ser.index
    df_data = pd.concat([trd_ser, data_s, data_p], axis=1).dropna()
    q = .05
    r = 1.
    clf = kalman1d(q, r)
    price_list = []
    for x_, b, p in df_data.values:
        x, _ = clf.step(x_, 1, b, p)
        price_list.append(x)
    return pd.Series(price_list, index=df_data.index).reindex(ts)


def KFEnsModel(df_data, q, p_init, P_init):
    r = 1.
    clf = kalman1d(q, r)
    price_list = []
    p, P = p_init, P_init
    for p_hat, sig in df_data.values:
        clf.R = sig ** 2
        p, P = clf.step(p_hat, 1., p, P)
        price_list.append(p)
    return pd.Series(price_list, index=df_data.index)


def KFEnsModelVel(df_data, q, p_init, P_init, max_velocity):
    # Initialization
    clf = KalmanFilter(dim_x=2, dim_z=1)
    # clf.Q = np.array([[q, 0], [0, 1e-6]])
    clf.x = np.array([p_init, 0.])
    clf.P = P_init
    clf.H = np.array([[1., 0.]])
    # Run data
    t_prev = df_data.index[0]
    price_list = []
    for t, p_hat, sig in df_data.reset_index().values:
        dt = (t - t_prev).total_seconds()
        # Data sensitive parameters
        clf.Q = np.array([[q * dt ** 4 / 4, q * dt ** 3 / 2],
                          [q * dt ** 3 / 2, q * dt ** 2]])
        clf.F = np.array([[1., dt], [0., 1.]])
        clf.R = np.array([[sig ** 2]])
        # Step
        clf.predict()
        clf.update(np.array([p_hat]))
        price_list.append(clf.x[0])
        # Clip velocity
        clf.x[1] = np.clip(clf.x[1], -max_velocity, max_velocity)
        # Save timestamp
        t_prev = t
    return pd.Series(price_list, index=df_data.index)


def z_score_params(data_array, tau, p=2, n=15):
    sigma = MSTD(tau / 2, n, p, value0=data_array[0])
    [sigma.push(x) for x in data_array]
    if sigma.value < 1e-6:
        sigma.value = 1e-6
    return sigma
