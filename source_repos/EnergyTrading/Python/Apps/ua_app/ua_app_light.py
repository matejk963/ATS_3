#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 23 19:48:06 2025

@author: marek
"""

import tkinter as tk
from tkinter import Canvas, messagebox, ttk, Toplevel
from PIL import Image, ImageTk
import glob
import os
import re
import shutil
from datetime import datetime, timedelta
import pandas as pd
import json
import requests
import subprocess

import smtplib
from email.message import EmailMessage

default_path = "/Users/marek/Work/Projects/vs_app/"
default_path = os.getcwd() + '/'
if default_path.split('/')[-2] == 'apps':
    default_path = os.path.dirname(os.getcwd()) + '/'
tol_price = .01
tol_vol = .01


class UA_APP_LIGHT:
    def __init__(self, date=None, path=default_path, test_bool=False):
        if date is None:
            self.date = (datetime.today() + timedelta(days=1)).date()
        else:
            self.date = date
        self.path = path
        self.__archive()
        self.__init()
        self.__test_bool = test_bool
        self.size = 0
        self.mac_numbers_bool = False
        # Load config
        self.load_config()
        self.__log = ''
        self.side_dict = {'buy': False, 'sell': False}

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
    def folder_path(self):
        return self.path + self.date_string

    @property
    def side_list(self):
        return [k for k, v in self.side_dict.items() if v]

    @property
    def log(self):
        return self.__log

    @staticmethod
    def load_curr_rate():
        response = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json")
        if response.status_code == 200:
            data = response.json()
            return data[0]['rate']
        else:
            raise ValueError("Failed to fetch rate")

    def __init(self):
        """
        Checks if a folder with today's date (format yyyy_mm_dd) exists in `self.path`.
        If not, creates it.
        """
        today_str = self.date_string  # Assuming self.date is a datetime.date object
        folder_path = os.path.join(self.path, today_str)
        
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"Created folder for today: {today_str}")
        else:
            print(f"Folder for today already exists: {today_str}")

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
        config_keys = ['EMAIL_LOGIN', 'MAIL_ETC']
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
            self.fee_dict = {k: v for k, v in aux_dict.items()}
            self.mac_numbers_bool = config_dict['BOOL_DICT']['NUMBERS_BOOL']
        # Load credentials
        PATH_LOGIN = self.path + 'config_login.json'
        with open(PATH_LOGIN, 'r') as file:
            config_dict = json.load(file)
            self.config['EMAIL_LOGIN'] = {k: v for k, v in config_dict['EMAIL_LOGIN'].items()}

    def load_jao(self):
        self.jao_xml_dict = {}
        for s in self.side_dict.keys():
            df_jao_result = self.__parse_jao(s)
            if df_jao_result is None:
                self.side_dict[s] = False
            else:
                self.side_dict[s] = True
                self.jao_xml_dict[s] = df_jao_result

    def __parse_jao(self, side):
        date_str = self.date.strftime("%Y%m%d")
        # Find all matching files
        if side == 'buy':
            direction = 'HUUA'
        else:
            direction = 'UAHU'
        pattern = "jao_results_" + direction + "_" + date_str + "*.csv"
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            self.__log += f"No file available for xls exchange results: {pattern} , please save manually \n"
            return None
        else:
            file_path = matching_files[-1]
        data = pd.read_csv(file_path).set_index('hour')
        # Make sure that for 24th hour is 0
        data.iloc[-1, 2] = 0.0
        self.size = max(self.size, data.shape[0])
        return data

    def get_xge_bids(self):
        # Load jao
        self.load_jao()
        # Load data
        data_dict = self.__parse_xge_results()
        if not data_dict:
            return None, None
        data_bids_list = []
        for s in self.side_list:
            df_jao = self.jao_xml_dict[s]
            df_aux = pd.concat([df_jao, data_dict[s]], axis=1)
            # Prepare data
            if s == 'buy':
                sign = 1
                data = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500])
                data_end = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[4000])
                bfill_bool = True
            else:
                sign = -1
                data = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500])
                data_end = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[-500, 4000])
                bfill_bool = False
            data.index.name = 'Hourly / Price'
            if df_jao.empty:
                pass
            else: 
                q_list = df_aux.loc[:, 'awd_qty'].values
                p_list = df_aux.loc[:, s].values
                clr_list = list(set([p for q, p in zip(q_list, p_list) if q > 0]))
                data_aux_list = [data]
                for p in sorted(clr_list):
                    data_aux = sign * df_aux["awd_qty"].where(df_aux[s] == p, 0).to_frame()
                    data_aux.index.name = 'Hourly / Price'
                    data_aux.columns = [round(p + 0.0049, 2)]
                    data_prev = pd.DataFrame(0.0, index=range(1, self.size + 1), columns=[round(p + 0.0049 + sign * tol_price, 2)])
                    data_prev.index.name = 'Hourly / Price'
                    if s == 'buy':
                        data_aux = pd.concat([data_aux, data_prev, data_end], axis=1)
                    else:
                        data_aux = pd.concat([data, data_prev, data_aux], axis=1)
                    data_aux_list.append(data_aux)
                data_aux_list.append(data_end)
                data_out = self.__merge_xge_bids(data_aux_list, bfill_bool)
                data_bids_list.append(data_out)
        data_out = self.__merge_xge_bids(data_bids_list, False)
        # Make sure that last row is 0
        data_out.iloc[-1, :] = 0.0
        # Path to flow dict
        date_str = self.date.strftime("%Y%m%d")
        pattern = "ETC_bid_" + date_str + ".xlsx"
        file_path = os.path.join(self.folder_path, pattern)
        data_out.to_excel(file_path)
        return data_out, file_path

    def send_xge_bids(self, file_path):
        receiver_email = self.config['MAIL_ETC']['TO']
        receiver_cc = self.config['MAIL_ETC']['CC']
        password = self.config['EMAIL_LOGIN']['PASSWORD']
        login = self.config['EMAIL_LOGIN']['USERNAME']
        address = self.config['EMAIL_LOGIN']['EMAIL']
        subject = "ETC_bid_" + self.date.strftime("%Y%m%d")
        
        html_content = """\
            <html>
                <body>
                    <h1>Dear all,</h1>
                    <p>Please find the conditional bid for HUPX DAM for the day:</p>\n\n
                    """+self.date_string+"""
                    <p>Best regards</p>
                </body>
            </html>
            """
        
        self.send_html_email(
              receiver_email,
              subject, "This is a plain text fallback content.", html_content, attachment_path=file_path,
              recipient_cc=receiver_cc, email_address=address, email_login=login, email_password=password
        )
        self.__log += 'send_xge: Email sent! \n'

    def __parse_xge_results(self):
        # Find xlsx files
        date_str = self.date.strftime("%m.%Y")
        pattern = "price_DAM_IDM_" + date_str + "*.xlsx"
        # Find all matching files
        matching_files = glob.glob(os.path.join(self.folder_path, pattern))
        if not matching_files:
            pattern = "price_DAM_IDM_" + date_str + "*.xls"
            matching_files = glob.glob(os.path.join(self.folder_path, pattern))
            if not matching_files:
                self.__log += f"No file available for xls exchange results: {pattern} , please save manually \n"
                return {}
            err_bool, file_path = self.__convert_xlsx(matching_files[-1], self.mac_numbers_bool)
            if err_bool:
                self.__log += f"No file available for xls exchange results: {pattern} , please save manually \n"
                return {}
        else:
            file_path = matching_files[-1]
        data = pd.read_excel(file_path, sheet_name='Ціна_РДН', skiprows=2)
        data = data.set_index('Числа')
        data.columns = range(1, data.shape[1] + 1)
        # Find tomorrow date
        try:
            price_ser = data.loc[self.date.day, :]
        except KeyError:
            self.__log += f"Date {self.date.day} is not available in xls exchange results file {file_path}, please update table \n"
            return None
        bids_dict = {}
        for s in self.side_list:
            fee = self.fee_dict[s]
            if s == 'buy':
                bid_ser = (price_ser / self.rate * .93 - fee).round(2)
            else:
                bid_ser = (price_ser / self.rate + fee).round(2)
            bid_ser.name = s
            # Convert to HU timezone
            bid_ser.iloc[:-1] = bid_ser.iloc[1:]
            bid_ser.iloc[-1] = 0
            bids_dict[s] = bid_ser
        return bids_dict

    def __merge_xge_bids(self, data_bids_list, bfill_bool):
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
                if bfill_bool:
                    data_aux = data.T.reindex(ts).bfill()
                else:
                    data_aux = data.T.reindex(ts).ffill()
                data_bids += data_aux
        data_bids = data_bids.T.astype(int)
        # Check if volumes are correct
        jao_ser_dict = {k: v['awd_qty'] for k, v in self.jao_xml_dict.items()}
        error_list = self.__check_volumes(data_bids, jao_ser_dict)
        if not error_list:
            pass
        else:
            self.__log += "Errors found in bids file:\n" + "\n".join(error_list)
        return data_bids

    @staticmethod
    def __convert_xlsx(file_path, mac_numbers_bool):
        # Define the file paths (adjust these paths to your actual file locations)
        xls_file = file_path
        xlsx_file = file_path + 'x'

        if mac_numbers_bool:
            # AppleScript to open the .xls file in Numbers and export it as .xlsx using the "Microsoft Excel" format
            applescript = f'''
            tell application "Numbers"
                activate
                open POSIX file "{xls_file}"
                delay 3 -- allow time for the file to open
                tell document 1
                    export to POSIX file "{xlsx_file}" as Microsoft Excel
                    close saving no
                end tell
            end tell
            '''
        else:
            # AppleScript to open the .xls file in Excel and export it as .xlsx using the "Excel XML file format"
            applescript = f'''
            tell application "Microsoft Excel"
                activate
                open POSIX file "{xls_file}"
                delay 3 -- allow time for the file to open
                set wb to active workbook
                save workbook as wb filename "{xlsx_file}" file format Excel XML file format
                close wb saving no
            end tell
            '''
        
        # Run the AppleScript using osascript
        try:
            subprocess.run(["osascript", "-e", applescript], check=True)
            return False, xlsx_file
        except:
            return True, xlsx_file

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
            elif abs(diff - tol_price) < 1e-9:
                if not (df[col1] >= df[col2]).all():
                    errors.append(f"Column {col2} does not have all rows lower than column {col1} (difference = {tol_price}).")
        
        # Return results
        if not errors:
            return []
        else:
            return errors

    @staticmethod
    def send_html_email(recipient, subject, text_content, html_content, attachment_path=None, recipient_cc=[],
                        smtp_server="smtp.gmail.com", smtp_port=587,
                        email_address="your_email@gmail.com",
                        email_login=None, email_password="", ):
        if email_login is None:
            email_login = email_address
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_address
        msg["To"] = recipient
        if not recipient_cc:
            pass
        else:
            msg["Cc"] = recipient_cc
        msg.set_content(text_content)

        msg.add_alternative(html_content, subtype="html")

        if attachment_path:
            with open(attachment_path, "rb") as file:
                msg.add_attachment(file.read(), maintype="application", subtype="octet-stream", filename=attachment_path.split("/")[-1])

        with smtplib.SMTP(smtp_server, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(email_login, email_password)
            smtp.send_message(msg)


def calculate_color(value, min_val, max_val):
    """Generate a color gradient: negative (white → blue), positive (white → red), zero (white)."""
    tol_vol = 1e-8  # small tolerance to avoid divide-by-zero

    if pd.isnull(value):
        return "#FFFFFF"

    max_abs = max(abs(min_val), abs(max_val)) * 1.4
    if max_abs < tol_vol:
        norm_value = 0
    else:
        norm_value = value / max_abs  # normalize to [-1, 1]

    if norm_value < 0:
        # Negative: white → blue
        intensity = int(255 * abs(norm_value))
        red = 255 - intensity
        green = 255 - intensity
        blue = 255
    else:
        # Positive: white → red
        intensity = int(255 * norm_value)
        red = 255
        green = 255 - intensity
        blue = 255 - intensity

    return f"#{red:02X}{green:02X}{blue:02X}"


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


def xge_bids(app_class):
    rate = process_rate()
    if rate is None:
        return 0
    else:
        app_class.rate = rate
    data, _ = app_class.get_xge_bids()
    data = data.reset_index()
    show_dataframe_with_heatmap(data)


def send_xge_bids(app_class):
    rate = process_rate()
    if rate is None:
        return 0
    else:
        app_class.rate = rate
    data, file_path = app_class.get_xge_bids()
    if file_path is None:
        messagebox.showinfo("Logs", str(app_class.log))
    else:
        app.send_xge_bids(file_path)


def load_xge_rate(app_class):
    entry_float.delete(0, tk.END)
    rate = app_class.load_curr_rate()
    entry_float.insert(0, str(rate))


def show_logs(app_class):
    messagebox.showinfo("Logs", str(app_class.log))


# Example function to get and print the float value from the entry
def process_rate():
    try:
        value = entry_float.get().replace(',', '.')
        rate = float(value)
        return rate
    except ValueError:
        messagebox.showinfo("Currency", "Please enter a valid float number for EURUAH.")
        return None


app = UA_APP_LIGHT()

# Create the main window
name = "UA Capa GUI_" + app.date_string
if app.test_bool:
    name += "_TEST"
window = tk.Tk()
window.title(name)
window.geometry("400x200")

# Load the background image
try:
    bg_image = Image.open(default_path + "logo.png")
    bg_image = bg_image.resize((115, 30), Image.LANCZOS)
    bg_photo = ImageTk.PhotoImage(bg_image)
except Exception as e:
    print(f"Error loading image: {e}")
    bg_photo = None

# ---------------------------
# Bottom Frame: Buttons and Canvas using Pack
# ---------------------------
bottom_frame = tk.Frame(window)
bottom_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

# Button Frame on the left inside bottom_frame
button_frame = tk.Frame(bottom_frame, width=250, height=300)
button_frame.pack(side=tk.LEFT, padx=10, pady=10)

button1 = tk.Button(button_frame, text="Show Bids", command=lambda: xge_bids(app))
button1.place(x=10, y=55, width=120, height=30)
button2 = tk.Button(button_frame, text="Send Bids", command=lambda: send_xge_bids(app))
button2.place(x=10, y=105, width=120, height=30)
button3 = tk.Button(button_frame, text="Show Logs", command=lambda: show_logs(app))
button3.place(x=10, y=155, width=120, height=30)

# ---------------------------
# Right Top Corner Frame: Float Input
# ---------------------------
# Create a frame for the float input in the top right corner
input_frame = tk.Frame(window)
input_frame.place(relx=1.0, y=10, anchor='ne')

# Label for float input
label_float = tk.Label(input_frame, text="Enter exchange rate EURUAH:")
label_float.pack(pady=(0, 5))

# Entry widget for float input
entry_float = tk.Entry(input_frame)
entry_float.pack(pady=(0, 5))
load_xge_rate(app)

# Button to trigger float processing
button_float = tk.Button(input_frame, text="Load EURUAH", command=lambda: load_xge_rate(app))
button_float.pack()

# Canvas on the right inside bottom_frame with a smaller size
canvas = Canvas(bottom_frame, width=150, height=200)
canvas.pack(side=tk.RIGHT, padx=0, pady=10)

# Display the background image on the canvas (if available)
if bg_photo:
    # Keep a reference to prevent garbage collection
    canvas.bg_photo = bg_photo
    canvas.create_image(0, 125, image=bg_photo, anchor="nw")

window.mainloop()