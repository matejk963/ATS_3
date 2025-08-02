#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 19 13:51:17 2023

@author: marek
"""

import numpy as np
import pandas as pd
from Math.lm_class import kalman, OnlineScoring, LinearModel
from Math.nlm_class import VasicekEKF, VasicekUKF
from sklearn.linear_model import LinearRegression
from Math.accumfeatures import MA, MSTD
# from pykalman import KalmanFilter
from filterpy.kalman import UnscentedKalmanFilter, MerweScaledSigmaPoints
tol=(1e-2)/2


def kalman_regression(X, y, q, r, intercept):
    d = X.shape[1]
    if intercept:
        d += 1
    clf = kalman(q, r)
    yhat = []
    beta_list = []
    beta = np.zeros((d, 1))
    P = np.zeros((d, d))
    param_list = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(x_train.dot(beta))
        beta_list.append([b[0] for b in beta])
        beta, P = clf.step(y_, x_train.reshape((1, d)), beta, P)
        param_list.append([x[0] for x in beta])
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'P': P}
    return out_dict


def ekf_regression(X, y, q, r):
    clf = VasicekEKF(q, r)
    d = clf.dim
    yhat = []
    beta_list = []
    beta = np.zeros((d, 1))
    P = np.zeros((d, d))
    param_list = []
    for x_, y_ in zip(X, y):
        x_train = x_
        #yhat.append(x_train.dot(beta))
        beta_list.append([b[0] for b in beta])
        beta, P = clf.step(y_, beta, P)
        param_list.append([x[0] for x in beta])
    score = clf.score(clf._u, clf._v)
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'P': P, 'score': score}
    return out_dict


def ukf_regression(X, y, q, r):
    clf = VasicekUKF(q, r)
    d = clf.dim
    yhat = []
    beta_list = []
    beta = np.random.randn(d, 1)
    P = np.random.randn(d, d) * np.sqrt(np.diag(q)).reshape(-1,1)
    P = P.dot(P.T)
    # beta = np.zeros((d, 1))
    # P = np.eye(d)
    param_list = []
    for x_, y_ in zip(X, y):
        x_train = x_
        #yhat.append(x_train.dot(beta))
        beta_list.append([b[0] for b in beta])
        beta, P = clf.step(y_, beta, P)
        param_list.append([x[0] for x in beta])
    score = clf.score(clf._u, clf._v)
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'P': P, 'score': score}
    return out_dict


def ukf1_regression(X, y, q, r):
    def fx(x, dt):
        x_new = [(x[1] * x[2] - x[0] * x[1]) * dt + x[0] + x[3],
                 x[1] + x[4], x[2] + x[5], x[3], x[4], x[5], x[6]]
        return np.array(x_new).reshape(-1)
    
    def hx(x, dt):
        x_new = [x[0] + x[3]]
        return np.array(x_new).reshape(-1)
    
    clf = VasicekUKF(q, r)
    d = clf.dim
    yhat = []
    beta_list = []
    beta = np.random.randn(d, 1)
    P = np.random.randn(d, d) * np.sqrt(np.diag(q)).reshape(-1,1)
    P = P.dot(P.T)
    P = np.eye(7)
    P[3, 3] = q[0, 0]
    P[4, 4] = q[1, 1]
    P[5, 5] = q[2, 2]
    P[6, 6] = r
    f, h = clf.inputs(1)
    points = MerweScaledSigmaPoints(7, alpha=.1, beta=2., kappa=-1)
    kf = UnscentedKalmanFilter(dim_x=7, dim_z=1, dt=1, fx=fx, hx=hx,
                               points=points)
    kf.P = P
    kf.R = clf.R
    kf.Q = clf.Q
    param_list = []
    for x_, y_ in zip(X, y):
        x_train = x_
        #yhat.append(x_train.dot(beta))
        beta_list.append([b[0] for b in beta])
        kf.predict()
        kf.update(y_)
        param_list.append([x[0] for x in beta])
    # score = clf.score(clf._u, clf._v)
    # out_dict = {'coeff': param_list, 'y_pred': yhat, 'P': P, 'score': score}
    return out_dict


def ftrl_regression(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LinearModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                      adaptive_l1=adaptive_l1, norm_g=False)
    yhat = []
    score = []
    param_list = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(clf.predict(x_train))
        score.append(clf.unc_score(x_train))
        clf.push(x_train, y_)
        param_list.append([x for x in clf.params])
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'score': score}
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


def ou_process(params, n, X_0=0, delta_t=1, par_sigma=0.05):
    alpha, mu, sigma = params
    X = np.zeros(n)
    np.random.seed(42)

    for t in range(n):
        W_t = np.random.normal(0, np.sqrt(delta_t))
        alpha_n = alpha + np.random.normal(0, par_sigma)
        mu_n = mu + np.random.normal(0, par_sigma)
        X[t] = alpha_n * (mu_n - X[t-1]) * delta_t + sigma * W_t + X[t-1]
    return X


def process(params, X, delta_t=1, par_sigma=0.05):
    a0, a1, sigma = params
    n = len(X)
    y = np.zeros(n)

    for t, x in enumerate(X):
        W_t = np.random.normal(0, np.sqrt(delta_t))
        a0_n = a0 + np.random.normal(0, par_sigma)
        a1_n = a1 + np.random.normal(0, par_sigma)
        y[t] = a0_n + a1_n * x * delta_t + sigma * W_t
    return y


N = 20000
tau = 300
burn = 2500

alpha = 0.3 # Rate of reversion
mu = 3.3 # Long-term mean
sigma = 0.2 # Volatility
params = [alpha, mu, sigma]

a_1 = 1 - alpha
a_0 = alpha * mu
# a_1 = 0.7
# a_0 = 2
params_1 = [a_0, a_1, sigma]

par_sigma = 0.02

data = ou_process(params, N, X_0=0, delta_t=1, par_sigma=par_sigma)
X_data = data[:-1].reshape(-1,1)
y_data = data[1:].reshape(-1,)

# y_data = process(params_1, X_data, delta_t=1, par_sigma=par_sigma)
#pd.Series(data).plot()
data_dict = {}
data_dict['raw'] = pd.Series(y_data)
theta_dict = {}

q = np.eye(2) * (par_sigma ** 2)
r = sigma ** 2

out_dict = kalman_regression(X_data, y_data, q, r, True)

# Estimated parameters
theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict['coeff']]
mu_list = [x[0] / y for x, y in zip(out_dict['coeff'], theta_list)]
data_dict['kalman'] = pd.Series(mu_list)

theta_est = np.mean(theta_list)
mu_est = np.mean(mu_list)
a0 = np.mean([x[0] for x in out_dict['coeff']])
a1 = np.mean([x[1] for x in out_dict['coeff']])
sk1 = a0

print('Kalman filter estimate')
print("Estimated alpha: %s %s" % (theta_est, np.std(theta_list)))
print("Estimated mu: %s %s" % (mu_est, np.std(mu_list)))
print("Estimated coefficients %s, %s" % (a0, a1))
print('\n')

q = np.eye(3) * (par_sigma ** 2)
q[0][0] = sigma ** 2
r = par_sigma ** 2

out_dict = ekf_regression(X_data, y_data, q, r)

# Estimated parameters
theta_list = [x[1] for i, x in enumerate(out_dict['coeff']) if i > burn]
mu_list = [x[2] for i, x in enumerate(out_dict['coeff']) if i > burn]
data_dict['kalman_ekf'] = pd.Series(mu_list)
theta_dict['ekf'] = pd.Series(theta_list)

theta_est = np.mean(theta_list) - par_sigma * 0
mu_est = np.mean(mu_list)

print('Extended Kalman filter estimate')
print("Estimated alpha: %s %s" % (theta_est, np.std(theta_list)))
print("Estimated mu: %s %s" % (mu_est, np.std(mu_list)))
print("Estimated score: %s" % out_dict['score'])
print('\n')

# UKF
out_dict = ukf_regression(X_data, y_data, q, r)

# Estimated parameters
theta_list = [x[1] for i, x in enumerate(out_dict['coeff']) if i > burn]
mu_list = [x[2] for i, x in enumerate(out_dict['coeff']) if i > burn]
data_dict['kalman_ukf'] = pd.Series(mu_list)
theta_dict['ukf'] = pd.Series(theta_list)

theta_est = np.mean(theta_list)
mu_est = np.mean(mu_list)

print('Unscented Kalman filter estimate')
print("Estimated alpha: %s %s" % (theta_est, np.std(theta_list)))
print("Estimated mu: %s %s" % (mu_est, np.std(mu_list)))
print("Estimated score: %s" % out_dict['score'])
print('\n')

alpha = 0.2
beta = 1
out_dict_lm = ftrl_regression(X_data, y_data, 0, 0, alpha, beta, True, False)

# Estimated parameters
theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict_lm['coeff']]
mu_list = [x[0] / y for x, y in zip(out_dict_lm['coeff'], theta_list)]
theta_list = [x for i, x in enumerate(theta_list) if i > burn]
mu_list = [x for i, x in enumerate(mu_list) if i > burn]
data_dict['reg_online'] = pd.Series(mu_list)
theta_dict['reg_online'] = pd.Series(theta_list)

theta_est = np.mean(theta_list)
mu_est = np.mean(mu_list)
a0 = np.mean([x[0] for x in out_dict_lm['coeff']])
a1 = np.mean([x[1] for x in out_dict_lm['coeff']])

print('Linear model online estimate')
print("Estimated alpha: %s %s" % (theta_est, np.std(theta_list)))
print("Estimated mu: %s %s" % (mu_est, np.std(mu_list)))
print("Estimated coefficients %s, %s" % (a0, a1))
print('\n')

# Linear regression
model = LinearRegression()
model.fit(X_data, y_data)

# Estimated parameters
theta_est = 1 - model.coef_[0]
mu_est = model.intercept_ / theta_est
a0 = model.intercept_
a1 = model.coef_[0]

print('Linear model offline estimate')
print("Estimated alpha:", theta_est)
print("Estimated mu:", mu_est)
print("Estimated coefficients %s, %s" % (a0, a1))
print('\n')

sk2 = a0

print(sk1/sk2)


# # Kalman Filter setup
# initial_state_mean = [0, 0]  # Initial guesses for c and phi
# transition_matrix = np.eye(2)  # Identity matrix since the state is constant
# observation_matrix = np.column_stack([np.ones(N-1), X_data.reshape(-1,)]).reshape(-1,1,2)  # Include a column for the constant term

# # Assuming small transition covariance as the state is constant
# transition_covariance = np.eye(2) * (par_sigma ** 2)
# observation_covariance = np.eye(1) * sigma ** 2  # Adjust as necessary based on your data's noise

# # Create the Kalman Filter
# kf = KalmanFilter(
#     initial_state_mean=initial_state_mean,
#     initial_state_covariance=np.eye(2),
#     transition_matrices=transition_matrix,
#     observation_matrices=observation_matrix,
#     transition_covariance=transition_covariance,
#     observation_covariance=observation_covariance,
# )

# # Estimate the parameters
# state_estimates = kf.em(y_data).smooth(y_data)[0]
# estimated_c, estimated_phi = state_estimates.mean(axis=0)

# theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in state_estimates]
# mu_list = [x[0] / y for x, y in zip(state_estimates, theta_list)]

# theta_est = np.mean(theta_list)
# mu_est = np.mean(mu_list)

# data_dict['kalman1'] = pd.Series(mu_list)

# print("Estimated alpha:", theta_est)
# print("Estimated mu:", mu_est)
# print("Estimated c, phi %s %s:" % (estimated_c, estimated_phi))

# pd.DataFrame(data_dict).plot()
