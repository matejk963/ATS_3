import numpy as np
import numba


# class EMA:
#     def __init__(self, tau, value0=0):
#         self.tau = tau
#         self.value = value0
#         self.z = 0

#     def push(self, z, dt=1):

#         # reference implementation
#         # alpha = dt / self.tau
#         # mu = np.exp(-alpha)

#         # linear interpolation
#         # if mu == 1:
#         #     nu = 0
#         # else:
#         #     nu = (1-mu) / alpha
#         # next point interpolation
#         #  nu = mu

#         # self.value = mu * self.value + (nu-mu) * self.z + (1-nu) * z
#         # self.z = z

#         if np.isnan(z):
#             pass
#         else:
#             self.value = _numba_EMA_push_(z, self.z, self.value, dt, self.tau)
#             self.z = z
#         return self.value
    
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


@numba.jit(nopython=True)
def _numba_EMA_push_(z, z0, value, dt, tau):
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

    def push(self, z, dt=1):
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

    def push(self, z, dt=1):
        val = 0
        for i in range(3):
            self._ema[i].push(z, dt)
            val += self.__coeffs[i] * self._ema[i].value

        self.value = val
        return self.value


class DerivativeEMA:
    def __init__(self, tau, n=1, gamma=.5, value0=0):
        tau_ = tau / n
        self.tau = tau_
        self.value = np.nan

        self._diffema = [DifferentialEMA(tau_, value0) for i in range(n)]
        self._gamma = gamma

    def push(self, z, dt=1):
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
    def __init__(self, tau, n, p=2, value0=0, std0=0):
        self.tau = tau
        self.value = np.nan
        self.p = p
        self._ma = [MA(tau, n, value0), MA(tau, n, std0)]

    @property
    def mean(self):
        return self._ma[0]

    @property
    def var(self):
        return self._ma[1]

    def push(self, z, dt=1):
        self.mean.push(z, dt)
        self.var.push(abs(z - self.mean.value) ** self.p, dt)
        self.value = (self.var.value ** (1 / self.p))
        return self.value


def _test_ema():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=300)
    y = np.cumsum(x) + 50
    ema_log = []
    iterated_ema_log = []
    diffema_log = []
    ret_ema_log = []
    true_ret_log = []
    ma_log = []
    mid = EMA(1)
    mid2 = IteratedEMA(1, 3)
    dmid = DifferentialEMA(1)
    ret_window = 1
    ret_mid = DifferentialEMA(ret_window)
    ma_mid = MA(20, 5)
    burnin = 200
    n = 0

    y0 = 0
    for y_ in y:
        mid.push(y_)
        mid2.push(y_)
        dmid.push(y_)
        ma_mid.push(y_)
        ret_mid.push(np.log(y_))

        n += 1
        if n > burnin:
            diffema_log.append(dmid.value)
            ema_log.append(mid.value)
            iterated_ema_log.append(mid2.value)
            ma_log.append(ma_mid.value)
            ret_ema_log.append(ret_mid.value)
            true_ret_log.append(np.log(y_) - np.log(y0))
            y0 = y_

    y = y[burnin:]
    x = x[burnin:]

    plt.plot(y, label='data')
    plt.plot(ema_log, label='EMA')
    plt.plot(iterated_ema_log, label='iEMA')
    plt.plot(ma_log, label='MA')
    plt.legend()
    plt.show()

    plt.plot(diffema_log, label='diffEMA operator')
    plt.plot(x, alpha=.4, label='data')
    plt.legend()
    plt.show()

    plt.plot(ret_ema_log,
             label='diffEMA logreturn')
    plt.plot(true_ret_log, '--',
             label='true logreturn')
    plt.legend()
    plt.show()


