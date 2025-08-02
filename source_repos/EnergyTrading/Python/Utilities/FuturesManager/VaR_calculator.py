# -*- coding: utf-8 -*-
"""
Created on Sat Dec 28 10:53:35 2024

@author: krajcovic
"""

import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import copy
import datetime as dt

from datetime import datetime, timedelta
import calendar

from Utilities.date_functions import start_date



from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager

from itertools import combinations
from scipy.stats import norm


class VaR_calculator:
    
    def __init__(self, params_dict, pivot_date=None):
        self._params_dict = params_dict
        self._original_params_dict = params_dict
        self._pivot_date = pivot_date
        
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def original_params_dict(self):
        return self._original_params_dict
    
    @property
    def pivot_date(self):
        return self._pivot_date
    
    @staticmethod
    def calculate_contract_hours(contract):
        """
        Parses the contract string and calculates the number of hours in the specified period.
        """
        try:
            parts = contract.split("_")
            if len(parts) != 5:
                raise ValueError(f"Invalid contract format: {contract}")
            
            country, delivery, product, period, year = parts
            year = int(year) + 2000  # Convert '25' -> 2025
            period = int(period)  # Convert to integer

            # Determine number of hours based on product type
            if product == "W":  # Week
                days = 7
            elif product == "M":  # Month
                days = calendar.monthrange(year, period)[1]  # Get number of days in the month
            elif product == "Q":  # Quarter
                start_month = (period - 1) * 3 + 1
                days = sum(calendar.monthrange(year, start_month + i)[1] for i in range(3))  # Sum days in 3 months
            elif product == "Y":  # Year
                days = 366 if calendar.isleap(year) else 365  # Check leap year
            else:
                raise ValueError(f"Unknown product type: {product}")

            # Calculate hours based on delivery type
            if delivery == "B":  # Base (all hours)
                hours = days * 24
            elif delivery == "P":  # Peak (08:00-20:00 on business days)
                business_days = sum(1 for day in range(1, days + 1) 
                                    if datetime(year, period, day).weekday() < 5)  # Count weekdays
                hours = business_days * 13  # Peak hours (08:00 - 20:00)
            else:
                raise ValueError(f"Unknown delivery type: {delivery}")

            return hours

        except Exception as e:
            return f"Error: {e}"

    
    
    def get_futures_data(self, spreads_list, spreads_weights):

        ta_inst = TechAnalysis_manager(markets=list({string.split('_')[0].upper()
                                           for sublist in spreads_list for string in sublist}))
        
        
        spreads = []
        hours_dict = {}
        for spread_legs, leg_weights in zip(spreads_list, spreads_weights ):
            spread_df = ta_inst.get_spread(spread_legs=spread_legs,
                                        leg_weights=leg_weights)
            spread_name = "x".join(spread_legs)
            spread_hours = max([self.calculate_contract_hours(contract)
                                for contract in spread_legs])
            hours_dict[spread_name] = spread_hours
            spread_df.columns = [spread_name]
            spreads.append(spread_df)

        spreads = pd.concat(spreads,axis=1).dropna()
        spreads = spreads.diff().iloc[-50:].copy()
        
        return spreads, hours_dict
    
    def calculate_var(self, positions, portfolio_size=None, percentile=0.90):
        """
        Calculate individual and portfolio VaR.
    
        Args:
            spreads_list (list): List of spreads data to process.
            portfolio_size (int): The size of portfolio combinations to consider.
            position_weights (list): Numerical weights for each asset, where positive = long, negative = short.
                                     If None, all positions are assumed equal weights (1 for long).
            percentile (float): The confidence level for VaR (e.g., 0.90 for 90% VaR).
    
        Returns:
            dict: A dictionary with DataFrames for individual and portfolio VaRs.
        """
        # Get spreads_list, weights and portfolio_lenght
        spreads_list = [a[0] for a in positions]
        spreads_weights = [a[1] for a in positions]
        position_weights = [a[2][0] for a in positions]
        if not portfolio_size:
            portfolio_size = len(spreads_list)
        # Fetch the futures data and spreads_hours
        spreads, spread_hours = self.get_futures_data(spreads_list, spreads_weights)
        
        # Calculate the Z-score for the given percentile
        z_score = norm.ppf(1 - percentile)  # Negative because VaR looks at potential losses
    
        # Ensure the position_weights matches the number of assets
        if position_weights is None:
            position_weights = [1] * spreads.shape[1]  # Default to equal weights (all long)
        elif len(position_weights) != spreads.shape[1]:
            raise ValueError("Length of position_weights must match the number of columns in spreads.")
    
        # Initialize dictionaries to store results
        var_results = {
            "individual_var": pd.DataFrame(),
            "portfolio_var": pd.DataFrame(),
        }
    
        # 1. Calculate individual VaR
        individual_results = []
        for i, col in enumerate(spreads.columns):
            std_dev = spreads[col].std()
            hours = spread_hours[col]  # Get hours for this spread
            var = z_score * std_dev * position_weights[i] * hours  # Adjust for weight and hours
            individual_results.append({
                'Asset': col,
                'Weight': position_weights[i],
                'Hours': hours,
                'Daily VaR': abs(var),
                'Weekly VaR': abs(var) * np.sqrt(5),
                'Monthly VaR': abs(var) * np.sqrt(21),
                'Quarterly VaR': abs(var) * np.sqrt(63),
                'Yearly VaR': abs(var) * np.sqrt(252)
            })
        var_results["individual_var"] = pd.DataFrame(individual_results)
    
        # 2. Calculate portfolio VaR for combinations of size `portfolio_size`
        portfolio_results = []
        for combo in combinations(spreads.columns, portfolio_size):  # Only combinations of specified size
            # Get indices for the combination
            indices = [spreads.columns.get_loc(c) for c in combo]
            
            # Select the subset of spreads for the current combination
            subset = spreads[list(combo)]
            
            # Use weights adjusted for positions and hours
            try:
                weights = [position_weights[j] * spread_hours[combo[i]]
                           for i,j in enumerate(indices)]
            except:
                print('154')
            # weights = np.array(weights) / np.abs(np.array(weights)).sum()  # Normalize weights
    
            # Portfolio variance calculation
            cov_matrix = subset.cov()
            portfolio_variance = np.dot(weights, np.dot(cov_matrix, weights))
            portfolio_std = np.sqrt(portfolio_variance)  # Portfolio standard deviation
    
            # Portfolio VaR
            portfolio_var = z_score * portfolio_std
            
            # Store the combination and portfolio VaR in the results
            portfolio_results.append({
                'Combination': combo,
                'Weights': weights,
                'Daily VaR': abs(portfolio_var),
                'Weekly VaR': abs(portfolio_var) * np.sqrt(5),
                'Monthly VaR': abs(portfolio_var) * np.sqrt(21),
                'Quarterly VaR': abs(portfolio_var) * np.sqrt(63),
                'Yearly VaR': abs(portfolio_var) * np.sqrt(252)
            })
        var_results["portfolio_var"] = pd.DataFrame(portfolio_results)
        
        return var_results



    
    
        
        
    
    
    
