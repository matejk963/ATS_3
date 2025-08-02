# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.


from dash import dcc, html, Input, Output, State, ALL, ctx
import dash
import plotly.express as px
import pandas as pd

import pickle

file_path = r'Z:\Data\Spot\Model\temp\fut_data_for_dash.pkl'
# with open(file_path, 'wb') as f:
#     pickle.dump(data_dict, f)

with open(file_path, 'rb') as f:
    data_dict = pickle.load(f)
    
# Function to simplify tuple-like strings for dropdown display
def simplify_tuple_string(s):
    if isinstance(s, str) and s.startswith("("):
        return s.strip("()").replace("'", "").replace(",", " -")  # Simplify tuple-like string
    return s
    
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
    html.Div(id='column-dropdown-container', style={'display': 'none'}),  # Dropdown for column selection
    html.Div(id='output')  # Placeholder for displaying the final selection or DataFrame plot
])
    
    
    
    
if __name__ == '__main__':
    app.run(debug=True)
