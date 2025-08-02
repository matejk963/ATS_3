# -*- coding: utf-8 -*-
"""
Created on Mon Dec 11 08:38:37 2023

@author: krajcovic
"""
from abc import ABC, abstractmethod

import padnas as pd
import numpy as np
from datetime import datetime, timedelta
import os

import re
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string,get_column_letter
from openpyxl.worksheet.cell_range import CellRange
import xlwings as xw

class ExcelCreator(ABC):
    
    """
    meta class to classes for creation of excell for each of the use cases:
        Bidding formular with hedging positions
        Market monitor
        
    """
    
    def file_path(self, folder_name, file_name):
        assert file_name.split('.')[1] == 'xlsx', 'Must be excel file'
        file_path = os.path.join(folder_path, file_name)
        return file_path
    
       
    def create_file(self):        
        df = pd.DataFrame()
        df.to_excel(self.file_path, index=False)
        
    
    def workbook_loader(self):
        if self._workbook is None:
            self._workbook = load_workbook(self.file_path)
        else:
            pass
        
    
    def create_sheet(self, sheet_name):
        self.workbook.create_sheet(title=sheet_name)        
        # Save the workbook
        self.workbook.save(self.file_path)
        
    
    def workbook_safe(self):
        self.workbook.save()
        self.workbook.close()
        
class CapaBnH_excel(ExcelCreator):
    
    def __init__(self, folder_name, file_name):
        self._folder_name = folder_name
        self._file_name = file_name
        self._sheet_name = None
        self._workbook = None
        
    @property
    def folder_name(self):
        return self._folder_name
    
    @property
    def file_name(self):
        
        return self._file_name
    
    @property
    def sheet_name(self):
        return self._sheet_name
    
    @property
    def workbook(self):
        self.workbook_loader
        return self._workbook

        
    def insert_value_to_cell(self, sheet_name_list,
                             cell_list,
                             value_list):
        
        sheet = self.workbook[sheet_name]
        sheet[cell] = value
        workbook.save(self.file_name)
        
        pass
    
            
        
        
        