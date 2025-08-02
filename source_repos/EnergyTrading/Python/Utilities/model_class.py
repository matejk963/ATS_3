import abc
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from Math.accumfeatures import MSTD, MA, EMA
from Math.lm_class import kalman
import json

from scipy.integrate import odeint
from scipy.optimize import minimize


class ModelClass():
    __metaclass__ = abc.ABCMeta

    def __init__(self, model_name, weight, burn):
        self.name = model_name
        self.weight = weight
        self._burn = burn

    @abc.abstractmethod
    def fit(self, X):
        raise "not implemented"
        pass

    @abc.abstractmethod
    def predict(self, X):
        pass

    @abc.abstractmethod
    def score(self, X, y, sample_weight=None):
        raise "not implemented"
        pass


# Constants
BID_ = True
ASK_ = False


class Iceberg():
    def __init__(self, level, volume):
        self.level = level
        self.volume = volume
        self.active = True

    def __dict__(self):
        return {'level': self.level,
                'volume': self.volume,
                'active': self.active}

    @classmethod
    def empty(cls):
        o = cls.__new__(cls)
        o.level = np.nan
        o.volume = np.nan
        o.active = False
        return o