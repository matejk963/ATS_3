import abc
import logging
import time
from .own_tools.math_features import EMA, MA, MSTD

log = logging.getLogger("market_making.model_statistics")


class ModelStats(object):
    strategy_id = None
    model_type = None
    model_params = []
    model_dict = {}
    last_value = None
    timestamp = None

    def __init__(self, model_type=None, model_params=None, strategy_id=''):
        if model_params is None:
            model_params = []
        self.strategy_id = strategy_id
        self.update_models(model_type, model_params)

    @property
    def attributes_list(self):
        return ['model_type', 'spread_value', 'timestamp']

    @property
    def spread_value(self):
        return self.model_dict['spread'].value

    @property
    def spread_std(self):
        if self.is_std_model:
            return self.model_dict['spread'].std
        else:
            return None

    @property
    def is_std_model(self):
        if self.model_type in ['MSTD_x', 'MSTD_t']:
            return True
        else:
            return False

    @property
    def is_fix_model(self):
        if self.model_type in ['FIX']:
            return True
        else:
            return False

    @property
    def count(self):
        return self.model_dict['spread'].count

    def update_models(self, model_type, model_params):
        self.model_type = model_type
        self.model_params = model_params
        if model_type is None:
            pass
        elif model_type == 'EMA':
            self.model_dict['spread'] = EmaModel(
                model_params[0], 0, model_params[1], False)
        elif self.model_type == 'MSTD_x':
            self.model_dict['spread'] = MstdModel(model_params[0], 30, 2., 0, model_params[2], model_params[1], 10,
                                                  False, False)
        elif self.model_type == 'MSTD_t':
            self.model_dict['spread'] = MstdModel(model_params[0], 30, 2., 0, model_params[2], model_params[1], 10,
                                                  True, False)
        elif model_type == 'MID':
            self.model_dict['spread'] = MidModel(0, model_params[1])
        else:
            raise ValueError(
                "Unknown model type in ModelStats: %s." % model_type)
        self.timestamp = time.time()

    def reset(self):
        if self.model_type is None:
            pass
        elif self.model_type == 'EMA':
            tau = self.model_params[0]
            tol = self.model_params[1]
            self.model_dict['spread'] = EmaModel(tau, 0, tol, False)
        elif self.model_type == 'MSTD_x':
            tau = self.model_params[0]
            tol = self.model_params[1]
            std0 = self.model_params[2]
            burn = self.model_dict['spread'].burn
            self.model_dict['spread'] = MstdModel(
                tau, 30, 2., 0, std0, tol, burn, False, False)
        elif self.model_type == 'MSTD_t':
            tau = self.model_params[0]
            tol = self.model_params[1]
            std0 = self.model_params[2]
            burn = self.model_dict['spread'].burn
            self.model_dict['spread'] = MstdModel(
                tau, 30, 2., 0, std0, tol, burn, True, False)
        elif self.model_type == 'MID':
            tol = self.model_params[1]
            self.model_dict['spread'] = MidModel(0, tol)
        else:
            raise ValueError(
                "Unknown model type in ModelStats: %s." % self.model_type)
        self.timestamp = time.time()

    def update_strategy_prices(self, bid_price, ask_price, mid_price):
        # Calculate spread
        self.model_dict['spread'].push(mid_price)
        log.debug(
            "[{}] Model price update spread BID // ASK -- MID // MODEL: {} // {} -- {}".format(
                self.strategy_id, bid_price, ask_price, mid_price, self.model_dict['spread'].value)
        )
        log.debug(
            "[{}] Model statistics: {}".format(
                self.strategy_id, self.model_dict['spread'].to_string())
        )
        self.timestamp = time.time()
        self.last_value = mid_price
        return self.model_dict['spread'].value

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}


class ModelClass(object, metaclass=abc.ABCMeta):
    __is_nan = False
    __tol = .025
    count = 0

    def __init__(self, tol):
        self._tol = tol

    @property
    def tol(self):
        return self.__tol

    @abc.abstractmethod
    def push(self, z):
        pass


class EmaModel(ModelClass):
    model = None
    __is_init = False

    def __init__(self, tau, value0=0, tol=.025, is_init=False):
        super(EmaModel, self).__init__(tol)
        self.model = EMA(tau, value0)
        self.__is_init = is_init

    def initialize(self, value0):
        self.model.value = value0
        self.model.z = value0
        self.__is_init = True

    @property
    def attributes_list(self):
        return ['value', 'z', 'count']

    @property
    def is_init(self):
        return self.__is_init

    @property
    def z(self):
        return self.model.z

    @property
    def value(self):
        if self.__is_nan:
            return None
        else:
            return self.model.value

    def push(self, z):
        if z is None:
            self.__is_nan = True
        else:
            self.__is_nan = False
            dt = abs(z - self.model.z)
            if dt >= self.tol:
                if self.is_init:
                    self.model.push(z, dt)
                    self.count += 1
                else:
                    self.initialize(z)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}

    def to_string(self):
        return "EMA value: %s, last z: %s, counter %s" % (self.value, self.model.z, self.count)


class MstdModel(ModelClass):
    model = None
    __is_init = False

    def __init__(self, tau, N, p=2., value0=0, std0=0, tol=.025, burn=10, time_model=False, is_init=False):
        super(MstdModel, self).__init__(tol)
        self.model = MSTD(tau / 2, N, p, value0, std0 ** 2)
        if time_model:
            self.dt = self.dt_1
        else:
            self.dt = self.dt_x
        self.z = 0
        self.std0 = std0
        self.__burn = burn
        self.__is_init = is_init

    def initialize(self, value0):
        param_list = [self.model.tau, self.model._ma[0].n,
                      self.model.p, value0, self.std0 ** 2]
        self.model = self.model.__class__(*param_list)
        self.__is_init = True

    @property
    def burn(self):
        return self.__burn

    @property
    def attributes_list(self):
        return ['value', 'std', 'z', 'count']

    @property
    def is_init(self):
        return self.__is_init

    @property
    def value(self):
        if self.count < self.burn:
            return None
        if self.__is_nan:
            return None
        else:
            return self.model.mean.value

    @property
    def std(self):
        if self.count < self.burn:
            return None
        if self.__is_nan:
            return None
        else:
            return self.model.value

    @staticmethod
    def dt_1(dx):
        return 1

    @staticmethod
    def dt_x(dx):
        return abs(dx)

    def push(self, z):
        if z is None:
            self.__is_nan = True
        else:
            self.__is_nan = False
            if self.is_init:
                dt = self.dt(z - self.z)
                tol = self.tol
            else:
                self.initialize(z)
                dt = 1e-4
                tol = 0
            if dt >= tol:
                self.model.push(z, dt)
                self.z = z
                self.count += 1

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}

    def to_string(self):
        return "MSTD value: %s, std: %s, last z: %s, counter %s" % (self.value, self.std, self.z, self.count)


class MidModel(ModelClass):
    __is_nan = False

    def __init__(self, value, tol):
        super(MidModel, self).__init__(tol)
        self.__value = value

    @property
    def attributes_list(self):
        return ['value', 'count']

    def push(self, z):
        if z is None:
            self.__is_nan = True
        else:
            self.__value = z
            if abs(self.__value - z) >= self.tol:
                self.count += 1

    @property
    def value(self):
        if self.__is_nan:
            return None
        else:
            return self.__value

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}

    def to_string(self):
        return "MID value: %s, last z: %s, counter %s" % (self.value, self.value, self.count)
