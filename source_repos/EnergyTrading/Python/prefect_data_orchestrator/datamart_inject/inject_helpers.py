#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Inject Helpers Module

This module contains helper functions for injecting calculated data
into the TimescaleDB database. These functions are used by multiple
injection scripts such as ATR and MACD injections.
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


def eff_month(ts, pos, period_type='M'):
    """
    Calculate effective period (month/quarter/year) based on timestamp and position.
    period_type: 'M' (month), 'Q' (quarter), 'Y' (year)
    """
    if isinstance(ts, pd.DatetimeIndex):
        ts_series = pd.Series(ts)
        if period_type == 'M':
            # Monthly logic
            next_period = ts_series.dt.to_period('M').dt.to_timestamp() + MonthBegin(pos)
            next_period2 = ts_series.dt.to_period('M').dt.to_timestamp() + MonthBegin(pos+1)
            cutoff = ts_series.dt.to_period('M').dt.to_timestamp() + MonthEnd()
            result = pd.Series(index=ts, dtype=object)
            months = cutoff.reset_index(drop=True)
            dates = ts_series.dt.date.reset_index(drop=True)
            next_m = next_period.reset_index(drop=True)
            next_m2 = next_period2.reset_index(drop=True)
            for month_end in months.unique():
                last_two = pd.bdate_range(end=month_end, periods=2).date
                month_positions = months[months == month_end].index
                for idx in month_positions:
                    if dates[idx] in last_two:
                        result.iloc[idx] = next_m2.iloc[idx]
                    else:
                        result.iloc[idx] = next_m.iloc[idx]
            return result
        elif period_type == 'Q':
            # Quarterly logic
            quarters = ts_series.dt.month.apply(lambda m: (m - 1) // 3 + 1)
            years = ts_series.dt.year
            # First day of next quarter
            next_q = pd.to_datetime({
                'year': years + ((quarters + pos - 1) // 4),
                'month': ((quarters + pos - 1) % 4) * 3 + 1,
                'day': 1
            })
            next_q2 = pd.to_datetime({
                'year': years + ((quarters + pos) // 4),
                'month': ((quarters + pos) % 4) * 3 + 1,
                'day': 1
            })
            # Quarter end
            q_end = (ts_series.dt.to_period('Q').dt.end_time).dt.normalize()
            result = pd.Series(index=ts, dtype=object)
            dates = ts_series.dt.date.reset_index(drop=True)
            q_ends = q_end.reset_index(drop=True)
            next_q = next_q.reset_index(drop=True)
            next_q2 = next_q2.reset_index(drop=True)
            for qtr_end in q_ends.unique():
                last_two = pd.bdate_range(end=qtr_end, periods=2).date
                qtr_positions = q_ends[q_ends == qtr_end].index
                for idx in qtr_positions:
                    if dates[idx] in last_two:
                        result.iloc[idx] = next_q2.iloc[idx]
                    else:
                        result.iloc[idx] = next_q.iloc[idx]
            return result
        elif period_type == 'Y':
            # Yearly logic
            years = ts_series.dt.year
            next_y = pd.to_datetime({'year': years + pos, 'month': 1, 'day': 1})
            next_y2 = pd.to_datetime({'year': years + pos + 1, 'month': 1, 'day': 1})
            y_end = pd.to_datetime({'year': years, 'month': 12, 'day': 31})
            result = pd.Series(index=ts, dtype=object)
            dates = ts_series.dt.date.reset_index(drop=True)
            y_ends = y_end.reset_index(drop=True)
            next_y = next_y.reset_index(drop=True)
            next_y2 = next_y2.reset_index(drop=True)
            for year_end in y_ends.unique():
                last_two = pd.bdate_range(end=year_end, periods=2).date
                year_positions = y_ends[y_ends == year_end].index
                for idx in year_positions:
                    if dates[idx] in last_two:
                        result.iloc[idx] = next_y2.iloc[idx]
                    else:
                        result.iloc[idx] = next_y.iloc[idx]
            return result
        else:
            raise ValueError("period_type must be 'M', 'Q', or 'Y'")
    else:
        # Single timestamp
        if period_type == 'M':
            next_period = ts.to_period('M').to_timestamp() + MonthBegin(pos)
            next_period2 = ts.to_period('M').to_timestamp() + MonthBegin(pos+1)
            cutoff = ts.to_period('M').to_timestamp() + MonthEnd()
            last_two = pd.bdate_range(end=cutoff, periods=2).date
            is_last_two_bdays = ts.date() in last_two
            return next_period2 if is_last_two_bdays else next_period
        elif period_type == 'Q':
            quarter = (ts.month - 1) // 3 + 1
            year = ts.year
            def q_start(y, q):
                return pd.Timestamp(year=y, month=(q-1)*3+1, day=1)
            next_q = q_start(year + ((quarter + pos - 1) // 4), ((quarter + pos - 1) % 4) + 1)
            next_q2 = q_start(year + ((quarter + pos) // 4), ((quarter + pos) % 4) + 1)
            q_end = (ts.to_period('Q').end_time).normalize()
            last_two = pd.bdate_range(end=q_end, periods=2).date
            is_last_two_bdays = ts.date() in last_two
            return next_q2 if is_last_two_bdays else next_q
        elif period_type == 'Y':
            year = ts.year
            next_y = pd.Timestamp(year=year+pos, month=1, day=1)
            next_y2 = pd.Timestamp(year=year+pos+1, month=1, day=1)
            y_end = pd.Timestamp(year=year, month=12, day=31)
            last_two = pd.bdate_range(end=y_end, periods=2).date
            is_last_two_bdays = ts.date() in last_two
            return next_y2 if is_last_two_bdays else next_y
        else:
            raise ValueError("period_type must be 'M', 'Q', or 'Y'")


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


def get_front_position(df, target_period):
    """
    Determine the front position for each datetime in the DataFrame
    given a target period (month, quarter, or year). Vectorized implementation.
    
    Args:
        df: DataFrame with DatetimeIndex
        target_period: Target period in 'YYYY-MM' format (e.g., '2025-05') for months,
                      'YYYY-QN' format (e.g., '2025-Q1') for quarters,
                      'YYYY' format (e.g., '2025') for years
        
    Returns:
        Series with front position values (1 = front period, 2 = second front, etc.)
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("DataFrame index must be a DatetimeIndex")
        
    dates = pd.Series(df.index)
    
    # Determine period type based on format
    if '-' not in str(target_period):  # Year format 'YYYY'
        period_type = 'Y'
        target_year = int(target_period)
    elif 'Q' in str(target_period):  # Quarter format 'YYYY-QN'
        period_type = 'Q'
        year_str, quarter_str = target_period.split('-')
        target_year = int(year_str)
        target_quarter = int(quarter_str[1])
    else:  # Month format 'YYYY-MM'
        period_type = 'M'
        # Parse target month
        target_date = pd.Timestamp(f"{target_period}-01")
        target_period_obj = target_date.to_period('M')
    
    # Process based on period type
    if period_type == 'M':
        # Calculate period ends for all dates at once
        period_ends = dates.dt.to_period('M').dt.to_timestamp() + MonthEnd()
        
        # Create a DataFrame to hold all calculations
        calc_df = pd.DataFrame({
            'date': dates,
            'period_end': period_ends
        })
        
        # Calculate month difference for each date
        calc_df['ts_period'] = calc_df['date'].dt.to_period('M')
        calc_df['period_diff'] = (
            (target_period_obj.year * 12 + target_period_obj.month) - 
            (calc_df['ts_period'].dt.year * 12 + calc_df['ts_period'].dt.month)
        )
        
        # Identify last two business days for each unique period end
        is_last_two_bdays = pd.Series(False, index=calc_df.index)
        
        # Process each unique period end
        for period_end in calc_df['period_end'].unique():
            # Get last two business days for this period
            last_two_bdays = pd.bdate_range(end=period_end, periods=2)
            # Find indices where date is in the last two business days
            # Convert both to date-only for comparison
            mask = calc_df['date'].dt.date.isin(last_two_bdays.date)
            is_last_two_bdays[mask] = True
        
        calc_df['is_last_two_bdays'] = is_last_two_bdays
        
        # Apply vectorized logic for position determination
        # Create mask for front position (pos=1) and second front position (pos=2)
        front_condition = (
            (calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 2)) |
            (~calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 1))
        )
        second_front_condition = (
            (calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 3)) |
            (~calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 2))
        )
        
        # Create a temporary Series with the calculated positions
        result = pd.Series(0, index=calc_df.index)
        result[front_condition] = 1
        result[second_front_condition] = 2
        result.index = calc_df['date']  # Set index to match original dates
        
    elif period_type == 'Q':
        # Calculate quarter for each datetime
        quarters = dates.dt.month.apply(lambda m: (m - 1) // 3 + 1)
        years = dates.dt.year
        
        # Calculate quarter difference for each datetime
        date_qtr_units = years * 4 + quarters
        target_qtr_units = target_year * 4 + target_quarter
        period_diff = target_qtr_units - date_qtr_units
        
        # Create a DataFrame to hold all calculations
        calc_df = pd.DataFrame({
            'datetime': dates,
            'quarter': quarters,
            'year': years,
            'period_diff': period_diff
        })
        
        # Calculate quarter ends
        calc_df['quarter_end'] = calc_df.apply(
            lambda row: pd.Timestamp(row['year'], row['quarter'] * 3, 1) + MonthEnd(), 
            axis=1
        )
        
        # Identify last two business days for each quarter
        is_last_two_bdays = pd.Series(False, index=calc_df.index)
        
        # Process each unique quarter end
        for qtr_end in calc_df['quarter_end'].unique():
            last_two_bdays = pd.bdate_range(end=qtr_end, periods=2)
            # Find indices where datetime is in the last two business days
            mask = calc_df['datetime'].isin(last_two_bdays)
            is_last_two_bdays[mask] = True
            
        calc_df['is_last_two_bdays'] = is_last_two_bdays
        
        # Create mask for front position (pos=1) and second front position (pos=2)
        front_condition = (
            (calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 2)) |
            (~calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 1))
        )
        second_front_condition = (
            (calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 3)) |
            (~calc_df['is_last_two_bdays'] & (calc_df['period_diff'] == 2))
        )
        
        # Create a temporary Series with the calculated positions
        result = pd.Series(0, index=calc_df.index)
        result[front_condition] = 1
        result[second_front_condition] = 2
        result.index = calc_df['datetime']  # Set index to match original dates
    
    else:  # Year
        # Calculate year difference
        years = dates.dt.year
        period_diff = target_year - years
        
        # Create a DataFrame to hold all calculations
        calc_df = pd.DataFrame({
            'datetime': dates,
            'year': years,
            'period_diff': period_diff
        })
        
        # Calculate year ends
        calc_df['year_end'] = calc_df['year'].apply(lambda y: pd.Timestamp(y, 12, 31))
        
        # Identify last five business days for each year
        is_last_five_bdays = pd.Series(False, index=calc_df.index)
        
        # Process each unique year end
        for year_end in calc_df['year_end'].unique():
            last_five_bdays = pd.bdate_range(end=year_end, periods=5)
            # Find indices where datetime is in the last five business days
            mask = calc_df['datetime'].isin(last_five_bdays)
            is_last_five_bdays[mask] = True
            
        calc_df['is_last_five_bdays'] = is_last_five_bdays
        
        # Create mask for front position (pos=1) and second front position (pos=2)
        front_condition = (
            (calc_df['is_last_five_bdays'] & (calc_df['period_diff'] == 2)) |
            (~calc_df['is_last_five_bdays'] & (calc_df['period_diff'] == 1))
        )
        second_front_condition = (
            (calc_df['is_last_five_bdays'] & (calc_df['period_diff'] == 3)) |
            (~calc_df['is_last_five_bdays'] & (calc_df['period_diff'] == 2))
        )
        
        # Create a temporary Series with the calculated positions
        result = pd.Series(0, index=calc_df.index)
        result[front_condition] = 1
        result[second_front_condition] = 2
        result.index = calc_df['datetime']  # Set index to match original dates
    
    return result


def generate_contract_codes(period_type, positions=None):
    """
    Generate contract codes for a specified period type and positions.
    
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
