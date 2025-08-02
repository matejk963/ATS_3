import numpy as np
import pandas as pd

from Math.lm_class import LinearModel, kalman, kalman1d, OnlineScoring
from Math.accumfeatures import MSTD
from sklearn.preprocessing import StandardScaler
#from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from sklearn.linear_model import LinearRegression
import statsmodels.api as sm
from sklearn.metrics import r2_score

from datetime import datetime, time
import pytz
import logging
import math

from collections import defaultdict



######################################################################################
### helper functions
class EMA:
    def __init__(self, span):
        self.span = span
        self.value = 0
        self.alpha = 2 / (span + 1)

    def push(self, value):
        self.value = self.alpha * value + (1 - self.alpha) * self.value

class TR_class:
    def __init__(self, tau, tau_ema, burn=10):
        self.tau = tau
        self.tau_ema = tau_ema
        self.reset()
        self.__burn = burn

    @property
    def param_keys(self):
        return ['tau', 'tau_ema']

    def update_params(self, params_dict):
        if 'tau' in params_dict.keys():
            self.tau = params_dict['tau']
        if 'tau_ema' in params_dict.keys():
            self.tau_ema = params_dict['tau_ema']

    @property
    def ewma_val(self):
        return self.ewma.value

    @property
    def is_burn(self):
        return self.tot_n < self.burn

    @property
    def min_tau(self):
        return self.tau // 3

    @property
    def old_value(self):
        return self.__old_value

    @property
    def bt(self):
        return self.__bt

    @property
    def burn(self):
        return self.__burn

    @property
    def tot_n(self):
        return self.__tot_n

    def reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index = 0
        self.__bt = 1
        self.__old_value = np.nan
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def soft_reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index += 1
        self.__bt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def initialize(self):
        self.ewma.value = .5
        self.ewma_T.value = self.tau
        self.init = False

    def push(self, value, volume=None):
        if self.tot_n < 1:
            self.init = True
        else:
            diff_value = value - self.old_value
            self.__bt = self.signed_tick_vals(diff_value)
            bt = max(self.__bt, 0)
            if self.init:
                self.initialize()
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
            if self.is_burn:
                self.phiT += bt
                self.__n += 1
            elif max(self.phiT, self.__n - self.phiT) < self.thres:
                self.phiT += bt
                self.__n += 1
            else:
                self.ewma.push(self.phiT / self.__n)
                self.ewma_T.push(self.__n)
                self.phiT = 0
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
                self.index += 1
                self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return self.index

    def signed_tick_vals(self, diff_value):
        if diff_value > 0:
            return 1
        elif diff_value < 0:
            return -1
        else:
            return 0

    def tick_imbalance_single(self, trades):
        self.soft_reset()
        index_series = []
        for trade in trades:
            value = trade[0]
            if not value or np.isnan(value):
                index_series.append((trade[2], self.index))
            else:
                index_series.append((trade[2], self.push(value)))

        return index_series

    def tick_imbalance_indices(self, trades):
        self.reset()
        index_series = []
        current_date = None
        daily_trades = []

        for trade in trades:
            trade_date = trade[2].date()
            if current_date is None:
                current_date = trade_date

            if trade_date != current_date:
                # Process the previous day's trades
                index_series.extend(self.tick_imbalance_single(daily_trades))
                daily_trades = []
                current_date = trade_date

            daily_trades.append(trade)

        # Process the last day's trades
        if daily_trades:
            index_series.extend(self.tick_imbalance_single(daily_trades))

        return index_series

def get_nine_am_unix_today_cet():
    # Define the CET timezone
    cet = pytz.timezone('CET')

    # Get today's date in the CET timezone
    today = datetime.now(cet).date()

    # Combine today's date with the time 09:00 AM in CET
    nine_am_today = cet.localize(datetime.combine(today, time(9, 0)))

    # Convert to Unix timestamp (seconds since epoch)
    unix_timestamp = int(nine_am_today.timestamp())

    return unix_timestamp

def calculate_ema(current_price, previous_ema, span):
    alpha = 2 / (span + 1)
    return alpha * current_price + (1 - alpha) * previous_ema

######################################################################################
### predictor calculation



