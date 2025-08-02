# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 15:50:43 2020

@author: zelenaymar
"""

import scipy.sparse as sp
import scipy.io
import numpy as np
import pandas as pd
import datetime as dt
from cvxopt import solvers, matrix, spmatrix


class SmoothCurveIE:
    def __init__(self, step, method='standard', verbosity=False):
        self.step = step

        f_keys = ['dates', 'mask_bid', 'mask_ask', 'price_bid', 'price_ask',
                  'contr', 'mask_xmass']
        i_keys = ['idx_a', 'idx_b']
        o_keys = ['curve', 'mask', 'price_bid', 'price_ask']
        self.forward_dict = {k: None for k in f_keys}
        self.indices_dict = {k: None for k in i_keys}
        self.outputs_dict = {k: None for k in o_keys}
        self.__penalty_mat = []
        self.__smooth_fact = np.nan
        self.__scale_fact = 1.0
        self.__init_vec = None
        self.__method = method
        self.__isverbose = verbosity

    @property
    def forward_contr(self):
        return self.forward_dict['contr']

    @property
    def forward_prods(self):
        return self.outputs_dict['prod']

    @property
    def smooth_lambd(self):
        if self.__smooth_fact < 1e-10:
            smooth_fact = 1e-10
        elif self.__smooth_fact > 1 - 1e-10:
            smooth_fact = 1 - 1e-10
        else:
            smooth_fact = self.__smooth_fact
        return (1 - smooth_fact) / smooth_fact

    @property
    def method(self):
        return self.__method

    @property
    def isverbose(self):
        return self.__isverbose

    @property
    def scale_fact(self):
        return self.__scale_fact

    @property
    def init_vec(self):
        return self.__init_vec

    @property
    def idx_a(self):
        return self.indices_dict['idx_a']

    @property
    def idx_b(self):
        return self.indices_dict['idx_b']

    def set_scale(self, scale_factor):
        self.__scale_fact = scale_factor

    def set_init(self, init_vec):
        self.__init_vec = matrix(init_vec)

    def eval_curve(self, curve_vec):
        mask = self.outputs_dict['mask']
        m, n = mask.shape
        curve_vec = curve_vec.reshape((n, 1))

        p_vec = mask @ curve_vec
        b_vec = self.outputs_dict['price_bid']
        a_vec = self.outputs_dict['price_ask']
        da_vec = np.clip(p_vec - a_vec, 0, None)
        db_vec = np.clip(b_vec - p_vec, 0, None)
        # Round to 0.5 cents
        da_vec = np.round(da_vec * 200) / 200
        db_vec = np.round(db_vec * 200) / 200

        name_list = ['bid_val', 'ask_val', 'crv_val', 'bid_exc', 'ask_exc']
        out_dict = {k: [] for k in name_list}
        out_dict['bid_val'] = b_vec.reshape((m,)).tolist()
        out_dict['crv_val'] = p_vec.reshape((m,)).tolist()
        out_dict['ask_val'] = a_vec.reshape((m,)).tolist()
        out_dict['bid_exc'] = db_vec.reshape((m,)).tolist()
        out_dict['ask_exc'] = da_vec.reshape((m,)).tolist()
        row_dict = {k: v for k, v in enumerate(self.forward_prods)}
        return pd.DataFrame.from_dict(out_dict).rename(index=row_dict)

    def create_curve(self, forward_ask, forward_bid, forward_prd,
                     smooth_factor, xmass_dict={}, res_prod=[], c_type='ns'):
        # start_time = dt.datetime.now().timestamp()
        # Creating curve
        self.__smooth_fact = smooth_factor

        # Preparing matrix
        M_mat_p, dates = forward_prd.create_mask(self.step, norm_bool=True)

        self.outputs_dict['mask'] = M_mat_p
        self.outputs_dict['prod'] = forward_prd.period

        # Contracts
        c_list = [x for x, p in zip(forward_prd.contract, forward_prd.period)
                  if p not in res_prod]

        self.forward_dict['dates'] = dates
        self.forward_dict['contr'] = c_list

        m = self.prepare_prodmat(forward_bid, forward_ask, forward_prd,
                                 res_prod)
        # Add xmass conditions
        if not xmass_dict:
            pass
        else:
            self.prepare_xmat(xmass_dict['fwd_xmass'], xmass_dict['fwd_contr'],
                              xmass_dict['vec_xmass'])

        n = M_mat_p.shape[1]
        if c_type == 'ns':
            H_mat = self.prepare_penalty_ns(n)
        elif c_type == 'bs':
            H_mat = self.prepare_penalty_bs(n)
        else:
            raise ValueError('Unknown smoothing method. ', c_type)
        H_mat, f_vec, A_mat, b_vec = self.prepare_param(H_mat, m, n)
        res = self.optimize(f_vec, H_mat, A_mat, b_vec, self.smooth_lambd,
                            self.init_vec)
        curve_vec = np.asarray(res['x'][:n]).reshape(n,) * self.scale_fact
        self.outputs_dict['curve'] = curve_vec
        # end_time = dt.datetime.now().timestamp()
        # print(end_time - start_time)
        return pd.Series(curve_vec, index=dates)

    def prepare_param(self, H_mat, m, n):
        M_mat_a = self.forward_dict['mask_ask_f']
        M_mat_b = self.forward_dict['mask_bid_f']
        p_vec_a = self.forward_dict['price_ask_f']
        p_vec_b = self.forward_dict['price_bid_f']

        m_a = np.sum(self.idx_a)
        m_b = np.sum(self.idx_b)

        # Prameters of mask matrix and calculate normalizing vector
        s_vec = self.normalize_error()
        """
        # s_vec = np.abs(np.asarray(M_mat.sum(axis=1)).reshape((m,)))
        s_vec = M_mat.getnnz(axis=1).reshape((m,))
        # Find indices of time spreads
        idx_ts = np.array([True if x == 'ts' else False
                           for x in self.forward_contr])
        s_vec[idx_ts] = s_vec[idx_ts] / 2
        """
        # Creating A matrix
        I_mat = sp.identity(m)
        I_vec = np.arange(m)
        I_mat_a = sp.coo_matrix((np.ones(m_a,), (np.arange(m_a), I_vec[self.idx_a])),
                                shape=(m_a, m))
        I_mat_b = sp.coo_matrix((np.ones(m_b,), (np.arange(m_b), I_vec[self.idx_b])),
                                shape=(m_b, m))
        Z_mat = sp.coo_matrix((m, n))
        A_mat = sp.vstack([sp.hstack([M_mat_a, -I_mat_a]),
                           sp.hstack([-M_mat_b, -I_mat_b]),
                           sp.hstack([Z_mat, -I_mat])])
        # Right hand vector
        # p_vec = self.forward_dict['price'] * s_vec.reshape((m, 1))
        p_vec = np.concatenate((p_vec_a, -p_vec_b), axis=0)
        b_vec = np.concatenate([p_vec, np.zeros((m, 1))])
        # Add fixed products
        if self.forward_dict['mask_ask_x'] is not None:
            M_mat_xa = self.forward_dict['mask_ask_x']
            M_mat_xb = self.forward_dict['mask_bid_x']
            p_vec_xa = self.forward_dict['price_ask_x']
            p_vec_xb = self.forward_dict['price_bid_x']
            m_xa = M_mat_xa.shape[0]
            m_xb = M_mat_xb.shape[0]
            Z_mat_ea = sp.coo_matrix((m_xa, m))
            Z_mat_eb = sp.coo_matrix((m_xb, m))
            # Extend A matrix & b vector
            A_mat = sp.vstack([A_mat,
                               sp.hstack([M_mat_xa, Z_mat_ea]),
                               sp.hstack([-M_mat_xb, Z_mat_eb])])
            p_vec_x = np.concatenate((p_vec_xa, -p_vec_xb), axis=0)
            b_vec = np.concatenate([b_vec, p_vec_x])
        if self.forward_dict['mask_xmass'] is not None:
            M_mat_xs = self.forward_dict['mask_xmass']
            m_xs = M_mat_xs.shape[0]
            Z_mat_ex = sp.coo_matrix((m_xs, m))
            A_mat = sp.vstack([A_mat,
                               sp.hstack([M_mat_xs, Z_mat_ex])])
            x_vec_c = np.zeros((m_xs, 1))
            b_vec = np.concatenate([b_vec, x_vec_c])

        # Creating f vector of error weights
        # f_vec = np.concatenate([np.zeros((n, 1)), n * np.ones((m, 1))])
        f_vec = np.concatenate([np.zeros((n, 1)), s_vec.reshape((m, 1))])
        # Extend dimensions of H_mat
        H_mat = sp.vstack([sp.hstack([H_mat,  sp.coo_matrix((n, m))]),
                           sp.coo_matrix((m, m + n))])
        return H_mat, f_vec, A_mat, b_vec

    def prepare_penalty_ns(self, n):
        # Preparation of penalty matrix with basis of natural splines
        if self.step == 'D':
            knot_vec = np.arange(0, n) / (30 * 4)
        elif self.step == 'M':
            knot_vec = np.arange(0, n) / 1
        dx = knot_vec[1:] - knot_vec[:-1]
        # Constructing W matrix (n - 2) x (n - 2)
        if (np.abs(dx[1:] - dx[:-1]) < 1e-6).all():
            W_mat_inv = inv_toepl3(2 * dx[0] / 3, dx[0] / 6, n - 2)
        else:
            diag_vec = np.vstack((dx[1:], 2 * (dx[1:] + dx[:-1]), dx[:-1])) / 6
            W_mat = sp.spdiags(diag_vec, [-1, 0, 1], n - 2, n - 2)
            W_mat_inv = sp.linalg.inv(W_mat)
        # Calculate delta matrix (n - 2) x n
        odx = 1. / dx
        elems_vec = np.vstack((odx[:-1], -(odx[:-1] + odx[1:]), odx[1:]))
        D_mat = sp.diags(elems_vec, [0, 1, 2], (n - 2, n))
        self.__penalty_mat = D_mat.T @ (W_mat_inv @ D_mat)
        return self.__penalty_mat

    def normalize_error(self):
        # Normalize errors
        if self.method == 'standard':
            return self.normalize_error_standard()
        elif self.method == 'norm':
            return self.normalize_error_norm()
        else:
            msg = 'Choose between norm/standard method. '
            raise ValueError(msg, self.method)

    def normalize_error_standard(self):
        # M_mat = sp.csr_matrix(self.forward_dict['mask_ask_f'])
        M_mat = sp.csr_matrix(self.forward_dict['mask_prd_t'])
        m, n = M_mat.shape
        n_e = len(M_mat.indices)
        M_mat_abs = sp.csr_matrix(([1] * n_e, M_mat.indices, M_mat.indptr),
                                  shape=(m, n))
        # Sum of columns
        sum_col = M_mat_abs.getnnz(axis=1).reshape((m, 1))
        # Find indices of time spreads
        idx_ts = np.array([True if x == 'ts' else False
                           for x in self.forward_contr])
        sum_col[idx_ts] = sum_col[idx_ts] / 2
        # Calculate weight matrix
        w_vec = sum_col
        return w_vec

    def normalize_error_norm(self):
        M_mat = sp.csr_matrix(self.forward_dict['mask_prd_t'])
        m, n = M_mat.shape
        n_e = len(M_mat.indices)
        M_mat_abs = sp.csr_matrix(([1] * n_e, M_mat.indices, M_mat.indptr),
                                  shape=(m, n))
        # Sum of columns
        sum_row = M_mat_abs.sum(axis=0).reshape((n, 1))
        sum_col = M_mat_abs.getnnz(axis=1).reshape((m, 1))
        # Find indices of time spreads
        idx_ts = np.array([True if x == 'ts' else False
                           for x in self.forward_contr])
        sum_col[idx_ts] = sum_col[idx_ts] / 2
        # Calculate weight matrix
        w_vec = sum_col / (np.absolute(M_mat) @ sum_row)
        return w_vec

    def prepare_prodmat(self, forward_bid, forward_ask, forward_prd, fix_prod):
        # Prepare & divide products to fixed & floating
        # Preparing matrix
        M_mat_a, _ = forward_ask.create_mask(self.step, norm_bool=True)
        M_mat_b, _ = forward_bid.create_mask(self.step, norm_bool=True)
        M_mat_p = self.outputs_dict['mask']

        # Tenors of products
        prd_list = forward_prd.period
        ask_list = forward_ask.period
        bid_list = forward_bid.period

        p_vec_a = np.atleast_2d(forward_ask.price).T / self.scale_fact
        p_vec_b = np.atleast_2d(forward_bid.price).T / self.scale_fact
        # Index products fixed
        idx_xb = [True if p in fix_prod else False for p in bid_list]
        idx_xa = [True if p in fix_prod else False for p in ask_list]
        idx_xp = [True if p in fix_prod else False for p in prd_list]
        # Remove fix items in bid/ask tenors (truncated)
        prd_list_t = [x for x, i in zip(prd_list, idx_xp) if not i]
        ask_list_t = [x for x, i in zip(ask_list, idx_xa) if not i]
        bid_list_t = [x for x, i in zip(bid_list, idx_xb) if not i]

        idx_xb = np.asarray(idx_xb)
        idx_xa = np.asarray(idx_xa)
        idx_xp = np.asarray(idx_xp)

        m = np.sum(~idx_xp)
        n = len(prd_list)

        # Indexing existing bid/ask that are not fixed products
        idx_a = [True if p in ask_list_t else False for p in prd_list_t]
        idx_b = [True if p in bid_list_t else False for p in prd_list_t]
        self.indices_dict['idx_a'] = np.asarray(idx_a)
        self.indices_dict['idx_b'] = np.asarray(idx_b)
        # Indexing all bid/ask (without truncation)
        idx_ta = np.asarray([True if p in ask_list else False for p in prd_list])
        idx_tb = np.asarray([True if p in bid_list else False for p in prd_list])

        # Floating products
        self.forward_dict['mask_prd_t'] = sp.coo_matrix(M_mat_p[~idx_xp, :])
        self.forward_dict['mask_bid_f'] = sp.coo_matrix(M_mat_b[~idx_xb, :])
        self.forward_dict['mask_ask_f'] = sp.coo_matrix(M_mat_a[~idx_xa, :])
        self.forward_dict['price_bid_f'] = p_vec_b[~idx_xb]
        self.forward_dict['price_ask_f'] = p_vec_a[~idx_xa]
        # Fixed products
        if np.sum(idx_xb) > 0:
            self.forward_dict['mask_bid_x'] = sp.coo_matrix(M_mat_b[idx_xb, :])
            self.forward_dict['price_bid_x'] = p_vec_b[idx_xb]
        else:
            self.forward_dict['mask_bid_x'] = None
            self.forward_dict['price_bid_x'] = None
        if np.sum(idx_xa) > 0:
            self.forward_dict['mask_ask_x'] = sp.coo_matrix(M_mat_a[idx_xa, :])
            self.forward_dict['price_ask_x'] = p_vec_a[idx_xa]
        else:
            self.forward_dict['mask_ask_x'] = None
            self.forward_dict['price_bid_x'] = None
        # All products
        self.outputs_dict['price_bid'] = np.empty((n, 1)) * np.nan
        self.outputs_dict['price_ask'] = np.empty((n, 1)) * np.nan
        # Fill it with prices
        self.outputs_dict['price_bid'][idx_tb] = p_vec_b * self.scale_fact
        self.outputs_dict['price_ask'][idx_ta] = p_vec_a * self.scale_fact
        return m

    def prepare_xmat(self, forward_xmass, forward_contr, bound_vec):
        dates = self.forward_dict['dates']
        M_mat_x, _ = forward_xmass.create_mask(self.step, date_vec=dates, norm_bool=True)
        M_mat_c, _ = forward_contr.create_mask(self.step, date_vec=dates, norm_bool=True)
        l_val = bound_vec[0]
        u_val = bound_vec[1]
        M_mat_l = -M_mat_x + l_val * M_mat_c
        M_mat_l = sp.coo_matrix(M_mat_l)
        M_mat_u = M_mat_x - u_val * M_mat_c
        M_mat_u = sp.coo_matrix(M_mat_u)
        self.forward_dict['mask_xmass'] = sp.vstack([M_mat_l, M_mat_u])

    @staticmethod
    def optimize(f_vec, H_mat, A_mat, b_vec, smooth_factor, init_vec):
        # Optimization part
        # Prepare matrices to cvxopt form
        H_mat = scipy_sparse_to_spmatrix(H_mat * smooth_factor)
        A_mat = scipy_sparse_to_spmatrix(A_mat)
        b_vec = matrix(b_vec)
        f_vec = matrix(f_vec)
        options = dict()
        options['show_progress'] = False
        if init_vec is None:
            res = solvers.qp(H_mat, f_vec, A_mat, b_vec, options=options)
        else:
            res = solvers.qp(H_mat, f_vec, A_mat, b_vec, initvals=init_vec,
                             options=options)
        return res


def scipy_sparse_to_spmatrix(A):
    """Efficient conversion from scipy sparse matrix to cvxopt sparse matrix"""
    coo = A.tocoo()
    SP = spmatrix(coo.data.tolist(), coo.row.tolist(), coo.col.tolist(),
                  size=A.shape)
    return SP


def resample_index(index, freq):
    assert isinstance(index, pd.DatetimeIndex)
    start_date = index.min()
    end_date = index.max() + pd.DateOffset(days=1)
    resampled_index = pd.date_range(start_date, end_date, freq=freq)
    return resampled_index


def inv_toepl3A(d, a, n):
    # Efficient calculation of tridiagonal symmetric toeplitz matrix
    # Creating factor vector
    rng = range(2, n + 1)
    phi_vec = [1, d]
    [phi_vec.append(d * phi_vec[-1] - (a ** 2) * phi_vec[-2]) for i in rng]
    m = [[(-1 ** (i + j)) * (a ** (j - i)) * phi_vec[i - 1] * phi_vec[-(j + 1)] / phi_vec[-1]
          if i <= j else 0 for i in range(1, n + 1)] for j in range(1, n + 1)]
    inv_mat = np.array(m)
    inv_mat = inv_mat + inv_mat.T - np.diag(inv_mat.diagonal())
    return inv_mat


def inv_toepl3(a, b, n):
    # Prepare data
    i = 0
    data = []
    row = []
    col = []
    if abs(a - 2 * b) < 1e-6:
        while i < n + 1:
            i += 1
            for j in range(i, n + 1):
                val = ch_mult1p(b, i, j, n)
                if abs(val) <= 1e-6:
                    continue
                else:
                    data.append(val)
                    row.append(i - 1)
                    col.append(j - 1)
    else:
        # rp = (a + np.sqrt((a ** 2) - 4 * (b ** 2))) / (2 * b)
        # rn = (a - np.sqrt((a ** 2) - 4 * (b ** 2))) / (2 * b)
        phi = np.arccosh(a / (2 * b))
        sinphi = np.sinh(phi)
        while i < n + 1:
            i += 1
            for j in range(i, n + 1):
                # val = ch_mult(b, i, j, rp, rn, n)
                val = ch_multN(b, i, j, phi, sinphi, n)
                if abs(val) <= 1e-4:
                    break
                else:
                    data.append(val)
                    row.append(i - 1)
                    col.append(j - 1)
    data = np.array(data)
    row = np.array(row)
    col = np.array(col)
    inv_mat = sp.csr_matrix((data, (row, col)), shape=(n, n))
    return inv_mat + inv_mat.T - sp.diags(inv_mat.diagonal(), 0, shape=(n, n))


def ch_mult1p(b, i, j, n):
    return ((-1) ** (i + j)) * (i * (n - j + 1) / (n + 1)) / b


def ch_mult(b, i, j, rp, rn, n):
    U_i = ((rp ** i) - (rn ** i))
    U_j = ((rp ** (n - j + 1)) - (rn ** (n - j + 1)))
    U_n = ((rp ** (n + 1)) - (rn ** (n + 1)))
    return ((-1) ** (i + j)) * (U_i * U_j / (U_n * (rp - rn))) / b


def ch_multN(b, i, j, phi, sinphi, n):
    U = ((np.exp(phi * (i - j)) * (1 - np.exp(-2 * phi * (n - j + 1))) *
          (1 - np.exp(-2 * phi * i)) / (1 - np.exp(-2 * phi * (n + 1)))) /
         (2 * sinphi))
    return ((-1) ** (i + j)) * U / b


def calc_Hmat(n):
    # Preparation of penalty matrix with basis of natural splines
    knot_vec = np.arange(0, n) / 1
    dx = knot_vec[1:] - knot_vec[:-1]
    # Constructing W matrix (n - 2) x (n - 2)
    if (np.abs(dx[1:] - dx[:-1]) < 1e-6).all():
        W_mat_inv = inv_toepl3(2 * dx[0] / 3, dx[0] / 6, n - 2)
    else:
        diag_vec = np.vstack((dx[1:], 2 * (dx[1:] + dx[:-1]), dx[:-1])) / 6
        W_mat = sp.spdiags(diag_vec, [-1, 0, 1], n - 2, n - 2)
        W_mat_inv = sp.linalg.inv(W_mat)
    # Calculate delta matrix (n - 2) x n
    odx = 1. / dx
    elems_vec = np.vstack((odx[:-1], -(odx[:-1] + odx[1:]), odx[1:]))
    D_mat = sp.diags(elems_vec, [0, 1, 2], (n - 2, n))
    H_mat = D_mat.T @ (W_mat_inv @ D_mat)
    return H_mat.todense()
