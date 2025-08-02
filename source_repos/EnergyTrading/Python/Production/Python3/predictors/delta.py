from Production.Python3.own_tools.math_features import DifferentialEMA, DerivativeEMA
import numpy as np




class FeatureDelta:
    def __init__(self, period, log_bool_diff=True, value0=None):
        """
        Initializes the FeatureTrdMomentum class with trade prices and parameters for momentum calculation.
        
        :param period: Period for momentum calculation.
        :param log_bool: If True, calculates log prices; otherwise, calculates simple prices.
        :param value0: Initial value for the momentum calculation.
        """
        self._period = period
        self._log_bool_diff = log_bool_diff
        self._value0 = value0
        self._diffEMA_class = DifferentialEMA(period, value0=np.log(value0) if log_bool_diff else value0)
        self._value = np.nan

    @property
    def period(self):
        return self._period
    @property
    def log_bool_diff(self):
        return self._log_bool_diff
    @property
    def value0(self):
        return self._value0
    @property
    def diffEMA_class(self):
        return self._diffEMA_class
    @property
    def value(self):
        return self._value
    
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

        return self.value


