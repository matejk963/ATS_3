# -*- coding: utf-8 -*-
"""
Created on Thu Dec  5 15:48:59 2024

@author: scasny
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import hdbscan
from scipy.spatial.distance import cdist


df = pd.read_parquet(r"W:\calib_results\calib_q_072024-092024.parquet")

param_df = df["combination"].str.split("_", expand=True).astype(float)
param_df.columns = [f"x{i+1}" for i in range(param_df.shape[1])]

param_df['objective'] = df['pnl']
high_obj_threshold = 0.9
# Filter high objective points (e.g., top 10%)
n = 1000  # Number of top values you want to select
high_obj_points = param_df.nlargest(n, 'objective')
high_obj_points = param_df[param_df['objective'] >= high_obj_threshold]

# Apply HDBSCAN clustering
clusterer = hdbscan.HDBSCAN(min_cluster_size=30)
cluster_labels = clusterer.fit_predict(high_obj_points)

# Add labels to the DataFrame
high_obj_points['cluster'] = cluster_labels


from sklearn.metrics import silhouette_score

# Exclude noise points (-1)
valid_points = high_obj_points[high_obj_points['cluster'] != -1]
sil_score = silhouette_score(valid_points.drop(['cluster'], axis=1), valid_points['cluster'])
print(f"Silhouette Score: {sil_score}")

from sklearn.metrics import davies_bouldin_score

db_score = davies_bouldin_score(valid_points.drop(['cluster'], axis=1), valid_points['cluster'])
print(f"Davies-Bouldin Index: {db_score}")

# Compute centroids
centroids = valid_points.groupby('cluster').mean()

# Intra-cluster compactness

# Inter-cluster separation
separation = cdist(centroids, centroids, metric='euclidean')
print(f"Inter-cluster Separation Matrix:\n{separation}")

print(valid_points['cluster'].value_counts())

clustered_df = param_df[param_df['objective'] >= high_obj_threshold].copy()
clustered_df['cluster'] = cluster_labels

objective_summary = clustered_df.groupby('cluster')['objective'].describe()
print(objective_summary)

# Assuming objective_summary is already calculated
objective_summary = high_obj_points.groupby('cluster')['objective'].agg(['mean', 'std', 'count'])

# Calculate a score for each cluster (higher is better)
objective_summary['score'] = objective_summary['mean'] / (objective_summary['std'] + 1)  # Adding 1 to avoid division by zero

# Sort clusters by score in descending order
best_clusters = objective_summary.sort_values('score', ascending=False)

print("Clusters ranked by score (mean/std):")
print(best_clusters)

# Select the best cluster (excluding -1)
best_cluster = best_clusters[best_clusters.index != -1].iloc[0]

print("\nBest Cluster:")
print(best_cluster)

# Get the parameters for the best cluster
best_cluster_points = high_obj_points[high_obj_points['cluster'] == best_cluster.name]
best_parameters = best_cluster_points.mean()

print("\nBest Parameters (Mean of Best Cluster):")
print(best_parameters)