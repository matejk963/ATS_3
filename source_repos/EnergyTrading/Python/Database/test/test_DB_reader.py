# -*- coding: utf-8 -*-
"""
Created on Tue Aug 15 08:06:25 2023

@author: krajcovic
"""

import sys
sys.path.append('X:\\Database')
sys.path.append('X:\\Loaders')
sys.path.append('X:\\BorderSpread')

from DB_reader import Database
from loader import spot_loader
from delivery_class import Delivery
from portfolio_sim import capaStratSim
import pandas as pd

db_reader = Database()

df = db_reader.getSpotPriceData(['bg'], _from='2023-08-01',
                                _to='2023-08-15')

# test = capaStratSim()

# fwd_ration = test.fwd_ratio('de', pd.to_datetime('20230815'))