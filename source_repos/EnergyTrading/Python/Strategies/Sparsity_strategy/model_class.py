import abc
import numpy as np
import pandas as pd
import json
from xgboost import XGBClassifier
import xgboost as xgb
from sklearn.metrics import confusion_matrix
import networkx as nx
import daft
import arviz as az
import json

az.rcParams["stats.hdi_prob"] = 0.89  # sets default credible interval used by arviz

# local packages
from Math.accumfeatures import MSTD, MA, EMA
from Math.lm_class import kalman

def thold_function(array, thold_for, thold_against):
    new_array = np.array(array)/sum(array)
    best, sbest = sorted([(v, i) for i, v in enumerate(new_array)], reverse=True)[:2]
    b_sb_diff = best[0] - sbest[0]
    return best[1] if (array[best[1]] > thold_for) and (b_sb_diff > thold_against) else 1
    
def long_short(array, thold_for, thold_against):
    # Only consider array[0] and array[2]
    values = [array[0], array[2]]
    best, sbest = sorted([(v, i) for i, v in enumerate(values)], reverse=True)[:2]
    b_sb_diff = best[0] - sbest[0]
    
    # Return the index (0 or 2) based on the thresholds
    return best[1] * 2 if (array[best[1] * 2] > thold_for) and (b_sb_diff > thold_against) else 1

#TODO: 
# [{k: list(v.keys())} for k,v in data_set_dict.items()] 
# transform into list of dictionary with keys [X_train, y_train, X_test, y_test]
# it has to be dataframe which contains feature columns\
class ModelClass(metaclass=abc.ABCMeta):

    def __init__(self, features=None, target=None, dataset_length=None):
        self.features = features
        self.target = target
        self.model = None
        self.model_raw = None
        # confusion matrices list
        if dataset_length:
            self.cms_list = [None] * dataset_length
    
    def load_model(self, config_model_dict, data_set_shape):
        # Initialize features, target, and dataset length using the config
        self.features = config_model_dict['features']
        self.target = config_model_dict['target']
        self.cms_list = [None] * data_set_shape  # Set up confusion matrix using dataset shape
        # Allow child classes to define the model-specific part
        self.initialize_model(config_model_dict)
    
    @abc.abstractmethod
    def initialize_model(self, config):
        """This method will be overridden in the child class to set the self.model"""
        pass

    @abc.abstractmethod
    def load_model_raw(self):
        pass

    @abc.abstractmethod
    def fit(self, X, y):
        pass

    @abc.abstractmethod    
    def predict_raw(self, X):
        pass

    @abc.abstractmethod
    def predict(self, X):
        pass

    @abc.abstractmethod
    def feature_importance(self):
        pass

    def check_input(self, X):
        pass

    def get_train_statistics(self, X_train, y_train):
        pass

    def get_test_statistics(self, X_test, y_test):
        pass

    def _calc_two_out_hdi(self, df_res):
        """Gives high density interval for df_res dataframe sampling it repeatedly with 2 out principle.

        Args:
            df_res (DataFrame): dataframe with result of train or test confusion matrix columns

        Returns:
            np.array: return np.array with shape (2,)
        """
        hdi = az.hdi(np.array([self._l_precision(df_res.sample(df_res.shape[0]-2)) for _ in range(100)]))
        return hdi
    
    def _calc_confusion_matrix(self, true_targets, preds):
        labels = [0, 1, 2] if self.target == 'y_comb' else [0, 1]
        return confusion_matrix(true_targets, preds, labels=labels)

    @staticmethod
    def _l_precision(df):
        return df['count_wp'].sum()/df['count'].sum()
    
    
    @classmethod
    def from_config(cls, config, data_set_shape):
        # Create an instance of the class
        instance = cls()
        # Call the load_model method to initialize it using the config
        instance.load_model(config, data_set_shape)
        return instance


