# -*- coding: utf-8 -*-
"""
Created on Mon Nov 29 15:40:46 2021

@author: zelenaymar
"""

import numpy as np
import abc
from random import random, seed
from Math.accumfeatures import MA
tol = 1e-10
# beta = 1e-7


class FTRLmodel():
    __metaclass__ = abc.ABCMeta
    def __init__(self, dim, intercept, learn_rate, tol, max_iter, lambda1=10,
                 lambda2=0, alpha=.5, beta=1e-7, norm_g=True, adaptive_l1=True):
        self.dim = dim
        self.intercept = intercept
        self.lambda1 = lambda1
        self.lambda2 = lambda2
        self.alpha = alpha
        self.beta = beta
        self.reset()
        self.__normalize = norm_g
        self.__adaptive = adaptive_l1
        self.__tol = tol
        self.__max_iter = max_iter
        self.__learn_rate = learn_rate
        self.__model_name = None

    @property
    def params(self):
        return self.__params

    @property
    def tol(self):
        return self.__tol

    @property
    def max_iter(self):
        return self.__max_iter

    @property
    def d(self):
        if self.intercept:
            return self.dim + 1
        else:
            return self.dim

    @property
    def norm_g(self):
        return self.__normalize

    @norm_g.setter
    def norm_g(self, value):
        if isinstance(value, bool):
            self.__normalize = value
        else:
            raise ValueError("FTRLmodel: norm_g must be a boolean %s" % value)

    @property
    def adaptive_l1(self):
        return self.__adaptive

    @adaptive_l1.setter
    def adaptive_l1(self, value):
        if isinstance(value, bool):
            self.__adaptive = value
        else:
            raise ValueError("FTRLmodel: adaptive_l1 must be a boolean %s" % value)

    @property
    def param_dict(self):
        out_dict = {}
        out_dict['dim'] = self.dim
        out_dict['lambda1'] = self.lambda1
        out_dict['lambda2'] = self.lambda2
        out_dict['alpha'] = self.alpha
        out_dict['beta'] = self.beta
        out_dict['norm_g'] = self.__normalize
        out_dict['adaptive_l1'] = self.__adaptive
        out_dict['tol'] = self.__tol
        out_dict['maxiter'] = self.__max_iter
        out_dict['lrate'] = self.__learn_rate
        out_dict['intercept'] = self.intercept
        out_dict['mname'] = self.__model_name
        return out_dict
        
    @abc.abstractmethod
    def predict(self, X):
        pass

    def reset(self):
        seed(42)
        # self.__params = np.zeros(self.dim)
        self.__params = np.asarray([random() for x in range(self.d)])
        # self.zt = np.zeros(self.dim)
        self.zt = np.asarray([random() for x in range(self.d)])
        self.nt = np.zeros(self.d)
        self.gt = np.zeros(self.d)
        self.yhat = self.predict(np.zeros(self.d))
        self._n = 0

    def next_step(self):
        self._n += 1  

    def check_conv(self):
        if self._n > self.__max_iter:
            return True
        else:
            return False

    def set_params(self, param_dict_):
        # Update hyper parameters
        param_list = self.param_dict.keys()
        [setattr(self, k, v) for k, v in param_dict_.items() if k in param_list]
        return 0

    def update_params(self, params_vec):
        self.__params = params_vec
        return 0

    def add_intercept(self, X_mat):
        n = X_mat.shape[0]
        if X_mat.ndim > 1:
            c_vec = np.ones((n, 1))
            return np.concatenate([c_vec, X_mat], axis=1)
        else:
            c_vec = np.ones((n,))
            return np.concatenate([c_vec, X_mat], axis=0)

    def gradient(self, X, y):
        self.yhat = self.predict(X)
        return X.T * (self.yhat - y)

    def seq_step(self, X_new, y_new):
        g = self.gradient(X_new, y_new)
        beta = self.params
        beta -= self.__learn_rate * g
        self.update_params(beta)
        self.next_step()
        return 0

    def push_old(self, X_new, y_new):
        self.next_step()
        # Calculate gradient
        g = self.gradient(X_new, y_new)
        if self.__normalize:
            norm = np.sqrt(g.T @ g)
            g /= norm
        self.gt = g
        # Update lambda1
        self.__update_lambda(g)
        for i in range(self.d):
            if X_new[i] == 0:
                continue
            # Update params
            sigma = (np.sqrt(self.nt[i] + g[i] ** 2) - np.sqrt(self.nt[i])) / self.alpha
            self.nt[i] += g[i] ** 2
            self.zt[i] += g[i] - sigma * self.params[i]
            # Update regression params
            if abs(self.zt[i]) <= self.lambda1:
                self.__params[i] = 0
            else:
                self.__params[i] = -1 / ((self.beta + np.sqrt(self.nt[i])) / \
                                         self.alpha + self.lambda2)
                if self.zt[i] >= 0:
                    self.__params[i] *= (self.zt[i] - self.lambda1)
                else:
                    self.__params[i] *= (self.zt[i] + self.lambda1)
        return 0

    def push(self, X_new, y_new):
        self.next_step() 
        for i in range(self.d):
            if X_new[i] == 0:
                continue
             # Update regression params
            if abs(self.zt[i]) <= self.lambda1:
                self.__params[i] = 0
            else:
                self.__params[i] = -1 / ((self.beta + np.sqrt(self.nt[i])) / \
                                         self.alpha + self.lambda2)
                if self.zt[i] >= 0:
                    self.__params[i] *= (self.zt[i] - self.lambda1)
                else:
                    self.__params[i] *= (self.zt[i] + self.lambda1)
        # Calculate gradient
        g = self.gradient(X_new, y_new)
        if self.__normalize:
            norm = np.sqrt(g.T @ g)
            if norm > tol:
                g /= tol
            else:
                g /= norm
        self.gt = g
        # Update lambda1
        self.__update_lambda(g)
        for i in range(self.d):
            if X_new[i] == 0:
                continue
            # Update params
            sigma = (np.sqrt(self.nt[i] + g[i] ** 2) - np.sqrt(self.nt[i])) / self.alpha
            self.nt[i] += g[i] ** 2
            self.zt[i] += g[i] - sigma * self.params[i]
        return 0

    def fit(self, X, y):
        y_hat = []
        for x_, y_ in zip(X, y):
            if self.intercept:
                x_train = np.concatenate([[1], x_])
            else:
                x_train = x_
            y_hat.append(self.predict(x_train))
            self.push(x_train, y_)
        return np.asarray(y_hat).reshape(-1,)

    def unc_score(self, X_new):
        score = 0
        for i in range(self.d):
            if X_new[i] == 0:
                continue
            score += self.alpha * (X_new[i]) / (self.beta + np.sqrt(self.nt[i]))
        return score

    def __update_lambda(self, gl):
        # Update parameter lambda for lasso
        if not self.__adaptive:
            return
        ni = 1 / ((self.beta + np.sqrt(self.nt)) / self.alpha + self.lambda2)
        g = np.sign(self.zt) * ni * gl
        idx = abs(self.zt) < self.lambda1
        g[idx] = 0
        eta = 1 / np.sqrt(self._n)
        self.lambda1 -= eta * sum(g)
        self.lambda1 = max(0, self.lambda1)


