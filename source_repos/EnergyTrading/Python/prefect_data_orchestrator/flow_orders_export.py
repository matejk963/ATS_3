import sys,os
import traceback
import json
from datetime import datetime, timedelta
import pandas as pd
import os
import glob
import re
from prefect import task, flow, get_run_logger

from Utilities.email_sending import send_plain_email, send_html_email
from OrderBook.test.export_data_daily_update import process

EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD') # the password needs to be set as EMAIL_PASSWORD in system variables of the computer where the process is running, it is located in S:/Algo/email_password.txt
if EMAIL_PASSWORD is None:
    raise ValueError("EMAIL_PASSWORD system variable not set")

RECIPIENT = "algotrading@energytrading.sk" # can also be a list of recipients

@task(log_prints=True)
def process_wrapper():
    return process()

@task(log_prints=True)
def first_day_of_next_or_next_next_month():
    today = datetime.today()
    
    # Get the current year and month
    current_year = today.year
    current_month = today.month
    
    # Calculate the first day of the next month
    if current_month == 12:
        first_day_next_month = datetime(current_year + 1, 1, 1)
    else:
        first_day_next_month = datetime(current_year, current_month + 1, 1)
    
    # Calculate the last day of the current month
    if current_month == 12:
        last_day_current_month = datetime(current_year, 12, 31)
    else:
        last_day_current_month = datetime(current_year, current_month + 1, 1) - timedelta(days=1)
    
    # Get the last two business days of the current month
    business_days = pd.date_range(start=today.replace(day=1), end=last_day_current_month, freq='B')
    last_business_day = business_days[-1]
    second_last_business_day = business_days[-2]
    
    # Check if today is within the last two business days of the current month
    if today >= last_business_day and today <= last_business_day:
        # Calculate the first day of the next-next month
        if current_month == 11:
            first_day_next_next_month = datetime(current_year + 1, 1, 1)
        elif current_month == 12:
            first_day_next_next_month = datetime(current_year + 1, 2, 1)
        else:
            first_day_next_next_month = datetime(current_year, current_month + 2, 1)
        return first_day_next_next_month.strftime('%Y%m%d')[2:]
    else:
        return first_day_next_month.strftime('%Y%m%d')[2:]
    
    print("First day of next month:", first_day_of_next_or_next_next_month())



def find_latest_file(folder, pattern):
    # Construct the search pattern
    search_pattern = os.path.join(folder, pattern)
    
    # Find all files matching the pattern
    files = glob.glob(search_pattern)
    
    if not files:
        print("No files found matching the pattern.")
        return None
    
    # Get the latest file based on modification time
    latest_file = max(files, key=os.path.getmtime)
    
    return latest_file


def convert_to_html_content(input_string):
    # Split the input string by the newline character
    lines = input_string.split('\n')
    # Wrap each line in a <p> tag
    html_lines = [f"<p>{line}</p>" for line in lines]
    # Join the lines into a single HTML string
    html_content = '\n'.join(html_lines)    
    return html_content

def convert_dataframe_to_html_content(df):
    # Convert the DataFrame to an HTML table
    html_content = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">\n'

    # Add the header row
    name = 'Order Book'
    html_content += '  <tr>\n'
    html_content += f'    <th>{name}</th>\n'
    for column in df.columns:
        html_content += f'    <th>{column}</th>\n'
    html_content += '  </tr>\n'

    # Add the data rows
    for idx, row in df.iterrows():
        html_content += '  <tr>\n'
        html_content += f'    <td>{idx}</td>\n'  # Add the index as the first column
        for item in row:
            html_content += f'    <td>{item}</td>\n'
        html_content += '  </tr>\n'

    # Close the HTML table
    html_content += '</table>'

    return html_content

@flow(retries=3, retry_delay_seconds=600, log_prints=True)
def orders_export():
    try:
        err_dict=process_wrapper()
            
        # Example usage
        folder_path = '//192.168.10.91/data/Data/orderbooks/base/m/figures'
        str_to_search='de_m_'+first_day_of_next_or_next_next_month()
        file_pattern = f'{str_to_search}*'
        latest_file = find_latest_file(folder_path, file_pattern)
        
        str_lst=[str(x) for x in err_dict]
        string_html = convert_to_html_content('\n'.join(str_lst))
        
        pattern = r"<p>\((.*?)\)</p>"
        matches = re.findall(pattern, string_html)
        data_list = [eval(f"({match})") for match in matches]

        # Convert to a DataFrame
        df = pd.DataFrame([d[1] for d in data_list], index=[d[0] for d in data_list])

        #email sending in case of success, also sending number of records uploaded
        html_content = """\
        <html>
            <body>
                <h1>Hello from Algosrv</h1>
                <p>The daily run of the orderbook job was successful. Please see the attached file for manual check.</p>\n\n
                <p>The err_dicts look as follows.</p>\n
                """+convert_dataframe_to_html_content(df)+ """
            </body>
        </html>
        """

        send_html_email(
            RECIPIENT, 
            "SUCCESS: Daily orderbook job", "This is a plain text fallback content.", html_content, attachment_path=latest_file,
                email_password=EMAIL_PASSWORD

        )


    except Exception as err:
        send_plain_email(
            RECIPIENT, 
            "FAIL: Daily orderbook job", f'{err}',
            email_password=EMAIL_PASSWORD
        )