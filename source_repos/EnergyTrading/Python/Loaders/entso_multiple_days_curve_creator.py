# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 21:13:23 2024

@author: krajcovic
"""

# -*- coding: utf-8 -*-
"""
Created on Sat Nov 16 16:36:00 2024

@author: krajcovic
"""

import pickle
import pandas as pd
import logging
import re
from datetime import datetime, timedelta
import os
from joblib import Parallel, delayed

file_path = r'C:\data\Data\Spot\Entso\Outages\outages_total.pkl'

with open(file_path, 'rb') as f:
    test = pickle.load(f)

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

def process_generation_unit(resource_mrid, gen_units, fcst_date):
    psr_type_data = {}
    for gen_unit_mrid, outages in gen_units.items():
        all_outages_data = []
        psr_type = None

        for outage_mrid, versions in outages.items():
            # Find the nearest created_date_time before fcst_date (consider all outages)
            valid_dates = [
                dt for dt, data in versions.items()
                if dt <= fcst_date
            ]

            if not valid_dates:
                continue

            closest_date = max(valid_dates)
            outage_data = versions[closest_date]

            # Only proceed if the selected outage is active
            if outage_data.get("doc_status") != "Active":
                continue

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
            combined_data = combined_data.resample('1h').mean()

            if psr_type not in psr_type_data:
                psr_type_data[psr_type] = combined_data
            else:
                psr_type_data[psr_type] = psr_type_data[psr_type].add(combined_data, fill_value=0)
        else:
            # Insert an empty DataFrame if no valid outage data is found
            if psr_type not in psr_type_data:
                psr_type_data[psr_type] = pd.DataFrame(columns=["Outage (MW)"])

    return psr_type_data


# Function for building outage curves for generation units
def get_outage_curves_for_all_units(whole_dict, fcst_dates, grids, output_folder):
    # Extract the relevant data for all generation units and forecast dates
    for grid in grids:
        if grid not in whole_dict:
            logging.warning(f"Grid {grid} not found in the provided data.")
            continue

        grid_data = whole_dict[grid]
        resource_dict = grid_data.get("resource_dict", {})

        for fcst_date in fcst_dates:
            psr_type_data = Parallel(n_jobs=-1)(
                delayed(process_generation_unit)(resource_mrid, gen_units, fcst_date)
                for resource_mrid, gen_units in resource_dict.items()
            )

            # Combine the results from parallel processing
            combined_psr_type_data = {}
            for data in psr_type_data:
                for psr_type, df in data.items():
                    if psr_type not in combined_psr_type_data:
                        combined_psr_type_data[psr_type] = df
                    else:
                        combined_psr_type_data[psr_type] = combined_psr_type_data[psr_type].add(df, fill_value=0)

            # Save the aggregated data for each psr_type to parquet for each forecast date
            output_file = os.path.join(output_folder, f"outage_curve_{grid}_{fcst_date.strftime('%Y%m%d')}.parquet")
            combined_psr_data = pd.concat(combined_psr_type_data.values(), keys=combined_psr_type_data.keys())
            combined_psr_data.index.names = ['PsrType', 'Timestamp']
            combined_psr_data.to_parquet(output_file)

# Example usage
fcst_dates = pd.date_range(datetime(2019,1,1,12), datetime(2026,1,1,12),freq='D') # Example forecast dates
# grids =  ["10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YFR-RTE------C",
grids = ["10Y1001A1001A82H", "10YAT-APG------L", "10YBE----------2",
             "10YHU-MAVIR----U", "10YRO-TEL------P"]  # Example grid IDs
output_folder = r'C:\data\Data\Spot\Entso\Outages\Curves'

get_outage_curves_for_all_units(test, fcst_dates, grids, output_folder)