class LinearModel(FTRLmodel):
    def __init__(self, dim, intercept=False, learn_rate=1, tol=1e-1, max_iter=100, lambda1=10,
                 lambda2=0, alpha=.5, beta=1e-7, norm_g=False, adaptive_l1=True):
        # Initialize Parent object
        super(LinearModel, self).__init__(dim, intercept, learn_rate, tol, max_iter,
                                          lambda1, lambda2, alpha, beta,
                                          norm_g, adaptive_l1)
        self.__model_name = 'Linear Model'

    def predict(self, X_vec):
        fx = X_vec @ self.params
        return fx 

    def new(self):
        p_dict = self.param_dict
        newmodel = LinearModel(p_dict['dim'], p_dict['intercept'], p_dict['lrate'],
                               p_dict['tol'], p_dict['maxiter'], p_dict['lambda1'],
                               p_dict['lambda2'], p_dict['alpha'], p_dict['beta'],
                               p_dict['norm_g'], p_dict['adaptive_l1'])
        return newmodel


class LogisticModel(FTRLmodel):
    def __init__(self, dim, intercept=False, learn_rate=1, tol=1e-1, max_iter=100, lambda1=10,
                 lambda2=0, alpha=.5, beta=1, norm_g=False, adaptive_l1=True):
        # Initialize Parent object
        super(LogisticModel, self).__init__(dim, intercept, learn_rate, tol, max_iter,
                                            lambda1, lambda2, alpha, beta,
                                            norm_g, adaptive_l1)
        self.__model_name = 'Logistic Model'

    def predict(self, X_vec):
        fx = X_vec @ self.params
        return 1. / (1. + np.exp(-max(min(fx, 35.), -35.)))

    def new(self):
        p_dict = self.param_dict
        newmodel = LogisticModel(p_dict['dim'], p_dict['intercept'], p_dict['lrate'],
                                 p_dict['tol'], p_dict['maxiter'], p_dict['lambda1'],
                                 p_dict['lambda2'], p_dict['alpha'], p_dict['beta'],
                                 p_dict['norm_g'], p_dict['adaptive_l1'])
        return newmodel

    def log_loss(self, X, y):
        l = -0.5 * self.lambda2 * np.sum(self.params * self.params)
        for x, o in zip(X, y):
            p = self.predict(x)
            l += o * np.log(p) + (1 - o) * np.log(1 - p)
        return l

    def opt_step(self, X_mat, y_vec):
        n = len(y_vec)
        beta_o = self.params
        p_vec = np.array([self.predict(x) for x in X_mat]).reshape((n, 1))
        w_vec = p_vec * (1 - p_vec)
        z_vec = X_mat @ beta_o + (y_vec - p_vec) * (1 / w_vec)
        XW_mat = X_mat * w_vec
        beta_n = np.linalg.solve(XW_mat.T @ X_mat, XW_mat.T @ z_vec - self.lambda2 * beta_o)
        self.update_params(beta_n)
        self.next_step()
        return beta_n

    def fit(self, X_mat, y_vec, beta_start=None, intercept=True):
        if intercept:
            X_mat = super(LogisticModel, self).add_intercept(X_mat)
        n, m = X_mat.shape
        if beta_start is None:
            beta_start = np.zeros((m, 1))
        if y_vec.ndim == 1:
            y_vec = y_vec.reshape((n, 1))
        self.update_params(beta_start)
        l_prev = -np.inf
        l_next = self.log_loss(X_mat, y_vec)
        while l_next - l_prev >= self.tol:
            l_prev = l_next
            beta = self.opt_step(X_mat, y_vec)
            l_next = self.log_loss(X_mat, y_vec)
            print(l_next)
            if self.check_conv():
                l_prev = l_next
            else:
                pass
        return beta


