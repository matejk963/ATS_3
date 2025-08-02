# -*- coding: utf-8 -*-
"""
Created on Thu Jun 22 10:20:55 2023

@author: Marek
"""

import psycopg2
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta


#establishing the connection
conn = psycopg2.connect(
   database='trayportdata', user='trayport', password='trayPwd321',
   host='192.168.10.141', port='5432'
)
        
# query = "select datetime, action, price, volume, side, persistentorderid, " + \
#         "companyid, brokerid " + \
#         "from trayport_orders ord " + \
#         "where ord.instid in " + \
#         "(select id_instrument from trayport_instrument where instname in ('?mkt')) " + \
#         "and ord.firstsequenceid = ?seqid1 " + \
#         "and ord.firstsequenceitemid = ?itemid " + \
#         "and ord.secondsequenceitemid = 0 " + \
#         "and ord.datetime >= to_timestamp('?bT', 'dd.mm.yyyy HH24:MI:SS') " + \
#         "and ord.datetime  < to_timestamp('?eT', 'dd.mm.yyyy HH24:MI:SS')"


# def calc_seqid(mkt, tenor):
#     com = com_dict(mkt)
#     return str(seqid_dict(com, tenor))


# def calc_itemid(tenor, start_date):
#     delta = relativedelta(start_date, datetime(2022,1,1))
#     if tenor.upper() == 'M':
#         idem_id = delta.months + 12 * delta.years + 217
#     elif tenor.upper() == 'Q':
#         idem_id = int((delta.months + 12 * delta.years) / 3) + 73
#     elif tenor.upper() == 'Y':
#         idem_id = int((delta.months + 12 * delta.years) / 12) + 19
#     else:
#         raise ValueError('Unknown tenor %s' % tenor)
#     return idem_id


# def calc_instname(mkt, prod, venue):
#     inst_name = ''
#     inst_name += mkt_dict(mkt)
#     com = com_dict(mkt)
#     if com == 'pwr':
#         inst_name += ' ' + prod_dict(prod)
#     elif com in ['gas', 'eua']:
#         pass
#     else:
#         raise ValueError('Unknown commodity %s' % com)
#     if venue == 'otc':
#         pass
#     elif venue == 'eex':
#         inst_name += ' EEX'
#     elif venue == 'ice':
#         inst_name += ' ICE ENDEX'
#         if com == 'pwr':
#             inst_name += ' Fin'
#     return inst_name


# def get_instnames(mkt, prod, venue_list):
#     return ', '.join([calc_instname(mkt, prod, v) for v in venue_list])


# def change_query(query, inst_name, tenor, start_date, bT, eT):
#     query = query.replace('?mkt', inst_name)
#     query = query.replace('?seqid1', calc_seqid(mkt, tenor))
#     query = query.replace('?itemid', str(calc_itemid(tenor, start_date)))
#     query = query.replace('?bT', bT.strftime('%d.%m.%Y %H:%M:%S'))
#     query = query.replace('?eT', eT.strftime('%d.%m.%Y %H:%M:%S'))
#     return query


# def mkt_dict(mkt):
#     my_dict = {}
#     my_dict['de'] = 'Germany'
#     my_dict['ttf'] = 'TTF Hi Cal 51.6'
#     return my_dict[mkt]


# def prod_dict(prod):
#     my_dict = {}
#     my_dict['base'] = 'Baseload'
#     my_dict['peak'] = 'Peaks'
#     return my_dict[prod]


# def com_dict(mkt):
#     my_dict = {}
#     my_dict['de'] = 'pwr'
#     my_dict['ttf'] = 'gas'
#     my_dict['eua'] = 'eua'
#     return my_dict[mkt]


# def seqid_dict(com, tenor):
#     my_dict = {}
#     if com == 'pwr':
#         my_dict['M'] = 10000104
#         my_dict['Q'] = 10000105
#         my_dict['Y'] = 10000106
#     elif com == 'gas':
#         my_dict['M'] = 10000305
#         my_dict['Q'] = 10000306
#         my_dict['S'] = 10000307
#         my_dict['SUM'] = 10000307
#         my_dict['WIN'] = 10000307
#         my_dict['Y'] = 10000309
#     elif com == 'eua':
#         my_dict['Y'] = 10000400
#     else:
#         raise ValueError('Unknown commodity %s' % com)
#     return my_dict[tenor.upper()]


# def prepare_data(data_raw, columns):
#     data_dict = {k: [x[i] for x in data_raw] for i, k in enumerate(columns)}
#     df_data = pd.DataFrame(data_dict)
#     df_data.set_index('datetime', inplace=True)
#     return df_data


# mkt = 'de'
# tenor = 'm'
# prod = 'base'
# venue_list = ['eex']
# start_date = datetime(2023, 8, 1)
# columns = ['datetime', 'action', 'price', 'volume', 'side', 'persistentorderid',
#            'companyid', 'brokerid']

# bT = datetime(2023, 7, 21, hour=8, minute=0, second=0)
# eT = datetime(2023, 7, 21, hour=18, minute=0, second=0)

# inst_name = get_instnames(mkt, prod, venue_list)
# query_w = change_query(query, inst_name, tenor, start_date, bT, eT)

# cursor = conn.cursor()
# #Executing an MYSQL function using the execute() method
# cursor.execute(query_w)
# # Fetch a single row using fetchone() method.
# data_raw = cursor.fetchall()
# #print('Connection established to: ',data_raw)

# pd_data = prepare_data(data_raw, columns)
# #Closing the connection
# conn.close()