if __name__ == '__main__':
    base_products = ['M_1', 'M_2', 'M_3', 'M_4', 'Q_1', 'Q_2', 'Q_3', 'Q_4']
    # base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3', 'Y_1']
    market_list = ['de', 'fr', 'be', 'nl', 'at', 'hu', 'cz', 'sk', 'hu', 'ro']
    market_list = ['de', 'fr', 'hu']
    delivery_dict = ['base', 'peak']
    
    # Generate the combinations
    products = []
    markets = []
    delivery = []
    
    for product in base_products:
        for market in market_list:
            for delivery_option in delivery_dict:
                products.append(product)
                markets.append(market)
                delivery.append(delivery_option)
    
    params_dict = {}
    
    params_dict['product_list'] = products
    
    params_dict['market_list'] = markets
    
    params_dict['delivery_list'] = delivery 
    
    params_dict['year_list'] = [None] * len(params_dict['market_list'])
    params_dict['ns'] = 2
    params_dict['cont'] = False
    
    
    params_dict['sD'] = dt.datetime(2020,1,1)
    params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
    params_dict['eD'] = dt.datetime(2025,1,8)
    params_dict['ns'] = 2
    params_dict['cont'] = False
    
    pivot_date = dt.datetime(2025,3,14)
    
    inst = VaR_calculator(params_dict, pivot_date)
    
    spread_positions = [['DE_B_M_2_25', 'DE_B_M_3_25'],
                        ['DE_B_Q_1_25', 'DE_B_Q_4_25'],
                        ['DE_B_Q_4_25', 'DE_B_Q_7_25'],
                        ['DE_B_M_2_25', 'DE_B_Q_1_25'],
                        ['DE_B_M_2_25', 'FR_B_M_2_25'],
                        ['DE_B_M_2_25', 'HU_B_M_2_25']]
    
    spreads_list = [list(pair) for pair in zip(*spread_positions)]
    positions = [3,1,-1,-1,3,-3]


    positions = [[['DE_B_M_4_25', 'DE_P_M_4_25'], [1,-1], [-3]],
                 [['DE_B_M_4_25', 'FR_B_M_4_25'], [1,-1], [-3]],
                 [['DE_B_Q_2_25', 'FR_B_Q_2_25'], [1,-1], [1]],
                 [['DE_B_M_5_25', 'FR_B_M_5_25'], [1,-1], [1]],
                 [['IT_B_Y_1_25', 'HU_B_Y_1_25'], [1,-1], [1]]]

    
    var_results = inst.calculate_var(positions=positions,
                              portfolio_size=4,
                              percentile=0.9)
    