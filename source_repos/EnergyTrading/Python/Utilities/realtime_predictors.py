#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Realtime Predictors Tools

This module contains functions for calculating technical indicators in real-time,
using both completed candles and the current evolving candle that incorporates
the latest trade data.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional, Union


def compute_macd_realtime(
    candles: pd.DataFrame,
    latest_trades: pd.DataFrame,
    se: int = 12,
    le: int = 26,
    cont: int = 9,
    candle_granularity: str = '1h'
) -> Dict[str, float]:
    """
    Compute MACD values using completed candles plus the current evolving candle.
    
    Parameters:
    -----------
    candles : pd.DataFrame
        DataFrame with completed candles including columns: 'open', 'high', 'low', 'close'
        and datetime index
    latest_trades : pd.DataFrame
        DataFrame with latest trade data for building the evolving candle
        Should include columns 'price' with datetime index
    se : int
        Short EMA period (default: 12)
    le : int
        Long EMA period (default: 26)
    cont : int
        Signal line period (default: 9)
    candle_granularity : str
        Time granularity for candles (e.g. '1h', '5min', '15min')
        
    Returns:
    --------
    Dict[str, float]
        Dictionary with 'macd', 'signal', and 'macd_hist' values
    """
    if candles.empty:
        return {'macd': np.nan, 'signal': np.nan, 'macd_hist': np.nan}
    
    # Make copies to avoid modifying original data
    candles = candles.copy()
    
    # Make sure we're working with datetime index
    candles.index = pd.to_datetime(candles.index)
    
    # Create the evolving candle using latest trades
    if not latest_trades.empty:
        latest_trades = latest_trades.copy()
        latest_trades.index = pd.to_datetime(latest_trades.index)
        
        # Determine the start time for the current evolving candle
        current_period_start = pd.Timestamp.now().floor(candle_granularity)
        
        # Filter trades that belong to the current period
        current_trades = latest_trades[latest_trades.index >= current_period_start]
        
        if not current_trades.empty:
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
                    'close': [current_close]
                },
                index=[current_period_start]
            )
            
            # Append the evolving candle to historical candles
            combined_candles = pd.concat([candles, evolving_candle])
        else:
            combined_candles = candles
    else:
        combined_candles = candles
    
    # Calculate EMAs on the combined data
    close_prices = combined_candles['close']
    short_ema = close_prices.ewm(span=se, adjust=False).mean()
    long_ema = close_prices.ewm(span=le, adjust=False).mean()
    
    # Calculate MACD line
    macd_line = short_ema - long_ema
    
    # Calculate Signal line
    signal_line = macd_line.ewm(span=cont, adjust=False).mean()
    
    # Calculate histogram
    macd_hist = macd_line - signal_line
    
    # Return the most recent values (from the evolving candle)
    return {
        'macd': macd_line.iloc[-1],
        'signal': signal_line.iloc[-1],
        'macd_hist': macd_hist.iloc[-1]
    }


def compute_atr_realtime(
    candles: pd.DataFrame,
    latest_trades: pd.DataFrame,
    period: int = 14,
    candle_granularity: str = '1h'
) -> float:
    """
    Compute ATR (Average True Range) using completed candles plus the current evolving candle.
    
    Parameters:
    -----------
    candles : pd.DataFrame
        DataFrame with completed candles including columns: 'open', 'high', 'low', 'close'
        and datetime index
    latest_trades : pd.DataFrame
        DataFrame with latest trade data for building the evolving candle
        Should include columns 'price' with datetime index
    period : int
        ATR lookback period (default: 14)
    candle_granularity : str
        Time granularity for candles (e.g. '1h', '5min', '15min')
        
    Returns:
    --------
    float
        The current ATR value
    """
    if candles.empty:
        return np.nan
    
    # Make copies to avoid modifying original data
    candles = candles.copy()
    
    # Make sure we're working with datetime index
    candles.index = pd.to_datetime(candles.index)
    
    # Create the evolving candle using latest trades
    if not latest_trades.empty:
        latest_trades = latest_trades.copy()
        latest_trades.index = pd.to_datetime(latest_trades.index)
        
        # Determine the start time for the current evolving candle
        current_period_start = pd.Timestamp.now().floor(candle_granularity)
        
        # Filter trades that belong to the current period
        current_trades = latest_trades[latest_trades.index >= current_period_start]
        
        if not current_trades.empty:
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
                    'close': [current_close]
                },
                index=[current_period_start]
            )
            
            # Append the evolving candle to historical candles
            combined_candles = pd.concat([candles, evolving_candle])
        else:
            combined_candles = candles
    else:
        combined_candles = candles
    
    # Calculate True Range for all candles
    high = combined_candles['high']
    low = combined_candles['low']
    prev_close = combined_candles['close'].shift(1)
    
    tr1 = high - low  # Current high - current low
    tr2 = (high - prev_close).abs()  # Current high - previous close
    tr3 = (low - prev_close).abs()  # Current low - previous close
    
    # True Range is the maximum of these three values
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate ATR using Wilder's smoothing method
    # First value = simple average, rest use Wilder's smoothing
    if len(tr) >= period:
        # Simple average for initial value
        atr_init = tr.iloc[:period].mean()
        
        # Apply Wilder's smoothing for remaining periods
        atr = atr_init
        for tr_val in tr.iloc[period:]:
            atr = ((period - 1) * atr + tr_val) / period
            
        return atr
    else:
        # Not enough data
        return np.nan


