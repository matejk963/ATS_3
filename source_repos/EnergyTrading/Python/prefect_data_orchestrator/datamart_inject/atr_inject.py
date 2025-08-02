#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ATR (Average True Range) Calculation and Injection Script - BETA VERSION

This script calculates ATR values for energy trading contracts and injects 
the results into a TimescaleDB database.

BETA Features:
- Pre-checks existing predictors and entries to avoid duplicates
- Only processes combinations that need to be inserted
- Skips metadata insertion if predictor exists but inserts data if entries missing
- Skips both if predictor and entries already exist

The script performs the following steps:
1. Generate all possible predictor combinations
2. Check which predictors and entries already exist
3. Process only necessary combinations
4. Extracts trade data for specific contracts
5. Generates candles with specified granularity
6. Calculates ATR values using the specified lookback period
7. Inserts the computed ATR values and metadata into the database
"""

import pandas as pd
import numpy as np
from pandas import to_datetime
from pandas.tseries.offsets import MonthEnd, MonthBegin, BDay
from sqlalchemy import text

# Import custom modules
from Database.DB_reader import Database
from Database.Timescale import utils
from Utilities.predictors_tools import generate_candles, compute_realtime_atr

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

def generate_all_predictor_names(contract_periods_map, candle_granularities, atr_lookbacks):
    """Generate all possible predictor names for the given configurations."""
    pred_names = []
    
    for contract_period, period_codes in contract_periods_map.items():
        for candle_granularity in candle_granularities:
            for atr_lookback in atr_lookbacks:
                for contract_code in period_codes:
                    pred_name = f"atr_{contract_code}_candles_{candle_granularity}_lookback_{atr_lookback}"
                    pred_names.append(pred_name)
    
    return pred_names

def main():
    """Main function to calculate ATR and inject into database."""
    # Configuration variables
    CANDLE_GRANULARITIES = ['5min', '15min', '30min', '1h']   # Only 1h granularity for missing combination
    ATR_LOOKBACKS = [21]
    START_DATE = '2025-01-01'
    END_DATE = '2025-06-30'
    CONTRACT_CODES = ['dem1', 'dem2']  # Only dem2 for missing ATR
    
    # Group contract codes by their period type (second character from the back)
    # e.g., dem1 => 'm' => 'M', deq1 => 'q' => 'Q', dey1 => 'y' => 'Y'
    contract_periods_map = {}
    
    for code in CONTRACT_CODES:
        period_char = code[-2].upper()
        if period_char in ['M', 'Q', 'Y']:
            if period_char not in contract_periods_map:
                contract_periods_map[period_char] = []
            contract_periods_map[period_char].append(code)
        else:
            print(f"Warning: Invalid contract period character in {code}. Skipping.")
    
    # Check if we have valid contract codes
    if not contract_periods_map:
        raise ValueError("No valid contract codes with recognized period types (M, Q, Y) found.")
        
    print(f"Running with candle granularities: {CANDLE_GRANULARITIES}, ATR lookbacks: {ATR_LOOKBACKS}")
    print(f"Contract periods detected: {list(contract_periods_map.keys())}, Date range: {START_DATE} to {END_DATE}")
    print(f"Processing contracts by period: {contract_periods_map}")
    
    # Generate all possible predictor names
    all_pred_names = generate_all_predictor_names(contract_periods_map, CANDLE_GRANULARITIES, ATR_LOOKBACKS)
    print(f"📋 Generated {len(all_pred_names)} total predictor combinations")
    
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
    if not need_predictor_insert and not need_entries_insert:
        print("✅ All predictors and entries already exist. Nothing to process.")
        return
    
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
            # This creates a new column showing which specific period each timestamp belongs to
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
            
        print(f"Created {contract_period} period_data:", list(period_data.keys()))
        
        # Process each combination of candle granularity and ATR lookback for this contract period
        for candle_granularity in CANDLE_GRANULARITIES:
            tf = candle_granularity
            
            # Check if this granularity has any work to do
            granularity_pred_names = [name for name in period_pred_names if f"candles_{tf}_" in name]
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
            
            # Process each ATR lookback period with the current candle granularity
            for atr_lookback in ATR_LOOKBACKS:
                # Check if this lookback period has any work to do
                lookback_pred_names = [name for name in granularity_pred_names if f"lookback_{atr_lookback}" in name]
                lookback_needs_work = any(name in need_predictor_insert or name in need_entries_insert for name in lookback_pred_names)
                
                if not lookback_needs_work:
                    print(f"⏭️ Skipping {contract_period} {tf} ATR({atr_lookback}) - all predictors and entries already exist")
                    continue
                
                print(f"\n--- Processing {contract_period} ATR (lookback={atr_lookback}) with {tf} candles ---")
                
                # 5. Calculate ATR directly for each period dataset
                period_atr_data = {}
                for period, period_df in period_data.items():
                    # Prepare dataframe
                    df = period_df.copy()
                    df['period'] = df.index.floor(tf)
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
                            atr_period=atr_lookback                        )
                        # Pure forward-fill ATR values across all periods (no boundaries)
                        df['atr'] = df['atr'].ffill()
                    
                    # Store result (key columns needed)
                    period_atr_data[period] = df[['datetime', 'nanotime', 'tradeid', 'atr']].copy()
                
                # 6. Recombine ATR data back into contract_data for this period
                parts_by_key = {key: [] for key in period_codes}  # Initialize only for codes in this period

                # Process each period's data
                for period, period_df in period_atr_data.items():
                    # Add front position column for filtering
                    period_df = period_df.set_index('datetime').copy()  # Avoid modifying the original dataframe
                    period_df['front_position'] = get_front_position(period_df, period)
                    
                    # Assign each row to the appropriate contract based on front position
                    for i, contract_code in enumerate(period_codes, 1):  # Only enumerate over current period's codes
                        # Get rows corresponding to this position
                        matching_rows = period_df[period_df['front_position'] == i].copy()
                        
                        if not matching_rows.empty:
                            # Remove the temporary column and add to the appropriate list
                            matching_rows.drop(columns=['front_position'], inplace=True)
                            parts_by_key[contract_code].append(matching_rows)                # Concatenate all parts for each key
                for key in contract_data.keys():
                    if parts_by_key[key]:  # Only concat if we have parts
                        contract_data[key] = pd.concat(parts_by_key[key])

                print(f"ATR computed with lookback={atr_lookback} on {tf} candles.")
                print("ATR assigned by front:", {k: v['atr'].notna().sum() for k, v in contract_data.items()})

                # === REMOVE REPETITIVE VALUES ===
                print(f"\n--- Removing repetitive ATR values for {contract_period} {tf} ---")
                for contract_code in period_codes:
                    if contract_code in contract_data:
                        df = contract_data[contract_code].copy()
                        original_atr_count = df['atr'].notna().sum() if 'atr' in df.columns else 0
                        
                        # Remove repetitive ATR values - keep only values that are different from the previous value
                        if 'atr' in df.columns:
                            df['atr'] = df['atr'].where(
                                df['atr'] != df['atr'].shift(1)
                            )
                        
                        contract_data[contract_code] = df
                        new_atr_count = df['atr'].notna().sum() if 'atr' in df.columns else 0
                        
                        print(f"✅ {contract_code} - ATR values: {original_atr_count:,} -> {new_atr_count:,} (removed {original_atr_count-new_atr_count:,} repetitive)")
                
                print(f"✅ Removed repetitive ATR values. Only ATR changes are preserved.")

                # 7. Process predictors metadata and data insertion
                timeframe = tf

                for contract_code in period_codes:  # Process only current period's contract codes
                    # Create unique predictor name
                    pred_name = f"atr_{contract_code}_candles_{tf}_lookback_{atr_lookback}"
                    
                    # Determine what action to take
                    if pred_name in skip_completely:
                        print(f"⏭️ Skipping {pred_name} - predictor and entries already exist")
                        continue
                    
                    # Get or insert predictor metadata
                    atr_pred_id = None
                    
                    if pred_name in need_predictor_insert:
                        # Insert new predictor
                        print(f"🆕 Inserting new predictor: {pred_name}")
                        
                        main_contract = contract_code
                        description = f"ATR (Average True Range) for {contract_period} contracts, based on {timeframe} candles with lookback period of {atr_lookback}, repetitive values removed, NaN values preserved"
                        location = r"EnergyTrading\Python\prefect_data_orchestrator\datamart_inject\atr_inject_beta.py"
                        prod_strategy = None
                        author = "MatejKrajcovic"
                        additional = f"Uses compute_atr with lookback={atr_lookback} on {timeframe} candles. Pure ffill across periods, repetitive values removed, NaN values preserved in database. Contract period: {contract_period}"
                        
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
                    atr_pred_id = pred_id_result.iloc[0]['pred_id'] if not pred_id_result.empty else None

                    if atr_pred_id is None:
                        print(f"❌ Error: Could not retrieve pred_id for {pred_name}. Skipping data insertion.")
                        continue

                    print(f"📋 Using pred_id: {atr_pred_id} for predictor {pred_name}")

                    # 8. Insert ATR values for each trade into the experimental_dataset_entries table
                    if pred_name in need_predictor_insert or pred_name in need_entries_insert:
                        print(f"📊 Inserting entries for {pred_name}")
                        
                        # Step 1: Extract necessary columns
                        df = timestamps.copy()
                        
                        # Step 2: Merge with ATR data
                        if contract_code in contract_data and 'atr' in contract_data[contract_code].columns:
                            df_with_atr = df.merge(
                                contract_data[contract_code].reset_index()[['datetime', 'nanotime', 'tradeid', 'atr']],
                                on=['datetime', 'nanotime', 'tradeid'],
                                how='left'
                            )

                            df_with_atr.rename(columns={'atr': 'pred_value'}, inplace=True)                            
                            # Add pred_id column
                            df_with_atr['pred_id'] = atr_pred_id
                            
                            # Sort by datetime for consistent processing
                            df_with_atr = df_with_atr.sort_values(by=['datetime', 'nanotime', 'pred_id'], ascending=[True, True, True])
                            
                            # Flag missing values in logs but don't store in database (column doesn't exist)
                            mask_missing = df_with_atr['pred_value'].isna()
                            missing_count = mask_missing.sum()
                            if missing_count > 0:
                                print(f"⚠️ Note: {missing_count} rows have missing ATR values - these will be inserted as NaN in database")
                            
                            # Clean up and prepare for insertion (keep NaN values as they are)
                            df_with_atr['pred_value'] = df_with_atr['pred_value'].astype(float)
                            
                            # Keep only the columns that match the database schema
                            columns_to_keep = ['datetime', 'nanotime', 'tradeid', 'pred_id', 'pred_value']
                            df_final = df_with_atr[columns_to_keep].reset_index(drop=True)
                            # Drop duplicates based on unique constraint columns
                            df_final = df_final.drop_duplicates(subset=['datetime', 'nanotime', 'tradeid', 'pred_id']).copy()
                              # Insert in batches
                            batch_size = 100_000
                            conn._connect()
                            
                            total_rows = len(df_final)
                            for start in range(0, total_rows, batch_size):
                                end = min(start + batch_size, total_rows)
                                batch = df_final.iloc[start:end]
                                # Remove duplicates before insertion - specifically targeting the unique constraint columns
                                batch = batch.drop_duplicates(['datetime', 'nanotime', 'tradeid', 'pred_id'])
                                
                                try:
                                    batch.to_sql('experimental_dataset_entries', conn.engine, schema='public', index=False, if_exists='append', method='multi')
                                    print(f"✅ Inserted rows {start} to {end} into TimescaleDB for {atr_pred_id}.")
                                except Exception as e:
                                    print(f"❌ Error inserting batch {start}-{end} for {atr_pred_id}: {e}")
                            
                            print(f"🎉 All batches for {atr_pred_id} inserted successfully.")
                        else:
                            print(f"⚠️ No ATR data available for {contract_code}. Skipping database insertion.")

if __name__ == "__main__":
    main()

# To run this script directly, uncomment and execute the following line:
# main()
