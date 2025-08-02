# -*- coding: utf-8 -*-
"""
Created on Tue Oct  1 09:58:29 2024

@author: scasny
"""

import json
import numpy as np
import xgboost as xgb

path = r"C:\develop\EnergyTrading\Python\Strategies\Sparsity_strategy\xgb_long.json"

# Load the JSON model
with open(path, 'r') as f:
    model = json.load(f)

# A function to make predictions using a single decision tree
def predict_single_tree(tree, features):
    node = 0  # Start at the root node (index 0)
    
    # Traverse the tree
    while tree['left_children'][node] != -1 and tree['right_children'][node] != -1:
        feature_index = tree['split_indices'][node]
        split_condition = np.float64(tree['split_conditions'][node])

        # Traverse left or right based on the split condition
        if features[feature_index] < split_condition:
            node = tree['left_children'][node]
        else:
            node = tree['right_children'][node]
    
    # Once a leaf is reached, return the base weight (prediction)
    return tree['base_weights'][node]

# Sigmoid function for binary classification
def sigmoid(x):
    return 1 / (1 + np.exp(-x))

# Function to make a prediction using all trees in the model
def predict_ensemble(model, features):
    # Sum the outputs from all trees 
    base_score = float(model['learner']['learner_model_param']['base_score'])
    logits = np.log(base_score / (1 - base_score))
    
    for tree in model['learner']['gradient_booster']['model']['trees']:
        # Check each tree contribution carefully
        tree_contribution = predict_single_tree(tree, features)
        print(f"Tree contribution: {tree_contribution}, Current Logits: {logits}")

        logits += tree_contribution

    # Optionally apply sigmoid if you're interested in probability
    probability = sigmoid(logits)
    return logits, probability  # Return both logit and probability for comparison


features = [0.7, 0.01, .5, 0.9, 0.9, -0.5, -0.5, 0.9, 0.25, 0.1, 0.7, 0.7]
logits, probability = predict_ensemble(model, features)
print("Predicted :", logits, probability)

loaded_model = xgb.XGBClassifier()

loaded_model.load_model(path)
a = loaded_model.predict([features], output_margin=True)
print(a)