def generate_evolving_candle(
    latest_trades: pd.DataFrame,
    candle_granularity: str = '1h'
) -> pd.DataFrame:
    """
    Generate a single candle from the most recent trades that's still evolving.
    
    Parameters:
    -----------
    latest_trades : pd.DataFrame
        DataFrame with latest trade data with 'price' column and datetime index
    candle_granularity : str
        Time granularity for the candle (e.g. '1h', '5min', '15min')
        
    Returns:
    --------
    pd.DataFrame
        Single-row DataFrame with the evolving candle (open, high, low, close)
    """
    if latest_trades.empty:
        return pd.DataFrame()
    
    # Make a copy to avoid modifying original data
    latest_trades = latest_trades.copy()
    
    # Make sure we're working with datetime index
    latest_trades.index = pd.to_datetime(latest_trades.index)
    
    # Determine the start time for the current evolving candle
    current_period_start = pd.Timestamp.now().floor(candle_granularity)
    
    # Filter trades that belong to the current period
    current_trades = latest_trades[latest_trades.index >= current_period_start]
    
    if current_trades.empty:
        return pd.DataFrame()
    
    # Create the evolving candle
    current_open = current_trades['price'].iloc[0]
    current_high = current_trades['price'].max()
    current_low = current_trades['price'].min()
    current_close = current_trades['price'].iloc[-1]
    
    # Create the evolving candle DataFrame
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
    
    return evolving_candle


def compute_realtime_indicators(
    completed_candles: pd.DataFrame,
    latest_trades: pd.DataFrame,
    candle_granularity: str = '1h',
    macd_params: Tuple[int, int, int] = (12, 26, 9),
    atr_period: int = 14
) -> Dict[str, float]:
    """
    Compute both MACD and ATR indicators using completed candles plus the evolving candle.
    
    Parameters:
    -----------
    completed_candles : pd.DataFrame
        DataFrame with completed candles including columns: 'open', 'high', 'low', 'close'
        and datetime index
    latest_trades : pd.DataFrame
        DataFrame with latest trade data for building the evolving candle
        Should include columns 'price' with datetime index
    candle_granularity : str
        Time granularity for the candle (e.g. '1h', '5min', '15min')
    macd_params : Tuple[int, int, int]
        MACD parameters: (short EMA, long EMA, signal) periods
    atr_period : int
        ATR lookback period
        
    Returns:
    --------
    Dict[str, float]
        Dictionary with 'macd', 'signal', 'macd_hist', and 'atr' values
    """
    # Compute MACD
    se, le, cont = macd_params
    macd_result = compute_macd_realtime(
        completed_candles, latest_trades, se, le, cont, candle_granularity
    )
    
    # Compute ATR
    atr_value = compute_atr_realtime(
        completed_candles, latest_trades, atr_period, candle_granularity
    )
    
    # Combine results
    result = {
        'macd': macd_result['macd'],
        'signal': macd_result['signal'],
        'macd_hist': macd_result['macd_hist'],
        'atr': atr_value
    }
    
    return result
