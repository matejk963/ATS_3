# -*- coding: utf-8 -*-
"""
Created on Wed Jan 17 14:41:55 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
# from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import RldMonitor as RM
from sklearn.linear_model import LinearRegression

import statsmodels.api as sm



sD = datetime(2013,1,1)
eD = datetime(2024,1,17)
mon_inst = RM()
mon_inst.set_date_range(sD, eD)

# raw_data = mon_inst.get_raw_data(monthly=True)

comb_rld = pd.DataFrame()
# test = mon_inst.process_data(raw_data)
for market in ['de', 'fr']:
    rld_curve = mon_inst.get_rld_curve(market=market)
    last_rld = rld_curve.iloc[-1].copy()
    last_rld.index = last_rld.name + pd.to_timedelta(last_rld.index,unit='h')
    last_rld.name = market
    if comb_rld.empty:
        comb_rld = last_rld.resample('M').mean()
    else:
        comb_rld = pd.concat([comb_rld, last_rld.resample('M').mean()],axis=1, join='inner')
        
comb_rld['de_fr'] = comb_rld['de'] - comb_rld['fr']


raw_da = mon_inst.get_raw_data()
data_da = mon_inst.get_da_data(mon_inst.process_data(raw_da))

data_da.set_index('value_date', inplace=True)
data_da.columns = ['rld']

# Compute moving average
base_da = data_da.resample('D').mean()
base_da['rld_ma_short'] = base_da['rld'].rolling(14).mean()
base_da['rld_ma_long'] = base_da['rld'].rolling(14*3).mean()
base_da['rld_ma'] = base_da['rld_ma_short']/base_da['rld_ma_long']
base_da['rld_ma_rank'] = pd.qcut(base_da['rld_ma'], 5, labels=False)
base_da['rld_fut_ma'] = base_da['rld_ma'].shift(-14)/base_da['rld_ma'] - 1

for rank in range(5):
    aux = base_da.loc[base_da['rld_ma_rank']==rank].copy()
    sns.histplot(aux['rld_fut_ma'],kde=True,legend=True, label=str(rank))
    plt.legend()
    plt.show()
    
from statsmodels.tsa.statespace.sarimax import SARIMAX
rld_series = base_da['rld'].copy()
p, d, q = 1, 1, 1  # Non-seasonal orders
P, D, Q, s = 1, 1, 1, 12  # Seasonal orders (example for monthly data)

# Define your SARIMAX model
# Note: Replace p, d, q with your ARIMA orders and P, D, Q, s with your seasonal orders
model = SARIMAX(rld_series, order=(p, d, q), seasonal_order=(P, D, Q, s))

# Fit the model
results = model.fit()

# Forecast future values - let's forecast the next 24 time points as an example
n_forecast = 90  # Change this based on your needs
forecast_result = results.get_forecast(steps=n_forecast)
forecast_mean = forecast_result.predicted_mean
forecast_conf_int = forecast_result.conf_int()

# Plot the historical data
plt.figure(figsize=(10, 6))
plt.plot(rld_series, label='Historical RLD Data')

# Plot the forecast along with the confidence interval
plt.plot(forecast_mean, label='Forecast')
plt.fill_between(forecast_conf_int.index,
                 forecast_conf_int.iloc[:, 0],
                 forecast_conf_int.iloc[:, 1], color='gray', alpha=0.3)

# Customize the plot
plt.title('RLD Forecast with Uncertainty Bands')
plt.xlabel('Date')
plt.ylabel('RLD')
plt.legend()
plt.show()


from statsmodels.tsa.statespace.structural import UnobservedComponents

ts = data_da['rld'].iloc[-8760*3:]

model = UnobservedComponents(ts, level='local linear trend', seasonal=12)
results = model.fit()
results.plot_diagnostics(figsize=(15, 12))
plt.show()
# Forecasting
forecast_steps = 24*7
forecast = results.get_forecast(steps=forecast_steps)
forecast_mean = forecast.predicted_mean
forecast_ci = forecast.conf_int()

# Plotting
plt.figure(figsize=(10, 6))
ts.plot(label='Observed')
forecast_mean.plot(label='Forecast', alpha=.7)
plt.fill_between(forecast_ci.index, forecast_ci.iloc[:, 0], forecast_ci.iloc[:, 1], color='k', alpha=.2)
plt.xlabel('Date')
plt.ylabel('Values')
plt.title('Forecast with Unobserved Components Model')
plt.legend()
plt.show()






# #DA data
# # Get seasonal averages
# da_test = mon_inst.get_da_data(test)
# da_test.set_index('value_date', inplace=True)
# mean = da_test.copy()
# mean_h = mean.groupby(mean.index.hour).mean()
# mean_h = mean_h/mean_h.mean()
# mean_h.index.name = 'hour'
# mean_h.columns = ['hour_ratio']
# mean_d = mean.groupby(mean.index.weekday).mean()
# mean_d = mean_d/mean_d.mean()
# mean_d.index.name = 'weekday'
# mean_d.columns = ['weekday_ratio']
# mean_m = mean.groupby(mean.index.month).median()
# mean_m = mean_m/mean_m.mean()
# mean_m.index.name = 'month'
# mean_m.columns = ['month_ratio']



# # Load normals data from xlsx
# normal = pd.read_excel(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\DE_normals.xlsx',
#                         sheet_name='Data')
# normal['m_start'] = pd.to_datetime(normal['m_start'].dt.date)
# normal['norm'] = normal['cons_norm'] - normal['wind_norm'] - normal['solar_norm']
# normal = normal[['m_start', 'norm']].copy()
# normal.set_index('m_start', inplace=True)
# normal = normal.resample('D').asfreq()
# normal['norm'] = normal['norm'].interpolate(method='linear')
# normal = normal.resample('W-MON').mean()
# normal = normal.resample('D').ffill()
# normal.reset_index(inplace=True)
# normal['weekday'] = normal['m_start'].dt.weekday
# normal = normal.merge(mean_d, on='weekday', how='left')
# normal['norm_d'] = normal['norm']*normal['weekday_ratio']
# normal.set_index('m_start', inplace=True)
# normal = normal.resample('H').ffill()
# normal.reset_index(inplace=True)
# normal['hour'] = normal['m_start'].dt.hour
# normal = normal.merge(mean_h, on='hour', how='left')
# normal['norm_h'] = normal['norm_d'] * normal['hour_ratio']
# normal.set_index('m_start', inplace=True)




# #Get renewables capacity
# res_capa = pd.read_excel(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\DE_res_capa.xlsx',
#                           sheet_name='Data')

# #Model trend with res capacity
# da_test.reset_index(inplace=True)
# da_test['m_start'] = da_test['value_date'].dt.to_period('M').dt.to_timestamp(how='start')
# da_test = da_test.merge(res_capa, on='m_start', how='left')
# da_test.set_index('value_date', inplace=True)
# # Regress data for major yearly trend
# X = sm.add_constant(da_test[['cap_solar', 'cap_wind']])
# y = da_test[0]

# model = sm.OLS(y, X).fit()

# da_test['predicted'] = model.predict(X)



# normal = pd.DataFrame(index=pd.date_range(start=da_test.index[0],
#                                           end=res_capa['m_start'].iloc[-1], freq='h'))
# normal.index.name = 'value_date'
# normal.reset_index(inplace=True)
# normal['m_start'] = normal['value_date'].dt.to_period('M').dt.to_timestamp(how='start')
# normal = normal.merge(res_capa, on='m_start', how='left')
# n_X = sm.add_constant(normal[['cap_solar', 'cap_wind']])
# normal['norm'] = model.predict(n_X)
# normal = normal[['value_date', 'norm']].copy()

# normal_y = normal.set_index('value_date').resample('YS').mean()
# normal_y.index.name = 'y_start'
# normal_y.reset_index(inplace=True)
# normal = normal.drop(['norm'],axis=1)
# normal['y_start'] = normal['value_date'].dt.to_period('Y').dt.to_timestamp(how='start')
# normal = normal.merge(normal_y, on='y_start', how='left')

# normal['month'] = normal['value_date'].dt.month
# normal = normal.merge(mean_m.reset_index(), on='month', how='left')

# normal['norm_m'] = normal['norm'] * normal['month_ratio']



# mon_inst.set_da_lookback(14)

# stats_h = mon_inst.assemble_stat(test, stat_type='hist')
# stats_f = mon_inst.assemble_stat(test, stat_type='fcst')
# stats = stats_h.shift(-14).merge(stats_f, left_index=True, right_index=True, suffixes=('_h', '_f'),
#                       how='right')






# # gas = rd.get_history(['TFMBMH4'], count=60, fields=['VWAP', 'OPINT_1']).astype(float)
# # eua = rd.get_history(['CFI2Z3^2'], count=500, fields=['VWAP', 'OPINT_1']).astype(float)

# def plot_dual_axis(df, col1, col2):
#     """
#     Plots two columns of a DataFrame on a dual y-axis graph.

#     :param df: Pandas DataFrame containing the data.
#     :param col1: Name of the first column to plot.
#     :param col2: Name of the second column to plot.
#     """

#     # Create a figure and a single subplot
#     fig, ax1 = plt.subplots()

#     # Plot the first column
#     color = 'tab:red'
#     ax1.set_xlabel('Index')
#     ax1.set_ylabel(col1, color=color)
#     ax1.plot(df[col1], color=color)
#     ax1.tick_params(axis='y', labelcolor=color)

#     # Instantiate a second axes that shares the same x-axis
#     ax2 = ax1.twinx()  
#     color = 'tab:blue'
#     ax2.set_ylabel(col2, color=color)  # we already handled the x-label with ax1
#     ax2.plot(df[col2], color=color)
#     ax2.tick_params(axis='y', labelcolor=color)

#     # Show the plot
#     plt.show()