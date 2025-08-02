# -*- coding: utf-8 -*-
"""
Created on Thu May 28 14:46:39 2020

@author: zelenaymar
"""

import abc
import numpy as np
import pandas as pd
import os
import pickle
from copy import deepcopy
from datetime import datetime
# from sklearn2pmml import sklearn2pmml
# from sklearn2pmml.pipeline import PMMLPipeline
# from sklearn.inspection import plot_partial_dependence, permutation_importance
# from sklearn.metrics import confusion_matrix, classification_report, accuracy_score


PATH = '//X:/Strategies/Models/Export/'


class AlgoModelOB():
    __metaclass__ = abc.ABCMeta

    def __init__(self):
        self.model_dict = dict()
        # self.weights = []
        # self.__check()
        self.class_nums = 0
        self.classifier = None
        self.classes = []

    @property
    def model_num(self):
        return len(self.names)

    @property
    def names(self):
        return [m.name for m in self.model_dict.values()]

    @property
    def weights(self):
        w = [m.weight for m in self.model_dict.values()]
        return [val / sum(w) for val in w]

    @property
    def single_model_class(self):
        return False

    @abc.abstractmethod
    def train(self, X_train, Y_train, Z_train=None):
        for m in self.model_dict.values():
            m.train(X_train, Y_train, Z_train)

    @abc.abstractmethod
    def prepare_data(self, data_dict):
        pass

    @abc.abstractmethod
    def predict(self, X_tests, Z_tests=None):
        self.__check()
        pred_class = np.zeros((X_tests.shape[0],))
        pred_probs = np.zeros((X_tests.shape[0], self.class_nums))
        for m, w in zip(self.model_dict.values(), self.weights):
            aux_class, aux_probs, _, _ = m.predict_all(X_tests, Z_tests)
            pred_class += aux_class * w
            pred_probs += aux_probs * w
        # idx_class = np.argmax(pred_probs, axis=1)
        if self.classifier:
            pred_class = [self.classes[i] for i in np.argmax(pred_probs, axis=1)]
        pred_class = np.array(pred_class)
        # pred_class = np.argmax(pred_probs, axis=1) - 1
        return pred_class, pred_probs

    @abc.abstractmethod
    def score(self, X, y, sample_weight=None):
        # Scoring of models for CV
        score_ = 0
        for m, w in zip(self.model_dict.values(), self.weights):
            score_aux = m.score(X, y, sample_weight=sample_weight)
            score_ += score_aux * w
        return score_

    def fit(self, X_train, Y_train, Z_train=None):
        return self.train(X_train, Y_train, Z_train)

    def print_results(self, Y_true, Y_pred, Z=None):
        if Z is None:
            Z = np.zeros(Y_true.shape[0])
            n_states = 1
        else:
            n_list = [len(m[k].keys()) for m, k in self.model_dict.items()]
            n_states = max(n_list)
        Y_true = {k: Y_true[Z == k] for k in range(0, n_states)}
        Y_pred = {k: Y_pred[Z == k] for k in range(0, n_states)}
        c_mat = {k: [] for k in range(0, n_states)}
        c_rep = {k: [] for k in range(0, n_states)}
        print('Model %s statistics...' % 'Swarm')
        for k in range(0, n_states):
            c_mat[k] = confusion_matrix(Y_true[k], Y_pred[k])
            c_rep[k] = classification_report(Y_true[k], Y_pred[k])
            print('Result in state %d' % k)
            print(c_mat[k])
            print(c_rep[k])
            print(' \n')
        return c_mat, c_rep

    def __check(self):
        if not self.classifier:
            return 0
        l_class = []
        [l_class.extend(m.class_list) for m in self.model_dict.values()]
        n_class = [len(m.class_list) for m in self.model_dict.values()]
        n_class = set(n_class).pop()
        a_class = set(l_class)
        if len(a_class) != n_class:
            raise ValueError('Inconsistent number of classes across models.')
        else:
            self.class_nums = n_class
            self.classes = l_class[:n_class]
        return 0

    def add_model(self, model_class):
        name_aux = self.names
        if model_class.single_model_class is True:
            name_aux.append(model_class.name)
        else:
            name_aux.extend(model_class.names)
        model_names = set(name_aux)
        if len(model_names) != self.model_num + model_class.model_num:
            raise ValueError('Duplicit names, merge not successfull. \n')
        if self.classifier is None:
            self.classifier = model_class.classifier
        else:
            if self.classifier is model_class.classifier:
                pass
            else:
                raise ValueError('Mixing classifiers with estimators. \n')
        if model_class.single_model_class is True:
            self.model_dict[model_class.name] = model_class
        else:
            self.model_dict = {**self.model_dict, **model_class.model_dict}
        # self.weights.extend(model_class.weight)
        self.__check()
        return 0

    def remove_model(self, names):
        # self.weights = [w for w, n in zip(self.weights, self.name)
        #                 if n not in names]
        [self.model_dict.pop(k) for k in names]
        return 0

    def feature_importances(self, state=None):
        I_list = [self.model_dict[k].feature_importances(state)
                  for k in self.names if k not in ['svc']]            
        fi_mat = np.concatenate(I_list, axis=1)
        w_vec = np.array([w for w, k in zip(self.weights, self.names)
                          if k not in ['svc']]).reshape((-1, 1))
        w_vec /= np.sum(w_vec)
        return fi_mat.dot(w_vec).reshape((-1,))

    def permutation_importances(self, X, y, state=None, n=5):
        I_list = [self.model_dict[k].permutation_importances(state)
                  for k in self.names]            
        fi_mat = np.concatenate(I_list, axis=1)
        w_vec = np.array([w for w, k in zip(self.weights, self.names)
                          if k not in ['svc']]).reshape((-1, 1))
        w_vec /= np.sum(w_vec)
        return fi_mat.dot(w_vec).reshape((-1,))

    def select_variables(self, impact_arr, pred_vars, best_n=[], thres=1):
        # Variables Selection
        n = len(pred_vars)
        if not best_n:
            best_n = n
        idx_sort = np.argsort(impact_arr)[::-1]
        imp_sort = [impact_arr[i] for i in idx_sort]
        imp_cums = np.cumsum(imp_sort)
        prd_sort = [pred_vars[i] for i in idx_sort]
        # Selected variables by best n
        out_var1 = [prd_sort[i] for i in range(0, best_n)]
        # Selected variables by prediction power
        out_var2 = [prd_sort[i] for i, c in enumerate(imp_cums) if c <= thres]
        if len(out_var1) <= len(out_var2):
            out_vars = out_var1
        else:
            out_vars = out_var2
        out_cums = imp_cums[len(out_vars) - 1]
        return out_vars, out_cums

    def export2file(self, name=[], date=None, path=None, toJava=True, state=None,
                    target=None):
        [self.model_dict[k].export2file(name, date, path, toJava, state, target)
         for k in self.names]
        return 0

