from .scenarios import Scenarios as scenarios
import fund_analysis.input_data as input_data
import pandas as pd
import numpy as np
import datetime as dt
import copy
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression
from sklearn.cluster import KMeans
from copulas.multivariate import GaussianMultivariate
from scipy.stats import norm

class FuelScenarios(scenarios):
    
    def __init__(self, base_data, fuel_type):
        super().__init__(base_data)
        self._fuel_type = fuel_type
        
    @property
    def fuel_type(self):
        return self._fuel_type
        
    # Basic scenarios given potential percentage changes
    def get_defined_scenarios(self, scen_list: list):
        scen_dict = {}
        for i, scen in enumerate(scen_list):
            scen_name = f'{self.fuel_type}_{(i+1)/10 * 100}th'
            scen_dict[scen_name] = self.curve_data['base'][[self.fuel_type]] * (1 + scen)
        return scen_dict
    
    
    def get_mcr_scenarios(self, n_samples=1000, std_steps=(-2, -1, 0, 1, 2), scen_list=None):
        # Resample to weekly means
        da_data_weekly = self.da_data['base'][['ttf', 'api2', 'eua']].resample('W').mean().dropna()
    
        # Compute percent change and log-transform non-zero changes
        log_diffs = da_data_weekly.pct_change().dropna() + 1
        for col in ['ttf', 'api2', 'eua']:
            log_diffs[col] = log_diffs[col][log_diffs[col] != 0].apply(np.log).dropna()
    
        # Extract last 52 weeks for copula training
        historical_data = log_diffs.iloc[-52*2:]
    
        # Fit Gaussian copula to the historical data
        copula = GaussianMultivariate()
        copula.fit(historical_data)
    
        # Sample from the copula
        samples = copula.sample(n_samples)
    
        # Calculate standard deviation for TTF
        ttf_std = log_diffs['ttf'].std()
    
        # Filter samples for -1 std first
        neg_filtered_samples = samples[
            (samples['ttf'] >= -1.1 * ttf_std) & (samples['ttf'] <= -0.9 * ttf_std)
        ]
    
        # Get base prices from the first row of daily resampled curve data
        base_prices = self.curve_data['base'].resample('D').mean().iloc[0]
    
        # Transform filtered samples to actual prices for -1 std
        neg_transformed_prices = {
            'ttf': base_prices['ttf'] * np.exp(neg_filtered_samples['ttf']),
            'api2': base_prices['api2'] * np.exp(neg_filtered_samples['api2']),
            'eua': base_prices['eua'] * np.exp(neg_filtered_samples['eua'])
        }
    
        # Compute MCR for -1 std transformed prices
        neg_mcr_values = (
            (neg_transformed_prices['ttf'] + 0.2 * neg_transformed_prices['eua'])
            / (neg_transformed_prices['api2'] / 6.5 + 0.35 * neg_transformed_prices['eua'])
        )
    
        # Repeat for +1 std
        pos_filtered_samples = samples[
            (samples['ttf'] >= 0.9 * ttf_std) & (samples['ttf'] <= 1.1 * ttf_std)
        ]
    
        pos_transformed_prices = {
            'ttf': base_prices['ttf'] * np.exp(pos_filtered_samples['ttf']),
            'api2': base_prices['api2'] * np.exp(pos_filtered_samples['api2']),
            'eua': base_prices['eua'] * np.exp(pos_filtered_samples['eua'])
        }
    
        pos_mcr_values = (
            (pos_transformed_prices['ttf'] + 0.2 * pos_transformed_prices['eua'])
            / (pos_transformed_prices['api2'] / 6.5 + 0.35 * pos_transformed_prices['eua'])
        )
    
        # Define target MCRs
        historical_mcr = (
            (da_data_weekly['ttf'] + 0.2 * da_data_weekly['eua'])
            / (da_data_weekly['api2'] / 6.5 + 0.35 * da_data_weekly['eua'])
        )
        mcr_std = historical_mcr.std()
        target_mcrs = [historical_mcr.mean() - mcr_std, historical_mcr.mean() + mcr_std]
    
        scen_dict = {}
        for which_std, target_mcr, mcr_values, transformed_prices in zip(
            ['-1_std', '1_std'], target_mcrs, [neg_mcr_values, pos_mcr_values], [neg_transformed_prices, pos_transformed_prices]
        ):
            closest_idx = (np.abs(mcr_values - target_mcr)).idxmin()
    
            # Get the closest triplet and compute adjustments
            closest_prices = {
                'ttf': transformed_prices['ttf'].loc[closest_idx],
                'api2': transformed_prices['api2'].loc[closest_idx],
                'eua': transformed_prices['eua'].loc[closest_idx]
            }
    
            # Apply the differences to the entire curve data
            temp = self.curve_data['base'][['ttf', 'api2', 'eua']].copy()
            for col in ['ttf', 'api2', 'eua']:
                temp[col] *= closest_prices[col] / base_prices[col]
                
            # scen_name = f"ttf_{round(closest_prices['ttf'],1)}_api2_{round(closest_prices['api2'],1)}_eua_{round(closest_prices['eua'],1)}"
            scen_name = f"mcr_{which_std}"
    
            scen_dict[scen_name] = temp
    
        return scen_dict

    

    def get_scenarios(self, scen_type:dict = {'defined':
        [a/100 for a in list(np.linspace(-30,30,99,
                                    retstep=False))]}):
        if list(scen_type)[0] in ['defined']:
            return self.get_defined_scenarios(scen_list=scen_type['defined'])
        elif list(scen_type)[0] in ['mcr']:
            return self.get_mcr_scenarios(scen_list=scen_type['mcr'])