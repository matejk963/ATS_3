from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
import pandas as pd
import numpy as np
from Utilities.excel_loaders import conn_out_xload
from Utilities.dfutils import dict_iloc
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments
import pickle
import mplfinance as mpf
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import datetime as dt

STORAGE_ = get_curr_storage_path()
l_path = '//192.168.10.91/data/Data/orderbooks/base/'

def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    print(file_path + file_name)
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)

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

dates_out = conn_out_xload()
allwd_broker_ids = [1441]

# ------------------ dataset prep ---------------------------------

# Load arguments
_INSTRUMENTS = ['dey1']
_START_DATE, _END_DATE = '2025-03-01', '2025-04-06'
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



data_class.create_connection('OracleSQL')
inst_trades = data_class.get_trades_inst('de', venue_list, start_date, end_date, prod='base', spread_bool=False)
instrument_ts = inst_trades[inst_trades.eval('broker_id==1441')].index.drop_duplicates()


obAtt = OB_attributes(['b_price', 'a_price'])
df_orders = {}
df_trades = {}

for k, ds in enumerate(dates):
    if ds in dates_out:
        continue
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
        orders = obAtt.prepare_ob_data(LoB, [0], aonn=True)
        # Trades
        data_class.create_connection('OracleSQL')
        trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT,
                                            prod)
        trades = trades[trades['broker_id'].isin(allwd_broker_ids)]
        trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')
        trades = data_class.clean_trades(trades, pd.DataFrame(orders), is_verbose=True)

        if i not in df_trades:
            df_trades[i] = trades
            df_orders[i] = pd.DataFrame(orders).set_index('timestamp')
        else:
            df_trades[i] = pd.concat([df_trades[i], trades])
            df_orders[i] = pd.concat([df_orders[i], pd.DataFrame(orders).set_index('timestamp')])

df = df.reset_index()

df['min'] = np.nan
df['max'] = np.nan

for idx, row in df.iterrows():
    index_placeholder, o,h,l,c, df_min, df_max = row
    if index_placeholder == dt.datetime(2023,2,25):
        print('stop')
    if idx == 0:
        last_min = [idx,l]
        last_min2 = [idx,l]
        last_max = [idx,h]
        last_max2 = [idx,h]
        df.loc[idx, 'min'] = l
        df.loc[idx, 'max'] = h
        continue

    last_max_idx_diff = idx - last_max[0]
    last_max2_idx_diff = idx - last_max2[0]
    last_min_idx_diff = idx - last_min[0]
    last_min2_idx_diff = idx - last_min2[0]
    # If the value is maximum
    if last_max[1] < h:
        # if last_max2[1] < h:
        df.loc[idx, 'max'] = h     
        if last_max_idx_diff > 1:
            # Move maxes
            last_max2 = last_max
            last_max = [idx, h]
            # Find new minimum
            # if last_max2[1] < h:
            new_min_slice = df.loc[last_max2[0]:last_max[0], 'low']
            new_min = new_min_slice.min()
            new_min_idx = new_min_slice.idxmin()
            last_min2 = last_min
            last_min = [new_min_idx, new_min]
            df.loc[idx, 'min'] = new_min
        else:
            last_max = [idx, h]

    # If the value is minimum
    if last_min[1] > l:
        # if last_min2[1] > l:
        df.loc[idx,'min'] = l
        if last_min_idx_diff > 1:
            # Move mins
            last_min2 = last_min
            last_min = [idx, l]
            # Find new minimum
            # if last_min2[1] > l:
            new_max_slice = df.loc[last_min2[0]:last_min[0], 'high']
            new_max = new_max_slice.max()
            new_max_idx = new_max_slice.idxmax()
            last_max2 = last_max
            last_max = [new_max_idx, new_max]
            df.loc[idx, 'max'] = new_max
        else:
            last_min = [idx,l]
    

df = df.set_index('index')  


# %%
import plotly.graph_objects as go
from Utilities.dfutils import show_in_window
# Prepare the OHLC data for a 1-hour interval (as an example)
ohlc_1h = df[['open', 'high', 'low', 'close']].dropna()
idxs = ohlc_1h.index.values
# Create the initial candlestick chart
fig = go.Figure(data=[go.Candlestick(
    x=ohlc_1h.index,
    open=ohlc_1h['open'],
    high=ohlc_1h['high'],
    low=ohlc_1h['low'],
    close=ohlc_1h['close']
)])
 
highs_x = df[['max']].dropna().index
lows_x = df[['min']].dropna().index
 
# Add scatter traces for highs (green) and lows (red)
fig.add_trace(go.Scatter(
    x=highs_x,
    y=df['max'].dropna(),
    mode='markers',
    marker=dict(symbol='cross', color='blue', size=8),
    name='Highs'
))
 
fig.add_trace(go.Scatter(
    x=lows_x,
    y=df['min'].dropna(),
    mode='markers',
    marker=dict(symbol='cross', color='orange', size=8),
    name='Lows'
))
 
# Customize layout
fig.update_layout(
    title="5-min OHLC Candlestick Chart with Highs and Lows",
    xaxis_title="Time",
    yaxis_title="Price"
)
 
show_in_window(fig)

# %%
df.loc[dt.datetime(2023,2,2)]