class ClassifierXgb(ModelClass):
    # define model targets
    # define model hierarchy
    # input model config
    def initialize_model(self, config_model_dict):
        # Child-specific logic for AnotherModel
        config = config_model_dict['config']
        self.model = XGBClassifier(
            objective='binary:logistic', 
            max_depth=config['max_depth'], 
            n_estimators=config['n_estimators'], 
            subsample=config.get('subsample', 1), 
            colsample_bytree=config.get('colsample', 1), 
            gamma=config.get('gamma', 0), 
            min_child_weight=config.get('min_ch', 0), 
            reg_lambda=config.get('lambda', 0), 
            reg_alpha=config.get('alfa', 0), 
            learning_rate=config.get('learning_rate', 0.3),
            scale_pos_weight=config.get('scale_pos_weight', 1))

    @classmethod   
    def load_model_raw(cls, path):
        raw_xgb = cls()
        with open(path, 'r') as f:
            raw_xgb.raw_model = json.load(f)
        return raw_xgb
    
    def export_model_raw(self, name):
        filename = f"{name}.json"
        self.model.save_model(filename)
        print("Model saved into", filename)
        return filename

    def fit(self, X, y):
        if hasattr(self.model, 'fit'):
            # If self.model has a fit method, proceed to use it
            if isinstance(X, pd.DataFrame):
                self.model.fit(X[self.features], y[self.target])
            else:
                self.model.fit(X, y[self.target])
        else:
            raise AttributeError(f"The model {self.model} does not have a 'fit' method")

    def feature_importance(self):
        if hasattr(self.model, 'feature_importances_'):
            # If self.model has a fit method, proceed to use it
            return self.model.feature_importances_
        else:
            raise AttributeError(f"The model {self.model} does not have a 'feature_importances_' method")

    
    def get_train_statistics(self, X_train, y_train):
        pass

    def get_test_statistics(self, X_test, y_test):
        pass

    def predict_raw(self, X):
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
                tree_contribution = predict_single_tree(tree, features)
                logits += tree_contribution
            # Apply sigmoid to convert logits to probability
            probability = sigmoid(logits)
            return probability
        if self.raw_model:
            raw_feat_len = len(self.raw_model['learner']['feature_names'])
            if raw_feat_len != len(X):
                raise ValueError(f"Features shape mismatch model_{raw_feat_len}/ input_{len(X)}")
            return predict_ensemble(self.raw_model, X)
        else:
            raise ValueError("Raw model is not loaded")

    def predict(self, X):
        if isinstance(X, pd.DataFrame):
            preds = self.model.predict_proba(X[self.features])[:, 1]
        else:
            preds = self.model.predict_proba(X)[:, 1]
        return preds