def _test_ema2():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=500)
    y = np.cumsum(x) + 50
    ema_log = []
    iterated_ema_log = []
    diffema_log = []
    ret_ema_log = []
    true_ret_log = []
    ma_log = []

    tau = .001
    mid = EMA(tau)
    mid2 = IteratedEMA(tau, 3)
    dmid = DifferentialEMA(tau)
    ret_mid = DifferentialEMA(tau)
    ma_mid = MA(0.025, 5)
    burnin = 200
    n = 0

    y0 = y[0]
    dt = 0
    csr = 0
    csr_log = []
    for y_ in y:
        mid.push(y_, dt)
        mid2.push(y_, dt)
        dmid.push(y_, dt)
        ma_mid.push(y_, dt)
        ret_mid.push(np.log(y_), dt)

        r = np.log(y_) - np.log(y0)
        y0 = y_
        dt = r ** 2
        csr += dt
        csr_log.append(csr)

        n += 1
        if n > burnin:
            diffema_log.append(dmid.value)
            ema_log.append(mid.value)
            iterated_ema_log.append(mid2.value)
            ma_log.append(ma_mid.value)
            ret_ema_log.append(ret_mid.value)
            true_ret_log.append(r)

    y = y[burnin:]
    x = x[burnin:]

    plt.plot(y, label='data')
    plt.plot(ema_log, label='EMA')
    plt.plot(iterated_ema_log, label='iEMA')
    plt.plot(ma_log, label='MA')
    plt.legend()
    plt.show()

    plt.plot(diffema_log, label='diffEMA operator')
    plt.plot(x, alpha=.4, label='data')
    plt.legend()
    plt.show()

    plt.plot(ret_ema_log,
             label='diffEMA logreturn')
    plt.plot(true_ret_log, '--',
             label='true logreturn')
    plt.legend()
    plt.show()

    plt.plot(csr_log, label='csr')
    plt.legend()
    plt.show()


def _test_ema3():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=500)
    y = np.cumsum(x) + 50
    ret_ema_log = []
    momentum_log = []

    tau = 25
    ret_mid = DifferentialEMA(tau)
    momentum_mid = DifferentialEMA(tau)
    ema_mid = EMA(5)
    n, burnin = 0, 200
    true_ret_log = []

    for i in range(len(y)):
        y_ = y[i]
        x = np.log(y_)
        ret_mid.push(x)
        ema_mid.push(x)
        momentum_mid.push(x - ema_mid.value)

        n += 1
        if n > burnin:
            ret_ema_log.append(ret_mid.value)
            true_ret_log.append(np.log(y_) - np.log(y[i-tau]))
            momentum_log.append(momentum_mid.value)

    plt.plot(ret_ema_log,
             label='D[tau, x] logreturn')
    plt.plot(true_ret_log, '--',
             label='true logreturn')
    plt.plot(momentum_log, label='x-EMA[tau, x] momentum')
    plt.legend()
    plt.show()


def _test_ema4():
    # tsting ema convergence to constant signal if continually updated
    import matplotlib.pyplot as plt
    y = [1 for _ in range(400)]
    ema_log = []

    ema = EMA(15)
    n, burnin = 0, 0

    for i in range(len(y)):
        ema.push(y[i])

        n += 1
        if n > burnin:
            ema_log.append(ema.value)

    plt.plot(ema_log, label='EMA')
    plt.plot(y, label='signal')
    plt.legend()
    plt.show()


def _test_ema5():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=1000)
    y = np.cumsum(x) + 50
    ema_log, ma_time_log = [], []

    tau = .05
    mid_ema = EMA(.001)
    n_ema = [2, 3, 4, 5]
    mids = [MA(tau, k) for k in n_ema]
    logs = [[] for _ in mids]
    mid_time = MA(150, 3)
    burnin = 200
    n = 0

    y0 = y[0]
    csr = 0
    csr_log = []
    for y_ in y:
        r = np.log(y_) - np.log(y0)
        y0 = y_
        dt = r ** 2

        [mid.push(y_, dt) for mid in mids]
        mid_time.push(y_)
        mid_ema.push(y_, dt)

        n += 1
        if n > burnin:
            ema_log.append(mid_ema.value)
            [log.append(mid.value) for mid, log in zip(mids, logs)]
            ma_time_log.append(mid_time.value)
            csr += dt
            csr_log.append(csr)

    y = y[burnin:]

    plt.figure()
    plt.plot(y, label='data')
    plt.plot(ema_log, '--', label='EMA .001')
    plt.plot(ma_time_log, label='MA time')
    for log, k in zip(logs, n_ema):
        plt.plot(log, label='MA '+str(k), alpha=.5)
    plt.legend()
    plt.show()

    plt.plot(csr_log, label='csr')
    plt.legend()
    plt.show()


