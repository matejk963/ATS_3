#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  1 16:02:14 2025

@author: marek
"""

import geopandas as gpd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from Database.DB_reader import Database
import matplotlib.colors as mcolors

# Path to the downloaded shapefile
shapefile_path = '/maps/ne_110m_admin_0_countries.shp'

def process(mkt_dict, base_path):
    # Load the dataset
    world = gpd.read_file(base_path + shapefile_path)
    
    date_start = (datetime.today() + timedelta(days=1)).date()
    date_end = (datetime.today() + timedelta(days=1, hours=23))
    
    db_reader = Database()
    df_spot = db_reader.getSpotPriceData(listOfMarkets=list(mkt_dict.keys()),
                                         _from=date_start.strftime('%Y-%m-%d'),
                                         _to=date_end.strftime('%Y-%m-%d'))
    
    # Load prices
    mean_series = df_spot.mean()
    price_dict = {mkt_dict[k]: round(v, 2) for k, v in mean_series.to_dict().items()
                  if not np.isnan(v)}
    
    # List of EU countries (simplified and not exhaustive)
    eu_countries = list(price_dict.keys())
    
    # Define the bounding box of the EU region
    eu_bbox = Polygon([(-10.5, 34.5), (40.0, 34.5), (40.0, 71.5), (-10.5, 71.5), (-10.5, 34.5)])
    
    # Filter for EU countries listed in `price_dict`
    filtered_world = world[world['NAME'].isin(price_dict.keys()) & world['NAME'].isin(eu_countries)]
    
    # Clip geometries to the EU bounding box
    filtered_world = filtered_world[filtered_world.intersects(eu_bbox)]
    
    # Add prices to the GeoDataFrame
    filtered_world['price'] = filtered_world['NAME'].map(price_dict)
    
    # Define a custom label position for mainland France
    custom_label_positions = {
        'France': Point(2.5, 46.5),  # Approximate centroid of mainland France
        'Denmark': Point(9.0, 56.0),
    }
    
    # Normalize the colormap between 25 and 175
    norm = mcolors.Normalize(vmin=25, vmax=175)
    
    # Plot the map with colors based on prices
    fig_path = '/Spot/Map/spot_map.png'
    fig, ax = plt.subplots(1, 1, figsize=(18, 12))
    filtered_world.boundary.plot(ax=ax, linewidth=1, edgecolor="black")  # Country boundaries
    filtered_world.plot(column='price', ax=ax, cmap='Spectral_r', legend=True,
                        edgecolor="black", norm=norm)
    
    # Add country labels with prices
    for idx, row in filtered_world.iterrows():
        if row['price'] is not None:
            if row['NAME'] in custom_label_positions:
                x, y = custom_label_positions[row['NAME']].x, custom_label_positions[row['NAME']].y
            else:
                x, y = row['geometry'].centroid.coords[0]
            if row['NAME'] == 'Denmark':
                price = str(round(mean_series['dkw'], 2)) + '/' + str(round(mean_series['dke'], 2))
            else:
                price = str((row['price']))
            ax.text(x, y, price, fontsize=18, ha='center', fontweight='bold', color='black')
    
    
    # Title and settings
    title = f"Spot Prices in EUR/MWh Baseload for date: {date_start.strftime('%a, %Y/%m/%d')}"
    plt.title(title, fontsize=14)
    plt.axis("off")
    plt.xlim(-10.5, 30.0)  # EU bounding box longitude range
    plt.ylim(34.5, 61.5)  # EU bounding box latitude range
    plt.tight_layout()
    fig.savefig(base_path + fig_path)
    plt.close(fig)
    
    return date_start


# mkt_dict = {'at': 'Austria', 'be': 'Belgium', 'bg': 'Bulgaria', 'cz': 'Czechia',
#             'de': 'Germany', 'dkw': 'Denmark', 'dke': 'Denmark', 'fr': 'France',
#             'hu': 'Hungary', 'nl': 'Netherlands', 'ro': 'Romania',
#             'si': 'Slovenia', 'sk': 'Slovakia'}
# sD = process(mkt_dict)
# print(f"Daily spot job for date: {sD.strftime('%a, %Y/%m/%d')}")
# shapefile_path = r'//192.168.10.91/data/Data/maps/ne_110m_admin_0_countries.shp'
# world = gpd.read_file(shapefile_path)
# print(world)

mkt_dict = {'at': 'Austria',
 'be': 'Belgium',
 'bg': 'Bulgaria',
 'cz': 'Czechia',
 'de': 'Germany',
 'dkw': 'Denmark',
 'dke': 'Denmark',
 'fr': 'France',
 'hu': 'Hungary',
 'nl': 'Netherlands',
 'ro': 'Romania',
 'si': 'Slovenia',
 'sk': 'Slovakia',
 'hr': 'Croatia',
 'gr': 'Greece',
 'es': 'Spain',
 'it_nord': 'Italy'}
sD = process(mkt_dict, r'//192.168.10.91/Data')

