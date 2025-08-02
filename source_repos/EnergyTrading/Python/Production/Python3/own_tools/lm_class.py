import numpy as np
import abc
tol = 1e-10


class FTRLmodel:
    __init_bool = None
    zt = None
    nt = None
    gt = None
    yhat = None
    __params = None
    __metaclass__ = abc.ABCMeta

    def __init__(self, dim, intercept, lambda1, lambda2, alpha, beta, norm_g, adaptive_l1):
        self.dim = dim
        self.intercept = intercept
        self.lambda1 = lambda1
        self.lambda2 = lambda2
        self.alpha = alpha
        self.beta = beta
        self.__normalize = norm_g
        self.__adaptive = adaptive_l1
        self.__tol = tol
        self.__model_name = None
        self._n = 0
        self.__init_bool = True

    @abc.abstractmethod
    def predict(self, x_vec):
        pass

    @property
    def params(self):
        return self.__params

    @property
    def tol(self):
        return self.__tol

    @property
    def d(self):
        if self.intercept:
            return self.dim + 1
        else:
            return self.dim

    @property
    def norm_g(self):
        return self.__normalize

    @norm_g.setter
    def norm_g(self, value):
        if isinstance(value, bool):
            self.__normalize = value
        else:
            raise ValueError("FTRLmodel: norm_g must be a boolean %s" % value)

    @property
    def adaptive_l1(self):
        return self.__adaptive

    @adaptive_l1.setter
    def adaptive_l1(self, value):
        if isinstance(value, bool):
            self.__adaptive = value
        else:
            raise ValueError("FTRLmodel: adaptive_l1 must be a boolean %s" % value)

    def next_step(self):
        self._n += 1

    def set_params(self, param_list, zt_list, nt_list, gt_list):
        self.__params = np.asarray(param_list)
        self.zt = np.asarray(zt_list)
        self.nt = np.asarray(nt_list)
        self.gt = np.asarray(gt_list)
        self.yhat = self.predict(np.zeros(self.d))
        self.__init_bool = False

    def push(self, x_new, y_new):
        self.next_step()
        for i in range(self.d):
            if x_new[i] == 0:
                continue
            # Update regression params
            if abs(self.zt[i]) <= self.lambda1:
                self.__params[i] = 0
            else:
                self.__params[i] = -1 / ((self.beta + np.sqrt(self.nt[i])) / self.alpha + self.lambda2)
                if self.zt[i] >= 0:
                    self.__params[i] *= (self.zt[i] - self.lambda1)
                else:
                    self.__params[i] *= (self.zt[i] + self.lambda1)
        # Calculate gradient
        g = self.gradient(x_new, y_new)
        if self.__normalize:
            norm = np.sqrt(g.T @ g)
            if norm < tol:
                g /= tol
            else:
                g /= norm
        self.gt = g
        # Update lambda1
        self.__update_lambda(g)
        for i in range(self.d):
            if x_new[i] == 0:
                continue
            # Update params
            sigma = (np.sqrt(self.nt[i] + g[i] ** 2) - np.sqrt(self.nt[i])) / self.alpha
            self.nt[i] += g[i] ** 2
            self.zt[i] += g[i] - sigma * self.params[i]
        return self.yhat

    def gradient(self, x, y):
        self.yhat = self.predict(x)
        return x.T * (self.yhat - y)

    def fit(self, x_vec, y):
        y_hat = []
        for x_, y_ in zip(x_vec, y):
            if self.intercept:
                x_train = np.concatenate([[1], x_])
            else:
                x_train = x_
            y_hat.append(self.predict(x_train))
            self.push(x_train, y_)
        return np.asarray(y_hat).reshape(-1, )

    def unc_score(self, x_new):
        score = 0
        for i in range(self.d):
            if x_new[i] == 0:
                continue
            score += self.alpha * (x_new[i]) / (self.beta + np.sqrt(self.nt[i]))
        return score

    def __update_lambda(self, gl):
        # Update parameter lambda for lasso
        if not self.__adaptive:
            return 0
        ni = 1 / ((self.beta + np.sqrt(self.nt)) / self.alpha + self.lambda2)
        g = np.sign(self.zt) * ni * gl
        idx = abs(self.zt) < self.lambda1
        g[idx] = 0
        eta = 1 / np.sqrt(self._n)
        self.lambda1 -= eta * sum(g)
        self.lambda1 = max(0, self.lambda1)
        return self.lambda1


