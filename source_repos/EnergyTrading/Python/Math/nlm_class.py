#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 24 12:18:57 2023

@author: marek
"""

import numpy as np
import abc
from random import random
tol = 1e-10


class NLModel():
    __metaclass__ = abc.ABCMeta
    def __init__(self, dim, model_name):
        self.dim = dim
        self.name = model_name

    @abc.abstractmethod
    def step(self, X_vec, y):
        pass


class EKF():
    __metaclass__ = abc.ABCMeta
    def __init__(self, f, H, A, Q, R):
        self.f = f
        self.A = A
        self.H = H
        self.Q = Q
        self.R = R
        self.__dim = self.f.size
        self._v = [1.]
        self._u = [0.]
        self.name = 'EKF'

    @abc.abstractmethod
    def kalman_gain(self, P_prior, H_mat):
        pass

    def score(self, u_vec, v_vec):
        L_list = [np.log(abs(f)) + (z * z) / f for z, f in zip(u_vec, v_vec)]
        return -sum(L_list)

    @property
    def dim(self):
        return self.__dim

    @staticmethod
    def eval_mat(matrix, x_vec):
        M_mat = np.empty(matrix.shape, dtype=object)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                element = matrix[i, j]
                M_mat[i, j] = element(x_vec) if callable(element) else element
        return M_mat

    def step(self, z_new, X_prior, P_prior):
        X_pred, P_pred = self.prediction(X_prior, P_prior)
        X_post, P_post = self.update(z_new, X_pred, P_pred)
        return X_post, P_post

    def prediction(self, X_post, P_post):
        X_pred = self.eval_mat(self.f, X_post)
        A_mat = self.eval_mat(self.A, X_post)
        P_pred = A_mat.dot(P_post.dot(A_mat.T)) + self.Q
        return X_pred, P_pred

    def update(self, z_new, X_prior, P_prior):
        H_mat = self.eval_mat(self.H, X_prior)
        # Kalman gain
        K_mat = self.kalman_gain(P_prior, H_mat)
        # Update var cov of observation P matrix
        P_post = (np.eye(self.dim) - K_mat.dot(H_mat)).dot(P_prior)
        # Update prediction
        z_hat = z_new - H_mat.dot(X_prior)
        X_post = X_prior + K_mat.dot(z_hat)
        self._u.append(z_hat.item())
        return X_post, P_post


class VasicekEKF(EKF):
    def __init__(self, Q, R, dt=1):
        f, A, H = self.inputs(dt)
        super().__init__(f, H, A, Q, R)

    def kalman_gain(self, P_prior, H_vec):
        F_k = (H_vec.dot(P_prior.dot(H_vec.T)) + self.R)
        self._v.append(F_k.item())
        return P_prior.dot(H_vec.T) / F_k

    @staticmethod
    def inputs(dt):
        A_mat = np.array([
            [lambda x: 1 - x[1][0] * dt, lambda x: (x[2][0] - x[0][0]) * dt,
             lambda x: x[1][0] * dt], 
            [0, 1, 0], [0, 0, 1]])
        H_mat = np.array([[1, 0, 0]])
        f_vec = np.array([
            [lambda x: (x[1][0] * x[2][0] - x[0][0] * x[1][0]) * dt + x[0][0],
             lambda x: x[1][0], lambda x: x[2][0]]])
        return f_vec.T, A_mat, H_mat


class UKF():
    __metaclass__ = abc.ABCMeta
    def __init__(self, f, h, Q, R, alpha, kappa, beta):
        self.f = f
        self.h = h
        self.Q = Q
        self.R = R
        self.L = 2 * Q.shape[0] + R.shape[0]
        self.update_params(alpha, kappa, beta)
        self.__dim = self.f.size
        self._v = [1.]
        self._u = [0.]
        self.name = 'UKF'

    def update_params(self, alpha, kappa, beta):
        self.__alpha = alpha
        self.__kappa = kappa
        self.__beta = beta
        self.__lamb = alpha * alpha * (self.L + kappa) - self.L
        w_m = self.lamb / (self.lamb + self.L)
        w_vec_i = [1 / (2 * (self.lamb + self.L))] * (2 * self.L)
        W_m_list = [w_m]
        W_c_list = [w_m + (1 - self.alpha ** 2 + self.beta)]
        W_m_list.extend(w_vec_i)
        W_c_list.extend(w_vec_i)
        self.__W_m = np.array(W_m_list).reshape(-1, 1)
        self.__W_c = np.array(W_c_list).reshape(-1, 1)

    @property
    def alpha(self):
        return self.__alpha

    @property
    def kappa(self):
        return self.__kappa

    @property
    def beta(self):
        return self.__beta

    @property
    def lamb(self):
        return self.__lamb

    @property
    def W_m(self):
        return self.__W_m

    @property
    def W_c(self):
        return self.__W_c

    @property
    def dim(self):
        return self.__dim

    @staticmethod
    def sqrt_matrix(M_mat):
        # return np.linalg.cholesky(M_mat)
        # Eigen decomposition
        SS, V = np.linalg.eigh(M_mat)
        # Taking square roots of the eigenvalues
        sqrt_SS = np.sqrt(SS)
        # Constructing the square root matrix
        return np.dot(V, np.dot(np.diag(sqrt_SS), V.T))

    @staticmethod
    def eval_mat(matrix, x_vec):
        M_mat = np.empty(matrix.shape, dtype=object)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                element = matrix[i, j]
                M_mat[i, j] = element(x_vec) if callable(element) else element
        return np.array(M_mat, dtype=float)

    def step(self, z_new, X_prior, P_prior):
        X_pred, P_pred, z_pred, Xs_p, Zs_p = self.prediction(X_prior, P_prior)
        X_post, P_post = self.update(z_new, X_pred, P_pred, z_pred, Xs_p, Zs_p)
        return X_post, P_post

    def __sigma_points(self, x_hat_a, P_prior):
        # Creating Cholesky decompozition of matrix P = A * A_T
        A_mat = self.block_diag(self.sqrt_matrix(P_prior))
        # Create X_a matrix of sigma points
        X_a = x_hat_a
        for i in range(self.L):
            X_i = x_hat_a + A_mat[:, i:i+1] * np.sqrt(self.L + self.lamb)
            X_a = np.concatenate([X_a, X_i], axis=1)
        for i in range(self.L):
            X_i = x_hat_a - A_mat[:, i:i+1] * np.sqrt(self.L + self.lamb)
            X_a = np.concatenate([X_a, X_i], axis=1)
        return X_a

    def prediction(self, X_post, P_post):
        m_x = self.Q.shape[0]
        m_u = self.R.shape[0]
        # Create augmented state vector
        x_hat_a = np.concatenate([X_post, np.zeros((m_x, 1)), np.zeros((m_u, 1))])
        # Create sigma points
        X_sigm = self.__sigma_points(x_hat_a, P_post)
        # Select states from augmented vector of sigma points
        X_x = X_sigm[:m_x, :]
        X_w = X_sigm[m_x:m_x * 2, :]
        X_u = X_sigm[m_x * 2:, :]
        # Create prediction from sigma points and x_prior
        for i in range(2 * self.L + 1):
            xw_vec = np.concatenate([X_x[:, i:i+1], X_w[:, i:i+1]], axis=1)
            x = self.eval_mat(self.f, xw_vec)
            try:
                X_mat_prior = np.concatenate([X_mat_prior, x], axis=1)
            except(NameError):
                X_mat_prior = x
        X_prior = X_mat_prior.dot(self.W_m)
        # Create prior var cov matrix P
        X_c = X_mat_prior - X_prior
        P_prior = np.dot(X_c, np.dot(np.diag(self.W_c.reshape(-1)), X_c.T))
        P_prior = self.check_matrix(P_prior)
        # Create prior observation
        for i in range(2 * self.L + 1):
            X_i = X_mat_prior[:, i:i+1]
            xu_vec = np.concatenate([X_i, X_u[:, i:i+1]])
            z = self.eval_mat(self.h, xu_vec)
            try:
                Z_mat_prior = np.concatenate([Z_mat_prior, z], axis=1)
            except(NameError):
                Z_mat_prior = z
        z_prior = Z_mat_prior.dot(self.W_m)
        return X_prior, P_prior, z_prior, X_mat_prior, Z_mat_prior

    def update(self, z_new, X_prior, P_prior, z_prior, X_mat_prior, Z_mat_prior):
        # Calculate Kalman Gain
        for i in range(2 * self.L + 1):
            X_i = X_mat_prior[:, i:i+1]
            z_i = Z_mat_prior[:, i:i+1]
            try:
                P_zz += (z_i - z_prior).dot((z_i - z_prior).T) * self.W_c[i]
                P_xz += (X_i - X_prior).dot((z_i - z_prior).T) * self.W_c[i]
            except(NameError):
                P_zz = (z_i - z_prior).dot((z_i - z_prior).T) * self.W_c[i]
                P_xz = (X_i - X_prior).dot((z_i - z_prior).T) * self.W_c[i]
        K_mat = self.kalman_gain(P_xz, P_zz)
        # Update var cov of observation P matrix
        P_post = P_prior - K_mat.dot(P_zz.dot(K_mat.T))
        # Update prediction
        z_hat = z_new - z_prior
        X_post = X_prior + K_mat.dot(z_new - z_prior)
        self._u.append(z_hat.item())
        return X_post, P_post

    @staticmethod
    def check_matrix(P_mat, is_var=True, tol=1e-9):
        if is_var:
            np.fill_diagonal(P_mat, np.where(np.diag(P_mat) < tol,
                                             tol, np.diag(P_mat)))
        P_mat[np.abs(P_mat) < tol] = 0
        return P_mat       

    @abc.abstractmethod
    def block_diag(self, A_mat):
        pass

    @abc.abstractmethod
    def kalman_gain(self, P_xz, P_zz):
        pass

    def score(self, u_vec, v_vec):
        L_list = [np.log(abs(f)) + (z * z) / f for z, f in zip(u_vec, v_vec)]
        return -sum(L_list)


class VasicekUKF(UKF):
    def __init__(self, Q, R, dt=1, alpha=1e-3, kappa=0, beta=2.):
        f, h = self.inputs(dt)
        R_mat = np.array([[R]])
        super().__init__(f, h, Q, R_mat, alpha, kappa, beta)
        self.__QL = self.sqrt_matrix(Q)
        self.__RL = np.array([[np.sqrt(R)]])

    @property
    def QL(self):
        return self.__QL

    @property
    def RL(self):
        return self.__RL

    def block_diag(self, A_mat):
        m1, n1 = A_mat.shape
        m2, n2 = self.QL.shape
        m3, n3 = self.RL.shape
        return np.block([
            [A_mat, np.zeros((m1, n2 + n3))],
            [np.zeros((m2, n1)), self.QL, np.zeros((m2, n3))],
            [np.zeros((m3, n1 + n2)), self.RL]])

    def kalman_gain(self, P_xz, P_zz):
        self._v.append(P_zz[0][0])
        return P_xz / P_zz[0][0]

    @staticmethod
    def inputs(dt):
        h_vec = np.array([[lambda x: x[0][0] + x[3][0]]])
        f_vec = np.array([
            [lambda x: (x[1][0] * x[2][0] - x[0][0] * x[1][0]) * dt + x[0][0] + x[0][1],
             lambda x: x[1][0] + x[1][1],
             lambda x: x[2][0] + x[2][1]]])          
        return f_vec.T, h_vec
