import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf

def generate_random_candles(num_candles=60, start_price=100.0, seed=None):
    """
    Create random OHLC data for demonstration.
    """
    if seed is not None:
        np.random.seed(seed)

    dates = pd.date_range("2023-01-01", periods=num_candles, freq="D")

    # Simple random walk for close
    returns = np.random.normal(loc=0.0, scale=0.02, size=num_candles)
    close_prices = [start_price]
    for ret in returns[1:]:
        close_prices.append(close_prices[-1] * (1 + ret))
    close_prices = np.array(close_prices)

    # Build OHLC from close
    opens = close_prices * (1 + np.random.normal(0, 0.005, size=num_candles))
    highs = np.maximum(opens, close_prices) * (1 + np.random.uniform(0.0001, 0.01, size=num_candles))
    lows  = np.minimum(opens, close_prices) * (1 - np.random.uniform(0.0001, 0.01, size=num_candles))
    volumes = np.random.randint(100, 2000, size=num_candles)

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": close_prices,
        "Volume": volumes
    }, index=dates)
    return df

def find_local_extrema(series, find_min=True):
    """
    Find local minima (if find_min=True) or maxima (if find_min=False) in a timeseries.
    Returns a Series with extrema values, datetime index, and no NaNs.
    """
    values = series.values
    index = series.index
    n = len(values)
    
    if n < 3:  # Need at least 3 points for neighbor comparison
        return pd.Series([], index=pd.DatetimeIndex([]))
    
    # Compare with neighbors
    if find_min:
        is_extrema = (values < np.roll(values, -1)) & (values < np.roll(values, 1))
    else:
        is_extrema = (values > np.roll(values, -1)) & (values > np.roll(values, 1))
    
    is_extrema[0] = is_extrema[-1] = False
    return pd.Series(values[is_extrema], index=index[is_extrema])

def filter_most_extreme(low_minima, high_maxima, df):
    """
    Keep only the most extreme minima (lowest Low) and maxima (highest High)
    up to each extremum's datetime.
    Returns two Series: filtered minima and maxima.
    """
    # Convert to list of (datetime, value, type)
    extrema = []
    for dt, val in low_minima.items():
        extrema.append((dt, val, 'min'))
    for dt, val in high_maxima.items():
        extrema.append((dt, val, 'max'))
    
    if not extrema:
        return pd.Series([], index=pd.DatetimeIndex([])), pd.Series([], index=pd.DatetimeIndex([]))
    
    # Sort by datetime
    extrema.sort(key=lambda x: x[0])
    
    # Keep only most extreme points
    most_extreme = []
    for dt, val, ext_type in extrema:
        if ext_type == 'min':
            # Check if this is the lowest Low up to this point
            prior_lows = df['Low'][df.index <= dt]
            if not prior_lows.empty and val == prior_lows.min():
                most_extreme.append((dt, val, 'min'))
        else:  # ext_type == 'max'
            # Check if this is the highest High up to this point
            prior_highs = df['High'][df.index <= dt]
            if not prior_highs.empty and val == prior_highs.max():
                most_extreme.append((dt, val, 'max'))
    
    # Convert back to Series
    minima = [(dt, val) for dt, val, ext_type in most_extreme if ext_type == 'min']
    maxima = [(dt, val) for dt, val, ext_type in most_extreme if ext_type == 'max']
    
    minima_series = pd.Series(
        [val for _, val in minima],
        index=pd.DatetimeIndex([dt for dt, _ in minima])
    )
    maxima_series = pd.Series(
        [val for _, val in maxima],
        index=pd.DatetimeIndex([dt for dt, _ in maxima])
    )
    
    return minima_series, maxima_series

