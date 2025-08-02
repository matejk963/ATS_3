# -*- coding: utf-8 -*-
"""
Created on Tue Jan 16 15:32:32 2024

@author: krajcovic
"""

import pandas as pd
from sqlalchemy import types
import numpy as np
from datetime import datetime, timedelta
from Loaders.EikonSpot_class import EikonSpot as EF
from Database.DB_reader import Database


countries = ['dke', 'fr', 'nl', 'be', 'at', 'dkw', 'de']

sD = datetime(2024,1,11)
eD = datetime(2024,1,15)
data_dict = {}
for m in countries:
    
    eikon_spot = EF(m, sD.strftime('%Y%m%d'), eD.strftime('%Y%m%d'))
    df_aux = eikon_spot.prices_df()
    data_dict[m] = df_aux
    # df_spot = pd.concat([df_spot, df_aux], axis=1)
    
db = Database()
dtypes = {
        'datetime': types.TIMESTAMP,
        'b_volume': types.FLOAT,
        's_volume': types.FLOAT,
        'volume': types.FLOAT,
        'price': types.FLOAT
    }
from_date = datetime(2024,1,11)
to_date = datetime(2024,1,15)-timedelta(hours=1)
db_data = {}
for m in countries:
    aux = data_dict[m]
    aux = aux[from_date:to_date]
    aux['price'] = aux[m].copy()
    aux[['b_volume', 's_volume', 'volume']] = 0
    
    aux = aux[['b_volume', 's_volume', 'volume', 'price']].copy()
    aux = aux.reset_index()
    name = 'stage_' + m
    aux.to_sql(name=name, schema='spot', con=db.connection_string, if_exists='replace', dtype=dtypes)