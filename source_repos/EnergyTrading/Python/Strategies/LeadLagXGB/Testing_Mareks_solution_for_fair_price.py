#!/usr/bin/env python
# coding: utf-8

# In[1]:


import mofr


# In[2]:


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
#from Database.TPData import TPData, TPDataDa, TPDataAssembly

from Strategies.LeadLagRegression_strategy.backtest_class import BacktestLL
from Strategies.LeadLagRegression_strategy.strategy_class import StrategyLL, VolumeClass
from support_functions import calculate_MACD, calculate_regression_model_price, calc_vol_intensity_index, calculate_regression_model_price_new
tol=(1e-1)/2

import seaborn as sns

from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource, Legend
from bokeh.io import output_notebook
from scipy.stats import gaussian_kde


# In[3]:


import seaborn as sns
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
from xgboost import XGBClassifier, plot_tree
import xgboost as xgb
import shap
from sklearn.model_selection import train_test_split
from sklearn import tree
from sklearn.tree import export_text
from sklearn.metrics import accuracy_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier



# In[6]:


data_lead =pd.concat([pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_jan_feb.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_mar_apr.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_may_june.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_july.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_aug.csv',
                    parse_dates=['datetime']).reset_index()])

data_lag=pd.concat([pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_jan_feb.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_mar_apr.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_may_june.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_july.csv',
                    parse_dates=['datetime']).reset_index(), pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_aug.csv',
                    parse_dates=['datetime']).reset_index()])


# In[7]:


data_lead['datetime']=pd.to_datetime(data_lead['datetime'], format='mixed')
data_lag['datetime']=pd.to_datetime(data_lag['datetime'], format='mixed')


# In[8]:


data_lag['time_diff']=data_lag['datetime'].diff().dt.total_seconds().fillna(0)
data_lead['time_diff']=data_lead['datetime'].diff().dt.total_seconds().fillna(0)


# In[9]:


data_lead=data_lead[data_lead['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]
data_lag=data_lag[data_lag['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]


# In[10]:


data_lag['date']=data_lag['datetime'].apply(lambda x: x.date())


# In[11]:


from Strategies.LeadLagEns.lead_lag_ensamble import LMOnline, LMOffline, DataClass
 
n_t = 15
d_t = 1

# Data properties
mkt = 'dem2'
mkt_l = ['dem1']
tau = 10
tau_ema = 10
n_ema = 16
 
diff_bool = True
vol_bool = False
scale_bool = True
isEma = False
 
tick_val = 200

km_bool = True
 
intercept = False
lambda1=.2
lambda2=.0
alpha=17.8
beta=2.9
 
adaptive_l1 = False
norm_g = True
 
model_class = LMOnline(1, intercept, lambda1, lambda2, alpha, beta,
                        adaptive_l1, norm_g)
model_class = LMOffline(intercept)
# Data preparation
data_class = DataClass(mkt, tau, tau_ema, diff_bool, vol_bool, scale_bool,
                       isEma, n_ema)

dict_lead={'dem1': data_lead}


# In[12]:


data_lag['timestamp']=data_lag['datetime']
data_lead['timestamp']=data_lead['datetime']

data_lag=calculate_MACD(data_lag, 6,14)
data_lag=calculate_MACD(data_lag, 12,26)
data_lag=calculate_MACD(data_lag, 18,38)

calculate_regression_model_price_new(dict_lead, data_lag, model_class, data_class,n_t, d_t, km_bool, vol_bool=False)


# In[ ]:




