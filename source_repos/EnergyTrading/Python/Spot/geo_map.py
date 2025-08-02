import geopandas as gpd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from Database.DB_reader import Database
import matplotlib.colors as mcolors
import os

# Path to the downloaded shapefile
shapefile_path = 'maps/ne_110m_admin_0_countries.shp'

def process(mkt_dict, base_path, target_date=None):
    fig = None
    ax = None
    
    try:
        # Use os.path.join for robust path handling
        full_path = os.path.join(base_path, shapefile_path)
        print(f"Loading shapefile from: {full_path}")  # Debug print
        world = gpd.read_file(full_path)
        
        # If no target_date provided, default to today
        if target_date is None:
            target_date = datetime.today().date()
        # Ensure target_date is a date object if datetime was passed
        elif isinstance(target_date, datetime):
            target_date = target_date.date()
        
        # Create datetime objects for start and end of the target date (rounded to whole hours)
        date_start = datetime.combine(target_date + timedelta(days=1), datetime.min.time())  # 00:00:00
        date_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()) + timedelta(hours=23)  # 23:00:00
        
        db_reader = Database()
        try:
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
            fig.savefig(base_path + fig_path, dpi=150, bbox_inches='tight')
            
            return date_start
            
        finally:
            # Cleanup database connection
            if hasattr(db_reader, 'engine') and db_reader.engine:
                db_reader.engine.dispose()
    
    except Exception as e:
        print(f"Error in geo_map processing: {e}")
        raise
    finally:
        # Ensure matplotlib resources are cleaned up
        if fig is not None:
            plt.close(fig)
        plt.close('all')  # Close any remaining figures
        
        # Force garbage collection
        import gc
        gc.collect()