###################################################################################################################
### functions calculating additional information used in strategy for each row of lag dataframe
def calculate_MACD(df_lag, se=12, le=26):
    # Extract date part from datetime for grouping
    df_lag['date'] = df_lag['datetime'].dt.date

    # Filtering the dataset to only include rows where trd_price is not null
    df_filtered = df_lag.dropna(subset=['trd_price'])

    # Function to calculate MACD for each group
    def calculate_macd(group):
        short_ema = group['trd_price'].ewm(span=se, adjust=False).mean()
        long_ema = group['trd_price'].ewm(span=le, adjust=False).mean()
        group['MACD_'+str(se)+'_'+str(le)] = short_ema - long_ema
        return group

    # Apply the MACD calculation to each group (each day)
    df_filtered = df_filtered.groupby('date').apply(calculate_macd)

    # Merging the results back into the original dataset
    df_lag = df_lag.merge(df_filtered[['datetime', 'MACD_'+str(se)+'_'+str(le)]].drop_duplicates('datetime', keep='last'), on='datetime', how='left')
    df_lag['MACD_'+str(se)+'_'+str(le)] = df_lag.groupby('date')['MACD_'+str(se)+'_'+str(le)].ffill()

    return df_lag


def calculate_lead_lag_triggers(df_lead, df_lag, max_secs_between_trades, cluster_trade_num_threshold, min_price_movement):
    def analyze_clusters(df):
        df = df[['datetime', 'trd_price', 'trd_side']].dropna().reset_index(drop=True)
        df['time_diff'] = df['datetime'].diff().dt.total_seconds().fillna(0)


        results = []
        i = 0
        while i < len(df) - cluster_trade_num_threshold + 1:
            # Check if the next cluster_trade_num_threshold - 1 trades are within the time threshold
            valid_cluster = all(df.iloc[j]['time_diff'] <= max_secs_between_trades for j in
                                range(i + 1, i + cluster_trade_num_threshold))

            if valid_cluster:
                cluster_df = df.iloc[i:i + cluster_trade_num_threshold]
                max_price = cluster_df['trd_price'].max()
                min_price = cluster_df['trd_price'].min()
                median_price = cluster_df['trd_price'].median()
                price_movement = max_price - min_price
                direction = 0
                if price_movement > min_price_movement and median_price > min_price and median_price < max_price:
                    if cluster_df[cluster_df['trd_price'] == min_price].index[0] < \
                            cluster_df[cluster_df['trd_price'] == max_price].index[0]:
                        direction = 1
                    else:
                        direction = -1
                results.append({
                    'start_index': i,
                    'end_index': i + cluster_trade_num_threshold - 1,
                    'start_datetime': cluster_df['datetime'][i],
                    'end_datetime': cluster_df['datetime'][i + cluster_trade_num_threshold - 1],
                    'price_movement': price_movement,
                    'direction': direction
                })
                # Skip to the trade after the current cluster
                i += 1
            else:
                i += 1

        return results

    trigger_df = pd.DataFrame(analyze_clusters(df_lead))[['end_datetime', 'direction']].rename(
        columns={'end_datetime': 'trigger_datetime', 'direction': 'trigger_action'}).reset_index(drop=True)
    trigger_df['datetime'] = trigger_df['trigger_datetime']

    # JOINING ON THE LAG DF finding the latest action in the lead DF
    data_lag = pd.merge_asof(df_lag,
                             trigger_df,
                             on='datetime', direction='backward')

    return data_lag


