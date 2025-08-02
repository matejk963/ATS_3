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

STORAGE_ = get_curr_storage_path()
l_path = STORAGE_ + 'Data/orderbooks/base/'

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


if __name__ == '__main__':
    dates_out = conn_out_xload_mac()
    allwd_broker_ids = [1441]

    # ------------------ dataset prep ---------------------------------

    # Load arguments
    _INSTRUMENTS = ['dem1', 'dem2', 'dem3','deq1', 'deq2', 'deq3', 'dey1', 'dey2', 'frm1', 'frm2', 'frq1', 'frq2', 'fry1']
    _START_DATE, _END_DATE = '2025-01-01', '2025-01-07'
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
    de_trades = data_class.get_trades_inst('de', venue_list, start_date, end_date, prod='base', spread_bool=False)
    de_ts = de_trades[de_trades.eval('broker_id==1441')].index.drop_duplicates()
    fr_trades = data_class.get_trades_inst('de', venue_list, start_date, end_date, prod='base', spread_bool=False)
    fr_ts = fr_trades[fr_trades.eval('broker_id==1441')].index.drop_duplicates()
    
    instrument_ts = de_ts.union(fr_ts)


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




df_instruments = pd.DataFrame({}, index=instrument_ts)
for key, df in df_trades.items():
    df_temp = df.reindex(instrument_ts)['price']
    if (df_temp > 0).sum() < 1:
        # Project the forward-filled values from frm1 onto instrument_ts
        projected_prices = df.reindex(df.index.union(instrument_ts))['price'].ffill().reindex(instrument_ts)

        # Create a mask that identifies the first occurrence of each forward-filled value
        first_occurrence_mask = projected_prices != projected_prices.shift(1)

        # Apply the mask to keep only the first occurrence of each forward-filled value
        df_temp = projected_prices.where(first_occurrence_mask)
    df_temp.name = 'price_' + key

    df_instruments = pd.concat([df_instruments, df_temp], axis=1)



def consecutive_true_counter(bool_array):
    # Create output array with same shape as input
    result = np.zeros_like(bool_array, dtype=int)
    
    # Process each column independently
    for col in range(bool_array.shape[1]):
        counter = 0
        for row in range(bool_array.shape[0]):
            if bool_array[row, col]:
                counter += 1
                result[row, col] = counter
            else:
                counter = 0
                result[row, col] = 0
    
    return result


# Weights Matrix <- for i in trades if j is nan -> W_m[i-1][j]++
# Price trades ffill()
# orders (max(80.0 - trade, 0)) + (min(80.1- trade, 0))
# target next trade price


df_instruments = pd.DataFrame({}, index=instrument_ts)
for key, df in df_trades.items():
    df_temp = df.reindex(instrument_ts)['price']
    if (df_temp > 0).sum() < 1:
        # Project the forward-filled values from df onto instrument_ts
        projected_prices = df.reindex(df.index.union(instrument_ts))['price'].ffill().reindex(instrument_ts)
        # Create a mask that identifies the first occurrence of each forward-filled value
        first_occurrence_mask = projected_prices != projected_prices.shift(1)
        # Apply the mask to keep only the first occurrence of each forward-filled value
        df_temp = projected_prices.where(first_occurrence_mask)
    df_temp.name = 'price_' + key
    df_instruments = pd.concat([df_instruments, df_temp], axis=1)

# Now add the function calculations for each instrument
for key, df in df_trades.items():
    # Get corresponding order book data
    orders = df_orders[key]
    
    # Align orders with all trade timestamps (both in df_trades and instrument_ts)
    aligned_orders = orders.reindex(orders.index.union(instrument_ts))
    
    # Forward fill missing values (since we want the most recent order book state for each trade)
    aligned_orders = aligned_orders.ffill()
    
    # Reindex to only include the trade timestamps we care about
    aligned_orders = aligned_orders.reindex(instrument_ts)
    
    # Get the trade prices (already calculated above)
    trade_prices = df_instruments['price_' + key].ffill()
    
    # Calculate the function for each timestamp where we have both order and trade data
    func_values = pd.Series(index=instrument_ts, dtype=float)
    mask = (~trade_prices.isna()) & (~aligned_orders['b_price'].isna()) & (~aligned_orders['a_price'].isna())
    
    # Only calculate where we have all required data
    if mask.any():
        # Fix: Use 'min' and 'max' for NumPy arrays instead of 'lower' and 'upper'
        bid_diff = aligned_orders.loc[mask, 'b_price'].values - trade_prices[mask].values
        ask_diff = aligned_orders.loc[mask, 'a_price'].values - trade_prices[mask].values
        
        func_values[mask] = np.maximum(bid_diff, 0) + np.minimum(ask_diff, 0)
    
    # Add the calculated function values to our results dataframe
    func_values.name = 'func_' + key
    df_instruments = pd.concat([df_instruments, func_values], axis=1)



