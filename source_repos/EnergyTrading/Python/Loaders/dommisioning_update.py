# -*- coding: utf-8 -*-
"""
Created on Wed Nov 20 12:42:13 2024

@author: krajcovic
"""

import pandas as pd

coal_data_path = '//192.168.10.91/data/Data/Spot/Entso/InstCap/2024-09-30-BeyondFossilFuels-Europe_Coal_Plants_Database (2).xlsx'
gas_data_path = '//192.168.10.91/data/Data/Spot/Entso/InstCap/20241118_BeyondFossilFuels_GasPlantsDatabase.xlsx'

df_units = pd.read_excel(coal_data_path, sheet_name='Unit')

# Rename columns for easier processing
df_units.columns = [
    'bff_unit_id', 'bff_plant_id', 'unit_name', 'plant_name', 'country', 'region',
    'fuel_type', 'owner', 'commissioning_year', 'retirement_year', 'retirement_announcement_date',
    'retirement_announced', 'country_phase_out', 'unit_type', 'unit_status_gross',
    'unit_status_detailed', 'capacity_mw_el_gross'
]

# Drop rows that are not part of the actual data
df_units = df_units.dropna(subset=['unit_name']).reset_index(drop=True)

# Filter relevant columns
df_filtered = df_units[[
    'country', 'fuel_type', 'unit_name', 'plant_name', 'retirement_year',
    'retirement_announcement_date', 'unit_type', 'unit_status_detailed', 'capacity_mw_el_gross'
]]

# Create nested dictionary {country: {fuel_type: {rest of the data}}}
units_dict = {}
for _, row in df_filtered.iterrows():
    country = row['country']
    fuel_type = row['fuel_type']
    
    if country not in units_dict:
        units_dict[country] = {}
    if fuel_type not in units_dict[country]:
        units_dict[country][fuel_type] = []
    
    unit_data = {
        'unit_name': row['unit_name'],
        'plant_name': row['plant_name'],
        'retirement_year': row['retirement_year'],
        'retirement_announcement_date': row['retirement_announcement_date'],
        'unit_type': row['unit_type'],
        'unit_status_detailed': row['unit_status_detailed'],
        'capacity_mw_el_gross': row['capacity_mw_el_gross']
    }
    units_dict[country][fuel_type].append(unit_data)

# Display a part of the nested dictionary
units_dict_sample = {k: v for k, v in list(units_dict.items())[:2]}  # Display only first two countries for brevity
units_dict_sample