def calculate_regression_model_price_new(dict_lead, df_lag, model_class, data_class,
                                         n_t, d_t, km_bool, vol_bool=False):
    # Filtering out only trades
    def deduplicate_trades(df):
        # cols = df.columns
        # #print(cols)
        #
        # def jitter(values, jitter_amount=1e-12):
        #     # Convert jitter amount to Timedelta
        #     jitter_timedelta = pd.to_timedelta(np.random.uniform(-jitter_amount, jitter_amount, len(values)), unit='s')
        #     return values + jitter_timedelta
        #
        # df['datetime']=jitter(df['datetime'])
        # df=df.set_index('datetime', inplace=False)
        #
        #
        #
        # df['pv'] = df['trd_price'] * df['volume']
        # df = df.groupby('datetime').agg({
        #     'pv': 'sum',
        #     # 'trd_price': 'sum',    # Mean of 'trd_price'
        #     'volume': 'sum',  # Sum of 'volume'
        #     'bid_price': 'mean',  # Max of 'bid_price'
        #     'ask_price': 'mean',  # Min of 'ask_price'
        #     'mid_price': 'mean',  # Median of 'mid_price'
        #     # 'time_diff': 'std'      # Standard deviation of 'time_diff'
        # })
        # df['trd_price'] = df['pv'] / df['volume']
        df_out = df.set_index('datetime', inplace=False).sort_index()
        df_out.index.name = 'index'
        agg_dict = {'trd_price': 'sum', 'volume': 'sum', 'bid_price': 'mean',
                    'ask_price': 'mean', 'mid_price': 'mean',
                    'trd_side': 'median', 'time_diff': 'first'}
        df_out['trd_price'] *= df_out['volume']
        df_out = df_out.groupby(df_out.index).agg(agg_dict)
        df_out['trd_price'] /= df_out['volume']
        return df_out

    data_lead_trds = {k: deduplicate_trades(v[v['trd_price'].isnull() == False]) for k, v in dict_lead.items()}
    data_lag_trds = deduplicate_trades(df_lag[df_lag['trd_price'].isnull() == False])
    # Create dataframes for processing and model
    data_p, data_v = pd.DataFrame([]), pd.DataFrame([])
    if not vol_bool:
        data_v = None
    col_list = [data_class.mkt]
    [col_list.append(m) for m in data_lead_trds.keys()]
    data_p = data_lag_trds.loc[:, 'trd_price']
    for m in col_list[1:]:
        data_p = pd.concat([data_p, data_lead_trds[m].loc[:, 'trd_price']], axis=1)
    data_p.columns = col_list
    if vol_bool:
        data_v = data_lag_trds.loc[:, 'volume']
        for m in col_list[1:]:
            data_v = pd.concat([data_v, data_lead_trds[m].loc[:, 'volume']], axis=1)
        data_v.columns = col_list
    # Train and model output
    mdl_dict = process_regression_model_price(data_p, data_v, model_class, data_class,
                                              n_t, d_t, km_bool)
    # Price and volume
    df_price = data_lag_trds.loc[:, ['trd_price', 'volume']]
    tag_ser = pd.Series('lag', index=df_price.index, name='tag')
    df_price = pd.concat([df_price, tag_ser], axis=1)
    for m, v in data_lead_trds.items():
        df_price_aux = v.loc[:, ['trd_price', 'volume']]
        tag_ser = pd.Series('lead_' + m, index=df_price.index, name='tag')
        df_price_aux = pd.concat([df_price_aux, tag_ser], axis=1)
        df_price = pd.concat([df_price, df_price_aux])
    df_price = df_price.sort_values(by=['index', 'tag'], axis=0, ascending=[True, True])
    df_price = df_price.reset_index().set_index(['index', 'tag'])
    # Bid ask of lagger
    df_ba = data_lag_trds.loc[:, ['bid_price', 'ask_price']]
    grouped = df_ba.groupby(df_ba.index.date)
    ba_dict = {date: group.dropna() for date, group in grouped
               if date in mdl_dict.keys()}
    # Combine into dataframe
    pd_mdl = pd.DataFrame([])
    for d, v in mdl_dict.items():
        df_ba_aux = ba_dict[d]
        ts = df_ba_aux.index.union(v.index)
        df_ba_aux = df_ba_aux.reindex(ts).ffill().reindex(v.index)
        df_out_aux = pd.concat([df_ba_aux, v], axis=1)
        if pd_mdl.empty:
            pd_mdl = df_out_aux
        else:
            pd_mdl = pd.concat([pd_mdl, df_out_aux])
    pd_mdl = pd_mdl.reset_index().set_index(['index', 'tag'])
    # Concat bot dataframes
    return pd.concat([df_price, pd_mdl], axis=1)


