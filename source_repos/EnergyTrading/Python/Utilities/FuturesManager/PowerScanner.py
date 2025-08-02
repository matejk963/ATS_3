# -*- coding: utf-8 -*-
"""
Created on Wed Jan 15 13:34:17 2025

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import copy
from datetime import datetime, timedelta
import datetime as dt

from Utilities.date_functions import start_date, end_date

from Utilities.FuturesManager.FuturesDataProcessor import FuturesDataProcessor
from Utilities.FuturesManager.FuturesDataCollector import FuturesDataCollector

from itertools import combinations
from scipy.stats import norm

class PowerScanner:
    
    def __init__(self, params_dict, pivot_date=None):
        self._params_dict = params_dict
        self._original_params_dict = params_dict
        self._pivot_date = pivot_date