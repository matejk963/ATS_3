import pandas as pd
import sys
import os

# Add the project root to sys.path to allow imports from other top-level directories like 'Database'
# Script location: Strategies/mm_MACD/analysis/
# Project root: ../../.. (relative to script location)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from Database.mcp.test.mcp_query import run_mcp_query
except ImportError as e:
    print(f"Error importing run_mcp_query: {e}")
    print("Please ensure that mcp_query.py is in Database/mcp/test/ and the project structure is correct.")
    print(f"Current sys.path includes: {project_root}")
    sys.exit(1)

# --- Dynamic MACD pred_id discovery for dem1 5min ---
def discover_macd_pred_ids_for_dem1_5min():
    """
    Query experimental_predictors for all MACD-related pred_ids for dem1 5min candles (all components).
    Returns a dict: {user_friendly_key: pred_id}
    """
    # This pattern matches all MACD components for dem1 5min, e.g.:
    # macd_macd_dem1_candles_5min_params_12_26_9, macd_signal_dem1_candles_5min_params_12_26_9, macd_macd_hist_dem1_candles_5min_params_12_26_9
    query = (
        "SELECT pred_id FROM \"public\".\"experimental_predictors\" "
        "WHERE pred_id LIKE 'macd_%_dem1_candles_5min_params_%'"
    )
    df = run_mcp_query(query)
    macd_pred_ids = {}
    if not df.empty and 'pred_id' in df.columns:
        for pred_id in df['pred_id']:
            # Example pred_id: macd_signal_dem1_candles_5min_params_12_26_9
            parts = pred_id.split('_')
            if len(parts) >= 9:
                # parts[1] is component (macd, signal, macd_hist)
                component = parts[1]
                params = '_'.join(parts[-3:])  # e.g. 12_26_9
                # Map to user-friendly key
                if component == 'signal':
                    key = f"macd_signal_{params}"
                elif component == 'macd':  # fallback, but should not happen
                    key = f"macd_macd_{params}"
                elif component == 'macd_hist':
                    key = f"macd_hist_{params}"
                else:
                    key = f"macd_{component}_{params}"
                macd_pred_ids[key] = pred_id
    return macd_pred_ids

# --- Build PRED_IDS_CONFIG at runtime ---
def build_pred_ids_config():
    config = {
        "atr_21": "atr_dem1_candles_5min_lookback_21",
        "swing_high": "swing_high_dem1_candles_5min",
        "swing_low": "swing_low_dem1_candles_5min",
    }
    config.update(discover_macd_pred_ids_for_dem1_5min())
    return config

def fetch_single_indicator_data(column_name, pred_id_value):
    """
    Fetches data for a single indicator (pred_id) and renames the 'value' column
    to the specified column_name. Ensures 'tradeid' from DB is renamed to 'trade_id'.
    """
    print(f"Attempting to fetch data for {column_name} (pred_id: {pred_id_value})...")
    
    query = f"""
    SELECT datetime, nanotime, tradeid, pred_value
    FROM "public"."experimental_dataset_entries"
    WHERE pred_id = '{pred_id_value}'
    ORDER BY datetime, nanotime, tradeid;
    """ # Changed trade_id to tradeid in SELECT and ORDER BY
    print(f"Executing query: {query}")

    print("Before calling run_mcp_query...")
    results_df = run_mcp_query(query)
    print("After calling run_mcp_query...")

    print(f"Raw results_df for {column_name} from run_mcp_query:")
    print(results_df.head())
    print(f"results_df for {column_name} dtypes:")
    print(results_df.dtypes if not results_df.empty else "DataFrame is empty")

    if results_df.empty:
        print(f"No data returned for {column_name} (pred_id: {pred_id_value}). Returning empty DataFrame.")
        # Ensure returned DataFrame has 'trade_id' column for consistency
        return pd.DataFrame(columns=['datetime', 'nanotime', 'trade_id', column_name])

    # Ensure correct data types before pivot
    results_df['datetime'] = pd.to_datetime(results_df['datetime'])
    results_df['pred_value'] = pd.to_numeric(results_df['pred_value'], errors='coerce') # Use pred_value
    # Assuming 'tradeid' is already in a suitable format from the DB for pivoting

    print(f"results_df for {column_name} before pivot:")
    print(results_df.head())
    print(f"results_df for {column_name} dtypes before pivot:")
    print(results_df.dtypes)

    try:
        indicator_df = results_df.pivot_table(
            index=['datetime', 'nanotime', 'tradeid'], 
            values='pred_value', # Use pred_value
            aggfunc='first' 
        ).rename(columns={'pred_value': column_name}).reset_index() # Rename pred_value to column_name
        
        # Rename 'tradeid' to 'trade_id' for consistency with base_df and merge operations
        if 'tradeid' in indicator_df.columns:
            indicator_df.rename(columns={'tradeid': 'trade_id'}, inplace=True)
            print(f"Renamed 'tradeid' to 'trade_id' in indicator_df for {column_name}.")

    except Exception as e:
        print(f"Error during pivot for {column_name}: {e}")
        print("Data causing pivot error:")
        print(results_df)
        # Ensure returned DataFrame has 'trade_id' column for consistency
        return pd.DataFrame(columns=['datetime', 'nanotime', 'trade_id', column_name])

    print(f"Successfully fetched and processed data for {column_name}.")
    return indicator_df

