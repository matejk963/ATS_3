# -*- coding: utf-8 -*-
"""
Created on Wed Apr 24 09:51:43 2024

@author: Marek
"""

import pandas as pd
from datetime import datetime
import platform
# import xlrd
import os
import csv


def price_xload(market, path_def=None, file=None):
    # Loads prices of products from excel file
    if path_def is None:
        path_def = r'Z:/Data/Pricing/curvePrices/'
    path = path_def + market + '/'
    path_show = path
    try:
        if file is None:
            f_list = [x for x in os.listdir(path)
                      if x.endswith('_mid.xlsx') and not x.startswith('~$')]
            f_list.sort(reverse=True, key=lambda x: os.path.getmtime(path + x))
            file = f_list[0]

        path_show = path + file
        df_data = pd.read_excel(path + file, index_col=0)
        return df_data.to_dict()[market]
    except(FileNotFoundError):
        print('load_price_x: File or directory does not exist.')
        print(path_show)
        return -1

def price_create_table(market, prod_list, path_def=None, file=None):
    # Create template for prices
    if path_def is None:
        path_def = r'Z:/Data/Pricing/curvePrices/'
    path = path_def + market + '/'
    os.makedirs(path, exist_ok=True)
    if file is None:
        date = datetime.today()
        file = market + '_' + date.strftime('%y%m%d') + '_mid.xlsx'
    df_data = pd.DataFrame([], index=prod_list, columns=[market])
    try:
        print('Saving product template to file: ')
        print(path + file)
        df_data.to_excel(path + file, index_label='Products')
        print('File SAVED. ')
        return 0
    except(IOError):
        print('Permission DENIED. ')
        return -1


def price_xload_all(market, path_def=None, file=None):
    # Loads prices of products from excel file
    if path_def is None:
        path_def = '//cezdata.corp/Sdp/CEZ/Obchod/Trading/ATI/Pricing/curvePrices/'
    path = path_def + market + '/'
    path_show = path
    try:
        if file is None:
            f_list = [x for x in os.listdir(path)
                      if x.endswith('bidask_feed.csv') and not x.startswith('~$')]
            f_list.sort(reverse=True, key=lambda x: os.path.getmtime(path + x))
            file = f_list[0]
 
        path_show = path + file
        df_data = pd.read_csv(path + file, delimiter=';', index_col=0, dtype=str)
        # Convert numeric columns by replacing ',' with '.' and then converting to float
        for col in df_data.columns:
            df_data[col] = df_data[col].str.replace(',', '.', regex=True).astype(float)
        return df_data.to_dict()['bid'], df_data.to_dict()['ask']
    except(ValueError):
        df_data = pd.read_csv(path + file, index_col=0, delimiter=',')
        return df_data.to_dict()['bid'], df_data.to_dict()['ask']
    except(FileNotFoundError):
        print('load_price_x: File or directory does not exist.')
        print(path_show)
        return -1


def price_create_table_all(market, prod_list, path_def=None, file=None):
    # Create template for prices
    if path_def is None:
        path_def = r'Z:/Data/Pricing/curvePrices/'
    path = path_def + market + '/'
    os.makedirs(path, exist_ok=True)
    if file is None:
        date = datetime.today()
        file = market + '_' + date.strftime('%y%m%d') + '_bid_ask.xlsx'
    df_data = pd.DataFrame([], index=prod_list, columns=['bid', 'ask'])
    try:
        print('Saving product template to file: ')
        print(path + file)
        df_data.to_excel(path + file, index_label='Products')
        print('File SAVED. ')
        return 0
    except(IOError):
        print('Permission DENIED. ')
        return -1


def conn_out_xload(path_def=None, file=None):
    # Loads dates with connection issues in KS
    if path_def is None:
        if 'arm' in platform.machine().lower():
            path_def = '/Volumes/data/Data/orderbooks/'
        else:
            path_def = '//192.168.10.91/data/Data/orderbooks/'
    path = path_def
    try:
        if file is None:
            f_list = [x for x in os.listdir(path)
                      if x.endswith('_out.csv') and not x.startswith('~$')]
            f_list.sort(reverse=True, key=lambda x: os.path.getmtime(path + x))
            file = f_list[0]

        file_path = path + file
        with open(file_path, newline='') as f:
            reader = csv.reader(f)
            data = [tuple(row) for row in reader]
        return [datetime(int(x[0]), int(x[1]), int(x[2])) for x in data[1:]]
    except(FileNotFoundError):
        print('conn_out_xload: File or directory does not exist.')
        print(path)
        return -1
    
def conn_out_xload_mac(path_def=None, file=None):
    from Utilities.Storage import get_curr_storage_path
    STORAGE_ = get_curr_storage_path()
    # Loads dates with connection issues in KS
    if path_def is None:
        path_def = STORAGE_ + 'Data/orderbooks/'
    path = path_def
    try:
        if file is None:
            f_list = [x for x in os.listdir(path)
                      if x.endswith('_out.csv') and not x.startswith('~$')]
            f_list.sort(reverse=True, key=lambda x: os.path.getmtime(path + x))
            file = f_list[0]

        file_path = path + file
        with open(file_path, newline='') as f:
            reader = csv.reader(f)
            data = [tuple(row) for row in reader]
        return [datetime(int(x[0]), int(x[1]), int(x[2])) for x in data[1:]]
    except(FileNotFoundError):
        print('conn_out_xload: File or directory does not exist.')
        print(path)
        return -1