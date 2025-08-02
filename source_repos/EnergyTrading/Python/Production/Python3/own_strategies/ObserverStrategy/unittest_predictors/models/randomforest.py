"""
TDD tests for Random Forest production models.
Specs:
1. Export sklearn model to json
2. Load raw model from json 
3. Raw model predict == sklearn model predict
"""

import unittest
import numpy as np
import sys
import os
import json

# Import our modules using relative path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'observer_strategy'))

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.datasets import make_classification
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: sklearn not available, tests will be skipped")


class TestRandomForest(unittest.TestCase):
    """TDD: Export sklearn to JSON, load raw model, predictions match"""
    
    def setUp(self):
        """Generate test data"""
        if not SKLEARN_AVAILABLE:
            self.skipTest("sklearn not available")
            
        # Generate synthetic random data with 50+ points
        from sklearn.datasets import make_classification
        
        self.X, self.y = make_classification(
            n_samples=60,        # 60 data points
            n_features=4,        # 4 features  
            n_informative=3,     # 3 informative features
            n_redundant=1,       # 1 redundant feature
            n_classes=2,         # Binary classification
            n_clusters_per_class=1,
            random_state=42,     # Fixed seed for reproducibility
            shuffle=False
        )
        
        print(f"Generated synthetic data: {self.X.shape[0]} samples, {self.X.shape[1]} features")
    
    def test_export_sklearn_model_to_json(self):
        """Spec 1: Export sklearn model to JSON"""
        if not SKLEARN_AVAILABLE:
            self.skipTest("sklearn not available")
        
        # Train sklearn model
        sklearn_rf = RandomForestClassifier(n_estimators=2, max_depth=2, random_state=42)
        sklearn_rf.fit(self.X, self.y)
        
        # TODO: Implement export_to_json function
        from own_tools.models.sklearn_exporter import export_sklearn_rf_to_json
        
        json_str = export_sklearn_rf_to_json(sklearn_rf)
        
        # Should be valid JSON
        model_dict = json.loads(json_str)
        self.assertIsInstance(model_dict, dict)
        self.assertIn('n_classes', model_dict)
        self.assertIn('trees', model_dict)
    
    def test_load_raw_model_from_json(self):
        """Spec 2: Load raw model from JSON"""
        if not SKLEARN_AVAILABLE:
            self.skipTest("sklearn not available")
        
        # Train and export sklearn model
        sklearn_rf = RandomForestClassifier(n_estimators=2, max_depth=2, random_state=42)
        sklearn_rf.fit(self.X, self.y)
        
        from own_tools.models.sklearn_exporter import export_sklearn_rf_to_json
        json_str = export_sklearn_rf_to_json(sklearn_rf)
        
        # Load into raw model
        from own_tools.models.random_forest import RandomForest
        
        rf = RandomForest.from_json(json_str)
        
        # Should load successfully
        self.assertIsNotNone(rf)
        self.assertEqual(rf.n_classes, 2)
        self.assertEqual(len(rf.trees), 2)
    
    def test_raw_model_predict_equals_sklearn_predict(self):
        """Spec 3: Raw model predict == sklearn model predict"""
        if not SKLEARN_AVAILABLE:
            self.skipTest("sklearn not available")
        
        # Train sklearn model
        sklearn_rf = RandomForestClassifier(n_estimators=2, max_depth=2, random_state=42)
        sklearn_rf.fit(self.X, self.y)
        sklearn_pred = sklearn_rf.predict(self.X)
        sklearn_proba = sklearn_rf.predict_proba(self.X)
        
        # Export to JSON and load into raw model
        from own_tools.models.sklearn_exporter import export_sklearn_rf_to_json
        from own_tools.models.random_forest import RandomForest
        
        json_str = export_sklearn_rf_to_json(sklearn_rf)
        raw_rf = RandomForest.from_json(json_str)
        raw_pred = raw_rf.predict(self.X)
        raw_proba = raw_rf.predict_proba(self.X)
        
        # Print actual predictions for verification
        print(f"\nActual y:           {self.y}")
        print(f"Sklearn predict:    {sklearn_pred}")
        print(f"Raw predict:        {raw_pred}")
        print(f"Predict match:      {np.array_equal(sklearn_pred, raw_pred)}")
        
        print(f"\nSklearn predict_proba:")
        for i, proba in enumerate(sklearn_proba):
            print(f"  Sample {i}: [{proba[0]:.6f}, {proba[1]:.6f}]")
        
        print(f"\nRaw predict_proba:")
        for i, proba in enumerate(raw_proba):
            print(f"  Sample {i}: [{proba[0]:.6f}, {proba[1]:.6f}]")
        
        print(f"\nProba match:        {np.allclose(sklearn_proba, raw_proba, atol=1e-10)}")
        print(f"Max proba diff:     {np.max(np.abs(sklearn_proba - raw_proba)):.12f}")
        
        # Predictions should be identical
        np.testing.assert_array_equal(sklearn_pred, raw_pred, 
            "Raw model predictions must match sklearn exactly")
        
        # Probabilities should be very close
        np.testing.assert_allclose(sklearn_proba, raw_proba, atol=1e-10,
            err_msg="Raw model probabilities must match sklearn closely")


def run_tests():
    """Run all tests"""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    run_tests()