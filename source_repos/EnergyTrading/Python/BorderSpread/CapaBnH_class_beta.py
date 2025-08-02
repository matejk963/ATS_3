# -*- coding: utf-8 -*-
"""
Created on Thu Nov 30 15:42:09 2023

@author: krajcovic
"""

"""
Class for auctions of country trans capacities
Main functions:
    fetching capa fair values
    fetching capa deltas for hedging
    sumarizing fv and deltas
    creating excel spreadsheet:
        sheet1 capa fv and deltas table
        sheet2 table for inserting positions,
            computing hedges and summarizing the net positions for each country
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import date, datetime, timedelta

from refinitiv import data as rd

import re
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string,get_column_letter
from openpyxl.worksheet.cell_range import CellRange
import xlwings as xw

import BorderSpread.border_class as bs
import BorderSpread.capacity_class as capa
from BorderSpread.PositionManager import PositionManagerCapa, PositionManagerHedge
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
from Loaders.EikonSpot_class import EikonSpot as es
from Loaders.EikonFut_class import EikonFut as ef
from Loaders.loader_web import JaoLoader as JL
from Utilities.date_functions import end_date, start_date


class CapaBnH:    
    def __init__(self,history_start,
                 history_end=None,
                 capa_type='M',
                 data_aggregation='M',
                 auction_date=datetime.today(),
                 border_type = ['implicit'],
                 delivery = ['base'],
                 hedge_market_list=['de', 'at', 'fr', 'hu', 'cz']):
        self._history_start = history_start
        self._history_end = history_end        
        self._capa_type = capa_type
        self._data_aggregation=data_aggregation
        self._auction_date = auction_date
        self._bs_class = None
        self._border_type = border_type
        self._delivery = delivery
        self._border_list = None
        self._hedge_market_list = hedge_market_list
        self._aux_capa_type = None
        
    def set_borders_list(self, borders_list):
        self._border_list = borders_list
        
    @property
    def history_start(self):
        return self._history_start
    @property
    def history_end(self):
        if self._history_end is None:
            return self.auction_date - timedelta(days=-1,
                                                 hours=1)
        else:
            return self._history_end - timedelta(days=-1,
                                                 hours=1)
    @property
    def border_list(self):
        return self._border_list
    @property
    def capa_type(self):
        return self._capa_type
    @property
    def aux_capa_type(self):
        return self._aux_capa_type
    @property
    def data_aggregation(self):
        return self._data_aggregation
    @property
    def auction_date(self):
        return self._auction_date
    @property
    def border_type(self):
        return self._border_type
    @property
    def delivery(self):
        return self._delivery
    @property
    def hedge_market_list(self):
        return self._hedge_market_list
    
    @property
    def capa_start(self):
        if self._aux_capa_type==None:
            return start_date(self.auction_date, self.capa_type)
        else:
            return start_date(self.auction_date, self.aux_capa_type)
    
    @property
    def capa_end(self):        
        if self._aux_capa_type==None:
            return end_date(self.auction_date, self.capa_type)
        else:
            return end_date(self.auction_date, self.aux_capa_type)
    
    @property
    def capa_settle_range(self):
        return pd.date_range(start=self.capa_start,
                             end=self.capa_end,
                             freq='D', inclusive='both',
                             normalize=True)
    
    @property
    def synthetic_capa_dict(self):
        pass
    
    @property
    def period_dict(self):
        my_dict = {}
        my_dict['W'] = 7
        my_dict['M'] = 30
        my_dict['Q'] = 91
        my_dict['Y'] = 365
        return my_dict
        
    @property
    def fut_product_name(self):
        if self.capa_type.upper() == 'M':
            return self.capa_type.upper() + '.' + str(self.capa_start.month)
        if self.capa_type.upper() == 'Q':
            return self.capa_type.upper() + '.' + str((self.capa_start.month-1)//3+1)
    
    @property
    def fut_year_list(self):
        return [self.capa_start.year]
    
    def reset_capa_type(self, new_capa_type):
        self._capa_type = new_capa_type
        
    def set_aux_capa_type(self, aux_capa_type):
        if aux_capa_type == 'Q_3':
            print('debug')
        self._aux_capa_type = aux_capa_type
        
        
    def get_scaling(self):
        return self.period_dict[self.capa_type]//\
            self.period_dict[self.data_aggregation]
    
    def border_class_init(self,border):
        self._bs_class = bs.DataBorderClass([border], self.border_type,
                                            start_date=self.history_start,
                                            end_date=self.history_end)
        self._bs_class.load_data()
    
    def bs_agg_data(self):
        self._data = dict()
        for del_ in self.delivery:
            self._data[del_] = self._bs_class.aggregate_data(self.data_aggregation,
                                                             delivery=del_)
    
    
    def capa_fit(self, border):
        self._capacity = capa.ImplicitCapacity([border], self.delivery)
        for b in border:
            for del_ in self.delivery:
                self._capacity.capa_fit(self._data[del_], del_, scaling=self.get_scaling())
                
    def divide_borders(self):
        return [a.split('_') for a in self.border_list]   
    
    
    def fut_settle_check(self, fut_out_df,fut_in_df,
                         fut_out_ric, fut_in_ric):
        #check if the futures prices are of the same settlement
        
        fut_out_list = [fut_out_df.index[0],
                        fut_out_df[fut_out_df.columns[0]][0]]
        fut_in_list = [fut_in_df.index[0],
                        fut_in_df[fut_in_df.columns[0]][0]]
        
        if fut_out_list[0] != fut_in_list[0]:
            if any(len(fut_out_ric)>1, len(fut_in_ric)>1):
                fut_out_df1 = rd.get_history(fut_out_ric[0][0],
                                         ['SETTLE'],
                                         start=self.auction_date-timedelta(days=10),
                                         count=20)
                fut_out_df2 = rd.get_history(fut_out_ric[0][1],
                                         ['SETTLE'],
                                         start=self.auction_date-timedelta(days=10),
                                         count=20)
                fut_out_df = pd.concat([fut_out_df1, fut_out_df2], axis=1, join='inner')
                fut_out_df['sum'] = fut_out_df.sum(axis=1)
                fut_out_df = fut_out_df[['sum']]
                fut_out_df = fut_out_df.loc[:self.auction_date].iloc[-2:-1]
                fut_in_df1 = rd.get_history(fut_in_ric[0][0],
                                         ['SETTLE'],
                                         start=self.auction_date-timedelta(days=10),
                                         count=20)
                fut_in_df2 = rd.get_history(fut_in_ric[0][1],
                                         ['SETTLE'],
                                         start=self.auction_date-timedelta(days=10),
                                         count=20)
                fut_in_df = pd.concat([fut_in_df1, fut_in_df2], axis=1, join='inner')
                fut_in_df['sum'] = fut_in_df.sum(axis=1)
                fut_in_df = fut_in_df[['sum']]
                fut_in_df = fut_in_df.loc[:self.auction_date].iloc[-2:-1]
            else:
                min_date = min(fut_out_list[0],
                               fut_in_list[0])
                rd.open_session()
                fut_out_df = rd.get_history(fut_out_ric,
                                         ['SETTLE'],
                                         start=min_date)
                fut_in_df = rd.get_history(fut_in_ric,
                                         ['SETTLE'],
                                         start=min_date)
                rd.close_session()
                fut_out_list = [fut_out_df.index[0],
                                fut_out_df[fut_out_df.columns[0]][0]]
                fut_in_list = [fut_in_df.index[0],
                                fut_in_df[fut_in_df.columns[0]][0]]
            
        return fut_out_list, fut_in_list
        
    
    def get_fut_prices(self,out_b, in_b):
        
        #initialize fut objects
        fut_out_obj = ef(out_b)
        fut_in_obj = ef(in_b)
        last_date = self.auction_date - timedelta(hours=1)
        #get futures rics
        fut_out_ric = fut_out_obj.fwd_code_creator([self.fut_product_name],
                                         self.delivery,
                                         self.fut_year_list)
        fut_in_ric = fut_in_obj.fwd_code_creator([self.fut_product_name],
                                         self.delivery,
                                         self.fut_year_list)
        #get futures prices
        rd.open_session()
        
        if 'dk' in out_b:
            fut_out_df1 = rd.get_history(fut_out_ric[0][0],
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_out_df2 = rd.get_history(fut_out_ric[0][1],
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_out_df = pd.concat([fut_out_df1, fut_out_df2], axis=1, join='inner')
            fut_out_df['sum'] = fut_out_df.sum(axis=1)
            fut_out_df = fut_out_df[['sum']]
            fut_out_df = fut_out_df[:last_date].iloc[[-1]]
        else:
            fut_out_df = rd.get_history(fut_out_ric,
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_out_df = fut_out_df[:last_date].iloc[[-1]]
        if 'dk' in in_b:
            fut_in_df1 = rd.get_history(fut_in_ric[0][0],
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_in_df2 = rd.get_history(fut_in_ric[0][1],
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_in_df = pd.concat([fut_in_df1, fut_in_df2], axis=1, join='inner')
            fut_in_df['sum'] = fut_in_df.sum(axis=1)
            fut_in_df = fut_in_df[['sum']]
            fut_in_df = fut_in_df[:last_date].iloc[[-1]]
        else:        
            fut_in_df = rd.get_history(fut_in_ric,
                                     ['SETTLE'],
                                     start=self.auction_date-timedelta(days=10),
                                     count=20)
            fut_in_df = fut_in_df[:last_date].iloc[[-1]]
        rd.close_session()
                
        return self.fut_settle_check(fut_out_df,fut_in_df,
                                     fut_out_ric, fut_in_ric)
    
    def get_capa_data_list(self):
        border_list = []
        out_list = []
        in_list = []
        settle_date_out_list = []
        settle_date_in_list = []        
        fut_out_list = []
        fut_in_list = []
        spread_list = []
        capa_fv_list = []
        delta_list = []
        fut_period_list = []
        for border, div_borders in zip(self.border_list,
                                       self.divide_borders()):
            out_b, in_b = div_borders[0], div_borders[1]
            self.border_class_init(border)
            self.bs_agg_data()
            self.capa_fit(border)
            fut_out_list_aux, fut_in_list_aux = self.get_fut_prices(out_b, in_b)
            settle_out, fut_out = fut_out_list_aux
            settle_in, fut_in = fut_in_list_aux
            
            assert settle_out == settle_in, 'settle dates are not equal'
            
            border_list.append(border)
            out_list.append(out_b)
            in_list.append(in_b)
            settle_date_out_list.append(settle_out)
            settle_date_in_list.append(settle_in)            
            fut_out_list.append(fut_out)
            fut_in_list.append(fut_in)
            spread_list.append(float(fut_in)-
                                     float(fut_out))
            capa_fv_list.append(self._capacity.capa_price(fut_out,
                                                   fut_in,
                                                   self.delivery[0])[1])
            delta_list.append(self._capacity.capa_delta(fut_out,
                                                   fut_in,
                                                   self.delivery[0])[1])
            fut_period_list.append(self.fut_product_name)
            
        return [border_list,
                out_list,
                in_list,
                settle_date_out_list,
                settle_date_in_list,
                fut_out_list,
                fut_in_list,
                spread_list,
                capa_fv_list,
                delta_list,
                fut_period_list]
            
        
    def process_list_to_df(self):
        
        master_list = self.get_capa_data_list()
        headers = ['border', 'market_out', 'market_in',
                   'settle_date_out', 'settle_date_in',
                   'fut_out', 'fut_in', 'spread',
                   'capa_fv', 'delta', 'fut_products']
        df = pd.DataFrame({f'Column{i}': col for i, col
                             in enumerate(master_list, start=1)})
        df.columns=headers
        df['ext'] = np.where(df['spread']<0, df['capa_fv'],
                             df['capa_fv']-df['spread'])
        cols = df.columns.tolist()  # Get the list of columns
        cols.insert(cols.index('delta'), cols.pop(cols.index('ext')))
        cols.insert(cols.index('fut_out'), cols.pop(cols.index('fut_products')))
        df = df[cols]
        
        return df
    
    def aggregate_capa_types(self):
        original_type = self.capa_type
        if self.capa_type == 'Y':
            capa_results_dict = {}
            for new_prod in ['Q_1', 'Q_2', 'Q_3', 'Q_4']:
                new_type, new_period = new_prod.split('_')
                self.reset_capa_type(new_type)
                self.set_aux_capa_type(new_prod)
                capa_results_dict[new_prod] = self.process_list_to_df()
        self.reset_capa_type(original_type)
                
        return capa_results_dict
    
    @staticmethod
    def merge_and_process(dfs, merge_cols, datetime_cols,
                                   float_cols, weighting_col):
        
        q_hours = {'Q.1': 91*24-1,
                   'Q.2': 91*24,
                   'Q.3': 92*24,
                   'Q.4': 92*24+1}
        
        comp_df = None
        for df in dfs.values():
            if comp_df is None:
                comp_df = df.copy()
            else:
                comp_df = pd.concat([comp_df,df], axis=0)
        comp_df[weighting_col] = comp_df[weighting_col].map(q_hours)
        # comp_df = comp_df.drop([weighting_col],axis=1)
        
        def weighted_averages(group, value_columns, weight_column):
            results = {}
            for value_column in value_columns:
                d = group[value_column]
                w = group[weight_column]
                try:
                    results[value_column] = (d * w).sum() / w.sum()
                except ZeroDivisionError:
                    results[value_column] = None
            return pd.Series(results)
                
        # comp_df = comp_df.groupby(merge_cols).mean()
        comp_df = comp_df.groupby(merge_cols).apply(weighted_averages,
                                                    float_cols, weighting_col).reset_index()
        
        
        return comp_df
                             
    
    def create_excel(self, file_path):
        if self.capa_type == 'M':
            self.process_list_to_df().to_excel(file_path,
                                              index=False,
                                              sheet_name='fv')
        else:
            self.merge_and_process(self.aggregate_capa_types(),
                                   merge_cols=['border', 'market_out', 'market_in','settle_date_out', 'settle_date_in'],
                                   datetime_cols=['settle_date_out', 'settle_date_in'],
                                   float_cols=['fut_out', 'fut_in', 'spread', 'capa_fv', 'ext', 'delta'],
                                   weighting_col='fut_products').to_excel(file_path,
                                                                     index=False,
                                                                     sheet_name='fv')
    def create_hedge_pos(self, file_path):  
        import pandas as pd
        from openpyxl import load_workbook
        
        # Load the source table from an Excel file
        source_file_path = file_path  # Replace with your source file path
        source_df = pd.read_excel(source_file_path, sheet_name='fv')
        
        # Map the source DataFrame to the target DataFrame
        target_df = pd.DataFrame()
        target_df['border'] = source_df['border']
        target_df['long_market'] = source_df['market_out']
        target_df['short_market'] = source_df['market_in']
        target_df['capa_pos'] = ''  # Leave blank as instructed
        target_df['delta'] = source_df['delta']
        
        # Assuming 'capa_pos' is to be filled later and is not 'capa_fv' from the source
        # We will create a formula for 'fut_pos' as a string that will be written to Excel
        # Here we are using a formula that references the row number dynamically using Excel's ROW() function
        target_df['fut_pos'] = '=IF(ISBLANK(C' + (target_df.index + 2).astype(str) + '), "", D' + (target_df.index + 2).astype(str) + ' * E' + (target_df.index + 2).astype(str) + ')'
        
        # Load the workbook and add a new sheet with the target DataFrame
        target_sheet_name = 'Total_Positions'  # Name of the new sheet
        book = load_workbook(source_file_path)
        writer = pd.ExcelWriter(source_file_path, engine='openpyxl')
        writer.workbook = book
        
        # # Ensure there's at least one visible sheet
        # if not any(sheet.sheet_state == 'visible' for sheet in book.worksheets):
        #     raise Exception("All sheets are hidden. At least one sheet must be visible.")
        
        # # Create a Pandas Excel writer using the openpyxl engine
        # with pd.ExcelWriter(source_file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        #     writer.workbook = book
        
        #     # If the target sheet already exists, remove it
        #     if target_sheet_name in writer.book.sheetnames:
        #         del writer.book[target_sheet_name]
        
        #     # Assuming 'df' is the DataFrame you want to write
        #     df.to_excel(writer, sheet_name=target_sheet_name)
        
        # If the target sheet already exists, remove it
        if target_sheet_name in book.sheetnames:
            del book[target_sheet_name]
        
        # Write the target DataFrame to the new sheet
        target_df.to_excel(writer, sheet_name=target_sheet_name, index=False)
        
        # Save the workbook
        # writer.save()
        
    def create_net_hedge(self, file_path):
        import pandas as pd
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        
        # Load the workbook
        wb = load_workbook(file_path)
        
        # Assume 'target_df' is in a sheet named 'TargetSheet' of the workbook
        target_sheet_name = 'Total_Positions'
        if target_sheet_name not in wb.sheetnames:
            wb.create_sheet(target_sheet_name)
        target_sheet = wb[target_sheet_name]
        
        # Create or clear the 'Market_Summary' sheet
        summary_sheet_name = 'Market_Summary'
        if summary_sheet_name in wb.sheetnames:
            wb.remove(wb[summary_sheet_name])
        wb.create_sheet(summary_sheet_name)
        summary_sheet = wb[summary_sheet_name]
        
        # Define the columns in the target sheet where data is located
        long_market_col = 'B'  # Assuming 'long_market' is in column B
        short_market_col = 'C'  # Assuming 'short_market' is in column C
        fut_pos_col = 'F'  # Assuming 'fut_pos' is in column F
        
        # Assuming that 'target_df' DataFrame is already created and filled with data
        # If you need to read it from the sheet, you can use pandas
        target_df = pd.read_excel(file_path,
                                  sheet_name=target_sheet_name)
        
        # Find unique markets from 'long_market' and 'short_market' columns in target_df
        unique_markets = pd.unique(target_df['long_market'].tolist() + target_df['short_market'].tolist())
        
        # Write headers to the summary sheet
        summary_sheet.append(['Market', 'Net Position'])
        
        # Write Excel formulas for each market
        row_num = 2
        for market in unique_markets:
            if market in self.hedge_market_list:
                cell_market = summary_sheet.cell(row=row_num, column=1)
                cell_market.value = market
            
                cell_net_pos = summary_sheet.cell(row=row_num, column=2)
                
                # Construct the SUMIF formulas
                long_formula = f"=SUMIF('{target_sheet_name}'!${long_market_col}:${long_market_col}, \"{market}\", " \
                               f"'{target_sheet_name}'!${fut_pos_col}:${fut_pos_col})"
                short_formula = f"-SUMIF('{target_sheet_name}'!${short_market_col}:${short_market_col}, \"{market}\", " \
                                f"'{target_sheet_name}'!${fut_pos_col}:${fut_pos_col})"
                
                cell_net_pos.value = f"{long_formula} + {short_formula}"
            
                row_num += 1
            else:
                continue
        
        # Save the workbook
        wb.save(file_path)
        
        
    
    
    
    
    
    def convert_to_relative(self, cell_ref, base_row, base_col):
        """
        Convert a cell reference to relative address from a base row and column.
        """
        match = re.match(r"((?:\w+!)?)(\$?[A-Z]+)(\$?\d+)", cell_ref)
        if not match:
            return None
    
        sheet, col, row = match.groups()
        col_index = column_index_from_string(col.strip('$')) - base_col
        row_index = int(row.strip('$')) - base_row
    
        return sheet, col_index, row_index
    
    
    def convert_to_stringint(self, sheet, col_offset, row_offset, base_row, base_col):
        """
        Convert relative address back to 'StringInt' format.
        """
        new_col = get_column_letter(base_col + col_offset)
        new_row = base_row + row_offset
    
        return f"{sheet}{new_col}{new_row}"
    
    @staticmethod
    def is_ref_in_excluded_range(ref, excluded_ranges):
        """
        Check if a cell reference is exactly within any of the excluded ranges.
        """
        for range_str in excluded_ranges:
            if '!' in range_str:
                sheet, range_part = range_str.split('!')
                if ref.startswith(sheet + '!'):
                    cell_range = CellRange(range_part)
                    if any(ref == f"{sheet}!{cell}" for cell in cell_range.cells):
                        return True
                
            else:
                cell_range = CellRange(range_str)
                if any(ref == cell for cell in cell_range.cells):
                    return True
        return False
    


        

    @property
    def formulas_dict(self):
        form = {}
        form['B3'] = '=INDEX(fv!$A$2:$AL$50;MATCH(Bidding!A9;fv!$A$2:$A$50;0);MATCH(Bidding!A3;fv!$A$1:$AL$1;0))'
        form['B4'] = '=ROUND(INDEX(fv!$A$2:$AL$50;MATCH(Bidding!A9;fv!$A$2:$A$190;0);MATCH(Bidding!A4;fv!$A$1:$AL$1;0));2)'
        form['A11'] = '=IF(B11="";"";ROUNDDOWN(C12/B8/B11;0))'
        form['B11'] = '=IF(B5="";"";B12+B5)'
        form['C11'] = '=IFERROR(A11*B11*B8;"")'
        form['A12'] = '=B6'
        form['B12'] = '=ROUND(INDEX(fv!$A$2:$AL$50;MATCH(Bidding!A9;fv!$A$2:$A$190;0);MATCH("capa_fv";fv!$A$1:$AL$1;0));2)'
        form['A13'] = '=IFERROR(IF(IF(B12>ROUNDDOWN(C12/B8/(A12+1);2);\
            A12+1;ROUNDDOWN(C12/B8/B12-0,01;0))<=B7;IF(B12>ROUNDDOWN(C12/B8/(A12+1);2);\
                                                       A12+1;ROUNDDOWN(C12/B8/B12-0,01;0));"");"")'
        form['B13'] = '=IFERROR(IF(B12>ROUNDDOWN(C12/B8/(A13);2);\
            ROUNDDOWN(C12/B8/(A13);2);B12-0,01);"")'
        return form
    
    
    @staticmethod
    def a1_to_r1c1(cell_address, base_cell_address):
        """
        Convert a cell address in A1 format to R1C1 format relative to a base cell address.
        """
        # Extract column and row from both addresses
        col_ref, row_ref = re.match(r'(\$?[A-Z]+)(\$?\d+)', cell_address).groups()
        base_col_ref, base_row_ref = re.match(r'(\$?[A-Z]+)(\$?\d+)', base_cell_address).groups()
    
        # Convert column letters to numbers
        col_num = column_index_from_string(col_ref.replace('$', ''))
        base_col_num = column_index_from_string(base_col_ref.replace('$', ''))
    
        # Determine absolute or relative column
        if '$' in col_ref:
            col_r1c1 = f"C{col_num}"
        else:
            relative_col = col_num - base_col_num
            col_r1c1 = f"C[{relative_col}]"
    
        # Determine absolute or relative row
        if '$' in row_ref:
            row_r1c1 = f"R{row_ref.replace('$', '')}"
        else:
            relative_row = int(row_ref) - int(base_row_ref.replace('$', ''))
            row_r1c1 = f"R[{relative_row}]"
    
        return f"{row_r1c1}{col_r1c1}"
    
    @staticmethod
    def r1c1_to_a1(r1c1_address, base_cell_address):
        """
        Convert a cell address in R1C1 format to A1 format relative to a base cell address.
        """
        # Extract relative or absolute row and column parts
        row_part, col_part = re.match(r'(R\[?-?\d*\]?)(C\[?-?\d*\]?)', r1c1_address).groups()
    
        # Extract base cell column and row
        base_col_letter, base_row_num = re.match(r'([A-Z]+)(\d+)', base_cell_address).groups()
        base_col_num = column_index_from_string(base_col_letter)
        base_row_num = int(base_row_num)
    
        # Convert row part
        if '[' in row_part:
            rel_row_offset = int(re.search(r'\[(-?\d+)\]', row_part).group(1))
            row_num = base_row_num + rel_row_offset
        else:
            row_num = int(re.search(r'R(\d+)', row_part).group(1))
    
        # Convert column part
        if '[' in col_part:
            rel_col_offset = int(re.search(r'\[(-?\d+)\]', col_part).group(1))
            col_num = base_col_num + rel_col_offset
        else:
            col_num = int(re.search(r'C(\d+)', col_part).group(1))
    
        return f"{get_column_letter(col_num)}{row_num}"
    

    
    def formula_a1_to_r1c1(self, formula, base_cell_address):
        """
        Convert a formula in A1 format to R1C1 format relative to a base cell address,
        ensuring that existing R1C1 references are not incorrectly altered.
        """

        def replace_with_r1c1(match):
            col_ref, row_ref = match.groups()
            cell_address = f"{col_ref}{row_ref}"
            # Check if this is part of an R1C1 reference
            if formula[match.start() - 1:match.start()] == 'R' or \
               formula[match.end():match.end() + 1] == 'C':
                return cell_address  # If so, do not replace
            r1c1_address = self.a1_to_r1c1(cell_address, base_cell_address)
            return r1c1_address

        # Modified regex to match A1 cell references
        cell_refs_pattern = r'(\$?[A-Z]{1,3})(\$?\d+)'
        formula = re.sub(cell_refs_pattern, replace_with_r1c1, formula)

        return formula

    
    
    def formula_r1c1_to_a1(self, formula, base_cell_address):
        """
        Convert a formula in R1C1 format to A1 format relative to a base cell address.
        """

        def replace_with_a1(match):
            row_ref = match.group(1)
            col_ref = match.group(2)
            r1c1_address = f"R{row_ref}C{col_ref}"
            return self.r1c1_to_a1(r1c1_address, base_cell_address)

        # Use re.sub with a function for targeted replacement
        return re.sub(r'R(\[?-?\d*\]?)C(\[?-?\d*\]?)', replace_with_a1, formula)
    
    def shift_formula(self, formula, from_cell, to_cell,
                      fixed_cells=None, fixed_cells_shift=None):
        if fixed_cells:
            formula = self.make_references_absolute(formula, fixed_cells)
        formula = self.formula_a1_to_r1c1(formula, from_cell)
        formula = self.formula_r1c1_to_a1(formula, to_cell)
        if fixed_cells_shift:
            formula = self.make_references_absolute(formula, fixed_cells_shift)
        return formula
        
    def shift_cell(self, cell, from_cell, to_cell):
        cell = self.a1_to_r1c1(cell, from_cell)
        cell = self.r1c1_to_a1(cell, to_cell)
        return cell
        
    def shift_r1c1_formula(self, formula, row_shift, col_shift, excluded_dict={}):
        """
        Shift an R1C1 formula by a specified number of rows and columns, excluding specified ranges.
        """
        # Convert excluded ranges from A1 to R1C1 format
        excluded_r1c1_ranges = []
        for base_address, ranges in excluded_dict.items():
            for range in ranges:
                r1c1_range = self.formula_a1_to_r1c1(range, base_address)
                excluded_r1c1_ranges.append(r1c1_range)

        def shift_reference(match):
            for ex_range in excluded_r1c1_ranges:
                if match.group(0) in ex_range:
                    return match.group(0)  # Return the original reference without shifting

            row_offset = int(match.group(1) or '0') + row_shift
            col_offset = int(match.group(2) or '0') + col_shift
            return f"R[{row_offset}]C[{col_offset}]"

        shifted_formula = re.sub(r'R\[(\-?\d*)\]C\[(\-?\d*)\]', shift_reference, formula)
        return shifted_formula
    
        
    @staticmethod
    def replace_exact_substrings(text, targets, replacements):
        """
        Replace exact substrings in a string based on lists of targets and replacements.
        Assumes targets and replacements are lists of the same length.
        """
        for target, replacement in zip(targets, replacements):
            pattern = r'\b' + re.escape(target) + r'\b'
            text = re.sub(pattern, replacement, text)
        return text

    
    def make_references_absolute(self, formula, references):
        """
        Make specific cell/range references in a formula absolute.
        """
        targets = references
        replacements = [self.convert_to_absolute(ref) for ref in references]
        return self.replace_exact_substrings(formula, targets, replacements)

    @staticmethod
    def convert_to_absolute(ref):
        """
        Convert a cell/range reference to its absolute form.
        """
        # For cell references (like B7)
        cell_ref_pattern = r'([A-Z]+)(\d+)'
        if re.match(cell_ref_pattern, ref):
            col, row = re.match(cell_ref_pattern, ref).groups()
            return f"${col}${row}"
        
        # For range references (like C3:D4)
        range_ref_pattern = r'([A-Z]+)(\d+):([A-Z]+)(\d+)'
        if re.match(range_ref_pattern, ref):
            start_col, start_row, end_col, end_row = re.match(range_ref_pattern, ref).groups()
            return f"${start_col}${start_row}:${end_col}${end_row}"

        return ref
        

      
    
    def create_bidding_sheet_with_formulas(self, file_path, formulas_dict, params_dict):       
        # Load the workbook
        wb = load_workbook(file_path)
        
        # Create or overwrite the 'Bidding' sheet
        sheet_name = 'Bidding'
        if sheet_name in wb.sheetnames:
            wb.remove(wb[sheet_name])
        sheet = wb.create_sheet(title=sheet_name)
    
        # Check if 'fv' sheet exists
        fv_sheet_name = 'fv'
        if fv_sheet_name not in wb.sheetnames:
            print(f"Sheet '{fv_sheet_name}' not found.")
            return
        fv_sheet = wb[fv_sheet_name]
    
        # Configuration for table layout
        max_tables_per_row = 5
        vertical_space = 2
        table_width = 3  # Number of columns per table
        table_height = 30  # Number of rows per table including headers
        start_row_offset = 1
    
        # Loop through values in column 'A' of 'fv' sheet and create tables
        for row_index, row in enumerate(fv_sheet.iter_rows(min_row=2, max_col=1, values_only=True)):
            border = row[0]
            if border is None:
                continue  # Skip empty cells
    
            # Calculate starting position for the new table
            start_row = start_row_offset + (row_index // max_tables_per_row) * (table_height + vertical_space)
            start_col = 1 + (row_index % max_tables_per_row) * (table_width + 1)  # +1 for one column space between tables
            if start_col == 17:
                print('debug')
            # Write value to A8 of the current table
            border_address = [start_row + 8, start_col]
            sheet.cell(row=border_address[0],
                       column=border_address[1],
                       value=border)
            border_cell_address = f"{get_column_letter(border_address[1])}{border_address[0]}"
            
            
            # Add headers to column 'A' of the current table
            headers_list = ['Auct Date', 'End Time', 'spread',
                            'ext', 'Bid Adj',
                            'Min Pos', 'Max Pos', 'Hours']
            headers_rows = [a for a in range(-8,0)]
            
            fixed_cells = ['B3', 'B4','B5', 'B6', 'B7', 'B8', 'C12']
            table_base = sheet.cell(row=start_row, column=start_col)
            fixed_cells_shift = [self.shift_cell(a,'A1',
                                                 table_base.coordinate) for a in
                                 fixed_cells]
            for header, row_shift  in zip(headers_list, headers_rows):
                sheet.cell(row=border_address[0]+row_shift,
                           column=border_address[1],
                           value=header)
                
                if header in params_dict[border].keys():
                    param = params_dict[border][header]
                    if param == 'formula':
                        formula_cell_r1c1 = f"R[{row_shift}]C[1]"
                        formula_cell_a1 = self.r1c1_to_a1(formula_cell_r1c1,
                                                          border_cell_address)

                        formula_key = self.r1c1_to_a1(self.shift_r1c1_formula(formula_cell_r1c1,
                                                              -start_row+1,
                                                              -start_col+1),
                                                      border_cell_address)
                        formula = self.formulas_dict[formula_key].replace(',','.').replace(';',',')
                        # formula = self.formula_a1_to_r1c1(formula, formula_key)

                        # formula = self.formula_r1c1_to_a1(formula, formula_cell_a1)
                        formula = self.shift_formula(formula, formula_key, formula_cell_a1,
                                                     fixed_cells, fixed_cells_shift)
                        
                        sheet.cell(row=border_address[0]+row_shift,
                                   column=border_address[1]+1,
                                   value=formula)
                        fixed_cells = fixed_cells_shift
                        del formula_cell_r1c1, formula_cell_a1, formula_key, formula
                    else:
                        sheet.cell(row=border_address[0]+row_shift,
                                   column=border_address[1]+1,
                                   value=param)
                        fixed_cells = fixed_cells_shift
                    
                else:
                    continue
            
                
            # Create table headers cols for the current table
            for col_offset, header in enumerate(['Vol', 'Bid', 'Risk']):
                sheet.cell(row=start_row + 9, column=start_col + col_offset, value=header)
            
            # fixed_cells = ['B3', 'B4','B5', 'B6', 'B7', 'B8', 'C12']
            # table_base = sheet.cell(row=start_row, column=start_col)
            # fixed_cells_shift = [self.shift_cell(a,'A1',
            #                                      table_base.coordinate) for a in
            #                      fixed_cells]
            
            for i in range(start_row + 10, start_row + 29):                
                for base_col in range(start_col, start_col+3):
                    formula_cell = sheet.cell(row=i, column=base_col)
                    formula_cell_a1 = formula_cell.coordinate
                    if formula_cell_a1 == 'Q14':
                        print(formula_cell_a1)
                    base_formula_cell = sheet.cell(row=i-start_row+1,
                                                   column=base_col-start_col+1)
                    base_formula_cell_a1 = base_formula_cell.coordinate
                    
                                        
                    if base_formula_cell_a1 in formulas_dict.keys():
                        

                        
                        formula = formulas_dict[base_formula_cell_a1].replace(',','.').replace(';',',')
                        # formula = self.make_references_absolute(formula, fixed_cells)

                        
                        formula_a1 = self.shift_formula(formula, base_formula_cell_a1,
                                                        formula_cell_a1,
                                                        fixed_cells_shift=fixed_cells_shift)
                        # formula_a1 = self.make_references_absolute(formula_a1, fixed_cells_shift)

                        formula_cell.value = formula_a1
                        fixed_cells = fixed_cells_shift

                    else:
                        
                        cell_above = sheet.cell(row=i-1,column=base_col)
                        cell_above_a1 = cell_above.coordinate
                        formula = cell_above.value

                        formula_a1 = self.shift_formula(formula, cell_above_a1,
                                                        formula_cell_a1,
                                                        fixed_cells_shift=fixed_cells_shift)
                        # formula_a1 = self.make_references_absolute(formula_a1, fixed_cells_shift)

                        formula_cell.value = formula_a1
                        fixed_cells = fixed_cells_shift
       
        
        # # Save the workbook
        wb.save(file_path)
        wb.close()
     
    @staticmethod
    def find_last_cell_in_row(workbook_path, sheet_name, start_cell):
        """
        Find the last cell with a value in the same row as the start cell.
        """
        wb = load_workbook(workbook_path)
        sheet = wb[sheet_name]
    
        start_col = start_cell.column
        start_row = start_cell.row
    
        # Iterate through cells in the same row, starting from the start column
        last_cell = start_cell
        for cell in sheet[start_row]:
            if cell.column < start_col:
                continue
            if cell.value is not None:
                last_cell = cell
            else:
                break  # Stop if an empty cell is found
    
        wb.close()
        return last_cell.coordinate
    
    @staticmethod
    def find_last_cell_in_column(workbook_path, sheet_name, start_cell):
        """
        Find the last cell with a value in the same column as the start cell.
        """
        wb = load_workbook(workbook_path)
        sheet = wb[sheet_name]
    
        start_col = start_cell.column
        start_row = start_cell.row
    
        # Iterate through cells in the same column, starting from the start row
        last_cell = start_cell
        for row in range(start_row, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=start_col)
            if cell.value is not None:
                last_cell = cell
            else:
                break  # Stop if an empty cell is found
    
        wb.close()
        return last_cell.coordinate
    
    @staticmethod
    def find_cells_with_value(workbook_path, sheet_name, search_range, target_value):
        """
        Find all cells within a specified range that contain a certain value.
        """
        wb = load_workbook(workbook_path)
        sheet = wb[sheet_name]
    
        # Split the range into start and end coordinates
        start_cell, end_cell = search_range.split(':')
        start_column = ''.join(filter(str.isalpha, start_cell))
        end_column = ''.join(filter(str.isalpha, end_cell))
        start_row_index = int(''.join(filter(str.isdigit, start_cell)))
        end_row_index = int(''.join(filter(str.isdigit, end_cell)))
    
        # Convert column letters to numbers
        start_col_index = column_index_from_string(start_column)
        end_col_index = column_index_from_string(end_column)
    
        found_cells = []
        for row in range(start_row_index, end_row_index + 1):
            for col in range(start_col_index, end_col_index + 1):
                cell = sheet.cell(row=row, column=col)
                if cell.value == target_value:
                    found_cells.append(cell.coordinate)
    
        wb.close()
        return found_cells
    
    @staticmethod
    def find_last_cell_above_value(workbook_path, sheet_name, cell_range, target_value):
        """
        Find the last cell with a value higher than a given value in a specified column range.
        """
        wb = load_workbook(workbook_path, data_only=True)
        sheet = wb[sheet_name]
    
        # Parse the cell range
        start_cell, end_cell = cell_range.split(':')
        column_letter = ''.join(filter(str.isalpha, start_cell))
        start_row = int(''.join(filter(str.isdigit, start_cell)))
        end_row = int(''.join(filter(str.isdigit, end_cell)))
    
        # Convert column letter to number
        column_index = column_index_from_string(column_letter)
    
        # Initialize last cell with value
        last_cell_with_value = None
    
        # Iterate over the rows in the column
        for i, row in enumerate(range(start_row, end_row + 1)):
            cell = sheet.cell(row=row, column=column_index)

            if isinstance(cell.value, (int, float)) and cell.value > target_value:
                last_cell_with_value = cell
            # if i >2 and last_cell_with_value == None:
                
    
        wb.close()
        return last_cell_with_value.coordinate if last_cell_with_value else None
    
    @staticmethod
    def recalculate_workbook(path, new_path=None):
        """
        Open an Excel workbook, recalculate all formulas, and save it.
        If new_path is provided, saves the workbook under a new name.
        """
        app = None
        try:
            app = xw.App(visible=False)
            wb = app.books.open(path)
            app.api.Calculate()
            save_path = new_path if new_path else path
            wb.save(save_path)
            wb.close()
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if app:
                app.quit()

        
    def position_checker_jao_api(self, file_path=None):
        self.recalculate_workbook(file_path)
        self._jao_loader = JL()
        # jao_dict = self._jao_loader.company_auction_loader(['etc'],
        #                                                     self.capa_settle_range,
        #                                                     self.capa_type)
        # positions = jao_dict['etc'].mean()
        # company_borders = positioins
        
        # jao_auct_sum = self._jao_loader.auction_loader(self.border_list,
        #                                     [self.capa_start],
        #                                     self.capa_type)
        
        # Configuration for table layout
        max_tables_per_row = 5
        vertical_space = 2
        table_width = 3  # Number of columns per table
        table_height = 30  # Number of rows per table including headers
        start_row_offset = 1
        
        wb_data = load_workbook(file_path, data_only=True)
        wb = load_workbook(file_path)
        fv_sheet = wb_data['fv']
        bid_sheet = wb_data['Bidding']
        target_sheet = wb['Total_Positions']
        
        # Loop through values in column 'A' of 'fv' sheet and create tables
        for row_index, row in enumerate(fv_sheet.iter_rows(min_row=2, max_col=1, values_only=True)):
            border = row[0]
            if border is None:
                continue  # Skip empty cells
                
            jao_auct_sum = self._jao_loader.auction_loader([border],
                                                [self.capa_start],
                                                self.capa_type)
    
            # Calculate starting position for the new table
            start_row = start_row_offset + (row_index // max_tables_per_row) * (table_height + vertical_space)
            start_col = 1 + (row_index % max_tables_per_row) * (table_width + 1)  # +1 for one column space between tables
            start_cell = fv_sheet.cell(row=start_row, column=start_col)
            start_cell_a1 = start_cell.coordinate        
        
            last_cell_a1 = self.find_last_cell_in_column(file_path, 'Bidding', start_cell)
            
            last_cell_a1 = self.shift_cell(last_cell_a1, 'A1', 'C1')
            table_range = start_cell_a1 + ':' + last_cell_a1
            
            filtered_cells = self.find_cells_with_value(file_path, 'Bidding', table_range, 'Bid')
            if len(filtered_cells)!=1:
                print('debug')
            assert len(filtered_cells) == 1, 'Multiple values matched for cell defining\
                the start of bidding formular'
                
            #find the last lowest awarded bid
            bid_header_cell = filtered_cells[0]
            
            bid_search_range = bid_header_cell + ':' + self.shift_cell(last_cell_a1, 'C1', 'B1')
            
            auct_result = jao_auct_sum[border]['auct_price']
            
            last_bid_a1 = self.find_last_cell_above_value(file_path, 'Bidding',
                                                          bid_search_range, auct_result[0])
            
            if last_bid_a1 == None:
                position = 0
            else:
            
                position_cell_a1 = self.shift_cell(last_bid_a1, 'B1', 'A1')
                position = bid_sheet[position_cell_a1].value
            
            name_header = 'border'
            value_header = 'capa_pos'
            # Find the columns for name and value based on headers
            name_col = None
            value_col = None
            for col in range(1, target_sheet.max_column + 1):
                header_value = target_sheet.cell(row=1, column=col).value
                if header_value == name_header:
                    name_col = col
                elif header_value == value_header:
                    value_col = col
        
            if not name_col or not value_col:
                print("Column header not found.")
                
            
            # Iterate over the cells in the name column to find the matching name
            for row in range(2, target_sheet.max_row + 1):  # Start from 2 to skip header
               cell_name = target_sheet.cell(row=row, column=name_col).value
               if cell_name == border:
                   # Write the value to the corresponding cell in the value column
                   target_sheet.cell(row=row, column=value_col).value = position
                   break
               
        wb.save(file_path)
        wb.close()
        
    @property
    def flow_dict(self):
        flows = {}
        flows['de_fr'] = ['de_be', 'be_fr', 'de_nl', 'nl_be']
        flows['fr_de'] = ['fr_be', 'be_de', 'be_nl', 'nl_de']
        flows['de_hu'] = ['de_at', 'at_hu', 'de_cz', 'cz_sk', 'sk_hu']
        flows['hu_de'] = ['hu_at', 'at_de', 'hu_sk', 'sk_cz', 'cz_de']
        return flows
        
     
    
    def flow_aggregator(self, file_path):
        df = pd.read_excel(file_path, sheet_name='Total_Positions')
        
        flow_positions = {}
        
        for key in self.flow_dict.keys():
            flow_list = self.flow_dict[key]
            df_aux = df.loc[df['border'].isin(flow_list)]
            df_aux = df_aux.set_index(['border'])
            df_aux = df_aux['capa_pos'].copy()
            
            for border in flow_list:
                if border not in df_aux:
                    df_aux[border] = 0
            
            if key in ['de_fr']:
                flow = min(df_aux['be_fr'],
                           df_aux['de_be']+min(df_aux['de_nl'], df_aux['nl_be']))
            elif key in ['de_fr']:
                flow = min(df_aux['be_fr'],
                          df_aux['de_be']+min(df_aux['de_nl', 'nl_be']))
            elif key in ['de_hu']:
                flow = min(df_aux['de_at'], df_aux['at_hu'])+\
                    min(df_aux['de_cz'], df_aux['cz_sk'], df_aux['sk_hu'])
            elif key in ['hu_de']:
                flow = min(df_aux['at_de'], df_aux['hu_at'])+\
                    min(df_aux['cz_de'], df_aux['sk_cz'], df_aux['hu_sk'])
            flow_positions[key] = flow
        
        return flow_positions
        
            
            
        

        
        
    
        
if __name__ == '__main__':
    borders_list = ['de_fr', 'fr_de']
    # borders_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
    #                 'de_nl', 'nl_de', 'be_nl', 'nl_be',
    #                 'be_fr', 'fr_be',
    #                 'de_at', 'at_de', 'at_hu', 'hu_at',
    #                 'at_cz', 'cz_at', 'cz_de', 'de_cz']
    params_dict = {}
    for border in borders_list:
        params_dict[border] = {'Max Risk': 20000,
                               'Hours': 744,
                               'spread': 'formula',
                               'ext': 'formula'}
    # divided_borders = [a.split('_') for a in border_list]
    # test_fut = rd.get_history(['DEBMc1'], ['SETTLE'],count=1)
    
    test_o = CapaBnH(datetime(2021,10,1), data_aggregation='M',
                      auction_date=datetime(2023,11,24),
                      capa_type='Y')
    test_o.set_borders_list(borders_list)
    test_dict = test_o.aggregate_capa_types()
    # test_o.create_excel()
    # test_o.create_hedge_pos()
    # test_o.create_net_hedge()
    
    # # Specify the path to the workbook
    # file_path = r'S:\Capa\CapaFv\Test\test_df.xlsx'    
    
    # # # Save the workbook with the replicated structures
    # test_o.create_bidding_sheet_with_formulas(file_path, test_o.formulas_dict, params_dict)
    
    # test_o.position_checker_jao_api(file_path)
    
    def merge_and_process(dfs, merge_cols, datetime_cols,
                                   float_cols, weighting_col):
        
        q_hours = {'Q.1': 91*24-1,
                   'Q.2': 91*24,
                   'Q.3': 92*24,
                   'Q.4': 92*24+1}
        
        comp_df = None
        for df in dfs.values():
            if comp_df is None:
                comp_df = df.copy()
            else:
                comp_df = pd.concat([comp_df,df], axis=0)
        comp_df[weighting_col] = comp_df[weighting_col].map(q_hours)
        # comp_df = comp_df.drop([weighting_col],axis=1)
        
        def weighted_averages(group, value_columns, weight_column):
            results = {}
            for value_column in value_columns:
                d = group[value_column]
                w = group[weight_column]
                try:
                    results[value_column] = (d * w).sum() / w.sum()
                except ZeroDivisionError:
                    results[value_column] = None
            return pd.Series(results)
                
        # comp_df = comp_df.groupby(merge_cols).mean()
        comp_df = comp_df.groupby(merge_cols).apply(weighted_averages,
                                                    float_cols, weighting_col).reset_index()
        
        
        return comp_df
            
    
    test_df = merge_and_process(dfs=test_dict, merge_cols=['border', 'market_out', 'market_in','settle_date_out', 'settle_date_in'],
                                    datetime_cols=['settle_date_out', 'settle_date_in'],
                                    float_cols=['fut_out', 'fut_in', 'spread', 'capa_fv', 'ext', 'delta'],
                                    weighting_col='fut_products')