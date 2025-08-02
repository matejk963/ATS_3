import pandas as pd
import numpy as np
import pickle
import sys
import os

# Ensure the Utilities directory is in the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Try to import feature_engineering, handling the import in case it's run as a script
try:
    from . import feature_engineering
except ImportError:
    import feature_engineering

def detect_swing_points(ohlc_df: pd.DataFrame,
                        high_col: str = 'high',
                        low_col: str = 'low') -> pd.DataFrame:
    """
    Compute swing highs/lows based on the posted algorithm. Marks new extremes and recalculates opposite swing.
    Returns DataFrame with 'swing_high' and 'swing_low' columns.
    
    Parameters
    ----------
    ohlc_df : pd.DataFrame
        DataFrame containing OHLC data, must have columns 'open', 'high', 'low', 'close'
    high_col : str, optional
        Name of the column containing high prices, by default 'high'
    low_col : str, optional
        Name of the column containing low prices, by default 'low'
        
    Returns
    -------
    pd.DataFrame
        DataFrame with 'swing_high' and 'swing_low' columns, indexed the same as input
    """
    df = ohlc_df.copy().reset_index()
    df['min'] = np.nan
    df['max'] = np.nan
    for idx, row in df.iterrows():
        o, h, l, c = row['open'], row[high_col], row[low_col], row['close']
        if idx == 0:
            last_min = [idx, l]
            last_min2 = [idx, l]
            last_max = [idx, h]
            last_max2 = [idx, h]
            df.at[idx, 'min'] = l
            df.at[idx, 'max'] = h
            continue
        last_max_idx_diff = idx - last_max[0]
        last_min_idx_diff = idx - last_min[0]
        if last_max[1] < h:
            df.at[idx, 'max'] = h
            if last_max_idx_diff > 1:
                last_max2 = last_max
                last_max = [idx, h]
                slice_low = df.loc[last_max2[0]: last_max[0], low_col]
                new_min = slice_low.min()
                new_min_idx = slice_low.idxmin()
                last_min2 = last_min
                last_min = [new_min_idx, new_min]
                df.at[idx, 'min'] = new_min
            else:
                last_max = [idx, h]
        if last_min[1] > l:
            df.at[idx, 'min'] = l
            if last_min_idx_diff > 1:
                last_min2 = last_min
                last_min = [idx, l]
                slice_high = df.loc[last_min2[0]: last_min[0], high_col]
                new_max = slice_high.max()
                new_max_idx = slice_high.idxmax()
                last_max2 = last_max
                last_max = [new_max_idx, new_max]
                df.at[idx, 'max'] = new_max
            else:
                last_min = [idx, l]
    result = pd.DataFrame({'swing_high': df['max'].values,
                           'swing_low':  df['min'].values},
                          index=ohlc_df.index)
    return result

def generate_candles(df: pd.DataFrame,
                     price_col: str = 'price',
                     granularity: str = '5T') -> pd.DataFrame:
    """
    Resample trade price series into regular OHLC candles.
    """
    df2 = df.copy()
    df2[price_col] = pd.to_numeric(df2[price_col], errors='coerce')
    ohlc = df2.resample(granularity)[price_col]\
              .agg(['first', 'max', 'min', 'last'])
    ohlc.columns = ['open', 'high', 'low', 'close']
    return ohlc.dropna()

def generate_ohlc_for_timestamps(df: pd.DataFrame,
                                 price_col: str = 'price',
                                 datetime_col: str = 'datetime',
                                 granularity: str = '1H') -> pd.DataFrame:
    """
    Compute per-trade cumulative OHLC within each period:
      - 'open' is first price in period
      - 'high' = max so far, 'low' = min so far, 'close' = current price
    """
    df2 = df.copy()
    df2[price_col] = pd.to_numeric(df2[price_col], errors='coerce')
    df2['period'] = df2[datetime_col].dt.floor(granularity)
    def cum_ohlc(g):
        g2 = g.copy()
        g2['open']  = g2[price_col].expanding().apply(lambda x: x.iloc[0], raw=False)
        g2['high']  = g2[price_col].expanding().max()
        g2['low']   = g2[price_col].expanding().min()
        g2['close'] = g2[price_col]
        return g2
    return df2.groupby('period', group_keys=False).apply(cum_ohlc)