def filter_alternating_extrema(low_minima, high_maxima, df):
    """
    Enforce alternation (min, max, min, ...) and insert opposite extremum before the first.
    Returns two Series: filtered minima and maxima.
    """
    extrema = []
    for dt, val in low_minima.items():
        extrema.append((dt, val, 'min'))
    for dt, val in high_maxima.items():
        extrema.append((dt, val, 'max'))
    
    if not extrema:
        return pd.Series([], index=pd.DatetimeIndex([])), pd.Series([], index=pd.DatetimeIndex([]))
    
    extrema.sort(key=lambda x: x[0])
    
    # Insert opposite extremum before the first
    first_dt, _, first_type = extrema[0]
    if first_type == 'min':
        prior_highs = df['High'][df.index < first_dt]
        if not prior_highs.empty:
            max_dt = prior_highs.idxmax()
            max_val = prior_highs[max_dt]
            extrema.insert(0, (max_dt, max_val, 'max'))
    else:
        prior_lows = df['Low'][df.index < first_dt]
        if not prior_lows.empty:
            min_dt = prior_lows.idxmin()
            min_val = prior_lows[min_dt]
            extrema.insert(0, (min_dt, min_val, 'min'))
    
    # Filter for alternation
    filtered_extrema = []
    last_type = None
    for dt, val, ext_type in extrema:
        if last_type is None or last_type != ext_type:
            filtered_extrema.append((dt, val, ext_type))
            last_type = ext_type
    
    minima = [(dt, val) for dt, val, ext_type in filtered_extrema if ext_type == 'min']
    maxima = [(dt, val) for dt, val, ext_type in filtered_extrema if ext_type == 'max']
    
    minima_series = pd.Series(
        [val for _, val in minima],
        index=pd.DatetimeIndex([dt for dt, _ in minima])
    )
    maxima_series = pd.Series(
        [val for _, val in maxima],
        index=pd.DatetimeIndex([dt for dt, _ in maxima])
    )
    
    return minima_series, maxima_series

def find_extrema(df):
    """
    Find first-level extrema, keep most extreme points, enforce alternation,
    and add to DataFrame as 'extrema_min' and 'extrema_max'.
    """
    result_df = df.copy()
    
    # Step 1: Find first-level extrema
    low_minima = find_local_extrema(df['Low'], find_min=True)
    high_maxima = find_local_extrema(df['High'], find_min=False)
    
    print("First-level minima (from Low):")
    print(low_minima)
    print("\nFirst-level maxima (from High):")
    print(high_maxima)
    
    # Step 2: Keep only most extreme points
    most_extreme_minima, most_extreme_maxima = filter_most_extreme(low_minima, high_maxima, df)
    
    
    print("\nMost extreme minima:")
    print(most_extreme_minima)
    print("\nMost extreme maxima:")
    print(most_extreme_maxima)
    
    # Step 3: Enforce alternation
    final_minima, final_maxima = filter_alternating_extrema(most_extreme_minima, most_extreme_maxima, df)
    
    print("\nFinal minima (after alternation):")
    print(final_minima)
    print("\nFinal maxima (after alternation):")
    print(final_maxima)
    
    # Step 4: Add to DataFrame
    result_df['extrema_min'] = np.nan
    result_df['extrema_max'] = np.nan
    
    if not final_minima.empty:
        # result_df.loc[final_minima.index, 'extrema_min'] = final_minima
        result_df.loc[low_minima.index, 'extrema_min'] = most_extreme_minima
    if not final_maxima.empty:
        # result_df.loc[final_maxima.index, 'extrema_max'] = final_maxima
        result_df.loc[high_maxima.index, 'extrema_max'] = most_extreme_maxima
    
    return result_df

def main():
    """
    Generate random candles, find extrema, and visualize the results.
    """
    # Generate random data
    num_candles = 60
    seed = 42  # For reproducibility
    df = generate_random_candles(num_candles=num_candles, seed=seed)
    
    print("Generated OHLC Data (first 5 rows):")
    print(df[['Open', 'High', 'Low', 'Close']].head())
    
    # Find extrema
    result_df = find_extrema(df)
    
    print("\nFinal DataFrame with extrema (last 10 rows):")
    print(result_df[['Low', 'High', 'extrema_min', 'extrema_max']].tail(10))
    
    # Visualize
    apds = []
    
    # Plot extrema_min (green triangles)
    if result_df['extrema_min'].notna().any():
        apds.append(
            mpf.make_addplot(
                result_df['extrema_min'],
                type='scatter',
                markersize=100,
                marker='^',
                color='green',
                label='Extrema Min'
            )
        )
    
    # Plot extrema_max (red triangles)
    if result_df['extrema_max'].notna().any():
        apds.append(
            mpf.make_addplot(
                result_df['extrema_max'],
                type='scatter',
                markersize=100,
                marker='v',
                color='red',
                label='Extrema Max'
            )
        )
    
    # Plot candlestick chart
    mpf.plot(
        result_df,
        type='candle',
        title='Random Candles with Extrema',
        ylabel='Price',
        addplot=apds,
        volume=True,
        style='yahoo',
        figsize=(12, 8)
    )

if __name__ == "__main__":
    main()