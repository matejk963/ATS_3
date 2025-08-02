# -*- coding: utf-8 -*-
"""
Created on Tue Aug 15 14:33:45 2023

@author: krajcovic
"""

import sys
sys.path.append('X:\\Loaders')

from data_scraper import scrapeOte
import pandas as pd

from EikonSpot_class import EikonSpot as ES

spot = ES('gr', '20230816', '20230819')

test = spot.prices_df()

