#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun May 14 16:19:26 2023

@author: marek
"""

import pandas as pd
from dateutil.relativedelta import relativedelta
from Utilities.delivery_class import Delivery
from datetime import datetime, timedelta


def end_date(date_time, period):
    #date_time = start_date(date_time, period)
    period_list = period.split('_')
    period = period_list[0]

    if period in ['D', 'd', 'DA', 'da']:
        end_date = date_time + relativedelta(days=1, hours=-1)
    elif period in ['W', 'w']:
        end_date = date_time + relativedelta(days=7, hours=-1)
    elif period in ['BoM']:
        end_date = pd.date_range(start_date, freq='M', periods=1)[0].to_pydatetime()
    elif period in ['M', 'm']:
        end_date = date_time + relativedelta(months=1, hours=-1)
    elif period in ['Q', 'q']:
        end_date = date_time + relativedelta(months=3, hours=-1)
    elif period in ['SUM', 'sum', 'WIN', 'win']:
        end_date = date_time + relativedelta(months=6, hours=-1)
    elif period in ['Y', 'y']:
        end_date = date_time + relativedelta(months=12, hours=-1)
    else:
        raise ValueError('Unknown period %s' % period)
    return end_date


def start_date(date_time, period):
    date_time += relativedelta(days=1)
    period_list = period.split('_')
    if len(period_list) == 1:
        period = period_list[0]
        num = 1
    elif len(period_list) == 2:
        period = period_list[0]
        num = int(period_list[1])
    else:
        raise ValueError('Unknown period %s' % period)

    if period in ['D', 'd']:
        return date_time + relativedelta(days=num - 1)
    elif period in ['DA', 'da']:
        return pd.date_range(date_time, freq='B', periods=1)[-1].to_pydatetime()
    elif period in ['BoM']:
        return start_date(date_time, 'D') + relativedelta(days=num)
    elif period.lower() in ['w', 'wk']:
        return date_time + timedelta(weeks=num) - timedelta(days=date_time.weekday())
    elif period in ['M', 'm']:
        if num == 0:
            date_time -= relativedelta(days=1)
            return start_date(date_time, 'M_1') + relativedelta(months=-1)
        else:
            return pd.date_range(date_time, freq='MS', periods=num)[-1].to_pydatetime()
    elif period in ['Q', 'q']:
        if num == 0:
            date_time -= relativedelta(days=1)
            return start_date(date_time, 'Q_1') + relativedelta(months=-3)
        else:
            return pd.date_range(date_time, freq='QS', periods=num)[-1].to_pydatetime()
    elif period in ['SUM', 'sum', 'WIN', 'win']:
        pass
    elif period in ['Y', 'y']:
        if num == 0:
            date_time -= relativedelta(days=1)
            return start_date(date_time, 'Y_1') + relativedelta(months=-12)
        else:
            return pd.date_range(date_time, freq='YS', periods=num)[-1].to_pydatetime()
    elif period in ['Wknd', 'wknd']:
        # Calculate the start of the weekend (Saturday)
        saturday = date_time + relativedelta(days=(5 - date_time.weekday()) + 7 * (num - 1))
        return saturday
    else:
        raise ValueError('Unknown period %s' % period)

    return start_date


def create_mask(datetime, tenor_list, delivery_list):
    sD_list = [start_date(datetime, t) for t in tenor_list]
    eD_list = [end_date(datetime, t) for t in tenor_list]
    date_range_list = [pd.date_range(s, e, freq='H') for s, e in zip(sD_list, eD_list)]
    ser_list = [pd.Series(getattr(Delivery(d_r), d).astype(int), index=d_r)
                for d_r, d in zip(date_range_list, delivery_list)]
    df_mask = pd.DataFrame(ser_list)
    df_mask.fillna(0, inplace=True)
    return df_mask.T


def date_dayahead(date):
    day_of_week = date.weekday()
    result_date = None
    if day_of_week < 4:
        result_date = date + timedelta(days=1)
    elif day_of_week == 4:
        result_date = date + timedelta(days=3)
    elif day_of_week == 5:
        result_date = date + timedelta(days=2)
    elif day_of_week == 6:
        result_date = date + timedelta(days=1)
    return result_date

def date_weekahead(date):
    day_of_week = date.weekday()
    delta = 7-day_of_week
    return (date + timedelta(days=delta))
        
