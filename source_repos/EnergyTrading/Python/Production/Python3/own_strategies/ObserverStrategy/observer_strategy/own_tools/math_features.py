import numpy as np
import math

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

class FeatureTrdMomentum:
    def __init__(self, period, log_bool_diff=True, log_bool_der=True, value0=1):
        """
        Initializes the FeatureTrdMomentum class with trade prices and parameters for momentum calculation.
        
        :param period: Period for momentum calculation.
        :param log_bool: If True, calculates log prices; otherwise, calculates simple prices.
        :param value0: Initial value for the momentum calculation.
        """
        self._period = period
        self._log_bool_diff = log_bool_diff
        self._log_bool_der = log_bool_der
        self._value0 = value0
        self._diffEMA_class = DifferentialEMA(period, value0=np.log(value0) if log_bool_diff else value0)
        self._derEMA_class = DerivativeEMA(period, 2, .5, value0=np.log(value0) if log_bool_der else value0)
        self._value = np.nan
        self._value_acc = np.nan

    @property
    def period(self):
        return self._period
    @property
    def log_bool_diff(self):
        return self._log_bool_diff
    @property
    def log_bool_der(self):
        return self._log_bool_der
    @property
    def value0(self):
        return self._value0
    @property
    def diffEMA_class(self):
        return self._diffEMA_class
    @property
    def derEMA_class(self):
        return self._derEMA_class
    @property
    def value(self):
        return self._value
    @property
    def value_acc(self):
        return self._value_acc
    
    def push(self, trade_price):
        """
        Pushes a new trade price to the momentum calculation.
        
        :param trade_price: New trade price to be processed.
        :return: Tuple containing the momentum and its acceleration.
        """

        if self.log_bool_diff:
            self._value = self.diffEMA_class.push(np.log(trade_price))
        else:
            self._value = self.diffEMA_class.push(trade_price)

        if self.log_bool_der:
            self._value_acc = self.derEMA_class.push(np.log(trade_price))
        else:
            self._value_acc = self.derEMA_class.push(trade_price)

        return self.value, self.value_acc

def calculate_dti_time(trades, interval='300s'):
    # --- Parse interval ---
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == 's':
        interval_seconds = value
    elif unit == 'm':
        interval_seconds = value * 60
    elif unit == 'h':
        interval_seconds = value * 3600
    else:
        raise ValueError("Unsupported interval format. Use 's', 'm', or 'h' suffix.")

    if not trades:
        return None

        # --- Filter trades within the time window ---
    now = max([t.execution_time for t in trades])  # datetime.utcnow().timestamp()
    start_time = now - interval_seconds
    recent_trades = [
        (t.price, t.quantity, t.execution_time)
        for t in trades
        if start_time < t.execution_time <= now
    ]
    if not recent_trades:
        return None

    # --- Aggregate trades with same timestamp using VWAP ---
    trade_dict = {}  # timestamp -> (sum_price_qty, sum_qty)
    for price, qty, ts in recent_trades:
        if ts not in trade_dict:
            trade_dict[ts] = [price * qty, qty]
        else:
            trade_dict[ts][0] += price * qty
            trade_dict[ts][1] += qty

    # Convert to list of (timestamp, vwap_price)
    aggregated = [(ts, total / qty) for ts, (total, qty) in trade_dict.items()]
    aggregated.sort()  # sort by timestamp

    if len(aggregated) < 2:
        return None

    # --- Calculate DTI ---
    open_price = aggregated[0][1]
    close_price = aggregated[-1][1]
    direction = math.copysign(1, close_price - open_price) if close_price != open_price else 0

    # Count number of price changes
    unique_prices = 0
    last_price = None
    for _, price in aggregated:
        if price != last_price:
            unique_prices += 1
            last_price = price

    dti = direction * unique_prices / interval_seconds
    return dti

def trd_gap_calc(row):
    if not row.get('trd_side', None):
        row['trd_side'] = 1 if row['trd_price'] > row['mid_price'] else -1

    if bool((row['trd_price'] > (row['a_price'])) or (row['trd_price'] < (row['b_price']))):
        if row['trd_side'] > 0.5:
            return round(row['trd_price'] - row['a_price'], 2)
        else:
            return round(row['trd_price'] - row['b_price'], 2)
    else:
        return 0.0