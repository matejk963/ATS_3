import numpy as np


class EMA:
    def __init__(self, tau, value0=0):
        self.tau = tau
        self.value = value0
        self.z = 0

    def push(self, z, dt=1.):

        # reference implementation
        # alpha = dt / self.tau
        # mu = np.exp(-alpha)

        # linear interpolation
        # if mu == 1:
        #     nu = 0
        # else:
        #     nu = (1-mu) / alpha
        # next point interpolation
        #  nu = mu

        # self.value = mu * self.value + (nu-mu) * self.z + (1-nu) * z
        # self.z = z

        if np.isnan(z):
            pass
        else:
            self.value = self._ema_push_(z, self.z, self.value, dt, self.tau)
            self.z = z
        return self.value

    @staticmethod
    def _ema_push_(z, z0, value, dt, tau):
        alpha = dt / tau
        mu = np.exp(-alpha)

        # previous point interpolation
        # nu = 1

        # linear interpolation
        if mu == 1:
            nu = 0
        else:
            nu = (1 - mu) / alpha

        # next point interpolation
        # nu = mu

        value = mu * value + (nu - mu) * z0 + (1 - nu) * z
        return value


class IteratedEMA:
    def __init__(self, tau, n, value0=0):
        self.value = np.nan
        self.n = n
        self._ema = [EMA(tau, value0) for _ in range(n)]

    def push(self, z, dt=1.):
        for ema in self._ema:
            ema.push(z, dt)
            z = ema.value

        self.value = z
        return self.value


class DifferentialEMA:
    def __init__(self, tau, value0=0):
        self.value = np.nan

        self.__beta = 0.65
        self.__gamma = 1.22208
        self.__alpha = 1 / (self.__gamma * (8 * self.__beta - 3))
        # this is actually evaluation of 6 different emas not 7
        # could be unrolled/cached
        self._ema = [EMA(self.__alpha * tau, value0),
                     IteratedEMA(self.__alpha * tau, 2, value0),
                     IteratedEMA(self.__alpha * self.__beta * tau, 4, value0)]

        self.__coeffs = [self.__gamma, self.__gamma, -2 * self.__gamma]

    def push(self, z, dt=1.):
        val = 0
        for i in range(3):
            self._ema[i].push(z, dt)
            val += self.__coeffs[i] * self._ema[i].value

        self.value = val
        return self.value


class DerivativeEMA:
    def __init__(self, tau, n=1., gamma=.5, value0=0):
        tau_ = tau / n
        self.tau = tau_
        self.value = np.nan

        self._diffema = [DifferentialEMA(tau_, value0) for i in range(n)]
        self._gamma = gamma

    def push(self, z, dt=1.):
        val = z
        for diff_ema in self._diffema:
            val = diff_ema.push(val, dt)
            val /= (self.tau ** self._gamma)
        self.value = val
        return self.value


class MA:
    def __init__(self, tau, n, value0=0):
        self.value = np.nan
        self.sum = 0
        self.n = n
        self.tau = tau
        self._ema = [IteratedEMA(2*tau/(n+1), k, value0)
                     for k in range(n)]

    def push(self, z, dt=1):
        self.sum = 0
        for ema in self._ema:
            ema.push(z, dt)
            self.sum += ema.value

        self.value = self.sum / self.n
        return self.value


class MSTD:
    def __init__(self, tau, n, p=2., value0=0):
        self.tau = tau
        self.value = np.nan
        self.p = p
        self._ma = [MA(tau, n, value0), MA(tau, n, 0)]

    @property
    def mean(self):
        return self._ma[0]

    @property
    def var(self):
        return self._ma[1]

    def push(self, z, dt=1.):
        self.mean.push(z, dt)
        self.var.push(abs(z - self.mean.value) ** self.p, dt)
        self.value = (self.var.value ** (1 / self.p))
        return self.value


def ffill(arr, axis=0):
    """
    Forward fill NaN values in a NumPy array along specified axis.
    """
    result = arr.copy()
    if arr.size == 0 or np.all(np.isnan(arr)):
        return result
    if axis == 0:
        for i in range(1, arr.shape[0]):
            mask = np.isnan(result[i])
            result[i, mask] = result[i-1, mask]
    else:
        for i in range(1, arr.shape[1]):
            mask = np.isnan(result[:, i])
            result[mask, i] = result[mask, i-1]
    return result

def diff(arr, periods=1, axis=0):
    """
    Calculate the difference between elements along specified axis.

    Parameters:
    -----------
    arr : numpy.ndarray
        Input array
    periods : int, default 1
        Number of periods to shift
    axis : int, default 0
        Axis along which to calculate difference

    Returns:
    --------
    numpy.ndarray
        Array of differences with same shape as input
    """
    result = np.empty_like(arr)

    if axis == 0:
        # Set first 'periods' rows to NaN
        result[:periods] = np.nan
        # Calculate differences for remaining rows
        result[periods:] = arr[periods:] - arr[:-periods]
    else:
        # Set first 'periods' columns to NaN
        result[:, :periods] = np.nan
        # Calculate differences for remaining columns
        result[:, periods:] = arr[:, periods:] - arr[:, :-periods]

    return result