pass
class DataModelReg(AlgoModelOB):
    # Regression model
    def __init__(self, model=None, model_name='', weight=1, states=1):
        model_class = model.__class__
        model_params = model.get_params(deep=False)
        self.model = {k: model_class(**model_params) for k in range(0, states)}
        self.weight = weight
        self.name = model_name
        self.__status = 0

    @property
    def single_model_class(self):
        return True

    @property
    def classifier(self):
        return False

    @property
    def model_num(self):
        return 1

    def train(self, X_train, Y_train, Z_train=None):
        # Training of single model
        if Z_train is None:
            Z_train = np.zeros(Y_train.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        X_train = {k: X_train[Z_train == k, :] for k in range(0, n_states)}
        Y_train = {k: Y_train[Z_train == k] for k in range(0, n_states)}
        print('Model %s in training...' % self.name)
        for k in range(0, n_states):
            self.model[k].fit(X_train[k], Y_train[k])
        self.__status = 1
        print('Model %s trained successfully.' % self.name)
        return 0

    def predict(self, X_tests, Z_tests=None):
        Y_pred, _, _, _ = self.predict_all(X_tests, Z_tests)
        return Y_pred

    def predict_all(self, X_tests, Z_tests=None):
        # Prediction of single model
        if self.__status == 0:
            raise ValueError('Model %s NOT trained. \n' % self.name)
        if Z_tests is None:
            Z_tests = np.zeros(X_tests.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        # Inputs
        X_tests = {k: X_tests[Z_tests == k, :] for k in range(0, n_states)}
        # Outputs
        Y_pred_dict = {k: [] for k in range(0, n_states)}
        for k in range(0, n_states):
            Y_pred_dict[k] = self.model[k].predict(X_tests[k])
        Y_pred = []
        count = {k: 0 for k in range(0, n_states)}
        for k in Z_tests:
            Y_pred.append(Y_pred_dict[k][count[k]])
            count[k] += 1
        del count
        Y_pred = np.array(Y_pred)
        return Y_pred, Y_pred, Y_pred_dict, Y_pred_dict

    def score(self, X, y, sample_weight=None):
        Z_tests = np.zeros(X.shape[0])
        n_states = 1
        # Inputs
        X_tests = {k: X[Z_tests == k, :] for k in range(0, n_states)}
        Y_tests = {k: y[Z_tests == k] for k in range(0, n_states)}
        score_ = 0
        for k in range(0, n_states):
            score_ += self.model[k].score(X_tests[k], Y_tests[k], sample_weight)
        return score_ / n_states

    def get_params(self, deep=True):
        c = self.__classes[0]
        output_dict = {}
        output_dict['model'] = self.model[0]
        output_dict['model_name'] = self.name
        output_dict['weight'] = self.weight
        output_dict['states'] = 1
        return output_dict

    def set_params(self, **params):
        self.model[0].set_params(**params)
        return self

    def feature_importances(self, state=None):
        # Calculates feature importances of model
        if state is None:
            state = list(self.model.keys())
        m = self.model
        try:
            I_list = [m[k].feature_importances_ for k in state]
        except(AttributeError):
            I_list = []
            for k in state:
                sel_vec = m[k]['feature_selection'].get_support()
                ftr_vec = m[k]['regression'].feature_importances_
                aux_vec = np.zeros((len(sel_vec),))
                aux_vec[sel_vec] = ftr_vec
                I_list.append(aux_vec)
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def permutation_importance(self, X, y, state=None, target=None, n=5):
        # Calculates permutation feature importances of model
        if state is None:
            state = list(self.model.keys())
        m = self.model
        I_list = [permutation_importance(m[k], X, y, n_repeats=n, n_jobs=-1)
                  for k in state]
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def export2file(self, name=[], date=None, path=None, toJava=True, state=None,
                    target=None):
        # Exports models for Java
        if date is None:
            date = datetime.today()
        if path is None:
            path = PATH
        if state is None:
            state = list(self.model.keys())
        # Make directory
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        try:
            os.makedirs(path)
        except(OSError):
            pass
        m = self.model
        # Create pipeline
        for k in state:
            file = self.name + '_' + '{:02}'.format(k)
            if toJava:
                file += '.pmml'
                pipeline = PMMLPipeline([("estimator", m[k])])
                sklearn2pmml(pipeline, path + file, with_repr=True, debug=False)
            else:
                file += '.sav'
                pickle.dump(m[k], open(path + file, 'wb'))
        return 0

    def import_model(self, name, date, path=None, target=None):
        # Import models from file
        states = list(self.model.keys())
        if path is None:
            path = PATH
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        for k in states:
            file = self.name + '_' + '{:02}'.format(k) + '.sav'
            file_name = path + file
            self.model[k] = pickle.load(open(file_name, 'rb'))
        self.__status = 1
        return 0


class DataModelMulti(AlgoModelOB):
    # Single model multi class
    def __init__(self, model=None, model_name='', weight=1, states=1):
        model_class = model.__class__
        model_params = model.get_params(deep=False)
        self.model = {k: model_class(**model_params) for k in range(0, states)}
        self.weight = weight
        self.name = model_name
        self.__classes = 0
        self.__status = 0

    @property
    def single_model_class(self):
        return True

    @property
    def classifier(self):
        return True

    @property
    def model_num(self):
        return 1

    @property
    def class_list(self):
        return self.__classes

    def train(self, X_train, Y_train, Z_train=None):
        # Training of single model
        if Z_train is None:
            Z_train = np.zeros(Y_train.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        self.__class_num = list(np.unique(Y_train))
        X_train = {k: X_train[Z_train == k, :] for k in range(0, n_states)}
        Y_train = {k: Y_train[Z_train == k] for k in range(0, n_states)}
        print('Model %s in training...' % self.name)
        for k in range(0, n_states):
            self.model[k].fit(X_train[k], Y_train[k])
        self.__status = 1
        print('Model %s trained successfully.' % self.name)
        return 0

    def predict(self, X_tests, Z_tests=None):
        Y_pred, _, _, _ = self.predict_all(X_tests, Z_tests)
        return Y_pred

    def predict_proba(self, X_tests, Z_tests=None):
        _, Y_prob, _, _ = self.predict_all(X_tests, Z_tests)
        return Y_prob
    
    def predict_all(self, X_tests, Z_tests=None):
        # Prediction of single model
        if self.__status == 0:
            raise ValueError('Model %s NOT trained. \n' % self.name)
        if Z_tests is None:
            Z_tests = np.zeros(X_tests.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        # Inputs
        X_tests = {k: X_tests[Z_tests == k, :] for k in range(0, n_states)}
        # Outputs
        Y_pred_dict = {k: [] for k in range(0, n_states)}
        Y_prob_dict = {k: [] for k in range(0, n_states)}
        for k in range(0, n_states):
            Y_pred_dict[k] = self.model[k].predict(X_tests[k])
            Y_prob_dict[k] = self.model[k].predict_proba(X_tests[k])
        Y_pred = []
        Y_prob = []
        count = {k: 0 for k in range(0, n_states)}
        for k in Z_tests:
            Y_pred.append(Y_pred_dict[k][count[k]])
            Y_prob.append(Y_prob_dict[k][count[k], :])
            count[k] += 1
        del count
        Y_pred = np.array(Y_pred)
        Y_prob = np.array(Y_prob)
        return Y_pred, Y_prob, Y_pred_dict, Y_prob_dict

    def score(self, X, y, sample_weight=None):
        Z_tests = np.zeros(X.shape[0])
        n_states = 1
        # Inputs
        X_tests = {k: X[Z_tests == k, :] for k in range(0, n_states)}
        Y_tests = {k: y[Z_tests == k] for k in range(0, n_states)}
        score_ = 0
        for k in range(0, n_states):
            score_ += self.model[k].score(X_tests[k], Y_tests[k], sample_weight)
        return score_ / n_states

    def get_params(self, deep=True):
        c = self.__classes[0]
        output_dict = {}
        output_dict['classes'] = self.__classes
        output_dict['model'] = self.model[0]
        output_dict['model_name'] = self.name
        output_dict['weight'] = self.weight
        output_dict['states'] = 1
        return output_dict

    def set_params(self, **params):
        self.model[0].set_params(**params)
        return self

    def print_results(self, Y_true, Y_pred, Z=None):
        # Print Accuracy & model stats
        if self.__status == 0:
            raise ValueError('Model %s NOT trained. \n' % self.name)
        if Z is None:
            Z = np.zeros(Y_true.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        Y_true = {k: Y_true[Z == k] for k in range(0, n_states)}
        Y_pred = {k: Y_pred[Z == k] for k in range(0, n_states)}
        c_mat = {k: [] for k in range(0, n_states)}
        c_rep = {k: [] for k in range(0, n_states)}
        print('Model %s statistics...' % 'Swarm')
        for k in range(0, n_states):
            c_mat[k] = confusion_matrix(Y_true[k], Y_pred[k])
            c_rep[k] = classification_report(Y_true[k], Y_pred[k])
            print('Result in state %d' % k)
            print(c_mat[k])
            print(c_rep[k])
            print(' \n')
        return c_mat, c_rep

    def plot_pd(self, X, target, pred_vars, features, state=0):
        # Partial dependence plot
        X = pd.DataFrame(X, columns=pred_vars)
        plot_partial_dependence(self.model[state], X, features, target=target)
        return 0

    def feature_importances(self, state=None):
        # Calculates feature importances of model
        if state is None:
            state = list(self.model.keys())
        m = self.model
        try:
            I_list = [m[k].feature_importances_ for k in state]
        except(AttributeError):
            I_list = []
            for k in state:
                sel_vec = m[k]['feature_selection'].get_support()
                ftr_vec = m[k]['classification'].feature_importances_
                aux_vec = np.zeros((len(sel_vec),))
                aux_vec[sel_vec] = ftr_vec
                I_list.append(aux_vec)
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def permutation_importance(self, X, y, state=None, target=None, n=5):
        # Calculates permutation feature importances of model
        if state is None:
            state = list(self.model.keys())
        m = self.model
        I_list = [permutation_importance(m[k], X, y, n_repeats=n, n_jobs=-1)
                  for k in state]
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def export2file(self, name=[], date=None, path=None, toJava=True, state=None,
                    target=None):
        # Exports models for Java
        if date is None:
            date = datetime.today()
        if path is None:
            path = PATH
        if state is None:
            state = list(self.model.keys())
        # Make directory
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        try:
            os.makedirs(path)
        except(OSError):
            pass
        m = self.model
        # Create pipeline
        for k in state:
            file = self.name + '_' + '{:02}'.format(k)
            if toJava:
                file += '.pmml'
                pipeline = PMMLPipeline([("classifier", m[k])])
                sklearn2pmml(pipeline, path + file, with_repr=True, debug=False)
            else:
                file += '.sav'
                pickle.dump(m[k], open(path + file, 'wb'))
        return 0

    def import_model(self, name, date, path=None, target=None):
        # Import models from file
        states = list(self.model.keys())
        if path is None:
            path = PATH
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        for k in states:
            file = self.name + '_' + '{:02}'.format(k) + '.sav'
            file_name = path + file
            self.model[k] = pickle.load(open(file_name, 'rb'))
        self.__status = 1
        return 0


class DataModelBi(AlgoModelOB):
    # Single model binomial class one against all
    def __init__(self, model=None, model_name='', classes=[], weight=1, states=1):
        model_class = model.__class__
        model_params = model.get_params(deep=False)
        self.model = {k: {c: model_class(**model_params) for c in classes}
                      for k in range(0, states)}
        self.weight = weight
        self.name = model_name
        self.__classes = classes
        self.__status = 0

    @property
    def single_model_class(self):
        return True

    @property
    def classifier(self):
        return True

    @property
    def model_num(self):
        return 1

    @property
    def class_list(self):
        return self.__classes

    def train(self, X_train, Y_train, Z_train=None):
        # Training of single model
        if Z_train is None:
            Z_train = np.zeros(Y_train.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        # 
        Y_train_ = {c: np.array([1 if x == c else -1 for x in Y_train])
                    for c in self.__classes}
        X_train = {k: X_train[Z_train == k, :] for k in range(0, n_states)}
        Y_train = {k: {c: Y_train_[c][Z_train == k] for c in self.__classes}
                   for k in range(0, n_states)}
        print('Model %s in training...' % self.name)
        [self.model[k][c].fit(X_train[k], Y_train[k][c]) for k in range(0, n_states)
         for c in self.__classes]
        self.__status = 1
        print('Model %s trained successfully.' % self.name)
        return 0

    def predict(self, X_tests, Z_tests=None):
        Y_pred, _, _, _ = self.predict_all(X_tests, Z_tests)
        return Y_pred

    def predict_proba(self, X_tests, Z_tests=None):
        _, Y_prob, _, _ = self.predict_all(X_tests, Z_tests)
        return Y_prob

    def predict_all(self, X_tests, Z_tests=None):
        # Prediction of single model
        if self.__status == 0:
            raise ValueError('Model %s NOT trained. \n' % self.name)
        if Z_tests is None:
            Z_tests = np.zeros(X_tests.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        # Inputs
        X_tests = {k: X_tests[Z_tests == k, :] for k in range(0, n_states)}
        # Outputs
        Y_pred_dict = {k: [] for k in range(0, n_states)}
        Y_prob_dict = {k: [] for k in range(0, n_states)}
        for k in range(0, n_states):
            prob_list = []
            for c in self.__classes:
                p_aux = self.model[k][c].predict_proba(X_tests[k])
                prob_list.append(p_aux[:, 1])
            prob_mat = np.concatenate([x.reshape((-1, 1)) for x in prob_list],
                                       axis=1)
            # prob_mat /= np.sum(prob_mat, axis=1).reshape((-1, 1))
            class_l = [self.__classes[i] for i in np.argmax(prob_mat, axis=1)]
            Y_pred_dict[k] = np.array(class_l)
            Y_prob_dict[k] = prob_mat
            del prob_list, prob_mat, class_l
        Y_pred = []
        Y_prob = []
        count = {k: 0 for k in range(0, n_states)}
        for k in Z_tests:
            Y_pred.append(Y_pred_dict[k][count[k]])
            Y_prob.append(Y_prob_dict[k][count[k], :])
            count[k] += 1
        del count
        Y_pred = np.array(Y_pred)
        Y_prob = np.array(Y_prob)
        return Y_pred, Y_prob, Y_pred_dict, Y_prob_dict

    def score(self, X, y, sample_weight=None):
        Z_tests = np.zeros(X.shape[0])
        n_states = 1
        # Inputs
        X_tests = {k: X[Z_tests == k, :] for k in range(0, n_states)}
        Y_tests = {k: y[Z_tests == k] for k in range(0, n_states)}
        # Output
        score_ = 0
        for k in range(0, n_states):
            prob_list = []
            for c in self.__classes:
                p_aux = self.model[k][c].predict_proba(X_tests[k])
                prob_list.append(p_aux[:, 1])
            prob_mat = np.concatenate([x.reshape((-1, 1)) for x in prob_list],
                                       axis=1)
            # prob_mat /= np.sum(prob_mat, axis=1).reshape((-1, 1))
            class_l = [self.__classes[i] for i in np.argmax(prob_mat, axis=1)]
            Y_preds = np.array(class_l)
            score_ += accuracy_score(Y_tests[k], Y_preds, sample_weight=sample_weight)
            del prob_list, class_l
        return score_ / n_states

    def get_params(self, deep=True):
        c = self.__classes[0]
        output_dict = {}
        output_dict['classes'] = self.__classes
        output_dict['model'] = self.model[0][c]
        output_dict['model_name'] = self.name
        output_dict['weight'] = self.weight
        output_dict['states'] = 1
        return output_dict

    def set_params(self, **params):
        k = 0
        for c in self.__classes:
            self.model[k][c].set_params(**params)
        return self

    def print_results(self, Y_true, Y_pred, Z=None):
        # Print Accuracy & model stats
        if self.__status == 0:
            raise ValueError('Model %s NOT trained. \n' % self.name)
        if Z is None:
            Z = np.zeros(Y_true.shape[0])
            n_states = 1
        else:
            n_states = len(self.model.keys())
        Y_true = {k: Y_true[Z == k] for k in range(0, n_states)}
        Y_pred = {k: Y_pred[Z == k] for k in range(0, n_states)}
        c_mat = {k: [] for k in range(0, n_states)}
        c_rep = {k: [] for k in range(0, n_states)}
        print('Model %s statistics...' % 'Swarm')
        for k in range(0, n_states):
            c_mat[k] = confusion_matrix(Y_true[k], Y_pred[k])
            c_rep[k] = classification_report(Y_true[k], Y_pred[k])
            print('Result in state %d' % k)
            print(c_mat[k])
            print(c_rep[k])
            print(' \n')
        return c_mat, c_rep

    def plot_pd(self, X, target, pred_vars, features, state=0):
        # Partial dependence plot
        X = pd.DataFrame(X, columns=pred_vars)
        plot_partial_dependence(self.model[state][target], X, features,
                                target=1)
        return 0

    def feature_importances(self, state=None, target=None):
        # Calculates feature importances of model
        if state is None:
            state = list(self.model.keys())
        if target is None:
            target = self.__classes
        m = self.model
        try:
            I_list = [m[k][c].feature_importances_ for k in state
                      for c in target]
        except(AttributeError):
            I_list = []
            for k in state:
                for c in target:
                    try:
                        sel_vec = m[k][c]['feature_selection'].get_support()
                        ftr_vec = m[k][c]['classification'].feature_importances_
                        aux_vec = np.zeros((len(sel_vec),))
                        aux_vec[sel_vec] = ftr_vec
                        I_list.append(aux_vec)
                    except(KeyError):
                        # SVC Linear
                        I_list = [m[k][c][self.name].coef_ for k in state
                                  for c in target]
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def permutation_importance(self, X, y, state=None, target=None, n=5):
        # Calculates permutation feature importances of model
        if state is None:
            state = list(self.model.keys())
        if target is None:
            target = self.__classes
        m = self.model
        I_list = [permutation_importance(m[k][c], X, y, n_repeats=n, n_jobs=-1)
                  for k in state for c in target]
        fi_mat = np.concatenate([x.reshape((-1, 1)) for x in I_list], axis=1)
        fi_vec = fi_mat.mean(axis=1).reshape((-1, 1))
        return fi_vec

    def export2file(self, name=[], date=None, path=None, toJava=True, state=None,
                    target=None):
        # Exports models for Java
        if date is None:
            date = datetime.today()
        if path is None:
            path = PATH
        if state is None:
            state = list(self.model.keys())
        if target is None:
            target = self.__classes
        # Make directory
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        try:
            os.makedirs(path)
        except(OSError):
            pass
        m = self.model
        # Create pipeline
        for k in state:
            for c in target:
                k_str = '{:02}'.format(k)
                if c == -1:
                    t_str = 'd'
                elif c == 1:
                    t_str = 'u'
                else:
                    t_str = 'n'
                file = self.name + '_' + k_str + '_' + t_str
                if toJava:
                    file += '.pmml'
                    pipeline = PMMLPipeline([("classifier", m[k][c])])
                    sklearn2pmml(pipeline, path + file, with_repr=True, debug=False)
                else:
                    file += '.sav'
                    pickle.dump(m[k][c], open(path + file, 'wb'))
        return 0

    def import_model(self, name, date, path=None):
        # Import models from file
        states = list(self.model.keys())
        target = self.__classes
        if path is None:
            path = PATH
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        for k in states:
            k_str = '{:02}'.format(k)
            for c in target:
                if c == -1:
                    t_str = 'd'
                elif c == 1:
                    t_str = 'u'
                else:
                    t_str = 'n'
                file = self.name + '_' + k_str + '_' + t_str + '.sav'
                file_name = path + file
                self.model[k][c] = pickle.load(open(file_name, 'rb'))
        self.__status = 1
        return 0


class FeaturesTranslator():
    def __init__(self, class_t, unit_t=1, unit_d=0.01):
        self.path = PATH
        self._tclass = class_t
        self._tunit = unit_t
        self._dunit = unit_d

    def translate(self, input_list, market_list, tenor_list, relative_bool):
        output_list = [self.__translate_single(x, market_list, tenor_list, relative_bool)
                       for x in input_list]
        return output_list

    def export2txt(self, feature_list, file_name, name=[], date=None, path=None):
        # Export features to txt file
        if date is None:
            date = datetime.today()
        if path is None:
            path = self.path
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        try:
            os.makedirs(path)
        except(OSError):
            pass
        # Save to file
        with open(path + file_name + '.txt', 'w') as f:
            f.write( ','.join( feature_list ) )
            f.close()
        return 0

    def export2csv(self, feature_list, file_name, market_list, tenor_list,
                   name=[], date=None, path=None, relative_bool=False):
        # Export features to txt file
        if date is None:
            date = datetime.today()
        if path is None:
            path = self.path
        if not name:
            path += 'Test/'
        else:
            path += date.strftime('%y%m%d') + '/'
            path += name + '/'
        try:
            os.makedirs(path)
        except(OSError):
            pass
        # Replace ncg with the
        market_list = ['the' if x in ['ncg'] else x for x in market_list]
        # Write header
        header_list = ['market', 'instr', 'down', 'neutral', 'up']
        header_list.extend(['x' + str(i + 1) for i in range(0, len(feature_list))])
        # Translate features
        feature_list = self.translate(feature_list, market_list, tenor_list,
                                      relative_bool)
        output_list = [market_list[0], tenor_list[0],
                       'config/down.pmml', 'config/neutral.pmml', 'config/up.pmml']
        output_list.extend(feature_list)
        # Save to file
        df_data = pd.DataFrame([output_list], columns=header_list)
        df_data.to_csv(path + file_name + '.csv', sep=';', header=True, index=False)
        return 0
        

    def __translate_single(self, input_name, market, tenor, relative_bool):
        # reference_instrument = '[' + market + ', ' + tenor + ']'
        rf_dict = {i: '[' + m + ', ' + t + ']' for i, (m, t)
                   in enumerate(zip(market, tenor))}
        # Delete later
        # if input_name[:12] == 'delta_am_wm_':
        #     input_name = 'diff_am_wm_' + input_name[12:]
        # Current
        if input_name in ['hour', 'weekday']:
            feature = 'current'
            metric = input_name
            output = metric
        elif input_name[:9] == 'ba_spread':
            feature = 'current'
            metric = input_name[:9]
            if len(input_name) < 11:
                num = 0
            else:
                num = int(input_name[10:])
            output = feature + '(' + rf_dict[num] + ',' + metric + ')'
        elif input_name[:6] == 'class_':
            feature = 'current'
            number_m = str(int(self._tclass * self._tunit))
            metric = 'bck_cls' + '(' + number_m + ')'
            num = int(input_name[6:])
            output = feature + '(' + rf_dict[num] + ',' + metric + ')'
        elif input_name[:10] == 'ba_volrat_':
            feature = 'current'
            number = str(int(input_name.split('_')[2]) * self._dunit)
            metric = 'vol_rat' + '(' + number + ')'
            try:
                num = int(input_name.split('_')[3])
            except(IndexError):
                num = 0
            output = feature + '(' + rf_dict[num] + ',' + metric + ')'
        # Delta
        elif input_name[:5] == 'delta':
            feature = 'delta'
            if input_name[:8] == 'delta_a_':
                metric = 'a_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                try:
                    num = int(input_name.split('_')[3])
                except(IndexError):
                    num = 0
                number = str(int(input_name.split('_')[2][:-1]) * self._tunit)
            elif input_name[:8] == 'delta_b_':
                metric = 'b_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                try:
                    num = int(input_name.split('_')[3])
                except(IndexError):
                    num = 0
                number = str(int(input_name.split('_')[2][:-1]) * self._tunit)
            elif input_name[:9] == 'delta_ba_':
                metric = 'ba_spread'
                try:
                    num = int(input_name.split('_')[3])
                except(IndexError):
                    num = 0
                number = str(int(input_name.split('_')[2][:-1]) * self._tunit)
            elif input_name[:8] == 'delta_mw':
                try:
                    number = str(int(input_name.split('_')[3][:-1]) * self._tunit)
                    num = int(input_name.split('_')[1][2:])
                    number_m = str(int(input_name.split('_')[2]) * self._dunit)
                except(IndexError):
                    num = 0
                    number_m = str(int(input_name.split('_')[1][2:]) * self._dunit)
                    number = str(int(input_name.split('_')[2][:-1]) * self._tunit)
                metric = 'mw_price' + '(' + number_m + ')'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
            elif input_name[:11] == 'delta_volA_':
                number_m = str(int(input_name.split('_')[2]) * self._dunit)
                number = str(int(input_name.split('_')[3][:-1]) * self._tunit)
                metric = 'a_volume' + '(' + number_m + ')'
                num = 0
            elif input_name[:11] == 'delta_volB_':
                number_m = str(int(input_name.split('_')[2]) * self._dunit)
                number = str(int(input_name.split('_')[3][:-1]) * self._tunit)
                metric = 'b_volume' + '(' + number_m + ')'
                num = 0
            else:
                ValueError('Unknown delta input: ')  
            output = feature + '(' + rf_dict[num] + ',' + metric + ',' + number + ')'
        # Diff
        elif input_name[:4] == 'diff':
            feature = 'diff'
            feature_dict = {k: [] for k in range(0, 2)}
            if input_name[:11] == 'diff_am_wm_':
                feature_aux = 'current'
                num = int(input_name.split('_')[4])
                # First
                metric = 'mid_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                # Second
                number_m = str(int(input_name.split('_')[3]) * self._dunit)
                metric = 'mw_price' + '(' + number_m + ')'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
            elif input_name[:7] == 'diff_mw':
                num = int(input_name.split('_')[1][2:])
                number_dict = (input_name[9:]).split('_')
                # First
                number_m = str(int(number_dict[0]) * self._tunit)
                if int(number_dict[0]) == 0:
                    feature_aux = 'current'
                    metric = 'mid_price'
                    if relative_bool:
                        metric = 'ln(' + metric + ')'
                    feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                else:
                    feature_aux = 'mov_avg'
                    metric = 'mid_price'
                    feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_m + ')'
                    if relative_bool:
                        feature_dict[0] = 'ln(' + feature_dict[0] + ')'
                # Second
                number_m = str(int(number_dict[1]) * self._tunit)
                if int(number_dict[1]) == 0:
                    feature_aux = 'current'
                    metric = 'mid_price'
                    if relative_bool:
                        metric = 'ln(' + metric + ')'
                    feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                else:
                    feature_aux = 'mov_avg'
                    metric = 'mid_price'
                    feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_m + ')'
                    if relative_bool:
                        feature_dict[1] = 'ln(' + feature_dict[1] + ')'
            else:
                ValueError('Unknown diff input: ')
            output = feature + '(' + feature_dict[0] + ',' + feature_dict[1] + ')'
        # Roll class
        elif input_name[:10] == 'roll_class':
            feature = 'mov_avg'
            number_m = str(int(self._tclass * self._tunit))
            metric = 'bck_cls' + '(' + number_m + ')'
            num = int(input_name.split('_')[1][5:])
            number = str(int(input_name.split('_')[2]) * self._tunit)
            output = feature + '(' + rf_dict[num] + ',' + metric + ',' + number + ')'
        # Lambdas
        elif input_name.split('_')[0] == 'lamb':
            # feature = 'diff'
            feature_aux = 'mov_avg'
            if input_name.split('_')[1] == 'a':
                metric = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            if input_name.split('_')[2] == 'ins':
                metric += 'update'
            elif input_name.split('_')[2] == 'del':
                metric += 'delete'
            else:
                ValueError('Unknown feature input: ')
            number_m = str(int(input_name.split('_')[3]) * self._dunit)
            number_t = str(int(input_name.split('_')[4][:-1]) * self._tunit)
            metric += '(' + number_m + ')'
            num = int(input_name.split('_')[-1])
            if int(number_t) == self._tunit:
                feature_aux = 'current'
                output = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
            else:
                output = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_t + ')'
        elif input_name.split('_')[0] == 'ilamb':
            feature = 'gtoe'
            feature_dict = {k: [] for k in range(0, 2)}
            metric_dict = {k: [] for k in range(0, 2)}
            feature_aux = 'diff'
            feature_aux_0 = 'current'
            feature_aux_1 = 'mov_avg'
            num = int(input_name.split('_')[-1])
            if input_name.split('_')[1] == 'a':
                metric_base = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric_base = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            number_d = str(int(input_name.split('_')[2]) * self._dunit)
            number_t = str(int(input_name.split('_')[3]) * self._tunit)
            metric_dict[0] = metric_base + 'update(' + number_d + ')'
            metric_dict[1] = metric_base + 'delete(' + number_d + ')'
            feature_dict[0] = feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[0] + '),' + \
                              feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[1] + ')'
            feature_dict[1] = feature_aux_1 + '(' + rf_dict[num] + ',' + metric_dict[0] + ',' + number_t + '),' + \
                              feature_aux_1 + '(' + rf_dict[num] + ',' + metric_dict[1] + ',' + number_t + ')'
            output = feature + '(' + feature_aux + '(' + feature_dict[0] + '),' + \
                                     feature_aux + '(' + feature_dict[1] + '))'
        elif input_name.split('_')[0] == 'dlamb':
            feature = 'feature_delta'
            feature_aux = 'diff'
            feature_aux_0 = 'mov_avg'
            feature_dict = {k: [] for k in range(0, 1)}
            metric_dict = {k: [] for k in range(0, 2)}
            num = int(input_name.split('_')[-1])
            if input_name.split('_')[1] == 'a':
                metric_base = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric_base = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            number_d = str(int(input_name.split('_')[2]) * self._dunit)
            number_t = str(int(input_name.split('_')[3]) * self._tunit)
            number_tf = str(int(input_name.split('_')[4]) * self._tunit)
            metric_dict[0] = metric_base + 'update(' + number_d + ')' + ',' + number_t
            metric_dict[1] = metric_base + 'delete(' + number_d + ')' + ',' + number_t
            feature_dict[0] = feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[0] + '),' + \
                              feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[1] + ')'
            output = feature + '(' + feature_aux + '(' + feature_dict[0] + '),' + number_tf + ')'      
        else:
            ValueError('Unknown feature input: ')
        return output

def __translate_single_old(self, input_name, market, tenor, relative_bool):
        # reference_instrument = '[' + market + ', ' + tenor + ']'
        rf_dict = {i: '[' + m + ', ' + t + ']' for i, (m, t)
                   in enumerate(zip(market, tenor))}
        # Delete later
        # if input_name[:12] == 'delta_am_wm_':
        #     input_name = 'diff_am_wm_' + input_name[12:]
        # Current
        if input_name in ['hour', 'weekday']:
            feature = 'current'
            metric = input_name
            output = metric
        elif input_name[:9] == 'ba_spread':
            feature = 'current'
            metric = input_name[:9]
            if len(input_name) < 11:
                num = 0
            else:
                num = int(input_name[10:])
            output = feature + '(' + rf_dict[num] + ',' + metric + ')'
        elif input_name[:6] == 'class_':
            feature = 'current'
            number_m = str(int(self._tclass * self._tunit))
            metric = 'bck_cls' + '(' + number_m + ')'
            num = int(input_name[6:])
            output = feature + '(' + rf_dict[num] + ',' + metric + ')'
        elif input_name[:10] == 'ba_volrat_':
            feature = 'current'
            number = str(int(input_name.split('_')[2]) * self._dunit)
            metric = 'vol_rat' + '(' + number + ')'
            try:
                num = int(input_name.split('_')[3])
            except(IndexError):
                num = 0
        # Delta
        elif input_name[:5] == 'delta':
            feature = 'delta'
            if input_name[:8] == 'delta_a_':
                metric = 'a_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                if len(input_name) < 13:
                    num = 0
                    n = -1
                else:
                    num = int(input_name[12:])
                    n = -3
                number = str(int(input_name[8:n]) * self._tunit)
            elif input_name[:8] == 'delta_b_':
                metric = 'b_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                if len(input_name) < 13:
                    num = 0
                    n = -1
                else:
                    num = int(input_name[12:])
                    n = -3
                number = str(int(input_name[8:n]) * self._tunit)
            elif input_name[:9] == 'delta_ba_':
                metric = 'ba_spread'
                if len(input_name) < 14:
                    num = 0
                    n = -1
                else:
                    num = int(input_name[13:])
                    n = -3
                number = str(int(input_name[9:n]) * self._tunit)
            elif input_name[:8] == 'delta_mw':
                try:
                    number_m = str(int(input_name[8:10]) * self._dunit)
                    metric = 'mw_price' + '(' + number_m + ')'
                    number = str(int(input_name[11:-1]) * self._tunit)
                    num = 0
                except(ValueError):
                    # metric = 'mid_price'
                    # number = str(int(input_name[10:-1]) * self._tunit)
                    # num = int(input_name[8:9])
                    number_m = str(int(input_name[10:12]) * self._dunit)
                    metric = 'mw_price' + '(' + number_m + ')'
                    number = str(int(input_name[13:-1]) * self._tunit)
                    num = int(input_name[8:9])
                if relative_bool:
                    metric = 'ln(' + metric + ')'
            elif input_name[:11] == 'delta_volA_':
                number_m = str(int(input_name[11:13]) * self._dunit)
                metric = 'a_volume' + '(' + number_m + ')'
                number = str(int(input_name[14:-1]) * self._tunit)
                num = 0
            elif input_name[:11] == 'delta_volB_':
                number_m = str(int(input_name[11:13]) * self._dunit)
                metric = 'b_volume' + '(' + number_m + ')'
                number = str(int(input_name[14:-1]) * self._tunit)
                num = 0
            else:
                ValueError('Unknown delta input: ')  
            output = feature + '(' + rf_dict[num] + ',' + metric + ',' + number + ')'
        # Diff
        elif input_name[:4] == 'diff':
            feature = 'diff'
            feature_dict = {k: [] for k in range(0, 2)}
            if input_name[:11] == 'diff_am_wm_':
                feature_aux = 'current'
                #num = int(input_name[14:])
                num = int(input_name[-1])
                # First
                metric = 'mid_price'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                # Second
                number_m = str(int(input_name[11:13]) * self._dunit)
                metric = 'mw_price' + '(' + number_m + ')'
                if relative_bool:
                    metric = 'ln(' + metric + ')'
                feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
            elif input_name[:7] == 'diff_mw':
                num = int(input_name[7:8])
                number_dict = (input_name[9:]).split('_')
                # First
                number_m = str(int(number_dict[0]) * self._tunit)
                if int(number_dict[0]) == 0:
                    feature_aux = 'current'
                    metric = 'mid_price'
                    if relative_bool:
                        metric = 'ln(' + metric + ')'
                    feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                else:
                    feature_aux = 'mov_avg'
                    metric = 'mid_price'
                    feature_dict[0] = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_m + ')'
                    if relative_bool:
                        feature_dict[0] = 'ln(' + feature_dict[0] + ')'
                # Second
                number_m = str(int(number_dict[1]) * self._tunit)
                if int(number_dict[1]) == 0:
                    feature_aux = 'current'
                    metric = 'mid_price'
                    if relative_bool:
                        metric = 'ln(' + metric + ')'
                    feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
                else:
                    feature_aux = 'mov_avg'
                    metric = 'mid_price'
                    feature_dict[1] = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_m + ')'
                    if relative_bool:
                        feature_dict[1] = 'ln(' + feature_dict[1] + ')'
            else:
                ValueError('Unknown diff input: ')
            output = feature + '(' + feature_dict[0] + ',' + feature_dict[1] + ')'
        # Roll class
        elif input_name[:10] == 'roll_class':
            feature = 'mov_avg'
            number_m = str(int(self._tclass * self._tunit))
            metric = 'bck_cls' + '(' + number_m + ')'
            num = int(input_name[10:11])
            number = str(int(input_name[12:]) * self._tunit)
            output = feature + '(' + rf_dict[num] + ',' + metric + ',' + number + ')'
        # Lambdas
        elif input_name.split('_')[0] == 'lamb':
            # feature = 'diff'
            feature_aux = 'mov_avg'
            if input_name.split('_')[1] == 'a':
                metric = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            if input_name.split('_')[2] == 'ins':
                metric += 'update'
            elif input_name.split('_')[2] == 'del':
                metric += 'delete'
            else:
                ValueError('Unknown feature input: ')
            number_m = str(int(input_name.split('_')[3]) * self._dunit)
            number_t = str(int(input_name.split('_')[4][:-1]) * self._tunit)
            metric += '(' + number_m + ')'
            num = int(input_name.split('_')[-1])
            if int(number_t) == self._tunit:
                feature_aux = 'current'
                output = feature_aux + '(' + rf_dict[num] + ',' + metric + ')'
            else:
                output = feature_aux + '(' + rf_dict[num] + ',' + metric + ',' + number_t + ')'
        elif input_name.split('_')[0] == 'ilamb':
            feature = 'gtoe'
            feature_dict = {k: [] for k in range(0, 2)}
            metric_dict = {k: [] for k in range(0, 2)}
            feature_aux = 'diff'
            feature_aux_0 = 'current'
            feature_aux_1 = 'mov_avg'
            num = int(input_name.split('_')[-1])
            if input_name.split('_')[1] == 'a':
                metric_base = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric_base = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            number_d = str(int(input_name.split('_')[2]) * self._dunit)
            number_t = str(int(input_name.split('_')[3]) * self._tunit)
            metric_dict[0] = metric_base + 'update(' + number_d + ')'
            metric_dict[1] = metric_base + 'delete(' + number_d + ')'
            feature_dict[0] = feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[0] + '),' + \
                              feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[1] + ')'
            feature_dict[1] = feature_aux_1 + '(' + rf_dict[num] + ',' + metric_dict[0] + ',' + number_t + '),' + \
                              feature_aux_1 + '(' + rf_dict[num] + ',' + metric_dict[1] + ',' + number_t + ')'
            output = feature + '(' + feature_aux + '(' + feature_dict[0] + '),' + \
                                     feature_aux + '(' + feature_dict[1] + '))'
        elif input_name.split('_')[0] == 'dlamb':
            feature = 'feature_delta'
            feature_aux = 'diff'
            feature_aux_0 = 'mov_avg'
            feature_dict = {k: [] for k in range(0, 1)}
            metric_dict = {k: [] for k in range(0, 2)}
            num = int(input_name.split('_')[-1])
            if input_name.split('_')[1] == 'a':
                metric_base = 'ob_ask_'
            elif input_name.split('_')[1] == 'b':
                metric_base = 'ob_bid_'
            else:
                ValueError('Unknown feature input: ')
            number_d = str(int(input_name.split('_')[2]) * self._dunit)
            number_t = str(int(input_name.split('_')[3]) * self._tunit)
            number_tf = str(int(input_name.split('_')[4]) * self._tunit)
            metric_dict[0] = metric_base + 'update(' + number_d + ')' + ',' + number_t
            metric_dict[1] = metric_base + 'delete(' + number_d + ')' + ',' + number_t
            feature_dict[0] = feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[0] + '),' + \
                              feature_aux_0 + '(' + rf_dict[num] + ',' + metric_dict[1] + ')'
            output = feature + '(' + feature_aux + '(' + feature_dict[0] + '),' + number_tf + ')'      
        else:
            ValueError('Unknown feature input: ')
        return output

