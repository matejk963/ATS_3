# -*- coding: utf-8 -*-
"""
Created on Wed Sep 13 08:21:54 2023

@author: krajcovic
"""


from Database.TPData import TPData as tpd
from RiskPremium import RP_Tools as rpt
import Loaders.RLD_fetch as rf
from RiskPremium.RP_Tools import MFR, Plot2v2a, calculate_return,\
    TP_trades_data, ttf_settle_data, vwap_from_tp_trades, gas_for_week,\
        ttf_intraweek_settle
from Database import DB_reader as dbr
from Loaders import RLD_fetch as rldf
from scipy.optimize import minimize_scalar
from Strategies import RegTools as rt

import refinitiv.data as rd


from Loaders.EikonSpot_class import EikonSpot as ES
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from datetime import time
import seaborn as sns
import refinitiv.data as rd
import pytz

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.model_selection import train_test_split
from tensorflow.keras.layers import PReLU

from Database.TPData import TPData

from sklearn.linear_model import LinearRegression


import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass

start_date = dt.datetime(2019,1,1)
end_date = dt.datetime(2023,9,1)

# data_p = rt.data_prep(start_date, end_date)


database = dbr.Database()
spot = database.getSpotPriceData(['de'], _from=start_date.strftime('%Y-%m-%d'),
                                 _to=end_date.strftime('%Y-%m-%d'))

spot_w = spot.resample('W').mean().iloc[1:]
spot_w.index = spot_w.index - dt.timedelta(days=6)

rld_data = rldf.RLDDatabaseData()


rld_da = rld_data.getResDayAhead(start_date, end_date, hourly=True)
rld_wa = rld_data.getResWeekAhead(start_date, end_date)

df = pd.concat([spot, rld_da],axis=1,join='inner')
df.columns = ['de', 'rld']
df = df.dropna()


trades = pd.read_csv(r's:\Algo\Database\Backups\wa_trades_20190604_20230901.csv',
                     index_col=0, parse_dates=True, dtype=float)

vwap = [(trades.loc[trades['idx']==a,'price']*trades.loc[trades['idx']==a,'volume']).sum()\
        /trades.loc[trades['idx']==a,'volume'].sum() for a in trades['idx'].drop_duplicates()]
vwap_index = trades['idx'].drop_duplicates().index.date
wa_vwap = pd.DataFrame(vwap, index=vwap_index,columns=['wa_vwap'])
wa_vwap.index = pd.to_datetime(wa_vwap.index)

pred_df = rt.lin_reg_wa(14, df, rld_wa['values'].explode())

control_df = rt.lin_reg_wa_opt(14,df)

# pred_df.columns = ['de_pred', 'date']
pred_df.index = pred_df['date']
pred_df = pred_df.drop(['date'],axis=1)

mean_vwap = wa_vwap.resample('d').mean()

agg_df = pd.concat([pred_df, rld_wa['mean'],
                    mean_vwap['wa_vwap'], control_df[['de', 'rld']]],axis=1,join='inner').dropna()

agg_df['pnl_settle'] = np.where(agg_df['de_pred']>agg_df['wa_vwap'],
                                agg_df['de']-agg_df['wa_vwap'],
                                agg_df['wa_vwap']-agg_df['de'])
agg_df['pred_error'] = agg_df['de_pred']/agg_df['de']-1
agg_df['rld_error'] = agg_df['mean']-agg_df['rld']

for year in agg_df.index.year.drop_duplicates():
    plt.figure()
    plt.plot(agg_df['pnl_settle'].loc[agg_df.index.year==year].cumsum())
    plt.title(year)
    plt.show()
    
agg_df['pos'] = np.where(agg_df['de_pred']<agg_df['wa_vwap'],-1,1)

agg_df['pnl_long'] = np.where(agg_df['pos']>0,agg_df['pnl_settle'],0)
agg_df['pnl_short'] = np.where(agg_df['pos']<0,agg_df['pnl_settle'],0)

print(agg_df.groupby(['pos']).mean().T)

agg_df['pnl_long'].cumsum().plot()
agg_df['pnl_short'].cumsum().plot()

for weekday in range(5):
    temp = agg_df.loc[agg_df.index.weekday==weekday].copy()
    plt.plot(temp['pnl_settle'].cumsum())
    plt.title(weekday)
    plt.show()
    
    
ttf = rt.data_prep(start_date,end_date,
                 mkt_list=['ttf'], tenor_list=['m'], tn_list=[1],
                 prod='base', venue_list=['eex'])

