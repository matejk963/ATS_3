#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Helper functions for contract processing in energy trading.

This module provides utility functions for handling energy trading contracts,
including month calculations, position determination, and contract data extraction.
"""

import pandas as pd
import numpy as np
from pandas import to_datetime
from pandas.tseries.offsets import MonthEnd, MonthBegin, BDay


def get_contract_by_position(contract_dict, position):
    """
    Return the contract DataFrame by ordinal position (1-based):
    1 = first key, 2 = second key, etc.
    
    Args:
        contract_dict: Dictionary of contract DataFrames
        position: Position index (1-based)
        
    Returns:
        DataFrame for the contract at the specified position
    """
    keys = list(contract_dict.keys())
    if position < 1 or position > len(keys):
        raise IndexError(f"Position {position} out of range")
    return contract_dict[keys[position-1]]


def eff_month(ts, pos):
    """
    Calculate effective month based on timestamp and position.
    
    Args:
        ts: Timestamp or DatetimeIndex
        pos: Position (months ahead, e.g. 1 for front month, 2 for second front)
        
    Returns:
        Timestamp of the effective month or Series of timestamps
        
    Notes:
        - If timestamp is in the last 2 business days of the month:
          - For pos=1: returns front+2 month (month after next)
          - For pos=2: returns front+3 month
        - Otherwise:
          - For pos=1: returns front+1 month (next month)
          - For pos=2: returns front+2 month
    """
    # Check if ts is a DatetimeIndex (multiple timestamps)
    if isinstance(ts, pd.DatetimeIndex):
        # Convert DatetimeIndex to Series with date values
        ts_series = pd.Series(ts)
        
        # Calculate next months for all timestamps at once
        next_month = ts_series.dt.to_period('M').dt.to_timestamp() + MonthBegin(pos)
        next_month2 = ts_series.dt.to_period('M').dt.to_timestamp() + MonthBegin(pos+1)        # Get current month's end date for each timestamp
        cutoff = ts_series.dt.to_period('M').dt.to_timestamp() + MonthEnd()
        
        # Create a Series to store results with the same index as the original ts (DatetimeIndex)
        result = pd.Series(index=ts)
        
        # Create a simple version with integer index for processing
        months = cutoff.reset_index(drop=True)
        dates = ts_series.dt.date.reset_index(drop=True)
        next_m = next_month.reset_index(drop=True)
        next_m2 = next_month2.reset_index(drop=True)
        
        # Process each unique month end separately
        for month_end in months.unique():
            # Get the last two business days for this month
            last_two = pd.bdate_range(end=month_end, periods=2).date
            
            # Find positions (integer indices) in this month
            month_positions = months[months == month_end].index
            
            # For each position in this month
            for pos in month_positions:
                # Check if date is in last two business days
                if dates[pos] in last_two:
                    # Use month+2 if in last two days
                    result.iloc[pos] = next_m2.iloc[pos]
                else:
                    # Use month+1 otherwise
                    result.iloc[pos] = next_m.iloc[pos]
            
        return result
        
    else:
        # Handle single timestamp case
        # First day of next month (front+1)
        next_month = ts.to_period('M').to_timestamp() + MonthBegin(pos)
        next_month2 = ts.to_period('M').to_timestamp() + MonthBegin(pos+1)
        
        # Get current month's end date
        cutoff = (ts.to_period('M').to_timestamp() + MonthEnd())
        
        # Get the last two business days of the month
        last_two = pd.bdate_range(end=cutoff, periods=2).date
        
        # Check if timestamp is in the last two business days
        is_last_two_bdays = ts.date() in last_two
        
        # Calculate base month (front+1 or front+2 depending on last 2 bdays)
        base_month = next_month2 if is_last_two_bdays else next_month
        
        return base_month


def add_month_ahead_flags(df):
    """
    Add month-ahead flags to DataFrame.
    
    Assumes df.index is a DatetimeIndex and df['eff_month'] is a Timestamp
    of the 1st of the "front‐month" (i.e. already computed with your 2-BD bump).
    
    Produces:
      - month_diff: how many months ahead eff_month is vs. the row's own month
      - dem1: True when month_diff == 1
      - dem2: True when month_diff == 2
      
    Args:
        df: DataFrame with eff_month column
        
    Returns:
        DataFrame with added month_diff, dem1, and dem2 columns
    """
    df = df.copy()
    # This row's own month as Period
    own = df.index.to_period('M')
    # The effective front-month as Period
    eff = pd.to_datetime(df['eff_month']).dt.to_period('M')
    
    # Compute raw month difference
    df['month_diff'] = (eff.year*12 + eff.month) - (own.year*12 + own.month)
    
    # Flags
    df['dem1'] = df['month_diff'] == 1
    df['dem2'] = df['month_diff'] == 2
    
    return df


def get_front_position(df, target_month):
    """
    Determine the front month position for each datetime in the DataFrame
    given a target month.
    
    Args:
        df: DataFrame with DatetimeIndex
        target_month: Target month in 'YYYY-MM' format (e.g., '2025-05')
        
    Returns:
        Series with front position values (1 = front month, 2 = second front, etc.)
        
    Notes:
        - This function does the opposite of eff_month:
          - If a timestamp is in the last 2 business days of the month:
            For effective month M, position is:
              - M-2 months = position 1 (front month)
              - M-3 months = position 2 (second front)
          - Otherwise:
            For effective month M, position is:
              - M-1 month = position 1 (front month)
              - M-2 months = position 2 (second front)
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("DataFrame index must be a DatetimeIndex")
    
    # Parse target month
    target_date = pd.Timestamp(f"{target_month}-01")
    target_period = target_date.to_period('M')
    
    # Initialize result Series
    result = pd.Series(index=df.index)
    
    # Convert index to Series for processing
    ts_series = pd.Series(df.index)
    
    # Process timestamps with vectorized operations
    # Get current month end date for each timestamp
    month_ends = ts_series.dt.to_period('M').dt.to_timestamp() + MonthEnd()
    
    # Create integer-indexed versions for processing
    dates = ts_series.dt.date.reset_index(drop=True)
    
    # Process each timestamp and assign its position
    for idx, ts in enumerate(ts_series):
        # Get the last two business days of the timestamp's month
        month_end = ts.to_period('M').to_timestamp() + MonthEnd()
        last_two_bdays = pd.bdate_range(end=month_end, periods=2).date
        
        # Check if timestamp is in the last two business days
        is_last_two_bdays = ts.date() in last_two_bdays
        
        # Calculate month difference between target and the timestamp's month
        ts_period = ts.to_period('M')
        month_diff = (target_period.year * 12 + target_period.month) - \
                     (ts_period.year * 12 + ts_period.month)
        
        # Determine position based on month difference and whether it's last 2 bdays
        if is_last_two_bdays:
            # In last 2 business days: 
            # pos=1 is target_month - 2, pos=2 is target_month - 3
            if month_diff == 2:
                result.iloc[idx] = 1  # front month
            elif month_diff == 3:
                result.iloc[idx] = 2  # second front
            else:
                result.iloc[idx] = None  # Neither front nor second front
        else:
            # Not in last 2 business days:
            # pos=1 is target_month - 1, pos=2 is target_month - 2
            if month_diff == 1:
                result.iloc[idx] = 1  # front month
            elif month_diff == 2:
                result.iloc[idx] = 2  # second front
            else:
                result.iloc[idx] = None  # Neither front nor second front
    
    return result

def generate_contract_codes(period_type, positions=None):
    """
    Generate contract codes based on period type and positions.
    
    Args:
        period_type: One of 'M' (month), 'Q' (quarter), or 'Y' (year)
        positions: List of positions to generate (default: [1, 2])
    
    Returns:
        List of contract codes for the specified period type and positions
    
    Examples:
        generate_contract_codes('M', [1, 2]) -> ['dem1', 'dem2']
        generate_contract_codes('Q', [1, 2]) -> ['deq1', 'deq2']
        generate_contract_codes('Y', [1, 2, 3]) -> ['dey1', 'dey2', 'dey3']
    """
    if positions is None:
        positions = [1, 2]
    
    period_map = {
        'M': 'm',
        'Q': 'q',
        'Y': 'y'
    }
    
    period_code = period_map.get(period_type.upper())
    if not period_code:
        raise ValueError(f"Invalid period type: {period_type}. Must be one of: 'M', 'Q', or 'Y'")
    
    return [f"de{period_code}{pos}" for pos in positions]
