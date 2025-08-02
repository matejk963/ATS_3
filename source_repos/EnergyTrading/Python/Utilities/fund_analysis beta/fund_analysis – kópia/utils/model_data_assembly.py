import fund_analysis.input_data as input_data
from fund_analysis.utils import ENUMS as enums
import pandas as pd
import numpy as np
import datetime as dt
import copy
from joblib import Parallel, delayed
try:
    import cupy as cp
except:
    pass
from sqlalchemy import create_engine, text
from numba import cuda

from sklearn.preprocessing import StandardScaler, PowerTransformer

from Database.DB_reader import Database
from Common.config_load import get_config_path as CONFIG_PATH
import json


PATH = CONFIG_PATH()
with open(PATH, 'r') as file:
    config_eex = json.load(file)['EEX_ftp']



class ModelDataAssembly:
    power_spot = None

    data_inst_dict = {}
    
    def __init__(self, params_dict, fcst_date,
                    predictors=['ResidualDemand',
                                'Hydro', 'Wind', 'Temp',
                                'AvailableCapacityData',
                                'Gas', 'Coal', 'Eua']):
        self._params_dict = params_dict
        self._fcst_date = fcst_date
        self._predictors = predictors
        self.data_dict = {}
        self.data_dict_normalized = {}
        self._av_cap_cols = []
        
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def fcst_date(self):
        return self._fcst_date
    
    @property
    def predictors(self):
        return self._predictors
    
    @property
    def av_cap_cols(self):
        if len(self._av_cap_cols) < 1:
            self.get_av_cap_cols()
        return self._av_cap_cols
    
    def update_fcst_date(self, new_fcst_date):
        
        self._fcst_date = new_fcst_date
        for predictor in self.predictors:
            self.init_data_inst(predictor=predictor,
                                params_dict=self.params_dict)
            inst = self.data_inst_dict[predictor]
            inst.update_params(self.fcst_date)               
            inst.da_data = {}                
            inst.data_curve = {}
        self.data_dict = {}
            # if self.data_dict:
            #     if self.data_dict[predictor]:
            #         self.data_dict[predictor]['curve'] = {}
            #         # for market, market_df in self.data_dict[predictor]['da'].items():
            #         #     self.data_dict[predictor]['da'][market] = market_df.sort_index().loc[:new_fcst_date].iloc[:-1].copy()

        
    def get_av_cap_cols(self):
        for market_long_name, market_dict in enums.capacity_source_dict.items():
            market = enums.to_own_name(market_long_name)
            for source in market_dict.keys():
                source_name = f"{source}_{market}"
                self._av_cap_cols.append(source_name)
        return self._av_cap_cols
            
    def kwargs_map(self, predictor):
        my_dict = {
            'AvailableCapacityData': {'cap_type': 'av_cap'},
            'ResidualDemand' : {'normalize_bool': True},
            'Hydro' : {'normalize_bool': True},
        }
        if predictor in my_dict:
            return my_dict[predictor]
        else:
            return {}
        
    def init_data_inst(self, predictor:str,
                        params_dict:dict):
        if predictor not in self.data_inst_dict:
            self.data_inst_dict[predictor] = getattr(input_data,
                                                        predictor)(params_dict,
                                                                    **self.kwargs_map(predictor))
        
    # def collect_data(self):
    #     gas_curve = {}
    #     gas_da = {}
    #     for predictor in self.predictors:
    #         if not predictor in self.data_dict:
    #             self.data_dict[predictor] = {}
    #             self.data_dict_normalized[predictor] = {}
    #             self.init_data_inst(predictor=predictor,
    #                                 params_dict=self.params_dict)
    #             inst = self.data_inst_dict[predictor]
    #             inst.update_params(self.fcst_date)
    #             for data_type in ['curve', 'da']:
    #                 if data_type in ['da']:
    #                     inst.get_da_data()
    #                     self.data_dict[predictor][data_type] = copy.deepcopy(inst.da_data)
    #                     if predictor in ['ResidualDemand', 'Hydro']:
    #                         self.data_dict_normalized[predictor][data_type] = copy.deepcopy(inst.da_data_normalized)
    #                     if predictor in ['AvailableCapacityData']:
    #                         for market, da_data_market_df in inst.da_data.items():
    #                             self._av_cap_cols.extend(list(da_data_market_df.columns))
    #                             self._av_cap_cols = list(np.unique(self.av_cap_cols))
    #                 else:
    #                     if predictor in ['Coal']:
    #                         inst.get_curve(gas_curve=gas_curve,
    #                                         gas_da=gas_da)
    #                     else:
    #                         inst.get_curve()
    #                     self.data_dict[predictor][data_type] = copy.deepcopy(inst.data_curve)
    #                     if predictor in ['ResidualDemand', 'Hydro']:
    #                         self.data_dict_normalized[predictor][data_type] = copy.deepcopy(inst.data_curve_normalized)
    #             if predictor in ['Gas']:
    #                 gas_curve = copy.deepcopy(inst.fut_matrix)
    #                 gas_da = copy.deepcopy(inst.da_data)
    #             del inst
                
    def collect_data(self, selected_data_type=None):
        gas_curve = {}
        gas_da = {}
    
        for predictor in self.predictors:
            # Initialize data if predictor is not already in the data_dict
            if predictor not in self.data_dict:
                self._initialize_predictor_data(predictor)
    
            inst = self.data_inst_dict[predictor]
            inst.update_params(self.fcst_date)
    
            # Handle curve and da data types separately if data is available
            if selected_data_type is None:
                if not self._has_data_for_type(inst, 'da'):
                    self._process_da_data(inst, predictor)
                if not self._has_data_for_type(inst, 'curve'):
                    self._process_curve_data(inst, predictor, gas_curve, gas_da)
            elif selected_data_type in ['curve']:
                self._process_curve_data(inst, predictor, gas_curve, gas_da)
            elif selected_data_type in ['da']:
                self._process_da_data(inst, predictor)
    
            # Update gas_curve and gas_da if predictor is Gas
            if predictor == 'Gas':
                gas_curve = copy.deepcopy(inst.fut_matrix)
                gas_da = copy.deepcopy(inst.da_data)
    
            # Clean up
            del inst
    
    def _initialize_predictor_data(self, predictor):
        """Initializes data structures for a given predictor."""
        self.data_dict[predictor] = {}
        self.data_dict_normalized[predictor] = {}
        self.init_data_inst(predictor=predictor, params_dict=self.params_dict)
    
    def _process_da_data(self, inst, predictor):
        """Processes 'da' data type for the given predictor."""
        inst.get_da_data()
        self.data_dict[predictor]['da'] = copy.deepcopy(inst.da_data)
    
        if predictor in ['ResidualDemand', 'Hydro']:
            self.data_dict_normalized[predictor]['da'] = copy.deepcopy(inst.da_data_normalized)
    
        if predictor == 'AvailableCapacityData':
            for market, da_data_market_df in inst.da_data.items():
                self._update_available_capacity_columns(da_data_market_df)
    
    def _process_curve_data(self, inst, predictor, gas_curve, gas_da):
        """Processes 'curve' data type for the given predictor."""
        if predictor == 'Coal':
            inst.get_curve(gas_curve=gas_curve, gas_da=gas_da)
        else:
            inst.get_curve()
    
        self.data_dict[predictor]['curve'] = copy.deepcopy(inst.data_curve)
    
        if predictor in ['ResidualDemand', 'Hydro']:
            self.data_dict_normalized[predictor]['curve'] = copy.deepcopy(inst.data_curve_normalized)
    
    def _update_available_capacity_columns(self, da_data_market_df):
        """Updates available capacity columns from the given DataFrame."""
        self._av_cap_cols.extend(list(da_data_market_df.columns))
        self._av_cap_cols = list(np.unique(self._av_cap_cols))
    
    def _has_data_for_type(self, inst, data_type):
        """Checks if there is data available for the given data type."""
        if data_type == 'da':
            return hasattr(inst, 'da_data') and bool(inst.da_data)
        elif data_type == 'curve':
            return hasattr(inst, 'data_curve') and bool(inst.data_curve)
        return False

                    
    def create_base_data(self, normalized=False, selected_data_type=None):
        if selected_data_type is None:
            data_type_list = ['da', 'curve']
        else:
            data_type_list = [selected_data_type]
        # Collect data
        self.collect_data(selected_data_type=selected_data_type)
        
        # Select the proper data_dict
        if normalized:
            data_dict = copy.deepcopy(self.data_dict_normalized)
        else:
            data_dict = copy.deepcopy(self.data_dict)
            
        new_dict = {}

        # Loop over data_types (e.g., 'da', 'curve', etc.)
        for data_type in data_type_list:  # Adjust the data types as needed
            new_dict[data_type] = {}# Initialize dictionary for each data_type
            merged_df = pd.DataFrame()  # Empty DataFrame to start merging
            
            # Loop through predictors and markets
            for predictor in self.predictors:
                if normalized and predictor not in ['ResidualDemand', 'Hydro']:
                    continue
                for market in data_dict[predictor][data_type]:
                    data_df = data_dict[predictor][data_type][market]
                    
                    # Create the new column name based on predictor and market
                    if predictor in ['ResidualDemand', 'Hydro']:
                        prefix = f'{predictor}_{market}'
                        data_df.columns = [prefix]
                    
                    # Rename the columns of the data_df with the prefix
                    # data_df.columns = [f'{prefix}_{col}' for col in data_df.columns]
                    
                    # Merge data_df into merged_df along axis=1
                    merged_df = pd.concat([merged_df, data_df], axis=1)
                    
            
            # Store the merged dataframe into new_dict
            new_dict[data_type]['base'] = merged_df
        if 'da' in data_type_list:
            new_dict['da']['base'] = new_dict['da']['base'].dropna().copy()
        if 'curve' in data_type_list:
            new_dict['curve']['base'] = new_dict['curve']['base'].loc[new_dict['curve']['base'].index.date != self.fcst_date.date()].copy()
        
        del data_dict
        return new_dict
    
    def fetch_base_data(self, da_source='db', normalized=False):
        if da_source in ['db']:
            selected_data_type = 'curve'
            base_dict = {'da':{'base': self.load_da_data()}}
        else:
            selected_data_type = None
            base_dict = {}
            
        curve_dict = self.create_base_data(normalized=normalized,
                                           selected_data_type=selected_data_type)        
        
        base_dict.update(curve_dict)
        return base_dict
    
    def get_power_spot(self):        
        self.power_spot = input_data.Power(self.params_dict)
        self.power_spot.get_da_data()
        
    def features_method_mapping(self, feature_type: str):
        method_map = {
            'rld_ex_av_cap': self.create_rld_ex_av_cap,
            'mcr': self.create_mcr,
            'ghr': self.create_ghr,
            'chr': self.create_chr,
            'gmc': self.create_gmc,
            'cmc': self.create_cmc
        }
        return method_map[feature_type]
        
    def create_rld_ex_av_cap(self,df: pd.DataFrame):
        rld_columns = [a for a in df.columns if 'ResidualDemand' in a]
        for rld_market in rld_columns:
            market_aux = rld_market.split('_')[1]
            # Vectorized operation
            new_columns = pd.DataFrame(df[[rld_market]].values-\
                                        df[self.av_cap_cols].values,
                                        columns=[f"{market_aux}_{col}" for
                                                col in self.av_cap_cols],
                                        index=df.index)
            
            # Concatenate the new columns to the original DataFrame
            df = pd.concat([df, new_columns], axis=1)
        df.drop(self.av_cap_cols,axis=1,inplace=True)
        
        return df
    
    # Gas marginal costs
    def create_gmc(self, df: pd.DataFrame):
        df['gmc'] = df['ttf'] + df['eua'] * 0.2
        return df
        
    # Coal marginal costs
    def create_cmc(self, df: pd.DataFrame):
        df['cmc'] = (df['api2']/6.5+df['eua']*0.35)
        return df
    
    # Gas heat rate
    def create_ghr(self, df: pd.DataFrame):
        for market in self.power_spot_dict.keys():
            if market in df.columns:
                ghr_name = f'ghr_{market}'
                df[ghr_name] = df[market]/df['gmc']
    
    # Coal hear rate
    def create_chr(self, df: pd.DataFrame):
        for market in self.power_spot_dict.keys():
            if market in df.columns:
                chr_name = f'chr_{market}'
                df[chr_name] = df[market]/df['cmc']

    @staticmethod
    def assert_columns_in_df(df, columns):
        # Check if all required columns are in the DataFrame
        missing_columns = [col for col in columns if col not in df.columns]
        
        # Assert that there are no missing columns
        assert len(missing_columns) == 0, f"Missing columns: {', '.join(missing_columns)}"
    
    # Marginal costs ratio
    def create_mcr(self, df: pd.DataFrame):
        name_cols = ['gmc', 'cmc']
        self.assert_columns_in_df(df, name_cols)
        df['mcr'] = df[name_cols[0]]/df[name_cols[1]]
        return df
    
    def create_model_features(self, data: dict,
                                features_type_list: list=
                                    ['rld_ex_av_cap',
                                    'gmc', 'cmc', 'mcr']):
        # data dict structure:
        #  {fcst_date: {scen_name: df}}
        adj_data = {}
        for scen_name, scen_df in data.items():
            for feature_type in features_type_list:
                scen_df = self.features_method_mapping(feature_type)(scen_df)
            adj_data[scen_name] = scen_df.copy()
        return adj_data
    
    def scaler_mapping(self, scaler_str: str):
        scaler_dict = {
            'YeoJohnson': PowerTransformer,
            'StandardScaler': StandardScaler
        }
        
        return scaler_dict[scaler_str]
    
    # @staticmethod
    # def insert_scenarios(base_df, scen_df):        
    #     base_df[scen_df.columns] = scen_df.copy()
    #     return base_df
    
    # def prepare_data(self, data: dict, scen_dict: dict = {}):
    #     # Create train data
    #     train_data = data['da'].copy()
    #     train_data = self.create_model_features(train_data)
    #     y_train = {}
    #     y_test = {}
    #     self.get_power_spot()
    #     train_df = train_data['base'].copy()
    #     for market, market_spot in self.power_spot.da_data.items():
    #         temp = pd.concat([market_spot,
    #                             train_df[['gmc']]],
    #                             join='inner',axis=1)
    #         temp['ghr'] = temp[market]/temp['gmc']
    #         y_train[market] = temp[['ghr']].copy()
        
    #     # Create test data
    #     test_data = data['curve'].copy()
        
    #     if scen_dict:
    #         scen_dfs = Parallel(n_jobs=8)(
    #                     delayed(self.insert_scenarios)(test_data['base'], df) 
    #                     for df in scen_dict.values()
    #                 )
    #         updated_scen_dict = {key: value for key, value
    #                                 in zip(scen_dict.keys(), scen_dfs)}
    #         test_data.update(updated_scen_dict)
    #     test_data = self.create_model_features(test_data)
        
    #     return train_data, test_data, y_train, y_test
    
    # from numba import cuda
    # import numpy as np
    

    @staticmethod
    @cuda.jit
    def insert_scenarios_kernel(base_data, scen_data):
        idx = cuda.grid(1)
        if idx < base_data.shape[0]:
            # Insert scenario data into the base data
            for i in range(base_data.shape[1]):
                base_data[idx, i] = scen_data[idx, i]

    def prepare_data(self, data: dict, scen_dict: dict = {}):
        print('Prepare data start')
        # Create train data
        train_data = data['da'].copy()
        train_data = self.create_model_features(train_data)
        y_train = {}
        y_test = {}
        self.get_power_spot()
        train_df = train_data['base'].copy()

        for market, market_spot in self.power_spot.da_data.items():
            temp = pd.concat([market_spot, train_df[['gmc']]], join='inner', axis=1)
            temp['ghr'] = temp[market] / temp['gmc']
            y_train[market] = temp[['ghr']].copy()

        # Create test data
        test_data = data['curve'].copy()

        if scen_dict:
            # Convert base DataFrame and scenario DataFrames to numpy arrays
            base_data = test_data['base'].values
            scen_arrays = {key: df.values for key, df in scen_dict.items()}

            # Allocate GPU memory and move data to the GPU
            base_data_gpu = cuda.to_device(base_data)

            for scen_key, scen_array in scen_arrays.items():
                scen_data_gpu = cuda.to_device(scen_array)

                # Set up thread configuration
                threads_per_block = 128
                blocks_per_grid = (base_data.shape[0] + (threads_per_block - 1)) // threads_per_block

                # Launch kernel
                self.insert_scenarios_kernel[blocks_per_grid, threads_per_block](base_data_gpu, scen_data_gpu)

                # Copy result back to host
                updated_base_data = base_data_gpu.copy_to_host()

                # Update the scenario DataFrame
                updated_scen_dict = pd.DataFrame(updated_base_data, columns=test_data['base'].columns,
                                                 index=test_data['base'].index)
                test_data.update({scen_key: updated_scen_dict})

        test_data = self.create_model_features(test_data)

        return train_data, test_data, y_train, y_test



    # def scale_data(self, train_data: dict,
    #                 test_data: dict,
    #                 scaler_str: str = 'YeoJohnson'):
    #     scaler = self.scaler_mapping(scaler_str)()  # Define the scaler once
    #     # Fit and transform the training data for each scenario
    #     train_scaled = scaler.fit_transform(train_data['base'].values)
    #     train_data_scaled = pd.DataFrame(train_scaled,
    #                                     columns=train_data[scen_name].columns,
    #                                     index=train_data[scen_name].index)
    #     test_data_scaled = {}
    #     # Iterate through train data and apply the scaling
    #     for scen_name, scen_df in test_data.items():
    #         # Apply the same transformation to the corresponding test data
    #         test_scaled = scaler.transform(scen_df.values)
    #         test_data_scaled[scen_name] = pd.DataFrame(test_scaled,
    #                                                 columns=test_data[scen_name].columns,
    #                                                 index=test_data[scen_name].index)

    #     return train_data_scaled, test_data_scaled  # Optionally return the updated dictionaries
    
    # def scale_data(self, train_data: dict,
    #                 test_data: dict,
    #                 scaler_str: str = 'YeoJohnson'):
    #     scaler = self.scaler_mapping(scaler_str)()  # Define the scaler once
    #     # Fit and transform the training data for each scenario
    #     train_scaled = scaler.fit_transform(train_data['base'].values)
    #     train_data_scaled = pd.DataFrame(train_scaled,
    #                                     columns=train_data['base'].columns,
    #                                     index=train_data['base'].index)
    #     test_data_scaled = {}
    #     # Iterate through train data and apply the scaling
    #     def scale_to_df(scaler, scen_df, scen_name):
    #         test_scaled = scaler.transform(scen_df.values)
    #         return pd.DataFrame(test_scaled,
    #                             columns=test_data[scen_name].columns,
    #                             index=test_data[scen_name].index)
        
    #     scaled_dfs = Parallel(n_jobs=8, pre_dispatch=16, backend='threading')(
    #                     delayed(scale_to_df)(scaler, df, scen_name) 
    #                     for scen_name, df in test_data.items()
    #                 )
    #     test_data_scaled = {key: value for key, value in
    #                         zip(test_data.keys(), scaled_dfs)}

    #     return train_data_scaled, test_data_scaled  # Optionally return the updated dictionaries
    
    def scale_data(self, train_data: dict, test_data: dict, scaler_str: str = 'YeoJohnson'):
        print('Scaling start')
        # Define the scaler once
        scaler = self.scaler_mapping(scaler_str)()
        
        # Ensure consistent data types in training data
        train_data_values = train_data['base'].values.astype(float)  # Convert to float to avoid type issues
        train_data_device = cp.asarray(train_data_values)  # Transfer data to GPU
        
        # Perform fit and transform using cupy for GPU acceleration
        train_scaled_device = cp.asarray(scaler.fit_transform(cp.asnumpy(train_data_device)))
        train_data_scaled = pd.DataFrame(cp.asnumpy(train_scaled_device),
                                         columns=train_data['base'].columns,
                                         index=train_data['base'].index)
        
        # Prepare to scale the test data
        test_data_scaled = {}
    
        # Define a function for GPU scaling
        def scale_to_df_gpu(scaler, scen_df):
            # Ensure consistent data types in test data
            scen_values = scen_df.values.astype(float)  # Convert to float to avoid type issues
            scen_device = cp.asarray(scen_values)  # Transfer data to GPU
            test_scaled_device = cp.asarray(scaler.transform(cp.asnumpy(scen_device)))
            return pd.DataFrame(cp.asnumpy(test_scaled_device),
                                columns=scen_df.columns,
                                index=scen_df.index)
    
        # Scale test data using GPU for parallel processing
        for scen_name, df in test_data.items():
            test_data_scaled[scen_name] = scale_to_df_gpu(scaler, df)
            
        print('Scaling end')
        return train_data_scaled, test_data_scaled
    
    
    
    def fill_da_data_to_db(self, normalized=False):
        db = Database()

        # Create an engine from the existing connection string
        con = db.connection_string
        engine = create_engine(con)  # Create the engine from the connection string

        # Check if the 'da_data' table exists
        query_check_table = """
        SELECT * 
        FROM "MODEL"."da_data"
        LIMIT 1;
        """

        # Try to check if the table exists using Pandas read_sql
        try:
            table_exists_df = pd.read_sql(query_check_table, engine)
            table_exists = not table_exists_df.empty
        except Exception as e:
            # If there's any error, we assume the table does not exist
            print(f"Error checking if table exists: {e}")
            table_exists = False

        # If table exists, get the last datetime and set self.params_dict['sD']
        if table_exists:
            with engine.connect() as connection:
                query_last_datetime = """
                SELECT MAX(datetime) as last_datetime 
                FROM "MODEL"."da_data";
                """
                last_datetime_result = connection.execute(text(query_last_datetime)).fetchone()
                last_datetime = last_datetime_result[0]

                # Convert to date and shift by 3 days
                if last_datetime:
                    last_date = pd.to_datetime(last_datetime).date()
                    new_date = last_date - pd.Timedelta(days=3)
                    new_datetime = pd.Timestamp(new_date)

                    # Set self.params_dict['sD'] to the new datetime
                    self.params_dict['sD'] = new_datetime

        # Proceed to create base data and fill into the database
        base_data = self.create_base_data(normalized=normalized, selected_data_type='da')
        df = base_data['da']['base'].copy()
        df.index.name = 'datetime'
        df = df.reset_index().copy()
        
        if normalized:
            table_name = "da_data_normalized"
            stage_table_name = 'stage_da_data_normalized'
        else:
            table_name = 'da_data'
            stage_table_name = 'stage_da_data'

        # Write to staging table
        df.to_sql(name=stage_table_name,
                schema='MODEL',
                con=engine,
                if_exists='replace', index=False)

        # Merge from staging to production

        db.merge_from_staging_to_prod('MODEL', table_name)


        # Dispose the engine connection
        engine.dispose()

        
        
    def load_da_data(self,normalized=False):
        db = Database()
        con = db.connection_string
        engine = create_engine(con)
        
        fcst_date = self.fcst_date
        
        if normalized:
            table_name = "da_data_normalized"
        else:
            table_name = 'da_data'
        
        query = text(f"""
            SELECT * FROM "MODEL".{table_name}
            WHERE DATE(datetime) <= '{fcst_date.date()}';
            """)
        
        df = pd.read_sql(query, engine, params={'fcst_date': fcst_date})
        df = df.set_index('datetime').sort_index()
        
        return df