# -*- coding: utf-8 -*-
"""
Created on Thu Aug  3 11:27:39 2023

@author: krajcovic
"""

import sys
sys.path.append('X:\\Loaders')
sys.path.append('X:\\Database')

from DB_writer import db_writer
from sqlalchemy import create_engine
from data_scraper import scrapeHu as hupx
import psycopg2
import pandas as pd
from sqlalchemy import create_engine, types, exc

from sqlalchemy import create_engine, MetaData, Table, Column, DateTime, Float
import sqlalchemy

from dateutil.relativedelta import relativedelta

from EikonSpot_class import EikonSpot as ES

from time import sleep

# import refinitiv.data as rd
# rd.open_session()

database='trayportdata'
username ='trayport'
password='trayPwd321'
host='192.168.10.141'
port='5432'

db_w = db_writer(database, username,
              password, host, port)

for country in ['at', 'be', 'cz', 'de', 'dkw',
                'dke','fr','hu','nl','sk', 'si', 'ro', 'bg']:
    db_w.database_write(country, start='20230915',
                        end='20230919', history=True)
    # db_w.database_write(country)


# for country in ['bg']:
#     db_w.database_write(country)

# db_w.database_write('bg', start='20170101',
#                     end='20230811', history=True)
# db_w.database_write('si', start='20170101',
#                     end='20230811', history=True)
    
    
    