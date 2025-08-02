# -*- coding: utf-8 -*-
"""
Created on Wed Nov 22 09:31:45 2023

@author: krajcovic
"""

import pandas as pd
from BorderSpread.Capa_functions import CapaFvFetch as FVF
from datetime import datetime, timedelta


# border_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
#                 'de_nl', 'nl_de', 'be_nl', 'nl_be',
#                 'be_fr', 'fr_be',
#                 'de_at', 'at_de', 'at_hu', 'hu_at',
#                 'at_cz', 'cz_at', 'cz_de', 'de_cz',
#                 'ro_hu', 'hu_ro', 'sk_cz', 'cz_sk',
#                 'sk_cz', 'hu_sk', 'sk_hu']

# fv_df_month = FVF(border_list)

border_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
                'de_nl', 'nl_de', 'be_nl', 'nl_be',
                'be_fr', 'fr_be',
                'de_at', 'at_de', 'at_hu', 'hu_at',
                'at_cz', 'cz_at', 'cz_de', 'de_cz']
# border_list = ['ro_bg', 'bg_ro']
border_list = ['be_de', 'be_nl',
               'de_be', 'de_nl', 'nl_be', 'nl_de']

# border_list = ['sk_cz', 'cz_sk', 'sk_hu', 'hu_sk']

fv_df_year = FVF(border_list, period='M')

# fv_df_month.to_excel(r'S:\Capa\CapaFv\2023_12_capa_fv_act5.xlsx')
fv_df_year.to_excel(r'S:\Capa\CapaFv\2024_Feb_FV.xlsx')

vol_dict = {'de_dke': 1, 'dkw_nl': 1, 'at_de': 5, 'be_de': 3,
            'be_nl': 3, 'de_at': 5, 'de_be': 3, 'de_nl': 3,
            'nl_be': 3, 'nl_de': 3, 'cz_de': 3, 'de_cz': 2,
            'at_hu': 2, 'hu_at': 2, 'at_cz': 2, 'cz_at': 2,
            'sk_cz': 1, 'hu_sk': 1, 'be_fr': 4, 'fr_be': 4}

price_dict = {'de_dke': 1.48, 'dkw_nl': 7.33, 'at_de': 1.49, 'be_de': 5.6,
            'be_nl': 3.96, 'de_at': 6.97, 'de_be': 5.11, 'de_nl': 4.36,
            'nl_be': 4.4, 'nl_de': 5.1, 'cz_de': 1.35, 'de_cz': 5.35,
            'at_hu': 6.89, 'hu_at': 1.71, 'at_cz': 2.01, 'cz_at': 3.88,
            'sk_cz': 0.8, 'hu_sk': 0.66, 'be_fr': 4.73, 'fr_be': 3.14}

vol_list = []
price_list = []
for m in fv_df_year['border']:
    price_list.append(price_dict[m])
    vol_list.append(vol_dict[m])
    
hours = ((datetime(2024,1,22)- datetime(2024,1,1)).days+1)*24
fv_df_year['vol'] = vol_list
fv_df_year['price'] = price_list
fv_df_year['pnl'] = (fv_df_year['fv'] - fv_df_year['price'])*fv_df_year['vol']*743
    


    
