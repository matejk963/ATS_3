from datetime import datetime, time
import pandas as pd
import numpy as np

from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
from Strategies.Sparse_momentum.ob_attributes import diff, unify_time_pd
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Database.TPData import TPData, TPDataDa
from Utilities.excel_loaders import conn_out_xload

dates_out = conn_out_xload()

l_path = '//192.168.10.91/data/Data/orderbooks/base/'


def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)

def product_dates(dates, t, tn, n_s):
    # Product dates
    pd_list = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                dates.shift(tn, freq='YS') if t == 'dec' else
                (dates + n_s * dates.freq).shift(tn, freq='AS-Apr') if t in ['sum'] else
                (dates + n_s * dates.freq).shift(tn, freq='AS-Oct') if t in ['win'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')]
    return pd_list

def get_index_for_ts(series, ts):
    idx_cand = (series - ts).abs().idxmin()
    while series[idx_cand] > ts:
        if idx_cand < 1:
            return 0
        else:
            idx_cand -= 1
    return idx_cand

AONN_ = True
n_s = 2
primary_tenor = 'y'
# mkt_list = ['de', 'de', 'de']
primary_mkt = {
    'mkt': 'de',
    'tenor': primary_tenor,
    'tn1': 1
}
secondary_mkts = [
    {'mkt': 'de', 'tenor': 'q', 'tn1': 1},
    {'mkt': 'de', 'tenor': 'y', 'tn1': 1},
    {'mkt': 'ttf', 'tenor': 'm', 'tn1': 1}
]


prod = 'base'
venue_list = ['eex']
# Order book features variables
features_list = ['sparsity']
depth_list = [0.1, 0.15, 0.2, 0.3, 0.5, 1.0]
period_list = [5, 20]
tick = 0.01
tick_val = 200
cls_margin = 0.10
obAtt = OB_attributes(features_list)
trAtt = TR_attributes(['trd_gap'])

#   -   -   - 
start_date = datetime(2024, 8, 1)
end_date = datetime(2024, 11, 6)
# end_date = datetime(2024, 5, 17)    
dates = pd.date_range(start_date, end_date, freq='B')


primary_mkt['pd'] = product_dates(dates, primary_mkt['tenor'], primary_mkt['tn1'], n_s)
_ = [sec_m.update({'pd': product_dates(dates, sec_m['tenor'], sec_m['tn1'], n_s)}) for sec_m in secondary_mkts]


start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)

is_db = True
is_tr = True


if is_db:
    data_class = TPData()
else:
    data_class = TPDataDa()
data_class_tr = TPDataDa()
df_data = pd.DataFrame()
for ds, pd1 in zip(dates, *primary_mkt['pd']):
    if ds in dates_out:
        continue
    try:
        bT = datetime.combine(ds, start_time)
        eT = datetime.combine(ds, end_time)
        ob_class = OrderBookSnaps(verbose=True)
        if is_db:
            LoB, ts = load_ob(primary_mkt['mkt'], primary_mkt['tenor'], bT, pd1, bT, eT)
            ob_class.update_data(LoB, ts)
        else:
            df_ord_data = data_class.get_orders_data(primary_mkt['mkt'], primary_mkt['tenor'], venue_list, pd1,
                                                bT, eT, prod, None)
            ob_class.import_from_tp(df_ord_data)
        if is_tr:
            data_class.create_connection('OracleSQL')
            trades = data_class.get_trades(primary_mkt['mkt'], primary_mkt['tenor'], venue_list, pd1, bT, eT,
                                                prod)
            trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')
        else:
            trades = data_class_tr.get_trades(primary_mkt['mkt'], primary_mkt['tenor'], venue_list, pd1, bT, eT, prod)
    
        data_dict = obAtt.prepare_ob_data(ob_class.LoB_dict, depth_list, aonn=AONN_)
        idx, csum, ts = obAtt.calc_tick_index(data_dict, None, None, 1)
        # ob_prim = obAtt.prepare_reg_data_mkt(data_dict, ts, idx, period_list,
        #                                      depth_list, ts_data=None, keep_ts=True)
    
        # reg_df = obAtt.prepare_reg_data_mkt(data_dict, ob_class.time_list, idx, [3, 5, 10, 20], [0.15, 0.25, 0.5])
        df_ba = pd.DataFrame(data_dict).set_index('timestamp')
        trades = data_class_tr.clean_trades(trades, df_ba, is_verbose=True)
        trades.rename(columns={'price': 'trd_price', 'volume': 'trd_vol'}, inplace=True)
        
        ts_new = trades.index.union(df_ba.index)
        trades = trades.reset_index().drop_duplicates('datetime', keep='first').set_index('datetime')
        ts_new = ts_new[~ts_new.duplicated(keep='first')]
        df_ba_ = df_ba.reindex(ts_new).ffill() # IMPORTANT FFILL AFTER concat with ob_prim
        
        df_current = pd.concat([df_ba_, trades], axis=1)
        
        df_current['last_trd_p'] = df_current['trd_price']
        df_current['last_trd_p'].ffill(inplace=True)
        df_current['bid_t1'] = df_current['b_price'].shift(-1) == df_current['b_price']
        df_current['ask_t1'] = df_current['a_price'].shift(-1) == df_current['a_price']
        df_current = pd.concat([df_current], axis=1)
        
        if df_data.empty:
            df_data = df_current.copy()
        else:
            df_data = pd.concat([df_data, df_current])
    except Exception as e:
        print(e)

