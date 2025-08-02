# -*- coding: utf-8 -*-
"""
Created on Thu Aug  3 10:59:40 2023

@author: krajcovic
"""

import sys
sys.path.append('X:\\Loaders')

from EikonSpot_class import EikonSpot as ES

spot = ES('de', '20230801', '20230803')

test = spot.spot_data()
