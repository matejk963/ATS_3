# -*- coding: utf-8 -*-
"""
Created on Fri Sep 15 15:47:07 2023

@author: Marek
"""

import numpy as np
from sklearn.datasets import make_classification, make_regression
from Math.lm_class import LogisticModel, LinearModel, kalman, OnlineScoring
from Math.accumfeatures import MSTD
from Calibration.calibration_class import ModelCalibration
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit


def z_score(data_array, tau, p=2, n=5):
    z_list = []
    sigma = MSTD(tau / 2, n, p, value0=data_array[0])
    for x in data_array:
        sigma.push(x)
        m_val = sigma.mean.value
        s_val = sigma.value
        if s_val < 1e-6:
            z = 0
        else:
            z = (x - m_val) / s_val
        z_list.append(0 if np.isnan(z) else z)
    return np.asarray(z_list).reshape(-1, 1)


N = 10000
tau = 300
burn = 500
n = 16
intercept0 = True
isClassification = False
isScaled = True
isEMA = True

if intercept0:
    bias = 2
else:
    bias = 0.

if isClassification:
    X, y = make_classification(n_samples=N, n_features=50, n_informative=20,
                               shift=bias)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    # EMA scale
    X_escale = np.column_stack([z_score(X[:, i], tau, n) for i in range(X.shape[1])])
else:
    X, y, coeff = make_regression(n_samples=N, n_features=100, n_informative=10,
                                  coef=True, bias=bias, noise=2)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    y_scaled = scaler.fit_transform(y.reshape(-1, 1))
    # EMA scale
    y_escale = z_score(y, tau, n=n)
    X_escale = np.column_stack([z_score(X[:, i], tau, n=n) for i in range(X.shape[1])])

d = X.shape[1]
if isScaled:
    if isEMA:
        X_data = X_escale
        y_data = y_escale.reshape(-1,)
    else:
        X_data = X_scaled
        y_data = y_scaled.reshape(-1,)
    intercept = False
else:
    X_data = X
    y_data = y
    intercept = intercept0

if isClassification:
    clf = LogisticModel(d, intercept)
else:
    clf = LinearModel(d, intercept)

score_class = OnlineScoring('r2s', burn=burn, tau=tau)

# Parameters fix and variable
opt_param = ['lambda1', 'lambda2', 'alpha', 'beta']
opt_param_val = [np.arange(0, 15, 0.5), np.arange(0, 2, 0.2),
                 np.arange(0.2, 3, 0.2), np.arange(0.5, 2, 0.5)]
opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}

fix_param = ['adaptive_l1', 'norm_g']
fix_param_val = [True, False]
fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

# Calibration module
calibration_class = ModelCalibration(clf, score_class, opt_param, fix_param_dict)
# CV
tscv = TimeSeriesSplit(n_splits=5, max_train_size=2*burn)
splits = [(train_idx, test_idx) for train_idx, test_idx in tscv.split(y_data)]
# Score
score_dict = calibration_class.calibrate_p(X_data, y_data, splits, opt_param_dict)
