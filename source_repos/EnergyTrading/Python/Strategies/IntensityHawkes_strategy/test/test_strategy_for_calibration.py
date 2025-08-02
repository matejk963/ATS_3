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
tol=0.019

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_ba_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_trades_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')

param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = time(17)
param_dict['br_fee'] = 0.0175
param_dict['ba_max'] = 0.5
param_dict['take_profit'] = 0.003
param_dict['stop_loss_rat'] = 1.5
param_dict['bid_threshold'] = 2
param_dict['ask_threshold'] = 2
# param_dict['train_lookback'] = 30
param_dict['trailing_tp_tau'] = 10
param_dict['trail_sl_bool'] = False

strategy_class = StrategyHI(HawkesIntensity,trades, ba, ['dem1'],
                            'MM', 'de', 'de', is_overnight=False, trailing_takeprofit=False)
# strategy_class.load_params(param_dict)

vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestIB(vol_class)

strategy_class.load_params(param_dict, contr_vars)

strategy_class.model.estimate_params()

est_params = strategy_class.model.params_dict
# strategy_class.model.major_dict = None

# strategy_class.model.create_train_test_dict()
# major_dict = strategy_class.model.major_dict


xx = backtest_class.simulate_strategy(strategy_class, 'de', strategy_class.model.return_data_dict()['dem1'])

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in strategy_class.stats_dict.keys() if k in ['timestamp', 'position', 'price_level',
                                                                                                      'bid_int', 'ask_int', 'sl', 'price_bid',
                                                                                                      'price_ask',
                                                                                                      'tp', 'sl']})
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "browser"
from Utilities.dfutils import date_filter
# df_data = date_filter(data_dict['m1'], '2023-09-11')
df_data = trades.reset_index().drop_duplicates('datetime').set_index('datetime')
df_params = pd.DataFrame(strategy_class.monitoring_dict).drop_duplicates('timestamp').set_index('timestamp')

df_agg = pd.concat([df_data, df_params], axis=1, join='outer').dropna(subset=['price_dem1'])


from plotly.subplots import make_subplots
# Create a figure with two subplots (rows) that share the same x-axis
fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
df_agg['color'] = df_agg['action_dem1'].map({-1: 'blue', 1: 'orange'})
colors = df_agg['action_dem1'].map({-1: 'blue', 1: 'orange'})
# Assign colors directly based on 'action_dem1' values for the df_agg scatter plot
color_map = {1: 'orange', -1: 'blue'}  # Define your color mapping
point_colors = df_agg['action_dem1'].map(color_map).tolist()  # Map your 'action_dem1' values to colors
# Modify this trace to color points based on 'action_dem1'
# Add traces
fig.add_trace(
    go.Scatter(
        x=df_agg.index, 
        y=df_agg['price_dem1'],
        mode='markers',
        marker=dict(color=point_colors),  # Use the mapped colors
        customdata=[
            [
                '<BR><b>bid_int: </b>' + str(df_agg.loc[i, 'bid_int']),
                '<BR><b>ask_int: </b>' + str(df_agg.loc[i, 'ask_int'])
            ] for i in df_agg.index
        ],
        hovertemplate='<b>%{x} </b> <br><b>Price Level:</b> %{y:.2f}<br>%{customdata}'
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(
        x=df['timestamp'],
        y=df['price_level'],
        mode='markers',
        marker=dict(color=df['position']),
        customdata=df[['bid_int', 'ask_int',
                       'price_bid', 'price_ask',
                       'tp', 'sl']],
        hovertemplate=
            '<b>Timestamp:</b> %{x}<br>' +
            '<b>Price Level:</b> %{y}<br>' +
            '<b>Bid Int:</b> %{customdata[0]}<br>' +
            '<b>Ask Int:</b> %{customdata[1]}<br>'+
            '<b>Bid:</b> %{customdata[2]}<br>' +
            '<b>Ask:</b> %{customdata[3]}'+
            '<b>Take Profit:</b> %{customdata[4]}<br>' +
            '<b>Stop Loss:</b> %{customdata[5]}<br>'
    ),
    row=1, col=1  # Also in the first subplot
)

# Second subplot (bid_int and ask_int)
fig.add_trace(
    go.Scatter(
        x=df_agg.index, 
        y=df_agg['bid_int'],
        mode='lines',
        name='Bid Int',
        line=dict(color='blue')
    ),
    row=2, col=1  # This specifies that this trace is in the second row and first column
)

fig.add_trace(
    go.Scatter(
        x=df_agg.index, 
        y=df_agg['ask_int'],
        mode='lines',
        name='Ask Int',
        line=dict(color='red')
    ),
    row=2, col=1  # Also in the second subplot
)

# # Update the layout to add titles and adjust the y-axes if needed
# fig.update_layout(
#     xaxis_title='Time',
#     xaxis2_title='Time',  # You might not need this since x-axes are shared
#     yaxis_title='Price Level',
#     yaxis2_title='Intensity',
#     title_text="Your Chart Title"  # Add your chart title
# )

fig.update_layout(
    title_text="Your Chart Title",
    xaxis_title='Time',
    yaxis_title='Price Level',
    yaxis2_title='Intensity'
)

# # Add color axis settings for mapping 'action_dem1' values to colors
# fig.update_layout(
#     coloraxis=dict(
#         colorbar_title='Action Dem1',
#         colorbar_tickvals=[-1, 1],
#         colorbar_ticktext=['-1 (blue)', '1 (orange)'],
#         colorscale=[[-1, 'blue'], [1, 'orange']]  # Mapping -1 to blue and 1 to orange
#     ),
#     # Other layout settings...
#     xaxis_title='Time',
#     yaxis_title='Price Level',
#     yaxis2_title='Intensity',
#     title_text="Your Chart Title"
# )

# Display the figure
fig.show()

