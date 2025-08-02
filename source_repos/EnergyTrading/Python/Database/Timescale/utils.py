import pandas as pd

def seqid_dict(com):
    my_dict = {}
    if com == 'pwr':
        my_dict['D'] = 10000100
        my_dict['WEND'] = 10000101
        my_dict['W'] = 10000102
        my_dict['M'] = 10000104
        my_dict['Q'] = 10000105
        my_dict['Y'] = 10000106
    elif com == 'gas':
        my_dict['DA'] = 10000302
        my_dict['WEND'] = 10000302
        my_dict['BOM'] = 10000301
        my_dict['M'] = 10000305
        my_dict['Q'] = 10000306
        my_dict['S'] = 10000307
        my_dict['SUM'] = 10000307
        my_dict['WIN'] = 10000307
        my_dict['Y'] = 10000309
    elif com == 'eua':
        my_dict['DEC'] = 10000400
    else:
        raise ValueError('Unknown commodity %s' % com)
    return my_dict


def instid_dict():
    my_dict = {}
    my_dict['de'] = {'eex': 10641710, 'otc': 10001126}
    my_dict['fr'] = {'eex': 10001075, 'otc': 10001109}
    my_dict['hu'] = {'eex': 10011036, 'otc': 10001137}
    my_dict['it'] = {'eex': 10100480, 'otc': 10001157}
    my_dict['es'] = {'eex': 10012528, 'otc': 10001183}
    my_dict['ttf'] = {'eex': 10002806, 'otc': 10002096}
    my_dict['the'] = {'eex': 10002148}
    my_dict['eua'] = {'eex': 10003008, 'ice': 10003007}
    my_dict['de_fr'] = {'eex': 10641750}
    my_dict['de_hu'] = {'eex': 10642360}
    my_dict['de_at'] = {'eex': 10641886}
    my_dict['de_cz'] = {'eex': 10642316}
    my_dict['it_de'] = {'eex': 10642564}
    my_dict['nl_de'] = {'eex': 10643876}
    return my_dict


def get_trades_data(instrument: str, start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """
    get_trades_data('deq1', '2025-05-01', '2025-05-10')\n
    Fetches and processes trade data for a specified instrument and date range.

    This function retrieves trades from a time-series database (TSDB), filters them
    by allowed broker IDs, and removes duplicate entries based on datetime.

    Parameters:
    instrument (str): The financial instrument identifier (e.g., 'deq1').
                      This is used to determine market, tenor, and other instrument-specific parameters.
    start_date_str (str): The start date for fetching trades, formatted as 'YYYY-MM-DD'.
    end_date_str (str): The end date for fetching trades, formatted as 'YYYY-MM-DD'.

    Returns:
    pd.DataFrame: A DataFrame containing the processed trade data. The DataFrame will have a
                  'datetime' index and include columns from the trades table. If no trades
                  are found or after filtering, an empty DataFrame with the same structure
                  might be returned.
    """
    
    from datetime import datetime, time
    from Database.TPData import TPData, TPDataDa
    from OrderBook.OrderBook import OrderBookSnaps
    from SynthSpread.spreadviewer_class import SpreadSingle
    from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
    import pandas as pd
    import numpy as np
    from Utilities.excel_loaders import conn_out_xload_mac
    from Utilities.dfutils import dict_iloc
    from Utilities.func_utils import load_arguments
    import pickle



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



    allwd_broker_ids = [1441]

    # ------------------ dataset prep ---------------------------------
    # Load arguments
    _INSTRUMENTS = [instrument]
    _START_DATE, _END_DATE = start_date_str, end_date_str

    # setting variables
    ins_dicts = [variables_from_instrument(x) for x in _INSTRUMENTS]
    n_s = 2
    mkt_list = [ins_dict['mkt'] for ins_dict in ins_dicts]
    tenor_list = [ins_dict['tenor'] for ins_dict in ins_dicts]
    tn1_list = [ins_dict['tn'] for ins_dict in ins_dicts]
    ts_lag = (lambda i: mkt_list[i] + tenor_list[i] + str(tn1_list[i]))(0)

    tn2_list = []
    prod = 'base'
    venue_list = ['eex']
    start_date = datetime.strptime(_START_DATE, '%Y-%m-%d').date()
    end_date = datetime.strptime(_END_DATE, '%Y-%m-%d').date()
    # ---------------------------------------------------------------------

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


    data_class = TPData()
    data_class.create_connection('timescaledb')

    result = pd.DataFrame()

    for k, ds in enumerate(dates):
        try:
            bT = datetime.combine(ds, start_time)
            eT = datetime.combine(ds, end_time)
            pd1_aux = [None if p is None else p[k] for p in product_date1]
            pd2_aux = [None if p is None else p[k] for p in product_date2]
            for (m, t, n, pd1, pd2) in zip(mkt_list, tenor_list, tn_list,
                                                        pd1_aux, pd2_aux):
                i = m + t + str(n)
                # Trades
                trades = data_class.get_trades_tsdb(m, t, venue_list, pd1, bT, eT,
                                                    prod)
                trades = trades[trades['broker_id'].isin(allwd_broker_ids)]
                trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')

                if result.empty:
                    result = trades
                else:
                    result = pd.concat([result, trades])
        except Exception as e:
            print(e)

    return result


def get_trades_item(market, tenor, itemid, start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """
    get_trades_item('de', 'y', 23, '2024-01-01', '2025-05-05')
    """    
    from datetime import datetime, time
    from Database.DB_reader import Database

    stmt = f"""
    select * from public.trades
    where instid = {instid_dict()[market]['eex']}
    and firstsequenceitemid = {itemid}
    and secondsequenceitemid = 0
    and firstsequenceid = {seqid_dict('pwr')[tenor.upper()]}
    and datetime >= '{start_date_str}'
    and datetime <= '{end_date_str}'
    and aggressorbroker_id_ut = 14;
    """
    print(stmt)
    db = Database('timescaledb')
    df = db.execute_general_query(stmt)
    df.set_index('datetime', inplace=True)
    df.index = df.index + pd.to_timedelta(df['nanotime'].astype(float), unit='ns')
    df = df.sort_index()[['tradeid', 'price', 'action', 'volume']]
    df['price'] = df['price'].astype(float)
    df['volume'] = df['volume'].astype(int)
    return df

def list_itemid(tenor):
    """
    tenor: 'm', 'q', 'y'
    """
    stmt = f"""
    select distinct firstsequenceitemid, firstsequenceitemname  from public.trades
    where firstsequenceid = {seqid_dict('pwr')[tenor.upper()]} order by firstsequenceitemid;
    """
    from datetime import datetime, time
    from Database.DB_reader import Database
    db = Database('timescaledb')
    df = db.execute_general_query(stmt)
    return df


if __name__ == "__main__":
    # Example usage
    trades_data = get_trades_data('deq1', '2025-05-01', '2025-05-10')
    print(trades_data.head())
    