ttf_da = ttf.loc[ttf.index.time<time(12,0,0)].resample('D').mean().dropna()
ttf_wa = ttf.resample('D').mean().dropna()

df2 = df.copy()
df2['hour'] = df2.index.hour
df2.index = df.index.date
df2 = df2.merge(ttf_da, left_index=True,
                right_index=True, how='inner')
df2.index = df2.index + pd.to_timedelta(df2['hour'], unit='h')
df2 = df2.drop(['hour'],axis=1)

df_wa = pd.concat([rld_wa, ttf_wa], axis=1, join='inner')


lookback = 28
pred_list = []
date_list = []
for date in df_wa.index-dt.timedelta(days=lookback):
    sD = date-dt.timedelta(days=lookback)
    if sD < df_wa.index[0]:
        continue
    else:
        try:
        
            train = df2.loc[((df2.index>=sD)&
                             (df2.index<=date))].copy()
            test_list = df_wa.loc[date]['values']
            add_list = [df_wa.loc[date]['ttfm1'] for a in test_list]
            test = np.array([test_list,add_list]).T
            model = LinearRegression()
            model.fit(train[['rld', 'ttfm1']],train['de'])
            pred = model.predict(test)
            pred_list.append(pred.mean())
            date_list.append(date)
        except:
            continue
pred_df2 = pd.DataFrame({'date': date_list,
                         'de_pred': pred_list})        
pred_df2.index = pred_df2['date']

agg_df = pd.concat([pred_df2, rld_wa['mean'],
                    mean_vwap['wa_vwap'], control_df[['de', 'rld']]],axis=1,join='inner').dropna()

agg_df['pnl_settle'] = np.where(agg_df['de_pred']>agg_df['wa_vwap'],
                                agg_df['de']-agg_df['wa_vwap'],
                                agg_df['wa_vwap']-agg_df['de'])
agg_df['pred_error'] = agg_df['de_pred']/agg_df['de']-1
agg_df['rld_error'] = agg_df['mean']-agg_df['rld']

for year in agg_df.index.year.drop_duplicates():
    plt.figure()
    plt.plot(agg_df['pnl_settle'].loc[agg_df.index.year==year].cumsum())
    plt.title(year)
    plt.show()
    
agg_df['pos'] = np.where(agg_df['de_pred']<agg_df['wa_vwap'],-1,1)

agg_df['pnl_long'] = np.where(agg_df['pos']>0,agg_df['pnl_settle'],0)
agg_df['pnl_short'] = np.where(agg_df['pos']<0,agg_df['pnl_settle'],0)

print(agg_df.groupby(['pos']).mean().T)

agg_df['pnl_long'].cumsum().plot()
agg_df['pnl_short'].cumsum().plot()

df_nn_train = df2.iloc[-3000:-500].copy()
df_nn_train['rld2'] = (df_nn_train['rld']**2)/1000
df_nn_train['rld3'] = (df_nn_train['rld']**3)/1000
# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(df_nn_train[['rld','ttfm1']],
                                                    df_nn_train['de'], test_size=0.2, random_state=42,
                                                    shuffle=False)

# Define the model
model = Sequential([
    Dense(10, activation=PReLU(), input_shape=(2,)),  # Hidden layer with 10 neurons
    Dense(10, activation='relu'),# Hidden layer with 10 neurons
    Dense(1)  # Output layer with a single neuron (for regression output)
])

# Compile the model
model.compile(optimizer='adam', loss='mse', metrics=['mae'])

# Define the early stopping criteria
early_stopping = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

# Train the model
model.fit(X_train, y_train, epochs=100, batch_size=10, validation_data=(X_test, y_test))

# Evaluate the model
loss, mae = model.evaluate(X_test, y_test)
print(f"Mean Absolute Error on Test Set: {mae}")

# # Make predictions (replace X_new with new data points you want to predict)
# X_new = np.array([11, 12, 13])
# y_pred = model.predict(X_new)
# print(f"Predictions: {y_pred.flatten()}")



# After training the model
y_val_pred = model.predict(X_test)

# Plotting the validation predictions against the original values
plt.figure(figsize=(10,6))
plt.scatter(X_test['rld'], y_test, color='blue', label='Original Values')
plt.scatter(X_test['rld'], y_val_pred, color='red', label='Predicted Values')
plt.xlabel('X values')
plt.ylabel('Y values')
plt.title('Original vs Predicted Values on Validation Data')
plt.legend()
plt.grid(True)
plt.show()

