from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
import pandas as pd
import numpy as np
from Utilities.excel_loaders import conn_out_xload_mac
from Utilities.dfutils import dict_iloc
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments
import pickle
from sqlalchemy import create_engine

_START_DATE, _END_DATE = '2025-01-01', '2025-01-03'

start_date = datetime.strptime(_START_DATE, '%Y-%m-%d').date()
end_date = datetime.strptime(_END_DATE, '%Y-%m-%d').date()

venue_list = ['eex']

data_class = TPData() 
data_class.create_connection('OracleSQL')
inst_trades = data_class.get_trades_inst('de', venue_list, start_date, end_date, prod='base', spread_bool=False)
de_ts = inst_trades[inst_trades.eval('broker_id==1441')].index.drop_duplicates()
inst_trades = data_class.get_trades_inst('fr', venue_list, start_date, end_date, prod='base', spread_bool=False)
fr_ts = inst_trades[inst_trades.eval('broker_id==1441')].index.drop_duplicates()

engine = create_engine('questdb://admin:ETCAlgo123!@192.168.10.91:5006/main')



