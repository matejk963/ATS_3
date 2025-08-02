# -*- coding: utf-8 -*-
"""
Created on Mon Feb 24 15:10:08 2025

@author: scasny
"""

from datetime import datetime, time, timedelta
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
import pandas as pd
from Utilities.excel_loaders import conn_out_xload_mac
from Utilities.dfutils import dict_iloc
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments
import pickle
import copy

dates_out = conn_out_xload_mac()
print("Dates out", dates_out)
STORAGE_ = get_curr_storage_path()
l_path = STORAGE_ + 'Data/orderbooks/base/'

def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)

def prepare_data_combined(LoB_dict, tr_dict, depth_list, inst_ts, curr_date):
    print("Prepare data combined entry")
    data_class_tr = TPDataDa()
    timestamp = inst_ts[inst_ts.date == curr_date.date()].drop_duplicates()

    ob_dict = obAtt.prepare_ob_data_basic(LoB_dict, depth_list)
    tr_df = data_class_tr.clean_trades(tr_dict, pd.DataFrame(ob_dict), is_verbose=True)
    
    # ffill OB data onto timestamp
    ob_df = pd.DataFrame(ob_dict).set_index('timestamp')
    ob_df = ob_df.reindex(ob_df.index.union(timestamp)).ffill().reindex(timestamp)

    return pd.concat([ob_df, tr_df], axis=1)

def variables_from_instrument(instrument: str):
    result = {
        'mkt': None,
        'tenor': None,
        'tn': None
    }
    for x in ['de', 'fr', 'ttf']:
        if x in instrument:
            result['mkt'] = x
    result['tenor'] = instrument[-2]
    result['tn'] = int(instrument[-1])
    return result


if __name__ == '__main__':
    _STORAGE = get_curr_storage_path()
    # ------------------ dataset prep ---------------------------------
    args_config = {
        '--instrument': {'type': str, 'default': 'ttfm1'},
        '--start_date': {'type': str, 'default': '2025-04-21'},
        '--end_date': {'type': str, 'default': '2025-04-23'},
        '--directory_path': {'type': str, 'default': 'data_factory/'}
    }

    # Load arguments
    _INSTRUMENT, _START_DATE, _END_DATE, _DIR_PATH = load_arguments(args_config)
    ins_dict = variables_from_instrument(_INSTRUMENT)
    n_s = 2
    mkt_list = [ins_dict['mkt']]
    tenor_list = [ins_dict['tenor']]
    tn1_list = [ins_dict['tn']]
    ts_lag = (lambda i: mkt_list[i] + tenor_list[i] + str(tn1_list[i]))(0)
    
    tn2_list = []
    prod = 'base'
    venue_list = ['eex']
    start_date = datetime.strptime(_START_DATE, '%Y-%m-%d').date()
    end_date = datetime.strptime(_END_DATE, '%Y-%m-%d').date()
    
    if not tn2_list:
        tn_list = [str(t1) for t1 in tn1_list]
    else:
        tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]
    
    dates = pd.date_range(start_date, end_date, freq='B')
    
    spread_class = SpreadSingle(mkt_list, tenor_list, tn1_list, tn2_list, venue_list)
    product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
    product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)
    
    start_time = time(9, 0, 0, 0)
    end_time = time(17, 0, 0, 0)
    
    gran = None
    
    is_db = True
    is_tr = True
    
    if is_db:
        data_class = TPData() 
    else:
        data_class = TPDataDa()
    
    # features_list = ['ba_volrat', 'mid_priceW', 'bid_sparsity', 'ask_sparsity']
    # features_list = [*OB_attributes.attr_list(),
    #                  *OB_attributes.attr_list(types='cross')]
    
    depth_list = [0.0, .3, 0.5, 0.9]
    period_list = [5, 20]
    tick = 0.01
    tick_val = 200
    cls_margin = 0.15
    obAtt = OB_attributes(OB_attributes.attr_list())
    trAtt = TR_attributes(['lvl_dist', 'trd_price', 'trd_gap', 'trd_side', 'last_trade_margin'])
    name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]
    
    
    class_ser = pd.Series([])
    df_data = pd.DataFrame()
    allwd_broker_ids = [1441]
    
    all_ob_dicts = {}
    all_tr_dicts = {}
    
    data_class.create_connection('OracleSQL')
    inst_union = pd.DataFrame()
    for m in ['de', 'fr', 'ttf']:
        inst_trades = data_class.get_trades_inst(m, venue_list, start_date, end_date + timedelta(days=1), prod='base', spread_bool=False)
        # inst_trades = trAtt.instrument_action_features(inst_trades, interval=[1, 2, 5, 10, 60])
        if inst_union.empty:
            inst_union = inst_trades
        else:
            inst_union = pd.concat([inst_union, inst_trades])
    
    inst_ts = inst_union.index

    for k, ds in enumerate(dates):
        if ds in dates_out:
            continue
        try:
            LoB_dicts = {}
            tr_dicts = {}
            bT = datetime.combine(ds, start_time)
            eT = datetime.combine(ds, end_time)
            pd1_aux = [None if p is None else p[k] for p in product_date1]
            pd2_aux = [None if p is None else p[k] for p in product_date2]
            for (m, t, n, pd1, pd2) in zip(mkt_list, tenor_list, tn_list,
                                                        pd1_aux, pd2_aux):
                i = m + t + str(n)
                # Order Book attributes
                ob_class = OrderBookSnaps(verbose=True)
                LoB, ts = load_ob(m, t, bT, pd1, bT, eT)
                ob_class.update_data(LoB, ts)

                # Trades
                data_class.create_connection('OracleSQL')
                trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT,
                                                    prod)
                trades = trades[trades['broker_id'].isin(allwd_broker_ids)]
                trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')

                tr_dicts[i] = trades
                LoB_dicts[i] = ob_class.LoB_dict

            
            df_current = prepare_data_combined(LoB_dicts[i], tr_dicts[i], depth_list, inst_ts, ds)
            
            if df_data.empty:
                df_data = df_current
            else:
                df_data = pd.concat([df_data, df_current])
        except Exception as e:
            print(e)
    
    # df_data.to_parquet(STORAGE_ + _DIR_PATH + f"reg_obt_{file_name}.parquet")