# -*- coding: utf-8 -*-
"""
Created on Mon Dec  2 14:08:40 2024

@author: Marek
"""

from Strategies.Autotrader.TP_api import TP_api
#from Database.TPData import TPData
from datetime import datetime
import Strategies.Autotrader.enumerate as ENUM


ENV = 'prod'
cls = TP_api(ENV)
cls.token


algo_id_dict = {'de': {'w1': "arbitrage-de-weeks",
                       'w2': "arbitrage-de-weeks_1",
                       'm1': "arbitrage-de-months",
                       'm3': "arbitrage-de-month_2",
                       'q1': "arbitrage-de-qa",
                       'q2': "arbitrage-de-qa-1",
                       'q3': "arbitrage-de-qa-2",
                       'q4': "arbitrage-de-qa-3",
                       'y1': "arbitrage-de-cal",
                       'y2': "arbitrage-de-cal-1"},
                'fr': {'w1': "arbitrage-fr-weeks",
                       'm1': "arbitrage-fr-months",
                       'q1': "arbitrage-fr-qa",
                       'q2': "arbitrage-fr-qa-1",
                       'y1': "arbitrage-fr-cal"}}

algo_id = algo_id_dict['de']['m1']
steer_type = 'time_slippage'
cls.steering(algo_id, steer_type)
data = cls.get_monitoring_for(algo_id, steer_type)
aux_list = [x for x in data.json()[0]['values'] if x != None]
aux_list[-1]
key = list(aux_list[-1].keys())[0]

sk = [x[0] - x[1] for x in aux_list[-1][key]]
diff_dict = {datetime.fromtimestamp(y): x - y for x, y in zip(sk[1::2], sk[:-1:2])}
# print([x - y for x, y in zip(sk[1:], sk[:-1])])
print(diff_dict)


# ENV = 'test'
# cls = TP_api(ENV)
# cls.token


# algo_id = "arbitrage-de-may"
# steer_type = 'time_slippage'
# cls.steering(algo_id, steer_type)
# data = cls.get_monitoring_for(algo_id, steer_type)
# aux_list = [x for x in data.json()[0]['values'] if x != None]
# aux_list[-1]
# key = list(aux_list[0].keys())[0]

# sk = [x[0] - x[1] for x in aux_list[0][key]]
# diff_dict = {datetime.fromtimestamp(y): x - y for x, y in zip(sk[1::2], sk[:-1:2])}
# # print([x - y for x, y in zip(sk[1:], sk[:-1])])
# print(diff_dict)