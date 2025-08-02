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


sD = datetime(2015,12,29)
eD = datetime(2024,2,1)

sm_inst = SM()
sm_inst.set_date_range(sD, eD)
sm_inst.set_grids(['de'])

power_spot = sm_inst.get_power_spot()

power_spot['hour'] = power_spot.index.hour
power_spot['weekday'] = power_spot.index.weekday
power_spot['peak'] = np.where(((power_spot['hour']>7)&
                               (power_spot['hour']<20)&
                               (power_spot['weekday']<5)),1,0)

peak = power_spot.loc[power_spot['peak']==1].copy()
peak = peak[['de']].resample('ME').mean()
base = power_spot[['de']].resample('ME').mean()

jan_b = base[base.index.month==1].copy()
jan_p = peak[peak.index.month==1].copy()

month = 2

print(base[base.index.month==month]-
      peak[peak.index.month==month])

apr_b = base[base.index.month==4].copy()
apr_p = peak[peak.index.month==4].copy()

may_b = base[base.index.month==5].copy()
may_p = peak[peak.index.month==5].copy()

jun_b = base[base.index.month==6].copy()
jun_p = peak[peak.index.month==6].copy()

q2_b = base[base.index.quarter==2].copy()
q2_p = peak[peak.index.quarter==2].copy()

q3_b = base[base.index.quarter==3].copy()
q3_p = peak[peak.index.quarter==3].copy()




# power_spot = power_spot.resample('D').mean()
# # gas_spot = sm_inst.get_gas_spot()
# # eua = sm_inst.get_eua_df()
# # coal_spot = sm_inst.get_coal_spot()

# # fuel_spot = pd.concat([gas_spot, coal_spot, eua],axis=1, join='outer')
# # fuel_spot = fuel_spot.loc[((fuel_spot.index>=datetime(2023,1,1))&
# #                            (fuel_spot.index<datetime(2024,2,1)))].copy()

# fuel_spot.to_csv(r'C:\Users\krajcovic\Documents\Trading\Data\FundDatabase\AvCap\Junk\fuel_costs.csv',
#               sep=';', decimal=',')

# css = pd.concat([power_spot, gas_spot, eua], axis=1, join='inner')
# css_m = css.resample('M').mean()
# css_m['css_m'] = css_m['de'] / (css_m['ttf_da']+css_m['eua']*0.2)

# css_m['month'] = css_m.index.month
# css_m['year'] = css_m.index.year

# css_m_y = css_m.groupby(['month']).mean()

# css_q = css.resample('Q').mean()
# css_q['css_q'] = css_q['de'] / (css_q['ttf_da']+css_q['eua']*0.2)

# css_q['month'] = css_q.index.month
# css_q['year'] = css_q.index.year

# css_q_y = css_q.groupby(['month']).mean()


