"""
Creation and generation of scenarios of fundamental data and fuels

Fundamental data scenarios are based on historical values relative
    to their normalized values
"""

import pandas as pd
import numpy as np
import datetime as dt


class Scenarios:
    
    def __init__(self, base_data):
        self._base_data = base_data
        
    @property
    def base_data(self):
        return self._base_data
    
    @property
    def da_data(self):
        return self.base_data['da']
    
    @property
    def curve_data(self):
        return self.base_data['curve']
    
    def get_normal_data(self):
        pass