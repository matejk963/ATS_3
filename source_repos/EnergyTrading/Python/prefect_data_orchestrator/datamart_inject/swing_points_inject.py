#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Swing Points Detection and Injection Script - ENHANCED VERSION

This script detects swing high and low points for energy trading contracts and injects 
the results into a TimescaleDB database.

ENHANCED Features:
- Pre-checks existing predictors and entries to avoid duplicates
- Only processes combinations that need to be inserted
- Skips metadata insertion if predictor exists but inserts data if entries missing
- Skips both if predictor and entries already exist
- REMOVES REPETITIVE VALUES: Only stores swing points when they change from previous value
- Significantly reduces data size while preserving all meaningful swing point signals

The script performs the following steps:
1. Generate all possible predictor combinations
2. Check which predictors and entries already exist
3. Process only necessary combinations
4. Extracts trade data for specific contracts
5. Generates candles with specified granularity
6. Calculates swing points (high/low) 
7. Shifts swing points forward by one period to ensure trades use swing points from previous period
8. Removes repetitive values (keeps only swing point changes)
9. Inserts the computed swing points and metadata into the database
"""

import pandas as pd
import numpy as np
from pandas import to_datetime
from pandas.tseries.offsets import MonthEnd, MonthBegin, BDay
from sqlalchemy import text

# Import custom modules
from Database.DB_reader import Database
from Database.Timescale import utils
from Utilities.predictors_tools import generate_candles, detect_swing_points

# Import all helper functions from centralized inject_helpers module
from prefect_data_orchestrator.datamart_inject.inject_helpers import (
    get_contract_by_position,
    eff_month,
    add_month_ahead_flags,
    get_front_position,
    generate_contract_codes
)

def check_existing_predictors_and_entries(conn, pred_names):
    """
    Check which predictors exist and which have entries.
    
    Returns:
    - predictors_exist: set of pred_names that exist in predictors table
    - entries_exist: set of pred_names that have entries in dataset_entries table
    """
    print("🔍 Checking existing predictors and entries...")
    
    if not pred_names:
        return set(), set()
    
    # Convert list to comma-separated string for SQL IN clause
    pred_names_str = "', '".join(pred_names)
    
    # Check existing predictors
    predictor_query = f"""
    SELECT pred_name, pred_id 
    FROM public.experimental_predictors 
    WHERE pred_name IN ('{pred_names_str}')
    """
    
    existing_predictors_df = conn.execute_general_query(predictor_query)
    predictors_exist = set(existing_predictors_df['pred_name'].tolist()) if not existing_predictors_df.empty else set()
    
    # Check existing entries (only for predictors that exist)
    entries_exist = set()
    if not existing_predictors_df.empty:
        pred_ids = existing_predictors_df['pred_id'].tolist()
        pred_ids_str = "', '".join(map(str, pred_ids))
        
        entries_query = f"""
        SELECT DISTINCT p.pred_name
        FROM public.experimental_predictors p
        JOIN public.experimental_dataset_entries e ON p.pred_id = e.pred_id
        WHERE p.pred_id IN ('{pred_ids_str}')
        """
        
        existing_entries_df = conn.execute_general_query(entries_query)
        entries_exist = set(existing_entries_df['pred_name'].tolist()) if not existing_entries_df.empty else set()
    
    print(f"📊 Found {len(predictors_exist)} existing predictors, {len(entries_exist)} with entries")
    return predictors_exist, entries_exist

def generate_all_predictor_names(contract_periods_map, candle_granularities):
    """Generate all possible predictor names for the given configurations."""
    pred_names = []
    
    for contract_period, period_codes in contract_periods_map.items():
        for candle_granularity in candle_granularities:
            for contract_code in period_codes:
                for swing_type in ['high', 'low']:
                    pred_name = f"swing_{swing_type}_{contract_code}_candles_{candle_granularity}"
                    pred_names.append(pred_name)
    
    return pred_names

def main():
    """Main function to calculate swing points and inject into database."""
    # Restrict to only the missing swing predictor combinations:
    # Only process 30min and 1h granularities for dem1, dem2, deq1, deq2 (as per previous analysis)
    CANDLE_GRANULARITIES = ['5min', '15min', '30min', '1h']  # Only these granularities are needed for swing points
    START_DATE = '2025-01-01'
    END_DATE = '2025-06-30'
    CONTRACT_CODES = ['dem1', 'dem2']

    # Group contract codes by their period type (second character from the back)
    contract_periods_map = {}
    for code in CONTRACT_CODES:
        period_char = code[-2].upper()
        if period_char in ['M', 'Q', 'Y']:
            if period_char not in contract_periods_map:
                contract_periods_map[period_char] = []
            contract_periods_map[period_char].append(code)
        else:
            print(f"Warning: Invalid contract period character in {code}. Skipping.")
    if not contract_periods_map:
        raise ValueError("No valid contract codes with recognized period types (M, Q, Y) found.")

    print(f"Running with candle granularities: {CANDLE_GRANULARITIES}")
    print(f"Contract periods detected: {list(contract_periods_map.keys())}, Date range: {START_DATE} to {END_DATE}")
    print(f"Processing contracts by period: {contract_periods_map}")

    # Generate all possible predictor names (only for missing combinations)
    all_pred_names = generate_all_predictor_names(contract_periods_map, CANDLE_GRANULARITIES)
    print(f"📋 Generated {len(all_pred_names)} total predictor combinations (targeted missing only)")
    
    # Check existing predictors and entries
    conn = Database('timescaledb')
    predictors_exist, entries_exist = check_existing_predictors_and_entries(conn, all_pred_names)
    
    # Determine what needs to be processed
    need_predictor_insert = set(all_pred_names) - predictors_exist
    need_entries_insert = predictors_exist - entries_exist
    skip_completely = entries_exist
    
    print(f"🆕 Need predictor insert: {len(need_predictor_insert)}")
    print(f"📊 Need entries insert only: {len(need_entries_insert)}")
    print(f"⏭️ Skip completely: {len(skip_completely)}")
    
    # If nothing needs processing, exit early
    # if not need_predictor_insert and not need_entries_insert:
        # print("✅ All predictors and entries already exist. Nothing to process.")
        # return
    
    # Only load data if we have work to do
    print("📥 Loading data from database...")
    
    # 1. Read data from source DB - do this once, outside the loop
    query = f"""select distinct datetime, nanotime, tradeid from public.trades 
              where datetime>='{START_DATE}' and datetime<='{END_DATE}' 
              and EXTRACT(HOUR FROM datetime) BETWEEN 8 AND 18
              and instid in ('10641710', '10001075', '10100480', '10012528', '10002806')
              order by datetime asc, nanotime asc"""
    timestamps = conn.execute(query)
    print(f"✅ Loaded {len(timestamps)} rows from source database.")    # 2. Fetch front contracts trades - do this once, outside the loop
    # Load clean contract data WITHOUT forward-fill (ffill only after predictor computation)
    contract_data_original = {}
    for contract_code in CONTRACT_CODES:
        df = utils.get_trades_data(contract_code, START_DATE, END_DATE)
        # Merge timestamps with contract trades on tradeid
        merged = timestamps.merge(
            df[['tradeid', 'price']],
            on='tradeid',
            how='left'
        )
        merged.set_index('datetime', inplace=True)
        # NO forward-fill here - keep original data clean for predictor computation
        contract_data_original[contract_code] = merged
    
    print("Merged timestamps into contract_data:", {k: v.shape for k, v in contract_data_original.items()})
    
    # Process each contract period separately
    for contract_period, period_codes in contract_periods_map.items():
        print(f"\n=== Processing {contract_period} contracts: {period_codes} ===")
        
        # Check if this period has any work to do
        period_pred_names = [name for name in all_pred_names if any(code in name for code in period_codes)]
        period_needs_work = any(name in need_predictor_insert or name in need_entries_insert for name in period_pred_names)
        
        if not period_needs_work:
            print(f"⏭️ Skipping {contract_period} - all predictors and entries already exist")
            continue
        
        # 3. Build period data using period-only keys - do this for each contract period
        period_data = {}
        
        # Process each contract code in this period type
        for pos, contract_code in enumerate(period_codes, 1):
            # Get the dataframe for this contract
            df_cont = contract_data_original[contract_code]
            tmp = df_cont.copy()
            
            # Calculate the effective period for each timestamp
            # Use eff_month with correct period_type for contract_period
            if contract_period == 'M':
                tmp['eff_month'] = eff_month(tmp.index, pos, period_type='M')
            elif contract_period == 'Q':
                tmp['eff_month'] = eff_month(tmp.index, pos, period_type='Q')
            elif contract_period == 'Y':
                tmp['eff_month'] = eff_month(tmp.index, pos, period_type='Y')
            else:
                raise ValueError(f"Unknown contract period: {contract_period}")
            
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
            
        print(f"Created {contract_period} period_data:", list(period_data.keys()))
        
        # Process each candle granularity for this contract period
        for candle_granularity in CANDLE_GRANULARITIES:
            tf = candle_granularity
            
            # Check if this granularity has any work to do
            granularity_pred_names = [name for name in period_pred_names if f"candles_{tf}" in name]
            granularity_needs_work = any(name in need_predictor_insert or name in need_entries_insert for name in granularity_pred_names)
            
            if not granularity_needs_work:
                print(f"⏭️ Skipping {contract_period} {tf} - all predictors and entries already exist")
                continue
            
            # Make a copy of the original contract data for each granularity (limited to current period's contracts)
            contract_data = {k: v.copy() for k, v in contract_data_original.items() if k in period_codes}
            
            # 4. Generate candles for each period with the current granularity
            print(f"\n--- Processing {contract_period} with granularity: {tf} ---")
            period_candles = {}
            for period, dfm in period_data.items():
                dfm = dfm.copy()
                dfm.index = to_datetime(dfm.index)
                # Build candles with specified granularity
                ch = generate_candles(dfm[['price']], granularity=tf)
                period_candles[period] = ch
            print(f"Generated {tf} candles for {len(period_candles)} periods.")
            
            print(f"\n--- Processing {contract_period} swing points with {tf} candles ---")
            
            # 5. Calculate swing points for each period dataset
            period_swing_data = {}
            for period, period_df in period_data.items():
                # Prepare dataframe
                df = period_df.copy()
                df['period'] = df.index.floor(tf)
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
                    df['candle_period'] = df['datetime'].dt.floor(tf)
                    
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
                period_swing_data[period] = df[['datetime', 'nanotime', 'tradeid', 'swing_high', 'swing_low']].copy()
            
            # 6. Recombine swing points data back into contract_data for this period
            parts_by_key = {key: [] for key in period_codes}  # Initialize only for codes in this period

            # Process each period's data
            for period, period_df in period_swing_data.items():
                # Add front position column for filtering
                period_df = period_df.set_index('datetime').copy()  # Avoid modifying the original dataframe
                period_df['front_position'] = get_front_position(period_df, period)
                
                # Assign each row to the appropriate contract based on front position
                for i, contract_code in enumerate(period_codes, 1):
                    # Get rows corresponding to this position
                    matching_rows = period_df[period_df['front_position'] == i].copy()
                    
                    if not matching_rows.empty:
                        # Remove the temporary column and add to the appropriate list
                        matching_rows.drop(columns=['front_position'], inplace=True)
                        parts_by_key[contract_code].append(matching_rows)            # Concatenate all parts for each key
            for key in contract_data.keys():
                if parts_by_key[key]:  # Only concat if we have parts
                    contract_data[key] = pd.concat(parts_by_key[key])

            print(f"Swing points computed and shifted one period forward on {tf} candles.")
            print("Swing highs assigned by front:", {k: v['swing_high'].notna().sum() for k, v in contract_data.items()})
            print("Swing lows assigned by front:", {k: v['swing_low'].notna().sum() for k, v in contract_data.items()})

            # === REMOVE REPETITIVE VALUES ===
            print(f"\n--- Removing repetitive swing point values for {contract_period} {tf} ---")
            for contract_code in period_codes:
                if contract_code in contract_data:
                    df = contract_data[contract_code].copy()
                    original_high_count = df['swing_high'].notna().sum() if 'swing_high' in df.columns else 0
                    original_low_count = df['swing_low'].notna().sum() if 'swing_low' in df.columns else 0
                    
                    # Remove repetitive swing highs - keep only values that are different from the previous value
                    if 'swing_high' in df.columns:
                        df['swing_high'] = df['swing_high'].where(
                            df['swing_high'] != df['swing_high'].shift(1)
                        )
                    
                    # Remove repetitive swing lows - keep only values that are different from the previous value
                    if 'swing_low' in df.columns:
                        df['swing_low'] = df['swing_low'].where(
                            df['swing_low'] != df['swing_low'].shift(1)
                        )
                    
                    contract_data[contract_code] = df
                    new_high_count = df['swing_high'].notna().sum() if 'swing_high' in df.columns else 0
                    new_low_count = df['swing_low'].notna().sum() if 'swing_low' in df.columns else 0
                    
                    print(f"✅ {contract_code} - Swing highs: {original_high_count:,} -> {new_high_count:,} (removed {original_high_count-new_high_count:,} repetitive)")
                    print(f"✅ {contract_code} - Swing lows: {original_low_count:,} -> {new_low_count:,} (removed {original_low_count-new_low_count:,} repetitive)")
            
            print(f"✅ Removed repetitive values. Only swing point changes are preserved.")

            # 7. Insert predictors metadata into database
            timeframe = tf

            for contract_code in period_codes:  # Process only current period's contract codes
                # Process each type of swing point (high and low)
                for swing_type in ['high', 'low']:
                    # Create unique predictor names that incorporate the granularity and period
                    pred_name = f"swing_{swing_type}_{contract_code}_candles_{tf}"
                    
                    # Determine what action to take
                    if pred_name in skip_completely:
                        print(f"⏭️ Skipping {pred_name} - predictor and entries already exist")
                        continue
                      # Get or insert predictor metadata
                    pred_id = None
                    
                    if pred_name in need_predictor_insert:
                        # Insert new predictor
                        print(f"🆕 Inserting new predictor: {pred_name}")
                        
                        main_contract = contract_code
                        description = f"Swing {swing_type} points for {contract_period} contracts, based on {timeframe} candles, shifted one period forward, repetitive values removed, NaN values preserved"
                        location = r"EnergyTrading\Python\prefect_data_orchestrator\datamart_inject\swing_points_inject.py"
                        prod_strategy = None
                        author = "MatejKrajcovic"
                        additional = f"Uses detect_swing_points on {timeframe} candles with values shifted one period forward. Pure ffill across periods, repetitive values removed, NaN values preserved in database. Contract period: {contract_period}"

                        # Define the SQL INSERT statement as a string with placeholders
                        stmt = """
                        INSERT INTO public.experimental_predictors
                        (pred_name, main_contract, description, "location", prod_strategy, author, additional, created_at)
                        VALUES (:pred_name, :main_contract, :description, :location, :prod_strategy, :author, :additional, CURRENT_TIMESTAMP)
                        """

                        # Execute the query with parameters passed as a dictionary
                        try:
                            conn.execute_general_query(stmt, {
                                'pred_name': pred_name,
                                'main_contract': main_contract,
                                'description': description,
                                'location': location,
                                'prod_strategy': prod_strategy,
                                'author': author,
                                'additional': additional
                            })
                            print(f"✅ Predictor metadata inserted for {pred_name}")
                        except Exception as e:
                            print(f"❌ Warning: Could not insert predictor {pred_name}. Error: {e}")
                            continue
                    
                    # Retrieve the pred_id (whether just inserted or already exists)
                    get_pred_id_query = "SELECT pred_id FROM public.experimental_predictors WHERE pred_name = :pred_name"
                    pred_id_result = conn.execute_general_query(get_pred_id_query, {'pred_name': pred_name})
                    pred_id = pred_id_result.iloc[0]['pred_id'] if not pred_id_result.empty else None
                    
                    if pred_id is None:
                        print(f"❌ Error: Could not retrieve pred_id for {pred_name}. Skipping data insertion.")
                        continue
                    
                    print(f"📋 Using pred_id: {pred_id} for predictor {pred_name}")
                    
                    # 8. Insert swing point values for each trade into the experimental_dataset_entries table
                    if pred_name in need_predictor_insert or pred_name in need_entries_insert:
                        print(f"📊 Inserting entries for {pred_name}")
                        
                        # Step 1: Extract necessary columns
                        df = timestamps.copy()
                        
                        # Step 2: Merge with swing point data
                        column_name = f"swing_{swing_type}"
                        if contract_code in contract_data and column_name in contract_data[contract_code].columns:
                            df_with_swing = df.merge(
                                contract_data[contract_code].reset_index()[['datetime', 'nanotime', 'tradeid', column_name]],
                                on=['datetime', 'nanotime', 'tradeid'],
                                how='left'
                            )
                            
                            # Rename column to pred_value directly
                            df_with_swing.rename(columns={column_name: 'pred_value'}, inplace=True)
                              # Add pred_id column
                            df_with_swing['pred_id'] = pred_id
                            
                            # Sort by datetime for consistent processing
                            df_with_swing = df_with_swing.sort_values(by=['datetime', 'nanotime', 'pred_id'], ascending=[True, True, True])
                            
                            # Flag missing values in logs but don't store in database (column doesn't exist)
                            mask_missing = df_with_swing['pred_value'].isna()
                            missing_count = mask_missing.sum()
                            if missing_count > 0:
                                print(f"⚠️ Note: {missing_count} rows have missing swing {swing_type} values - these will be inserted as NaN in database")
                            
                            # Clean up and prepare for insertion (keep NaN values as they are)
                            df_with_swing['pred_value'] = df_with_swing['pred_value'].astype(float)
                            
                            # Keep only the columns that match the database schema
                            columns_to_keep = ['datetime', 'nanotime', 'tradeid', 'pred_id', 'pred_value']
                            df_final = df_with_swing[columns_to_keep].reset_index(drop=True)
                            # Drop duplicates based on unique constraint columns
                            df_final = df_final.drop_duplicates(subset=['datetime', 'nanotime', 'tradeid', 'pred_id']).copy()
                            
                            # Insert in batches
                            batch_size = 100_000
                            conn._connect()
                            
                            total_rows = len(df_final)
                            for start in range(0, total_rows, batch_size):
                                end = min(start + batch_size, total_rows)
                                batch = df_final.iloc[start:end]
                                # Remove duplicates before insertion - specifically targeting the unique constraint columns                                batch = batch.drop_duplicates(['datetime', 'nanotime', 'tradeid', 'pred_id'])
                                
                                try:
                                    batch.to_sql('experimental_dataset_entries', conn.engine, schema='public', index=False, if_exists='append', method='multi')
                                    print(f"✅ Inserted rows {start} to {end} into TimescaleDB for {pred_id}.")
                                except Exception as e:
                                    print(f"❌ Error inserting batch {start}-{end} for {pred_id}: {e}")

main()