def compute_atr(df: pd.DataFrame,
                high_col: str = 'high',
                low_col: str = 'low',
                close_col: str = 'close',
                period: int = 14) -> pd.Series:
    """
    Compute ATR with first value as simple average, then Wilder smoothing.
    """
    high = df[high_col]
    low  = df[low_col]
    prev = df[close_col].shift()
    tr1 = high - low
    tr2 = (high - prev).abs()
    tr3 = (low  - prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # first ATR = simple rolling average over 'period'
    atr_init = tr.rolling(window=period, min_periods=period).mean()
    
    # Wilder smoothing for rest
    atr_smoothed = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    
    # combine: use simple average where available, else ewm
    atr = atr_init.combine_first(atr_smoothed)
    return atr

def compute_atr_from_candles(df: pd.DataFrame, 
                            candles: pd.DataFrame, 
                            period: int = 14) -> pd.DataFrame:
    """
    Compute ATR for each row using lookback from candles (excluding current period).
    
    Parameters:
    -----------
    df : DataFrame
        Trade data with either 'period' or 'datetime' column to determine current time
    candles : DataFrame
        OHLC candles with 'high', 'low', 'close' columns and datetime index
    period : int
        Number of periods to look back for ATR calculation
        
    Returns:
    --------
    DataFrame
        Copy of input df with added 'atr' column
    """
    # Ensure index is datetime for candles
    candles = candles.copy()
    candles.index = pd.to_datetime(candles.index)
    
    # Prepare result column
    atrs = []
    for idx, row in df.iterrows():
        curr_time = row['period'] if 'period' in row else row['datetime']
        
        # Get lookback window (exclude current period)
        lookback = candles.loc[candles.index < curr_time].tail(period)
        if len(lookback) < period:
            atrs.append(np.nan)
            continue
            
        prev_close = lookback['close'].shift(1)
        tr = pd.DataFrame({
            'high': lookback['high'],
            'low': lookback['low'],
            'prev_close': prev_close
        })
        tr['tr'] = tr.apply(lambda r: max(
            r['high'] - r['low'],
            abs(r['high'] - r['prev_close']) if not pd.isna(r['prev_close']) else 0,
            abs(r['low'] - r['prev_close']) if not pd.isna(r['prev_close']) else 0
        ), axis=1)
        atrs.append(tr['tr'].mean())
        
    df = df.copy()
    df['atr'] = atrs
    return df

# def detect_swing_points(ohlc_df: pd.DataFrame,
#                         high_col: str = 'high',
#                         low_col: str = 'low') -> pd.DataFrame:
#     """
#     Identify swing highs/lows on OHLC DataFrame.
#     """
#     df = ohlc_df.copy().reset_index()
#     df['swing_high'] = np.nan
#     df['swing_low']  = np.nan

#     # init
#     first_h = df.at[0, high_col]
#     first_l = df.at[0, low_col]
#     last_high = [0, first_h]
#     last_low  = [0, first_l]
#     df.at[0, 'swing_high'] = first_h
#     df.at[0, 'swing_low']  = first_l

#     for idx, row in df.iterrows():
#         if idx == 0:
#             continue
#         h = row[high_col]
#         l = row[low_col]
#         # new high?
#         if h > last_high[1]:
#             df.at[idx, 'swing_high'] = h
#             if idx - last_high[0] > 1:
#                 low_slice = df.loc[last_high[0]:idx, low_col]
#                 df.at[idx, 'swing_low'] = low_slice.min()
#             last_high = [idx, h]
#         # new low?
#         if l < last_low[1]:
#             df.at[idx, 'swing_low'] = l
#             if idx - last_low[0] > 1:
#                 high_slice = df.loc[last_low[0]:idx, high_col]
#                 df.at[idx, 'swing_high'] = high_slice.max()
#             last_low = [idx, l]

#     swings = df.set_index(df.columns[0])[['swing_high', 'swing_low']]
#     return swings.ffill()

def compute_atr_from_candles_vectorized(df: pd.DataFrame, 
                                       candles: pd.DataFrame, 
                                       period: int = 14) -> pd.DataFrame:
    """
    Compute ATR for each row using lookback from candles (excluding current period).
    Vectorized implementation for better performance.
    
    Parameters:
    -----------
    df : DataFrame
        Trade data with either 'period' or 'datetime' column to determine current time
    candles : DataFrame
        OHLC candles with 'high', 'low', 'close' columns and datetime index
    period : int
        Number of periods to look back for ATR calculation
        
    Returns:
    --------
    DataFrame
        Copy of input df with added 'atr' column
    """
    # Ensure index is datetime for candles
    candles = candles.copy()
    candles.index = pd.to_datetime(candles.index)
    
    # Compute true range for all candles at once
    prev_close = candles['close'].shift(1)
    candles['tr1'] = candles['high'] - candles['low']
    candles['tr2'] = (candles['high'] - prev_close).abs()
    candles['tr3'] = (candles['low'] - prev_close).abs()
    candles['tr'] = candles[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # Create a copy of df for results
    result_df = df.copy()
    
    # Determine which time column to use
    time_col = 'period' if 'period' in df.columns else 'datetime'
    
    # Calculate rolling ATR for each timestamp in df
    result_df['atr'] = result_df[time_col].apply(
        lambda curr_time: candles.loc[candles.index < curr_time, 'tr']
                               .tail(period)
                               .mean() if len(candles.loc[candles.index < curr_time]) >= period else np.nan
    )
    
    return result_df

def calculate_MACD(df_lag,
                   price_col: str = 'close',
                   se: int = 12,
                   le: int = 26,
                   cont: int = 9) -> pd.DataFrame:
    """
    Compute MACD (Moving Average Convergence Divergence).
    
    Returns a DataFrame indexed by datetime with columns:
      ['MACD', 'Signal', 'MACD_hist']
      
    Parameters:
    -----------
    df_lag : DataFrame
        Input DataFrame with price data
    price_col : str
        Name of the column containing price data (default: 'close')
    se : int
        Short EMA period (default: 12)
    le : int
        Long EMA period (default: 26)
    cont : int
        Signal line period (default: 9)
    """
    df = df_lag.copy()
    # ensure datetime column
    if 'datetime' not in df.columns:
        df = df.reset_index().rename(columns={'index':'datetime'})
    df = df.dropna(subset=[price_col])
    
    # MACD
    close = df[price_col]
    short_ema = close.ewm(span=se, adjust=False).mean()
    long_ema = close.ewm(span=le, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=cont, adjust=False).mean()
    hist = macd - signal
    
    # assemble output
    out = pd.DataFrame({
        'MACD': macd,
        'Signal': signal,
        'MACD_hist': hist
    })
    out.index = df['datetime']
    out.index.name = 'datetime'
    return out

def compute_macd_from_candles_vectorized(df: pd.DataFrame,
                                        candles: pd.DataFrame,
                                        se: int = 12,
                                        le: int = 26,
                                        cont: int = 9) -> pd.DataFrame:
    """
    Compute MACD for each row in df using lookback from candles (excluding current period).
    Vectorized implementation for better performance.
    
    Parameters:
    -----------
    df : DataFrame
        Trade data with either 'period' or 'datetime' column to determine current time
    candles : DataFrame
        OHLC candles with 'close' column and datetime index
    se : int
        Short EMA period (default: 12)
    le : int
        Long EMA period (default: 26)
    cont : int
        Signal line period (default: 9)
        
    Returns:
    --------
    DataFrame
        Copy of input df with added 'macd', 'signal', and 'macd_hist' columns
    """
    # Ensure index is datetime for candles
    candles = candles.copy()
    candles.index = pd.to_datetime(candles.index)
    
    # Precompute MACD on all available candle data
    # This won't be used directly, but helps with vectorization
    close = candles['close']
    short_ema = close.ewm(span=se, adjust=False).mean()
    long_ema = close.ewm(span=le, adjust=False).mean()
    candles['macd'] = short_ema - long_ema
    candles['signal'] = candles['macd'].ewm(span=cont, adjust=False).mean()
    candles['macd_hist'] = candles['macd'] - candles['signal']
    
    # Create a copy of df for results
    result_df = df.copy()
    
    # Determine which time column to use
    time_col = 'period' if 'period' in df.columns else 'datetime'
    
    # For each timestamp in df, calculate MACD using historical data up to that point
    def compute_macd_for_time(curr_time):
        # Get historical data up to but not including current period
        historical_data = candles.loc[candles.index < curr_time].copy()
        
        # If not enough data, return NaN
        if len(historical_data) < le:
            return pd.Series({'macd': np.nan, 'signal': np.nan, 'macd_hist': np.nan})
        
        # Return last computed values
        last_row = historical_data.iloc[-1]
        return pd.Series({
            'macd': last_row['macd'],
            'signal': last_row['signal'],
            'macd_hist': last_row['macd_hist']
        })
    
    # Apply computation to each row
    macd_values = result_df[time_col].apply(compute_macd_for_time)
    
    # Add results to the dataframe
    result_df['macd'] = macd_values['macd']
    result_df['signal'] = macd_values['signal']
    result_df['macd_hist'] = macd_values['macd_hist']
    
    return result_df

def combine_candles_with_latest_trades(
    candles: pd.DataFrame,
    latest_trades: pd.DataFrame,
    candle_granularity: str = '1h'
) -> pd.DataFrame:
    """
    Combine historical completed candles with the current evolving candle
    created from latest trades.
    
    Parameters:
    -----------
    candles : pd.DataFrame
        DataFrame with completed candles including columns: 'open', 'high', 'low', 'close'
        and datetime index
    latest_trades : pd.DataFrame
        DataFrame with latest trade data with 'price' column and datetime index
    candle_granularity : str
        Time granularity for candles (e.g. '1h', '5min', '15min')
        
    Returns:
    --------
    pd.DataFrame
        Combined DataFrame with historical candles and the current evolving candle
    """
    if candles.empty:
        return pd.DataFrame()
    
    # Make copies to avoid modifying original data
    candles = candles.copy()
    
    # Make sure we're working with datetime index
    candles.index = pd.to_datetime(candles.index)
    
    # If no latest trades, return the original candles
    if latest_trades.empty:
        return candles
    
    # Process latest trades
    latest_trades = latest_trades.copy()
    latest_trades.index = pd.to_datetime(latest_trades.index)
    
    # Determine the start time for the current evolving candle
    current_period_start = pd.Timestamp.now().floor(candle_granularity)
    
    # Filter trades that belong to the current period
    current_trades = latest_trades[latest_trades.index >= current_period_start]
    
    # If no trades in current period, return the original candles
    if current_trades.empty:
        return candles
    
    # Create the evolving candle
    current_open = current_trades['price'].iloc[0]
    current_high = current_trades['price'].max()
    current_low = current_trades['price'].min()
    current_close = current_trades['price'].iloc[-1]
    
    # Create a DataFrame for the evolving candle
    evolving_candle = pd.DataFrame(
        {
            'open': [current_open],
            'high': [current_high],
            'low': [current_low],
            'close': [current_close],
            'volume': [len(current_trades)]
        },
        index=[current_period_start]
    )
    
    # Append the evolving candle to historical candles
    combined_candles = pd.concat([candles, evolving_candle])
    
    return combined_candles

def compute_realtime_candles_per_trade(
    trades_df: pd.DataFrame,
    price_col: str = 'price',
    datetime_col: str = 'datetime',
    candle_granularity: str = '1h'
) -> pd.DataFrame:
    """
    Compute real-time OHLC data for each individual trade.
    
    For each trade, this function calculates what the current candle's OHLC would be
    at the exact moment of that trade, based on all trades within the same time period
    that occurred up to that point.
    
    Parameters:
    -----------
    trades_df : pd.DataFrame
        DataFrame containing trade data with datetime and price information
    price_col : str
        Name of the column containing price data (default: 'price')
    datetime_col : str
        Name of the column containing datetime data (default: 'datetime')
    candle_granularity : str
        Time granularity for candles (e.g., '1h', '15min', '5min')
        
    Returns:
    --------
    pd.DataFrame
        Original DataFrame with added columns:
        - 'period': start time of the candle period this trade belongs to
        - 'candle_open': open price of the current candle period
        - 'candle_high': highest price in the current candle period up to this trade
        - 'candle_low': lowest price in the current candle period up to this trade
        - 'candle_close': this trade's price (current close)
        - 'candle_volume': number of trades in the current candle period up to this trade
    """
    # Make a copy to avoid modifying the original DataFrame
    df = trades_df.copy()
    
    # Ensure datetime column is datetime type
    df[datetime_col] = pd.to_datetime(df[datetime_col])
    
    # Convert price column to numeric if it's not already
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    
    # Add candle period column
    df['period'] = df[datetime_col].dt.floor(candle_granularity)
    
    # Initialize OHLC columns
    df['candle_open'] = np.nan
    df['candle_high'] = np.nan
    df['candle_low'] = np.nan
    df['candle_close'] = df[price_col]  # Each trade's price is the current close
    df['candle_volume'] = np.nan
    
    # Process each candle period group
    result_dfs = []
    
    # Process each period separately
    for period, group in df.groupby('period'):
        # Sort by datetime within the period
        group = group.sort_values(by=datetime_col)
        
        # Get the first price as the open for the entire period
        period_open = group[price_col].iloc[0]
        
        # Apply expanding calculations for each row in the period
        group['candle_open'] = period_open  # Same open for all trades in this period
        group['candle_high'] = group[price_col].expanding().max()
        group['candle_low'] = group[price_col].expanding().min()
        # close is already set to the current price
        group['candle_volume'] = range(1, len(group) + 1)  # Count of trades up to this point
            
        result_dfs.append(group)
    
    # Combine all processed periods back together
    result = pd.concat(result_dfs)
    
    # Sort by the original datetime
    result = result.sort_values(by=datetime_col)
    
    return result

def pair_trade_with_historical_lookback(
    trades_df: pd.DataFrame,
    historical_candles: pd.DataFrame,
    lookback_periods: int = 30,
    price_col: str = 'price',
    datetime_col: str = 'datetime',
    candle_granularity: str = '1h',
    candle_col: str = 'close'
) -> pd.DataFrame:
    """
    Pair each trade with historical lookback data from completed candles.
    
    Simplified function that only shifts candles and merges them with the trades dataframe.
    
    Parameters:
    -----------
    trades_df : pd.DataFrame
        DataFrame containing trade data with datetime and price information
    historical_candles : pd.DataFrame
        DataFrame with historical completed candles with 'open', 'high', 'low', 'close' columns
        and datetime index
    lookback_periods : int
        Number of historical candle periods to include in lookback (default: 30)
    price_col : str
        Name of the column containing price data (default: 'price')
    datetime_col : str
        Name of the column containing datetime data (default: 'datetime')
    candle_granularity : str
        Time granularity for candles (e.g., '1h', '15min', '5min')
    candle_col : str
        Name of the column in historical_candles to use for lookback data (default: 'close')
        
    Returns:
    --------
    pd.DataFrame
        Original DataFrame with added columns:
        - 'period': start time of the candle period this trade belongs to
        - 'close_t' (current trade close price)
        - 'close_t-1', 'close_t-2', ..., 'close_t-n': Historical prices
          for each lookback period (where n is lookback_periods)
    """
    # Make a copy of the trades dataframe
    df = trades_df.copy()
    
    # Ensure datetime column is datetime type
    df[datetime_col] = pd.to_datetime(df[datetime_col])
    
    # Add candle period column
    df['period'] = df[datetime_col].dt.floor(candle_granularity)
    
    # Ensure candles index is datetime and sorted
    candles = historical_candles.copy()
    if not isinstance(candles.index, pd.DatetimeIndex):
        candles.index = pd.to_datetime(candles.index)
    candles = candles.sort_index()
    
    # Ensure the requested candle column exists
    if candle_col not in candles.columns:
        raise ValueError(f"Column '{candle_col}' not found in historical_candles DataFrame. Available columns: {candles.columns.tolist()}")
    
    # Shift the data so each value correctly represents the past value
    # Create a dictionary of shifted series for each lookback period
    shifted_data = {f'close_t-{i}': candles[candle_col].shift(i) 
                   for i in range(1, lookback_periods + 1)}
    
    # Create a DataFrame with all the shifted data
    close_histories = pd.DataFrame(shifted_data)
    
    # Reorder columns from oldest to most recent
    cols = [f'close_t-{i}' for i in range(lookback_periods, 0, -1)]
    close_histories = close_histories[cols]
    
    # Direct merge of historical data with trades using join
    history_df = pd.merge(
        df,
        close_histories, 
        left_on='period',
        right_index=True,
        how='left'
    )
    
    # Add current trade price as close_t
    history_df['close_t'] = df[price_col]
    
    # Fill any missing values with NaN
    result = history_df.fillna(np.nan)
    
    return result

def compute_realtime_atr(
    trades_df: pd.DataFrame,
    historical_candles: pd.DataFrame,
    atr_period: int = 14,
    price_col: str = 'price',
    datetime_col: str = 'datetime',
    candle_granularity: str = '1h'
) -> pd.DataFrame:
    """
    Compute real-time ATR (Average True Range) for each trade based on historical candles
    and the evolving candle formed by real-time trades.
    
    The function follows these steps:
    1. Takes trades DataFrame and computes real-time candles for each trade
    2. Adds last close from historical data using lookback=1
    3. Calculates true range for each trade using current OHLC and previous close
    4. Calculates true range in historical candles
    5. Merges true ranges from trades with true ranges from candles
    6. Computes ATR as rolling average of true ranges
    
    Parameters:
    -----------
    trades_df : pd.DataFrame
        DataFrame containing trade data with datetime and price information
    historical_candles : pd.DataFrame
        DataFrame with historical completed candles with 'open', 'high', 'low', 'close' columns
        and datetime index
    atr_period : int
        Number of periods to use for ATR calculation (default: 14)
    price_col : str
        Name of the column containing price data (default: 'price')
    datetime_col : str
        Name of the column containing datetime data (default: 'datetime')
    candle_granularity : str
        Time granularity for candles (e.g., '1h', '15min', '5min')
    
    Returns:
    --------
    pd.DataFrame
        Original trades DataFrame with added columns:
        - Real-time candle data (candle_open, candle_high, candle_low, candle_close)
        - 'prev_close': Previous candle's close price
        - 'true_range': True range for each trade
        - 'atr': ATR value for each trade
    """
    # Step 1: Compute real-time candles for each trade
    trades_with_candles = compute_realtime_candles_per_trade(
        trades_df=trades_df,
        price_col=price_col,
        datetime_col=datetime_col,
        candle_granularity=candle_granularity
    )
    
    # Step 2: Use pair_trade_with_historical_lookback to add previous close (lookback_periods = 1)
    trades_with_history = pair_trade_with_historical_lookback(
        trades_df=trades_with_candles,
        historical_candles=historical_candles,
        lookback_periods=1,
        price_col=price_col,
        datetime_col=datetime_col,
        candle_granularity=candle_granularity,
        candle_col='close'
    )
    
    # Rename the column for clarity
    trades_with_history = trades_with_history.rename(columns={'close_t-1': 'prev_close'})
    
    # Step 3: Calculate true range for each trade using current OHLC and previous close
    def calculate_true_range(row):
        high_low = row['candle_high'] - row['candle_low']
        
        # If there's no previous close, just use high-low
        if pd.isna(row['prev_close']):
            return high_low
        
        high_prev_close = abs(row['candle_high'] - row['prev_close'])
        low_prev_close = abs(row['candle_low'] - row['prev_close'])
        
        return max(high_low, high_prev_close, low_prev_close)
    
    trades_with_history['true_range'] = trades_with_history.apply(calculate_true_range, axis=1)
    
    # Step 4: Calculate true range in historical candles
    candles = historical_candles.copy()
    if not isinstance(candles.index, pd.DatetimeIndex):
        candles.index = pd.to_datetime(candles.index)
    
    # Calculate true range for historical candles
    candles['prev_close'] = candles['close'].shift(1)
    candles['true_range'] = candles.apply(
        lambda row: max(
            row['high'] - row['low'],
            abs(row['high'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0,
            abs(row['low'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0
        ),
        axis=1
    )
    
    # Create a series of all true ranges (from historical candles and current trades)
    # Step 5: Merge true ranges from trades with true ranges from candles
    result = pair_trade_with_historical_lookback(
        trades_df=trades_with_history[['period', datetime_col, 'true_range']],
        historical_candles=candles[['true_range']],
        lookback_periods=atr_period,  # Use the same period for ATR calculation
        price_col='true_range',  # Use true_range as the price column
        datetime_col=datetime_col,
        candle_granularity=candle_granularity,
        candle_col='true_range'
    )

    result = result.drop(columns=['period', 'true_range'], errors='ignore')  # Remove if exists
    result = result.set_index(datetime_col)  # Ensure datetime index
    result['atr'] = result.mean(axis=1)  # Initialize ATR with NaN

    # insert daetetime,nanotime and tradeid back to atr
    result = result[['atr']].reset_index().merge(trades_df[[datetime_col, 'nanotime', 'tradeid']], on=datetime_col, how='left')
    
    
    
    return result[['datetime', 'nanotime', 'tradeid', 'atr']]

def compute_realtime_macd(
    trades_df: pd.DataFrame,
    historical_candles: pd.DataFrame,
    se: int = 12,  # Short EMA period
    le: int = 26,  # Long EMA period
    signal_period: int = 9,  # Signal line period
    price_col: str = 'price',
    datetime_col: str = 'datetime',
    candle_granularity: str = '1h'
) -> pd.DataFrame:
    """
    Compute real-time MACD (Moving Average Convergence Divergence) for each trade based on historical candles
    and the evolving candle formed by real-time trades.
    
    The function follows these steps:
    1. Gets real-time candles from trades
    2. Calculates OHLC mean for real-time candles
    3. Calculates OHLC mean for historical candles
    4. Uses pair_trade_with_historical_lookback for each moving average length
    5. Calculates moving averages and combines them to get MACD, signal line, and histogram
    
    Parameters:
    -----------
    trades_df : pd.DataFrame
        DataFrame containing trade data with datetime and price information
    historical_candles : pd.DataFrame
        DataFrame with historical completed candles with 'open', 'high', 'low', 'close' columns
        and datetime index
    se : int
        Short EMA period (default: 12)
    le : int
        Long EMA period (default: 26)
    signal_period : int
        Signal line period (default: 9)
    price_col : str
        Name of the column containing price data (default: 'price')
    datetime_col : str
        Name of the column containing datetime data (default: 'datetime')
    candle_granularity : str
        Time granularity for candles (e.g., '1h', '15min', '5min')
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with columns:
        - 'datetime': Trade datetime
        - 'nanotime': Trade nanotime (if present in original data)
        - 'tradeid': Trade ID (if present in original data)
        - 'macd': MACD line values
        - 'signal': Signal line values
        - 'histogram': Histogram values (MACD - Signal)
    """
    # Step 1: Compute real-time candles for each trade
    trades_with_candles = compute_realtime_candles_per_trade(
        trades_df=trades_df,
        price_col=price_col,
        datetime_col=datetime_col,
        candle_granularity=candle_granularity
    )
    
    # Step 2: Calculate OHLC mean for real-time candles
    trades_with_candles['ohlc_mean'] = (
        trades_with_candles['candle_open'] + 
        trades_with_candles['candle_high'] + 
        trades_with_candles['candle_low'] + 
        trades_with_candles['candle_close']
    ) / 4
      # Step 3: Calculate OHLC mean for historical candles without creating a full copy
    # Ensure index is datetime
    if not isinstance(historical_candles.index, pd.DatetimeIndex):
        historical_candles.index = pd.to_datetime(historical_candles.index)
    
    # Create a view with only the columns we need and add OHLC mean
    hist_candles_view = pd.DataFrame(index=historical_candles.index)
    hist_candles_view['ohlc_mean'] = (
        historical_candles['open'] + 
        historical_candles['high'] + 
        historical_candles['low'] + 
        historical_candles['close']
    ) / 4
    
    # Step 4: Use pair_trade_with_historical_lookback for short EMA data
    short_ema_data = pair_trade_with_historical_lookback(
        trades_df=trades_with_candles[['period', datetime_col, 'ohlc_mean']],
        historical_candles=hist_candles_view,
        lookback_periods=se,  # Use the short EMA period
        price_col='ohlc_mean',
        datetime_col=datetime_col,
        candle_granularity=candle_granularity,
        candle_col='ohlc_mean'
    )
      # Step 5: Use pair_trade_with_historical_lookback for long EMA data
    long_ema_data = pair_trade_with_historical_lookback(
        trades_df=trades_with_candles[['period', datetime_col, 'ohlc_mean']],
        historical_candles=hist_candles_view,  # Reuse the view we created above
        lookback_periods=le,  # Use the long EMA period
        price_col='ohlc_mean',
        datetime_col=datetime_col,
        candle_granularity=candle_granularity,
        candle_col='ohlc_mean'
    )
    
    # Calculate short EMA - removing period and ohlc_mean columns
    short_ema_cols = [col for col in short_ema_data.columns if col.startswith('close_t')]
    short_ema = short_ema_data[short_ema_cols].mean(axis=1)
    
    # Calculate long EMA - removing period and ohlc_mean columns
    long_ema_cols = [col for col in long_ema_data.columns if col.startswith('close_t')]
    long_ema = long_ema_data[long_ema_cols].mean(axis=1)
    
    # Calculate MACD line
    macd_line = short_ema - long_ema
    
    # Create a DataFrame with the MACD line to use for signal line calculation
    macd_df = pd.DataFrame({
        'period': trades_with_candles['period'],
        datetime_col: trades_with_candles[datetime_col],
        'macd': macd_line
    })

    macd_candles = pd.DataFrame({'period': macd_df['period'],
                                 'macd': macd_line})
    macd_candles = macd_candles.groupby('period').last().reset_index()
    
    # Now use pair_trade_with_historical_lookback for signal line
    signal_data = pair_trade_with_historical_lookback(
        trades_df=macd_df,
        historical_candles=macd_candles.set_index('period'),
        lookback_periods=signal_period,
        price_col='macd',
        datetime_col=datetime_col,
        candle_granularity=candle_granularity,
        candle_col='macd'
    )
    
    # Calculate signal line
    signal_cols = [col for col in signal_data.columns if col.startswith('close_t')]
    signal_line = signal_data[signal_cols].mean(axis=1)
    
    # Calculate histogram (MACD - Signal)
    histogram = macd_line - signal_line
    
    # Create final result DataFrame
    result = pd.DataFrame({
        datetime_col: trades_with_candles[datetime_col],
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    })
    
    # Add tradeid and nanotime if they exist in the original DataFrame
    if 'nanotime' in trades_df.columns:
        result = pd.merge(result, trades_df[[datetime_col, 'nanotime']], on=datetime_col, how='left')
    
    if 'tradeid' in trades_df.columns:
        result = pd.merge(result, trades_df[[datetime_col, 'tradeid']], on=datetime_col, how='left')
    
    # Ensure columns are in the desired order
    columns = [datetime_col]
    if 'nanotime' in result.columns:
        columns.append('nanotime')
    if 'tradeid' in result.columns:
        columns.append('tradeid')
    columns.extend(['macd', 'signal', 'histogram'])
    
    return result[columns].rename(columns={'histogram': 'hist'})



if __name__ == "__main__":
    # Test the implementation of pair_trade_with_historical_lookback and technical analysis
    import pickle
    import time
    
    # Paths to pickle files
    candles_path = r"C:\Users\krajcovic\Documents\Testing Data\macd_levels backup\monthly_candles_5m_dem1_dem2_20250101_20250522.pkl"
    trades_path = r"C:\Users\krajcovic\Documents\Testing Data\macd_levels backup\monthly_data_20250101_20250522.pkl"
    
    print("Loading pickle data...")
    # Load data from pickle files
    with open(candles_path, 'rb') as f:
        hist_candles_dict = pickle.load(f)
    with open(trades_path, 'rb') as f:
        trades_dict = pickle.load(f)
    
    # Use March 2025 data for testing
    month_key = '2025-03'
    hist_candles = hist_candles_dict[month_key]
    trades = trades_dict[month_key].reset_index()
    
    # Make sure historical candles have a datetime index
    if not isinstance(hist_candles.index, pd.DatetimeIndex):
        hist_candles.index = pd.to_datetime(hist_candles.index)
    
    # Display sample data
    print("\nSample historical candles:")
    print(hist_candles.tail(3))
    print("\nSample trades:")
    print(trades.head(3))
    
    # Measure performance
    start_time = time.time()
    
    # Test the pair_trade_with_historical_lookback function
    print("\nRunning pair_trade_with_historical_lookback...")
    result = pair_trade_with_historical_lookback(
        trades_df=trades,
        historical_candles=hist_candles,
        lookback_periods=5,  # Use 5 periods for testing
        candle_granularity='5min'  # Match the 5-minute candles in the data
    )
    
     # Test the compute_realtime_atr function
    print("\nCalculating real-time ATR...")
    atr_result = compute_realtime_atr(
        trades_df=trades,
        historical_candles=hist_candles,
        atr_period=14,
        price_col='price',
        datetime_col='datetime',
        candle_granularity='1h'
    )
    
    print("\nATR results (last 3 trades):")
    print(atr_result.tail(3)[['datetime', 'atr']])
    
    # Test the compute_realtime_macd function
    print("\nCalculating real-time MACD...")
    macd_result = compute_realtime_macd(
        trades_df=trades,
        historical_candles=hist_candles,
        se=12,
        le=26,
        signal_period=9,
        price_col='price',
        datetime_col='datetime',
        candle_granularity='1h'
    )
    
    print("\nMACD results (last 3 trades):")
    print(macd_result.tail(3)[['datetime', 'macd', 'signal', 'histogram']])
    
    # Test the detect_swing_points function
    print("\nCalculating swing points...")
    # First, generate some candles with a suitable timeframe
    hourly_candles = generate_candles(trades, granularity='1h')
    swing_points = detect_swing_points(hourly_candles)
    
    print("\nSwing points results (first 5 rows):")
    print(swing_points.head(5))
    
    end_time = time.time()
    print(f"\nExecution time: {end_time - start_time:.2f} seconds")