def process_regression_model_price(data_p, data_v, model_class, data_class,
                                   n_t, d_t, km_bool):
    # Training and testing days
    sample_dates = sorted(list(set(data_p.index.date)))
    n = n_t + d_t
    date_range_dict = {k: pd.date_range(k, periods=n, freq='B')
                       for k in sample_dates[:-n+1]}
    data_dict = data_class.data_process_2(data_p, data_v, km_bool=km_bool)
    split_dict = data_class.split_data(data_dict, date_range_dict, d_t)
    for v in split_dict.values():
        d_list = []
        for d in v['keys']:
            if (len(v['train'][d]['X']) == 0) or (len(v['tests'][d]['X']) == 0):
                v['train'].pop(d)
                v['tests'].pop(d)
                d_list.append(d)
        for d in d_list:
            v['keys'].remove(d)
    # Market
    mkt = data_class.mkt
    mkt_l = [x for x in data_p.columns if x != mkt]
    pred_dict = {m: [] for m in mkt_l}
    for m in mkt_l:
        # Scale
        reg_data = data_class.scale_data_dict(split_dict[m])
        # Fit
        pred_dict[m] = data_class.prepare_model_trds(data_p, mkt, model_class, reg_data)
    # mdl_dict = data_class.process_model_supp_n(pred_dict)
    # pd_out = pd.DataFrame([])
    # for d, v in mdl_dict.items():
    #     if pd_out.empty:
    #         pd_out = v
    #     else:
    #         pd_out = pd.concat([pd_out, v])
    return data_class.process_model_supp_n(pred_dict)