class HierarchyModel():
    """_summary_
        1. load hierarchy from dag and mappings
        2. d
    Raises:
        ValueError: _description_
        AssertionError: _description_

    Returns:
        _type_: _description_
    """
    MODEL_MAPPINGS_ = {
        'xgb': ClassifierXgb,
    }
    OUTPUT_FUNC_MAPPINGS_ = {
        'thold_func': long_short,
        # 'long_short_func': long_short
    }
    def __init__(self):
        self.input_layer = None
        self.model_layer = {}
        self.output_layer = {}
        self.model_outputs = {} #TODO: reset probably
        self.dag = None
        self.coordinates = {}
        self.loaded_raw = False

    def load_hierarchy(self, dag: nx.DiGraph, config_models_dict: dict, data_set_shape, draw=False):
        self.dag = dag
        self._assert_all_nodes_have_func_name(self.dag)
        assert all([self.dag.nodes[model]['func_name'] in self.MODEL_MAPPINGS_ or 
                    self.dag.nodes[model]['func_name'] in self.OUTPUT_FUNC_MAPPINGS_ 
                    for model in list(self.dag.nodes)]), "Some of the model(s) are not mapped."
        
        self.model_layer = {model_name: self.MODEL_MAPPINGS_[self.dag.nodes[model_name]['func_name']].from_config(
            config_models_dict[model_name],
            data_set_shape
        ) for model_name in self._dag_sort if self.dag.nodes[model_name]['func_name'] in self.MODEL_MAPPINGS_}

        last_node = self._dag_sort[-1]
        self.output_layer = {
            'name': last_node,
            'func': self.OUTPUT_FUNC_MAPPINGS_[last_node],
            'args': config_models_dict[last_node]['args'],
            'kwargs': config_models_dict[last_node]['kwargs']
        }
        if self.output_layer == {}:
            raise ValueError(f"Last node in the dag is not represented in OUTPUT_FUNC_MAPPINGS_")
        
        self._generate_coordinates()
        if draw:
            self.draw_dag()
    
    def load_raw(self, hierarchy_path):
        self.loaded_raw = True
        with open(hierarchy_path, 'r') as f:
            hierarchy_dict = json.load(f)
        self.dag = CustomDAG.from_dict(hierarchy_dict['dag_structure'])
        for model, model_path in hierarchy_dict['models_layer'].items():
            self.model_layer[model] = self.MODEL_MAPPINGS_[
                self.dag[model]['func_name']].load_model_raw(model_path)
        

    def call_output_function(self, X):
        func = self.output_layer['func']
        args = self.output_layer['args']
        kwargs = self.output_layer['kwargs']
        return np.array([func(row, *args, **kwargs) for row in X])

    def export_hierarchy(self):
        #
        result = {
            "dag_structure": {
                'nodes': list(self.dag.nodes),
                'edges': list(self.dag.edges),
                'attributes': {x: {'func_name': self.dag.nodes[x]['func_name']} for x in self.dag.nodes}
            },
            "models_layer": {
                k: model.export_model_raw(k) for k, model in self.model_layer.items()
            }
        }
        filename = "hierarchy_dump.json"
        with open(filename, 'w') as f:
            json.dump(result, f)
        print("Hierarchy saved into", filename)

    def predict_raw(self):
        pass

    def predict(self, X):
        outputs = {}
        # Loop through the topologically sorted nodes and run each corresponding model function
        for node in self._dag_sort:
            if node not in self.model_layer.keys():
                parent_outputs = [outputs[parent] for parent in self.dag.predecessors(node)]
                stack = np.stack(parent_outputs, axis=1)
                outputs[node] = self.call_output_function(stack)
                break
            # If the node has parents, gather their outputs and pass to the model function
            if list(self.dag.predecessors(node)):
                parent_outputs = [outputs[parent] for parent in self.dag.predecessors(node)]
                stack = np.stack(parent_outputs, axis=1)
                outputs[node] = self.model_layer[node].predict(stack)
            else:
                temp_preds = self.model_layer[node].predict(X)
                outputs[node] = temp_preds

        self.model_outputs = outputs
        return outputs[self.output_layer['name']]

    def fit(self, data_train):
        X_train = data_train['X_train']
        y_train = data_train['y_train']
        # Dictionary to store the outputs of each node
        outputs = {}
        # Loop through the topologically sorted nodes and run each corresponding model function
        for node in self._dag_sort:
            if node not in self.model_layer.keys():
                continue
            # If the node has parents, gather their outputs and pass to the model function
            if list(self.dag.predecessors(node)):
                parent_outputs = [outputs[parent] for parent in self.dag.predecessors(node)]
                stack = np.stack(parent_outputs, axis=1)
                self.model_layer[node].fit(stack, y_train)
                outputs[node] = self.model_layer[node].predict(stack)
            else:
                self.model_layer[node].fit(X_train, y_train)  # For nodes without parents
                outputs[node] = self.model_layer[node].predict(X_train)


    @staticmethod
    def _assert_all_nodes_have_func_name(dag):
        # Check all nodes in the graph
        for node, data in dag.nodes(data=True):
            # Assert that the 'func_name' attribute is defined for each node
            assert 'func_name' in data, f"Node {node} does not have a 'func_name' attribute"

    
    @property
    def _dag_sort(self):
        if not isinstance(self.dag, nx.DiGraph):
            raise AssertionError(f"{self.__class__} attribute self.dag has not loaded graph ")
        return list(nx.topological_sort(self.dag))
    
    def _generate_coordinates(self):
        # Topologically sort the nodes to respect dependencies
        sorted_nodes = self._dag_sort
        
        # Dictionary to store y-level of each node
        layer_map = {}
        # Dictionary to store x, y coordinates
        coordinates = {}
        
        # Track which nodes are on each y-level
        layer_nodes = {}
        
        # Assign layers (y-level) based on dependencies
        for node in sorted_nodes:
            # Get the maximum y-level of its predecessors
            predecessors = list(self.dag.predecessors(node))
            if predecessors:
                max_layer = max(layer_map[predecessor] for predecessor in predecessors)
                layer = max_layer + 1
            else:
                # No predecessors, place on layer 0
                layer = 0
            
            # Update layer_map and track nodes on this layer
            layer_map[node] = layer
            if layer not in layer_nodes:
                layer_nodes[layer] = []
            layer_nodes[layer].append(node)
        
        # Assign x-coordinates based on the number of nodes in each layer
        for layer, nodes in layer_nodes.items():
            n = len(nodes)
            x_positions = np.linspace(0, n-1, n)  # Evenly space nodes in the layer
            for i, node in enumerate(nodes):
                coordinates[node] = (x_positions[i], -layer)  # y = -layer to invert y-axis for drawing
        
        self.coordinates = coordinates
    
    def draw_dag(self):
        pgm = daft.PGM()
        for node in self.dag.nodes:
            pgm.add_node(node, node, *self.coordinates[node])
        for edge in self.dag.edges:
            pgm.add_edge(*edge)
        pgm.render()



