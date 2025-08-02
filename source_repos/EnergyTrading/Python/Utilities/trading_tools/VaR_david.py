from Utilities.trading_tools.VaR_calculator import VaR_calculator

import pandas as pd
import numpy as np
import datetime as dt

# Initialize var calculator
inst = VaR_calculator()

# Positions
positions = [[['DE_B_M_5_25', 'DE_P_M_5_25'], [1,-1], [-1]],
            [['DE_B_M_4_25', 'FR_B_M_4_25'], [1,-1], [-1]],
            [['DE_B_Q_2_25', 'FR_B_Q_2_25'], [1,-1], [1]],
            [['DE_B_M_5_25', 'FR_B_M_5_25'], [1,-1], [1]],
            [['DE_B_M_6_25', 'FR_B_M_6_25'], [1,-1], [-1]],
            [['IT_B_Y_1_25', 'HU_B_Y_1_25'], [1,-1], [1]],
            [['IT_B_M_5_25', 'IT_B_M_6_25'], [1,-1], [3]],
            [['DE_B_M_7_25', 'DE_P_M_8_25'], [1,-1], [1]]]

# Calculate VaR for positions
var_results = inst.calculate_var(positions=positions,
                            # portfolio_size=4,
                            percentile=0.9)

