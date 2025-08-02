# -*- coding: utf-8 -*-
"""
Created on Mon Feb 24 15:10:08 2025

@author: scasny
"""

from datetime import datetime, time, timedelta
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes, unify_time_pd
import pandas as pd
from Utilities.excel_loaders import conn_out_xload_mac
from Utilities.dfutils import dict_iloc
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments
import pickle
import copy

# Global variable to control merge method
OBOOK_FIRST = True

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

def prepare_data_combined(LoB_dicts, tr_dicts, trAtt, depth_list, period_list,
                          dates, dates_out, curr_date, inst_ts, gran=None):
    print("Prepare data combined entry")
    data_class_tr = TPDataDa()
    timestamp = inst_ts[inst_ts.date == curr_date.date()]
    ob_dict = {k: {} for k in LoB_dicts.keys()}
    for i, LoB in LoB_dicts.items():
        ob_dict[i] = obAtt.prepare_ob_data_basic(LoB, depth_list)
        tr_dicts[i] = data_class_tr.clean_trades(tr_dicts[i], pd.DataFrame(ob_dict[i]), is_verbose=True)
    
    # debug = [ob_dict, tr_dicts]
    # pickle.dump(debug, open("debug.pkl", "wb"))
    
    print("Prepare reg data mkt")
    ob_prim = unify_time_pd(pd.DataFrame(ob_dict[ts_lag]).set_index('timestamp'), timestamp)
    print("ob_prim shape", ob_prim.shape)
    # trades attributes
    print("Prepare trd reg data")
    tr_dicts[ts_lag]['trd_price'] = tr_dicts[ts_lag]['price']
    tr_prim = trAtt.prepare_reg_data(tr_dicts[ts_lag], timestamp, [], period_list)
    print("tr_prim shape", tr_prim.shape)
    
    # Choose merge method based on OBOOK_FIRST flag
    if OBOOK_FIRST:
        # Original method: orderbook first, then trades
        combined_data = pd.concat([ob_prim, tr_prim], axis=1)
    else:
        # New method: adjust timestamps to avoid conflicts
        combined_data = _merge_with_timestamp_adjustment(ob_prim, tr_prim)
    
    return tr_prim, ob_dict, tr_dicts, combined_data

