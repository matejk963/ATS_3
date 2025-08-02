# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 15:02:03 2024

@author: Marek
"""
import sys
sys.path.append(r'C:\data\ua\apps')

import tkinter as tk
from tkinter import Canvas, messagebox, ttk, Toplevel
from PIL import Image, ImageTk
import glob
import os
import re
import shutil
from datetime import datetime, timedelta
from openpyxl import load_workbook
import xlwings as xw
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import json
from email_sending import send_html_email
from scipy.optimize import linprog


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

default_path='C:/data/ua/'
# default_path="/Users/marek/Work/Projects/ua_app/"
tol_price = .1
tol_price1 = .01
tol_vol = .01
# jao_dict = {0: 'MAIL_JAO_VS', 1: 'MAIL_JAO_NG'}
# inv_dict = {'VS': 0, 'NaftoGaz': 1}


class UA_APP:
    def __init__(self, date=None, path=default_path, test_bool=False):
        if date is None:
            self.date = (datetime.today() + timedelta(days=1)).date()
        else:
            self.date = date
        self.path = path
        self.__archive()
        self.__test_bool = test_bool
        # Load config
        self.load_config()
        self.__log = ''
        self.side_list = ['buy', 'sell']
        self.size = 0
        loader_list = ['jao_bids', 'jao_xml', 'jao_xml_price',
                       'xge_bids', 'xge_bids_dict', 'xge_results']
        self.__loader_dict = {x: False for x in loader_list}
        self.__loaded_values = {x: None for x in loader_list}

    @property
    def today_date(self):
        return self.date - timedelta(days=1)

    @property
    def test_bool(self):
        return self.__test_bool

    @property
    def date_string(self):
        return self.date.strftime("%Y_%m_%d")

    @property
    def log(self):
        return self.__log

    @property
    def opp_side(self):
        return {'buy': 'sell', 'sell': 'buy'}

    @property
    def jao_xml_bool(self):
        return self.__loader_dict['jao_xml']

    @jao_xml_bool.setter
    def jao_xml_bool(self, value):
        if isinstance(value, bool):
            self.__loader_dict['jao_xml'] = value
        else:
            raise ValueError('jao_xml_bool value must be boolean, instead was {}'.format(value))

    @property
    def jao_xml_bids(self):
        return self.__loaded_values['jao_xml']

    @jao_xml_bids.setter
    def jao_xml_bids(self, dict_series):
        if all([isinstance(s, pd.Series) and 23 <= s.size <= 25 for s in dict_series.values()]):
            self.__loaded_values['jao_xml'] = dict_series
        else:
            raise ValueError('jao_xml_bids value must be Series, instead was {}'.format(dict_series))

    @property
    def jao_xml_price(self):
        return self.__loaded_values['jao_xml_price']

    @jao_xml_price.setter
    def jao_xml_price(self, dict_series):
        if all([isinstance(s, pd.Series) and 23 <= s.size <= 25 for s in dict_series.values()]):
            self.__loaded_values['jao_xml_price'] = dict_series
        else:
            raise ValueError('jao_xml_bids value must be Series, instead was {}'.format(dict_series))

    @property
    def xge_bids_bool(self):
        return self.__loader_dict['xge_bids']

    @xge_bids_bool.setter
    def xge_bids_bool(self, value):
        if isinstance(value, bool):
            self.__loader_dict['xge_bids'] = value
        else:
            raise ValueError('xge_bids_bool value must be boolean, instead was {}'.format(value))

    @property
    def xge_bids(self):
        return self.__loaded_values['xge_bids']

    @xge_bids.setter
    def xge_bids(self, df):
        if isinstance(df, pd.DataFrame) and df.shape[0] == self.size:
            self.__loaded_values['xge_bids'] = df
        else:
            raise ValueError('xge_bids value must be DataFrame, instead was {}'.format(df))

    @property
    def xge_bids_dict(self):
        return self.__loaded_values['xge_bids_dict']

    @xge_bids_dict.setter
    def xge_bids_dict(self, df_dict):
        self.__loaded_values['xge_bids_dict'] = {k: None for k in df_dict.keys()}
        for k, df in df_dict.items():
            if isinstance(df, pd.DataFrame) and df.shape[0] == self.size:
                self.__loaded_values['xge_bids_dict'][k] = df
            else:
                raise ValueError('xge_bids value must be DataFrame, instead was {}'.format(df))

    @property
    def xge_results_bool(self):
        return self.__loader_dict['xge_results']

    @xge_results_bool.setter
    def xge_results_bool(self, value):
        if isinstance(value, bool):
            self.__loader_dict['xge_results'] = value
        else:
            raise ValueError('xge_results_bool value must be boolean, instead was {}'.format(value))

    @property
    def check_path(self):
        date_str = self.date.strftime("%Y_%m_%d")
        self.folder_path = self.path + date_str
        if os.path.exists(self.folder_path):
            return True
        else:
            return False

    def check_cmp(self, idx):
        return any([idx in x for x in self.cmp_dict.values()])

    def set_side_list(self, selected_option):
        if selected_option == 'All':
            self.side_list = ['buy', 'sell']
        elif selected_option == 'buy':
            self.side_list = ['buy']
        else:
            self.side_list = ['sell']

    def get_index(self, selected_option):
        if selected_option == 'All':
            return 'all'
        elif selected_option == 'None':
            return 'None'
        else:
            return self.inv_dict[selected_option]

    def __archive(self):
        """
        Moves all folders in `directory` that do not match the `target_date` (format yyyy_mm_dd)
        into an `Archive/` folder. If `Archive/` does not exist, it will be created.
        
        Parameters:
            directory (str): The directory to process.
            target_date (str): The specific date to match in yyyy_mm_dd format.
        """
        archive_folder = os.path.join(self.path, "Archive")
        # Create Archive/ folder if it doesn't exist
        if not os.path.exists(archive_folder):
            os.makedirs(archive_folder)
        # Regular expression for date format yyyy_mm_dd
        date_regex = re.compile(r"^\d{4}_\d{2}_\d{2}$")
        for item in os.listdir(self.path):
            item_path = os.path.join(self.path, item)
            # Check if item is a folder and matches the date format
            if os.path.isdir(item_path) and date_regex.match(item):
                try:
                    # Convert folder name to a datetime.date object
                    folder_date = datetime.strptime(item, "%Y_%m_%d").date()
                    
                    # Archive folders with dates before target_date
                    if folder_date < self.date:
                        shutil.move(item_path, archive_folder)
                        print(f"Moved folder: {item} to Archive/")
                except ValueError:
                    print(f"Skipped non-matching folder: {item}")
            else:
                print(f"Skipped non-folder or non-matching item: {item}")

    def load_config(self):
        config_keys = ['EMAIL_LOGIN', 'MAIL_JAO_VS', 'MAIL_JAO_NG', 'MAIL_JAO_UH',
                       'MAIL_JAO_GE', 'MAIL_XGE']
        # Load config
        if self.test_bool:
            cfg_file = 'config_test.json'
        else:
            cfg_file = 'config.json'
        PATH_CFG = self.path + cfg_file
        with open(PATH_CFG, 'r') as file:
            config_dict = json.load(file)
            self.config = {k: v for k, v in config_dict.items() if k in config_keys}
            aux_dict = config_dict['AUX_DICT']
            self.jao_dict = {v[0]: v[1] for v in aux_dict.values()}
            self.inv_dict = {k: v[0] for k, v in aux_dict.items()}
            self.fac_dict = {v[0]: v[2] for k, v in aux_dict.items()}
            self.auto_xge_dict = {v[0]: v[3] for k, v in aux_dict.items()}
            self.fee_dict = {v[0]: v[4] for k, v in aux_dict.items()}
            self.eic_dict = {v[0]: v[5] for k, v in aux_dict.items()}
            self.cmp_dict = {k: [] for k in ['buy', 'sell']}
            self.xge_bool = config_dict['BOOL_DICT']['HUPX']
        # Load credentials
        PATH_LOGIN = self.path + 'config_login.json'
        with open(PATH_LOGIN, 'r') as file:
            config_dict = json.load(file)
            self.config['EMAIL_LOGIN'] = {k: v for k, v in config_dict['EMAIL_LOGIN'].items()}

    def load_xml(self):
        contract_id_dict = {k: None for k in self.side_list}
        document_id_dict = {k: None for k in self.side_list}
        data_list_dict = {k: [] for k in self.side_list}
        if self.check_path:
            for side in self.side_list:
                self.__parse_jao_bids(side)
                contract_id, document_id, data_list = self.__parse_xml(side)
                contract_id_dict[side] = contract_id
                document_id_dict[side] = document_id
                data_list_dict[side] = data_list
            if all([not k for k in data_list_dict.values()]):
                pass
            else:
                data_dict = {k: None for k in self.side_list}
                data_p_dict = {k: None for k in self.side_list}
                side_list_del = []
                for side in self.side_list:
                    for v in data_list_dict[side]:
                        if data_dict[side] is None:
                            try:
                                data_dict[side] = v.loc[:, 'awd_qty'].copy()
                                data_p_dict[side] = v.loc[:, 'clearing_px'].copy()
                            except(AttributeError):
                                data_dict[side] = pd.Series(0, index=range(1, self.size + 1))
                                data_p_dict[side] = pd.Series(0, index=range(1, self.size + 1))
                        else:
                            if v.empty:
                                pass
                            else:
                                data_dict[side] += v.loc[:, 'awd_qty']
                    if not data_list_dict[side]:
                        # Delete side
                        data_dict.pop(side)
                        data_p_dict.pop(side)
                        data_list_dict.pop(side)
                        contract_id_dict.pop(side)
                        document_id_dict.pop(side)
                        side_list_del.append(side)
                self.side_list = [s for s in self.side_list if s not in side_list_del]
                self.jao_xml_bids = data_dict
                self.jao_xml_price = data_p_dict
                self.jao_xml_list = data_list_dict
                self.jao_cai_dict = {k: v for k, v in contract_id_dict.items()}
                self.jao_xml_bool = True
                data_list_dict_out = {k: [] for k in self.side_list}
                for idx in self.jao_dict.keys():
                    idx_jao = {s: v.index(idx) if idx in v else None
                               for s, v in self.cmp_dict.items()}
                    for side in self.side_list:
                        df_empty = pd.DataFrame([], columns=data_list_dict[side][0].columns)
                        if idx_jao[side] is None:
                            data_list_dict_out[side].append(df_empty)
                        else:
                            data_list_dict_out[side].append(data_list_dict[side][idx_jao[side]])
        else:
            date_str = self.date.strftime("%Y_%m_%d")
            self.__log += 'Load xml: Path for date {} does not exist, try to create path {} manually \n'.format(date_str, self.folder_path)
        return contract_id_dict, document_id_dict, data_list_dict_out

    def send_xml(self, data_s, contract_id_dict, document_id_dict, idx):
        type_dict = {'bid_qty': 'int64', 'bid_px': 'float64',
                     'awd_qty': 'int64', 'clearing_px': 'float64'}
        inv_dict = {v: k for k, v in self.inv_dict.items()}
        if inv_dict[idx] == 'VS':
            vs_bool = True
        else:
            vs_bool = False
        MAIL_CFG = self.jao_dict[idx]
        receiver_email = self.config[MAIL_CFG]['TO']
        receiver_cc = self.config[MAIL_CFG]['CC']
        password = self.config['EMAIL_LOGIN']['PASSWORD']
        login = self.config['EMAIL_LOGIN']['USERNAME']
        address = self.config['EMAIL_LOGIN']['EMAIL']
        if self.jao_xml_bool:
            df_html_dict = {}
            for s, data in data_s.items():
                if data.empty:
                    continue
                data = data.astype(type_dict)
                # Replace dots with commas for decimal points
                for column in data.select_dtypes(include=['float']):
                    data[column] = data[column].map(lambda x: f'{x:,.2f}'.replace('.', ','))
                df_html_dict[s] = data.reset_index().to_html(index=False, border=1)
            html_body = ""
            for s in df_html_dict.keys():
                if s == 'buy':
                    subject = "Results_JAO_HUUA_" + self.date.strftime("%Y%m%d")
                else:
                    subject = "Results_JAO_UAHU_" + self.date.strftime("%Y%m%d")
                if self.test_bool:
                    subject += "_TEST"
                html_body = f"""
                    <p>Please find the CAI code below:</p>
                    {contract_id_dict[s]}
                    <p>On capacity border</p>
                    {document_id_dict[s]}
                    <p>Please find the Results from auction below:</p>
                    {df_html_dict[s]}
                    <br><br>
                """
            
                html_content = f"""
                <html>
                    <body>
                        <h1>Hello,</h1>
                        {html_body}
                        <p>Best regards,</p>
                        <p>Your ETC</p>
                    </body>
                </html>
                """
    
                # If VS then send csv
                if vs_bool:
                    date_str = self.date.strftime("%Y%m%d")
                    if s == 'buy':
                        direction = 'HUUA'
                    else:
                        direction = 'UAHU'
                    pattern = "jao_results_" + direction + "_" + date_str + ".csv"
                    attachment_path = os.path.join(self.folder_path, pattern)
                    data_s[s].to_csv(attachment_path)
                    attachment = attachment_path.replace('\\', '/')
                else:
                    attachment = None
                
                send_html_email(
                      receiver_email, 
                      subject, "This is a plain text fallback content.", html_content, attachment_path=attachment,
                      recipient_cc=receiver_cc, email_address=address, email_login=login, email_password=password
                )
                if attachment is not None:
                    if os.path.exists(attachment_path):
                        os.remove(attachment_path)
                    else:
                        self.__log += f'CSV file "{attachment_path}" does not exist.'
            self.__log += 'send_xml: Email sent! \n'
        else:
            self.__log += 'send_xml: Load xml first! \n'

    def load_xge_bids(self, mkt_str):
        loop_bool = False
        data_def = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500])
        data_def.index.name = 'Hourly / Price'
        if mkt_str == 'all':
            idx_list = [k for k in self.jao_dict.keys() if self.check_cmp(k)]
            loop_bool = True
        elif mkt_str in [str(x) for x in self.jao_dict.keys()]:
            idx = int(mkt_str)
        else:
            idx = None
        if self.check_path:
            if loop_bool:
                data_bids_list = []
                error_list = []
                for idx in idx_list:
                    if self.auto_xge_dict[idx]:
                        data = self.__parse_jao_xge_bids(idx)
                        errors = None
                    else:
                        data, _, errors = self.__parse_xlsx_xge_bids(idx)
                    data_bids_list.append(data)
                    if errors is None:
                        pass
                    else:
                        error_list.append(errors)
                data_bids_dict = {k: v for k, v in zip(idx_list, data_bids_list)}
                data_bids, file_path, errors = self.__merge_xge_bids(data_bids_list)
                if errors is None:
                    pass
                else:
                    error_list.append(errors)
                if not error_list:
                    error_log = None
                else:
                    error_log = "\n".join(error_list)
            else:
                if self.auto_xge_dict[idx]:
                    data_bids = self.__parse_jao_xge_bids(idx)
                    file_path, error_log = None, None
                else:
                    data_bids, file_path, error_log = self.__parse_xlsx_xge_bids(idx)
                data_bids_dict = {idx: data_bids}
            if not error_log:
                # No errors
                self.xge_bids = data_bids
                self.xge_bids_dict = data_bids_dict
                self.xge_bids_bool = True
            return error_log, file_path, data_bids
        else:
            date_str = self.date.strftime("%Y_%m_%d")
            self.__log += 'Load xchange bids: Path for date {} does not exist, try to create path {} manually \n'.format(date_str, self.folder_path)
            return None, None, None

    def send_xge_bids(self, file_path):
        if self.xge_bool:
            receiver_email = self.config['MAIL_XGE']['CC']
            receiver_cc = []
        else:
            receiver_email = self.config['MAIL_XGE']['TO']
            receiver_cc = self.config['MAIL_XGE']['CC']
        password = self.config['EMAIL_LOGIN']['PASSWORD']
        login = self.config['EMAIL_LOGIN']['USERNAME']
        address = self.config['EMAIL_LOGIN']['EMAIL']
        if self.xge_bids_bool:
            subject = "ETC_bid_" + self.date.strftime("%Y%m%d")
            if self.test_bool:
                subject += "_TEST"
            # Replace dots with commas for decimal points
            data = self.xge_bids
            # data.columns = data.columns.astype(str).str.replace('.', ',', regex=False)
            for column in data.select_dtypes(include=['float']):
                data[column] = data[column].map(lambda x: f'{x:,.2f}'.replace('.', ','))
            df_html = data.reset_index().to_html(index=False, border=1)
            attachment = file_path.replace('\\', '/')
            html_content = """\
                <html>
                    <body>
                        <h1>Dear all,</h1>
                        <p>Please find the conditional bid for HUPX DAM for the day:</p>\n\n
                        """+self.date_string+"""
                        <p>Please find the Table below:</p>\n
                        """+df_html+ """
                        <p>Best regards,</p>
                        <p>Your ETC</p>
                    </body>
                </html>
                """

            send_html_email(
                  receiver_email,
                  subject, "This is a plain text fallback content.", html_content, attachment_path=attachment,
                  recipient_cc=receiver_cc, email_address=address, email_login=login, email_password=password
            )
            self.__log += 'send_xge: Email sent! \n'
        else:
            self.__log += 'send_xge: Load xml first! \n'

    def load_results(self, mkt_str):
        if mkt_str == 'all':
            idx_list = [k for k in self.jao_dict.keys() if self.check_cmp(k)]
        elif mkt_str in [str(x) for x in self.jao_dict.keys()]:
            idx_list = [int(mkt_str)]
        else:
            idx_list = list(self.jao_dict.keys())
        if self.check_path:
            data_list = []
            path_list = []
            path_deal_list = []
            data_dict, file_path_dict, error_log = self.__parse_results()
            for idx in idx_list:
                data_list.append(data_dict[idx])
                path_list.append(file_path_dict[idx])
                # Save deal confirmation
                deal_path = self.__deal_confirmation(data_dict[idx], idx)
                if deal_path is None:
                    error_log += 'Wrong deal confirmation file'
                path_deal_list.append(deal_path)
            if not error_log:
                self.xge_results_bool = True
            return error_log, path_deal_list, data_list
        else:
            date_str = self.date.strftime("%Y_%m_%d")
            self.__log += 'Load results: Path for date {} does not exist, try to create path {} manually \n'.format(date_str, self.folder_path)
            return None, None, None

    def send_results(self, file_path, data, idx):
        MAIL_CFG = self.jao_dict[idx]
        receiver_email = self.config[MAIL_CFG]['TO']
        receiver_cc = self.config[MAIL_CFG]['CC']
        password = self.config['EMAIL_LOGIN']['PASSWORD']
        login = self.config['EMAIL_LOGIN']['USERNAME']
        address = self.config['EMAIL_LOGIN']['EMAIL']
        if self.xge_results_bool:
            subject = "ETC_results_" + self.date.strftime("%Y%m%d")
            if self.test_bool:
                subject += "_TEST"
            # Replace dots with commas for decimal points
            data['volume'] = data['volume'].apply(format_volume)
            data['price'] = data['price'].map(lambda x: f'{x:,.2f}'.replace('.', ','))
            df_html = data.reset_index().to_html(index=False, border=1)
            attachment = file_path.replace('\\', '/')
            html_content = """\
                <html>
                    <body>
                        <h1>Dear all,</h1>
                        <p>Please find the exchange results for HUPX DAM for the day:</p>\n\n
                        """+self.date_string+"""
                        <p>Please find the Table below:</p>\n
                        """+df_html+ """
                        <p>Best regards,</p>
                        <p>Your ETC</p>
                    </body>
                </html>
                """

            send_html_email(
                  receiver_email,
                  subject, "This is a plain text fallback content.", html_content, attachment_path=attachment,
                  recipient_cc=receiver_cc, email_address=address, email_login=login, email_password=password
            )
            self.__log += 'send_results: Email sent! \n'
        else:
            self.__log += 'send_results: Load results first! \n'

    def __parse_jao_bids(self, side):
        # Find xlsx files
        date_str = self.date.strftime("%Y%m%d")
        if side == 'buy':
            border = 'HUUA'
        else:
            border = 'UAHU'
        pattern = "Bid_JAO_" + border + '_' + date_str + "*.xlsx"
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            self.__log += f"No file available for xlsx jao bids: {pattern} , please save manually \n"
        else:
            id_list = list(set([int(re.search(r'_(\d+)\.xlsx$', path).group(1)) for path in matching_files]))
            self.cmp_dict[side] = [i for i in id_list if i in self.jao_dict.keys()]
            if not self.cmp_dict[side]:
                self.cmp_dict[side].append(0)

    def __parse_xml(self, side):
        # Find xml files
        date_str = self.date.strftime("%y%m%d")
        if side == 'buy':
            pattern = "11XETC---------9_A_R-HU-UA-D-DAILYPRODU-" + date_str + "-*.xml"
        else:
            pattern = "11XETC---------9_A_R-UA-HU-D-DAILYPRODU-" + date_str + "-*.xml"
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            self.__log += f"No file available for xml: {pattern} , please save manually \n"
            return None, None, []
        else:
            file_path = matching_files[-1]
        
        tree = ET.parse(file_path)
        root = tree.getroot()

        document_id_elem = root.find(".//AuctionIdentification")
        if document_id_elem is not None:
            document_id = document_id_elem.attrib['v']  # Extracting 'v' attribute
            self.__log += f"AuctionIdentification: {document_id} \n"
        else:
            self.__log += "AuctionIdentification not found! \n"
        date_string = document_id.split('-')[-2]
        date_xml = datetime.strptime(date_string, '%y%m%d').date()
        if date_xml != self.date:
            tmr_str = self.date.strftime("%y%m%d")
            self.__log += f"Date in .xml file: {date_string} does not correspond to tommorow's date: {tmr_str} \n"
            return None, None, []

        # Extract ContractIdentification
        contract_id_elem = root.find(".//ContractIdentification")
        if contract_id_elem is not None:
            contract_id = contract_id_elem.attrib['v']  # Extracting 'v' attribute
            self.__log += f"Contract Identification: {contract_id} \n"
        else:
            self.__log += "Contract Identification not found! \n"

        # Extract intervals and their properties
        intervals = root.findall(".//Interval")

        col_list = ['hour', 'bid_qty', 'bid_px', 'awd_qty', 'clearing_px']
        data_dict = {m: {k: [] for k in col_list} for m in self.jao_dict.keys()}
        idx_dict = {m: {} for m in self.jao_dict.keys()}
        idx = 0

        if intervals:
            for interval in intervals:
                pos = int(interval.find("Pos").attrib['v']) if interval.find("Pos") is not None else np.nan
                qty = float(interval.find("Qty").attrib['v']) if interval.find("Qty") is not None else np.nan
                price_amount = float(interval.find("PriceAmount").attrib['v']) if interval.find("PriceAmount") is not None else np.nan
                bid_px = float(interval.find("BidPriceAmount").attrib['v']) if interval.find("BidPriceAmount") is not None else np.nan
                bid_qty = float(interval.find("BidQty").attrib['v']) if interval.find("BidQty") is not None else np.nan
                try:
                    if idx_dict[idx][pos] == idx and pos == 1:
                        idx += 1
                        idx_dict[idx][pos] = idx
                except KeyError:
                    idx_dict[idx][pos] = idx
                # Make lists
                data_dict[idx]['hour'].append(pos)
                data_dict[idx]['bid_qty'].append(bid_qty)
                data_dict[idx]['bid_px'].append(bid_px)
                data_dict[idx]['awd_qty'].append(qty)
                data_dict[idx]['clearing_px'].append(price_amount)
        else:
            self.__log += "No intervals found! Make sure .xml file is correct \n"

        try:
            data_list = []
            for v in data_dict.values():
                data = pd.DataFrame(v)
                data = data.set_index('hour')
                data_list.append(data)
                self.size = max(self.size, data.shape[0])
        except:
            data_list = []
        return contract_id, document_id, data_list

    def __parse_jao_xge_bids(self, idx):
        data = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500])
        data.index.name = 'Hourly / Price'
        idx_jao = {s: v.index(idx) if idx in v else 0 for s, v in self.cmp_dict.items()}
        fee = self.fee_dict[idx]
        for s in self.side_list:
            df_jao = self.jao_xml_list[s][idx_jao[s]]
            if s == 'buy':
                continue
            if df_jao.empty:
                pass
            else: 
                q_list = df_jao.loc[:, 'awd_qty'].values
                p_list = df_jao.loc[:, 'clearing_px'].values
                clr_list = list(set([p for q, p in zip(q_list, p_list) if q > 0]))
                # col_dict = {p * 1e-8 + fee: p for p in clr_list}
                col_dict = {p: fee for p in clr_list}
                data_aux_list = [data]

                for p in sorted(col_dict.keys()):
                    # p = col_dict[k]
                    k = col_dict[p]
                    data_aux = -df_jao["awd_qty"].where(df_jao["clearing_px"] == p, 0).to_frame()
                    data_aux.index.name = 'Hourly / Price'
                    data_aux.columns = [round(k + 0.0049, 2)]
                    data_prev = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[round(k + 0.0049 - tol_price1, 2)])
                    data_prev.index.name = 'Hourly / Price'
                    data_aux = pd.concat([data, data_prev, data_aux], axis=1)
                    data_aux_list.append(data_aux)
                data_out, _, _ = self.__merge_xge_bids(data_aux_list)
        return data_out

    def __parse_xlsx_xge_bids(self, idx):
        # Find xml files
        date_str = self.date.strftime("%Y%m%d")
        if idx is None:
            pattern = "ETC_bid_" + date_str + "*.xlsx"
            idx_jao = {s: 0 for s in self.side_list}
        else:
            pattern = "ETC_bid_" + date_str + "_" + str(idx) + "*.xlsx"
            idx_jao = {s: v.index(idx) if idx in v else 0 for s, v in self.cmp_dict.items()}
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            jao_ser = None
            for s in self.side_list:
                if jao_ser is None:
                    if self.jao_xml_list[s][idx_jao[s]].loc[:, "awd_qty"].empty:
                        continue
                    jao_ser = self.jao_xml_list[s][idx_jao[s]].loc[:, "awd_qty"]
                else:
                    jao_ser += self.jao_xml_list[s][idx_jao[s]].loc[:, "awd_qty"]
            if jao_ser.sum() < tol_vol:
                data_bids = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500])
                data_bids.index.name = 'Hourly / Price'
            else:
                data_bids = None
            self.__log += f"No file available for xlsx exchange bids: {pattern} , please save manually \n"
            return data_bids, None, None
        else:
            file_path = matching_files[-1]
        data_bids = pd.read_excel(file_path).set_index('Hourly / Price')
        # Check columns
        try:
            self.__check_alternating_columns(data_bids)
            error_list = []
        except TypeError:
            data_bids.columns = pd.Index([float(val.replace(',', '.')) for val in data_bids.columns])
            self.__check_alternating_columns(data_bids)
            error_list = []
        if not error_list:
            error_log = None
        else:
            error_log = "Errors found in bids file:\n" + "\n".join(error_list)
            return data_bids, file_path, error_log
        # Check if volumes are correct
        error_aux_list = self.__check_volumes(data_bids, self.jao_xml_bids)
        error_list.extend(error_aux_list)
        if not error_list:
            error_log = None
        else:
            error_log = "Errors found in bids file:\n" + "\n".join(error_list)
        return data_bids, file_path, error_log

    def __merge_xge_bids(self, data_bids_list):
        data_bids = pd.DataFrame([])
        for data in data_bids_list:
            if data is None:
                continue
            if data_bids.empty:
                data_bids = data.T
                ts = data_bids.index
            else:
                ts = ts.union(data.T.index)
                data_bids = data_bids.reindex(ts).ffill()
                data_aux = data.T.reindex(ts).ffill()
                data_bids += data_aux
        data_bids = data_bids.T.astype(int)
        # Check if volumes are correct
        error_list = self.__check_volumes(data_bids, self.jao_xml_bids)
        if not error_list:
            error_log = None
        else:
            error_log = "Errors found in bids file:\n" + "\n".join(error_list)
        # Save file
        date_str = self.date.strftime("%Y%m%d")
        pattern = "ETC_bid_" + date_str + ".xlsx"
        file_path = os.path.join(self.folder_path, pattern)
        data_bids.to_excel(file_path)
        return data_bids, file_path, error_log

    def __parse_results_old(self):
        error_log = ''
        # Find xml files
        date_str = self.today_date.strftime("%Y%m%d")
        if self.xge_bool:
            pattern = "HUPX_exchange_results*.xlsx"
        else:
            pattern = "ETC_" + date_str + "*.xls"
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            self.__log += f"No file available for xlsx exchange bids: {pattern} , please save manually \n"
            return None, None, None
        else:
            file_path = matching_files[-1]
        if self.xge_bool:
            data = self.__parse_hupx_results_data(file_path)
        else:
            data = pd.read_excel(file_path)
            # Locate the start of the table by identifying the header row
            header_row = data[data.iloc[:, 0] == "Hour"].index[0] + 1
            if data.iloc[header_row, 0] == 0:
                # Start with 0 hour
                end_row = data[data.iloc[:, 0] == 23].index[0] + 1
            else:
                # Start with 1 hour
                end_row = data[data.iloc[:, 0] == 24].index[0] + 1
            data = data.iloc[header_row:end_row, :].reset_index(drop=True)
            # Rename columns to match the desired structure
            data.columns = ["hour", "price", "volume"]
            data = data.set_index("hour")
        index = pd.Index(data.price.values).drop_duplicates()
        # Load bids xge
        data_bids_dict = {k: self.unify_index(v.T, index) for k, v in self.xge_bids_dict.items()}
        data_bids_diff_dict = {k: self.df_bids_diff(v.T, index) for k, v in self.xge_bids_dict.items()}
        data_bids_all = self.unify_index(self.xge_bids.copy().T, index)
        data_bids_all_diff = self.df_bids_diff(self.xge_bids.copy().T, index)
        # Output
        keys = ['hour', 'price', 'volume']
        out_dict = {m: {k: [] for k in keys} for m in data_bids_dict.keys()}
        for h in data.index:
            price = data.loc[h, 'price']
            tot_vol = data.loc[h, 'volume']
            bid_all_vol = data_bids_all.loc[price, h]
            bid_all_diff_vol = data_bids_all_diff.loc[price, h]
            if abs(tot_vol - bid_all_vol) < tol_vol:
                # We got full volume
                vol_test = 0
                for m in data_bids_dict.keys():
                    vol_m = data_bids_dict[m].loc[price, h]
                    out_dict[m]['hour'].append(h)
                    out_dict[m]['price'].append(price)
                    out_dict[m]['volume'].append(vol_m)  
                    vol_test += vol_m
                if abs(vol_test - tot_vol) > tol_vol:
                    error_log += f'Results: Volumes of xge bids in hour {h} do not match with total volume {vol_test} // {tot_vol} \n'
            elif tot_vol - bid_all_vol < -tol_vol:
                # We got partial volume
                partial_vol = round(bid_all_vol - tot_vol, 1)
                vol_test = 0
                rel_dict = {m: v.loc[price, h] / bid_all_diff_vol for m, v in data_bids_diff_dict.items()}
                for m in data_bids_dict.keys():
                    vol_m = data_bids_dict[m].loc[price, h]
                    vol_m -= rel_dict[m] * partial_vol
                    out_dict[m]['hour'].append(h)
                    out_dict[m]['price'].append(price)
                    out_dict[m]['volume'].append(vol_m)
                    vol_test += vol_m
                if abs(vol_test - tot_vol) > tol_vol:
                    error_log += f'Results: Volumes of xge bids in hour {h} do not match with total volume {vol_test} // {tot_vol} \n'
            else:
                # Overbought should not happen
                error_log += f'Results: Volumes of xge bids in hour {h} bigger with total volume {bid_all_vol} // {tot_vol} \n'
        # Save files
        date_str = self.date.strftime("%Y%m%d")
        file_path_dict = {}
        inv_dict = {v: k for k, v in self.inv_dict.items()}
        flow_dict = pd.DataFrame()
        for m in out_dict.keys():
            out_dict[m] = pd.DataFrame(out_dict[m]).set_index('hour')
            pattern = "ETC_results_" + date_str + "_" + str(m) + ".xlsx"
            file_path = os.path.join(self.folder_path, pattern)
            out_dict[m].to_excel(file_path)
            file_path_dict[m] = file_path
            # Flow dict populate
            flow_dict['HUUA_' + inv_dict[m]] = out_dict[m]['volume'].apply(lambda x: x if x > 0 else 0)
            flow_dict['UAHU_' + inv_dict[m]] = out_dict[m]['volume'].apply(lambda x: abs(x) if x < 0 else 0)
        # Path to flow dict
        pattern = "ETC_flows_" + date_str + ".xlsx"
        file_path = os.path.join(self.folder_path, pattern)
        flow_dict.to_excel(file_path)
        return out_dict, file_path_dict, error_log

    def __parse_results(self):
        error_log = ''
        # Find xml files
        date_str = self.today_date.strftime("%Y%m%d")
        if self.xge_bool:
            pattern = "HUPX_exchange_results*.xlsx"
        else:
            pattern = "ETC_" + date_str + "*.xls"
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            self.__log += f"No file available for xlsx exchange bids: {pattern} , please save manually \n"
            return None, None, None
        else:
            file_path = matching_files[-1]
        if self.xge_bool:
            data = self.__parse_hupx_results_data(file_path)
            self.__deal_confirmation_hupx(data)
        else:
            data = pd.read_excel(file_path)
            # Locate the start of the table by identifying the header row
            header_row = data[data.iloc[:, 0] == "Hour"].index[0] + 1
            if data.iloc[header_row, 0] == 0:
                # Start with 0 hour
                end_row = data[data.iloc[:, 0] == 23].index[0] + 1
            else:
                # Start with 1 hour
                end_row = data[data.iloc[:, 0] == 24].index[0] + 1
            data = data.iloc[header_row:end_row, :].reset_index(drop=True)
            # Rename columns to match the desired structure
            data.columns = ["hour", "price", "volume"]
            data = data.set_index("hour")
        index = pd.Index(data.price.values).drop_duplicates()
        # Vol diff prices
        p_diff = [y for x, y in zip(self.xge_bids.columns[:-1], self.xge_bids.columns[1:])
                  if abs(y - x - tol_price) < tol_price + 1e-9]
        # Change index according to 
        index = pd.Index([x - 0.01 if float(x) in p_diff else x for x in index])
        # Load bids xge
        data_bids_all = self.unify_index(self.xge_bids.copy().T, index)
        data_bids_all_diff = self.df_bids_diff(self.xge_bids.copy().T, index)
        data_bids_dict = {k: self.unify_index(v.T, data_bids_all.index) for k, v in self.xge_bids_dict.items()}
        data_bids_diff_dict = {k: self.df_bids_diff(v.T, data_bids_all.index) for k, v in self.xge_bids_dict.items()}
        # Output
        keys = ['hour', 'price', 'volume']
        out_dict = {m: {k: [] for k in keys} for m in data_bids_dict.keys()}
        for h in data.index:
            price_x = data.loc[h, 'price']
            if price_x in p_diff:
                price = price_x - 0.01
            else:
                price = price_x
            price_l = self.get_prev_value(data_bids_all.index, price)
            while price_l not in self.xge_bids.columns:
                price_l = self.get_prev_value(data_bids_all.index, price_l)
            price_n = self.get_next_value(self.xge_bids.columns, price_l)
            tot_vol = data.loc[h, 'volume']
            bid_all_vol = data_bids_all.loc[price, h]
            bid_all_diff_vol = data_bids_all_diff.loc[price, h]
            vol_dict = self.distribute(h, price, price_l, price_n, tot_vol, bid_all_vol,
                                       data_bids_dict, bid_all_diff_vol, data_bids_diff_dict)
            vol_test = 0
            for m, vol_m in vol_dict.items():
                if vol_m is None:
                    error_log += f'No feasible solution in hour {h}'
                    break
                out_dict[m]['hour'].append(h)
                out_dict[m]['price'].append(price_x)
                out_dict[m]['volume'].append(vol_m)
                vol_test += vol_m
            if abs(vol_test - tot_vol) > tol_vol:
                error_log += f'Results: Volumes of xge bids in hour {h} do not match with total volume {vol_test} // {tot_vol} \n'
        # Save files
        date_str = self.date.strftime("%Y%m%d")
        file_path_dict = {}
        inv_dict = {v: k for k, v in self.inv_dict.items()}
        # Flows excel
        head_index_list = ['Direction', 'EIC', 'Gran', 'CAI']
        # External schedule
        exter_dict = pd.DataFrame()
        for m in out_dict.keys():
            out_dict[m] = pd.DataFrame(out_dict[m]).set_index('hour')
            pattern = "ETC_results_" + date_str + "_" + str(m) + ".xlsx"
            file_path = os.path.join(self.folder_path, pattern)
            out_dict[m].to_excel(file_path)
            file_path_dict[m] = file_path
            # Flow dict populate
            # External schedule
            # HUUA direction
            vol_ser = out_dict[m]['volume'].apply(lambda x: x if x > 0 else 0)
            if vol_ser.sum() > 0:
                # Populate
                head_val_list = ['HU > UA', self.eic_dict[m], 'Daily',
                                 self.jao_cai_dict['buy']]
                head_ser = pd.Series(head_val_list, index=head_index_list)
                exter_dict['HUUA_' + inv_dict[m]] = pd.concat([head_ser, vol_ser])
            # UAHU direction
            vol_ser = out_dict[m]['volume'].apply(lambda x: abs(x) if x < 0 else 0)
            if vol_ser.sum() > 0:
                # Populate
                head_val_list = ['UA > HU', self.eic_dict[m], 'Daily',
                                 self.jao_cai_dict['sell']]
                head_ser = pd.Series(head_val_list, index=head_index_list)
                exter_dict['UAHU_' + inv_dict[m]] = pd.concat([head_ser, vol_ser])
        # Internal schedule
        inter_dict = pd.DataFrame()
        # Buy side
        vol_ser = data['volume'].apply(lambda x: x if x > 0 else 0)
        if vol_ser.sum() > 0:
            # Populate
            head_val_list = ['IMPORT', '15X-HUPX-------5']
            head_ser = pd.Series(head_val_list, index=head_index_list[:2])
            inter_dict['HUPX_ETC'] = pd.concat([head_ser, vol_ser])
        # Sell side
        vol_ser = data['volume'].apply(lambda x: abs(x) if x < 0 else 0)
        if vol_ser.sum() > 0:
            # Populate
            head_val_list = ['EXPORT', '15X-HUPX-------5']
            head_ser = pd.Series(head_val_list, index=head_index_list[:2])
            inter_dict['ETC_HUPX'] = pd.concat([head_ser, vol_ser])
        # Path to flow dict
        pattern = "ETC_flows_" + date_str + ".xlsx"
        file_path = os.path.join(self.folder_path, pattern)
        # flow_dict.to_excel(file_path)
        # Write to Excel with two sheets
        with pd.ExcelWriter(file_path) as writer:
            exter_dict.to_excel(writer, sheet_name='External')
            inter_dict.to_excel(writer, sheet_name='Internal')
        return out_dict, file_path_dict, error_log


    def __parse_hupx_results_data(self, file_path):
        data = pd.read_excel(file_path)
        # Locate the start of the table by identifying the header row
        header_row = data[data.iloc[:, 0] == "Period (cet/cest)"].index[0] + 1
        end_row = data[data.iloc[:, 0] == '23 - 00'].index[0] + 1
        # Locate columns
        col_list = ['Linear Schedule']
        idx_col = [0, 1]
        idx_col.extend([i for i, x in enumerate(data.iloc[header_row - 2, :].values)
                        if x in col_list])
        data = data.iloc[header_row:end_row, idx_col].reset_index(drop=True)
        data.columns = ['hour', 'price', 'volume']
        data.loc[:, 'hour'] = data.loc[:, 'hour'].str[:2].astype(int) + 1
        return data.set_index('hour')

    def distribute(self, h, price, price_l, price_n, tot_vol, bid_all_vol,
                   data_bids_dict, bid_all_diff_vol, data_bids_diff_dict):
        # Calculate boundaries
        bid_list = [(x.loc[price_l, h], x.loc[price_n, h]) for x in data_bids_dict.values()]
        # Transform into bounds buy and sell
        bound_list = []
        for v1, v2 in bid_list:
            buy_max = v1 if v1 > 0 else 0.0
            buy_min = v2 if v2 > 0 else 0.0
            sell_max = -v2 if v2 < 0 else 0.0
            sell_min = -v1 if v1 < 0 else 0.0
            
            bound_list.append((buy_min, buy_max, sell_min, sell_max))
        # If we have only buys or only sells then we use former algorithm
        # Sell max must be 0
        only_buy = all([x[3] == 0 for x in bound_list])
        # Buy max must be 0
        # only_sell = all([x[1] == 0 for x in bound_list])
        if only_buy:
            # Old method
            out_dict = self.frac_distribution(h, price, tot_vol, bid_all_vol, data_bids_dict,
                                              bid_all_diff_vol, data_bids_diff_dict)
        else:
            # Merge buys and sells
            # Opt method
            vec_b_min = [x[0] for x in bound_list]
            vec_b_max = [x[1] for x in bound_list]
            vec_s_min = [x[2] for x in bound_list]
            vec_s_max = [x[3] for x in bound_list]
            factor_vec = [self.fac_dict[k] for k in data_bids_dict.keys()]
            aux_dict = self.optim_distribution(tot_vol, vec_b_min, vec_b_max, vec_s_min, vec_s_max, factor_vec)
            out_dict = {}
            for i, m in enumerate(data_bids_dict.keys()):
                out_dict[m] = aux_dict[i]
        return out_dict

    @staticmethod
    def frac_distribution(h, price, tot_vol, bid_all_vol, data_bids_dict,
                          bid_all_diff_vol, data_bids_diff_dict):
        out_dict = {}
        if abs(tot_vol - bid_all_vol) < tol_vol:
            # We got full volume
            for m in data_bids_dict.keys():
                vol_m = data_bids_dict[m].loc[price, h]
                out_dict[m] = vol_m
        elif tot_vol - bid_all_vol < -tol_vol:
            # We got partial volume
            partial_vol = round(bid_all_vol - tot_vol, 1)
            rel_dict = {m: v.loc[price, h] / bid_all_diff_vol for m, v in data_bids_diff_dict.items()}
            for m in data_bids_dict.keys():
                vol_m = data_bids_dict[m].loc[price, h]
                vol_m -= rel_dict[m] * partial_vol
                out_dict[m] = vol_m
        return out_dict

    @staticmethod
    def optim_distribution(tot_vol, vec_b_min, vec_b_max, vec_s_min, vec_s_max,
                           factor_list):
        n = len(factor_list)
        # Objective function: maximize B1 + S1 + B2 + S2
        c = []
        # minimize negative sum = maximize sum
        [c.extend([-x] * 2) for x in factor_list] # minimize negative sum = maximize sum
    
        # Constraints: (B1 - S1) + (B2 - S2) = V_M
        A_eq = [[1, -1] * n]
        b_eq = [tot_vol]
    
        # Variable bounds
        bounds = []
        bounds.extend([(b_min, b_max), (s_min, s_max)] for
                      b_min, b_max, s_min, s_max in
                      zip(vec_b_min, vec_b_max, vec_s_min, vec_s_max))
        bounds = [b for pair in bounds for b in pair]
        # General optimization
        res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')
    
        if res.success:
            return {i: res.x[2*i] - res.x[2*i + 1] for i in range(n)}
        else:
            return {i: None for i in range(n)}

    def __deal_confirmation(self, data, idx):
        # Load deal confirmation data
        date_str = self.date.strftime("%Y%m%d")
        path = os.path.join(self.path, "deal_conf", self.date.strftime("%y%m"))
        file_name = f"Deal_confirmation_HUUA_{idx}.xlsx"
        file_path = os.path.join(path, file_name)
        
        # Read the data using pandas
        data_all = pd.read_excel(file_path)
        
        # Find indices of date
        idx_date = [i + 4 for i, x in enumerate(data_all.iloc[2:, 0]) if x.date() == self.date]
        
        # Prepare data
        hupx_q_list_, hupx_p_list = (data.loc[:, x].values for x in ['volume', 'price'])
        
        idx_jao = {s: v.index(idx) if idx in v else None for s, v in self.cmp_dict.items()}
        jao_p_dict = {side: self.jao_xml_price[side].values for side in self.side_list}
        jao_q_dict = {}
        for s in self.side_list:
            if idx_jao[s] is None:
                try:
                    jao_q_dict[s] = self.jao_xml_list[s][0].loc[:, 'awd_qty'] * 0
                except IndexError:
                    o_s = self.opp_side[s]
                    jao_q_dict[s] = self.jao_xml_list[o_s][0].loc[:, 'awd_qty'] * 0
            else:
                jao_q_dict[s] = self.jao_xml_list[s][idx_jao[s]].loc[:, 'awd_qty']
        # Open workbook with xlwings
        app = xw.App(visible=False)  # Run Excel in the background
        try:
            wb = app.books.open(file_path)
            
            for s in self.side_list:
                jao_p_list = jao_p_dict[s]
                jao_q_list = jao_q_dict[s]
                if s == 'buy':
                    hupx_q_list = [q if q > 0 else 0 for q in hupx_q_list_]
                    sheet = wb.sheets["HU_UA"]
                else:
                    hupx_q_list = [-q if q < 0 else 0 for q in hupx_q_list_]
                    sheet = wb.sheets["UA_HU"]
            
                if (len(idx_date) != len(hupx_q_list)) or (len(idx_date) != len(jao_q_list)):
                    self.__log += "deal_confirmation: length of date indices are not equal "
                    self.__log += f"{len(idx_date)} // {len(hupx_q_list)} // {len(jao_q_list)} \n"
                    return None
                
                # Write data to the workbook
                for row, j_q, j_p, h_q, h_p in zip(idx_date, jao_q_list, jao_p_list, hupx_q_list, hupx_p_list):
                    sheet.range(f"E{row}").value = j_p  # Jao price
                    if j_q > 0:
                        sheet.range(f"G{row}").value = j_q  # Jao quantity (if greater than 0)
                    sheet.range(f"F{row}").value = h_p  # HUPX price
                    if h_q > 0:
                        sheet.range(f"H{row}").value = h_q  # HUPX quantity (if greater than 0)
            # Save the workbook with recalculated formulas
            wb.api.RefreshAll()  # Refresh formulas
            # wb.api.CalculateFull()  # Ensure full calculation
            file_name_date = f"Deal_confirmation_HUUA_{date_str}_{idx}.xlsx"
            file_path_date = os.path.join(self.folder_path, file_name_date)
            wb.save(file_path_date)
            wb.save(file_path)
        finally:
            wb.close()
            app.quit()
        
        return file_path_date

    def __deal_confirmation_hupx(self, data):
        # Load deal confirmation data
        path = os.path.join(self.path, "deal_conf", self.date.strftime("%y%m"))
        file_name = "HUPX_results_HUUA.xlsx"
        file_path = os.path.join(path, file_name)
        
        # Read the data using pandas
        data_all = pd.read_excel(file_path)
        
        # Find indices of date
        idx_date = [i + 4 for i, x in enumerate(data_all.iloc[2:, 0]) if x.date() == self.date]
        
        # Prepare data
        hupx_q_list_, hupx_p_list = (data.loc[:, x].values for x in ['volume', 'price'])
        # Open workbook with xlwings
        app = xw.App(visible=False)  # Run Excel in the background
        try:
            wb = app.books.open(file_path)
            
            for s in self.side_list:
                if s == 'buy':
                    hupx_q_list = [q if q > 0 else 0 for q in hupx_q_list_]
                    sheet = wb.sheets["HU_UA"]
                else:
                    hupx_q_list = [-q if q < 0 else 0 for q in hupx_q_list_]
                    sheet = wb.sheets["UA_HU"]
            
                if (len(idx_date) != len(hupx_q_list)):
                    self.__log += "HUPX_results: length of date indices are not equal "
                    self.__log += f"{len(idx_date)} // {len(hupx_q_list)} \n"
                    return 0

                # Write data to the workbook
                for row, h_q, h_p in zip(idx_date, hupx_q_list, hupx_p_list):
                    sheet.range(f"E{row}").value = h_p  # HUPX price
                    if h_q > 0:
                        sheet.range(f"F{row}").value = h_q  # HUPX quantity (if greater than 0)
            # Save the workbook with recalculated formulas
            wb.api.RefreshAll()  # Refresh formulas
            wb.save(file_path)
        finally:
            wb.close()
            app.quit()

        return 0

    @staticmethod
    def __check_alternating_columns(df):
        # Extract column names
        columns = list(df.columns)
        
        # Initialize a list to collect errors
        errors = []
        
        # Check if columns are sorted in ascending order
        if columns != sorted(columns):
            errors.append("Columns are not sorted in ascending order.")
        
        # Check the alternating pattern
        for i in range(1, len(columns)):
            if i % 2 == 1:  # Odd-indexed columns: arbitrary number > previous
                if columns[i] <= columns[i-1]:
                    errors.append(
                        f"Column at index {i} ({columns[i]}) must be greater than column at index {i-1} ({columns[i-1]})."
                    )
            else:  # Even-indexed columns: must be previous + 0.1
                if abs(columns[i] - (columns[i-1] + tol_price)) > tol_price + 1e-9:
                    errors.append(
                        f"Column at index {i} ({columns[i]}) must be equal to column at index {i-1} ({columns[i-1]}) + {tol_price}."
                    )
        
        # Return results
        if not errors:
            return []
        else:
            return errors

    @staticmethod
    def __check_volumes(df, ser_max_dict):
        # Extract column names
        columns = df.columns
        errors = []
        first_col = columns[0]
        if 'buy' in ser_max_dict.keys():
            ser_max = ser_max_dict['buy']
            if (df.loc[df[first_col] > 0, first_col] <= ser_max.loc[df[first_col] > 0]).all():
                pass
            else:
                errors.append(f"First column {first_col} exceeds maximal capacity BUY obtained in JAO.")
                return errors
        if 'sell' in ser_max_dict.keys():
            ser_max = ser_max_dict['sell']
            if (-df.loc[df[first_col] < 0, first_col] <= ser_max.loc[df[first_col] < 0]).all():
                pass
            else:
                errors.append(f"First column {first_col} exceeds maximal capacity BUY obtained in JAO.")
                return errors
        
        # Iterate through columns pairwise
        for i in range(len(columns) - 1):
            col1 = columns[i]
            col2 = columns[i + 1]
            diff = round(col2 - col1, 2)
            
            # Case 1: Difference greater than 0.1
            if diff > tol_price:
                if not df[col1].equals(df[col2]):
                    errors.append(f"Rows in columns {col1} and {col2} are not the same (difference > {tol_price}).")
            
            # Case 2: Difference exactly 0.1
            elif abs(diff - tol_price) < tol_price + 1e-9:
                if not (df[col1] >= df[col2]).all():
                    errors.append(f"Column {col2} does not have all rows lower than column {col1} (difference = {tol_price}).")
        
        # Return results
        if not errors:
            return []
        else:
            return errors

    def df_bids_diff(self, df_bids, index):
        df_bids = df_bids.diff(-1)
        df_bids.iloc[0, :] = df_bids.iloc[0, :]
        # Unify indices
        return self.unify_index(df_bids, index)

    @staticmethod
    def unify_index(df_bids, index):
        # Unify indices
        ts = index.union(df_bids.index)
        return df_bids.reindex(ts).ffill()

    @staticmethod
    def get_prev_value(index, value):
        loc = index.get_loc(value)  # Get position of the value
        if loc > 0:  # Ensure there is a previous value
            return index[loc - 1]  # Previous and current value
        else:
            return index[loc]

    @staticmethod
    def get_next_value(index, value):
        loc = index.get_loc(value)  # Get position of the value
        if loc < len(index) - 1:  # Ensure there is a next value
            return index[loc + 1]  # Previous and current value
        else:
            return index[loc]


def format_volume(value):
    if value.is_integer():  # Check if the value is an integer
        return str(int(value))  # Convert to integer and then string
    else:
        return f"{value:.1f}".replace('.', ',')


# Function to handle button click and change the circle's color
def show_dataframe(df):
    popup = Toplevel(window)
    popup.title("DataFrame Viewer")
    popup.geometry("400x800")

    # Add a Treeview widget for displaying the DataFrame
    tree = ttk.Treeview(popup, columns=list(df.columns), show="headings")
    tree.pack(expand=True, fill="both", padx=10, pady=10)

    # Add column headings
    for col in df.columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=20)  # Center-align the text

    # Insert DataFrame rows into the Treeview
    for _, row in df.iterrows():
        tree.insert("", tk.END, values=list(row))

    # Close button
    close_button = tk.Button(popup, text="Close", command=popup.destroy)
    close_button.pack(pady=5)


def calculate_color(value, min_val, max_val):
    """Generate a color gradient from white to red based on the value."""
    if pd.isnull(value):  # Handle NaN values
        return "#FFFFFF"
    if abs(max_val - min_val) < tol_vol:
        intensity = 0
    else:
        intensity = int(255 * (value - min_val) / (max_val - min_val))
    return f"#FF{255 - intensity:02X}{255 - intensity:02X}"


def show_dataframe_with_heatmap(df, column_scale=False, mkt_str=None):
    popup = Toplevel(window)
    title = "Colored DataFrame Viewer "
    if mkt_str is not None:
        title += str(mkt_str)
    popup.title(title)
    popup.geometry("400x900")

    # Canvas for rendering the DataFrame
    canvas = tk.Canvas(popup, bg="white")
    canvas.pack(fill=tk.BOTH, expand=True)

    # Calculate global min and max values for all numeric columns
    if column_scale:
        min_val = df.min()
        max_val = df.max()
    else:
        min_val = df.min().min()
        max_val = df.max().max()

    # Cell dimensions
    cell_width = 60
    cell_height = 30
    x_offset = 50
    y_offset = 30

    # Draw table headers
    for col_idx, col in enumerate(df.columns):
        canvas.create_rectangle(
            x_offset + col_idx * cell_width,
            y_offset,
            x_offset + (col_idx + 1) * cell_width,
            y_offset + cell_height,
            fill="lightgrey",
            outline="black"
        )
        canvas.create_text(
            x_offset + col_idx * cell_width + cell_width / 2,
            y_offset + cell_height / 2,
            text=col,
            font=("Arial", 10, "bold")
        )

    # Draw table cells
    for row_idx, row in df.iterrows():
        for col_idx, col in enumerate(df.columns):
            value = row[col]
            if col_idx == 0:
                color = "lightgrey"
                value = int(value)
            else:
                if column_scale:
                    color = calculate_color(value, min_val.loc[col], max_val.loc[col])
                else:
                    color = calculate_color(value, min_val, max_val)

            # Draw the cell background
            canvas.create_rectangle(
                x_offset + col_idx * cell_width,
                y_offset + (row_idx + 1) * cell_height,
                x_offset + (col_idx + 1) * cell_width,
                y_offset + (row_idx + 2) * cell_height,
                fill=color,
                outline="black"
            )

            # Add the cell value as text
            canvas.create_text(
                x_offset + col_idx * cell_width + cell_width / 2,
                y_offset + (row_idx + 1) * cell_height + cell_height / 2,
                text=str(round(value, 2)),
                font=("Arial", 10)
            )

    # Add a Close button
    close_button = tk.Button(popup, text="Close", command=popup.destroy)
    close_button.pack(pady=10)


def change_circle_color(circle_id):
    canvas.itemconfig(circle_id, fill="green")


def jao_bids(app_class, circle_id):
    selected_option = dropdown.get()
    contract_id_dict, document_id_dict, data_dict = app_class.load_xml()
    idx_ = app_class.get_index(selected_option)
    if app_class.jao_xml_bool:
        if idx_ not in ['all', 'None']:
            # data_list = [data_list[idx_]]
            data_list = [{s: data_dict[s][idx_] for s in app_class.side_list}]
            idx_list = [idx_]
        elif idx_ == 'all':
            idx_list = list(app_class.jao_dict.keys())
            idx_list = [k for k in app_class.jao_dict.keys() if app_class.check_cmp(k)]
            data_list = [{s: data_dict[s][i] for s in app_class.side_list} for i in idx_list]
        else:
            idx_list = [0]
            data_list = [{s: data_dict[s][0] for s in app_class.side_list}]
        try:
            for data_d, idx in zip(data_list, idx_list):
                app_class.send_xml(data_d, contract_id_dict, document_id_dict, idx)
            messagebox.showinfo("Mail sent", "Success!")
            change_circle_color(circle_id)
        except OSError as e:
            messagebox.showinfo("Mail Issue", "Mail Issue, try again!")
            messagebox.showinfo("Error", e)
        # app.send_xml(data, contract_id, document_id)
        # messagebox.showinfo("Popup Message", "Success!")
        # change_circle_color(circle_id)
    else:
        messagebox.showinfo("Mail not sent", app_class.log)


def xge_bids(app_class, circle_id):
    selected_option = dropdown.get()
    idx = app_class.get_index(selected_option)
    error_log, file_path, data = app_class.load_xge_bids(str(idx))
    if error_log is not None:
        messagebox.showinfo("Popup Message", error_log)
    else:
        try:
            app_class.send_xge_bids(file_path)
            if app_class.xge_bids_bool:
                change_circle_color(circle_id)
                messagebox.showinfo("Popup Message", "Success!")
            else:
                messagebox.showinfo("Popup Message", "Something gone wrong!")
        except OSError:
            messagebox.showinfo("Popup Message", "Mail Issue, try again!")


def xge_results(app_class, circle_id, mkt_idx=None):
    selected_option = dropdown.get()
    idx = app_class.get_index(selected_option)
    if idx not in ['all', 'None']:
        idx_list = [idx]
    elif idx == 'all':
        idx_list = list(app_class.jao_dict.keys())
        idx_list = [k for k in app_class.jao_dict.keys() if app_class.check_cmp(k)]
    else:
        idx_list = [0]
    if mkt_idx is None:
        error_log, file_path_list, data_list = app_class.load_results(str(idx))
        if error_log:
            messagebox.showinfo("Popup Message", error_log)
        else:
            try:
                for data, file_path, i in zip(data_list, file_path_list, idx_list):
                    app_class.send_results(file_path, data, i)
                if app_class.xge_results_bool:
                    change_circle_color(circle_id)
                    button10.configure(bg="blue", fg="red")
                    messagebox.showinfo("Popup Message", "Success!")
                else:
                    messagebox.showinfo("Popup Message", "Something gone wrong!")
            except OSError:
                messagebox.showinfo("Popup Message", "Mail Issue, try again!")      
    else:
        if (idx == 'all') or (idx == app_class.get_index(mkt_idx)):
            idx = app_class.get_index(mkt_idx)
            if idx not in ['all', 'None']:
                idx_list = [idx]
            elif idx == 'all':
                idx_list = list(app_class.jao_dict.keys())
                idx_list = [k for k in app_class.jao_dict.keys() if app_class.check_cmp(k)]
            else:
                idx_list = [0]
            error_log, file_path_list, data_list = app_class.load_results(str(idx))
            if error_log:
                messagebox.showinfo("Popup Message", error_log)
            else:
                try:
                    for data, file_path, i in zip(data_list, file_path_list, idx_list):
                        app_class.send_results(file_path, data, i)
                        if app_class.xge_results_bool:
                            bool_dict[mkt_idx] = True
                    if all([v for v in bool_dict.values()]):
                        change_circle_color(circle_id)
                        button10.configure(bg="blue", fg="red")
                        messagebox.showinfo("Popup Message", "Success!")
                except OSError:
                    messagebox.showinfo("Popup Message", "Mail Issue, try again!")
        else:
            pass


def show_logs(app_class):
    messagebox.showinfo("Logs", app_class.log)
    

def jao_bids_button(app_class):
    selected_option = dropdown.get()
    _, _, data_dict = app_class.load_xml()
    idx = app_class.get_index(selected_option)
    if app_class.jao_xml_bool:
        data = None
        type_dict = {'hour': 'int64'}
        for s in app_class.side_list:
            type_dict['awd_qty_' + s] = 'int64'
            if idx in ['all', 'None']:
                if data is None:
                    data = app_class.jao_xml_bids[s].to_frame()
                else:
                    data = pd.concat([data, app_class.jao_xml_bids[s].to_frame()], axis=1)
            else:
                if data_dict[s][idx].loc[:, 'awd_qty'].empty:
                    data_new = pd.DataFrame(0, index=range(1, 25), columns=['awd_qty'])
                    data_new.index.name = 'hour'
                else:
                    data_new = data_dict[s][idx].loc[:, 'awd_qty'].to_frame()
                if data is None:
                    data = data_new
                else:
                    data = pd.concat([data, data_new], axis=1)
        data.columns = ['awd_qty_' + s for s in app_class.side_list]
        data = data.reset_index()
        data.fillna(0, inplace=True)
        show_dataframe_with_heatmap(data.astype(type_dict))


def xge_bids_button(app_class):
    selected_option = dropdown.get()
    idx = app_class.get_index(selected_option)
    app_class.load_xml()
    error_log, file_path, data = app_class.load_xge_bids(str(idx))
    data = data.reset_index()
    show_dataframe_with_heatmap(data)
    if not app_class.xge_bids_bool:
        messagebox.showinfo("Popup Message", error_log)


def xge_results_button(app_class):
    selected_option = dropdown.get()
    idx = app_class.get_index(selected_option)
    app_class.load_xml()
    app_class.load_xge_bids(str(idx))
    error_log, file_path_list, data_list = app_class.load_results(str(idx))
    if idx == 'all':
        idx_list = list(app_class.inv_dict.keys())
    elif idx == 'None':
        idx_list = [None]
    else:
        idx_list = [selected_option]
    for data, i in zip(data_list, idx_list):
        data = data.reset_index()
        type_dict = {'hour': 'int64', 'price': 'float64', 'volume': 'float64'}
        show_dataframe_with_heatmap(data.astype(type_dict), True, i)
        if not app_class.xge_results_bool:
            messagebox.showinfo("Popup Message", error_log)
        else:
            button10.configure(bg="blue", fg="red")

def save_deal_conf_button(app):
    idx_2_names_map = {
        0: 'VS ENERGY',
        1: 'NG',
        2: 'UH',
        3: 'GE',
        'HUUA': 'HUPX'
    }

    # Load deal confirmation data
    date_str = app.date.strftime("%Y%m%d")
    path = os.path.join(app.path, "deal_conf", app.date.strftime("%y%m"))

    # Loop through each deal conf
    for file in os.listdir(path):
        file_path = os.path.join(path, file)
        
        base_name = os.path.splitext(file)[0]  # Remove .xlsx extension
        name_parts = base_name.rsplit("_", 1)  # Split at the last '_'

        if len(name_parts) < 2:
            print(f"Skipping file {file} - doesn't match expected naming pattern.")
            continue  # Ensure there's an index at the end

        idx_str = name_parts[-1]  # Last part is expected index
        try:
            idx = int(idx_str)  # Try converting to integer
        except ValueError:
            try:
                idx_str == 'HUUA'
                idx = 'HUUA'  # If integer fails, try converting to float
            except ValueError:
                print(f"Skipping file {file} - index '{idx_str}' is neither an integer nor a HUUA for HUPX name.")
                continue  # Skip files where the last part isn't a valid number


        # Check if index is mapped
        company = idx_2_names_map.get(idx)
        if company is None:
            print(f"Skipping file {file} - no mapping for index {idx}")
            continue  # Skip files with an unknown index

        # Create destination path
        year_str = app.date.strftime("%Y")
        folder_date_str = app.date.replace(day=1).strftime("%Y%m%d")

        if idx_str in ['HUUA']:
            dest_path = os.path.join("//192.168.10.10/net/",
                                    year_str, "Ukrajina/1_UKRAJINA",
                                    company, "CONFIRMATION", folder_date_str,
                                    f"{name_parts[0]}_{idx_str}.xlsx")  # Fixed .xlsx extension
        else:
            dest_path = os.path.join("//192.168.10.10/net/",
                                year_str, "Ukrajina/1_UKRAJINA",
                                company, "CONFIRMATION", folder_date_str,
                                f"{name_parts[0]}_{date_str}.xlsx")  # Fixed .xlsx extension

        # Copy file
        shutil.copy(file_path, dest_path)
        button10.configure(bg="blue", fg="green")
        print(f"Copied {file} to {dest_path}")

def update_deal_conf_template(app):
    """
    Finds the latest deal confirmation file in the destination folder based on
    the date string in its filename, removes the date, replaces it with an index,
    and copies it back to the source folder with the new filename.
 
    Parameters:
        app (object): An application object containing `date` and `path` attributes.
    """
 
    # Mapping for destination folders to index
    names_2_idx_map = {
        'VS ENERGY': 0,
        'NG': 1,
        'UH': 2,
        'GE': 3,
        'HUPX': 'HUUA'
    }
 
    # Define paths
    year_str = app.date.strftime("%Y")
    folder_date_str = app.date.replace(day=1).strftime("%Y%m%d")
    dest_base_path = "//192.168.10.10/net/"
    source_path = os.path.join(app.path, "deal_conf", app.date.strftime("%y%m"))
 
   
 
    # Iterate over company folders
    for company, idx in names_2_idx_map.items():
        # Initialize variables to track the latest file
        latest_file = None
        latest_date = None
        latest_company = None  # Store company folder name
        dest_folder = os.path.join(dest_base_path, year_str, "Ukrajina/1_UKRAJINA", company, "CONFIRMATION", folder_date_str)
       
        if not os.path.exists(dest_folder):
            continue  # Skip if folder doesn't exist
 
        for file in os.listdir(dest_folder):
            file_path = os.path.join(dest_folder, file)
            if not os.path.isfile(file_path):
                continue  # Skip directories
 
            # Extract base name and check for expected pattern
            base_name, ext = os.path.splitext(file)
            name_parts = base_name.rsplit("_", 1)  # Split at last underscore
            if 'predplatby' in name_parts[0].lower():
                continue
            if len(name_parts) != 2:
                print(f"Skipping file {file} - doesn't match expected pattern.")
                continue
           
            date_part = name_parts[-1]
           
            # Validate and parse the date
            try:
                file_date = datetime.strptime(date_part, "%Y%m%d")
                # Update latest file based on the date in the filename
                if latest_date is None or file_date > latest_date:
                    latest_date = file_date
                    latest_file = file
                    latest_company = company  # Store associated company
            except:
                try:
                    date_part == 'HUUA'
                    latest_file = file
                    latest_company = company  # Store associated company
                except ValueError:
                    print(f"Skipping file {file} - invalid date format: {date_part} or file is not for HUPX")
                    continue
 
           
 
        # If no valid file is found, exit
        if not latest_file:
            print("No valid files found in the destination folder.")
            return
 
        # Extract filename parts and remove date
        base_name, ext = os.path.splitext(latest_file)
        name_parts = base_name.rsplit("_", 1)  # Remove date part
        new_base_name = name_parts[0]  # Keep only the base name
 
        # Determine the index based on company
        company_idx = names_2_idx_map.get(latest_company, "UNKNOWN")
        new_file_name = f"{new_base_name}_{company_idx}{ext}"  # Insert index instead of date
 
        # Define new file path in the source folder
        new_file_path = os.path.join(source_path, new_file_name)
 
        # Copy file back to the source folder with new name
        shutil.copy(os.path.join(dest_base_path, year_str, "Ukrajina/1_UKRAJINA", latest_company, "CONFIRMATION", folder_date_str, latest_file), new_file_path)
 
        print(f"Copied latest file {latest_file} as {new_file_name} to {source_path}")

# Function to handle dropdown selection
def handle_selection(event):
    selected_option = dropdown.get()
    label.config(text=f"Selected Company: {selected_option}")
    canvas.itemconfig(circle1, fill="red")
    canvas.itemconfig(circle2, fill="red")
    bool_dict = {k: False for k in app.inv_dict.keys()}


def handle_selection_side(event):
    selected_option = dropdown_side.get()
    label_side.config(text=f"Selected Side: {selected_option}")
    canvas.itemconfig(circle1, fill="red")
    canvas.itemconfig(circle2, fill="red")
    bool_dict = {k: False for k in app.inv_dict.keys()}
    app.set_side_list(selected_option)


# app = UA_APP(date=datetime(2025,3,15).date(), test_bool=False)
app = UA_APP(test_bool=False)
name_dict = {v: k for k, v in app.inv_dict.items()}
bool_dict = {k: False for k in app.inv_dict.keys()}

# Create the main window
name = "UA Capa GUI_" + app.date_string
if app.test_bool:
    name += "_TEST"
window = tk.Tk()
window.title(name)
window.geometry("600x500")

# Load the background image
try:
    bg_image = Image.open(default_path + "logo.png")
    bg_image = bg_image.resize((115, 30), Image.LANCZOS)
    bg_photo = ImageTk.PhotoImage(bg_image)
except Exception as e:
    print(f"Error loading image: {e}")
    bg_photo = None

# ---------------------------
# Top Frame: Dropdowns using Grid
# ---------------------------
top_frame = tk.Frame(window)
top_frame.pack(side=tk.TOP, fill=tk.X, pady=10)

# Company Label and Dropdown (Column 0)
label = tk.Label(top_frame, text="Select an option Company:", font=("Arial", 12))
label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
options_comp = ["All", "VS", "NaftoGaz", "UH", "GE", "None"]
dropdown = ttk.Combobox(top_frame, values=options_comp, state="readonly")
dropdown.set("All")
dropdown.grid(row=1, column=0, padx=10, pady=10, sticky="w")
dropdown.bind("<<ComboboxSelected>>", handle_selection)

# Side Label and Dropdown (Column 1)
label_side = tk.Label(top_frame, text="Select an option Side:", font=("Arial", 12))
label_side.grid(row=0, column=1, padx=10, pady=10, sticky="w")
options_side = ["All", "buy", "sell"]
dropdown_side = ttk.Combobox(top_frame, values=options_side, state="readonly")
dropdown_side.set("All")
dropdown_side.grid(row=1, column=1, padx=10, pady=10, sticky="w")
dropdown_side.bind("<<ComboboxSelected>>", handle_selection_side)

# ---------------------------
# Bottom Frame: Buttons and Canvas using Pack
# ---------------------------
bottom_frame = tk.Frame(window)
bottom_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

# Button Frame on the left inside bottom_frame
button_frame = tk.Frame(bottom_frame, width=250, height=300)
button_frame.pack(side=tk.LEFT, padx=10, pady=10)

button1 = tk.Button(button_frame, text="L&S JAO Bids", command=lambda: jao_bids(app, None))
button1.place(x=10, y=55, width=120, height=30)
button2 = tk.Button(button_frame, text="L&S Xchange Bids", command=lambda: xge_bids(app, None))
button2.place(x=10, y=105, width=120, height=30)
button3 = tk.Button(button_frame, text="Xge Results", command=lambda: xge_results(app, None))
button3.place(x=10, y=155, width=120, height=30)
# Example of buttons with names from name_dict
button4 = tk.Button(button_frame, text=name_dict[0], command=lambda: xge_results(app, None, name_dict[0]))
button4.place(x=130, y=155, width=60, height=30)
button5 = tk.Button(button_frame, text=name_dict[1], command=lambda: xge_results(app, None, name_dict[1]))
button5.place(x=190, y=155, width=60, height=30)
button6 = tk.Button(button_frame, text="Show Logs", command=lambda: show_logs(app))
button6.place(x=10, y=205, width=120, height=30)
button7 = tk.Button(button_frame, text="Show Jao Bids", command=lambda: jao_bids_button(app))
button7.place(x=10, y=255, width=120, height=30)
button8 = tk.Button(button_frame, text="Show Xge Bids", command=lambda: xge_bids_button(app))
button8.place(x=130, y=255, width=120, height=30)
button9 = tk.Button(button_frame, text="Show Xge Rslt", command=lambda: xge_results_button(app))
button9.place(x=130, y=205, width=120, height=30)
button10 = tk.Button(button_frame, text="Save Deal confs", command=lambda: save_deal_conf_button(app))
button10.place(x=130, y=105, width=120, height=30)
button11 = tk.Button(button_frame, text="Update DC templates", command=lambda: update_deal_conf_template(app))
button11.place(x=130, y=55, width=120, height=30)

# Canvas on the right inside bottom_frame
canvas = Canvas(bottom_frame, width=200, height=300)
canvas.pack(side=tk.RIGHT, padx=10, pady=10)


# Display the background image on the canvas (if available)
if bg_photo:
    canvas.create_image(55, 250, image=bg_photo, anchor="nw")

# Draw three vertically aligned small red circles on the canvas
circle1 = canvas.create_oval(150, 50, 160, 60, fill="red")
circle2 = canvas.create_oval(150, 100, 160, 110, fill="red")
circle3 = canvas.create_oval(150, 150, 160, 160, fill="red")

window.mainloop()
