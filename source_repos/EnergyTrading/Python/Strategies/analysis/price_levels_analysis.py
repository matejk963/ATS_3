from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
import pandas as pd
import numpy as np
from Utilities.excel_loaders import conn_out_xload
from Utilities.Storage import get_curr_storage_path
import mplfinance as mpf
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt


# -------------------- Setup and Data Loading --------------------

STORAGE_ = get_curr_storage_path()
l_path = '//192.168.10.91/data/Data/orderbooks/base/'

def load_ob(m, t, dt_obj, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt_obj.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook...' % dt_obj.strftime('%y-%m-%d'))
    print(file_path + file_name)
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook created in %d sec' % time_load)
    return ob_class.LoB_select(bT, eT, freq=None)

def variables_from_instrument(instrument: str):
    result = {'mkt': None, 'tenor': None, 'tn': None}
    for x in ['de', 'fr', 'ttf']:
        if x in instrument:
            result['mkt'] = x
    result['tenor'] = instrument[-2]
    result['tn'] = int(instrument[-1])
    return result

dates_out = conn_out_xload()
allwd_broker_ids = [1441]

# Dataset preparation
_INSTRUMENTS = ['dey1']
_START_DATE, _END_DATE = '2025-03-17', '2025-03-21'
ins_dicts = [variables_from_instrument(x) for x in _INSTRUMENTS]
n_s = 2
mkt_list = [ins_dict['mkt'] for ins_dict in ins_dicts]
tenor_list = [ins_dict['tenor'] for ins_dict in ins_dicts]
tn1_list = [ins_dict['tn'] for ins_dict in ins_dicts]
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

start_time = time(9, 0, 0)
end_time = time(17, 40, 0)
is_db = True

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
    for (m, t, n, pd1, pd2) in zip(mkt_list, tenor_list, tn_list, pd1_aux, pd2_aux):
        i = m + t + str(n)
        ob_class = OrderBookSnaps(verbose=True)
        LoB, ts = load_ob(m, t, bT, pd1, bT, eT)
        ob_class.update_data(LoB, ts)
        orders = obAtt.prepare_ob_data(LoB, [0], aonn=True)
        data_class.create_connection('OracleSQL')
        trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT, prod)
        trades = trades[trades['broker_id'].isin(allwd_broker_ids)]
        trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')
        trades = data_class.clean_trades(trades, pd.DataFrame(orders), is_verbose=True)
        if i not in df_trades:
            df_trades[i] = trades
            df_orders[i] = pd.DataFrame(orders).set_index('timestamp')
        else:
            df_trades[i] = pd.concat([df_trades[i], trades])
            df_orders[i] = pd.concat([df_orders[i], pd.DataFrame(orders).set_index('timestamp')])

# -------------------- Candlestick Data Resampling --------------------

resolution = '15min'
df = df_trades['dey1'].copy()
open_series = df['price'].resample(resolution).first()
high_series = df['price'].resample(resolution).max()
low_series = df['price'].resample(resolution).min()
close_series = df['price'].resample(resolution).last()
volume_series = df['volume'].resample(resolution).sum()
df = pd.concat([open_series, high_series, low_series, close_series, volume_series],
               axis=1, keys=['open', 'high', 'low', 'close', 'volume'])

# -------------------- Level 3 Extrema Computation --------------------

def compute_core_level3(df):
    loc_min1 = df['low'].copy()
    loc_max1 = df['high'].copy()
    # Level 2 extrema
    loc_min2 = loc_min1[((loc_min1 <= loc_min1.shift(1)) & (loc_min1 < loc_min1.shift(-1)) |
                         (loc_min1 < loc_min1.shift(1)) & (loc_min1 <= loc_min1.shift(-1)))]
    loc_max2 = loc_max1[((loc_max1 >= loc_max1.shift(1)) & (loc_max1 > loc_max1.shift(-1)) |
                         (loc_max1 > loc_max1.shift(1)) & (loc_max1 >= loc_max1.shift(-1)))]
    # Level 3 extrema
    loc_min3 = loc_min2[((loc_min2 <= loc_min2.shift(1)) & (loc_min2 < loc_min2.shift(-1)) |
                         (loc_min2 < loc_min2.shift(1)) & (loc_min2 <= loc_min2.shift(-1)))]
    loc_max3 = loc_max2[((loc_max2 >= loc_max2.shift(1)) & (loc_max2 > loc_max2.shift(-1)) |
                         (loc_max2 > loc_max2.shift(1)) & (loc_max2 >= loc_max2.shift(-1)))]
    return loc_min2, loc_max2, loc_min3, loc_max3

