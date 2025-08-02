# -*- coding: utf-8 -*-
"""
Created on Tue Jul 18 11:06:16 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
import os
import requests
from dateutil.relativedelta import relativedelta
import sys

sys.path.append('X:\\Loaders')
sys.path.append('X:\\BorderSpread')
from EikonSpot_class import EikonSpot
from border_class import DataBorderClass
import capacity_class as capa
import CapaBacktestParams_class as CapaParams

import time

time.time()
capa_params = CapaParams.CapaParams(['de_be', 'be_de',
                                  'be_nl', 'nl_be',
                                  'de_fr', 'fr_de',
                                  'fr_be', 'be_fr',
                                  'at_hu', 'hu_at',
                                  'at_si', 'si_at',
                                  'it_fr', 'fr_it'],
                                 '20230101', '20230717')


df = capa_params.ParamsData()


