# -*- coding: utf-8 -*-
"""
Created on Sat Nov 16 16:36:00 2024

@author: krajcovic
"""

import pickle

file_path = r'//192.168.10.91/data/Data/Spot/Entso/Outages/outages_total.pkl'

with open(file_path, 'rb') as f:
    test = pickle.load(f)
    
import pandas as pd
import logging
import re
from datetime import timedelta

def parse_resolution(resolution_str):
    match = re.match(r'PT(\d+)([HMS])', resolution_str)
    if match:
        value, unit = match.groups()
        value = int(value)
        if unit == 'M':
            return timedelta(minutes=value)
        elif unit == 'H':
            return timedelta(hours=value)
        elif unit == 'S':
            return timedelta(seconds=value)
    return None

# Placeholder function for building outage curves for generation units
def get_outage_curves_for_all_units(whole_dict, fcst_dates):
    # Extract the relevant data for all generation units and forecast dates
    curves = {}

    for grid, grid_data in whole_dict.items():
        resource_dict = grid_data.get("resource_dict", {})

        for fcst_date in fcst_dates:
            psr_type_data = {}

            for resource_mrid, gen_units in resource_dict.items():
                for gen_unit_mrid, outages in gen_units.items():
                    all_outages_data = []
                    psr_type = None

                    for outage_mrid, versions in outages.items():
                        # Find the nearest created_date_time before fcst_date
                        valid_dates = [dt for dt in versions.keys() if dt <= fcst_date]
                        
                        if not valid_dates:
                            continue
                        
                        closest_date = max(valid_dates)
                        outage_data = versions[closest_date]
                        
                        # Handle multiple resolutions
                        data_df = outage_data["data"].copy()
                        data_df["Outage (MW)"] = data_df["Installed (MW)"] - data_df["Quantity (MW)"]
                        resolutions = outage_data.get("resolution", [])
                        resolution_change_dates = outage_data.get("resolution_change_dates", [])
                        start_time, end_time = outage_data.get("start_end", [None, None])
                        psr_type = outage_data.get("psr_type")

                        if start_time is None or end_time is None:
                            logging.warning("Missing start or end time for outage data.")
                            continue

                        # Insert the end date as a final point to ensure proper resampling limits
                        if len(data_df) < 1:
                            continue
                        else:
                            data_df.loc[end_time] = data_df.iloc[-1]

                        # Resample each part of the data to its resolution and then to minutes
                        if isinstance(resolutions, list) and len(resolutions) > 1:
                            resampled_data = pd.DataFrame()
                        
                            for i in range(len(resolutions)):
                                # Start time for the resolution
                                res_start_time = resolution_change_dates[i] if i < len(resolution_change_dates) else data_df.index.min()
                        
                                # End time for the resolution
                                if i < len(resolutions) - 1:
                                    res_end_time = resolution_change_dates[i + 1]
                                else:
                                    res_end_time = data_df.index.max()
                        
                                # Slice data for this specific resolution
                                resolution_data = data_df.loc[(data_df.index >= res_start_time) & (data_df.index <= res_end_time)]
                        
                                # Parse and use the resolution to resample the data
                                interval_delta = parse_resolution(resolutions[i])
                                if interval_delta is None:
                                    logging.warning(f"Unsupported resolution: {resolutions[i]}")
                                    continue
                        
                                # Resample the data to its resolution interval using forward fill
                                resolution_data_resampled = resolution_data.resample(interval_delta).ffill()
                        
                                # Resample to minute-level granularity using forward fill
                                resolution_data_resampled = resolution_data_resampled.resample('1min').ffill()
                        
                                # Combine the resampled data
                                resampled_data = pd.concat([resampled_data, resolution_data_resampled])
                        
                        else:
                            # Handle the case of a single resolution
                            interval_delta = parse_resolution(resolutions[0]) if isinstance(resolutions, list) and resolutions else None
                            if interval_delta is None:
                                logging.warning(f"Unsupported resolution: {resolutions}")
                                continue
                        
                            # Resample to the resolution interval using forward fill
                            resampled_data = data_df.resample(interval_delta).ffill()
                        
                            # Resample to minute-level granularity using forward fill
                            resampled_data = resampled_data.resample('1min').ffill()
                        
                        # Ensure that the final resampled data covers the entire period from start to end date
                        resampled_data = resampled_data.reindex(pd.date_range(start_time, end_time, freq='1min'), method='ffill').fillna(0)

                        # Keep only the "Outage (MW)" column
                        resampled_data = resampled_data[["Outage (MW)"]]

                        # Store the resampled data in the list of all outages for the generation unit
                        all_outages_data.append(resampled_data)

                    if all_outages_data:
                        # Concatenate all outage dataframes for the generation unit
                        combined_data = pd.concat(all_outages_data)
                        combined_data = combined_data.groupby(combined_data.index).sum()

                        # Cap the combined data to the maximum installed capacity from data_df
                        installed_capacity = data_df["Installed (MW)"].max()
                        combined_data["Outage (MW)"] = combined_data["Outage (MW)"].clip(upper=installed_capacity)

                        # Resample the combined data to hourly granularity using mean
                        combined_data = combined_data.resample('1h').mean().fillna(0)

                        if psr_type not in psr_type_data:
                            psr_type_data[psr_type] = combined_data
                        else:
                            psr_type_data[psr_type] = psr_type_data[psr_type].add(combined_data, fill_value=0)
                    else:
                        # Insert an empty DataFrame if no valid outage data is found
                        if psr_type not in psr_type_data:
                            psr_type_data[psr_type] = pd.DataFrame(columns=["Outage (MW)"])

            # Add the aggregated data for each psr_type to the curves dictionary for each forecast date
            if grid not in curves:
                curves[grid] = {}
            curves[grid][fcst_date] = psr_type_data

    return curves

# Example usage
fcst_dates = [pd.Timestamp("2024-11-18")]  # Example forecast dates
grid = "10YHU-MAVIR----U"  # Example grid ID
curves = get_outage_curves_for_all_units({grid: test[grid]}, fcst_dates)

if curves is None:
    print("No valid outage data found for the given forecast date and generation unit.")
