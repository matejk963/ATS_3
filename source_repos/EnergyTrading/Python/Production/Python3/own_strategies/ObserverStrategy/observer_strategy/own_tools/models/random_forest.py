"""
Pure Python Random Forest implementation using only numpy and built-ins.
Designed to match sklearn RandomForestClassifier exactly.
"""

import numpy as np
import json
from .decision_tree import DecisionTree


class RandomForest:
    """Production Random Forest Classifier - load and predict only"""
    
    def __init__(self):
        self.trees = []
        self.n_classes = None
    
    def predict(self, X):
        """Predict classes using majority voting"""
        probas = self.predict_proba(X)
        return np.argmax(probas, axis=1)
    
    def predict_proba(self, X):
        """Predict class probabilities"""
        X = np.array(X)
        n_samples = X.shape[0]
        n_estimators = len(self.trees)
        
        # Get probabilities from all trees
        all_probabilities = np.zeros((n_samples, n_estimators, self.n_classes))
        
        for i, tree in enumerate(self.trees):
            tree_probas = tree._predict_proba_samples(X, self.n_classes)
            all_probabilities[:, i, :] = tree_probas
        
        # Average probabilities across all trees
        probabilities = np.mean(all_probabilities, axis=1)
        
        return probabilities
    
    @classmethod
    def from_dict(cls, rf_dict):
        """Load trained random forest from dictionary"""
        rf = cls()
        rf.n_classes = rf_dict['n_classes']
        
        # Reconstruct trees
        rf.trees = []
        for tree_dict in rf_dict['trees']:
            tree = DecisionTree.from_dict(tree_dict)
            rf.trees.append(tree)
        
        return rf
    
    @classmethod
    def from_json(cls, json_str):
        """Load model from JSON string"""
        model_dict = json.loads(json_str)
        return cls.from_dict(model_dict)
    