def fetch_and_merge_indicators(base_df=None, indicators_to_fetch=None): # Added default base_df=None
    """
    Fetches data for specified indicators and merges them.
    If base_df is None, the first fetched indicator DataFrame becomes the base.

    Args:
        base_df (pd.DataFrame, optional): DataFrame with 'datetime', 'nanotime', 'trade_id'.
                                          'datetime' should be datetime objects. Defaults to None.
        indicators_to_fetch (list, optional): List of keys from PRED_IDS_CONFIG
                                              (e.g., ["atr_21", "macd_12_26_9"]).
                                              Defaults to all defined in PRED_IDS_CONFIG.

    Returns:
        pd.DataFrame: Merged DataFrame with indicator data.
    """
    if base_df is not None and not all(col in base_df.columns for col in ['datetime', 'nanotime', 'trade_id']):
        raise ValueError("If base_df is provided, it must contain 'datetime', 'nanotime', and 'trade_id' columns.")

    merged_df = base_df.copy() if base_df is not None else None

    # Use dynamic config
    PRED_IDS_CONFIG = build_pred_ids_config()

    if indicators_to_fetch is None:
        target_indicators = PRED_IDS_CONFIG
    else:
        target_indicators = {key: PRED_IDS_CONFIG[key] for key in indicators_to_fetch if key in PRED_IDS_CONFIG}

    if not target_indicators:
        print("No indicators specified or found in PRED_IDS_CONFIG.")
        return base_df if base_df is not None else pd.DataFrame()

    first_indicator = True
    for col_name_key, pred_id_val in target_indicators.items():
        indicator_df = fetch_single_indicator_data(col_name_key, pred_id_val)
        
        if indicator_df.empty:
            print(f"No data for {col_name_key}. Adding NaN column if a merged_df exists.")
            if merged_df is not None:
                 merged_df[col_name_key] = pd.NA
            continue

        if merged_df is None: # This happens if base_df was None and this is the first indicator with data
            merged_df = indicator_df
            print(f"Initialized merged_df with {col_name_key}. Shape: {merged_df.shape}")
            first_indicator = False # No longer the first, as merged_df is now set
        else:
            # Ensure merge keys are present in indicator_df if it's not the first one initializing merged_df
            if not all(col in indicator_df.columns for col in ['datetime', 'nanotime', 'trade_id']):
                print(f"Indicator {col_name_key} is missing one or more merge keys. Skipping merge.")
                merged_df[col_name_key] = pd.NA # Add NaN column as data cannot be merged
                continue
            
            merged_df = pd.merge(merged_df, indicator_df,
                                 on=['datetime', 'nanotime', 'trade_id'],
                                 how='outer' if first_indicator and base_df is None else 'left') # Use outer for the very first merge if no base_df
            print(f"Merged {col_name_key}. Shape after merge: {merged_df.shape}")
        
        if first_indicator and base_df is None:
            first_indicator = False


    # If merged_df is still None (e.g., all indicators returned empty data and no base_df)
    if merged_df is None:
        print("No data fetched for any indicator. Returning empty DataFrame.")
        return pd.DataFrame()
        
    return merged_df

if __name__ == "__main__":
    print("Running example usage of fetch_dem1_5min_indicators.py")
    print("Ensure MCP Server is running and accessible.")

    # --- Fetch all configured indicators and merge them ---
    print("\nFetching all configured indicators and merging them...")
    # Call without a base_df, it will use the first indicator as the base
    df_with_all_indicators = fetch_and_merge_indicators() 
    
    print("\nDataFrame merged with all indicators:")
    print(df_with_all_indicators.head())
    print(df_with_all_indicators.info()) # Use info() for better summary

    # --- Drop NA to see successfully merged rows ---
    if not df_with_all_indicators.empty:
        print("\nDataFrame after dropping rows where ALL indicators are NA (or any NA if that's preferred):")
        # Use the dynamic config to get indicator columns
        indicator_cols = list(build_pred_ids_config().keys())
        df_cleaned = df_with_all_indicators.dropna(subset=indicator_cols, how='all')
        print(df_cleaned.head())
        print(df_cleaned.info())
    else:
        print("\nMerged DataFrame is empty, nothing to clean or show.")

    # --- Example of fetching a subset (still without a base_df) ---
    # indicators_subset = ["atr_21", "swing_high"]
    # print(f"\\nFetching subset of indicators: {indicators_subset}...")
    # df_with_subset_indicators = fetch_and_merge_indicators(indicators_to_fetch=indicators_subset)
    # print("\\nDataFrame merged with subset of indicators:")
    # print(df_with_subset_indicators.head())
    # print(df_with_subset_indicators.info())

    # --- How to use in your Jupyter Notebook ---
    # print("\n--- Notebook Usage Example ---")
    # print("1. Ensure this script (fetch_dem1_5min_indicators.py) is in Strategies/mm_MACD/analysis/")
    # print("2. In your notebook, after loading your base 'timestamps' DataFrame (from public.trades):")
    # print("   Make sure 'timestamps' has 'datetime', 'nanotime', 'trade_id' columns.")
    # print("   timestamps['datetime'] = pd.to_datetime(timestamps['datetime']) # Ensure datetime type")
    # print("\n   from Strategies.mm_MACD.analysis.fetch_dem1_5min_indicators import fetch_and_merge_indicators")
    # print("   # Fetch all indicators defined in PRED_IDS_CONFIG:")
    # print("   # final_df = fetch_and_merge_indicators(timestamps.copy())")
    # print("   # Or fetch a specific list:")
    # print("   # my_indicators = ['atr_21', 'macd_12_26_9']")
    # print("   # final_df = fetch_and_merge_indicators(timestamps.copy(), indicators_to_fetch=my_indicators)")
    # print("   # print(final_df.head())")
    # print("   # print(final_df.info())")
    pass
