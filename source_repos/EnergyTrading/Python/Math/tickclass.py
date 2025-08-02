# -*- coding: utf-8 -*-
"""
Created on Fri Apr 12 16:35:25 2024

@author: Marek
"""

from bisect import bisect_left
import numpy as np


class tick_class():
    def __init__(self, tick_val, tick_num):
        self.tick_val = tick_val
        self.tick_num = tick_num
        self.reset()

    def __call__(self, x):
        tick_diff = self.tick_func(x)
        try:
            csum_curr = self.csum_list[-1]
            idx_curr = self.idx_list[-1]
        except(IndexError):
            csum_curr = 0
            idx_curr = 0
        if np.isnan(tick_diff):
            self.csum_list.append(csum_curr)
        else:
            self.csum_list.append(csum_curr + tick_diff)
        if csum_curr + tick_diff - self.csum_l > self.tick_num:
            self.csum_l = self.csum_list[-1]
            self.idx_list.append(idx_curr + 1)
        else:
            self.idx_list.append(idx_curr)
        self.x_lag = x

    def reset(self):
        self.csum_l = 0
        self.x_lag = None
        self.idx_list = []
        self.csum_list = []

    def truncate_old(self, a_list, b_list, X_list, tick_rng):
        idx = bisect_left(self.csum_list, self.csum_list[-1] - tick_rng)
        self.idx_list = self.idx_list[idx:]
        self.csum_list = self.csum_list[idx:]
        return a_list[idx:], b_list[idx:], X_list[idx:]

    def truncate(self, tick_rng):
        idx = bisect_left(self.csum_list, self.csum_list[-1] - tick_rng)
        self.idx_list = self.idx_list[idx:]
        self.csum_list = self.csum_list[idx:]
        return idx

    def tick_func(self, x):
        try:
            val = abs(x - self.x_lag) / self.tick_val
        except(TypeError):
            val = 0
        return val