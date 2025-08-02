# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 16:56:32 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

import seaborn as sns

from Spot.Monitor_class import SettleMonitor as SM


sD = datetime(2015,1,1)
eD = datetime(2024,1,23)

sm_inst = SM()
sm_inst.set_date_range(sD, eD)
sm_inst.set_grids(['de'])

power_spot = sm_inst.get_power_spot()
power_spot = power_spot.resample('D').mean()
gas_spot = sm_inst.get_gas_spot()
eua = sm_inst.get_eua_df()


css = pd.concat([power_spot, gas_spot, eua], axis=1, join='inner')
css_m = css.resample('M').mean()
css_m['css_m'] = css_m['de'] / (css_m['ttf_da']+css_m[0]*0.2)

css_m['month'] = css_m.index.month
css_m['year'] = css_m.index.year

css_m_y = css_m.groupby(['month']).mean()

css_q = css.resample('Q').mean()
css_q['css_q'] = css_q['de'] / (css_q['ttf_da']+css_q[0]*0.2)

css_q['month'] = css_q.index.month
css_q['year'] = css_q.index.year


