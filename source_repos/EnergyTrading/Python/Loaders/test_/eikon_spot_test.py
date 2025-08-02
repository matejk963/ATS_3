# -*- coding: utf-8 -*-
"""
Created on Thu Aug  3 10:19:00 2023

@author: krajcovic
"""

import sys
sys.path.append('X:\\Loaders')

from EikonSpot_class import EikonSpot as ES
import pandas as pd

import refinitiv.data as rd

rd.open_session()
#
# test = rd.get_history(universe=['EHLDE01'],
#                       start='20230801',
#                       end='20230803')

spot = ES('dke', '20230801', '20230803')

test = spot.fwd_rel_code_creator(spot.grid, 'M_1', 'base')