def calculate_regression_model_price(df_lead, df_lag, tau, tau_ema, n_days, fit_reg_coef, coef1, coef2):
    # Filtering out only trades
    def deduplicate_trades(df):
        # cols = df.columns
        # #print(cols)
        #
        # def jitter(values, jitter_amount=1e-12):
        #     # Convert jitter amount to Timedelta
        #     jitter_timedelta = pd.to_timedelta(np.random.uniform(-jitter_amount, jitter_amount, len(values)), unit='s')
        #     return values + jitter_timedelta
        #
        # df['datetime']=jitter(df['datetime'])
        # df=df.set_index('datetime', inplace=False)
        #
        #
        #
        # df['pv'] = df['trd_price'] * df['volume']
        # df = df.groupby('datetime').agg({
        #     'pv': 'sum',
        #     # 'trd_price': 'sum',    # Mean of 'trd_price'
        #     'volume': 'sum',  # Sum of 'volume'
        #     'bid_price': 'mean',  # Max of 'bid_price'
        #     'ask_price': 'mean',  # Min of 'ask_price'
        #     'mid_price': 'mean',  # Median of 'mid_price'
        #     # 'time_diff': 'std'      # Standard deviation of 'time_diff'
        # })
        # df['trd_price'] = df['pv'] / df['volume']

        return df.set_index('datetime', inplace=False).sort_index()

    data_lead_trds = deduplicate_trades(df_lead[df_lead['trd_price'].isnull() == False])
    data_lag_trds = deduplicate_trades(df_lag[df_lag['trd_price'].isnull() == False])

    data_lead_trds['tag'] = 'lead'
    data_lag_trds['tag'] = 'lag'

    df_trds = pd.concat([data_lead_trds, data_lag_trds]).sort_index()

    df_trds['lead_price'] = df_trds[['trd_price', 'tag']].apply(lambda row: row['trd_price'] if row['tag'] == 'lead' else None, axis=1)
    df_trds['lead_volume'] = df_trds[['volume', 'tag']].apply(lambda row: row['volume'] if row['tag'] == 'lead' else None, axis=1)
    df_trds['lead_pv'] = df_trds[['trd_price', 'volume', 'tag']].apply(lambda row: row['trd_price'] * row['volume'] if row['tag'] == 'lead' else None, axis=1)

    df_trds['lag_price'] = df_trds[['trd_price', 'tag']].apply(lambda row: row['trd_price'] if row['tag'] == 'lag' else None, axis=1)
    df_trds['lag_volume'] = df_trds[['volume', 'tag']].apply(lambda row: row['volume'] if row['tag'] == 'lag' else None, axis=1)
    df_trds['lag_pv'] = df_trds[['trd_price', 'volume', 'tag']].apply(lambda row: row['trd_price'] * row['volume'] if row['tag'] == 'lag' else None, axis=1)


    agg_dict = {'index': 'first', 'datetime': 'first'}
    agg_dict.update({k: 'sum' for k in ['lead_volume', 'lead_pv', 'lag_volume', 'lag_pv']})

    df_trds['date'] = df_trds.index.date
    dates_list = sorted(list(set(df_trds['date'])))

    df_list = []
    df_list2 = []

    sort_order=[True, False, True]

    for current_day in dates_list:
        df_trds_1day = df_trds[df_trds['date'] == current_day].reset_index()
        df_trds_1day['execution_time'] = df_trds_1day['datetime'].astype('int64')  # Already in nanoseconds

        # Preparing tick data
        ti_cls = TR_class(tau, tau_ema)

        df_trds_1day = df_trds_1day.sort_values(by=['datetime', 'lag_volume', 'lag_price'], ascending=sort_order).reset_index()


        # Create the list of tuples
        lag_trades = [(row['lag_price'], row['volume'], row['execution_time']) for index, row in
                      df_trds_1day.iterrows()]


        idx_series = ti_cls.tick_imbalance_single(lag_trades)
        idx_series = pd.DataFrame(idx_series, columns=['index', 0])


        if 'level_0' in df_trds_1day.columns:
            del df_trds_1day['level_0']

        # Create returns
        df_trds_indexed_1day = pd.concat([df_trds_1day, idx_series[0]], axis=1).reset_index()
        lag_index = df_trds_indexed_1day[df_trds_indexed_1day['tag'] == 'lag'].index.min()
        lead_before_lag = df_trds_indexed_1day[(df_trds_indexed_1day['tag'] == 'lead') & (df_trds_indexed_1day.index < lag_index)]
        df_trds_indexed_1day.loc[lead_before_lag.index, 0] = 0

        df_trds_indexed_1day['tick_id'] = str(current_day) + '_' + df_trds_indexed_1day[0].fillna(0).apply(str)
        #df_trds_indexed_1day['datetime'] = df_trds_indexed_1day['timestamp']
        #df_trds_indexed_1day = df_trds_indexed_1day.set_index('datetime')
        df_trds_indexed_1day_grouped = df_trds_indexed_1day.groupby('tick_id').agg(
            agg_dict).reset_index().set_index('datetime')

        df_trds_indexed_1day_grouped['lead_price'] = df_trds_indexed_1day_grouped['lead_pv'] / \
                                                     df_trds_indexed_1day_grouped['lead_volume']
        df_trds_indexed_1day_grouped['lag_price'] = df_trds_indexed_1day_grouped['lag_pv'] / \
                                                    df_trds_indexed_1day_grouped['lag_volume']

        df_trds_indexed_1day_grouped['lead_log_ret'] = np.log(df_trds_indexed_1day_grouped['lead_price'].ffill() ).diff()
        df_trds_indexed_1day_grouped['lag_log_ret'] = np.log(df_trds_indexed_1day_grouped['lag_price'].ffill() ).diff()
        df_list.append(df_trds_indexed_1day_grouped)
        df_list2.append(df_trds_indexed_1day)

    df_trds_indexed = pd.concat(df_list).sort_index()
    df_trds = pd.concat([df_trds.sort_values(by=['datetime', 'lag_volume', 'lag_price'], ascending=sort_order).reset_index(drop=True), pd.concat(df_list2).sort_values(by=['datetime', 'lag_volume', 'lag_price'], ascending=sort_order).reset_index(drop=True)['tick_id']], axis=1)

    #Model fitting and scoring
    # Prepare to store predictions
    df_trds_indexed['lag_log_ret_pred'] = np.nan
    df_trds_indexed['coef1'] = np.nan
    df_trds_indexed['coef2'] = np.nan
    df_trds_indexed['date'] = df_trds_indexed.index.date
    dates_list = sorted(list(set(df_trds_indexed['date'])))

    # Loop through each day and fit the model using the previous n days
    for current_day in dates_list[n_days:]:
        # Get the previous n days data
        start_day = dates_list[dates_list.index(current_day) - n_days]
        training_data = df_trds_indexed[start_day:current_day]

        # Skip if not enough datadf_filtered
        if len(training_data) < n_days:
            continue

        # Independent variable (lead_log_ret) and dependent variable (lag_log_ret)
        X_train = training_data['lead_log_ret'].fillna(0)
        y_train = training_data['lag_log_ret'].fillna(0)

        # Add a constant to the independent variable
        X_train = sm.add_constant(X_train)

        # Fit the model using statsmodels
        model = sm.OLS(y_train, X_train).fit()

        # Predict the lag_log_ret for the current day using the model
        X_test = sm.add_constant(df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'lead_log_ret'].fillna(0))
        df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'lag_log_ret_pred'] = model.predict(X_test).fillna(0)
        df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'coef1'] = model.params[0] if fit_reg_coef  else coef1 #model.params[0]#0.00000000001#
        df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'coef2'] = model.params[1] if fit_reg_coef  else coef2 #model.params[1]#0.8661 #

    # Production predicted price
    df_trds['prev_tick_id']=df_trds['tick_id'].apply(lambda x: x.split('_')[0]+'_')+df_trds['tick_id'].apply(lambda x: str(int(x.split('_')[1])-1))
    df_trds_indexed['lead_price_tick']=df_trds_indexed['lead_price']
    df_trds_indexed['lag_price_tick']=df_trds_indexed['lag_price']
    df_trds_indexed['prev_tick_id']=df_trds_indexed['tick_id']

    df_trds=df_trds.merge(df_trds_indexed[['prev_tick_id', 'lead_price_tick', 'lag_price_tick', 'coef1', 'coef2']], how='left', on='prev_tick_id')
    df_trds_lead=df_trds[df_trds['tag']=='lead']

    def predict_lag_price(lead_price_tick, lead_price, lag_price_tick, coef1, coef2):
        if all([lead_price_tick, lead_price, lag_price_tick, coef1, coef2]):
            return lag_price_tick*np.exp((coef1+coef2*np.log(lead_price/lead_price_tick)))
        else:
            return None

    df_trds_lead['lag_price_predicted']=df_trds_lead[['lead_price_tick', 'lead_price', 'lag_price_tick', 'coef1', 'coef2']].apply(lambda row: predict_lag_price(row['lead_price_tick'], row['lead_price'], row['lag_price_tick'], row['coef1'], row['coef2']), axis=1)
    df_trds_lead['lag_price_predicted_datetime']=df_trds_lead['timestamp']
    df_trds_lead['datetime']=df_trds_lead['timestamp']



 


    #data_lag=pd.merge_asof(df_lag,df_trds_lead[['datetime','lag_price_predicted','lag_price_predicted_datetime', 'lag_price_tick']], on='datetime', direction='backward')


    return df_trds_lead


