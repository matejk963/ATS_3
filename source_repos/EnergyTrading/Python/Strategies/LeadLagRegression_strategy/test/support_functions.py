import numpy as np
import pandas as pd

from Math.lm_class import LinearModel, kalman, kalman1d, OnlineScoring
from Math.accumfeatures import MSTD
from sklearn.preprocessing import StandardScaler
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from sklearn.linear_model import LinearRegression
import statsmodels.api as sm
from sklearn.metrics import r2_score


###################################################################################################################
### functions calculating additional information used in strategy for each row of lag dataframe
def calculate_MACD(df_lag):
    # Extract date part from datetime for grouping
    df_lag['date'] = df_lag['datetime'].dt.date

    # Filtering the dataset to only include rows where trd_price is not null
    df_filtered = df_lag.dropna(subset=['trd_price'])

    # Function to calculate MACD for each group
    def calculate_macd(group):
        short_ema = group['trd_price'].ewm(span=12, adjust=False).mean()
        long_ema = group['trd_price'].ewm(span=26, adjust=False).mean()
        group['MACD'] = short_ema - long_ema
        return group

    # Apply the MACD calculation to each group (each day)
    df_filtered = df_filtered.groupby('date').apply(calculate_macd)

    # Merging the results back into the original dataset
    df_lag = df_lag.merge(df_filtered[['datetime', 'MACD']], on='datetime', how='left')
    df_lag['MACD'] = df_lag.groupby('date')['MACD'].ffill()

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


