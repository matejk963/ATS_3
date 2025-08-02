# -*- coding: utf-8 -*-
"""
Created on Fri Jan 24 10:21:34 2020

@author: zelenaymar
"""

import sys
sys.path.append('P:\\Dev\\DevMarek\\2019\\Smoothing')
sys.path.append('P:\\Dev\\DevMarek\\2019\\loaders')
sys.path.append('P:\\Dev\\DevMarek\\2019\\utils\\date')

import numpy as np
import datetime as dt
import pandas as pd
from smoother import Forwards
from Curve.smoothIE import SmoothCurveIE
from product_date import calc_start_date
from Utilities.excel_loaders import price_xload_all


# date = dt.datetime(2020, 3, 9)
date = dt.datetime.today().replace(minute=0, hour=0, second=0, microsecond=0)
today = dt.datetime.today().replace(minute=0, hour=0, second=0, microsecond=0)
market = 'ttf'
step = 'D'

# Bids & Asks
if date < today:
    path_price = 'Close/bidask_feed_' + date.strftime('%y%m%d') + '.csv'
else:
    path_price = 'test_bidask_feed.csv'
price_dict_bid, price_dict_ask = price_xload_all(market, file=path_price)

fwds_prd = Forwards()
fwds_bid = Forwards()
for ten, p in price_dict_bid.items():
    try:
        start_date = calc_start_date(date, ten)
        fwds_bid.add_forward(p, start_date, ten)
        fwds_prd.add_forward(1, start_date, ten)
    except(ValueError):
        ten_list = [ten[0] + x for x in ten[1:].split('x', 2)]
        sd_list = [calc_start_date(date, x) for x in ten_list]
        fwds_bid.add_forward_spread(p, sd_list[0], sd_list[1], ten)
        fwds_prd.add_forward_spread(1, sd_list[0], sd_list[1], ten)

fwds_ask = Forwards()
for ten, p in price_dict_ask.items():
    try:
        start_date = calc_start_date(date, ten)
        fwds_ask.add_forward(p, start_date, ten)
    except(ValueError):
        ten_list = [ten[0] + x for x in ten[1:].split('x', 2)]
        sd_list = [calc_start_date(date, x) for x in ten_list]
        fwds_ask.add_forward_spread(p, sd_list[0], sd_list[1], ten)

xmass_bool = True
xmass_dict = {}
if xmass_bool:
    fwds_xmass = Forwards()
    fwds_contr = Forwards()
    start_date = pd.date_range(date, periods=1, freq='AS-DEC')[0]
    fwds_contr.add_forward(1, start_date, '2M')
    start_date = pd.date_range(start_date, periods=24, freq='D')[-1]
    end_date = pd.date_range(start_date, periods=10, freq='D')[-1]
    fwds_xmass.add_forward(1, start_date, None, end_date_=end_date)
    xmass_dict['fwd_xmass'] = fwds_xmass
    xmass_dict['fwd_contr'] = fwds_contr
    xmass_dict['vec_xmass'] = [0.97, 1.00]

method = 'norm'
# method = 'standard'
fix_bool = True
# Create smooth curve
fx_prod = ['DA']
if not fix_bool:
    smooth_factor = [round(10000 * x) / 10000 for x in np.arange(0.95, 0.99, 0.05)]
    s_curve = SmoothCurveIE(step, method=method)
    curve_dict = {x: s_curve.create_curve(fwds_ask, fwds_bid, fwds_prd, x, fx_prod)
                  for x in smooth_factor}
else:
    smooth_factor = 1.0
    s_curve = SmoothCurveIE(step, method=method, verbosity=True)
    b_curve = s_curve.create_curve(fwds_ask, fwds_bid, fwds_prd, smooth_factor,
                                   xmass_dict, fx_prod)
    base_curve = b_curve.resample('MS').mean()
    s_curve.set_init(b_curve.values)
    s_curve.set_scale(b_curve.mean())

    # Add extreme months Jun & Jan
    # idx_m = [i for i, x in enumerate(base_curve.index.month) if x in [1, 6]]
    # tens = ['M' + str(i) + 'x' + str(j) for i, j in zip(idx_m[:3:], idx_m[1:4:])]
    # vals = [base_curve.iloc[i] - base_curve.iloc[j] for i, j in zip(idx_m[:3:], idx_m[1:4:])]

    bool_ser = (base_curve.shift(1) > base_curve) & (base_curve.shift(-1) > base_curve) | (base_curve.shift(1) < base_curve) & (base_curve.shift(-1) < base_curve)
    idx_m = [i for i, x in enumerate(bool_ser.values) if x]
    tens = ['M' + str(i) + 'x' + str(j) for i, j in zip(idx_m[4:-1], idx_m[4+1:])]
    vals = [base_curve.iloc[i] - base_curve.iloc[j] for i, j in zip(idx_m[4:-1], idx_m[4+1:])]

    ba_s = 0.025 / 2
    for ten, p in zip(tens, vals):
        ten_list = [ten[0] + x for x in ten[1:].split('x', 2)]
        sd_list = [calc_start_date(date, x) for x in ten_list]
        fwds_bid.add_forward_spread(p - ba_s, sd_list[0], sd_list[1], ten)
        fwds_ask.add_forward_spread(p + ba_s, sd_list[0], sd_list[1], ten)
        fwds_prd.add_forward_spread(1, sd_list[0], sd_list[1], ten)

    # Create smooth curve
    fx_prod.extend(tens)
    smooth_factor = [round(100 * x) / 100 for x in np.arange(0.1, 0.95, 0.05)]
    # s_curve = SmoothCurveIE(step, method=method)
    curve_dict = {x: s_curve.create_curve(fwds_ask, fwds_bid, fwds_prd, x,
                                          xmass_dict, fx_prod)
                  for x in smooth_factor}
    curve_dict[1.0] = b_curve

curve_df = pd.DataFrame(curve_dict)
df_gpl_ttf = curve_df.iloc[:, 0].resample('MS').mean()[1:]
curve_df.plot(grid=True, legend=True, figsize=(15, 7))

out_dict = {x: s_curve.eval_curve(curve_dict[x].values)
            for x in curve_dict.keys()}