def _test_ema6():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=300)
    y = np.cumsum(x) + 50
    ema_log, ma_log, ma_time_log = [], [], []

    tau = 20
    mid_ema = EMA(1, value0=y[0])
    mid = MA(tau, 3, value0=y[0])
    mid_time = MA(tau, 3, value0=y[0])
    burnin = 200
    n = 0

    csr = 0
    csr_log = []
    for y_ in y:
        # volume
        dt = np.random.choice([1, 5, 10])
        mid.push(y_, dt)
        mid_ema.push(y_, dt)
        mid_time.push(y_)

        n += 1
        if n > burnin:
            ema_log.append(mid_ema.value)
            ma_log.append(mid.value)
            ma_time_log.append(mid_time.value)
            csr += dt
            csr_log.append(csr)

    y = y[burnin:]

    fig, ax = plt.subplots(1, 2)
    ax[0].plot(y, label='data')
    ax[0].plot(ema_log, label='EMA 1', alpha=.5)
    ax[0].plot(ma_log, label='MA '+str(tau), alpha=.5)
    ax[0].plot(ma_time_log, label='MA time', alpha=.5)
    ax[0].legend()

    ax[1].plot(csr_log, label='csr')
    ax[1].legend()

    plt.show()


def _test_ema7(window=30):
    import matplotlib.pyplot as plt
    x = 5*np.random.normal(size=500)
    y = np.cumsum(x) + 50
    movavg, movavg3_exp,  movavg5_exp, movavg_exp_var, ema_log = [], [], [], [], []
    movavg5_var = []
    normalization_log = []
    data = []
    buffer = []
    ema = EMA(window, value0=y[0])
    ma3 = MA(window, 3, value0=y[0])
    ma5 = MA(window, 6, value0=y[0])
    normalization = MA(50, 3, value0=1e-3)
    ret = y[1:] / y[:-1] - 1
    q1 = np.quantile(ret, .02)
    q2 = np.quantile(ret, 1-.02)
    ret = ret[ret > q1]
    ret = ret[ret < q2]
    rsq = np.mean(ret**2)
    lookback = 40
    ma_var = MA(lookback, 6, value0=y[0])
    print(rsq)
    dts = [0]
    y_prev = y[0]
    for y_ in y[1:]:

        dt = y_ / y_prev - 1
        normalization.push(dt ** 2)
        tau = dt ** 2 / normalization.value

        if tau > lookback:
            tau = lookback
        if tau > 0.1:
            y_prev = y_
            ma_var.push(y_, tau)
        else:
            tau = 0

        ema.push(y_)
        ma3.push(y_)
        ma5.push(y_)

        buffer.append(y_)
        if len(buffer) == window:
            data.append(y_)
            movavg.append(np.mean(buffer))
            movavg3_exp.append(ma3.value)
            movavg5_exp.append(ma5.value)
            movavg5_var.append(ma_var.value)
            ema_log.append(ema.value)
            normalization_log.append(normalization.value)
            buffer.pop(0)
            dts.append(tau)

    fig, ax1 = plt.subplots()
    color = 'tab:red'
    ax1.plot(data, '.-', color=color, label='y', linewidth=.1, markersize=1)
    ax1.plot(movavg, label='MA', alpha=.4)
    ax1.plot(movavg3_exp, label='MA exp3', alpha=.4)
    ax1.plot(movavg5_exp, label='MA exp5', alpha=.4)
    ax1.plot(movavg5_var, '-', label='MA var', alpha=.4)
    ax1.plot(ema_log, label='EMA', alpha=.4)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.legend()

    ax2 = ax1.twinx()
    color = 'tab:blue'
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.plot(dts, '-', color=color, linewidth=.5,
             alpha=.2)
    ax2.set_ylabel('update weight', color=color)
    fig.tight_layout()
    plt.show()


