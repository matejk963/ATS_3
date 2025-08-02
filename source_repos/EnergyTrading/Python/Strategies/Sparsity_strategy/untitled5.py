import pandas as pd
import numpy as np
from sklearn.feature_selection import mutual_info_regression

# Your existing code
df = pd.read_parquet(r"W:\calib_results\calib_q_072024-092024.parquet")

df_params = df["combination"].str.split("_", expand=True).astype(float)
df_params.columns = [f"x{i+1}" for i in range(df_params.shape[1])]

Xs = df_params
Y = df['pnl']

# Calculate Mutual Information (MI) for consistency analysis
mi_scores = mutual_info_regression(Xs, Y, random_state=42)
mi_scores_dict = dict(zip(Xs.columns, mi_scores))

# Normalize MI scores
mi_scores_normalized = mi_scores / np.sum(mi_scores)

# Calculate a consistency score for each combination
df['consistency_score'] = df_params.apply(lambda row: np.sum(row * mi_scores_normalized), axis=1)

# Combine pnl and consistency score
df['combined_score'] = df['pnl'] * df['consistency_score']

# Find the combination with the highest combined score
best_combination = df.loc[df['combined_score'].idxmax()]

print("Best combination:")
print(f"Parameters: {best_combination['combination']}")
print(f"PNL: {best_combination['pnl']}")
print(f"Consistency Score: {best_combination['consistency_score']}")
print(f"Combined Score: {best_combination['combined_score']}")

# Display MI scores for reference
print("\nMutual Information Scores:")
for param, score in mi_scores_dict.items():
    print(f"{param}: {score}")