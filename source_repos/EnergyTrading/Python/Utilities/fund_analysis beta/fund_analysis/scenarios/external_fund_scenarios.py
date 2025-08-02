"""
Scenarios for External fundamentals
"""

from .scenarios import Scenarios as scenarios
import fund_analysis.input_data as input_data
import pandas as pd
import numpy as np
import datetime as dt
import copy
from fund_analysis.utils import ENUMS as enums
from sklearn.neighbors import KernelDensity
from numba import cuda, jit, float32
import numba.cuda.random as nrand
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import norm
from scipy.optimize import curve_fit
from joblib import Parallel, delayed
import math
from scipy.optimize import minimize
import numba



class ExternalFundScenarios(scenarios):
    
    
    def __init__(self, base_data,
                    base_data_normalized,
                    params_dict,
                    fund_type='ResidualDemand',
                    scenario_type='historical',
                    unique_markets_list=[]):
        super().__init__(base_data)
        self._scenario_type = scenario_type
        self._base_data_normalized = base_data_normalized
        self._fund_type = fund_type
        self._params_dict = params_dict
        if len(unique_markets_list) < 1:
            self.unique_markets_list = self.get_markets_for_residual_load()
        else:
            self.unique_markets_list = unique_markets_list
        self.data_inst_dict = {}
            
    @property
    def scenario_type(self):
        return self._scenario_type
        
    @property
    def base_data_normalized(self):
        return self._base_data_normalized
    
    @property
    def fund_type(self):
        return self._fund_type
    
    @property
    def params_dict(self):
        return self._params_dict
    
    def update_fund_type(self, new_fund_type):
        self._fund_type = new_fund_type
            
    def get_markets_for_residual_load(self):
        return [a.split('_')[1] for a in self.da_data['base'].columns if 'ResidualDemand' in a]
    
    @staticmethod
    def generate_kde_samples_per_month(df, value_col='rld_da', month_col='month', num_samples=1000):
        # Initialize an empty list to store each month's KDE samples
        samples_list = []

        # Loop through each month (from 1 to 12)
        for month in range(1, 13):
            # Filter the data for the current month
            month_data = df[df[month_col] == month][value_col].dropna().values

            if len(month_data) > 1:  # Ensure there are enough data points for KDE
                # Fit the KDE model on the current month's data
                kde = KernelDensity(kernel='gaussian', bandwidth=0.1).fit(month_data[:, np.newaxis])

                # Generate 1000 samples from the fitted KDE
                kde_samples = kde.sample(num_samples).flatten()  # Flatten the samples into a 1D array

                # Ensure no negative values
                kde_samples = np.maximum(kde_samples, 0)

                # Append the samples to the list
                samples_list.append(kde_samples)

        # Create a DataFrame from the samples list (rows = months, columns = samples)
        samples_df = pd.DataFrame(samples_list, index=np.arange(1, 13), columns=[f'sample_{i}' for i in range(1, num_samples + 1)])

        return samples_df
  
    
    # Paralelized GPU version
    # OU process
    @staticmethod
    @cuda.jit
    def apply_ou_process(ou_samples, samples, L, theta, sigma, dt, mean_bias, num_variables, len_month_indices, random_state):
        i, j = cuda.grid(2)
        if i < len_month_indices and j < num_variables:
            current_value = samples[i, j]
    
            # Generate correlated noise
            ou_noise = 0.0
            for k in range(num_variables):
                # Generate random numbers using CUDA's curand (from a uniform distribution in [0, 1])
                rnd = nrand.xoroshiro128p_uniform_float32(random_state, i * num_variables + j)
                noise = (rnd - 0.5) * 2.0  # Convert to a normal-like range approximately in [-1, 1]
                ou_noise += L[j, k] * noise
    
            # Apply the OU process for the next value
            next_value = current_value + theta[j] * (mean_bias - current_value) * dt + sigma[j] * math.sqrt(dt) * ou_noise
    
            # Ensure non-negative values and apply a soft correction for negative values
            if math.isnan(next_value) or math.isinf(next_value):
                next_value = 0.0
            if next_value < 0:
                next_value = current_value * math.exp(-theta[j] * dt)
    
            # Store the generated value
            ou_samples[i, j] = max(next_value, 0)

    
    @staticmethod
    @cuda.jit
    def apply_forecast_weighting_gpu_kernel(forecast_values, ou_samples, weights, result, num_variables, num_periods):
        i, j = cuda.grid(2)
        for sim in range(ou_samples.shape[0]):
            if i < num_periods and j < num_variables:
                # Extract scalar values from device arrays
                forecast_val = forecast_values[i,j]  # Use flattened value
                ou_val = ou_samples[sim, i, j]
                weight = weights[i,0]  # Use flattened value
        
                # Perform the computation
                result[sim, i, j] = weight * forecast_val + (1.0 - weight) * ou_val

    
    def sample_scenarios_with_ou(self, scen_values, tau_values, variance_values, fcst_values, hist_data, variables, num_samples=100, dt=1.0):
        mean_bias = 1.0  # Target mean for convergence
        fcst_values_backup = fcst_values.copy()
        num_periods = len(fcst_values)  # Number of periods from forecast values
        num_variables = len(variables)  # Number of variables
        scenarios_dict = {}  # Initialize scenarios_dict
        
        # Estimate OU parameters from historical data
        def estimate_ou_params(hist_data):
            params_dict = {}
            for var in hist_data.columns:
                x = np.arange(len(hist_data))
                y = hist_data[var].values
                
                def model_fit(x, a, b, a1, b1):
                    omega = 2 * np.pi / 14
                    return a + b * x + a1 * np.cos(omega * x) + b1 * np.sin(omega * x)
                
                params, _ = curve_fit(model_fit, x, y,
                                      bounds=([0 , np.inf]))
                a, b, a1, b1 = params
                theta = np.arctan(a1 / b1)
                alpha = np.sqrt(a1 ** 2 + b1 ** 2)
                params_dict[var] = {'a': a, 'b': b, 'alpha': alpha, 'theta': theta}
            return params_dict
        

    
        ou_params = estimate_ou_params(hist_data)
        
        # Convert theta values to device
        theta_values = np.array([ou_params[var]['theta'] for var in variables], dtype=np.float32)
        theta_values_device = cuda.to_device(theta_values)
    
        # Create month and year indices from fcst_values before arraying
        month_year_indices = np.array([(date.year, date.month) for date in fcst_values.index], dtype=[('year', 'i4'), ('month', 'i4')])
        fcst_values = np.array(fcst_values, dtype=np.float32).round(2).flatten()
    
        # Allocate device memory before launching the CUDA kernel
        tau_values_flat = np.concatenate([val.values.flatten() if isinstance(val, pd.DataFrame) else np.array(val).flatten() for val in tau_values.values()]).astype(np.float32)
        variance_values = np.array(list(variance_values.values())).astype(np.float32)
        tau_values_flat_device = cuda.to_device(tau_values_flat)
        variance_values_device = cuda.to_device(variance_values)
        month_year_indices_device = cuda.to_device(month_year_indices)
    
        # Iterate over each unique (year, month) combination to reduce the number of periods processed at once
        ou_samples = np.zeros((num_samples, num_periods, num_variables), dtype=np.float64)
        unique_month_years = np.unique(month_year_indices)
        for month_year in unique_month_years:
            month_indices_for_month = np.where((month_year_indices == month_year))[0]
            if len(month_indices_for_month) == 0:
                continue
    
            # Retrieve KDE distributions for the given month from scen_values
            kde_distributions = np.zeros((num_variables, 1000), dtype=np.float64)
            for j, variable in enumerate(variables):
                kde_distributions[j, :] = scen_values[variable].loc[month_year[1]].values.flatten()
    
            kde_distributions_device = cuda.to_device(kde_distributions)
    
            # Allocate device memory for the current month's samples
            ou_samples_for_month = np.ascontiguousarray(ou_samples[:, month_indices_for_month, :])
            ou_samples_device = cuda.to_device(ou_samples_for_month)
    
            

            @cuda.jit
            def process_simulation(ou_samples, mean_bias, dt, num_samples, num_variables, num_periods, kde_distributions, tau_values_flat, rng_states, state_transition_matrices, bin_edges_list):
                sim = cuda.grid(1)
                if sim < num_samples:
                    random_state = rng_states[sim]
            
                    # Iterate over variables for each simulation
                    for j in range(num_variables):
                        # Initialize the current value
                        current_value = 0
                        num_bins = state_transition_matrices.shape[1]
                        bin_edges = bin_edges_list[j]
                        max_indices_per_bin = 100  # Assume maximum of 100 elements per bin for simplicity
            
                        for k in range(num_periods):
                            if k == 0:
                                # Step 1: Set initial value for the first time step, draw a random sample from KDE
                                rand_num = nrand.xoroshiro128p_uniform_float32(rng_states, sim)
                                idx = int(math.trunc(rand_num * (kde_distributions.shape[1] - 1)))
                                idx = min(max(idx, 0), kde_distributions.shape[1] - 1)
                                current_value = max(kde_distributions[j, idx], 0)
                                ou_samples[sim, k, j] = current_value
                                continue
            
                            # Step 2: Determine the current state based on quantile bins
                            current_state = 0
                            for i in range(len(bin_edges) - 1):
                                if bin_edges[i] <= current_value < bin_edges[i + 1]:
                                    current_state = i
                                    break
                            current_state = max(0, min(num_bins - 1, current_state))
            
                            # Step 3: Bin the KDE values based on the bin edges
                            binned_indices = cuda.local.array((10, 100), numba.int32)  # Assuming 10 bins and max 100 elements per bin
                            bin_counts = cuda.local.array((10,), numba.int32)  # Track count of elements in each bin
                            for i in range(len(bin_counts)):
                                bin_counts[i] = 0
            
                            for i in range(len(kde_distributions[j])):
                                for b in range(len(bin_edges) - 1):
                                    if bin_edges[b] <= kde_distributions[j, i] < bin_edges[b + 1]:
                                        if bin_counts[b] < max_indices_per_bin:
                                            binned_indices[b, bin_counts[b]] = i
                                            bin_counts[b] += 1
                                        break
            
                            # Step 4: Apply weights to the binned KDE
                            kde_weights = state_transition_matrices[j, current_state, :]
                            weighted_bins = cuda.local.array((10,), numba.float32)
                            for b in range(num_bins):
                                weighted_bins[b] = bin_counts[b] * kde_weights[b]
            
                            # Step 5: Normalize to create probabilities
                            total_weight = 0.0
                            for b in range(num_bins):
                                total_weight += weighted_bins[b]
            
                            if total_weight > 0:
                                for b in range(num_bins):
                                    weighted_bins[b] /= total_weight
            
                            # Step 6: Sample from the weighted bins
                            rand_num = nrand.xoroshiro128p_uniform_float32(rng_states, sim)
                            cumulative_prob = 0.0
                            idx = 0
                            for b in range(num_bins):
                                cumulative_prob += weighted_bins[b]
                                if rand_num < cumulative_prob:
                                    idx = b
                                    break
            
                            # Step 7: Draw an index from the selected bin
                            if bin_counts[idx] > 0:
                                selected_idx = binned_indices[idx, int(nrand.xoroshiro128p_uniform_float32(rng_states, sim) * bin_counts[idx])]
                                proposed_sample = kde_distributions[j, selected_idx]
                            else:
                                proposed_sample = 0.0
            
                            # Update the current value directly using the proposed value
                            current_value = proposed_sample
                            ou_samples[sim, k, j] = current_value







            
            def compute_state_transition_matrix(hist_data, num_bins=10):
                """
                Compute an adaptive state transition matrix from historical data using quantile-based binning.
                
                Parameters:
                hist_data (pd.DataFrame): Historical time series data to compute the state transition matrix from.
                num_bins (int): Number of quantile bins to discretize the data into.
            
                Returns:
                tuple: State transition matrix representing the transition probabilities between states, and bin edges for each variable.
                """
                num_variables = hist_data.shape[1]
                state_transition_matrices = []
                bin_edges_list = []
            
                # Discretize each variable's data into 'num_bins' quantile bins
                for j in range(num_variables):
                    data = hist_data.iloc[:, j]
                    # Create quantile-based bins
                    binned_data, bin_edges = pd.qcut(data, q=num_bins, labels=False, retbins=True, duplicates='drop')
                    bin_edges_list.append(bin_edges)
            
                    # Initialize the transition matrix for the variable
                    transition_matrix = np.zeros((num_bins, num_bins))
            
                    # Count transitions between bins
                    for k in range(1, len(binned_data)):
                        prev_state = binned_data.iloc[k - 1]
                        curr_state = binned_data.iloc[k]
                        if not pd.isna(prev_state) and not pd.isna(curr_state):
                            transition_matrix[prev_state, curr_state] += 1
            
                    # Normalize each row to get probabilities (each row should sum to 1)
                    row_sums = transition_matrix.sum(axis=1, keepdims=True)
                    transition_matrix = np.divide(transition_matrix, row_sums, where=row_sums != 0)
            
                    state_transition_matrices.append(transition_matrix)
            
                return np.array(state_transition_matrices), bin_edges_list





            threads_per_block = 256  # Increased to boost occupancy and workload per block
            blocks_per_grid = (num_samples + threads_per_block - 1) // threads_per_block
            
            if blocks_per_grid < 48:
                blocks_per_grid = 96*2
    
            # Allocate random states for each sample
            rng_states = nrand.create_xoroshiro128p_states(num_samples, seed=1)
            
            state_transition_matrices, bin_edge_list = compute_state_transition_matrix(hist_data)
            
            state_transition_matrices_device = cuda.to_device(state_transition_matrices)
            bin_edges_list_device = cuda.to_device(bin_edge_list)
            
            print('Processing scenarios')
    
            # Launch the CUDA kernel for the current month
            process_simulation[blocks_per_grid, threads_per_block](
                                        ou_samples_device, mean_bias, dt,
                                        num_samples, num_variables, len(month_indices_for_month),
                                        kde_distributions_device, tau_values_flat_device,
                                        rng_states, state_transition_matrices_device, bin_edges_list_device
                                    )
            
            print('Processing ends')

    
            # Copy the result back to host for the current month
            ou_samp_month = ou_samples_device.copy_to_host()
            mean_values = mean_bias / np.mean(ou_samp_month, axis=1, keepdims=True)  # Shape becomes (100, 1, 5)
            result = mean_values * ou_samp_month  # Now broadcasting works
            ou_samples[:, month_indices_for_month, :] = result
    
            # Cleanup device memory for the current month
            del ou_samples_device, kde_distributions_device
            cuda.current_context().deallocations.clear()
    
        # Apply forecast weighting after correction using GPU
        forecast_values_device = cuda.to_device(fcst_values.astype(np.float64))
        # ou_samples_device = cuda.to_device(ou_samples.reshape(-1, num_variables))
        ou_samples_device = cuda.to_device(ou_samples.astype(np.float64))
        weights = np.array([0.95, 0.90, 0.85, 0.7, 0.6] + list(np.linspace(0.5, 0.1, max(0, num_periods // 24 - 6))), dtype=np.float64)
    
        if len(weights) < num_periods:
            weights = np.concatenate([weights, np.zeros(num_periods - len(weights))], axis=0)
        else:
            weights = weights[:num_periods]
    
        weights_device = cuda.to_device(weights[:, np.newaxis])
        result_device = cuda.device_array_like(ou_samples_device)
    
        threads_per_block = (16, 16)
        blocks_per_grid_x = (num_periods + threads_per_block[0] - 1) // threads_per_block[0]
        blocks_per_grid_y = (num_variables + threads_per_block[1] - 1) // threads_per_block[1]
        blocks_per_grid = (blocks_per_grid_x, blocks_per_grid_y)
        
        forecast_values_2d = np.array(fcst_values_backup, dtype=np.float32).round(2)
        forecast_values_2d_device = cuda.to_device(forecast_values_2d)
    
        self.apply_forecast_weighting_gpu_kernel[blocks_per_grid, threads_per_block](
            forecast_values_2d_device, ou_samples_device, weights_device, result_device, num_variables,num_periods
        )
    
        ou_samples = result_device.copy_to_host().reshape(num_samples, num_periods, num_variables)
    
        # Cleanup device memory
        del forecast_values_device, ou_samples_device, weights_device, result_device, theta_values_device
        cuda.current_context().deallocations.clear()
    
        # Construct scenarios dictionary from the OU samples
        for sim in range(num_samples):
            scenarios_dict[f'ExtDataSim_{sim + 1}'] = pd.DataFrame(ou_samples[sim], index=np.arange(num_periods), columns=variables)
    
        return scenarios_dict





    @staticmethod
    def compute_kendall_tau_per_month(time_series):
        tau_dict = {}

        # Extract the 'month' from the datetime index
        time_series['month'] = time_series.index.month

        # Group by month and compute the Kendall's Tau correlation matrix for each month
        for month in range(1, 13):
            subset = time_series[time_series['month'] == month]
            
            # Compute the Kendall's Tau correlation matrix if there are enough data points
            if len(subset) > 1:
                tau_matrix = subset.drop('month', axis=1).corr(method='kendall')
                tau_dict[f'month_{month}'] = tau_matrix
            else:
                tau_dict[f'month_{month}'] = None

        return tau_dict
    
    def get_historical_scenarios(self, scen_list, fcst_date):
        if self.fund_type in ['ResidualDemand']:
            # Get wind historical data
            wind_inst = input_data.Wind(params_dict=self.params_dict,
                                        normalize_bool=True)
            wind_inst.set_pivot_date(fcst_date-dt.timedelta(days=1))
            wind_inst.unique_markets_list = ['de', 'fr', 'be', 'nl', 'at', 'es']
            wind_inst.get_mid_data()
            wind_inst.get_month_data()
            wind_inst.update_mid_data()
            wind_inst.get_da_data()
            wind_inst.get_curve()
            # Get solar historical data
            solar_inst = input_data.Solar(params_dict=self.params_dict,
                                          normalize_bool=True)
            solar_inst.set_pivot_date(fcst_date-dt.timedelta(days=1))
            solar_inst.unique_markets_list = ['de', 'fr', 'be', 'nl', 'at','es']
            solar_inst.get_mid_data()
            solar_inst.get_month_data()
            solar_inst.update_mid_data()
            solar_inst.get_da_data()
            solar_inst.get_curve()
            
            # Use lists to collect data for efficient concatenation
            da_data_list = []
            curve_nominal_list = []
            curve_normalized_list = []

            for market, market_da in wind_inst.da_data_normalized.items():
                temp_solar_normalized = solar_inst.da_data_normalized[market].copy()
                temp_wind_normalized = market_da.copy()
                temp_solar_curve_nominal = solar_inst.data_curve[market].copy()
                temp_wind_curve_nominal = wind_inst.data_curve[market].copy()
                temp_solar_curve_normalized = solar_inst.data_curve_normalized[market].copy()
                temp_wind_curve_normalized = wind_inst.data_curve_normalized[market].copy()
                
                # Calculate daily average data for the market
                temp = pd.concat([temp_solar_normalized, temp_wind_normalized], axis=1)
                temp[market] = np.where(temp['Solar'] == 0, temp['Wind'], (temp['Solar'] + temp['Wind']) / 2)
                da_data_list.append(temp[[market]].copy())

                # Calculate nominal curve data for the market
                temp_curve_nominal = pd.concat([temp_solar_curve_nominal, temp_wind_curve_nominal], axis=1)
                temp_curve_nominal[market] = temp_curve_nominal['Solar'] + temp_curve_nominal['Wind']
                curve_nominal_list.append(temp_curve_nominal[[market]].copy())
                
                # Calculate normalized curve data for the market
                temp_curve_normalized = pd.concat([temp_solar_curve_normalized, temp_wind_curve_normalized], axis=1)
                temp_curve_normalized[market] = np.where(temp_curve_normalized['Solar'] == 0,
                                                         temp_curve_normalized['Wind'],
                                                         (temp_curve_normalized['Solar'] + temp_curve_normalized['Wind']) / 2)
                curve_normalized_list.append(temp_curve_normalized[[market]].copy())
            
            # Concatenate all data collected in the lists
            da_data = pd.concat(da_data_list, axis=1)
            curve_nominal = pd.concat(curve_nominal_list, axis=1)
            curve_normalized = pd.concat(curve_normalized_list, axis=1)

            # Get normalized curve
            res_normal_curve = self.get_normal_curve(normalized_curve=curve_normalized,
                                                     nominal_curve=curve_nominal)
            res_nominal_curve = curve_nominal.copy()
            del curve_nominal, curve_normalized
            res_normal_curve['month'] = res_normal_curve.index.month
        
        monthly_scen_dict = {}
        variance_dict = {}
        
        # Parallelize variance computation and KDE sampling using GPU if possible
        da_data['month'] = da_data.index.month
        variance_dict = {rld_col: da_data[[rld_col]].var().iloc[0] for rld_col in da_data.columns}
          # Generate KDE samples per month in parallel
        monthly_scen_dict = {rld_col: self.generate_kde_samples_per_month(da_data[[rld_col, 'month']].copy(),
                                                                  value_col=rld_col,
                                                                  month_col='month')
                     for rld_col in da_data.columns if rld_col != 'month'}
        
        tau_dict = self.compute_kendall_tau_per_month(da_data)
        
        # Get both normal and monthly curves
        normal_curve = self.get_normal_curve()
        normal_curve = normal_curve[[a for a in normal_curve.columns if self.fund_type in a]]
        normal_curve = normal_curve[[f"ResidualDemand_{a}" for a in monthly_scen_dict.keys()]]
        normal_curve['month'] = normal_curve.index.month
        
        # Get monthly curve and combine with normal
        monthly_curve = self.get_monthly_curve()
        combined_curve = self.combine_normal_and_monthly_curves(normal_curve, monthly_curve)

        # Align with res_normal_curve, not curve_normalized
        if 'res_normal_curve' in locals():
            combined_curve, res_normal_curve = combined_curve.align(res_normal_curve, join='inner', axis=0)

        # Sample scenarios with OU process using GPU
        percentiles_dict = self.sample_scenarios_with_ou(
            monthly_scen_dict,
            tau_dict,
            variance_dict,
            res_normal_curve,  # Use res_normal_curve as forecast values
            da_data.drop(['month'], axis=1).dropna(),
            list(da_data.drop(['month'], axis=1).columns),
            num_samples=100
        )
        
          # Create scenario curves dict
        scen_curves_dict = {}
        percentiles_arr = np.stack([df.values for df in percentiles_dict.values()],axis=0)
        combined_curve_arr = combined_curve.drop(['month'],axis=1).values
        res_normal_curve_arr = res_normal_curve.drop(['month'],axis=1).values
        res_nominal_curve_arr = res_nominal_curve.values
        
        
        
        # Map percentiles scenarios to their corresponding month values using GPU parallelization
        scen_curves_arr = self.map_scenarios_to_rld(percentiles_arr, combined_curve_arr, res_nominal_curve_arr)
        
        scen_curves_dict = {a: pd.DataFrame(scen_curves_arr[i],columns=combined_curve.drop(['month'],axis=1).columns,
                                            index=combined_curve.index)
                            for i, a in enumerate(percentiles_dict.keys())}
        
        scen_curves_dict = self.add_percentiles(scen_curves_dict)
        
        return scen_curves_dict
    
    def add_percentiles(self, scen_curves_dict):
        for market, market_dict in self.base_data['perc'].items():
            temp = pd.concat([v[f"ResidualDemand_{market}"] for a, v in scen_curves_dict.items() if 'ExtDataSim' in a],axis=1,
                             keys=[k for k in scen_curves_dict.keys()])
            for perc, perc_df in market_dict.items():
                perc_name = f"{perc}th_perc"
                if perc_name not in scen_curves_dict:
                    scen_curves_dict[perc_name] = pd.DataFrame()
                temp_perc = pd.DataFrame(temp.quantile(perc/100,axis=1))
                temp_perc.columns = perc_df.columns
                temp_perc = perc_df.combine_first(temp_perc)
                temp_perc.columns = [f"ResidualDemand_{market}"]
                if scen_curves_dict[perc_name].empty:
                    scen_curves_dict[perc_name] = temp_perc.copy()
                else:
                    scen_curves_dict[perc_name] = pd.concat([scen_curves_dict[perc_name],
                                                             temp_perc], axis=1)
        return scen_curves_dict
    
    @staticmethod
    def map_scenarios_to_rld(percentiles_arr, normal_curve_arr, res_normal_curve_arr, threads_per_block=(16, 16)):
        @cuda.jit
        def map_scenarios_kernel(results, percentiles_arr, normal_curve_arr, res_normal_curve_arr):
            # Calculate 2D indices for the thread in the grid
            x, y = cuda.grid(2)
    
            # Ensure the indices are within the bounds of the 2D slice
            if x < percentiles_arr.shape[1] and y < percentiles_arr.shape[2]:
                # Iterate over the depth dimension
                for d in range(percentiles_arr.shape[0]):
                    results[d, x, y] = normal_curve_arr[x, y] - (res_normal_curve_arr[x, y] * (percentiles_arr[d, x, y] - 1))

        # Initialize the results array
        results = np.zeros(percentiles_arr.shape, dtype=np.float64)

        # Transfer data to GPU
        d_percentiles_arr = cuda.to_device(percentiles_arr)
        d_normal_curve_arr = cuda.to_device(normal_curve_arr)
        d_res_normal_curve_arr = cuda.to_device(res_normal_curve_arr)
        d_results = cuda.to_device(results)

        # Define the number of blocks per grid
        num_rows, num_columns = normal_curve_arr.shape
        blocks_per_grid_x = (num_rows + threads_per_block[0] - 1) // threads_per_block[0]
        blocks_per_grid_y = (num_columns + threads_per_block[1] - 1) // threads_per_block[1]
        blocks_per_grid = (blocks_per_grid_x, blocks_per_grid_y)

        # Launch the CUDA kernel
        map_scenarios_kernel[blocks_per_grid, threads_per_block](d_results, d_percentiles_arr, d_normal_curve_arr, d_res_normal_curve_arr)

        # Synchronize to ensure that the GPU has finished the computations
        cuda.synchronize()

        # Copy the result back to host
        results = d_results.copy_to_host()

        # Clean up GPU memory
        del d_percentiles_arr
        del d_normal_curve_arr
        del d_res_normal_curve_arr
        del d_results
        cuda.current_context().deallocations.clear()  # Clear any deallocated GPU memory from the context

        return results
        
        
    
    
    # GPU parallelizable function for variance computation (example)
    @staticmethod
    @cuda.jit
    def compute_variance_gpu(data, result):
        i = cuda.grid(1)
        if i < data.shape[1]:
            mean = 0.0
            for j in range(data.shape[0]):
                mean += data[j, i]
            mean /= data.shape[0]
            var = 0.0
            for j in range(data.shape[0]):
                var += (data[j, i] - mean) ** 2
            var /= data.shape[0]
            result[i] = var

    def parallel_variance_computation(self, da_data):
        # Convert data to GPU array
        data_device = cuda.to_device(da_data.values)
        result_device = cuda.device_array(da_data.shape[1], dtype=np.float32)
        
        # Configure the blocks
        threads_per_block = 128
        blocks_per_grid = (da_data.shape[1] + (threads_per_block - 1)) // threads_per_block
        
        # Launch the kernel
        self.compute_variance_gpu[blocks_per_grid, threads_per_block](data_device, result_device)
        
        # Copy the result back to host
        result = result_device.copy_to_host()
        
        # Create a variance dictionary
        variance_dict = {col: result[i] for i, col in enumerate(da_data.columns)}
        return variance_dict

    # GPU parallelizable function for mapping percentiles to months
    @staticmethod
    @cuda.jit
    def map_percentiles_gpu(percentile_values, normal_curve_values, res_normal_curve_values, result):
        i, j = cuda.grid(2)
        if i < percentile_values.shape[0] and j < percentile_values.shape[1]:
            result[i, j] = normal_curve_values[i, j] - (res_normal_curve_values[i, j] * (percentile_values[i, j] - 1))

    def map_percentiles_to_months_gpu(self, percentiles_dict, normal_curve, res_normal_curve):
        scen_curves_dict = {}
        threads_per_block = (16, 16)
        
        for percentile, percentile_df in percentiles_dict.items():
            scen_name = f"{self.fund_type}_{percentile}"
            scen_list = []
            for col in percentile_df.columns:
                rld_col_name = f'ResidualDemand_{col}'
                
                # Convert data to GPU arrays
                percentile_values_device = cuda.to_device(percentile_df[col].values)
                normal_curve_values_device = cuda.to_device(normal_curve[rld_col_name].values)
                res_normal_curve_values_device = cuda.to_device(res_normal_curve[col].values)
                result_device = cuda.device_array_like(percentile_values_device)
                
                # Configure the blocks
                blocks_per_grid_x = (percentile_df.shape[0] + threads_per_block[0] - 1) // threads_per_block[0]
                blocks_per_grid_y = (percentile_df.shape[1] + threads_per_block[1] - 1) // threads_per_block[1]
                blocks_per_grid = (blocks_per_grid_x, blocks_per_grid_y)
                
                # Launch the kernel
                self.map_percentiles_gpu[blocks_per_grid, threads_per_block](
                    percentile_values_device, normal_curve_values_device, res_normal_curve_values_device, result_device
                )
                
                # Copy result back to host
                temp = pd.Series(result_device.copy_to_host(), index=percentile_df.index, name=rld_col_name)
                scen_list.append(temp)
            scen_curves_dict[scen_name] = pd.concat(scen_list, axis=1)
        return scen_curves_dict

    
    def get_normal_curve(self, nominal_curve=None,
                            normalized_curve=None):
        if nominal_curve is None:
            nominal_curve = copy.deepcopy(self.base_data['curve']['base'])
        if normalized_curve is None:
            normalized_curve = copy.deepcopy(self.base_data_normalized['curve']['base'])
        normal_curve = (nominal_curve/normalized_curve).dropna(axis=1, how='all')
        del nominal_curve, normalized_curve
        return normal_curve
    
    def get_monthly_curve(self):
        """Get monthly forecast curve from base_data"""
        try:
            monthly_curve = copy.deepcopy(self.base_data['curve']['month'])
            monthly_curve = monthly_curve[[a for a in monthly_curve.columns if self.fund_type in a]]
            monthly_curve['month'] = monthly_curve.index.month
            return monthly_curve
        except KeyError:
            # If no monthly data available, return None
            return None

    def combine_normal_and_monthly_curves(self, normal_curve, monthly_curve):
        """
        Combine normal and monthly curves:
        - Use MONTH data where available (typically first 30 days)
        - Use NORMAL data for the rest
        """
        if monthly_curve is None:
            return normal_curve
        
        combined_curve = normal_curve.copy()
        
        # Align the curves
        monthly_curve, combined_curve = monthly_curve.align(combined_curve, join='outer', axis=0)
        
        # For each column, use monthly data where available, normal elsewhere
        for col in combined_curve.columns:
            if col in monthly_curve.columns and col != 'month':
                # Use monthly data where it's not null, otherwise keep normal
                mask = monthly_curve[col].notna()
                combined_curve.loc[mask, col] = monthly_curve.loc[mask, col]
        
        return combined_curve
    
    def get_scenarios(self, scen_type:dict = {'historical':
        [a/100 for a in list(range(1,100))]},
                      fcst_date=None):
        if fcst_date is None:
            fcst_date = self.params_dict['eD']
        if list(scen_type)[0] in ['historical']:
            return self.get_historical_scenarios(scen_list=\
                scen_type['historical'],
                fcst_date=fcst_date)
                
    # def sample_scenarios_with_ou(self, scen_values, tau_values, variance_values, fcst_values, hist_data, variables, num_samples=100, dt=1.0):
    #     mean_bias = 1.0  # Target mean for convergence
    #     fcst_values_backup = fcst_values.copy()
    #     num_periods = len(fcst_values)  # Number of periods from forecast values
    #     num_variables = len(variables)  # Number of variables
    #     scenarios_dict = {}  # Initialize scenarios_dict
        
    #     # Estimate OU parameters from historical data
    #     def estimate_ou_params(hist_data):
    #         params_dict = {}
    #         for var in hist_data.columns:
    #             x = np.arange(len(hist_data))
    #             y = hist_data[var].values
                
    #             def model_fit(x, a, b, a1, b1):
    #                 omega = 2 * np.pi / 14
    #                 return a + b * x + a1 * np.cos(omega * x) + b1 * np.sin(omega * x)
                
    #             params, _ = curve_fit(model_fit, x, y,
    #                                   bounds=([0 , np.inf]))
    #             a, b, a1, b1 = params
    #             theta = np.arctan(a1 / b1)
    #             alpha = np.sqrt(a1 ** 2 + b1 ** 2)
    #             params_dict[var] = {'a': a, 'b': b, 'alpha': alpha, 'theta': theta}
    #         return params_dict
        

    
    #     ou_params = estimate_ou_params(hist_data)
        
    #     # Convert theta values to device
    #     theta_values = np.array([ou_params[var]['theta'] for var in variables], dtype=np.float32)
    #     theta_values_device = cuda.to_device(theta_values)
    
    #     # Create month and year indices from fcst_values before arraying
    #     month_year_indices = np.array([(date.year, date.month) for date in fcst_values.index], dtype=[('year', 'i4'), ('month', 'i4')])
    #     fcst_values = np.array(fcst_values, dtype=np.float32).round(2).flatten()
    
    #     # Allocate device memory before launching the CUDA kernel
    #     tau_values_flat = np.concatenate([val.values.flatten() if isinstance(val, pd.DataFrame) else np.array(val).flatten() for val in tau_values.values()]).astype(np.float32)
    #     variance_values = np.array(list(variance_values.values())).astype(np.float32)
    #     tau_values_flat_device = cuda.to_device(tau_values_flat)
    #     variance_values_device = cuda.to_device(variance_values)
    #     month_year_indices_device = cuda.to_device(month_year_indices)
    
    #     # Iterate over each unique (year, month) combination to reduce the number of periods processed at once
    #     ou_samples = np.zeros((num_samples, num_periods, num_variables), dtype=np.float64)
    #     unique_month_years = np.unique(month_year_indices)
    #     for month_year in unique_month_years:
    #         month_indices_for_month = np.where((month_year_indices == month_year))[0]
    #         if len(month_indices_for_month) == 0:
    #             continue
    
    #         # Retrieve KDE distributions for the given month from scen_values
    #         kde_distributions = np.zeros((num_variables, 1000), dtype=np.float64)
    #         for j, variable in enumerate(variables):
    #             kde_distributions[j, :] = scen_values[variable].loc[month_year[1]].values.flatten()
    
    #         kde_distributions_device = cuda.to_device(kde_distributions)
    
    #         # Allocate device memory for the current month's samples
    #         ou_samples_for_month = np.ascontiguousarray(ou_samples[:, month_indices_for_month, :])
    #         ou_samples_device = cuda.to_device(ou_samples_for_month)
    
    #         @cuda.jit
    #         def process_simulation(ou_samples, mean_bias, dt, num_samples, num_variables, num_periods, kde_distributions, tau_values_flat, variance_values, rng_states, theta_values):
    #             sim = cuda.grid(1)
    #             if sim < num_samples:
    #                 random_state = rng_states[sim]
            
    #                 # Iterate over variables for each simulation
    #                 for j in range(num_variables):
    #                     theta = theta_values[j]
    #                     # Apply the OU process to generate samples for each time step
    #                     for k in range(num_periods):
    #                         # Sample from the KDE distribution at each time step
    #                         rand_num = nrand.xoroshiro128p_uniform_float32(rng_states, sim)  # Correctly pass both rng_states and sim
    #                         idx = int(math.trunc(rand_num * (kde_distributions.shape[1] - 1)))
            
    #                         # Ensure idx is within valid range
    #                         idx = min(max(idx, 0), kde_distributions.shape[1] - 1)
            
    #                         sampled_value = kde_distributions[j, idx] - mean_bias
            
    #                         if k == 0:
    #                             # Set initial value for the first time step
    #                             ou_samples[sim, k, j] = sampled_value
    #                         else:
    #                             # Apply OU process for subsequent time steps
    #                             ou_samples[sim, k, j] = ou_samples[sim, k - 1, j] + theta * (mean_bias - ou_samples[sim, k - 1, j]) * dt + sampled_value
                                
    #         @cuda.jit
    #         def process_simulation(ou_samples, mean_bias, dt, num_samples, num_variables, num_periods, kde_distributions, tau_values_flat, variance_values, rng_states, theta_values):
    #             sim = cuda.grid(1)
    #             if sim < num_samples:
    #                 random_state = rng_states[sim]
            
    #                 # Iterate over variables for each simulation
    #                 for j in range(num_variables):
    #                     theta = theta_values[j]
    #                     # Apply the OU process to generate samples for each time step
    #                     for k in range(num_periods):
    #                         # Sample from the KDE distribution at each time step
    #                         rand_num = nrand.xoroshiro128p_uniform_float32(rng_states, sim)  # Correctly pass both rng_states and sim
    #                         idx = int(math.trunc(rand_num * (kde_distributions.shape[1] - 1)))
            
    #                         # Ensure idx is within valid range
    #                         idx = min(max(idx, 0), kde_distributions.shape[1] - 1)
            
    #                         proposed_sample = kde_distributions[j, idx] - mean_bias
            
    #                         # Filter the proposed value through Metropolis-Hastings
    #                         if k == 0:
    #                             # Set initial value for the first time step, ensuring it is non-negative
    #                             current_value = max(proposed_sample, 0)
    #                         else:
    #                             # Apply OU process for subsequent time steps
    #                             new_value = ou_samples[sim, k - 1, j] + theta * (mean_bias - ou_samples[sim, k - 1, j]) * dt + proposed_sample
            
    #                             # Ensure proposed value is within a reasonable range
    #                             if new_value < 0:
    #                                 new_value = ou_samples[sim, k - 1, j] * 0.5  # Limit further downside
            
    #                             # Metropolis-Hastings acceptance step
    #                             current_density = kde_distributions[j, idx]  # KDE density at the current state
    #                             proposed_density = kde_distributions[j, idx]  # KDE density at the proposed state (using the same index as a simplification)
            
    #                             # Calculate acceptance probability
    #                             acceptance_prob = min(1.0, proposed_density / (current_density + 1e-10))  # Add small value to avoid division by zero
    #                             random_acceptance = nrand.xoroshiro128p_uniform_float32(rng_states, sim)
            
    #                             # Accept or reject the proposed sample
    #                             if random_acceptance < acceptance_prob:
    #                                 current_value = new_value  # Accept the proposed value
    #                             else:
    #                                 current_value = ou_samples[sim, k - 1, j]  # Reject and keep the previous value
            
    #                         ou_samples[sim, k, j] = current_value


    #         threads_per_block = 128  # Increased to boost occupancy and workload per block
    #         blocks_per_grid = (num_samples + threads_per_block - 1) // threads_per_block
            
    #         if blocks_per_grid < 48:
    #             blocks_per_grid = 48
    
    #         # Allocate random states for each sample
    #         rng_states = nrand.create_xoroshiro128p_states(num_samples, seed=1)
    
    #         # Launch the CUDA kernel for the current month
    #         process_simulation[blocks_per_grid, threads_per_block](ou_samples_device, mean_bias, dt,
    #                                    num_samples, num_variables, len(month_indices_for_month),
    #                                    kde_distributions_device, tau_values_flat_device,
    #                                    variance_values_device, rng_states, theta_values_device)
    
    #         # Copy the result back to host for the current month
    #         ou_samp_month = ou_samples_device.copy_to_host()
    #         mean_values = mean_bias / np.mean(ou_samp_month, axis=1, keepdims=True)  # Shape becomes (100, 1, 5)
    #         result = mean_values * ou_samp_month  # Now broadcasting works
    #         ou_samples[:, month_indices_for_month, :] = result
    
    #         # Cleanup device memory for the current month
    #         del ou_samples_device, kde_distributions_device
    #         cuda.current_context().deallocations.clear()
    
    #     # Apply forecast weighting after correction using GPU
    #     forecast_values_device = cuda.to_device(fcst_values.astype(np.float64))
    #     # ou_samples_device = cuda.to_device(ou_samples.reshape(-1, num_variables))
    #     ou_samples_device = cuda.to_device(ou_samples.astype(np.float64))
    #     weights = np.array([0.95, 0.90, 0.85, 0.7, 0.6] + list(np.linspace(0.5, 0.1, max(0, num_periods // 24 - 6))), dtype=np.float64)
    
    #     if len(weights) < num_periods:
    #         weights = np.concatenate([weights, np.zeros(num_periods - len(weights))], axis=0)
    #     else:
    #         weights = weights[:num_periods]
    
    #     weights_device = cuda.to_device(weights[:, np.newaxis])
    #     result_device = cuda.device_array_like(ou_samples_device)
    
    #     threads_per_block = (16, 16)
    #     blocks_per_grid_x = (num_periods + threads_per_block[0] - 1) // threads_per_block[0]
    #     blocks_per_grid_y = (num_variables + threads_per_block[1] - 1) // threads_per_block[1]
    #     blocks_per_grid = (blocks_per_grid_x, blocks_per_grid_y)
        
    #     forecast_values_2d = np.array(fcst_values_backup, dtype=np.float32).round(2)
    #     forecast_values_2d_device = cuda.to_device(forecast_values_2d)
    
    #     self.apply_forecast_weighting_gpu_kernel[blocks_per_grid, threads_per_block](
    #         forecast_values_2d_device, ou_samples_device, weights_device, result_device, num_variables,num_periods
    #     )
    
    #     ou_samples = result_device.copy_to_host().reshape(num_samples, num_periods, num_variables)
    
    #     # Cleanup device memory
    #     del forecast_values_device, ou_samples_device, weights_device, result_device, theta_values_device
    #     cuda.current_context().deallocations.clear()
    
    #     # Construct scenarios dictionary from the OU samples
    #     for sim in range(num_samples):
    #         scenarios_dict[f'Simulation_{sim + 1}'] = pd.DataFrame(ou_samples[sim], index=np.arange(num_periods), columns=variables)
    
    #     return scenarios_dict
