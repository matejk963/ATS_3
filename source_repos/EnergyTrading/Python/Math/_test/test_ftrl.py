#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep  5 08:56:09 2023

@author: marek
"""

import numpy as np
import pandas as pd
from sklearn.datasets import load_iris, load_breast_cancer
from sklearn.datasets import make_classification, make_regression
from Math.lm_class import LogisticModel, LinearModel, kalman, OnlineScoring
from Math.accumfeatures import MA, MSTD
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.preprocessing import StandardScaler


def ftrl_classification(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LogisticModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                        adaptive_l1=adaptive_l1)
    yhat = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_ 
        yhat.append(clf.predict(x_train))
        clf.push(x_train, y_)
    probs = np.array([[1-p, p] for p in yhat])
    y_pred = probs.argmax(axis=1)
    out_dict = {'coeff': clf.params, 'y_pred': y_pred, 'probs': probs}
    return out_dict


def ftrl_regression(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LinearModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                      adaptive_l1=adaptive_l1, norm_g=False)
    yhat = []
    score = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(clf.predict(x_train))
        score.append(clf.unc_score(x_train))
        clf.push(x_train, y_)
    out_dict = {'coeff': clf.params, 'y_pred': yhat, 'score': score}
    return out_dict


def kalman_regression(X, y, q, r, intercept):
    d = X.shape[1]
    if intercept:
        d += 1
    clf = kalman(q, r)
    param_list = []
    yhat = []
    beta = np.zeros((d, 1))
    P = np.zeros((d, d))
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(x_train.dot(beta))
        beta, P = clf.step(y_, x_train.reshape((1, d)), beta, P)
        param_list.append([x for x in beta])
    out_dict = {'coeff': beta, 'y_pred': yhat, 'beta': beta, 'P': P,
                'params': param_list}
    return out_dict


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


N = 2000
tau = 300
burn = 1000
intercept = True
isClassification = False

if intercept:
    shift = 0.5
else:
    shift = 0.
    
if isClassification:
    X, y = make_classification(n_samples=10000, n_features=50, n_informative=20,
                               shift=shift)
else:
    X, y, coeff = make_regression(n_samples=10000, n_features=1,
                                  n_informative=1, coef=True, bias=2, noise=2)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    y_scaled = scaler.fit_transform(y.reshape(-1, 1))
    # EMA scale
    y_escale = z_score(y, tau, n=16)
    X_escale = np.column_stack([z_score(X[:, i], tau, 16) for i in range(X.shape[1])])
    
    
lambda1=10
lambda2=1
alpha=3
beta=1

if intercept:
    q = np.eye(2) * 0.0005
else:
    q = 0.0005
r = 0.1

isScaled = False
isEMA = True
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
    intercept = True

score_class = OnlineScoring('r2s', burn=burn, tau=tau)

if isClassification:
    out_dict = ftrl_regression(X, y, lambda1, lambda2, alpha, beta, intercept)
    pc = out_dict['probs']
    y_all = pd.DataFrame([[x, z] for x, z in zip(y, pc)],
                         columns=['true', 'ftrl'])
else:
    out_dict = ftrl_regression(X_data, y_data, lambda1, lambda2, alpha, beta, intercept, False)
    y_pred = out_dict['y_pred']
    y_all = pd.DataFrame([[x, z] for x, z in zip(y_data, y_pred)],
                         columns=['true', 'ftrl'])
    score_ser = pd.Series([score_class.score(y_p, y_n) for y_p, y_n in zip(y_pred, y_data)])
    
    out_dict_kal = kalman_regression(X_data, y_data, q, r, intercept)
    a0 = np.mean([x[0] for x in out_dict_kal['params']])
    a1 = np.mean([x[1] for x in out_dict_kal['params']])
    print('a0, a1: %s %s' % (a0, a1))
    # Linear regression
    model = LinearRegression()
    model.fit(X_data, y_data)

    # Estimated parameters
    a0 = model.intercept_
    a1 = model.coef_[0]
    print('a0, a1: %s %s' % (a0, a1))
