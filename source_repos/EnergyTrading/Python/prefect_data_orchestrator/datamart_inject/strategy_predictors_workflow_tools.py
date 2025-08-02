#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Strategy Predictors Workflow Tools

This module provides tools for processing strategy predictors workflow including:
1. Converting relative contracts to absolute periods
2. Generating candles from period data
3. Computing MACD and other technical indicators

Functions:
- process_relative_contracts_to_periods: Convert relative contract data to absolute period data
- compute_macd_from_period_data: Generate candles and compute MACD from period data
- compute_swing_points_from_period_data: Generate candles and compute swing points from period data
- compute_atr_from_period_data: Generate candles and compute ATR from period data
"""

import pandas as pd
import numpy as np
from pandas import to_datetime
from pandas.tseries.offsets import MonthEnd, MonthBegin, BDay

# Import custom modules
from Database.DB_reader import Database
from Database.Timescale import utils
from Utilities.predictors_tools import generate_candles, compute_realtime_macd, detect_swing_points, compute_realtime_atr

# Import helper functions
from prefect_data_orchestrator.datamart_inject.inject_helpers import (
    get_contract_by_position,
    eff_month,
    add_month_ahead_flags,
    get_front_position,
    generate_contract_codes
)

def process_relative_contracts_to_periods(contract_codes, start_date, end_date):
    """
    Process relative contract data and convert to absolute period data.
    
    Args:
        contract_codes: List of contract codes (e.g., ['dem1', 'dem2'])
        start_date: Start date string (e.g., '2025-01-01')
        end_date: End date string (e.g., '2025-06-30')
    
    Returns:
        dict: period_data dictionary with absolute periods as keys and DataFrames as values
    """
    
    # Group contract codes by their period type (second character from the back)
    contract_periods_map = {}
    for code in contract_codes:
        period_char = code[-2].upper()
        if period_char in ['M', 'Q', 'Y']:
            if period_char not in contract_periods_map:
                contract_periods_map[period_char] = []
            contract_periods_map[period_char].append(code)
        else:
            print(f"Warning: Invalid contract period character in {code}. Skipping.")
    
    if not contract_periods_map:
        raise ValueError("No valid contract codes with recognized period types (M, Q, Y) found.")
    
    print(f"Contract periods detected: {list(contract_periods_map.keys())}")
    print(f"Processing contracts by period: {contract_periods_map}")
    
    # Connect to database
    conn = Database('timescaledb')
    
    # Step 1: Load timestamps from database
    print("📥 Loading timestamps from database...")
    query = f"""select distinct datetime, nanotime, tradeid from public.trades 
              where datetime>='{start_date}' and datetime<='{end_date}' 
              and EXTRACT(HOUR FROM datetime) BETWEEN 9 AND 17
              and instid in ('10641710', '10001075', '10100480', '10012528', '10002806')
              order by datetime asc, nanotime asc"""
    timestamps = conn.execute(query)
    print(f"✅ Loaded {len(timestamps)} timestamp rows from database.")
    
    # Step 2: Load contract data
    print("📥 Loading contract trade data...")
    contract_data_original = {}
    for contract_code in contract_codes:
        df = utils.get_trades_data(contract_code, start_date, end_date)
        # Merge timestamps with contract trades on tradeid
        merged = timestamps.merge(
            df[['tradeid', 'price']],
            on='tradeid',
            how='left'
        )
        merged.set_index('datetime', inplace=True)
        # Keep original data clean (no forward-fill)
        contract_data_original[contract_code] = merged
    
    print("✅ Contract data loaded:", {k: v.shape for k, v in contract_data_original.items()})
    
    # Step 3: Process each contract period separately to create period_data
    all_period_data = {}
    
    for contract_period, period_codes in contract_periods_map.items():
        print(f"\n=== Processing {contract_period} contracts: {period_codes} ===")
        
        # Build period data using period-only keys
        period_data = {}
        
        # Process each contract code in this period type
        for pos, contract_code in enumerate(period_codes, 1):
            # Get the dataframe for this contract
            df_cont = contract_data_original[contract_code]
            tmp = df_cont.copy()
            
            # Calculate the effective period for each timestamp
            tmp['eff_month'] = eff_month(tmp.index, pos, period_type=contract_period)
            
            # Format period key based on the current contract period
            for m, grp in tmp.groupby('eff_month'):
                if contract_period == 'M':
                    key = m.strftime('%Y-%m')
                elif contract_period == 'Q':
                    quarter = (m.month - 1) // 3 + 1
                    key = f"{m.year}-Q{quarter}"
                elif contract_period == 'Y':
                    key = f"{m.year}"
                
                if key not in period_data:
                    period_data[key] = grp.sort_index()
                else:
                    period_data[key] = pd.concat([period_data[key], grp.sort_index()]).sort_index()
        
        print(f"✅ Created {contract_period} period_data with {len(period_data)} periods: {list(period_data.keys())}")
        
        # Add to overall result with period type prefix to avoid conflicts
        for key, data in period_data.items():
            full_key = f"{contract_period}_{key}"
            all_period_data[full_key] = data
    
    return all_period_data

def compute_macd_from_period_data(period_data, candle_granularity, se=12, le=26, cont=9):
    """
    Generate candles and compute MACD from period data.
    
    This function covers steps 4 and 5 of the data flow:
    4. Generate candles for each period with the specified granularity
    5. Calculate MACD values using the specified parameters
    
    Args:
        period_data: Dictionary with period keys and DataFrame values (from process_relative_contracts_to_periods)
        candle_granularity: String specifying candle granularity (e.g., '5min', '15min', '30min', '1h')
        se: Short EMA period (default: 12)
        le: Long EMA period (default: 26) 
        cont: Signal line period (default: 9)
    
    Returns:
        dict: Dictionary with same period keys containing MACD data (macd, signal, hist columns)
    """
    
    print(f"\n--- Computing MACD with granularity: {candle_granularity}, params: ({se},{le},{cont}) ---")
    
    # Step 4: Generate candles for each period
    print(f"🕯️ Generating {candle_granularity} candles for {len(period_data)} periods...")
    period_candles = {}
    for period, dfm in period_data.items():
        dfm = dfm.copy()
        dfm.index = to_datetime(dfm.index)
        # Build candles with specified granularity
        ch = generate_candles(dfm[['price']], granularity=candle_granularity)
        period_candles[period] = ch
    print(f"✅ Generated {candle_granularity} candles for {len(period_candles)} periods.")
    
    # Step 5: Calculate MACD for each period
    print(f"📊 Computing MACD for {len(period_data)} periods...")
    period_macd_data = {}
    for period, period_df in period_data.items():
        # Prepare dataframe
        df = period_df.copy()
        df['period'] = df.index.floor(candle_granularity)
        df['datetime'] = df.index
        df = df.reset_index(drop=True)
        
        # Get candles for this period
        period_candles_data = period_candles.get(period)
        
        if period_candles_data is None or period_candles_data.empty:
            # No candles for this period, mark MACD values as NaN
            df['macd'] = np.nan
            df['signal'] = np.nan
            df['hist'] = np.nan
        else:
            # Compute MACD using the specified parameters
            df = compute_realtime_macd(
                df,
                period_candles_data,
                se=se,
                le=le,
                signal_period=cont
            )
            # Pure forward-fill MACD values across all periods (no boundaries)
            df['macd'] = df['macd'].ffill()
            df['signal'] = df['signal'].ffill()
            df['hist'] = df['hist'].ffill()
        
        # Store result (key columns needed)
        period_macd_data[period] = df[['datetime', 'nanotime', 'tradeid', 'macd', 'hist']].drop_duplicates().copy()
    
    print(f"✅ MACD computed for {len(period_macd_data)} periods with parameters ({se},{le},{cont})")
    
    return period_macd_data

def compute_swing_points_from_period_data(period_data, candle_granularity):
    """
    Generate candles and compute swing points from period data.
    
    This function covers steps 4 and 5 of the swing points data flow:
    4. Generate candles for each period with the specified granularity
    5. Calculate swing points (high/low) and shift them forward by one period
    
    Args:
        period_data: Dictionary with period keys and DataFrame values (from process_relative_contracts_to_periods)
        candle_granularity: String specifying candle granularity (e.g., '5min', '15min', '30min', '1h')
    
    Returns:
        dict: Dictionary with same period keys containing swing points data (swing_high, swing_low columns)
    """
    
    print(f"\n--- Computing Swing Points with granularity: {candle_granularity} ---")
    
    # Step 4: Generate candles for each period
    print(f"🕯️ Generating {candle_granularity} candles for {len(period_data)} periods...")
    period_candles = {}
    for period, dfm in period_data.items():
        dfm = dfm.copy()
        dfm.index = to_datetime(dfm.index)
        # Build candles with specified granularity
        ch = generate_candles(dfm[['price']], granularity=candle_granularity)
        period_candles[period] = ch
    print(f"✅ Generated {candle_granularity} candles for {len(period_candles)} periods.")
    
    # Step 5: Calculate swing points for each period
    print(f"📊 Computing swing points for {len(period_data)} periods...")
    period_swing_data = {}
    for period, period_df in period_data.items():
        # Prepare dataframe
        df = period_df.copy()
        df['period'] = df.index.floor(candle_granularity)
        df['datetime'] = df.index
        df = df.reset_index(drop=True)
        
        # Get candles for this period
        period_candles_data = period_candles.get(period)
        
        if period_candles_data is None or period_candles_data.empty:
            # No candles for this period, mark swing points as NaN
            df['swing_high'] = np.nan
            df['swing_low'] = np.nan
        else:
            # Compute swing points using the detect_swing_points function on candle data
            swing_points_df = detect_swing_points(period_candles_data, high_col='high', low_col='low')
            
            # Shift swing points one period forward (to ensure trades use swing points from previous period)
            # and pure forward-fill across all periods (no boundaries)
            swing_points_df['swing_high'] = swing_points_df['swing_high'].shift(1).ffill()
            swing_points_df['swing_low'] = swing_points_df['swing_low'].shift(1).ffill()
            
            # Calculate the candle period for each trade
            df['candle_period'] = df['datetime'].dt.floor(candle_granularity)
            
            # Prepare swing points data with candle period
            swing_df = swing_points_df.reset_index()
            swing_df['candle_period'] = swing_df.iloc[:, 0]  # First column contains datetime index
            
            # Merge with the trade data based on candle period
            merged_data = pd.merge_asof(
                df[['datetime', 'nanotime', 'tradeid', 'candle_period']],
                swing_df[['candle_period', 'swing_high', 'swing_low']],
                left_on='candle_period',
                right_on='candle_period',
                direction='backward'
            )
            
            # Copy the swing points from merged data to our original dataframe
            df = pd.merge(
                df,
                merged_data[['datetime', 'nanotime', 'tradeid', 'swing_high', 'swing_low']],
                on=['datetime', 'nanotime', 'tradeid'],
                how='left'
            )
        
        # Store result (keep only necessary columns)
        period_swing_data[period] = df[['datetime', 'nanotime', 'tradeid', 'swing_high', 'swing_low']].drop_duplicates().copy()
    
    print(f"✅ Swing points computed and shifted one period forward for {len(period_swing_data)} periods")
    
    return period_swing_data

def compute_atr_from_period_data(period_data, candle_granularity, atr_lookback=21):
    """
    Generate candles and compute ATR from period data.
    
    This function covers steps 4 and 5 of the ATR data flow:
    4. Generate candles for each period with the specified granularity
    5. Calculate ATR values using the specified lookback period
    
    Args:
        period_data: Dictionary with period keys and DataFrame values (from process_relative_contracts_to_periods)
        candle_granularity: String specifying candle granularity (e.g., '5min', '15min', '30min', '1h')
        atr_lookback: ATR lookback period (default: 21)
    
    Returns:
        dict: Dictionary with same period keys containing ATR data (atr column)
    """
    
    print(f"\n--- Computing ATR with granularity: {candle_granularity}, lookback: {atr_lookback} ---")
    
    # Step 4: Generate candles for each period
    print(f"🕯️ Generating {candle_granularity} candles for {len(period_data)} periods...")
    period_candles = {}
    for period, dfm in period_data.items():
        dfm = dfm.copy()
        dfm.index = to_datetime(dfm.index)
        # Build candles with specified granularity
        ch = generate_candles(dfm[['price']], granularity=candle_granularity)
        period_candles[period] = ch
    print(f"✅ Generated {candle_granularity} candles for {len(period_candles)} periods.")
    
    # Step 5: Calculate ATR for each period
    print(f"📊 Computing ATR for {len(period_data)} periods...")
    period_atr_data = {}
    for period, period_df in period_data.items():
        # Prepare dataframe
        df = period_df.copy()
        df['period'] = df.index.floor(candle_granularity)
        df['datetime'] = df.index
        df = df.reset_index(drop=True)
        
        # Get candles for this period
        period_candles_data = period_candles.get(period)
        
        if period_candles_data is None or period_candles_data.empty:
            # No candles for this period, mark ATR values as NaN
            df['atr'] = np.nan
        else:
            # Compute ATR using the specified lookback period
            df = compute_realtime_atr(
                df,
                period_candles_data,
                atr_period=atr_lookback
            )
            # Pure forward-fill ATR values across all periods (no boundaries)
            df['atr'] = df['atr'].ffill()
        
        # Store result (key columns needed)
        period_atr_data[period] = df[['datetime', 'nanotime', 'tradeid', 'atr']].drop_duplicates().copy()
    
    print(f"✅ ATR computed for {len(period_atr_data)} periods with lookback {atr_lookback}")
    
    return period_atr_data

def main():
    """Example usage of the trades processing, MACD computation, swing points, and ATR functions."""
    
    # Configuration
    START_DATE = '2025-01-01'
    END_DATE = '2025-01-31'
    CONTRACT_CODES = ['dem1', 'dem2']  # Test with monthly contracts first
    CANDLE_GRANULARITY = '15min'
    MACD_PARAMS = (12, 26, 9)
    ATR_LOOKBACK = 21
    
    print(f"Processing contracts: {CONTRACT_CODES}")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print(f"Candle granularity: {CANDLE_GRANULARITY}")
    print(f"MACD parameters: {MACD_PARAMS}")
    print(f"ATR lookback: {ATR_LOOKBACK}")
    
    # Step 1-3: Process contracts to period data
    period_data = process_relative_contracts_to_periods(CONTRACT_CODES, START_DATE, END_DATE)
    
    # Display intermediate results
    print(f"\n📊 Period data created: {len(period_data)} periods")
    for period_key, data in period_data.items():
        print(f"  {period_key}: {len(data)} rows")
    
    # Step 4-5: Compute MACD from period data
    macd_data = compute_macd_from_period_data(
        period_data, 
        CANDLE_GRANULARITY, 
        se=MACD_PARAMS[0], 
        le=MACD_PARAMS[1], 
        cont=MACD_PARAMS[2]
    )
    
    # Step 4-5: Compute swing points from period data
    swing_data = compute_swing_points_from_period_data(period_data, CANDLE_GRANULARITY)
    
    # Step 4-5: Compute ATR from period data
    atr_data = compute_atr_from_period_data(period_data, CANDLE_GRANULARITY, ATR_LOOKBACK)
    
    # Display final results
    print(f"\n🎉 MACD computation complete! Created {len(macd_data)} period datasets:")
    for period_key, data in macd_data.items():
        macd_count = data['macd'].notna().sum()
        hist_count = data['hist'].notna().sum()
        print(f"  {period_key}: {len(data)} rows, {macd_count} MACD values, {hist_count} histogram values")
    
    print(f"\n🎉 Swing points computation complete! Created {len(swing_data)} period datasets:")
    for period_key, data in swing_data.items():
        high_count = data['swing_high'].notna().sum()
        low_count = data['swing_low'].notna().sum()
        print(f"  {period_key}: {len(data)} rows, {high_count} swing highs, {low_count} swing lows")
    
    print(f"\n🎉 ATR computation complete! Created {len(atr_data)} period datasets:")
    for period_key, data in atr_data.items():
        atr_count = data['atr'].notna().sum()
        print(f"  {period_key}: {len(data)} rows, {atr_count} ATR values")
    
    return period_data, macd_data, swing_data, atr_data

if __name__ == "__main__":
    period_data, macd_data, swing_data, atr_data = main()
