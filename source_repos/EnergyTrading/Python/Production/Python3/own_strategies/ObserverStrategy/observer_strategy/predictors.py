import numpy as np
import math
import json
from .own_tools.math_features import EMA, IteratedEMA, DerivativeEMA, DifferentialEMA
from .OB_attributes import OB_attributes

def _sparsity_func(order_book):
    _MIN_N_ORDERS = 4
    order_book = np.array(order_book)

    # Calculate differences
    diff = np.diff(order_book)

    # Shift the differences to align with the required positions
    if len(diff) < 1:
        return 2.0

    # diff = diff[:-1]  # Remove last element to align with shifted values

    length = len(diff)
    if length < _MIN_N_ORDERS:
        return 2.0

    # Define the manual kernel and normalize
    manual_kernel = np.array([2, 1.5, 1.25, 1, 1])
    kernel_list = manual_kernel / 2

    # Calculate weighted differences
    sum_w_diff = 0
    for i in range(min(4, length)):  # To handle cases where length is less than 5
        sum_w_diff += kernel_list[i] * abs(diff[i])

    return min(round(sum_w_diff, 2), 1)

def predictor_sparsity(obAttr: OB_attributes):
    bids = [x.price for x in obAttr.bids]
    asks = [x.price for x in obAttr.asks]
    return {
        'b_price_sparsity': _sparsity_func(bids),
        'a_price_sparsity': _sparsity_func(asks)
    }


def predictor_ba_volrat(obAttr: OB_attributes, p_depth):
    return obAttr.vol_ratio(p_depth)

def predictor_mid_priceW(obAttr: OB_attributes, p_depth):
    return obAttr.mid_priceW(p_depth)

def predictor_mid_priceW_d(obAttr: OB_attributes, p_depth):
    return obAttr.mid_priceW(p_depth) - obAttr.mid_price()

def delta_a(period):
    return 