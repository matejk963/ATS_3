# -*- coding: utf-8 -*-
"""
Created on Wed Nov  6 15:14:07 2024

@author: scasny
"""

import numpy as np
from datetime import datetime, timedelta

class Mock():
    def mock_sparsity(size=None):
        if size:
            return [round(min(np.random.gamma(1, 0.5)/2, 1), 2) for _ in range(size)]
        else:
            return round(min(np.random.gamma(1, 0.5)/2, 1), 2)
    
    def mock_datetime(interval: timedelta, rate=60):
        start_time = datetime(2023, 1, 1, 8, 0)  # January 1, 2023, at 8 AM
        generate_timediff = lambda: np.random.exponential(rate)
        initial_datetime = start_time + timedelta(seconds=generate_timediff())
        
        # Ensure the initial datetime is within the allowed hours
        if not (8 <= initial_datetime.hour < 18):
            initial_datetime = initial_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
        
        datetime_sequence = [initial_datetime]
        
        while datetime_sequence[-1] < (start_time + interval):
            next_datetime = datetime_sequence[-1] + timedelta(seconds=generate_timediff())
            
            # Check if next datetime is within 8 AM to 6 PM
            if 8 <= next_datetime.hour < 18:
                datetime_sequence.append(next_datetime)
            else:
                # If not, skip to the next day at 8 AM
                next_datetime = next_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
                next_datetime += timedelta(days=1)
                datetime_sequence.append(next_datetime)
                
        # Ensure we only include datetimes within the specified interval
        datetime_sequence = [dt for dt in datetime_sequence if dt < start_time + interval]
        
        return datetime_sequence
    
    def mock_trade_prices(datetime_seq, base, std=0.1):
        # Generate random normal values with mean=0 and std=0.1
        random_increments = np.round(np.random.normal(0, std, len(datetime_seq)), 2)
        
        # Create cumulative sum starting from the base value
        cumulative_values = np.cumsum(np.insert(random_increments, 0, base))[:-1]
        
        # Combine the datetime_seq and cumulative values into a 2D array
        result_array = np.column_stack((datetime_seq, np.round(cumulative_values, 2)))
        
        return result_array



