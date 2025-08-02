# -*- coding: utf-8 -*-
"""
Created on Thu Dec  7 16:03:10 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from BorderSpread.CapaBnH_class_beta import CapaBnH as CBH

file_path = r'S:\Capa\CapaFv\Test\jan_24_v6.xlsx'

# border_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
#                 'de_nl', 'nl_de', 'be_nl', 'nl_be',
#                 'be_fr', 'fr_be',
#                 'de_at', 'at_de', 'at_hu', 'hu_at',
#                 'at_cz', 'cz_at', 'cz_de', 'de_cz']
params_dict = {}
# for border in border_list:
#     params_dict[border] = {'Max Risk': 20000,
#                            'Hours': 744}
    
"""
Dec 2023 auction date example
"""

borders_list = ['dkw_nl', 'nl_dkw', 'dkw_de', 'de_dkw',
                'de_fr', 'fr_de', 'de_be', 'be_de', 'de_nl', 'nl_de',
                'be_nl', 'nl_be', 'be_fr', 'fr_be',
                'de_at', 'at_de', 'at_hu', 'hu_at', 'at_cz', 'cz_at',
                'cz_de','de_cz',
                'hu_ro', 'ro_hu', 'cz_sk',
                'sk_hu', 'hu_sk']
borders_list = [ 'de_at', 'at_de']
# borders_list = ['fr_be', 'be_fr', 'de_fr', 'fr_de']
min_pos_list = [5,5]
max_pos_list = [5,5]

for max_pos, min_pos, border in zip(max_pos_list,
                                    min_pos_list, borders_list):
    params_dict[border] = {'Min Pos': min_pos,
                           'Max Pos': max_pos,
                           'Hours': 744,
                           'spread': 'formula', 'ext':'formula'}


    
test_o = CBH(datetime(2023,1,1), data_aggregation='M', capa_type='M')

# test_auct = test_o.position_checker_jao_api()

test_o.set_borders_list(borders_list)
test_o.create_excel(file_path)
test_o.create_hedge_pos(file_path)
test_o.create_net_hedge(file_path)
test_o.create_bidding_sheet_with_formulas(file_path, test_o.formulas_dict, params_dict)
# test_o.position_checker_jao_api(file_path)
flows_pos = test_o.flow_aggregator(file_path)



# test_o.merge_and_process(test_o.aggregate_capa_types(),
#                          merge_cols=['border', 'market_out', 'market_in','settle_date_out', 'settle_date_in'],
#                             datetime_cols=['settle_date_out', 'settle_date_in'],
#                             float_cols=['fut_out', 'fut_in', 'spread', 'capa_fv', 'ext', 'delta'],
#                             weighting_col='fut_products')

# cal_dict = test_o.aggregate_capa_types()
