# -*- coding: utf-8 -*-
"""
Created on Mon Jul  3 14:19:21 2023

@author: Marek
"""

import oracledb
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys


#establishing the connection
dsn = "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=192.168.10.141)(PORT=1521))(CONNECT_DATA=(SERVER = DEDICATED)(SERVICE_NAME=DBSELT)))"


connection = oracledb.connect(
    user="rove_trayport",
    password="rove_trayport",
    dsn=dsn)  # the connection string copied from the cloud console

print("Successfully connected to Oracle Database")

cursor = connection.cursor()
cursor.execute("SELECT * FROM rove_od.TRAYPORT_VW_TRADES")
x = cursor.fetchone()

connection.close()