class kalman1d():
    def __init__(self, Q, R):
        self.Q = Q
        self.R = R

    def step(self, y_new, x_new, beta_prior, P_prior):
        beta_pred, P_pred = self.prediction(y_new, beta_prior, P_prior)
        beta_post, P_post = self.update(y_new, x_new, beta_pred, P_pred)
        return beta_post, P_post

    def update(self, y, x, beta_prior, P_prior):
        # Kalman gain
        K_t = P_prior * x / (x * x * P_prior + self.R)
        # Update var cov of observation P matrix
        P_post = (1 - K_t * x) * P_prior
        # Update prediction
        beta_post = beta_prior + K_t * (y - beta_prior * x)
        return beta_post, P_post
        
    def prediction(self, y_new, beta_post, P_post):
        P_pred = P_post + self.Q
        beta_pred = beta_post * 1
        return beta_pred, P_pred


class kalman():
    def __init__(self, Q, R):
        self.Q = Q
        self.R = R
        self.name = 'KF'

    def step(self, y_new, x_new, beta_prior, P_prior):
        beta_pred, P_pred = self.prediction(y_new, beta_prior, P_prior)
        beta_post, P_post = self.update(y_new, x_new, beta_pred, P_pred)
        return beta_post, P_post

    def update(self, y, X_vec, beta_prior, P_prior):
        dim = max(X_vec.shape)
        # Kalman gain
        K_t = P_prior.dot(X_vec.T) / (X_vec.dot(P_prior.dot(X_vec.T)) + self.R)
        # Update var cov of observation P matrix
        P_post = (np.eye(dim) - K_t.dot(X_vec)).dot(P_prior)
        # Update prediction
        beta_post = beta_prior + K_t.dot(y - X_vec.dot(beta_prior))
        return beta_post, P_post
    
    def prediction(self, y_new, beta_post, P_post):
        P_pred = P_post + self.Q
        beta_pred = beta_post * 1
        return beta_pred, P_pred


