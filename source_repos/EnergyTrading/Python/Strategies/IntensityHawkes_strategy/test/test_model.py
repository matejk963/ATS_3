# -*- coding: utf-8 -*-
"""
Created on Fri Feb 23 13:20:09 2024

@author: krajcovic
"""

import warnings
warnings.filterwarnings("ignore")


from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Strategies.IntensityHawkes_strategy.calibration import HIStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.IntensityHawkes_strategy.model_class import HawkesIntensity
from Strategies.IntensityHawkes_strategy.backtest_class import BacktestIB
from Strategies.IntensityHawkes_strategy.strategy_class import StrategyHI, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
from scipy.integrate import odeint
from scipy.optimize import minimize
tol=0.019

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_ba_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_trades_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')



hi_obj = HawkesIntensity(trades, ba, ['dem1'])

# hi_obj.prepare_data()
# hi_obj.create_data_dict()
# hi_obj.estimate_params()

hi_obj.compute_intensities()

# hi_obj.create_train_test_dict()
# params_dict = hi_obj.params_dict
# data_dict = hi_obj.data_dict

# def objective_function(params, empirical_moments):
#     def calculate_theoretical_moments(alpha, beta,
#                                       lambda_infinity, t_max,
#                                       initial_conditions):
#         def system_of_odes(y, t):
#             E_Nt, E_lambda_t = y
#             dE_Nt_dt = E_lambda_t
#             dE_lambda_t_dt = beta * (lambda_infinity - E_lambda_t) + alpha * E_lambda_t
#             return [dE_Nt_dt, dE_lambda_t_dt]

#         t = np.linspace(0, t_max, 100)
#         sol = odeint(system_of_odes, initial_conditions, t)
#         E_Nt = sol[:, 0]
#         E_lambda_t = sol[:, 1]

#         theoretical_mean = E_Nt[-1]
#         theoretical_variance = E_lambda_t[-1]

#         return theoretical_mean, theoretical_variance
#     alpha, beta, lambda_infinity = params
#     theoretical_moments = calculate_theoretical_moments(alpha, beta, lambda_infinity, t_max=10, initial_conditions=[0, 0])
#     squared_error = sum((empirical_moment - theoretical_moment) ** 2 for empirical_moment, theoretical_moment in zip(empirical_moments, theoretical_moments))
#     return squared_error
# best_results = []
# estimated_params = []
# methods = []
# parameter_bounds = [(0, None), (0, None), (0, None)]
# for date, date_dict in data_dict.items():
#     for prod, prod_df in date_dict.items():
#         empirical_moments = prod_df['bid_empirical_moments_dem1']


#     # Define ranges for your initial guesses:
#     # These ranges are just examples; adjust them based on your understanding of the problem
#     mu_range = np.linspace(0.01, 0.05, 5)  # Baseline intensity
#     alpha_range = np.linspace(0.05, 0.2, 4)  # Excitation coefficient
#     beta_range = np.linspace(0.005, 0.02, 4)  # Decay rate
    
#     # Placeholder for the best initial guess and result
#     best_initial_guess = None
#     best_result = None
    
#     # Loop through the ranges of initial guesses
#     for mu in mu_range:
#         for alpha in alpha_range:
#             for beta in beta_range:
#                 for method in [ 'TNC','L-BFGS-B', 'SLSQP']:
#                     initial_guess = [alpha, beta, mu]
                    
#                     # Define the optimization process
#                     result = minimize(
#                         objective_function,  # Assuming this is your static method
#                         initial_guess,
#                         args=(empirical_moments,),
#                         method=method,
#                         bounds=parameter_bounds,# You can change this method based on your requirements
#                         options={'disp': False}  # Set to True if you want to see the convergence messages
#                     )
                    
#                     # Check if the optimization was successful
#                     if result.success:
#                         best_initial_guess = initial_guess
#                         best_results.append(best_initial_guess)
#                         estimated_params.append(result.x)
#                         methods.append(method)
#                         best_result = result
#                         print(date)
#                         print(f"Converged with initial guess: {best_initial_guess}")
#                         print(f"Result: {best_result.x}")
#                         break  # Exit the loop if a successful optimization is found
        
#             if best_result is not None:
#                 break  # Break the outer loop if a solution has been found
        
#     # If no solution found
#     if best_result is None:
#         print("No convergence with the tried initial guesses.")

#     else:
        
#         # If you found a solution, you can process it further here
#         print(f"Best initial guess leading to convergence: {best_initial_guess}")
#         print(f"Optimization details: {best_result}")


# best_guess_df = pd.DataFrame(best_results, columns=['alpha_g', 'beta_g', 'mu_g'])
# est_params_df = pd.DataFrame(estimated_params, columns=['alpha_e', 'beta_e', 'mu_e'])
# methods_df = pd.DataFrame(methods, columns=['method'])
# params = pd.concat([best_guess_df, est_params_df, methods_df],axis=1)

# summary_std = params.loc[params['method']!='TNC'].groupby(['method','alpha_g', 'beta_g', 'mu_g']).std()
# summary_count = params.groupby(['method','alpha_g', 'beta_g', 'mu_g']).count()