# sec_dict = {}
# for mkt_dict in secondary_mkts:
#     current_df = pd.DataFrame()
#     for ds, pd1 in zip(dates, *mkt_dict['pd']):
#         try:
#             bT = datetime.combine(ds, start_time)
#             eT = datetime.combine(ds, end_time)
            
#             trades = data_class.get_trades(mkt_dict['mkt'], mkt_dict['tenor'], venue_list, pd1, bT, eT, prod)
#             if current_df.empty:
#                 current_df = trades
#             else:
#                 current_df = pd.concat([current_df, trades])
#         except Exception as e:
#             print(e)
#             pass
#     sec_dict[f"{mkt_dict['mkt']}_{mkt_dict['tenor']}"] = current_df

# df_data = df_data.set_index('timestamp').reset_index()
# for sec_mkt, df in sec_dict.items():
#     col_name = f"diff_{sec_mkt}"
#     df = df[~df.index.duplicated()]
#     diff_series = diff(df['price'], 5, True)
#     for ts, price in diff_series.to_dict().items():
#         index = get_index_for_ts(df_data['timestamp'], ts)
#         df_data.loc[index, col_name] = price
#     df_data[col_name].ffill(inplace=True)

# df_data['hour'] = df_data['timestamp'].dt.hour
# df_data['last_trade_margin'] = df_data['last_trd_p'] - df_data['mid_price']
# ========================================================================
# IMPORTANT: overwrite ba_spread from log scale into eur
df_data['ba_spread'] = df_data['a_price'] - df_data['b_price']

### scaled sparsity !!!!!
from scipy.stats import norm
import math
def df_days_tag(df):
    unique_dates = df['timestamp'].dt.date.unique()
    
    # Create a dictionary to map unique dates to tags
    date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
    
    # Add a new column for the tags
    df['day'] = df['timestamp'].dt.date.map(date_to_tag)
    
    return df.copy()

df_data = df_days_tag(df_data).copy()

# Function to insert missing values into the sorted array
def insert_missing_values(sorted_array, full_range):
    updated_array = sorted_array.copy()  # Copy to avoid modifying the original array
    
    for value in full_range:
        if value not in updated_array:
            # Find the indices of the closest values before and after `value`
            index_prev = np.searchsorted(updated_array, value, side='left') - 1
            index_next = index_prev + 1
            
            # Handle cases where index_prev or index_next is out of range
            if index_prev < 0:
                index_prev = 0
            if index_next >= len(updated_array):
                index_next = len(updated_array) - 1
            
            # Insert the missing value into the sorted array
            updated_array = np.insert(updated_array, index_next, value)
    
    return updated_array

