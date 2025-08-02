# -*- coding: utf-8 -*-
"""
Created on Sun Sep 22 09:34:07 2024

@author: krajcovic
"""

from Utilities.FuturesManager.FuturesManager import FuturesManager
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash
import copy
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

# Function to get the available unique columns from MultiIndex DataFrame's second level
def get_columns_from_multiindex(df):
    if isinstance(df.columns, pd.MultiIndex):
        # Get unique values from level 1 (second level) of the MultiIndex
        unique_level_1_values = df.columns.get_level_values(1).unique()
        return [{'label': col, 'value': col} for col in unique_level_1_values]
    return []



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
    html.Div(id='column-dropdown-container', style={'display': 'none'}),  # Dropdown for column selection
    html.Div(id='output')  # Placeholder for displaying the final selection or DataFrame plot
])

# Combined callback to handle dropdown updates and plotting
@app.callback(
    [Output('dropdown-container', 'children'),
     Output('output', 'children', allow_duplicate=True),  # Allow duplicate
     Output('column-dropdown-container', 'style')],
    [Input('refresh-1', 'n_clicks'), Input({'type': 'refresh-button', 'index': ALL}, 'n_clicks')],
    [State('level-1-dropdown', 'value'), State({'type': 'dynamic-dropdown', 'index': ALL}, 'value'),
     State('dropdown-container', 'children'), State('column-dropdown-container', 'style')],
    prevent_initial_call=True  # Prevent the callback from firing on initial load
)
def update_dropdowns_and_plot(refresh1_clicks, dynamic_button_clicks, level1_value, dynamic_values, current_children, column_style):
    triggered_input = ctx.triggered_id

    # Ensure new_children is always initialized properly
    if current_children is None:
        new_children = []
    else:
        new_children = current_children.copy()

    # Handle dropdown updates first
    if triggered_input == 'refresh-1':
        new_children = []  # Clear all lower levels
        column_style = {'display': 'none'}  # Hide column dropdown initially
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
        return new_children, None, column_style  # Return updated dropdowns without a plot

    # If a DataFrame is reached, show the level 2 column selection dropdown
    if isinstance(current_dict, pd.DataFrame):
        # Sort MultiIndex before using .xs() to avoid performance warning
        current_dict = current_dict.sort_index()

        # Populate level 2 column dropdown
        columns_dropdown = dcc.Dropdown(
            id='level-2-column-dropdown',
            options=get_columns_from_multiindex(current_dict),
            placeholder='Select Column to Plot',
            style={'width': '50%', 'marginTop': '10px'}
        )
        column_style = {'display': 'block'}  # Show column dropdown
        new_children = new_children + [columns_dropdown]  # Add column selection dropdown

        return new_children, None, column_style  # Return column selection dropdown

    return new_children, None, column_style  # Return dropdowns without a plot if not at a DataFrame

# Function to flatten the MultiIndex
def flatten_multiindex(df):
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten the MultiIndex by joining the levels with an underscore
        df.columns = ['_'.join(col).strip() for col in df.columns.values]
    return df

# Updated plot_data function
@app.callback(
    Output('output', 'children', allow_duplicate=True),  # Allow duplicate
    [Input('level-2-column-dropdown', 'value')],
    [State('dropdown-container', 'children'),
     State('level-1-dropdown', 'value'), State({'type': 'dynamic-dropdown', 'index': ALL}, 'value')],
    prevent_initial_call=True  # Prevent the callback from firing on initial load
)
def plot_data(column_value, current_children, level1_value, dynamic_values):
    # Check if the column dropdown exists and if a valid column is selected
    if column_value is None or not ctx.triggered:
        return None

    # Dynamically traverse data_dict based on selected values
    selected_values = [level1_value] + [parse_tuple_like_string(val) for val in dynamic_values if val]
    current_dict = data_dict

    # Traverse data_dict to get the correct DataFrame
    for value in selected_values:
        if isinstance(current_dict, dict) and value in current_dict:
            current_dict = current_dict[value]
        else:
            return "Error: Unable to find DataFrame"

    # Ensure the current_dict is a DataFrame
    if isinstance(current_dict, pd.DataFrame):
        # Fully sort MultiIndex to avoid PerformanceWarning
        current_dict = current_dict.sort_index(sort_remaining=True)

        # Select all columns in level 1 that match the selected column_value
        try:
            filtered_df = current_dict.loc[:, current_dict.columns.get_level_values(1) == column_value]
        except KeyError:
            return f"Error: Column '{column_value}' not found in DataFrame"

        # Flatten the MultiIndex
        filtered_df = flatten_multiindex(filtered_df)

        # Plot the flattened DataFrame
        fig = px.line(filtered_df)
        return dcc.Graph(figure=fig)

    return "Error: No DataFrame found at this level"






if __name__ == '__main__':
    app.run_server(debug=True)
