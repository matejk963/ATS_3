"""
Base class for handling input data used in the a/m/f

Basic inputs:
    params_dict: dict of standardized params defining contracts
    params_dict = {'market_list': [list of markets/grids],
                    'product_list': [list of products either relative: M_1 => front month(only current or continous
                                                                        based on 'cont' condition)/
                                                    or absolute:  M.1 => January],
                    'delivery_list': [list of delivery of products: 'base'/'peak'],
                    'year_list': [list of years of the products/ None for relative products],
                    'sD': datetime(y,m,d) of start of the series,
                    'eD': datetime(y,m,d) of end of series,
                    'cont': bool for fething the continouse contracts
                    }
                    
Class responsibility:
    Prepare parameters from params_dict for the rest of the classes
    Hold common properties
    """

import pandas as pd
import numpy as np
import datetime as dt
from dateutil.relativedelta import relativedelta
import copy
from Utilities.date_functions import start_date, end_date
# from fund_analysis.data_loader import DataLoader as data_loader

live_price_path = 'T:\LiveScreen_v01.xlsx'

class InputData:
    start_date_list = []
    end_date_list = []
    unique_markets_list = []
    
    def __init__(self,params_dict):
        self._params_dict = params_dict
        self._original_params_dict = copy.deepcopy(params_dict)
        from fund_analysis.data_loader import DataLoader as data_loader
        self._data_loader = data_loader(params_dict)
        self._pivot_date = params_dict['eD']
        self.transform_and_update_params_dict()
        self.get_curve_start_end_date()
        
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def original_params_dict(self):
        return self._original_params_dict
    
    # Properties dierctly from params_dict
    @property
    def market_list(self):
        return self.params_dict['market_list']
    
    @property
    def product_list(self):
        return self.params_dict['product_list']
    
    @property
    def delivery_list(self):
        return self.params_dict['delivery_list']
    
    @property
    def year_list(self):
        return self.params_dict['year_list']
    
    @property
    def sD(self):
        return self.params_dict['sD']
    
    @property
    def eD(self):
        return self.params_dict['eD']
    
    @property
    def cont(self):
        return self.params_dict['cont']
    
    @property
    def data_loader(self):
        return self._data_loader
    
    @property
    def pivot_date(self):
        # Check if eD is a business day, if not, shift 1 business day back
        if pd.Timestamp(self.eD).weekday() >= 5:  # If it's Saturday (5) or Sunday (6)
            return self._pivot_date - pd.tseries.offsets.BDay(1)  # Shift to previous business day
        else:
            return self._pivot_date

    
    @property
    def unique_markets(self):
        if len(self.unique_markets_list) < 1:
            return list(np.unique(self.params_dict['market_list']))
        else:
            return self.unique_markets_list
    
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
    def update_params_dict(self, new_params_dict):
        self._params_dict = new_params_dict
        self.reset_variables
        
    def set_pivot_date(self, new_pivot_date):
        self._pivot_date = new_pivot_date
        
    def update_params(self, new_pivot_date):
        self.set_pivot_date(new_pivot_date)
        self.transform_and_update_params_dict()
    
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
    
    
        
    def products_start_and_end_dates(self):
        start_date_list = []
        end_date_list = []
        for product, delivery, year in zip(self.product_list,
                                            self.delivery_list,
                                            self.year_list):
            aux_start, aux_end = self.get_start_end_product_date(product,
                                                                    delivery,
                                                                    year)
            self.start_date_list.append(aux_start)
            self.end_date_list.append(aux_end)
        
        
    def get_curve_start_end_date(self):
        self.curve_start_date = self.pivot_date
        self.curve_end_date = None
        if len(self.start_date_list) < 1:
            self.products_start_and_end_dates()
        
        for aux_start, aux_end in zip(self.start_date_list,
                                    self.end_date_list):
            if self.curve_end_date is None:
                self.curve_end_date = aux_end
            else:
                if self.curve_end_date < aux_end:
                    self.curve_end_date = aux_end
                    
    def get_start_end_product_date(self, product, delivery, year):
        if '.' in product:
            period, tenor = product.split('.')
            tenor = int(tenor)
            if period in ['m', 'M']:
                del_start = dt.datetime(int(year), int(tenor), 1)
                del_end = del_start + relativedelta(months=1) - dt.timedelta(hours=1)
            elif period in ['q', 'Q']:
                del_start = dt.datetime(int(year), int(tenor) * 3 - 2, 1)
                del_end = del_start + relativedelta(months=3) - dt.timedelta(hours=1)
            elif period in ['y', 'Y']:
                del_start = dt.datetime(int(year), 1, 1)
                del_end = del_start + relativedelta(months=12) - dt.timedelta(hours=1)
            elif period.lower() in ['w', 'wk']:
                del_start = self.get_start_date_from_week(year, tenor)
                del_end = del_start + dt.timedelta(days=7) - dt.timedelta(hours=1)
            elif period.lower() in ['wknd']:
                del_start = self.get_start_date_from_week(year, tenor) + dt.timedelta(days=5)  # Saturday
                del_end = del_start + dt.timedelta(days=1) + dt.timedelta(hours=23, minutes=59)  # End of Sunday
            elif period.lower() in ['d', 'da']:
                del_start = dt.datetime(year, 1, 1) + relativedelta(days=tenor - 1)  # Adjust for offset
                del_end = del_start + dt.timedelta(hours=23, minutes=59, seconds=59)  # End of day
        else:
            del_start = start_date(self.pivot_date, product)
            del_end = end_date(self.pivot_date, product)
    
        # Uncomment the following lines if specific delivery adjustments are needed
        # if delivery in ['peak']:
        #     del_end = self.get_nearest_older_business_day(del_end)
        
        return del_start, del_end

    
    @staticmethod
    def get_start_date_from_week(year, week_number):
        # Create a date object for January 1st of the given year
        jan_1 = dt.datetime(year, 1, 1)
        # Calculate the number of days to the first Monday of the year
        days_to_monday = (7 - jan_1.weekday()) % 7  # 0 represents Monday
        # Calculate the start of the week in ISO terms (adjust to the first Monday)
        start_of_iso_week = jan_1 + dt.timedelta(days=days_to_monday)
        # Calculate the start date of the given week number, subtract 1 from week_number because timedelta weeks starts from 0
        start_date_of_week = start_of_iso_week + dt.timedelta(weeks=week_number - 1)
        # Return the start date as a datetime object (no need to convert to pandas datetime unless specifically needed)
        return start_date_of_week
    
    def get_futures_periods(self):
        fut_periods_list = []
        if len(self.start_date_list) < 1:
            self.products_start_and_end_dates()
        for del_start, del_end in zip(self.start_date_list,
                                        self.end_date_list):
            fut_periods_list.append((del_end - self.pivot_date).total_seconds()//3600 + 1)
            
        return max(fut_periods_list)
    
    def get_future_week_number(self, weeks_ahead):
        # Calculate the future date by adding the specified number of weeks to the current date
        future_date = self.pivot_date + dt.timedelta(weeks=weeks_ahead)
        # Return the ISO week number of the future date
        return future_date.isocalendar()[1]  
    
    def transform_and_update_params_dict(self):
        new_params_dict = self.transform_params_dict(self.pivot_date)
        self.update_params_dict(new_params_dict)  
    
    def transform_params_dict(self, pivot):
        base_dict = copy.deepcopy(self.original_params_dict)
        products_list = base_dict['product_list']
        rel_tenors_list = [a.split('_')[1] for a in products_list]
        periods_list = [a.split('_')[0] for a in products_list]
        
        # Calculate start dates
        dates_list = [
            start_date(pivot, product) if product.lower() not in ['wk', 'wknd']
            else start_date(pivot, 'w') if product.lower() in ['wk']
            else None
            for product in products_list
        ]
        
        # Calculate fixed tenors
        fix_tenor_list = [
            self.get_future_week_number(int(c)) if b.lower() in ['w', 'wk', 'wknd']
            else a.day if b in ['D']  # For daily products, use the day of the month
            else a.month if b in ['M']
            else (a.month - 1) // 3 + 1 if b in ['Q']
            else 1 if b in ['Y']
            else None
            for a, b, c in zip(dates_list, periods_list, rel_tenors_list)
        ]
        
        # Transform product list and extract years
        transformed_products_list = [
            a + '.' + str(b) for a, b in zip(periods_list, fix_tenor_list)
        ]
        transformed_years_list = [a.year for a in dates_list]
        
        # Update and return the transformed dictionary
        new_dict = base_dict
        new_dict['product_list'] = transformed_products_list
        new_dict['year_list'] = transformed_years_list
        return new_dict

        
    
    # DayAhead data
    def da_vector(self, df):
        out_df = df.unstack().reset_index()
        out_df.columns = ['hours', 'forecast_date', 0]
        out_df['value_date'] = out_df['forecast_date'] + pd.to_timedelta(out_df['hours'], unit='h')
        out_df = out_df.sort_values('value_date')
        out_df = out_df.loc[((out_df['hours']>23)&
                                (out_df['hours']<48))].copy()
        out_df = out_df[['value_date', 0]].copy()
        out_df = out_df.rename(columns={0: self.fund_type})
        out_df.set_index('value_date',inplace=True)
        return out_df