def compute_core_level3_single(price):
    """
    Computes level-2 and level-3 extrema (minima and maxima) from a single price series.
    
    Parameters:
    -----------
    price : pandas.Series
        Series of price values.
        
    Returns:
    --------
    tuple of pandas.Series:
        (loc_min2, loc_max2, loc_min3, loc_max3)
        where:
         - loc_min2: level-2 minima positions
         - loc_max2: level-2 maxima positions
         - loc_min3: level-3 minima positions (filtered from level-2 minima)
         - loc_max3: level-3 maxima positions (filtered from level-2 maxima)
    """
    # Level 2 extrema using neighbor comparisons
    # For minima: check the conditions for a local low
    loc_min2 = price[((price <= price.shift(1)) & (price < price.shift(-1))) |
                     ((price < price.shift(1)) & (price <= price.shift(-1)))]
    
    # For maxima: check the conditions for a local high
    loc_max2 = price[((price >= price.shift(1)) & (price > price.shift(-1))) |
                     ((price > price.shift(1)) & (price >= price.shift(-1)))]
    
    # Level 3 extrema computed from level 2 extrema
    # For minima: apply the same logic to the level-2 minima positions
    loc_min3 = loc_min2[((loc_min2 <= loc_min2.shift(1)) & (loc_min2 < loc_min2.shift(-1))) |
                        ((loc_min2 < loc_min2.shift(1)) & (loc_min2 <= loc_min2.shift(-1)))]
    
    # For maxima: similarly apply the logic to level-2 maxima
    loc_max3 = loc_max2[((loc_max2 >= loc_max2.shift(1)) & (loc_max2 > loc_max2.shift(-1))) |
                        ((loc_max2 > loc_max2.shift(1)) & (loc_max2 >= loc_max2.shift(-1)))]
    
    return loc_min2, loc_max2, loc_min3, loc_max3


def compute_adjusted_level3(df):
    loc_min2, loc_max2, candidate_min3, candidate_max3 = compute_core_level3(df)
    candidates = []
    for idx, value in candidate_min3.dropna().items():
        candidates.append((idx, value, 'min'))
    for idx, value in candidate_max3.dropna().items():
        candidates.append((idx, value, 'max'))
    candidates.sort(key=lambda x: x[0])

    adjusted = []
    last_high = None  # Track the last Level 3 high value
    last_low = None   # Track the last Level 3 low value

    for cand in candidates:
        ts, value, typ = cand
        if not adjusted:
            # First extremum, accept it
            adjusted.append(cand)
            if typ == 'min':
                last_low = value
            else:
                last_high = value
        else:
            last_ts, last_val, last_typ = adjusted[-1]
            if typ == last_typ:
                # Same type as the last accepted extremum
                if typ == 'min' and value < last_val:
                    # Replace if the new minimum is lower
                    adjusted[-1] = cand
                    last_low = value
                elif typ == 'max' and value > last_val:
                    # Replace if the new maximum is higher
                    adjusted[-1] = cand
                    last_high = value
            else:
                # Different type, check against the last extremum of the same type
                if typ == 'min':
                    if last_low is None or value < last_low:
                        adjusted.append(cand)
                        last_low = value
                elif typ == 'max':
                    if last_high is None or value > last_high:
                        adjusted.append(cand)
                        last_high = value

    adj_min = pd.Series(np.nan, index=df.index)
    adj_max = pd.Series(np.nan, index=df.index)
    for ts, value, typ in adjusted:
        if typ == 'min':
            adj_min.at[ts] = value
        elif typ == 'max':
            adj_max.at[ts] = value
    return adj_min, adj_max

loc_min2, loc_max2, candidate_min3, candidate_max3 = compute_core_level3(df)
adj_min_level3, adj_max_level3 = compute_adjusted_level3(df)

cand_min_df = pd.DataFrame(candidate_min3, columns=['candidate_min_level3'])
cand_max_df = pd.DataFrame(candidate_max3, columns=['candidate_max_level3'])
adj_min_df  = pd.DataFrame(adj_min_level3, columns=['adj_min_level3'])
adj_max_df  = pd.DataFrame(adj_max_level3, columns=['adj_max_level3'])
df_extrema = pd.concat([df, cand_min_df, cand_max_df, adj_min_df, adj_max_df], axis=1)

# -------------------- Plotting with Interactive Matplotlib --------------------

plt.ion()

df_clean = df_extrema.dropna(subset=['open', 'high', 'low', 'close']).copy()
df_clean.index = pd.to_datetime(df_clean.index)
df_plot = df_clean

ap_level2_min = mpf.make_addplot(df_plot['candidate_min_level3'], type='scatter',
                                 markersize=100, marker='o', color='blue')
ap_level2_max = mpf.make_addplot(df_plot['candidate_max_level3'], type='scatter',
                                 markersize=100, marker='o', color='blue')
# can_level2_min = mpf.make_addplot(df_plot['candidate_min_level3'], type='scatter',
#                                  markersize=100, marker='x', color='green')
# can_level2_max = mpf.make_addplot(df_plot['candidate_max_level3'], type='scatter',
#                                  markersize=100, marker='x', color='green')
addplots = [ap_level2_min, ap_level2_max]

fig, axlist = mpf.plot(df_plot, type='candle', addplot=addplots,
                         volume=False, returnfig=True,
                         title="Interactive Candlestick Chart (No Horizontal Gaps)",
                         style='charles')
plt.show()


