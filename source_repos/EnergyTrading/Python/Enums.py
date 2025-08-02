# from entsoe.mappings import NEIGHBOURS

residual_load_tables_list = ['DEU_' + a for a in ['00', '06', '12', '18']]+\
                           ['FRA_' + a for a in ['00', '06', '12', '18']]+\
                               ['NLD_' + a for a in ['00', '06', '12', '18']]+\
                                   ['BEL_' + a for a in ['00', '06', '12', '18']]+\
                                       ['AUT_' + a for a in ['00', '06', '12', '18']]+\
                                ['CZE_' + a for a in ['00', '06', '12', '18']]+\
                                    ['HUN_' + a for a in ['00', '06', '12', '18']]+\
                                        ['ROU_' + a for a in ['00', '06', '12', '18']]
                                       
fund_mnd_tables_list = [a + '_00' for a in ['DEU', 'FRA', 'NLD', 'BEL', 'AUT']]
spot_grid_tables = [
    'de', 'at', 'fr', 'be', 'nl', 
    'dkw', 'dke', 'fi', 'no1', 
    'no2', 'no3', 'no4', 'no5', 
    'pl', 'se1', 'se2', 'se3', 
    'se4', 'hu', 'cz', 'sk',
    'ro', 'si', 'bg', 'es', 'it',
    'it_nord', 'gr', 'hr']

export_ntc_grid_list = ['DEU', 'FRA', 'BEL', 'AUT', 'NLD',
           'CZE', 'SVK', 'HUN', 'ROU', 'ITA']



GRID_TO_ENTSO_ZONE = {
    'DEU': 'DE_LU',
    'FRA': 'FR',
    'BEL': 'BE',
    'NLD': 'NL',
    'AUT': 'AT',
    'CZE': 'CZ',
    'SVK': 'SK',
    'HUN': 'HU',
    'ROU': 'RO',
    'ITA': 'IT'
    }

ENTSO_ZONE_TO_GRID = {
    'DE_LU': 'DEU',
    'FR': 'FRA',
    'BE': 'BEL',
    'NL': 'NLD',
    'AT': 'AUT',
    'CZ': 'CZE',
    'SK': 'SVK',
    'HU': 'HUN',
    'RO': 'ROU',
    'IT': 'ITA',
    'CH': 'CHE',
    'DK_1': 'DKW',
    'DK_2': 'DKE',
    'ES': 'ESP'
}



normal_codes = {'DEU': {'CON': 102237152,
                        'Wind': 103058677,
                        'Solar': 103286609,
                        'Temp': 110775197},
                'FRA': {'CON': 102339673,
                        'Wind': 106819241,
                        'Solar': 104575908,
                        'INF': 125191},
                'NLD': {'CON': 101819315,
                        'Wind': 110803547,
                        'Solar': 110696131},
                'BEL': {'CON': 102339676,
                        'Wind': 106815919,
                        'Solar': 104567539},
                'AUT': {'CON': 102238608,
                        'Wind': 106808409,
                        'Solar':116713960,
                        'INF': 101613419},
                'CZE': {'CON': 112774966,
                        'Wind': None,
                        'Solar': 104564610},
                'HUN': {'CON': 112775479,
                        'Wind': None,
                        'Solar': 118071950,
                        'Temp': 112775448},
                'ROU': {'CON': 113860142,
                        'Wind': 106827554 ,
                        'Solar': 110247043},
                'SVK': {'CON': 110211315,
                        'Wind':None,
                        'Solar': None},
                'ITA': {'CON': 112095467,
                        'Wind': 114974085 ,
                        'Solar': 104095144},
                'ESP': {'CON': 112777292,
                        'Wind': 113958169,
                        'Solar': 104563796},
                'OSC': {'AO': 117500737,
                        'NAO': 117469253}}

CHECK_LIST = [b for a, b in GRID_TO_ENTSO_ZONE.items()]

DATABASE = {
    'postgre': {
        'residual': {
            'tables': ['de'],
            'columns': [
                'forecast_date',
                'value_date',
                'con_ens',
                'con_op',
                'wind_ens',
                'wind_op',
                'solar_ens',
                'solar_op'],
            'primary_key': ['forecast_date', 'value_date']
        },
        'spot': {
            'tables': spot_grid_tables,
            'columns': [[
                'datetime',
                'b_volume',
                's_volume',
                'volume',
                'price'] for _ in range(len(spot_grid_tables))],
            'primary_key': ['datetime']
        },
        'normal': {
            'tables': ['de'],
            'columns': [
                'value_date',
                'solar',
                'wind',
                'con'],
            'primary_key': ['value_date']
        },
        'algo': {
            'tables': ['strategy_trades'],
            'columns': [[
                'trade_id',
                'order_id',
                'exchange',
                'execution_time',
                'state',
                'algo_id',
                'price',
                'quantity',
                'buy_delivery_area',
                'sell_delivery_area',
                'product_id',
                'product_type',
                'product_name',
                'slot_type',
                'slot_information',
                'counterparty',
                'aggressor',
                'initiator',
                'aggressor_broker_id',
                'initiator_broker_id']],
            'primary_key': ['trade_id']
        },
        'FUND_AvailCap': {
            'tables': ['DEU_12', 'FRA_12'],
            'columns': [[
                'forecast_date', 'value_date',
                'Coal_de', 'Gas_de',
                'Lig_de', 'Nuc_de',
                'Oil_de', 'Pump_de',
                'Res_de', 'RoR_de'],
                ['forecast_date','value_date',
                    'Coal_fr', 'Gas_fr',
                    'Hydro Res_fr', 'Hydro RoR_fr',
                    'Nuc_fr', 'Oil_fr', 'Pump_fr']],
            'primary_key': ['forecast_date', 'value_date']
               
                
        },
        'FUND_ResidualDemand': {
            'tables': residual_load_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'rld'] for _ in range(len(residual_load_tables_list))],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_Wind': {
            'tables': residual_load_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'Wind'] for _ in residual_load_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_Wind_mnd': {
            'tables': fund_mnd_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'Wind'] for _ in fund_mnd_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_Solar': {
            'tables': residual_load_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'Solar'] for _ in residual_load_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_Solar_mnd': {
            'tables': fund_mnd_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'Solar'] for _ in fund_mnd_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_CON': {
            'tables': residual_load_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'CON'] for _ in residual_load_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        'FUND_CON_mnd': {
            'tables': fund_mnd_tables_list,
             'columns':[['forecast_date', 'value_date',
                        'CON'] for _ in fund_mnd_tables_list],
            'primary_key': ['forecast_date', 'value_date']              
                           },
        # 'FUND_Export_NTC': {
        #     'tables': export_ntc_grid_list,
        #     'columns': [['value_date'] +
        #                 [a for a in NEIGHBOURS[GRID_TO_ENTSO_ZONE[a]] if a not in CHECK_LIST]
        #                 for a in export_ntc_grid_list],
        #     'primary_key': ['value_date']
        #     }
        'cot': {
            'tables': ['cot_entries'],
            'columns': [['date',
                        'instrument',
                        'direction',
                        'actor',
                        'risk_reducing',
                        'volume']],
            'primary_key': ['date',
                        'instrument',
                        'direction',
                        'actor',
                        'risk_reducing']
        }

    },
    'oracle': {
        'ROVE_OD': {
            'TRAYPORT_VW_TRADES'
        }
    }
}

