"""
Class for managing, calling and communicating with and among system classes

Master function: get_fcst_curves()
Process:
    1. Gather base data (both nominal and normalized)
    2. Collect scenarios based on base_data
"""

from fund_analysis import input_data, scenarios, models, utils
from fund_analysis.utils import ENUMS as enums
from itertools import product
import pandas as pd
import copy
import numpy as np
import datetime as dt
from itertools import combinations
import itertools
import os


class FairValueManager:
    
    def __init__(self, params_dict: dict,
                    fcst_range: list):
        self._params_dict = params_dict
        self._fcst_range = fcst_range
        self._predictors= ['AvailableCapacityData',
                            'ResidualDemand',
                            'Hydro', 'Wind', 'Temp',
                            'Gas', 'Coal', 'Eua']
        self.fcst_curves = {}
        self.scen_inst_dict = {}
        
        self._method_mapping = {
                "country_spreads": {
                    "method": self.calculate_country_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
                "period_spreads": {
                    "method": self.calculate_period_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
                "b_p_spreads": {
                    "method": self.calculate_base_peak_spreads,
                    "params": ["curve_pred_nominal", "base_products", "columns_dict"],
                },
                "css_spreads": {
                    "method": self.calculate_clean_spark_spreads,
                    "params": ["curve_pred_nominal", "base_products", "columns_dict", "fuel_data"],
                },
                "capa_spreads": {
                    "method": self.calculate_capa_spreads,
                    "params": ["curve_pred_nominal", "base_products", "columns_dict"],
                },
            }

        
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def fcst_range(self):
        return self._fcst_range
    
    @property
    def predictors(self):
        return self._predictors
    
    def update_predictors(self, new_predictors):
        self._predictors = new_predictors
    
    def data_assembly_inst(self, fcst_date, predictors):
        if not hasattr(self, '_data_assembly_inst'):
            self._data_assembly_inst = utils.ModelDataAssembly(self.params_dict,
                                        fcst_date, predictors)
        self._data_assembly_inst.update_fcst_date(fcst_date)
        return self._data_assembly_inst
    
    # Call for base data
    def call_for_base_data(self, fcst_date, predictors: list=[]):
        # Predictors used
        if len(predictors)<1:
            predictors = self.predictors
        else:
            self.update_predictors(predictors)
        
        # base_data = self.data_assembly_inst(fcst_date, predictors)\
        #     .create_base_data()
        # base_data_normalized = self.data_assembly_inst(fcst_date, predictors)\
        #     .create_base_data(normalized=True)
        
        base_data = self.data_assembly_inst(fcst_date, predictors)\
            .fetch_base_data()
        base_data_normalized = self.data_assembly_inst(fcst_date, predictors)\
            .fetch_base_data(normalized=True)
            
        return base_data, base_data_normalized
    
    def return_base_data(base_data, base_data_normalized):
        return base_data, base_data_normalized
    
    def scenarios_inst(self, predictor: str,
                        params: dict = None):
        # predictor atribute should be name of the predictor from the list
        scenarios_inst_mapping_dict = {
            'ext_data_scen_inst': scenarios.ExternalFundScenarios,
            'av_cap_scen_inst': scenarios.AvCapScenarios,
            'fuels_scen_inst': scenarios.FuelScenarios
        }
        scen_inst_name = f'{enums.get_scen_inst_from_type(predictor)}'
        if not scen_inst_name in self.scen_inst_dict:
            scen_class = scenarios_inst_mapping_dict[scen_inst_name]
            
            if scen_class is None:
                raise ValueError(f"Unknown scenario type: {predictor}")
            
            # Instantiate the scenario class, passing in the params dictionary as arguments
            self.scen_inst_dict[predictor] = scen_class(**params)
            
            if scen_inst_name in ['ext_data_scen_inst']:
                self.scen_inst_dict[predictor]\
                    .update_fund_type(predictor)
                    
    @staticmethod
    def merge_percentile_scenarios(scenario_dict):
        merged_percentile_data = {}

        # Loop through each percentile (10th, 20th, ..., 90th)
        for percentile in range(10, 100, 10):
            # Initialize a list to hold DataFrames for this percentile
            percentile_dfs = []

            for group_name, group_scenarios in scenario_dict.items():
                for scenario_name, df in group_scenarios.items():
                    # Skip "mean" in AvailableCapacityData group
                    if group_name == "AvailableCapacityData" and "mean" in scenario_name:
                        continue
                    
                    # Check if the scenario matches the current percentile
                    if f"{percentile}th" in scenario_name:
                        percentile_dfs.append(df)

            # Concatenate all DataFrames for the current percentile and store in the dictionary
            if percentile_dfs:
                merged_percentile_data[f"{percentile}th"] = pd.concat(percentile_dfs, axis=1)

        return merged_percentile_data
    
    # @staticmethod
    # def combine_scenarios(crude_scen_dict, base_data, exclude_groups=None):
    #     if exclude_groups is None:
    #         exclude_groups = []
        
    #     scen_dict = {}
        
    #     # Extract all groups and scenarios into a list, excluding specified groups
    #     groups = [group for group in crude_scen_dict.keys() if group not in exclude_groups]
    #     group_scenarios = [list(crude_scen_dict[group].items()) for group in groups]
        
    #     # Generate all unique combinations across different groups using Cartesian product
    #     combinations = product(*group_scenarios)
        
    #     # Combine DataFrames for each combination
    #     for i, combination in enumerate(combinations):
    #         scen_name = "_".join([scen for scen, _ in combination])
    #         combined_df = base_data['curve']['base'].copy()
    #         for _, scen_df in combination:
    #             combined_df[scen_df.columns] = scen_df
    #         scen_dict[scen_name] = combined_df
        
    #     return scen_dict

    @staticmethod
    def combine_scenarios(crude_scen_dict, base_data, exclude_groups=None):
        if exclude_groups is None:
            exclude_groups = []
        
        scen_dict = {}
        
        # Filter groups to exclude specified ones
        groups = [group for group in crude_scen_dict.keys() if group not in exclude_groups]
        
        # Step 1: Apply each group's scenarios to the base data individually
        for group in groups:
            for scen_name, scen_df in crude_scen_dict[group].items():
                combined_df = base_data['curve']['base'].copy()
                combined_df[scen_df.columns] = scen_df
                scen_dict[f"{scen_name}"] = combined_df
        
        # Step 2: Generate combinations of two distinct groups
        group_pairs = combinations(groups, 2)  # All pairwise combinations of groups
        
        for group1, group2 in group_pairs:
            for scen1_name, scen1_df in crude_scen_dict[group1].items():
                for scen2_name, scen2_df in crude_scen_dict[group2].items():
                    combined_df = base_data['curve']['base'].copy()
                    combined_df[scen1_df.columns] = scen1_df
                    combined_df[scen2_df.columns] = scen2_df
                    scen_name = f"{scen1_name}_{scen2_name}"
                    scen_dict[scen_name] = combined_df
        
        return scen_dict
                        
    def get_fcst_curves(self,model_params_dict:dict,
                        return_test_data=False,
                        master_params_dict: dict = {},
                        base_data={}, base_data_normalized={},
                        scaled_data = []):
        prediction_dict = {}
        prediction_nominal_dict = {}
        for fcst_date in self.fcst_range:
            print(f"{fcst_date} start of process at {dt.datetime.now()}")
            try:
                data_assembly_inst = self.data_assembly_inst(fcst_date=fcst_date,
                                                                predictors=self.predictors)
                # Call for base data
                if not base_data:        
                    print(f"base data compilation start at {dt.datetime.now()}")
                    base_data, base_data_normalized = self.call_for_base_data(fcst_date)
                    print(f"base data compilation end at {dt.datetime.now()}")
                # Collect scenarios
                crude_scen_dict = {}
                # Loop through each predictor and collect its scenarios
                # If master_params_dict will contain empty dict for given predictor
                #   default prams will be used
                if not master_params_dict:
                    for predictor in self.predictors:
                        scen_list = [a/100 for a in list(range(10,99, 10))]
                        scen_list_fuels = [a/100 for a in list(np.linspace(-30,30,9,
                                        retstep=False))]
                        if predictor in ['ResidualDemand']:
                            master_params_dict[predictor] = {'params': {
                                                                'fund_type': predictor,
                                                                'params_dict': self.params_dict},
                                                            'scen_type': {'historical' : scen_list}}
                        elif predictor in ['AvailableCapacityData']:
                            master_params_dict[predictor] = {'params': {
                                                                'params_dict': self.params_dict},
                                                            'scen_type': {'historical' : scen_list}}
                        elif predictor in ['Gas', 'Coal', 'Eua', 'mcr']:
                            master_params_dict[predictor] = {'params': {
                                                                'fuel_type': enums.fuel_names_map[predictor]},
                                                            'scen_type': {'defined': scen_list_fuels}}
                
    
                for predictor, params_dict in master_params_dict.items():
                    if predictor in ['ResidualDemand']:
                        params_dict['params'].update({'base_data': base_data,
                                                'base_data_normalized': base_data_normalized})
                    else:
                        params_dict['params'].update({'base_data': base_data})
                    self.scenarios_inst(predictor=predictor,
                                        params=params_dict['params'])
                    if predictor in ['ResidualDemand']:
                        print(f"{predictor} scenarios generation start at {dt.datetime.now()}")
                        crude_scen_dict[predictor] = self.scen_inst_dict[predictor]\
                            .get_scenarios(scen_type=params_dict['scen_type'],
                                           fcst_date=fcst_date)
                        print(f"{predictor} scenarios generation end at {dt.datetime.now()}")
                    else:
                        print(f"{predictor} scenarios generation start at {dt.datetime.now()}")
                        crude_scen_dict[predictor] = self.scen_inst_dict[predictor]\
                            .get_scenarios(scen_type=params_dict['scen_type'])
                        print(f"{predictor} scenarios generation end at {dt.datetime.now()}")
                    if predictor in ['AvailableCapacityData']:
                        extended_mean = self.scen_inst_dict[predictor].fill_base_curve(crude_scen_dict[predictor]['mean'],
                                                                                    self.scen_inst_dict[predictor].inst_data['curve'],
                                                                                    fill_type='inst')
                        common_index = base_data['curve']['base'].index.intersection(extended_mean.index)
                        common_columns = base_data['curve']['base'].columns.intersection(extended_mean.columns)
                        base_data['curve']['base'].update(extended_mean.loc[common_index, common_columns])
                        
                
                scen_dict = self.combine_scenarios(crude_scen_dict, base_data)
                # Merge and prepare scenarios data with base data
                print(f"Prepartion and scaling start at {dt.datetime.now()}")
                train_data, test_data, y_train, y_test = data_assembly_inst.prepare_data(base_data,
                                                                                        scen_dict)
                # Scale data
                train_data_scaled, test_data_scaled = data_assembly_inst.scale_data(train_data=train_data,
                                                                                    test_data=test_data)
                print(f"Prepartion and scaling end at {dt.datetime.now()}")
                # train_data_scaled, test_data_scaled = scaled_data
                print(f"Modeling start at {dt.datetime.now()}")
                model_inst = models.Model(train_data_scaled,
                                        test_data_scaled,
                                        y_train, model_params_dict)
                curve_pred = model_inst.model_predict_curve()
                curve_pred_nominal = {}
                print(f"Modeling start at {dt.datetime.now()}")
                for grid, pred_df in curve_pred.items():
                    temp = pred_df.copy()
                    for col in temp.columns:
                        temp[col] = temp[col] * (test_data[col]['ttf'] + test_data[col]['eua']*0.2)
                    curve_pred_nominal[grid] = temp
                fuel_data = {a:b[['ttf', 'eua']] for a, b in test_data.items()}
                prediction_dict[fcst_date] = copy.deepcopy(curve_pred)
                prediction_nominal_dict[fcst_date] = copy.deepcopy(curve_pred_nominal)
                
                self.create_spreads(prediction_dict, prediction_nominal_dict, fuel_data)
                
                prediction_dict = {}
                prediction_nominal_dict = {}
                del fuel_data
                
                base_data = {}
                base_data_normalized = {}
                print(f"Loop end at {dt.datetime.now()}")
            except KeyError as e:
                # If the key doesn't exist, print or log the error and continue
                print(f"KeyError: {e}. Skipping this market and continuing.")
                continue
        # if return_test_data:
        #     print(f"Returning predicitons at time {dt.datetime.now()}")
        #     return  {a:b[['ttf', 'eua']] for a, b in test_data.items()}
        # else:
        #     return  {a:b[['ttf', 'eua']] for a, b in test_data.items()}
        print(f"Prediction for {fcst_date} done at {dt.datetime.now()}")
        
    def create_spreads(self, prediction_dict,
                       prediction_nominal_dict, fuel_data):
        method_mapping = {
                "country_spreads": {
                    "method": self.calculate_country_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
                "period_spreads": {
                    "method": self.calculate_period_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
                "b_p_spreads": {
                    "method": self.calculate_base_peak_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
                "css_spreads": {
                    "method": self.calculate_clean_spark_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict", "fuel_data"],
                },
                "capa_spreads": {
                    "method": self.calculate_capa_spreads,
                    "params": ["curve_pred", "base_products", "columns_dict"],
                },
            }

        columns_dict = self.get_scenario_columns(prediction_dict)
        base_products = list(dict.fromkeys(self.params_dict['product_list']))
        

        
        for pred_type, curve_pred in zip(['ratio', 'nominal'],
                                         [prediction_dict, prediction_nominal_dict]):
            for spread_name, config in method_mapping.items():
                method = config["method"]
                if "fuel_data" in config["params"]:
                    params = [curve_pred, base_products, columns_dict, fuel_data]
                else:
                    params = [curve_pred, base_products, columns_dict]
                
                result, period_dict = method(*params)
                self.save_nested_dict_to_parquet(result, os.path.join(r'X:\Data\Spot\Model\Forecasts',
                                                                      pred_type))
                print(f"{spread_name} for prediction type: {pred_type} saved successfully")
                
        
        pass
    
    @staticmethod
    def get_scenario_columns(data_dict):
        temp = data_dict[list(data_dict)[0]]['de'].copy()  
        columns_dict = {
            'base_col': ['base'],
            'base_sim': [f'ExtDataSim_{int(a)}' for a in range(1, 101)],
            'base_mcr': ['mcr_-1_std', 'mcr_1_std'],
            'base_avcap': ['AvailableCapacityData_10th', 'AvailableCapacityData_mean', 'AvailableCapacityData_90th'],
            'mcr_lower_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'mcr_-1_std' in a)],
            'mcr_upper_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'mcr_1_std' in a)],
            'avcap_lower_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_10th' in a)],
            'avcap_mean_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_mean' in a)],
            'avcap_upper_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_90th' in a)],
        }
        del temp
        
        return columns_dict
        
    @staticmethod
    def save_nested_dict_to_parquet(data_dict, base_directory):
        """
        Recursively traverse a nested dictionary and save DataFrames as parquet files in a directory structure
        that mirrors the dictionary's keys.

        Parameters:
            data_dict (dict): A nested dictionary where the innermost values are DataFrames.
            base_directory (str): The base directory where the folder structure and parquet files will be saved.
        """
        def sanitize_key(key):
            """Convert keys to strings and sanitize them to ensure valid file and directory names."""
            if isinstance(key, (int, float, pd.Timestamp)):
                key = str(key)
            return str(key).replace(" ", "_").replace(":", "-").replace("/", "-").replace("\\", "-")

        def save_recursive(current_dict, current_path):
            for key, value in current_dict.items():
                # Sanitize the key to ensure it is a valid directory or file name
                sanitized_key = sanitize_key(key)

                # Construct the new path
                new_path = os.path.join(current_path, sanitized_key)

                if isinstance(value, dict):
                    # Create a folder for the current key if it doesn't exist
                    os.makedirs(new_path, exist_ok=True)
                    save_recursive(value, new_path)
                elif isinstance(value, pd.DataFrame):
                    # Save the DataFrame as a parquet file
                    parquet_file = os.path.join(new_path + ".parquet")
                    value.to_parquet(parquet_file)
                else:
                    raise ValueError(f"Unexpected value type: {type(value)} at key: {key}")

        # Start the recursive saving process
        save_recursive(data_dict, base_directory)
        
    @staticmethod
    def load_nested_dict_from_parquet(base_directory):
        """
        Traverse a directory structure and rebuild a nested dictionary where parquet files are
        loaded as DataFrames and directory levels represent nested keys.

        Parameters:
            base_directory (str): The base directory containing the saved folder structure and parquet files.

        Returns:
            dict: A nested dictionary mirroring the directory structure with DataFrames loaded from parquet files.
        """
        def load_recursive(current_path):
            nested_dict = {}
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)

                if os.path.isdir(item_path):
                    # If the item is a directory, recurse into it
                    key = item
                    nested_dict[key] = load_recursive(item_path)
                elif item.endswith(".parquet"):
                    # If the item is a parquet file, load it as a DataFrame
                    key = os.path.splitext(item)[0]
                    nested_dict[key] = pd.read_parquet(item_path)
            return nested_dict

        # Perform datetime conversion for the first-level keys using strptime
        top_level_dict = load_recursive(base_directory)
        converted_dict = {}
        for key, value in top_level_dict.items():
            try:
                datetime_key = dt.datetime.strptime(key, "%Y-%m-%d_%H-%M-%S")
            except ValueError as e:
                print(f"Error converting key '{key}' to datetime: {e}")
                datetime_key = key
            converted_dict[datetime_key] = value

        return converted_dict
        
    @staticmethod
    def calculate_country_spreads(data_dict, base_products, selected_columns_dict, include_periods_info=True):
        spreads_dict = {}
        periods_info = {} if include_periods_info else None
    
        for fcst_date, countries_data in data_dict.items():
            spreads_dict[fcst_date] = {}
            if include_periods_info:
                periods_info[fcst_date] = {}
    
            country_keys = list(countries_data.keys())
            country_pairs = list(itertools.combinations(country_keys, 2))  # Get all unique pairs of countries
    
            for (country_1, country_2) in country_pairs:
                df_1 = countries_data[country_1]
                df_2 = countries_data[country_2]
    
                # Calculate the spread (difference) between the two countries
                spread_df = df_1 - df_2
    
                # Separate into `base` and `peak`
                filtered_spreads = {"base": {}, "peak": {}}
    
                for scenario_type, columns in selected_columns_dict.items():
                    filtered_df = spread_df[columns]
    
                    # Base: full period
                    filtered_spreads["base"][scenario_type] = filtered_df
    
                    # Peak: weekdays and specified hours
                    peak_filtered_df = filtered_df[
                        (filtered_df.index.weekday < 5)  # Weekdays (Monday to Friday)
                    ].between_time('08:00', '20:00')  # Between 08:00 and 20:00
                    filtered_spreads["peak"][scenario_type] = peak_filtered_df
    
                pair_name = f"{country_1}_{country_2}"
                spreads_dict[fcst_date][pair_name] = filtered_spreads
    
            # Aggregating spreads based on the base_products list
            aggregated_spreads = {}
            for pair_name, base_peak_spreads in spreads_dict[fcst_date].items():
                base_peak_aggregates = {"base": {}, "peak": {}}
                for level in ["base", "peak"]:
                    scenario_aggregates = {}
                    for scenario_type, filtered_df in base_peak_spreads[level].items():
                        scenario_stats = {}
                        for product in base_products:
                            if product.startswith('W_'):
                                week_offset = int(product.split('_')[1])
                                start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
                                end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
                            elif product.startswith('M_'):
                                month_offset = int(product.split('_')[1])
                                start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
                                end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
                            elif product.startswith('Q_'):
                                quarter_offset = int(product.split('_')[1])
                                quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
                                start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
                                end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
                            elif product.startswith('Y_'):
                                year_offset = int(product.split('_')[1])
                                start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
                                end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
                            else:
                                raise ValueError(f"Unknown product type: {product}")
    
                            # Store period information if requested
                            if include_periods_info:
                                periods_info[fcst_date][product] = {'start_date': start_date, 'end_date': end_date}
    
                            # Calculate statistics for the given period
                            period_data = filtered_df.loc[start_date:end_date]
                            if not period_data.empty:
                                if "_sim" in scenario_type:
                                    # Calculate row-wise stats
                                    scenario_stats[product] = {
                                        'mean': period_data.mean(axis=1).mean(),
                                        'median': period_data.median(axis=1).mean(),
                                        '90th': period_data.quantile(0.9, axis=1).mean(),
                                        '10th': period_data.quantile(0.1, axis=1).mean(),
                                    }
                                else:
                                    # Non-sim scenarios: direct column mean for the period
                                    period_mean = period_data.mean(axis=0).to_frame().T
                                    period_mean.index = [product]
                                    scenario_stats[product] = period_mean
    
                        # Create a DataFrame from the scenario statistics
                        if "_sim" in scenario_type:
                            scenario_df = pd.DataFrame.from_dict(scenario_stats, orient='index')
                        else:
                            scenario_df = pd.concat(scenario_stats.values())
    
                        # Store the aggregated statistics for the current scenario
                        scenario_aggregates[scenario_type] = scenario_df
    
                    # Store the aggregated statistics for the current level
                    base_peak_aggregates[level] = scenario_aggregates
    
                # Store the aggregated statistics for the current pair
                aggregated_spreads[pair_name] = base_peak_aggregates
    
            spreads_dict[fcst_date] = aggregated_spreads
            
        out_dict = {}
        out_dict['country_spreads'] = spreads_dict
    
        return (out_dict, periods_info) if include_periods_info else out_dict


    
    @staticmethod
    def calculate_period_spreads(data_dict, base_products, selected_columns_dict, include_periods_info=True):
        def _get_product_period(fcst_date, product):
            """Helper function to calculate the start and end dates for a given product."""
            if product.startswith("W_"):
                week_offset = int(product.split("_")[1])
                start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
                end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
            elif product.startswith("M_"):
                month_offset = int(product.split("_")[1])
                start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
                end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
            elif product.startswith("Q_"):
                quarter_offset = int(product.split("_")[1])
                quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
                start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
                end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
            elif product.startswith("Y_"):
                year_offset = int(product.split("_")[1])
                start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
                end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
            else:
                raise ValueError(f"Unknown product type: {product}")

            return start_date, end_date

        period_spreads_dict = {}
        periods_info = {} if include_periods_info else None

        for fcst_date, countries_data in data_dict.items():
            period_spreads_dict[fcst_date] = {}
            if include_periods_info:
                periods_info[fcst_date] = {}

            for country, df in countries_data.items():
                country_spreads = {"base": {}, "peak": {}}

                for scenario_type, columns in selected_columns_dict.items():
                    filtered_df = df[columns]

                    # Separate base and peak hours
                    scenario_base_df = filtered_df.resample('1h').mean()  # Hourly resampled data

                    # Filter for weekdays and peak hours
                    weekday_mask = filtered_df.index.weekday < 5
                    scenario_peak_df = filtered_df[weekday_mask].between_time("08:00", "20:00").resample('1h').mean()

                    # Aggregate spreads for each base product combination
                    for i, product1 in enumerate(base_products):
                        for product2 in base_products[i + 1:]:
                            spread_name = f"{product1}_{product2}"
                            start_date1, end_date1 = _get_product_period(fcst_date, product1)
                            start_date2, end_date2 = _get_product_period(fcst_date, product2)

                            base_period_data1 = scenario_base_df.loc[start_date1:end_date1]
                            base_period_data2 = scenario_base_df.loc[start_date2:end_date2]

                            peak_period_data1 = scenario_peak_df.loc[start_date1:end_date1]
                            peak_period_data2 = scenario_peak_df.loc[start_date2:end_date2]

                            # Skip if no data is available for the period
                            if base_period_data1.empty or base_period_data2.empty:
                                continue

                            if peak_period_data1.empty or peak_period_data2.empty:
                                continue

                            if "_sim" in scenario_type:
                                # Simulated scenario: Calculate statistics for spreads
                                base_spread = base_period_data1.mean() - base_period_data2.mean()
                                peak_spread = peak_period_data1.mean() - peak_period_data2.mean()

                                base_stats = {
                                    "mean": base_spread.mean(),
                                    "median": base_spread.median(),
                                    "90th": base_spread.quantile(0.9),
                                    "10th": base_spread.quantile(0.1),
                                }
                                base_stats_df = pd.DataFrame([base_stats], index=[spread_name])
                                base_df = country_spreads["base"].setdefault(scenario_type, pd.DataFrame())
                                country_spreads["base"][scenario_type] = pd.concat([base_df, base_stats_df])

                                peak_stats = {
                                    "mean": peak_spread.mean(),
                                    "median": peak_spread.median(),
                                    "90th": peak_spread.quantile(0.9),
                                    "10th": peak_spread.quantile(0.1),
                                }
                                peak_stats_df = pd.DataFrame([peak_stats], index=[spread_name])
                                peak_df = country_spreads["peak"].setdefault(scenario_type, pd.DataFrame())
                                country_spreads["peak"][scenario_type] = pd.concat([peak_df, peak_stats_df])

                            else:
                                # Non-simulated scenario: Store raw spreads
                                base_spread = base_period_data1.mean(axis=0) - base_period_data2.mean(axis=0)
                                base_spread = pd.DataFrame(base_spread,index=base_spread.index,columns=[spread_name]).T
                                peak_spread = peak_period_data1.mean(axis=0) - peak_period_data2.mean(axis=0)
                                peak_spread = pd.DataFrame(peak_spread,index=peak_spread.index,columns=[spread_name]).T
    
                                base_spread_df = country_spreads["base"].setdefault(scenario_type, pd.DataFrame())
                                country_spreads["base"][scenario_type] = pd.concat([base_spread_df,
                                                                                    base_spread])
    
                                peak_spread_df = country_spreads["peak"].setdefault(scenario_type, pd.DataFrame())
                                country_spreads["peak"][scenario_type] = pd.concat([peak_spread_df,
                                                                                    peak_spread])

                period_spreads_dict[fcst_date][country] = country_spreads
                
        out_dict = {}
        out_dict['period_spreads'] = period_spreads_dict

        return (out_dict, periods_info) if include_periods_info else out_dict

    
    
    @staticmethod    
    def calculate_base_peak_spreads(data_dict, base_products, selected_columns_dict, include_periods_info=True):
        spreads_dict = {}
        periods_info = {} if include_periods_info else None
    
        for fcst_date, countries_data in data_dict.items():
            spreads_dict[fcst_date] = {}
            if include_periods_info:
                periods_info[fcst_date] = {}
    
            for country, df in countries_data.items():
                scenario_spreads = {}
                product_periods = {}
    
                # Define periods for base and peak calculations
                for product in base_products:
                    if product.startswith('W_'):
                        week_offset = int(product.split('_')[1])
                        start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
                        end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
                    elif product.startswith('M_'):
                        month_offset = int(product.split('_')[1])
                        start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
                        end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
                    elif product.startswith('Q_'):
                        quarter_offset = int(product.split('_')[1])
                        quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
                        start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
                        end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
                    elif product.startswith('Y_'):
                        year_offset = int(product.split('_')[1])
                        start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
                        end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
                    else:
                        raise ValueError(f"Unknown product type: {product}")
    
                    product_periods[product] = {'start_date': start_date, 'end_date': end_date}
    
                    # Store period information if requested
                    if include_periods_info:
                        periods_info[fcst_date][product] = {'start_date': start_date, 'end_date': end_date}
    
                for scenario, columns in selected_columns_dict.items():
                    scenario_stats = {}
                    for product, period in product_periods.items():
                        start_date, end_date = period['start_date'], period['end_date']
    
                        # Filter data for the selected columns
                        period_data = df.loc[start_date:end_date, columns]
                        if period_data.empty:
                            continue
    
                        # Base calculation: Mean of all hours
                        base_stats = {
                            'mean': period_data.mean(axis=1).mean(),
                            'median': period_data.median(axis=1).mean(),
                            '90th': period_data.quantile(0.9, axis=1).mean(),
                            '10th': period_data.quantile(0.1, axis=1).mean(),
                        }
    
                        # Peak calculation: Business days, 09:00 to 20:00
                        peak_data = period_data[
                            (period_data.index.weekday < 5)  # Weekdays (Monday to Friday)
                        ].between_time('08:00', '20:00')
                        if not peak_data.empty:
                            peak_stats = {
                                'mean': peak_data.mean(axis=1).mean(),
                                'median': peak_data.median(axis=1).mean(),
                                '90th': peak_data.quantile(0.9, axis=1).mean(),
                                '10th': peak_data.quantile(0.1, axis=1).mean(),
                            }
                        else:
                            peak_stats = {key: None for key in ['mean', 'median', '90th', '10th']}
    
                        # Calculate spread
                        scenario_stats[product] = {
                            key: peak_stats[key] - base_stats[key] if peak_stats[key] is not None else None
                            for key in ['mean', 'median', '90th', '10th']
                        }
    
                    # Convert scenario statistics to DataFrame
                    scenario_spreads[scenario] = pd.DataFrame.from_dict(scenario_stats, orient='index')
    
                # Store the scenario spreads for the current country
                spreads_dict[fcst_date][country] = scenario_spreads
                
        out_dict = {}
        out_dict['b_p_spreads'] = spreads_dict
    
        return (out_dict, periods_info) if include_periods_info else out_dict
    
    @staticmethod
    def calculate_clean_spark_spreads(data_dict, base_products, selected_columns_dict, fuel_data, include_periods_info=True):
        css_dict = {}
        periods_info = {} if include_periods_info else None
    
        for fcst_date, countries_data in data_dict.items():
            css_dict[fcst_date] = {}
            if include_periods_info:
                periods_info[fcst_date] = {}
    
            for country, power_df in countries_data.items():
                css_country = {"base": {}, "peak": {}}  # Add base/peak levels
    
                for scenario_type, columns in selected_columns_dict.items():
                    # Filter the power DataFrame to include only selected columns
                    filtered_power_df = power_df[columns]
    
                    # Initialize DataFrames to store CSS for the selected columns
                    scenario_base_css_df = pd.DataFrame(index=filtered_power_df.index)
                    scenario_peak_css_df = pd.DataFrame(index=filtered_power_df.index)
    
                    for scenario in filtered_power_df.columns:
                        if scenario not in fuel_data:
                            raise KeyError(f"Scenario '{scenario}' missing in fuel_data.")
    
                        # Retrieve TTF and EUA prices for the scenario
                        fuel_df = fuel_data[scenario]
                        if not set(['ttf', 'eua']).issubset(fuel_df.columns):
                            raise ValueError(f"Fuel data for scenario '{scenario}' must contain 'ttf' and 'eua' columns.")
    
                        # CSS formula for both base and peak
                        scenario_css = (
                            filtered_power_df[scenario]
                            - 2 * (fuel_df['ttf'] + (0.211 * fuel_df['eua']))
                        )
    
                        # Base CSS
                        scenario_base_css_df[scenario] = scenario_css
    
                        # Peak CSS: Filter business days and hours
                        peak_css = scenario_css[
                            (scenario_css.index.weekday < 5)  # Weekdays (Monday to Friday)
                        ].between_time('08:00', '20:00')  # Between 09:00 and 20:00
                        scenario_peak_css_df[scenario] = peak_css
    
                    # Aggregating CSS over base_products
                    for product in base_products:
                        if product.startswith("W_"):
                            week_offset = int(product.split("_")[1])
                            start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
                            end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
                        elif product.startswith("M_"):
                            month_offset = int(product.split("_")[1])
                            start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
                            end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
                        elif product.startswith("Q_"):
                            quarter_offset = int(product.split("_")[1])
                            quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
                            start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
                            end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
                        elif product.startswith("Y_"):
                            year_offset = int(product.split("_")[1])
                            start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
                            end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
                        else:
                            raise ValueError(f"Unknown product type: {product}")
    
                        # Store period information if requested
                        if include_periods_info:
                            periods_info[fcst_date][product] = {"start_date": start_date, "end_date": end_date}
    
                        # Calculate CSS for the given period
                        base_period_data = scenario_base_css_df.loc[start_date:end_date]
                        peak_period_data = scenario_peak_css_df.loc[start_date:end_date]
    
                        # Handle scenarios with '_sim' for stats
                        if "_sim" in scenario_type:
                            if not base_period_data.empty:
                                base_stats = {
                                    "mean": base_period_data.mean(axis=1).mean(),
                                    "median": base_period_data.median(axis=1).mean(),
                                    "90th": base_period_data.quantile(0.9, axis=1).mean(),
                                    "10th": base_period_data.quantile(0.1, axis=1).mean(),
                                }
                                base_stats_df = pd.DataFrame([base_stats], index=[product])
                                css_country["base"][scenario_type] = pd.concat(
                                    [css_country["base"].get(scenario_type, pd.DataFrame()), base_stats_df]
                                )
    
                            if not peak_period_data.empty:
                                peak_stats = {
                                    "mean": peak_period_data.mean(axis=1).mean(),
                                    "median": peak_period_data.median(axis=1).mean(),
                                    "90th": peak_period_data.quantile(0.9, axis=1).mean(),
                                    "10th": peak_period_data.quantile(0.1, axis=1).mean(),
                                }
                                peak_stats_df = pd.DataFrame([peak_stats], index=[product])
                                css_country["peak"][scenario_type] = pd.concat(
                                    [css_country["peak"].get(scenario_type, pd.DataFrame()), peak_stats_df]
                                )
                        else:
                            # Non-sim scenarios
                            if not base_period_data.empty:
                                base_df = base_period_data.mean(axis=0).to_frame().T
                                base_df.index = [product]  # Set the product as the index
                                css_country["base"][scenario_type] = pd.concat(
                                    [css_country["base"].get(scenario_type, pd.DataFrame()), base_df]
                                )
    
                            if not peak_period_data.empty:
                                peak_df = peak_period_data.mean(axis=0).to_frame().T
                                peak_df.index = [product]  # Set the product as the index
                                css_country["peak"][scenario_type] = pd.concat(
                                    [css_country["peak"].get(scenario_type, pd.DataFrame()), peak_df]
                                )
    
                # Store CSS values for the current country
                css_dict[fcst_date][country] = css_country
                
        out_dict = {}
        out_dict['css_spreads'] = css_dict
    
        return (out_dict, periods_info) if include_periods_info else out_dict
    
    @staticmethod
    def calculate_capa_spreads(data_dict, base_products, selected_columns_dict, selected_spreads=None, include_periods_info=True):
        """
        Calculate capacity spreads where negative differences are zero for both directions (leg2 - leg1 and leg1 - leg2).
        Includes base/peak separation, `_sim` stats logic, and direct means for non-`_sim` scenarios.
        """
        capa_spreads_dict = {}
        periods_info = {} if include_periods_info else None
    
        for fcst_date, countries_data in data_dict.items():
            capa_spreads_dict[fcst_date] = {}
            if include_periods_info:
                periods_info[fcst_date] = {}
    
            # Prepare country pairs, filter if selected_spreads provided
            country_keys = list(countries_data.keys())
            country_pairs = list(itertools.combinations(country_keys, 2))
            if selected_spreads:
                country_pairs = [pair for pair in country_pairs if f"{pair[0]}_{pair[1]}" in selected_spreads]
    
            for (country_1, country_2) in country_pairs:
                df_1 = countries_data[country_1]
                df_2 = countries_data[country_2]
    
                # Calculate non-negative spreads
                spread_2_1 = (df_2 - df_1).clip(lower=0)  # leg2 - leg1
                spread_1_2 = (df_1 - df_2).clip(lower=0)  # leg1 - leg2
    
                # Process both directions
                for spread_name, spread_df in zip([f"{country_1}_{country_2}", f"{country_2}_{country_1}"], [spread_2_1, spread_1_2]):
                    capa_spreads_dict[fcst_date][spread_name] = {"base": {}, "peak": {}}
    
                    for scenario_type, columns in selected_columns_dict.items():
                        filtered_df = spread_df[columns]
    
                        # Separate base and peak spreads
                        base_df = filtered_df
                        peak_df = filtered_df[
                            (filtered_df.index.weekday < 5)  # Weekdays (Mon-Fri)
                        ].between_time('08:00', '20:00')  # Peak hours
    
                        # Aggregate spreads over base_products
                        for product in base_products:
                            if product.startswith('W_'):
                                week_offset = int(product.split('_')[1])
                                start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
                                end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
                            elif product.startswith('M_'):
                                month_offset = int(product.split('_')[1])
                                start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
                                end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
                            elif product.startswith('Q_'):
                                quarter_offset = int(product.split('_')[1])
                                quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
                                start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
                                end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
                            elif product.startswith('Y_'):
                                year_offset = int(product.split('_')[1])
                                start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
                                end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
                            else:
                                raise ValueError(f"Unknown product type: {product}")
    
                            # Store period information if requested
                            if include_periods_info:
                                periods_info[fcst_date][product] = {"start_date": start_date, "end_date": end_date}
    
                            # Process base data
                            base_period_data = base_df.loc[start_date:end_date]
                            peak_period_data = peak_df.loc[start_date:end_date]
    
                            # Handle `_sim` scenarios with stats
                            if "_sim" in scenario_type:
                                if not base_period_data.empty:
                                    base_stats = {
                                        "mean": base_period_data.mean(axis=1).mean(),
                                        "median": base_period_data.median(axis=1).mean(),
                                        "90th": base_period_data.quantile(0.9, axis=1).mean(),
                                        "10th": base_period_data.quantile(0.1, axis=1).mean(),
                                    }
                                    base_stats_df = pd.DataFrame([base_stats], index=[product])
                                    capa_spreads_dict[fcst_date][spread_name]["base"][scenario_type] = pd.concat(
                                        [capa_spreads_dict[fcst_date][spread_name]["base"].get(scenario_type, pd.DataFrame()), base_stats_df]
                                    )
    
                                if not peak_period_data.empty:
                                    peak_stats = {
                                        "mean": peak_period_data.mean(axis=1).mean(),
                                        "median": peak_period_data.median(axis=1).mean(),
                                        "90th": peak_period_data.quantile(0.9, axis=1).mean(),
                                        "10th": peak_period_data.quantile(0.1, axis=1).mean(),
                                    }
                                    peak_stats_df = pd.DataFrame([peak_stats], index=[product])
                                    capa_spreads_dict[fcst_date][spread_name]["peak"][scenario_type] = pd.concat(
                                        [capa_spreads_dict[fcst_date][spread_name]["peak"].get(scenario_type, pd.DataFrame()), peak_stats_df]
                                    )
                            else:
                                # Non-sim scenarios: Direct means for each period
                                if not base_period_data.empty:
                                    base_df_mean = base_period_data.mean(axis=0).to_frame().T
                                    base_df_mean.index = [product]
                                    capa_spreads_dict[fcst_date][spread_name]["base"][scenario_type] = pd.concat(
                                        [capa_spreads_dict[fcst_date][spread_name]["base"].get(scenario_type, pd.DataFrame()), base_df_mean]
                                    )
    
                                if not peak_period_data.empty:
                                    peak_df_mean = peak_period_data.mean(axis=0).to_frame().T
                                    peak_df_mean.index = [product]
                                    capa_spreads_dict[fcst_date][spread_name]["peak"][scenario_type] = pd.concat(
                                        [capa_spreads_dict[fcst_date][spread_name]["peak"].get(scenario_type, pd.DataFrame()), peak_df_mean]
                                    )
                                    
        out_dict = {}
        out_dict['capa_spreads'] = capa_spreads_dict
    
        return (out_dict, periods_info) if include_periods_info else out_dict





        
        
        
    