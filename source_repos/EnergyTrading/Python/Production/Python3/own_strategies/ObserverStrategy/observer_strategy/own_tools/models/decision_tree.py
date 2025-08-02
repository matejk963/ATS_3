"""
Pure Python Decision Tree implementation using only numpy and built-ins.
Designed to match sklearn DecisionTreeClassifier exactly.
"""

import numpy as np
from collections import Counter
import json


class DecisionTreeNode:
    """Single node in decision tree"""
    
    def __init__(self):
        self.feature_idx = None      # Feature index for split
        self.threshold = None        # Threshold value for split
        self.left = None            # Left child node
        self.right = None           # Right child node
        self.value = None           # Leaf node prediction (class)
        self.class_probs = None     # Leaf node class probabilities  
        self.samples = 0            # Number of samples at this node
        self.is_leaf = False        # Whether this is a leaf node


class DecisionTree:
    """Production Decision Tree Classifier - load and predict only"""
    
    def __init__(self):
        self.root = None
    
    def predict(self, X):
        """Predict classes for samples in X"""
        return self._predict_samples(X)
    
    def _predict_samples(self, X):
        """Predict classes for samples in X"""
        X = np.array(X)
        predictions = []
        
        for sample in X:
            prediction = self._predict_sample(sample, self.root)
            predictions.append(prediction)
        
        return np.array(predictions)
    
    def _predict_proba_samples(self, X, n_classes):
        """Predict class probabilities for samples in X"""
        X = np.array(X)
        probabilities = []
        
        for sample in X:
            proba = self._predict_proba_sample(sample, n_classes)
            probabilities.append(proba)
        
        return np.array(probabilities)
    
    def _predict_sample(self, sample, node):
        """Predict single sample"""
        if node.is_leaf:
            return node.value
        
        if sample[node.feature_idx] <= node.threshold:
            return self._predict_sample(sample, node.left)
        else:
            return self._predict_sample(sample, node.right)
    
    def _predict_proba_sample(self, sample, n_classes):
        """Predict class probabilities for single sample"""
        node = self._traverse_to_leaf(sample, self.root)
        
        if node.class_probs is not None:
            # Ensure we have probabilities for all classes
            probs = np.zeros(n_classes)
            for i, prob in enumerate(node.class_probs):
                if i < n_classes:
                    probs[i] = prob
            return probs
        else:
            # Fallback: create one-hot encoding from majority class
            probs = np.zeros(n_classes)
            if node.value is not None and node.value < n_classes:
                probs[node.value] = 1.0
            return probs
    
    def _traverse_to_leaf(self, sample, node):
        """Traverse tree to find leaf node for sample"""
        if node.is_leaf:
            return node
        
        if sample[node.feature_idx] <= node.threshold:
            return self._traverse_to_leaf(sample, node.left)
        else:
            return self._traverse_to_leaf(sample, node.right)
    
    
    @classmethod
    def from_dict(cls, tree_dict):
        """Load trained tree from dictionary"""
        tree = cls()
        tree.root = tree._dict_to_node(tree_dict['tree']) if tree_dict['tree'] else None
        return tree
    
    def _dict_to_node(self, node_dict):
        """Convert dictionary to node"""
        if node_dict is None:
            return None
        
        node = DecisionTreeNode()
        node.feature_idx = node_dict['feature_idx']
        node.threshold = node_dict['threshold']
        node.value = node_dict['value']
        node.class_probs = node_dict.get('class_probs', None)  # Handle both old and new format
        node.samples = node_dict['samples']
        node.is_leaf = node_dict['is_leaf']
        node.left = self._dict_to_node(node_dict['left'])
        node.right = self._dict_to_node(node_dict['right'])
        
        return node