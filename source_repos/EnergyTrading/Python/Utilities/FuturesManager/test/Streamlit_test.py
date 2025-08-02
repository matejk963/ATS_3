# -*- coding: utf-8 -*-
"""
Created on Sun Sep 22 09:34:07 2024

@author: krajcovic
"""

from Utilities.FuturesManager.FuturesManager import FuturesManager

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
import datetime as dt


params_dict = {}
params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1', 'Y_2']*4
params_dict['market_list'] = ['de'] * 8 + ['fr']*8
params_dict['delivery_list'] = ['base']*4 + ['peak'] * 4 + ['base']*4 + ['peak'] * 4
params_dict['eD'] = dt.datetime(2024,8,9)

params_dict = {}
params_dict['product_list'] = ['M_2', 'Q_4']*4
params_dict['market_list'] = ['de'] * 4 + ['fr'] * 4
params_dict['delivery_list'] = ['base']*2 + ['peak'] * 2 + ['base']*2 + ['peak'] * 2
params_dict['eD'] = dt.datetime(2024,8,9)

fm_inst = FuturesManager(params_dict)

data_dict = fm_inst.analyze_data()

@st.cache
def expensive_computation(data):
    # Perform the expensive task
    return processed_data


# Function to recursively traverse the nested dictionary
def traverse_dict(d, level=0):
    if isinstance(d, dict):
        selected_key = st.selectbox(f"Select Level {level}", list(d.keys()))
        if selected_key:
            traverse_dict(d[selected_key], level + 1)
    else:
        st.write(f"Final Value: {d}")

# Streamlit app layout
st.title("Nested Dictionary Visualizer")

st.write("Navigate through the nested dictionary using dropdowns.")
traverse_dict(data_dict)

import subprocess

# Use subprocess to run Streamlit
subprocess.run(['streamlit', 'run', 'X:/Utilities/FuturesManager/Streamlit_test.py'])

