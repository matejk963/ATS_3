# %%

import os
import pickle
from datetime import datetime, timedelta
import pandas as pd
import logging
import re
from joblib import Parallel, delayed

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

tol = 1e-6

class OutageCurveCreator:
    def __init__(self, base_file_path, output_folder):
        self.base_file_path = base_file_path
        self.output_folder = output_folder
        self.gen_psr_map = {}

    def parse_resolution(self, resolution_str):
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

    def deduce_input_file_path(self, grid):
        return os.path.join(self.base_file_path, f"outages_{grid}_merged.pkl")

    def process_outage(self,gen_resource_mrid,
                       outage_mrid, versions, fcst_date, mandatory_columns):
        if outage_mrid == 'qQngIsYRi1HWjVmV6SbtLw':
            print('debug 39')
        valid_dates = [dt for dt in versions.keys() if dt <= fcst_date]
        if not valid_dates:
            logging.warning(f"No valid dates for outage {outage_mrid} of gen_resource {gen_resource_mrid} at {fcst_date}")
            return None
        
        closest_date = max(valid_dates)
        outage_data = versions[closest_date]

        if outage_data.get("doc_status") != "Active":
            logging.warning(f"Skipping outage {outage_mrid} due to inactive status")
            return None

        data_df = outage_data["data"].copy()
        if not all(value in data_df.columns for value in mandatory_columns):
            return None

        data_df["Outage (MW)"] = data_df["Installed (MW)"] - data_df["Quantity (MW)"]

        psr_type = outage_data.get("psr_type")

        if closest_date > outage_data.get("start_end", [None, None])[1]:
            return None

        if data_df.empty:
            return None
        
        last_row = pd.DataFrame(data_df.iloc[[-1]].values, 
                                index=[outage_data["start_end"][1]], 
                                columns=data_df.columns)
        data_df = pd.concat([data_df, last_row])

        # data_df = data_df.loc[fcst_date:].copy()
        resampled_data = data_df.resample('min').ffill().iloc[:-1].copy()
        resampled_data[closest_date] = resampled_data["Outage (MW)"]

        return resampled_data[[closest_date]], psr_type

    def process_generation_unit(self, resource_mrid, prod_units, fcst_date, 
                                mandatory_columns=["Quantity (MW)", "Installed (MW)"]):
        
        psr_type_data = {}
        psr_map = {}

        for gen_resource_mrid, gen_unit in prod_units.items():
            results = Parallel(n_jobs=-1)(
                delayed(self.process_outage)(gen_resource_mrid, outage_mrid, versions, fcst_date, mandatory_columns)
                for outage_mrid, versions in gen_unit.items()
            )
            

            all_outages_data = [res for res in results if res is not None]
            if all_outages_data:
                # Ensure all DataFrames have the same index type
                for i in range(len(all_outages_data)):
                    df, _ = all_outages_data[i]
                    if isinstance(df.index, pd.MultiIndex):
                        all_outages_data[i] = (df.set_index(df.index.to_flat_index()), _)
                
                combined_data = pd.concat([df for df, _ in all_outages_data], axis=1)
                combined_data = combined_data.dropna(axis=1, how='all')

                if combined_data.shape[1] > 0:
                    combined_data["Outage (MW)"] = combined_data.T.sort_index().T.ffill(axis=1).iloc[:, -1].copy()
                    combined_data = combined_data[["Outage (MW)"]]
                    combined_data = combined_data.groupby(combined_data.index).sum()
                    installed_capacity = combined_data["Outage (MW)"].max()
                    combined_data["Outage (MW)"] = combined_data["Outage (MW)"].clip(upper=installed_capacity)
                    combined_data = combined_data.resample('1h').mean()
                    combined_data = combined_data.loc[fcst_date:].copy()

                    psr_type_data[gen_resource_mrid] = combined_data

                for _, psr_type in all_outages_data:
                    psr_map[gen_resource_mrid] = psr_type

        return psr_type_data, psr_map

    def get_outage_curves_for_all_units(self, grid, fcst_dates):
        input_file = self.deduce_input_file_path(grid)
        if not os.path.exists(input_file):
            logging.error(f"Input file not found for grid {grid}: {input_file}")
            return
        # input_file = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/outages_10YHU-MAVIR----U_20240101_20240129.pkl'
        with open(input_file, 'rb') as f:
            whole_dict = pickle.load(f)

        if grid not in whole_dict:
            logging.warning(f"Grid {grid} not found in the provided data.")
            return

        grid_data = whole_dict[grid]
        resource_dict = grid_data.get("resource_dict", {})

        for fcst_date in fcst_dates:

            
            results = Parallel(n_jobs=-1)(
                delayed(self.process_generation_unit)(resource_mrid, prod_units, fcst_date)
                for resource_mrid, prod_units in resource_dict.items()
            )

            combined_psr_type_data = {}
            self.gen_psr_map = {}  # Reset the map before updating it

            for psr_type_data, psr_map in results:
                self.gen_psr_map.update(psr_map)  # Aggregate all psr mappings

                for gen_resource_mrid, df in psr_type_data.items():
                    psr_type = self.gen_psr_map.get(gen_resource_mrid, "Unknown")
                    if psr_type not in combined_psr_type_data:
                        combined_psr_type_data[psr_type] = df
                    else:
                        combined_psr_type_data[psr_type] = combined_psr_type_data[psr_type].add(df, fill_value=0)

            output_file = os.path.join(self.output_folder, f"outage_curve_{grid}_{fcst_date.strftime('%Y%m%d')}.parquet")
            if combined_psr_type_data:
                combined_psr_data = pd.concat(combined_psr_type_data.values(), keys=combined_psr_type_data.keys())
                if combined_psr_data.shape[0] > tol:
                    combined_psr_data.index.names = ['PsrType', 'Timestamp']
                    combined_psr_data.to_parquet(output_file)


# Example usage
if __name__ == "__main__":
    base_file_path = '//192.168.10.91/d/data/Data/Spot/Entso/Outages'
    output_folder = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/Curves'
    grid = "10YHU-MAVIR----U"
    fcst_dates = pd.date_range(datetime(2024, 12, 31, 12), datetime(2024, 12, 31, 12), freq='D')

    processor = OutageCurveCreator(base_file_path, output_folder)
    processor.get_outage_curves_for_all_units(grid, fcst_dates)

# %%