class OnlineScoring:
    def __init__(self, method, burn=10, tau=0):
        self.count = 0
        self.__init = True
        self.__method = method
        self.__burn = burn
        self.__tau = tau

    @property
    def is_burn(self):
        if self.count < self.__burn:
            return True
        else:
            return False

    @property
    def burn(self):
        return self.__burn

    @property
    def method(self):
        return self.__method

    def initialize(self):
        if self.__init:
            if self.method == 'r2':
                self.__r2_init()
            elif self.method == 'mae':
                self.__mae_init()
            elif self.method == 'r2s':
                self.__r2s_init()
            else:
                return ValueError('Unknown method %s for computing score'
                                  % self.method)
            # init_name = '_' + self.method + '_init'
            # getattr(self, init_name)
        return self.__init

    def reset(self):
        self.count = 0
        self.__init = True

    def __r2_init(self):
        self.SS_res = 0
        self.SS_tot = 0
        self.y_mean = 0
        self.__init = False

    def __mae_init(self):
        self.mae = 0
        self.__init = False

    def __r2s_init(self):
        self.SS_res = MA(self.__tau / 2, 16)
        self.SS_tot = MA(self.__tau / 2, 16)
        self.y_mean = 0
        self.__init = False

    def r2_coeff(self, y_pred, y_new):
        # Update mean y
        delta = y_new - self.y_mean
        self.y_mean += delta / (self.count + 1)
        if self.is_burn:
            pass
        else:
            # Using Welford inline algorithm to calculate SS_tot
            self.SS_res += (y_new - y_pred) ** 2
            self.SS_tot += delta * (y_new - self.y_mean)
        self.count += 1
        return 1 - (self.SS_res / (self.SS_tot + tol))

    def r2s_coeff(self, y_pred, y_new):
        # Update mean y
        delta = y_new - self.y_mean
        self.y_mean += delta / (self.count + 1)
        if self.is_burn:
            pass
        else:
            # Using Welford inline algorithm to calculate SS_tot
            self.SS_res.push((y_new - y_pred) ** 2)
            self.SS_tot.push(delta * (y_new - self.y_mean))
        self.count += 1
        return 1 - (self.SS_res.value / (self.SS_tot.value + tol))

    def mse_coeff(self, y_pred, y_new):
        error = y_pred - y_new
        delta = error - self.mae
        if self.is_burn:
            pass
        else:
            self.mae += delta / (self.count + 1)
        self.count += 1
        return self.mae

    def score(self, y_pred, y_new):
        self.initialize()
        if self.method == 'r2':
            score = self.r2_coeff(y_pred, y_new)
        elif self.method == 'mae':
            score = self.mae_coeff(y_pred, y_new)
        elif self.method == 'r2s':
            score = self.r2s_coeff(y_pred, y_new)
        else:
            return ValueError('Unknown method %s for computing score' % self.method)
        return score