def _merge_with_timestamp_adjustment(ob_prim, tr_prim):
    """
    Merge orderbook and trades data with timestamp adjustment to avoid conflicts.
    """
    # Create a combined dataframe with datetime column for processing
    df = pd.concat([ob_prim, tr_prim], axis=1)
    df = df.reset_index()
    df = df.rename(columns={'timestamp': 'datetime'})
    
    # Create floored timestamp to the millisecond
    df['ts_millis'] = df['datetime'].dt.floor('ms')
    
    # Get next row's values for comparison
    next_trade = df['trd_price'].shift(-1)
    next_ts_millis = df['ts_millis'].shift(-1)
    
    # Condition 1: Non-trade row just before a trade in same millisecond → shift timestamp
    mask_shift = (
        df['trd_price'].isna() &
        next_trade.notna() &
        (df['ts_millis'] == next_ts_millis)
    )
    
    # Shift timestamp of those rows forward by 1 millisecond
    df.loc[mask_shift, 'datetime'] += pd.Timedelta(milliseconds=1)
    
    # Clean up and return with timestamp as index
    df = df.drop(['ts_millis'], axis=1)
    df = df.set_index('datetime')
    
    return df

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
        '--instrument': {'type': str, 'default': 'dey1'},
        '--start_date': {'type': str, 'default': '2025-04-04'},
        '--end_date': {'type': str, 'default': '2025-06-24'},
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
    end_time = time(17, 40, 0, 0)
    
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
    trAtt = TR_attributes(['trd_price', 'trd_gap', 'trd_side', 'last_trade_margin'])
    name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]
    
    
    class_ser = pd.Series([])
    df_data = pd.DataFrame()
    allwd_broker_ids = [1441]
    
    all_ob_dicts = {}
    all_tr_dicts = {}
    
    data_class.create_connection('OracleSQL')
    inst_trades = data_class.get_trades_inst(mkt_list[0], venue_list, start_date, end_date + timedelta(days=1), prod='base', spread_bool=False)
    
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
                if is_db:
                    LoB, ts = load_ob(m, t, bT, pd1, bT, eT)
                    ob_class.update_data(LoB, ts)
                else:
                    data_class.create_connection('PostgreSQL')
                    df_ord_data = data_class.get_orders_data(m, t, venue_list, pd1,
                                                              bT, eT, prod, pd2)
                    ob_class.import_from_tp(df_ord_data)
                # Trades
                if is_tr:
                    data_class.create_connection('OracleSQL')
                    trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT,
                                                        prod)
                    trades = trades[trades['broker_id'].isin(allwd_broker_ids)]
                    trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')
                else:
                    trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT, prod)
                tr_dicts[i] = trades
                LoB_dicts[i] = ob_class.LoB_dict
             
            # debug = [LoB_dicts, tr_dicts]
            # pickle.dump(debug, open("debug.pkl", "wb"))
            
            tr_prim, ob_dicts, tr_dicts, df_current = prepare_data_combined(LoB_dicts, tr_dicts, trAtt, depth_list,
                                               period_list, dates, dates_out, ds, inst_trades.index)
            if all_ob_dicts != {}:
                for key in all_ob_dicts:
                    for sub_key in all_ob_dicts[key]:
                        # Check if the object is a list or pandas object and apply the correct method
                        if isinstance(all_ob_dicts[key][sub_key], list):
                            all_ob_dicts[key][sub_key].extend(ob_dicts[key][sub_key])
                        else:
                            all_ob_dicts[key][sub_key] = pd.concat([all_ob_dicts[key][sub_key], ob_dicts[key][sub_key]])
    
                    all_tr_dicts[key] = pd.concat([all_tr_dicts[key], tr_dicts[key]])
            else:
                for key, v in ob_dicts.items():
                    all_ob_dicts[key] = copy.deepcopy(ob_dicts[key])
                    all_tr_dicts[key] = tr_dicts[key].copy()
            
            if df_data.empty:
                df_data = df_current
            else:
                df_data = pd.concat([df_data, df_current])
        except Exception as e:
            print(e)
    
    df_data = trAtt.aggregated_reg(df_data)
    # df_data = trAtt.diff_metrics(df_data, ['a_price', 'b_price', 'b_price_sparsity', 'a_price_sparsity', 'scaled_sparsity'], [5, 10, 20, 50, 100])
    # fair_price = trAtt.fair_price_on_lagger(all_ob_dicts[ts_lag], all_tr_dicts, dates, dates_out, ts_lag, n=16)
    
    df_ba = pd.DataFrame(all_ob_dicts[ts_lag]).set_index('timestamp')
    ts_new = df_data.index.union(df_ba.index)
    df_reg = df_data.copy()
    ts_new = ts_new[~ts_new.duplicated(keep='first')]
    df_ba_ = df_ba.reindex(ts_new).ffill() #INFO: FFILL AFTER concat with ob_prim
    

    # df_reg = df_reg.set_index('timestamp')
    concat_columns = list(set(df_reg.columns) - set(df_ba_.columns))
    df_cleaned = df_reg.groupby(df_reg.index).apply(
        lambda x: x.bfill().ffill().iloc[0]
    )
    df_backtest = pd.concat([df_ba_, df_cleaned[concat_columns]], axis=1)
    
    df_backtest['bid_t1'] = df_backtest['b_price'].shift(-1) == df_backtest['b_price']
    df_backtest['ask_t1'] = df_backtest['a_price'].shift(-1) == df_backtest['a_price']
    df_backtest.dropna(subset=['b_price'])
    
    if len(mkt_list) == 1:    
        file_name = mkt_list[0] + tenor_list[0] + str(tn1_list[0])
    else:
        file_name = mkt_list[0] + tenor_list[0] + str(tn1_list[0]) + '->' + mkt_list[1] + tenor_list[1] + str(tn1_list[1])
    import pickle
    
    def clean_ba_dupl(df_input):
        df = df_input[['b_price', 'a_price', 'trd_price']].copy()
        df['b_price_lag'] = df['b_price'].shift(1)
        df['a_price_lag'] = df['a_price'].shift(1)
        df['mask'] = (
            (df['b_price_lag'] != df['b_price']) |
            (df['a_price_lag'] != df['a_price']) |
            (~df['trd_price'].isna())
        )
        return df['mask']
    

    df_backtest[clean_ba_dupl(df_backtest)].to_parquet(STORAGE_ + _DIR_PATH + f"backtest_obt_{file_name}.parquet")
    
    df_data.to_parquet(STORAGE_ + _DIR_PATH + f"reg_obt_{file_name}.parquet")