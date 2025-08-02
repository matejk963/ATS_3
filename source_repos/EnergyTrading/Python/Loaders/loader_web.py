# -*- coding: utf-8 -*-
"""
Created on Mon Jul 31 15:19:41 2023

@author: Marek
"""

import requests
import pandas as pd
import numpy as np
from dateutil import tz
from datetime import datetime
from dateutil.relativedelta import relativedelta


class JaoLoader:
    def __init__(self):
        self.token = '86e20d1e-c0fc-406d-95b6-bc8ae625f3c0'

    @property    
    def border_dict(self):
        border_dict = {}
        border_dict['at_cz'] = 'AT-CZ'
        border_dict['at_hu'] = 'AT-HU'
        border_dict['at_si'] = 'AT-SI'
        border_dict['cz_at'] = 'CZ-AT'
        border_dict['cz_de'] = 'CZ-DE(TenneT)'
        border_dict['cz_sk'] = 'CZ-SK'
        border_dict['hr_hu'] = 'HR-HU'
        border_dict['hr_si'] = 'HR-SI'
        border_dict['hu_at'] = 'HU-AT'
        border_dict['hu_hr'] = 'HU-HR'
        border_dict['hu_sk'] = 'HU-SK'
        border_dict['hu_si'] = 'HU-SI'
        border_dict['si_at'] = 'SI-AT'
        border_dict['si_hr'] = 'SI-HR'
        border_dict['si_hu'] = 'SI-HU'
        border_dict['sk_hu'] = 'SK-HU'
        border_dict['sk_cz'] = 'SK-CZ'
        border_dict['at_de'] = 'AT-DE'
        border_dict['be_fr'] = 'BE-FR'
        border_dict['be_nl'] = 'BE-NL'
        border_dict['be_de'] = 'BE-DE'
        border_dict['de_at'] = 'DE-AT'
        border_dict['de_cz'] = 'DE(TenneT)-CZ'
        border_dict['de_fr'] = 'DE-FR'
        border_dict['de_nl'] = 'DE-NL'
        border_dict['de_be'] = 'DE-BE'
        border_dict['fr_be'] = 'FR-BE'
        border_dict['fr_de'] = 'FR-DE'
        border_dict['nl_be'] = 'NL-BE'
        border_dict['nl_de'] = 'NL-DE'
        border_dict['at_it'] = 'AT-IT'
        border_dict['it_at'] = 'IT-AT'
        border_dict['it_fr'] = 'IT-FR'
        border_dict['fr_it'] = 'FR-IT'
        border_dict['it_si'] = 'IT-SI'
        border_dict['si_it'] = 'SI-IT'
        border_dict['es_fr'] = 'ES-FR'
        border_dict['fr_es'] = 'FR-ES'
        border_dict['bg_ro'] = 'BG-RO'
        border_dict['ro_bg'] = 'RO-BG'
        border_dict['bg_gr'] = 'BG-GR'
        border_dict['gr_bg'] = 'GR-BG'
        border_dict['it_gr'] = 'IT-GR'
        border_dict['gr_it'] = 'GR-IT'
        border_dict['dkw_dke'] = 'D1-D2'
        border_dict['dke_dkw'] = 'D2-D1'
        border_dict['dkw_nl'] = 'DK-NL'
        border_dict['nl_dkw'] = 'NL-DK'
        border_dict['dke_de'] = 'D2-DE'
        border_dict['de_dke'] = 'DE-D2'
        border_dict['dkw_de'] = 'D1-DE'
        border_dict['de_dkw'] = 'DE-D1'
        border_dict['hu_ro'] = 'HU-RO'
        border_dict['ro_hu'] = 'RO-HU'
        return border_dict

    @property
    def company_dict(self):
        company_dict = {}
        company_dict['etc'] = '11XETC---------9'
        company_dict['cez'] = '11XCEZ-CZ------1'
        company_dict['danske'] = '11XDANSKECOM---P'
        company_dict['statkraft'] = '11XSTATKRAFT001N'
        company_dict['freepoint'] = '11XFREEPOINT---N'
        company_dict['se'] = '11XSEBRATISLAVA4'
        company_dict['secondfoundation'] = '27XSECOND-FOUNDP'
        company_dict['shell'] = '11XSHELLTRADINGZ'
        company_dict['edf'] = '11XEDFTRADING--G'
        company_dict['ezpada'] = '111XEZPADA------P'
        company_dict['eph'] = '27X-EP-COMMO---N'
        return company_dict

    def jao_auct_response(self, date, corridor, tenor):
        url1 = 'https://api.jao.eu/OWSMP/getauctions?horizon='
        url2 = '&corridor='
        url3 = '&fromdate='
        if tenor.upper() == 'M':
            horizon = 'monthly'
        elif tenor.upper() == 'Y':
            horizon = 'yearly'
        else:
            raise ValueError('Unknown horizon: %s' % tenor)
        d = datetime(date.year, date.month, 1)
        date_str = (d - relativedelta(months=1)).strftime('%Y-%m-%d')
        url = url1 + horizon + url2 + corridor + url3 + date_str
        response = requests.get(url,
                      headers={'AUTH_API_KEY': self.token}).json()
        if type(response) != list:
            out = None
        else:
            out = response[0]
        
        return out

    def auction_loader(self, border_list, date_range, tenor):
        date_format = '%Y-%m-%d'
        param_list = ['auct_date', 'auct_price', 'auct_volume', 'maintenances']

        auct_dict = {}
        for border in border_list:
            date_list = []
            aux_dict = {k: [] for k in param_list}
            corridor = self.border_dict[border]
            for d in date_range:
                if d > datetime.today():
                    break
                response = self.jao_auct_response(d, corridor, tenor)
                if response is not None:
                    # Obtain values
                    auct_date = response['bidGateClosure'].split('T')[0]
                    if response['results'] == []:
                        auct_price = np.nan
                        auct_volume = np.nan
                    else:
                        auct_price = response['results'][0]['auctionPrice']
                        auct_volume = response['results'][0]['allocatedCapacity']
                    maintenances = response['maintenances']
                    if not maintenances:
                        pass
                    elif maintenances[0]['offeredCapacity'] == None:
                        pass
                    else:
                        maintenances = [self.maint_dict(x) for x in response['maintenances']]
                    # Save to dict
                    date_list.append(d)
                    aux_dict['auct_date'].append(datetime.strptime(auct_date, date_format))
                    aux_dict['auct_price'].append(auct_price)
                    aux_dict['auct_volume'].append(auct_volume)
                    aux_dict['maintenances'].append(maintenances)
                else:
                    date_list.append(d)
                    aux_dict['auct_date'].append(np.nan)
                    aux_dict['auct_price'].append(np.nan)
                    aux_dict['auct_volume'].append(np.nan)
                    aux_dict['maintenances'].append(np.nan)

            # new_date_list = [np.nan]*(len(aux_dict)-len(date_list)) + date_list
            auct_dict[border] = pd.DataFrame(aux_dict, index=date_list)
            
        xx = 2
        return auct_dict

    def company_auction_loader(self, company_list, date_range, tenor,
                               border_list=[]):
        if not border_list:
            border_list = self.border_dict.keys()
        auct_dict = {k: {} for k in company_list}
        for company in company_list:
            aux_dict = {k: [] for k in border_list}
            for border in border_list:
                corridor = self.border_dict[border]
                for d in date_range:
                    try:
                        response = self.jao_auct_response(d, corridor, tenor)
                    except(KeyError):
                        print('Fail on date %s and border %s' % (d, border))
                        aux_dict[border].append(False)
                        continue
                    # Obtain values
                    win_bool = self.company_dict[company] in self.company_win_list(response)
                    aux_dict[border].append(win_bool)
            auct_dict[company] = pd.DataFrame(aux_dict, index=date_range)
        return auct_dict

    def single_ac_loader(self, company, sD, tenor, border_list=[]):
        date_format = '%Y-%m-%d'
        param_list = ['border', 'auct_date', 'auct_price', 'maintenances']
        if not border_list:
            border_list = self.border_dict.keys()
        out_dict = {k: [] for k in param_list}
        for border in border_list:
            corridor = self.border_dict[border]
            try:
                response = self.jao_auct_response(sD, corridor, tenor)
            except(KeyError):
                print('Fail on date %s and border %s' % (sD, border))
                continue
            isBool = self.company_dict[company] in self.company_win_list(response)
            if isBool:
                # Obtain values
                auct_date = response['bidGateClosure'].split('T')[0]
                auct_price = response['results'][0]['auctionPrice']
                maintenances = response['maintenances']
                if not maintenances:
                    pass
                else:
                    maintenances = [self.maint_dict(x) for x in response['maintenances']]
                # Save to dict
                out_dict['border'].append(border)
                out_dict['auct_date'].append(datetime.strptime(auct_date, date_format))
                out_dict['auct_price'].append(auct_price)
                out_dict['maintenances'].append(maintenances)
        return out_dict

    def auction_info_loader(self, tenor, sD, border_list=[],
                            from_date=None, to_date=None):
        param_list = ['border', 'auct_date', 'auct_volume', 'maintenances']
        if not border_list:
            border_list = self.border_dict.keys()
        out_dict = {}
        for border in border_list:
            corridor = self.border_dict[border]
            try:
                response = self.jao_auct_response(sD, corridor, tenor)
            except(KeyError):
                print('Fail on date %s and border %s' % (sD, border))
                continue
            auct_date = self.str2time(response['bidGateClosure'][:19])
            auct_volume = response['products'][0]['atc']
            if auct_volume is None:
                auct_volume = np.nan
            maintenances = response['maintenances']
            if not maintenances:
                pass
            else:
                maintenances = [self.maint_dict(x) for x in response['maintenances']]
            # Save to dict
            date = auct_date.strftime('%Y-%m-%d')
            isBool = True
            if from_date is None:
                pass
            elif auct_date < from_date:
                isBool = False
            if to_date is None:
                pass
            elif auct_date > to_date:
                isBool = False
            if isBool:
                if date not in out_dict.keys():
                    out_dict[date] = {k: [] for k in param_list}
                out_dict[date]['border'].append(border)
                out_dict[date]['auct_date'].append(auct_date)
                out_dict[date]['auct_volume'].append(auct_volume)
                out_dict[date]['maintenances'].append(maintenances)
        return out_dict

    def maint_dict(self, maint_dict):
        out_dict = {k: 0 for k in ['start', 'end', 'red']}
        out_dict['start'] = self.str2time(maint_dict['periodStart'][:19])
        out_dict['end'] = self.str2time(maint_dict['periodStop'][:19]) - relativedelta(hours=1)
        out_dict['red'] = maint_dict['reducedOfferedCap'] / maint_dict['offeredCapacity']
        return out_dict

    @staticmethod
    def company_win_list(maint_dict):
        return [x['eicCode'] for x in maint_dict['winningParties']]     

    @staticmethod
    def str2time(date_str):
        date_format = '%Y-%m-%dT%H:%M:%S'
        from_tz = tz.gettz('UTC')
        to_tz = tz.gettz('Europe/Berlin')
        date = datetime.strptime(date_str, date_format)
        return date.replace(tzinfo=from_tz).astimezone(to_tz).replace(tzinfo=None)

'''
jao = JaoLoader()
date_range = pd.date_range(datetime(2017, 1, 1), datetime(2023, 1, 1), freq='YS')
#auct_dict = jao.auction_loader(['de_fr'], date_range, 'm')
company = 'etc'
date_list = [datetime(2023, 8, 1)]
#jao_dict = jao.company_auction_loader([company], date_list, 'm')
jao_dict = jao.auction_info_loader('m', datetime(2023,9,1),
                                   from_date=datetime(2023,8,19), to_date=datetime(2023,8,26))
'''
