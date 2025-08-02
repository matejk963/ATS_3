from Strategies.Base.feature_interface import FeatureInterface
import matplotlib.pyplot as plt
from abc import ABC, abstractmethod, ABCMeta
import pandas as pd
import numpy as np


class StrategyBase():
    __metaclass__ = ABCMeta

    _position = 0
    market = ''
    instrument = ''
    state_vars = []
    contr_vars = []
    _actions = []
    _no_action = None
    stats_dict = dict()
    _is_overnight = False
    
    def __init__(self, features_pool, strategy_data_columns, param_dict, actions, no_action, is_overnight):
        self.param_dict = {}
        assert all([issubclass(x, FeatureInterface) for x in features_pool.values()])
        self.features = [features_pool[x](strategy_data_columns, *list(param_dict[x].get('params', {}).values()), 
                                        suffix=param_dict[x]['suffix'])
                        for x in features_pool.keys() if param_dict[x]['active']]
        self.columns = strategy_data_columns
        self.param_dict = param_dict
        self._actions = actions
        self._no_action = no_action
        self._is_overnight = is_overnight
        self.sim_iteration = 0

    @abstractmethod
    def process(self):
        pass

    @property
    def param_list(self):
        return list(self.param_dict.keys())