def _test_ema8():
    window = 500
    u = np.random.uniform(size=10000)
    u[u < .5] = -1
    u[u >= .5] = 1
    ma = MA(window, 6, 0)
    ma_log, true_ma = [], []
    buffer = []
    data = []

    for ut in u:
        buffer.append(ut)
        ma.push(ut, dt=1)

        if len(buffer) == window:
            data.append(ut)
            movavg = np.mean(buffer)
            buffer.pop(0)

            ma_log.append(ma.value)
            true_ma.append(movavg)

    n = 9000
    import matplotlib.pyplot as plt
    plt.plot(data[n:], 'x', label='data')
    plt.plot(ma_log[n:], alpha=.5, label='MA')
    plt.plot(true_ma[n:], alpha=.5,  label='true MA')
    plt.legend()
    plt.show()


def _test_mstd():
    import matplotlib.pyplot as plt
    x = np.random.normal(size=300)
    y = np.cumsum(x) + 50
    true_std_log = []
    emas_std_log = []
    true_ret_log = []
    aux_ret_log = []
    emas_ma_log = []
    emastd_ma_log = []
    true_ma_log = []
    std_window = 30
    N = 35
    std_mid = MSTD(std_window / 2, N, p=2)
    ma_mid = MA(std_window / 2, N)
    burnin = 200
    n = 0

    y0 = y[0]
    for y_ in y[1:]:
        std_mid.push(np.log(y_) - np.log(y0))
        ma_mid.push(np.log(y_) - np.log(y0))
        
        aux_ret_log.append(np.log(y_) - np.log(y0))
        if len(aux_ret_log) > std_window:
            aux_ret_log = aux_ret_log[-std_window:]

        n += 1
        if n > burnin:
            emas_std_log.append(std_mid.value)
            emas_ma_log.append(ma_mid.value)
            emastd_ma_log.append(std_mid.mean.value)
            true_std_log.append(np.std(np.asarray(aux_ret_log)))
            true_ma_log.append(np.mean(np.asarray(aux_ret_log)))
            true_ret_log.append(np.log(y_) - np.log(y0))
        y0 = y_

    y = y[burnin:]
    x = x[burnin:]

    plt.figure()
    plt.plot(emas_std_log, label='EMA STD')
    plt.plot(true_std_log, label='True STD')
    plt.legend()
    plt.show()
    
    plt.figure()
    plt.plot(emas_ma_log, label='EMA MA')
    plt.plot(emastd_ma_log, label='EMA STD MA')
    plt.plot(true_ma_log, label='True MA')
    plt.legend()
    plt.show()


def _test_dtema():
    import matplotlib.pyplot as plt
    x = np.arange(-.5, .5, .001)
    y = 1 * x ** 4
    emas_dt1_log = []
    emas_dt2_log = []
    
    tau = 30
    dt1_ema = DerivativeEMA(tau, n=1, gamma=1)
    dt2_ema = DerivativeEMA(tau, n=2, gamma=1)
    burnin = 60
    n = 0
    
    for y_ in y:
        dt1_ema.push(y_)
        dt2_ema.push(y_)
        
        n += 1
        if n > burnin:
            emas_dt1_log.append(dt1_ema.value * 1000)
            emas_dt2_log.append(dt2_ema.value * (1000 ** 2))

    # Create a plot with a secondary y-axis
    fig, ax1 = plt.subplots()
    
    # Plot the first series
    color = 'tab:red'
    ax1.set_xlabel('X-axis label')
    ax1.set_ylabel('EMA DT1', color=color)
    ax1.plot(emas_dt1_log, color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    
    # Create a second y-axis for the second series
    ax2 = ax1.twinx()
    color = 'tab:blue'
    ax2.set_ylabel('EMA DT2', color=color)
    ax2.plot(emas_dt2_log, color=color)
    ax2.tick_params(axis='y', labelcolor=color)
    
    # Show the plot
    plt.show()
    return 0


if __name__ == '__main__':
    _test_dtema()