class CustomDAG:
    def __init__(self):
        # Store graph as adjacency list, where key is the node and value is a list of child nodes
        self.adjacency_list = {}
        self.node_attributes = {}  # Dictionary to store node attributes

    def __getitem__(self, node):
        # Allow attribute access with `[]` syntax, similar to networkx
        if node in self.node_attributes:
            return self.node_attributes[node]
        else:
            raise KeyError(f"Node '{node}' not found in the DAG.")

    def add_node(self, node, **attributes):
        # Add a new node if it doesn't already exist
        if node not in self.adjacency_list:
            self.adjacency_list[node] = []
        # Store node attributes
        if node not in self.node_attributes:
            self.node_attributes[node] = attributes
        else:
            self.node_attributes[node].update(attributes)

    def add_edge(self, from_node, to_node):
        # Add an edge from `from_node` to `to_node`
        if from_node not in self.adjacency_list:
            self.add_node(from_node)
        if to_node not in self.adjacency_list:
            self.add_node(to_node)
        self.adjacency_list[from_node].append(to_node)

    def get_children(self, node):
        # Return children of the given node
        return self.adjacency_list.get(node, [])

    def get_parents(self, node):
        # Return parents of the given node
        parents = [n for n, children in self.adjacency_list.items() if node in children]
        return parents

    def topological_sort(self):
        # Perform topological sort of the nodes
        visited = set()
        stack = []

        def dfs(node):
            if node in visited:
                return
            visited.add(node)
            for child in self.get_children(node):
                dfs(child)
            stack.append(node)

        for node in self.adjacency_list:
            if node not in visited:
                dfs(node)

        return stack[::-1]  # Reverse the stack to get the topological order

    @classmethod
    def from_dict(cls, dag_structure):
        # Create an instance of CustomDAG from JSON data
        custom_dag = cls()
        for node in dag_structure['nodes']:
            attributes = dag_structure['attributes'][node]
            custom_dag.add_node(node, **attributes)
        for from_node, to_node in dag_structure['edges']:
            custom_dag.add_edge(from_node, to_node)
        return custom_dag