def get_target_for_ins(df_instruments, instrument):
    price_column = f'price_{instrument}'
    if price_column not in df_instruments.columns:
        raise ValueError(f"Column {price_column} not found in DataFrame")
    
    # Return raw values without any filling
    target_series = df_instruments[price_column]
    target_series.name = f'y_{instrument}'
    
    return target_series



def ridge_regression(X, y, lambda_value=100.0):
    """Robust implementation of ridge regression"""
    # Add intercept column
    X_with_intercept = np.hstack([np.ones((X.shape[0], 1)), X])
    
    # Get dimensions
    n_samples, n_features = X_with_intercept.shape
    
    # Create identity matrix for regularization
    identity = np.identity(n_features)
    identity[0, 0] = 0  # Don't penalize intercept
    
    # Compute matrices
    XtX_plus_lambda = X_with_intercept.T.dot(X_with_intercept) + lambda_value * identity
    Xty = X_with_intercept.T.dot(y)
    
    # Try multiple approaches with increasing robustness
    try:
        # Try direct solve first (fastest)
        coefs = np.linalg.solve(XtX_plus_lambda, Xty)
    except np.linalg.LinAlgError:
        try:
            # Try SVD-based least squares
            coefs, _, _, _ = np.linalg.lstsq(XtX_plus_lambda, Xty, rcond=1e-10)
        except np.linalg.LinAlgError:
            # Last resort: manual pseudo-inverse with conditioning
            u, s, vh = np.linalg.svd(XtX_plus_lambda, full_matrices=False)
            # Filter small singular values
            s_inv = np.where(s > 1e-10 * s[0], 1.0 / s, 0.0)
            coefs = vh.T @ (s_inv[:, np.newaxis] * u.T) @ Xty
    
    # Extract intercept and coefficients
    intercept = coefs[0]
    weights = coefs[1:]
    
    return weights, intercept

def simple_ridge_regression(X, y, lambda_value=1.0):
    # Adjust target by subtracting the intercept
    # This makes the regression predict the residual (y - A)
    
    n_features = X.shape[1]
    identity = np.eye(n_features)
    
    try:
        # No need for an intercept column in X since we're using A directly
        XtX_plus_lambda = X.T @ X + lambda_value * identity
        Xty = X.T @ y
        coefs = np.linalg.solve(XtX_plus_lambda, Xty)
    except np.linalg.LinAlgError:
        # Fallback to pseudo-inverse if matrix is singular
        coefs = np.linalg.pinv(XtX_plus_lambda) @ Xty
    
    return coefs


def constrained_coefficient_model_with_lastprice_features(X, W_m, D, y, window_size=200, lambda_value=1.0, mask_thold=5):
    n_samples, n_features = X.shape
    test_size = n_samples - window_size
    predictions = np.full(test_size, np.nan)
    
    # For tracking coefficients
    # Track valid windows per instrument
    valid_windows = 0
    fallback_count = 0
    
    for i in range(test_size):
        # Define window
        start_idx = i
        end_idx = i + window_size
        
        target_mask = y[start_idx:end_idx].values > 0
        y_masked = y[start_idx:end_idx].values[target_mask]
        y_window = (y_masked - np.roll(y_masked, 1))[1:]
        # Get window data
        X_window = X[start_idx:end_idx].copy()[target_mask][1:]
        W_m_window = W_m[start_idx:end_idx].copy()[target_mask][1:]
        D_window = D[start_idx:end_idx].copy()[target_mask][1:]
        
        X_comb = X_window * W_m_window
        
        if target_mask.sum() < mask_thold:
            predictions[i] = 0.0
            continue
        # Create feature matrix - include all features plus last price
        features = np.hstack([X_comb, D_window])

        # Use Ridge Regression with higher regularization
        coef = simple_ridge_regression(features, y_window, lambda_value=0.05)
    
        # Predict next sample
        next_idx = end_idx
        if next_idx < n_samples:
            features_next = np.hstack([
                X[next_idx]*W_m[next_idx].reshape(1, -1),
                D[next_idx].reshape(1, -1)])
            intercept = y_masked[-1]
            # Make prediction using our coefficients
            predictions[i] = np.dot(features_next, coef) + intercept
        valid_windows += 1
    

        
        if (i+1) % 1000 == 0:
            print(f"Processed {i+1}/{test_size} samples")

    return predictions