def calculate_regression_model_price(df_lead, df_lag, tau, tau_ema, n_days):
    # Filtering out only trades
    def deduplicate_trades(df):
        cols = df.columns
        #print(cols)

        df['pv'] = df['trd_price'] * df['volume']
        df = df.groupby('datetime').agg({
            'pv': 'sum',
            # 'trd_price': 'sum',    # Mean of 'trd_price'
            'volume': 'sum',  # Sum of 'volume'
            'bid_price': 'mean',  # Max of 'bid_price'
            'ask_price': 'mean',  # Min of 'ask_price'
            'mid_price': 'mean',  # Median of 'mid_price'
            # 'time_diff': 'std'      # Standard deviation of 'time_diff'
        })
        df['trd_price'] = df['pv'] / df['volume']

        return df

    data_lead_trds = deduplicate_trades(df_lead[df_lead['trd_price'].isnull() == False].set_index('datetime', inplace=False))
    data_lag_trds = deduplicate_trades(df_lag[df_lag['trd_price'].isnull() == False].set_index('datetime', inplace=False))

    data_lead_trds['tag'] = 'lead'
    data_lag_trds['tag'] = 'lag'

    df_trds = pd.concat([data_lead_trds, data_lag_trds]).sort_index()

    df_trds['lead_price'] = df_trds[['trd_price', 'tag']].apply(lambda row: row['trd_price'] if row['tag'] == 'lead' else None, axis=1)
    df_trds['lead_volume'] = df_trds[['volume', 'tag']].apply(lambda row: row['volume'] if row['tag'] == 'lead' else None, axis=1)
    df_trds['lead_pv'] = df_trds[['trd_price', 'volume', 'tag']].apply(lambda row: row['trd_price'] * row['volume'] if row['tag'] == 'lead' else None, axis=1)

    df_trds['lag_price'] = df_trds[['trd_price', 'tag']].apply(lambda row: row['trd_price'] if row['tag'] == 'lag' else None, axis=1)
    df_trds['lag_volume'] = df_trds[['volume', 'tag']].apply(lambda row: row['volume'] if row['tag'] == 'lag' else None, axis=1)
    df_trds['lag_pv'] = df_trds[['trd_price', 'volume', 'tag']].apply(lambda row: row['trd_price'] * row['volume'] if row['tag'] == 'lag' else None, axis=1)

    # Preparing tick data
    ti_cls = TR_class(tau, tau_ema)

    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'sum' for k in ['lead_volume', 'lead_pv', 'lag_volume', 'lag_pv']})

    df_trds['date'] = df_trds.index.date
    dates_list = sorted(list(set(df_trds['date'])))

    df_list = []
    df_list2 = []

    for current_day in dates_list:
        df_trds_1day = df_trds[df_trds['date'] == current_day]
        idx_series = ti_cls.tick_imbalance_indices(df_trds_1day.loc[:, 'lag_price'])
        # Create returns
        df_trds_indexed_1day = pd.concat([df_trds_1day.reindex(idx_series.index), idx_series], axis=1).reset_index()
        df_trds_indexed_1day['tick_id'] = str(current_day) + '_' + df_trds_indexed_1day[0].fillna(0).apply(str)
        df_trds_indexed_1day['datetime'] = df_trds_indexed_1day['index']
        df_trds_indexed_1day = df_trds_indexed_1day.set_index('datetime')
        df_trds_indexed_1day_grouped = df_trds_indexed_1day.groupby('tick_id').agg(
            agg_dict).reset_index().set_index('index')

        df_trds_indexed_1day_grouped['lead_price'] = df_trds_indexed_1day_grouped['lead_pv'] / \
                                                     df_trds_indexed_1day_grouped['lead_volume']
        df_trds_indexed_1day_grouped['lag_price'] = df_trds_indexed_1day_grouped['lag_pv'] / \
                                                    df_trds_indexed_1day_grouped['lag_volume']

        df_trds_indexed_1day_grouped['lead_log_ret'] = np.log(df_trds_indexed_1day_grouped['lead_price'].ffill() ).diff()
        df_trds_indexed_1day_grouped['lag_log_ret'] = np.log(df_trds_indexed_1day_grouped['lag_price'].ffill() ).diff()
        df_list.append(df_trds_indexed_1day_grouped)
        df_list2.append(df_trds_indexed_1day['tick_id'])

    df_trds_indexed = pd.concat(df_list).sort_index()
    df_trds = df_trds.merge(pd.concat(df_list2).sort_index(), left_index=True, right_index=True, how='left')

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

        # Skip if not enough data
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
        df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'coef1'] = 0.00001 #model.params[0]
        df_trds_indexed.loc[df_trds_indexed['date'] == current_day, 'coef2'] = 0.8661 #model.params[1]

    # Production predicted price
    df_trds['prev_tick_id']=df_trds['tick_id'].apply(lambda x: x.split('_')[0]+'_')+df_trds['tick_id'].apply(lambda x: str(float(x.split('_')[1])-1))
    df_trds_indexed['lead_price_tick']=df_trds_indexed['lead_price']
    df_trds_indexed['lag_price_tick']=df_trds_indexed['lag_price']
    df_trds_indexed['prev_tick_id']=df_trds_indexed['tick_id']

    df_trds=df_trds.reset_index().merge(df_trds_indexed[['prev_tick_id', 'lead_price_tick', 'lag_price_tick', 'coef1', 'coef2']], how='left', on='prev_tick_id')
    df_trds_lead=df_trds[df_trds['tag']=='lead']

    def predict_lag_price(lead_price_tick, lead_price, lag_price_tick, coef1, coef2):
        if all([lead_price_tick, lead_price, lag_price_tick, coef1, coef2]):
            return lag_price_tick*np.exp((coef1+coef2*np.log(lead_price/lead_price_tick)))
        else:
            return None

    df_trds_lead['lag_price_predicted']=df_trds_lead[['lead_price_tick', 'lead_price', 'lag_price_tick', 'coef1', 'coef2']].apply(lambda row: predict_lag_price(row['lead_price_tick'], row['lead_price'], row['lag_price_tick'], row['coef1'], row['coef2']), axis=1)
    df_trds_lead['lag_price_predicted_datetime']=df_trds_lead['datetime']

    data_lag=pd.merge_asof(df_lag,df_trds_lead[['datetime','lag_price_predicted','lag_price_predicted_datetime', 'lag_price_tick']], on='datetime', direction='backward')

    return data_lag