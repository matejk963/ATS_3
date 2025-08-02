# -*- coding: utf-8 -*-
"""
Created on Fri Jul 14 10:33:48 2023

@author: Marek
"""

import numpy as np
from math import factorial
import pandas as pd


def kernel_ema(t, tau, n, tick=1):
    p1 = ((t / tau) ** (n - 1)) / factorial(n - 1)
    p2 = np.exp(-t / tau) / tau
    return p1 * p2 * tick


def kernel_ma(t, tau, n, tick=1):
    tau_hat = 2 * tau / (n + 1)
    p1 = ((n + 1) / n) * (np.exp(-t / tau_hat) / (2 * tau))
    p2_list = [((t / tau_hat) ** k) / factorial(k) for k in np.arange(0, n)]
    return p1 * sum(p2_list)


def kernel_diff(t, tau, tick=1):
    gamma = 1.22208
    beta = 0.65
    alpha = 1 / (gamma * (8 * beta - 3))
    p1 = kernel_ema(t, alpha * tau, 1, tick=tick)
    p2 = kernel_ema(t, alpha * tau, 2, tick=tick)
    p3 = kernel_ema(t, alpha * beta * tau, 4, tick=tick)
    return gamma * (p1 + p2 - 2 * p3)


def kernel_gdev(t, tau, gamma, n, tick=1):
    val = t
    for n in range(1, n + 1):
        val = kernel_diff(val, tau, tick=tick) / (tau ** gamma)
    return val


tick = .1
tau = 20
n_list = [1, 5, 8, 16, 20, 100]

t_array = np.arange(0, 5 * tau, tick)
k_dict = {n: np.array([kernel_ma(t, tau, n) for t in t_array]) for n in n_list}

df_kernel = pd.DataFrame(k_dict, index=t_array)
df_kernel.plot(grid=True, legend=True, figsize=(12, 5))

tick = .01
tau_list = [1, 2, 3, 4]
t_array = np.arange(0, 20, tick)
k_dict = {tau: np.array([(abs(kernel_diff(t, tau, tick=tick))) for t in t_array]) for tau in tau_list}
#k_dict[0] = np.array([np.log(kernel_ema(t, tau, n_list[0])) for t in t_array])

df_kernel = pd.DataFrame(k_dict, index=t_array)
df_kernel.plot(grid=True, legend=True, figsize=(12, 5))


tick = .01
tau_list = [1, 2, 3, 4]
t_array = np.arange(0, 20, tick)
k_dict = {tau: np.array([kernel_diff(t, tau, tick=tick) for t in t_array]) for tau in tau_list}
#k_dict[0] = np.array([np.log(kernel_ema(t, tau, n_list[0])) for t in t_array])

df_kernel = pd.DataFrame(k_dict, index=t_array)
df_kernel.plot(grid=True, legend=True, figsize=(12, 5))


tick = .01
tau = 3
n = 1
gamma_list = [0, .5, 1]
t_array = np.arange(0, 20, tick)
k_dict = {gamma: np.array([kernel_gdev(t, tau, gamma, n, tick=tick) for t in t_array]) for gamma in gamma_list}
#k_dict[0] = np.array([np.log(kernel_ema(t, tau, n_list[0])) for t in t_array])

df_kernel = pd.DataFrame(k_dict, index=t_array)
df_kernel.plot(grid=True, legend=True, figsize=(12, 5))
