import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import geodesic

# Path to the extracted shapefile directory
shapefile_path = r"C:\Users\krajcovic\Documents\Algo\Projects\Data\ne_110m_admin_0_countries\ne_110m_admin_0_countries.shp"

# Load the shapefile (GeoDataFrame)
# Load the shapefile (GeoDataFrame)
world = gpd.read_file(shapefile_path)

# List of countries to process
countries_to_process = ["Germany", "France", "Italy", "Spain", "Iceland",
                        "Greece", "Ukraine", "Algeria", "Egypt", "Turkey"]

# Dictionary with custom sampling points
custom_points = {
    "Azores": [38.22799871002208, -26.852245246685932, 500],  # [longitude, latitude, radius in km]
    "NorthSea": [55.379062732879945, 3.3161289971029424, 250],
    "Baltic": [58.30601569521, 19.91613184627471, 500],
    "Bermuda": [29.699272531492042, -69.7352009028432, 1000]
}

# Initialize an empty DataFrame to hold results
final_df = pd.DataFrame(columns=['longitude', 'latitude', 'quadrant', 'country'])

def sample_points_within_radius(center_point, radius_km, n_samples):
    points = []
    for _ in range(n_samples):
        # Random distance and angle
        r = np.sqrt(np.random.uniform(0, 1)) * radius_km
        theta = np.random.uniform(0, 2 * np.pi)
        # Offset in meters
        dx = r * np.cos(theta) * 1000
        dy = r * np.sin(theta) * 1000
        # Calculate new point
        new_point = geodesic(meters=dx).destination(center_point, 90)
        new_point = geodesic(meters=dy).destination((new_point.latitude, new_point.longitude), 0)
        points.append([new_point.longitude, new_point.latitude])
    return points

for country_name in countries_to_process:
    # Filter the GeoDataFrame for the current country
    if 'NAME' in world.columns:
        country = world[world['NAME'] == country_name]
    elif 'ADMIN' in world.columns:
        country = world[world['ADMIN'] == country_name]
    else:
        raise ValueError("Country name column not found. Please check the column names.")
    
    # Re-project geometries to a projected CRS
    country = country.to_crs(epsg=3395)
    
    # Get bounding box coordinates
    minx, miny, maxx, maxy = country.total_bounds
    
    # Generate a grid of coordinates within the bounding box
    num_points = 1000  # Total number of points
    latitudes = np.linspace(miny, maxy, int(np.sqrt(num_points)))
    longitudes = np.linspace(minx, maxx, int(np.sqrt(num_points)))
    grid_points = np.array(np.meshgrid(longitudes, latitudes)).T.reshape(-1, 2)
    
    # Convert grid points to GeoDataFrame
    grid_gdf = gpd.GeoDataFrame(geometry=[Point(xy) for xy in grid_points], crs=country.crs)
    
    # Filter points that fall within the country
    points_within_country = grid_gdf[grid_gdf.within(country.geometry.unary_union)]
    
    # Get the centroid of the country
    centroid = country.geometry.centroid.iloc[0]
    
    # Divide points into quadrants
    points_within_country.loc[:, 'quadrant'] = points_within_country.apply(
        lambda row: (
            'NE' if row.geometry.y > centroid.y and row.geometry.x > centroid.x else
            'NW' if row.geometry.y > centroid.y and row.geometry.x < centroid.x else
            'SE' if row.geometry.y < centroid.y and row.geometry.x > centroid.x else
            'SW'
        ), axis=1)
    
    # Sample n/4 points from each quadrant
    n = 100  # Total number of points desired per country
    quadrants = ['NE', 'NW', 'SE', 'SW']
    
    # Adjust sample size for each quadrant
    sampled_points_list = []
    for q in quadrants:
        quadrant_points = points_within_country[points_within_country['quadrant'] == q]
        sample_size = min(len(quadrant_points), n // 4)
        if sample_size > 0:
            sampled_points_list.append(quadrant_points.sample(sample_size, random_state=1))
        else:
            print(f"Not enough points in {q} quadrant for {country_name}")
    
    sampled_points = pd.concat(sampled_points_list)
    
    # Create DataFrame with longitude, latitude, quadrant, and country
    sampled_points['longitude'] = sampled_points.geometry.x
    sampled_points['latitude'] = sampled_points.geometry.y
    sampled_points['country'] = country_name
    country_df = sampled_points[['longitude', 'latitude', 'quadrant', 'country']].reset_index(drop=True)
    
    # Append the results to the final DataFrame
    final_df = pd.concat([final_df, country_df], ignore_index=True)

# Add custom points to final_df
for name, (lon, lat, radius) in custom_points.items():
    center_point = (lat, lon)  # Note the order is (latitude, longitude)
    sampled_custom_points = sample_points_within_radius(center_point, radius, n)
    custom_df = pd.DataFrame(sampled_custom_points, columns=['longitude', 'latitude'])
    custom_df['quadrant'] = 'Custom'
    custom_df['country'] = name
    final_df = pd.concat([final_df, custom_df], ignore_index=True)

# Plotting the points
fig, ax = plt.subplots(1, 1, figsize=(10, 10))
world.boundary.plot(ax=ax, linewidth=1)
final_gdf = gpd.GeoDataFrame(final_df, geometry=[Point(xy) for xy in zip(final_df.longitude, final_df.latitude)])
final_gdf.plot(ax=ax, color='red', markersize=5)
plt.xlabel('Longitude')
plt.ylabel('Latitude')
plt.title(f'Evenly Distributed Points in Selected Countries and Custom Areas')
plt.show()


