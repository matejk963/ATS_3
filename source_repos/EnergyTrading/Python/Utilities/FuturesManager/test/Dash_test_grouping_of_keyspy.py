# -*- coding: utf-8 -*-
"""
Created on Sun Sep 22 09:34:07 2024

@author: krajcovic
"""

from Utilities.FuturesManager.FuturesManager import FuturesManager
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash
import datetime as dt
import pandas as pd
import ast
import plotly.express as px

params_dict = {}
params_dict['product_list'] = ['M_1', 'M_2', 'M_3', 'Q_1']*4
params_dict['market_list'] = ['de'] * 8 + ['fr']*8
params_dict['delivery_list'] = ['base']*4 + ['peak'] * 4 + ['base']*4 + ['peak'] * 4
params_dict['eD'] = dt.datetime(2024, 9, 19)

fm_inst = FuturesManager(params_dict)
data_dict = fm_inst.analyze_data()

# Function to simplify tuple-like strings for dropdown display
def simplify_tuple_string(s):
    if isinstance(s, str) and s.startswith("("):
        return s.strip("()").replace("'", "").replace(",", " -")  # Simplify tuple-like string
    return s

# Function to convert tuple-like strings back into tuples
def parse_tuple_like_string(s):
    try:
        return ast.literal_eval(s) if isinstance(s, str) and s.startswith("(") else s
    except (SyntaxError, ValueError):
        return s  # Return the original string if parsing fails

# Function to generate dropdown options based on current dictionary level
def get_options_from_dict(current_dict):
    return [{'label': simplify_tuple_string(str(k)), 'value': str(k)} for k in current_dict.keys()]

# Dash app setup
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# App layout with the initial dropdown and refresh button
app.layout = html.Div([
    dcc.Dropdown(
        id='level-1-dropdown',
        options=get_options_from_dict(data_dict),
        placeholder='Select Level 1',
        style={'width': '50%', 'marginTop': '10px'}
    ),
    html.Button('Refresh Level 1', id='refresh-1', n_clicks=0, style={'marginTop': '10px'}),
    html.Div(id='dropdown-container'),  # Placeholder for additional dropdowns
    html.Div(id='output')  # Placeholder for displaying the final DataFrame plot
])

# Combined callback to handle dropdown updates and plotting
@app.callback(
    [Output('dropdown-container', 'children'),
     Output('output', 'children', allow_duplicate=True)],  # Allow duplicate
    [Input('refresh-1', 'n_clicks'), Input({'type': 'refresh-button', 'index': ALL}, 'n_clicks')],
    [State('level-1-dropdown', 'value'), State({'type': 'dynamic-dropdown', 'index': ALL}, 'value'),
     State('dropdown-container', 'children')],
    prevent_initial_call=True  # Prevent the callback from firing on initial load
)
def update_dropdowns_and_plot(refresh1_clicks, dynamic_button_clicks, level1_value, dynamic_values, current_children):
    triggered_input = ctx.triggered_id

    # Ensure new_children is always initialized properly
    if current_children is None:
        new_children = []
    else:
        new_children = current_children.copy()

    # Handle dropdown updates first
    if triggered_input == 'refresh-1':
        new_children = []  # Clear all lower levels
    elif isinstance(triggered_input, dict) and 'index' in triggered_input:
        level_changed = triggered_input['index']
        new_children = new_children[:level_changed-1]  # Clear dropdowns below the changed level

    # Convert stringified tuple-like values back to tuples
    dynamic_values = [parse_tuple_like_string(val) for val in dynamic_values]
    selected_values = [level1_value] + dynamic_values
    selected_values = [val for val in selected_values if val]  # Filter out None values

    # Traverse the data_dict based on selected values
    current_dict = data_dict
    for value in selected_values:
        if isinstance(current_dict, dict) and value in current_dict:
            current_dict = current_dict[value]
        else:
            break

    # Generate dropdowns if we're still in a dictionary
    if isinstance(current_dict, dict):
        level = len(selected_values) + 1
        new_dropdown = dcc.Dropdown(
            id={'type': 'dynamic-dropdown', 'index': level},
            options=get_options_from_dict(current_dict),
            placeholder=f'Select Level {level}',
            style={'width': '50%', 'marginTop': '10px'}
        )
        refresh_button = html.Button(
            f'Refresh Level {level}', id={'type': 'refresh-button', 'index': level}, n_clicks=0, style={'marginTop': '10px'}
        )
        # Only add the new dropdown and button if not already present
        if not any(dropdown['props']['id']['index'] == level for dropdown in new_children):
            new_children = new_children[:level-2] + [new_dropdown, refresh_button]  # Replace lower-level dropdowns
        return new_children, None  # Return updated dropdowns without a plot

    # If a dictionary is reached and Level 1 is 'bb_bands', plot all DataFrames beyond Level 4
    if level1_value == 'bb_bands' and isinstance(current_dict, dict):
        fig_list = []
        for key, df in current_dict.items():
            if isinstance(df, pd.DataFrame):
                # Flatten the MultiIndex
                df = flatten_multiindex(df)
                # Create the plot for the current DataFrame
                fig = px.line(df)
                fig_list.append(dcc.Graph(figure=fig))

        # Return all plots for the selected group (plot all DataFrames at Level 4 or deeper)
        return new_children, fig_list

    # If not 'bb_bands', plot only the specific DataFrame under the selected key
    if isinstance(current_dict, pd.DataFrame):
        # Flatten the MultiIndex
        df = flatten_multiindex(current_dict)
        # Plot the specific DataFrame
        fig = px.line(df)
        return new_children, dcc.Graph(figure=fig)

    return new_children, None  # Return dropdowns without a plot if no DataFrame is found

# Function to flatten the MultiIndex
def flatten_multiindex(df):
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten the MultiIndex by joining the levels with an underscore
        df.columns = ['_'.join(col).strip() for col in df.columns.values]
    return df

if __name__ == '__main__':
    app.run_server(debug=True)