# Calculate the time since the first lead trade of the day and total number of lead trades
def calc_vol_intensity_index(df, n, tag):
    # Ensure datetime columns are properly parsed
    df["datetime"] = pd.to_datetime(df["datetime"])

    # Initialize a new column for the metric
    df["VII_" + tag + "_" + str(n)] = None

    # Group by date to process each day separately
    for day, day_df in df.groupby("date"):
        #print(f'{tag}  {n} {day}')

        # Filter out the lead trades for the current day (trd_price not null)
        lead_trades = day_df[(day_df["tag"] == tag) & (day_df["trd_price"].notnull())]

        if lead_trades.empty:
            continue  # If no lead trades, skip this day

        # Precompute important information
        lead_trades = lead_trades.sort_values("datetime")
        lead_trades["cumcount"] = list(range(1, len(lead_trades) + 1)) # Cumulative count of trades

        lead_trades["time_since_first"] = (lead_trades["datetime"] - lead_trades["datetime"].iloc[0]).dt.total_seconds()
        lead_trades["time_since_last"]=lead_trades['datetime']

        lead_trades["time_diff"] = lead_trades["datetime"].diff().dt.total_seconds()
        lead_trades["time_since_last_n"]=lead_trades["time_diff"].rolling(window=n-1).sum()

        # Merge the lead_trades back into the original day_df based on datetime to avoid row-wise filtering
        day_df = day_df.merge(lead_trades[["cumcount", "time_since_first", "time_since_last", "time_since_last_n"]], left_index=True, right_index=True, how='left')

        # Fill forward to ensure every row has values for cumcount and time_since_first where applicable
        day_df["cumcount"].fillna(method="ffill", inplace=True)
        day_df["time_since_first"].fillna(method="ffill", inplace=True)
        day_df["time_since_last"].fillna(method="ffill", inplace=True)
        day_df["time_since_last_n"].fillna(method="ffill", inplace=True)


        # Calculate the average time between the last n trades and since the first lead trade
        day_df["avg_time_last_n_trades"] = (day_df["time_since_last_n"]+(day_df['datetime']-day_df['time_since_last']).dt.total_seconds()) / n
        day_df["avg_time_since_first_lead"] = (day_df["time_since_first"]+(day_df['datetime']-day_df['time_since_last']).dt.total_seconds()) / day_df["cumcount"]

        # Calculate the final metric
        day_df["VII_" + tag + "_" + str(n)] = 1/(day_df["avg_time_last_n_trades"] / day_df["avg_time_since_first_lead"])

        # Update the original dataframe with the new metric
        df.loc[df["date"] == day, "VII_" + tag + "_" + str(n)] = day_df["VII_" + tag + "_" + str(n)]

    return df
