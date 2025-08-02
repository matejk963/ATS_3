import fund_analysis.scenarios as scenarios
import pandas as pd
import datetime as dt
import pickle
import os

data_test_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\fund_analysis\test\data'

file_path = os.path.join(data_test_dir, 'base_data.pkl')
with open(file_path, 'rb') as f:
    base_data = pickle.load(f)

scen_list = [a/100 for a in range(-30,31,5)]
inst = scenarios.FuelScenarios(base_data, 'ttf')

scen_dict = inst.get_defined_scenarios(scen_list)