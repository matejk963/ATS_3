#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun  4 12:16:21 2023

@author: marek
"""


import abc
import numpy as np
import pandas as pd
import scipy.sparse as sp
import math
from functools import reduce
from datetime import datetime
import matplotlib.pyplot as plt
from copy import deepcopy
from scipy.stats import norm
import pickle
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.stats.diagnostic import acorr_ljungbox
from datetime import timedelta

from Utilities.date_functions import end_date, start_date
from Utilities.delivery_class import Delivery


class fwdCurve(object):
    __metaclass__  = abc.ABCMeta
 
    def __init__(self, forward_list, step):
        forward_list.sort()
        self.market = forward_list[0].market
        self.prices = []
        self.start_dates = []
        self.end_dates = []
        self.periods = []
        self.dels = []
 
        self.step = step
        self.sT = forward_list[0].start_date
        self.eT = forward_list[0].end_date
 
        for f in forward_list:
            if self.market != f.market:
                raise ValueError('Different market detected %s' % f.market)
            else:
                self.prices.append(f.price)
                self.start_dates.append(f.start_date)
                self.end_dates.append(f.end_date)
                self.periods.append(f.period)
                self.dels.append(f.delivery)
                self.sT = min(f.start_date, self.sT)
                self.eT = max(f.end_date, self.eT)
        # Create mask
        self.mask = self.create_mask()

    @abc.abstractmethod
    def create_curve(self):
        pass
    
    @property
    def date_vec(self):
        return pd.date_range(self.sT, self.eT, freq=self.step)

    def create_mask(self): # no need for forward_list, or?
        M = []
        for s, e, d in zip(self.start_dates, self.end_dates, self.dels):
            M.append(mask(self.date_vec, s, e, d))
        return np.stack(M)

    def create_curve_pd(self):
        return pd.Series(self.create_curve(), index=self.date_vec)

    def rem_arbitrage(self):
        dummy = rem_lindep(self.mask.T)

        self.mask = self.mask[np.logical_not(dummy), :]

        for attr_name in ('prices', 'start_dates', 'end_dates', 'periods', 'dels'):
            old_attr_val = getattr(self, attr_name)
            new_attr_val = [val for i, val in enumerate(old_attr_val) if not dummy[i]]
            setattr(self, attr_name, new_attr_val)
            
    def get_forward_list(self):
        """
        Reconstructs the list of forward objects from internal attributes.
        """
        return [
            forward(self.market, price, sD, p, d)
            for price, sD, eD, p, d in zip(self.prices, self.start_dates, self.end_dates, self.periods, self.dels)
        ]
 

class rawCurve(fwdCurve):
    def __init__(self, forward_list, step='h'):
        super(rawCurve, self).__init__(forward_list, step)

    def create_curve(self):
        p_vec = np.asarray(self.prices)
        M = self.mask
        return M.T @ np.linalg.solve(M @ M.T, p_vec * np.sum(M, axis= 1) )
    

class shpCurve(fwdCurve):        
    def __init__(self, forward_list, step='h', smoothstep=None, smoothweights=None, df_spot=None):
        super(shpCurve, self).__init__(forward_list, step)
        self.init = False
        self.smoothstep = smoothstep or [7*24, 14*24]
        self.smoothweights = smoothweights or [1, 1]
        
        self.df_spot = df_spot.copy() if df_spot is not None else None  # store for compute_indexes

        # Initialize optional attributes
        self.hourly_index = None
        self.idx_MvsQ_vals = None
        self.idx_QvsY_vals = None

        self.A_sparse = None
        self.unique_prices = None
        self.prices_long = None
        self.date_index = None   
    
    def rem_arbitrage(self):
        super().rem_arbitrage()  # call the original logic from fwdCurve
        self.init = False
    
    def update_prices(self, forward_list):
        forward_list.sort()
    
        # Optional: check same market
        for f in forward_list:
            if self.market != f.market:
                raise ValueError(f"Different market detected: {f.market}")
    
        # Clear and update
        self.prices = [f.price for f in forward_list]
        self.start_dates = [f.start_date for f in forward_list]
        self.end_dates = [f.end_date for f in forward_list]
        self.periods = [f.period for f in forward_list]
        self.dels = [f.delivery for f in forward_list]
    
        # Update time range
        self.sT = min(f.start_date for f in forward_list)
        self.eT = max(f.end_date for f in forward_list)
    
        # Rebuild mask
        self.mask = self.create_mask()
        self.init = False  # mark curve as outdated
    
    def build_subproblems(self, date_filter=None):
        """
        Builds subproblem structure based on unique forward price values.
        Only stores what is actually needed for downstream shaping logic.
        """
        # Step 1: Remove arbitrage if needed
        self.rem_arbitrage()
    
        # Step 2: Create raw curve (as full time series)
        #fw_curve = self.create_curve_pd()
        raw_curve = rawCurve(deepcopy(self.get_forward_list()), step=self.step)
        raw_curve.rem_arbitrage()
        fw_curve = raw_curve.create_curve_pd()
        if date_filter is not None:
            fw_curve = fw_curve.loc[date_filter:]
    
        # Step 3: Extract full price vector and time index
        prices_long = np.array(fw_curve)
        self.prices_long = prices_long
        self.date_index = fw_curve.index
    
        # Step 4: Build sparse matrix A_sparse based on unique prices
        unique_values = np.array(list(dict.fromkeys(prices_long)))
        value_to_index = {val: i for i, val in enumerate(unique_values)}
        m = len(unique_values)
    
        A_rows = np.array([value_to_index[val] for val in prices_long])
        A_cols = np.arange(len(prices_long))
        A_data = np.ones(len(prices_long), dtype=float)
        A_sparse = sp.coo_matrix((A_data, (A_rows, A_cols)), shape=(m, len(prices_long))).tocsr()
    
        counts = np.array([np.sum(prices_long == val) for val in unique_values])
        A_sparse = A_sparse.multiply(1 / counts[:, None]).tocsr()
    
        self.A_sparse = A_sparse
        self.unique_prices = unique_values
    
        # Step 5: Cut into blocks using helper
        aA, bA = cut_blocks(A_sparse)
    
        # Store only what you use
        self.bA = bA                        # block membership for each time index
        self.subproblem_sizes = {}         # size of each subproblem
        for i in range(int(max(aA))):
            # Use logical masking to get size without storing the block
            row_mask = (aA == i + 1)
            col_mask = (bA == i + 1)
            size = np.sum(row_mask) * np.sum(col_mask)  # rows * columns of block
            self.subproblem_sizes[i] = size
        
    def compute_indexes(self):
        df_spot = self.df_spot.copy()
        #df_spot = pd.read_csv(r'C:\Users\benko\Downloads\Matus\Matus\Python\Curve\spot.csv').set_index('datetime')
        df_spot.index = pd.to_datetime(df_spot.index)
    
        keyFunH = lambda d: (d.month-1, ((d.weekday() < 5) and 0) + ((d.weekday() >= 5) and 1) + ((d.weekday() >= 6) and 1), d.hour)
        
        idx_vec = [keyFunH(x) for x in df_spot.index]
        dim_vec = [len({t[i] for t in idx_vec}) for i in range(3)]
        data_matrix = create_nested_list(dim_vec)
    
        df_data_idx = df_spot / df_spot.groupby(pd.Grouper(freq='ME')).transform('mean')
    
        [ (lambda idx: reduce(lambda l, i: l[i], idx[:-1], data_matrix)[idx[-1]].append(x[0]))(keyFunH(d))
         for d, x in zip(df_data_idx.index, df_data_idx.values) ]
    
        comp_matrix = compute_stat(data_matrix, np.mean)
        idx_calc_vec = [reduce(lambda m, i: m[i], keyFunH(d), comp_matrix) for d in self.date_vec]
        
        self.hourly_index = pd.Series(idx_calc_vec, index=self.date_vec, name='index_mean')  # store as attribute
    
        # Additional index levels
        spot_MA = df_spot.groupby(pd.Grouper(freq='ME')).transform('mean')
        spot_QA = df_spot.groupby(pd.Grouper(freq='QE')).transform('mean')
        spot_YA = df_spot.groupby(pd.Grouper(freq='YE')).transform('mean')
    
        idx_MvsQ = spot_MA / spot_QA
        idx_QvsY = spot_QA / spot_YA
        
        colname = df_spot.columns[0]  # assuming single-column input
    
        # Store aggregated values as attributes
        self.idx_MvsQ_vals = (idx_MvsQ.groupby(idx_MvsQ.index.month)[colname].mean().tolist())
        self.idx_QvsY_vals = (idx_QvsY.groupby(idx_QvsY.index.quarter)[colname].mean().tolist())

        # Compute residual series: actual price / monthly avg - modelled index
        actual_index = df_spot[colname] / spot_MA[colname]
        self.residual_series = (actual_index - self.hourly_index).dropna().asfreq('h')
        
    def generate_noise(self, use_existing, path_existing, path_save_new=None, time_span=None):    
        if use_existing:
            with open(path_existing, "rb") as f:
                model_result = pickle.load(f)
                print(f"[SARIMAX] Loaded model from {path_existing}")
        else:
            # --- Step 1: Work with a copy of the spot data ---
            df_spot = self.df_spot.copy()
            df_spot.index = pd.to_datetime(df_spot.index)
            spot_series = df_spot.squeeze()
            assert isinstance(spot_series, pd.Series), "Spot data must be a Series."
    
            # --- Step 2: Get residual series and restrict to given time_span ---
            resid_series = self.residual_series  # Already stored from compute_indexes()
            if time_span:
                start, end = time_span
                resid_subset = resid_series.loc[start:end]
                duration = end - start
                if duration > timedelta(days=90):
                    print("[Warning] Time span > 3 months. SARIMAX training may take several minutes or longer.")
            else:
                resid_subset = resid_series
    
            resid_clean = clean_residual_jumps(resid_subset)
    
            # --- Step 3: Fit SARIMAX model ---
            p, d, q = 14, 0, 2
            P, D, Q, s = 2, 0, 2, 24
    
            model = SARIMAX(
                resid_clean,
                order=(p, d, q),
                seasonal_order=(P, D, Q, s),
                enforce_stationarity=False,
                enforce_invertibility=False
            )
            model_result = model.fit(maxiter=500, disp=True)
            print("[SARIMAX] created new noise.")
    
            if path_save_new:
                with open(path_save_new, "wb") as f:
                    pickle.dump(model_result, f)
                    print(f"[SARIMAX] Saved model to {path_save_new}")
    
            # --- Step 4: Diagnostic check ---
            lb = acorr_ljungbox(model_result.resid, lags=[14, 24, 48, 72], return_df=True)
            print("\n[Ljung-Box Test Results]")
            print(lb)
    
            min_pval = lb['lb_pvalue'].min()
            if min_pval > 0.3:
                print("[Diagnostic] Residuals appear white noise. Excellent fit. Proceed confidently.")
            elif min_pval > 0.1:
                print("[Diagnostic] Residuals are likely acceptable. Fit is good.")
            elif min_pval > 0.05:
                print("[Diagnostic] Residuals may still have structure. Proceed with caution.")
            else:
                print("[Warning] Poor SARIMAX residuals. Consider trying a different time span or contact the developer.")
    
        return model_result
        
    def smooth(self, shapecurve):
        S = sp.eye(len(shapecurve))
        for i, s in enumerate(self.smoothstep):
            Stemp = smooth_hessian(s, len(shapecurve))
            S = S + self.smoothweights[i] * Stemp.T.dot(Stemp)
        #A = sp.coo_matrix(self.mask)
        #self.smoothcurve = qp(S, shapecurve, A, np.sum(self.mask, axis=1) * self.prices)
        Mask = tuple_list(self.date_vec)
        A = sp.coo_matrix(Mask)
        self.smoothcurve = qp(S, shapecurve, A, Mask@shapecurve)
        
    def create_curve(self, smoothed=True):
        if not self.init:
            self.rem_arbitrage()
            self.compute_indexes()
            self.build_subproblems(date_filter=datetime(2025, 1, 1))  # adjust if needed
            #self.build_subproblems(date_filter=date_filter)
    
            b_new = self.A_sparse @ self.prices_long
            shaped_vals = []
    
            for prob in self.subproblem_sizes:
                size = self.subproblem_sizes[prob]
                period = self.date_index[self.bA == prob + 1]
                idx = self.hourly_index[self.bA == prob + 1].values
    
                if size < 1000:
                    x_unc = idx * b_new[prob]
                elif size < 2500:
                    idx_values = [self.idx_MvsQ_vals[i - 1] for i in np.unique(period.month)]
                    mean_val = np.mean(idx_values)
                    x_unc = []
                    for i in np.unique(period.month):
                        m_mask = (period.month == i)
                        x_unc += (idx[m_mask] * b_new[prob] * self.idx_MvsQ_vals[i - 1] / mean_val).tolist()
                    x_unc = np.array(x_unc)
                else:
                    idx_values = [self.idx_QvsY_vals[math.ceil(i / 3) - 1] for i in np.unique(period.month)]
                    mean_val = np.mean(idx_values)
                    x_unc = []
                    for i in np.unique(period.month):
                        m_mask = (period.month == i)
                        x_unc += (idx[m_mask] * b_new[prob] * self.idx_MvsQ_vals[i - 1] *
                                  self.idx_QvsY_vals[math.ceil(i / 3) - 1] / mean_val).tolist()
                    x_unc = np.array(x_unc)
    
                res = b_new[prob] - np.mean(x_unc)
                x_shaped = x_unc + res
                shaped_vals.extend(x_shaped.tolist())
    
            self.shaped_curve = np.array(shaped_vals)
            self.init = True
        
        if not smoothed:
            return pd.Series(self.shaped_curve, index=self.date_index)
        
        self.smooth(self.shaped_curve)
        self.curve_pd = pd.Series(self.smoothcurve, index=self.date_index)
        return self.curve_pd
        #return self.smoothcurve
    
    def simulate(self, use_existing=True, sarimax_path=None, path_save_new=None, time_span=None, N=100, gran='MS', random_state=None):
        """
        Simulates N forward price curve scenarios using a SARIMAX model and rescaled residuals.
    
        Parameters:
        - use_existing: bool, whether to load a saved SARIMAX model or train a new one
        - sarimax_path: str, path to a saved SARIMAX results object (required if use_existing=True)
        - path_save_new: str, where to save the new SARIMAX model if trained
        - time_span: tuple of (start_date, end_date) to define the training window
        - N: number of scenarios to generate
        - gran: resampling frequency (e.g., 'MS' for month start)
        - random_state: seed for reproducibility
    
        Returns:
        - simulated_curves_dict: dict[int -> np.ndarray], N simulated curves
        """
    
        if not hasattr(self, "curve_pd"):
            raise ValueError("Run create_curve() first to compute the base curve (self.curve_pd)")
    
        # Step 1: Get or train SARIMAX model
        result_sarima = self.generate_noise(
            use_existing=use_existing,
            path_existing=sarimax_path,
            path_save_new=path_save_new,
            time_span=time_span
        )
    
        # Step 2: Simulate from SARIMAX
        index_curve = self.curve_pd
        T = len(index_curve)
        t_index = index_curve.index
        #rng = np.random.default_rng(random_state)
        n_states = result_sarima.model.k_states
    
        simulated_curves_dict = {}
        scale = 1.5 # a number between 1 and 2 (1 means more volatility, 2 means less)
    
        for i in range(N):
            initial_state = np.zeros((n_states, 1))
            sarimax_noise = result_sarima.simulate(nsimulations=T, initial_state=initial_state)
            sarimax_noise_pd = pd.Series(sarimax_noise, index=t_index)
    
            s_noise_agg_pd = sarimax_noise_pd.resample(gran).mean().reindex(t_index).ffill()
            curve_agg_pd = index_curve.resample(gran).mean().reindex(t_index).ffill()
            
            # Normalize noise
            sarimax_noise_pd -= s_noise_agg_pd
            norm_factor = sarimax_noise_pd.abs().max() or 1
            sarimax_noise_pd /= scale * norm_factor
            
            # Rescale residuals by base curve
            scaled_residual = sarimax_noise_pd * curve_agg_pd
            # Final simulated curve = base + scaled residual
            simulated_curves_dict[i] = index_curve.values + scaled_residual.values
    
        # Optionally store last run info
        self.last_simulated_noise = sarimax_noise_pd
        self.last_noise_agg = s_noise_agg_pd
        self.simulated_curves = simulated_curves_dict
    
        return simulated_curves_dict
    
    def export_simulations(self):
        if not hasattr(self, "simulated_curves"):
            raise ValueError("No simulations to export.")
        return pd.DataFrame.from_dict(self.simulated_curves, orient='index', columns=self.curve_pd.index)    
    
    def plot(self):
        if hasattr(self, "curve_pd"):
            self.curve_pd.plot(title="Smoothed Shaped Curve")
        else:
            raise ValueError("Call create_curve() first to generate the curve.")

    def plot_simulation(self, sim_index=0):
        """
        Plot one simulated scenario against the original curve.
        """
        if not hasattr(self, "simulated_curves"):
            raise ValueError("Run simulate() first to generate simulations.")
        if not hasattr(self, "curve_pd"):
            raise ValueError("Run create_curve() first to generate the base curve.")
    
        sim_curve = self.simulated_curves[sim_index]
    
        plt.figure(figsize=(14, 6))
        plt.plot(self.curve_pd.index, self.curve_pd.values, label="Original (Index Curve)", color="black", linestyle="--", linewidth=2)
        plt.plot(self.curve_pd.index, sim_curve, label=f"Simulation {sim_index + 1}", color="red", linewidth=1.5)
    
        plt.title(f"Original Curve vs Simulation {sim_index + 1}")
        plt.xlabel("Time")
        plt.ylabel("Price")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()
    
    def plot_simulation_envelope(self):
        """
        Plot mean and P10–P90 band of all simulations against the original curve.
        """
        if not hasattr(self, "simulated_curves"):
            raise ValueError("Run simulate() first to generate simulations.")
        if not hasattr(self, "curve_pd"):
            raise ValueError("Run create_curve() first to generate the base curve.")
    
        sim_df = pd.DataFrame.from_dict(self.simulated_curves, orient='index', columns=self.curve_pd.index)
    
        mean_curve = sim_df.mean(axis=0)
        p10_curve = sim_df.quantile(0.10, axis=0)
        p90_curve = sim_df.quantile(0.90, axis=0)
    
        plt.figure(figsize=(14, 6))
        plt.plot(self.curve_pd.index, self.curve_pd.values, label="Original Curve", color="black", linestyle="--", linewidth=2)
        plt.plot(mean_curve.index, mean_curve, label="Mean Simulated Curve", color="blue", linewidth=2)
        plt.fill_between(p10_curve.index, p10_curve, p90_curve, color="blue", alpha=0.2, label="P10–P90 Band")
    
        plt.title("Simulated Scenarios vs Original Curve")
        plt.xlabel("Time")
        plt.ylabel("Price")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()

class forward:
    def __init__(self, market, price, start_date, period, delivery,
                 currency='eur', unit='mwh'):
        self.market = market.lower()
        self.price = price
        self.start_date = start_date
        self.end_date = end_date(start_date, period)
        self.period = period
        self.delivery = delivery
        self.currency = currency.lower()
        self.unit = unit.lower()
        self.__check()

    @property
    def del_dummy(self):
        if self.delivery == 'peak':
            return 0
        else:
            return 1

    def __check(self):
        PERMITTED_DEL = ('base', 'peak')
        PERMITTED_CUR = ('eur', 'usd', 'gbp')
        PERMITTED_UNT = ('mwh', 'btu')
        
        assert self.delivery in PERMITTED_DEL
        assert self.currency in PERMITTED_CUR
        assert self.unit in PERMITTED_UNT

    def __lt__(self, other):
        # Ordering of forwards in order of importance:
        # base < peak
        # early start < late start
        # long product period < short product period
        # price

        return [self.start_date, self.start_date - self.end_date, self.del_dummy,
                self.price] < \
               [other.start_date, other.start_date - other.end_date, other.del_dummy,
                other.price]

    def __eq__(self, other):
        return self.start_date == other.start_date and \
               self.end_date == other.end_date and \
               self.delivery == other.delivery and \
               self.market == other.market and \
               self.currency == other.currency and \
               self.unit == other.unit and \
               self.price == other.price


class shapeindex:
    ## BOTTLENECK: needs optimization
    def __init__(self, key=lambda d: 0, value=np.array([1])):
        self.key = key
        self.value = value

    # division by 3 means that we have 3 types of days
    def indexvec(self, dates):
        return [self.value[self.key(d)] for d in dates]


def mask(date_vec, start_date, end_date, delivery):
    del_arr = getattr(Delivery(date_vec), delivery)
    bool_mask = np.logical_and(np.logical_and(date_vec >= start_date,
                                              date_vec <= end_date),
                               del_arr)
    return bool_mask.astype(float)


def rem_lindep(mat):
    # Removes linearly dependent vectors from matrix

    # QR decomposition
    R = np.linalg.qr(mat, mode= 'r')

    # Which number is regarded as zero
    tol = max(mat.shape) * np.finfo(max(np.abs(np.diag(R)))).eps * 10

    # Initialize first column independent
    s1 = R.shape[0]
    s2 = R.shape[1]
    depdummy = [True, ] * s2
    depdummy[0] = False

    # Vector dependent if orthonormal base does not grow
    c = 1
    r = 1
    while r < s1 and c < s2:
        last_r = r
        while r <= c and r < s1:
            if abs(R[r, c]) > tol:
                depdummy[c] = False
                last_r = r + 1
            r += 1
        c += 1
        r = last_r

    return depdummy


# Ancillary computing functions:

def qp(H, g, A, b):
    # Sparse inputs
    # Solves equality constrained QP
    # Solution of QP solves linear equalities
    # [H At] [ x     ] = [g]
    # [A 0 ] [ lambda]   [b]

    Z = sp.coo_matrix((A.shape[0],A.shape[0]))
    HH = sp.vstack([sp.hstack([H, A.T]), sp.hstack([A, Z])])
    gg = np.concatenate([g, b])

    # CG solution
    x = sp.linalg.lgmres(HH, gg)
    return x[0][0:H.shape[0]]


def smooth_hessian(step, length):
    if length > 2 * step:
        sub_up_diag = np.concatenate([np.zeros(2*step), np.ones(length - 2 * step)])
        main_diag = -2*np.concatenate([np.zeros(step), np.ones(length - 2 * step), np.zeros(step)])
        sub_low_diag = np.concatenate([np.ones(length - 2 * step), np.zeros(2*step)])
        diags = np.vstack([sub_low_diag, main_diag, sub_up_diag])
        return sp.spdiags(diags, [-step, 0, step], length, length)
    else:
        return sp.coo_matrix((length, length))
    
    
def tuple_list(date_vec):
    period = 'M'
    start = date_vec[0]
    end = date_vec[-1]
    tuple_list = []
    while start < end:
        end_aux = end_date(start, period)
        tuple_list.append((start, end_aux))
        start = start_date(start, period)
    M = []
    [M.append(mask(date_vec, x[0], x[1], 'base')) for x in tuple_list]
    return np.stack(M)


def create_nested_list(dimensions):
    # Base case: if there's only one dimension left, create a list of empty lists.
    if len(dimensions) == 1:
        return [[] for _ in range(dimensions[0])]
    # Recursive step: build the current dimension by nesting the remaining dimensions.
    return [create_nested_list(dimensions[1:]) for _ in range(dimensions[0])]


def compute_stat(matrix, func):
    """
    Recursively replaces each innermost list in the nested matrix with the statistic
    computed by applying func (e.g. np.mean, np.median) to that list.
    If an innermost list is empty, returns np.nan.
    """
    return [compute_stat(x, func) if isinstance(x, list) and (len(x) == 0 or isinstance(x[0], list))
            else func(x) if x else np.nan
            for x in matrix]


def cut_blocks(matrix):
    """
    CUT MATRIX INTO INDEPENDENT NON-ZERO BLOCKS
    Identifies which columns and rows belong to which non-zero block of a sparse matrix.

    Parameters:
        matrix (scipy.sparse.spmatrix): Input sparse matrix (CSR or COO format)

    Returns:
        row_idx (np.ndarray): Numeric vector for row indices
        col_idx (np.ndarray): Numeric vector for column indices
    """
    if not sp.issparse(matrix):
        raise ValueError("Input matrix must be a sparse matrix (e.g., CSR, COO format).")
    
    matrix = matrix.tocsr()  # Ensure efficient row slicing
    row_idx = np.full(matrix.shape[0], np.nan)
    col_idx = np.full(matrix.shape[1], np.nan)
    
    old_columns = np.array([])
    columns = matrix[0, :].toarray().ravel() != 0
    
    while not np.array_equal(old_columns, columns):
        old_columns = columns.copy()
        rows = matrix[:, columns].sum(axis=1).A.ravel() != 0
        columns = matrix[rows, :].sum(axis=0).A.ravel() != 0
    
    if np.all(rows) or np.all(columns):
        row_idx[rows] = 1
        col_idx[columns] = 1
    else:
        sub_matrix = matrix[~rows, :][:, ~columns].tocsc()  # Keep it sparse
        row_idx_old, col_idx_old = cut_blocks(sub_matrix)
        
        row_idx[rows] = 1
        row_idx[~rows] = 1 + row_idx_old
        
        col_idx[columns] = 1
        col_idx[~columns] = 1 + col_idx_old
    
    return row_idx, col_idx


def clean_residual_jumps(resid_series, max_iter=100, threshold_sigma=3):
    """
    Removes jump outliers from a residual series using iterative thresholding.
    """

    resid = resid_series.dropna().values

    for i in range(max_iter): 
        mu, sigma = norm.fit(resid)
        threshold = threshold_sigma * sigma
        jump_mask = np.abs(resid - mu) > threshold

        if not np.any(jump_mask):
            print(f"[Jump Cleaning] Converged after {i} iterations.")
            break

        resid[jump_mask] = mu

    return pd.Series(resid, index=resid_series.dropna().index)