train_days = 3
for i in range(train_days, df_data['day'].max()+1):
    df_hist = df_data[(df_data['day'] >= i-train_days) & (df_data['day'] < i)]
    df_curr = df_data[df_data['day'] == i]
    
    sp = sorted(df_hist['a_price_sparsity'].values)
    # Create a full range with steps of 0.01
    full_range = np.round(np.arange(0.0, 1.01, 0.01), 2)
    full_range = np.concatenate([full_range, np.array([2.0])], axis=0)
    sp = np.round(sp, 2)
    
    # Step 3: Fill missing values
    filled_sp = insert_missing_values(sp, full_range)
    length = len(filled_sp)
    
    func = lambda a: norm.ppf(np.where(filled_sp == a)[0][0]/length)
    df_data.loc[df_data['day'] == i, 'scaled_sparsity'] = df_curr.apply(
        lambda row: math.erf((func(row['a_price_sparsity'])-func(row['b_price_sparsity']))/2), axis=1)
    


# df_data.dropna(subset=['int'], inplace=True)

import pickle
pickle.dump(df_data, open(
    f"obtrd_{'_'.join(list(map(str, [*primary_mkt.values()][:3])))}.pkl","wb"))

# df_data = pickle.load(open(
#     f"obtrd_{'_'.join(list(map(str, [*primary_mkt.values()][:3])))}.pkl","rb"))
df_data['trd_side_last'] = df_data['trd_side'].shift(1)
df_data.dropna(subset=['trd_side_last'], inplace=True)


from abc import ABC, abstractmethod

class FeatureInterface(ABC):
    @abstractmethod
    def condition_short(data):
        # mandatory
        pass
    
    @abstractmethod
    def condition_long(data):
        # mandatory
        pass
    def condition_close_short(data):
        # optional, define only when feature is designated to close short position
        return False
    def condition_close_long(data):
        # optional, define only when feature is designated to close long position
        return False
    
    def condition_close(data):
        # method that is called in strategy.check_state
        return False
    
    @staticmethod
    def check_data(strategy_data_columns, data_columns):
        assert all([x in strategy_data_columns for x in data_columns])

class FeatureSparsity(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_dense, thold_sparse):
        self.thold_dense = thold_dense
        self.thold_sparse = thold_sparse
        self.data_columns = ['a_price_sparsity', 'b_price_sparsity']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def _allowed_value(self, data):
        if data['a_price_sparsity'] > 1.5 or data['b_price_sparsity'] > 1.5:
            return False
        else:
            return True
        
    def condition_long(self, data):
        return (data['a_price_sparsity'] > self.thold_sparse
                 and data['b_price_sparsity'] < self.thold_dense) and self._allowed_value(data)
    
    def condition_short(self, data):
        return (data['b_price_sparsity'] > self.thold_sparse
                 and data['a_price_sparsity'] < self.thold_dense) and self._allowed_value(data)
    
class FeatureDirectionChange(FeatureInterface):
    def __init__(self, strategy_data_columns, thold):
        self.thold = thold
        self.data_columns = ['trd_side', 'trd_side_last', 'trd_price', 'last_trd_p']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def _common_condition(self, data):
        return int(data['trd_side']) != int(data['trd_side_last'])
    
    def _calc_trd_diff(self, data):
        p_curr = data['trd_price']
        p_prev = data['last_trd_p']
        return round(p_curr - p_prev, 2)
    
    def condition_long(self, data):
        return self._common_condition(data) and data['trd_side'] > 0.5 and self._calc_trd_diff(data) > self.thold
    
    def condition_short(self, data):
        return self._common_condition(data) and data['trd_side'] < 0.5 and self._calc_trd_diff(data) < -self.thold
    
    
feature_sp = FeatureSparsity(df_data.columns, 0.35, 0.25)
feature_dc = FeatureDirectionChange(df_data.columns, 0.14)

df_data['sp_long'] = df_data.apply(lambda row: feature_sp.condition_long(row), axis=1)
df_data['sp_short'] = df_data.apply(lambda row: feature_sp.condition_short(row), axis=1)
df_data['dc_long'] = df_data.apply(lambda row: feature_dc.condition_long(row), axis=1)
df_data['dc_short'] = df_data.apply(lambda row: feature_dc.condition_short(row), axis=1)