class LinearOnlineModel(FTRLmodel):
    def __init__(self, dim, intercept=False, lambda1=10, lambda2=0, alpha=.5, beta=1e-7,
                 norm_g=False, adaptive_l1=False):
        # Initialize Parent object
        super().__init__(dim, intercept, lambda1, lambda2, alpha, beta, norm_g, adaptive_l1)
        self.__model_name = 'Linear Model'

    def predict(self, x_vec):
        fx = x_vec @ self.params
        return fx


class LogisticOnlineModel(FTRLmodel):
    def __init__(self, dim, intercept=False, lambda1=10, lambda2=0, alpha=.5, beta=1,
                 norm_g=False, adaptive_l1=False):
        # Initialize Parent object
        super().__init__(dim, intercept, lambda1, lambda2, alpha, beta, norm_g, adaptive_l1)
        self.__model_name = 'Logistic Model'

    def predict(self, x_vec):
        fx = x_vec @ self.params
        return 1. / (1. + np.exp(-max(min(fx, 35.), -35.)))


class LinearOffline:
    __init_bool = None
    yhat = None
    __params = None
    __metaclass__ = abc.ABCMeta

    def __init__(self, dim, intercept):
        self.dim = dim
        self.intercept = intercept
        self.__model_name = None
        self._n = 0
        self.__init_bool = True

    @abc.abstractmethod
    def predict(self, x_vec):
        pass

    @property
    def params(self):
        return self.__params

    @property
    def d(self):
        if self.intercept:
            return self.dim + 1
        else:
            return self.dim

    def next_step(self):
        self._n += 1

    def set_params(self, param_list):
        self.__params = np.asarray(param_list)
        self.yhat = self.predict(np.zeros(self.d))
        self.__init_bool = False

    def push(self, x_new, y_new):
        self.next_step()
        return self.predict(x_new)


class LinearOfflineModel(LinearOffline):
    def __init__(self, dim, intercept):
        # Initialize Parent object
        super().__init__(dim, intercept)
        self.__model_name = 'Linear Model'

    def predict(self, x_vec):
        fx = x_vec @ self.params
        return fx


class LogisticOfflineModel(LinearOffline):
    def __init__(self, dim, intercept):
        # Initialize Parent object
        super().__init__(dim, intercept)
        self.__model_name = 'Logistic Model'

    def predict(self, x_vec):
        fx = x_vec @ self.params
        return 1. / (1. + np.exp(-max(min(fx, 35.), -35.)))


class Kalman1D:
    def __init__(self, Q, R):
        self.Q = Q
        self.R = R

    def step(self, y_new, x_new, beta_prior, P_prior):
        beta_pred, P_pred = self.prediction(y_new, beta_prior, P_prior)
        beta_post, P_post = self.update(y_new, x_new, beta_pred, P_pred)
        return beta_post, P_post

    def update(self, y, x, beta_prior, P_prior):
        # Kalman gain
        K_t = P_prior * x / (x * x * P_prior + self.R)
        # Update var cov of observation P matrix
        P_post = (1 - K_t * x) * P_prior
        # Update prediction
        beta_post = beta_prior + K_t * (y - beta_prior * x)
        return beta_post, P_post

    def prediction(self, y_new, beta_post, P_post):
        P_pred = P_post + self.Q
        beta_pred = beta_post * 1
        return beta_pred, P_pred