def fast_historical_non_nan_rolling_mean(series, window_size=3):
    # Create a series with only non-NaN values
    valid_data = series.dropna()
    
    # For each index in the original series, find the mean of the 
    # last 'window_size' non-NaN values that occurred before it
    result = pd.Series(index=series.index, dtype=float)
    
    for idx in series.index:
        # Get historical valid data
        historical_valid = valid_data.loc[:idx].iloc[:-1]
        
        # Calculate mean of last n values
        if len(historical_valid) > 0:
            result.loc[idx] = historical_valid.tail(window_size).mean()
    
    return result

price_columns = [col for col in df_instruments.columns if col.startswith('price_')]
func_columns = [col for col in df_instruments.columns if col.startswith('func_')]

w_scaler = lambda row: 1 - (np.minimum(100, row)/np.minimum(100, row).max())
df_instruments['day'] = df_instruments.index.day
fair_price = pd.DataFrame({'fair_price': np.full(df_instruments.index.shape[0], np.nan)}, index=df_instruments.index)
for instrument in _INSTRUMENTS:

    for day in df_instruments['day'].unique():
        print(f"\nProcessing {instrument}")
        target_instrument = instrument
        # target_instrument = column.split('_')[-1]
        day_idx = df_instruments[df_instruments['day'] == day].index
        y = get_target_for_ins(df_instruments[df_instruments['day'] == day], target_instrument)
        mask = df_instruments.reindex(y.index)[price_columns].values > 0
        W_m = consecutive_true_counter(~mask)
        W_m = np.apply_along_axis(w_scaler, 0, W_m)
        D = df_instruments.reindex(y.index)['func_' + target_instrument].fillna(0.0).values.reshape(-1, 1)
        X = df_instruments.reindex(y.index)[price_columns]
        X.iloc[0] = df_instruments[df_instruments['day'] == day][price_columns].mean().fillna(0)
        X_fill = X.ffill()
        change_mask = X_fill.diff(1).ffill().abs() > 0.001
        X[change_mask] = X_fill.diff(1).ffill()[change_mask]
        X[X > 10.0] = 0.0
        X = X.ffill().values
    
    
        w_size = 500
        predictions = constrained_coefficient_model_with_lastprice_features(X, W_m, D, y,window_size=w_size, lambda_value=1.0)
        fair_price.loc[day_idx, instrument] = pd.Series(np.concatenate([np.full(w_size, np.nan), predictions]), index=day_idx)
    
    # from sklearn.metrics import r2_score
    # import matplotlib.pyplot as plt

    # window_size = 3

    # # Right shift the rolling mean by 1 to ensure we only use past data
    # lagged_rolling_mean = fast_historical_non_nan_rolling_mean(df_instruments.reindex(y.index)['price_' + target_instrument])
    # lagged_rolling_mean = lagged_rolling_mean[w_size:]
    # # Remove NaN values for R² calculation
    # valid_mask = ~np.isnan(lagged_rolling_mean)
    # y_valid = y[w_size:][valid_mask]
    # predictions_valid = predictions[valid_mask]
    # lagged_mean_valid = lagged_rolling_mean[valid_mask]

    # # Calculate R² using properly lagged rolling mean
    # ss_total = np.sum((y_valid - lagged_mean_valid)**2)
    # ss_residual = np.sum((y_valid - predictions_valid)**2)
    # r2_rolling = 1 - (ss_residual / ss_total)

    # plt.Figure()
    # x = np.arange(1000)
    # plt.plot(x, y[w_size:1500].values, label='y_true')
    # plt.plot(x, predictions[:1000], label='pred')
    # plt.plot(x, lagged_rolling_mean[:1000], label='naive')
    # plt.legend()
    # plt.show()
    # print("Instrument", target_instrument, 'R2', r2_rolling)


def calc_ev(df_trades):
    bin_edges = np.arange(-1.0, 1.05, 0.05)  # Adding 0.05 to include 1.0 as the
    histograms = []
    for i, row in df_trades.reset_index().iterrows():
        curr_price = row['trd_price']
        try:
            data = df_trades['trd_price'].values[i:i+100]
        except IndexError:
            break
        data = data - curr_price
        counts, _ = np.histogram(data, bins=bin_edges, density=False)
        probabilities = counts / np.sum(counts)
        histograms.append(probabilities)

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    EV = [np.sum(bin_centers * probabilities) for probabilities in histograms]

    return EV