FTP = {

    'con': {
        'hist_ens': "History/Eur_Power/Demand/5010557_HIST_Pwr_PCA_CON_ECEns_AVG_{country}_F_{year}.CSV",
        'hist_op': "History/Eur_Power/Demand/5011215_HIST_Pwr_PCA_CON_ECOP_DEU_F_{year}.CSV",
        'live_ens': "Live/Eur_Power/Demand/5005429_Pwr_PCA_CON_ECEns_AVG_DEU_F_{date}.CSV",
        'live_op': "Live/Eur_Power/Demand/5005430_Pwr_PCA_CON_ECOP_DEU_F_{date}.CSV",
        'normal': "History/Eur_Power/Normals/5022227_HIST_Pwr_PCA_CON_DEU_N_A_{year}.CSV"
    },
    'wind': {
        'hist_ens': "History/Eur_Power/Supply/5011254_HIST_Pwr_PCA_PRO_Wind_ECens_AVG_DEU_F_{year}.CSV",
        'hist_op': "History/Eur_Power/Supply/5010503_HIST_Pwr_PCA_PRO_Wind_ECop_DEU_F_{year}.CSV",
        'live_ens': "Live/Eur_Power/Supply/5007708_Pwr_PCA_PRO_Wind_ECens_AVG_DEU_F_{date}.CSV",
        'live_op': "Live/Eur_Power/Supply/5007707_Pwr_PCA_PRO_Wind_ECop_DEU_F_{date}.CSV",
        'normal': "History/Eur_Power/Supply/5108383_HIST_Pwr_PCA_PRO_Wind_AVG_DEU_N_A_{year}.CSV"
    },
    'solar': {
        'hist_ens': "History/Eur_Power/Supply/5018189_HIST_Pwr_PCA_PRO_Solar_ECens_AVG_DEU_F_{year}.CSV",
        'hist_op': "History/Eur_Power/Supply/5011011_HIST_Pwr_PCA_PRO_Solar_ECop_DEU_F_{year}.CSV",
        'live_ens': "Live/Eur_Power/Supply/5018188_Pwr_PCA_PRO_Solar_ECens_AVG_DEU_F_{date}.CSV",
        'live_op': "Live/Eur_Power/Supply/5004202_Pwr_PCA_PRO_Solar_ECop_DEU_F_{date}.CSV",
        'normal': "History/Eur_Power/Supply/5108391_HIST_Pwr_PCA_PRO_Solar_AVG_DEU_N_A_{year}.CSV"
    }
}



CUR_CODES = {'DEU':{'Coal': 105269300,
                   'Lig': 105269303,
                   'Gas': 105663406,
                   'Pump': 111205650,
                   'RoR': 111205652,
                   'Res': 111205651,
                   'Nuc': 105269302,
                   'Oil': 106819498,
                   'Wind': 2},
            'FRA': {'Coal': 106336320,
                  'Gas': 106336321,
                  'Hydro Res': 106336323,
                  'Hydro RoR': 106336324,
                  'Nuc': 106336319,
                  'Oil': 106336325,
                  'Pump': 106336322}}

FTP_DATE_FORMAT = {
    'avcap': '%Y-%m'
}
# FTP = {
#     'live': {'rld': None,
#              'con': None,
#              'wind': None,
#              'solar': None,
#              'instcap': None,
#              'avcap': {
#                  'DE': "History/Eur_Power/Supply/5044792_HIST_Pwr_PCA_PRO_AvailCap_EEX_REMIT_E1_DEU_F_{date}.CSV"
#              }},
#     'hist': {'rld': None,
#              'con': None,
#              'wind': None,
#              'solar': None,
#              'instcap': None,
#              'avcap': None},
#     'normal': {
#         'con': None,
#         'wind': None,
#         'solar': None
#         },
#     'rld': None,
#     'con': None,
#     'wind': None,
#     'solar': None,
#     'instcap': None,
#     'avcap': {
#         'DE': {
#             'hist': {
#                 'weeks': 
#             },
#             'live': {},
#             'normal': {}
#         }
#     }
# }