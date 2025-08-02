import sys,os
import traceback
import json
from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact

from Database.DB_writer import db_writer
from Database.DB_reader import Database
from Utilities.email_sending import send_plain_email, send_html_email
from Spot.geo_map import process


EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD') # the password needs to be set as EMAIL_PASSWORD in system variables of the computer where the process is running, it is located in S:/Algo/email_password.txt
if EMAIL_PASSWORD is None:
    raise ValueError("EMAIL_PASSWORD environment variable not set")

local_db_config_path = '//192.168.10.91/data/EnergyTrading/configSpot.json'
local_db_config_path_test = '//192.168.10.91/data/EnergyTrading/configSpot_test.json'

def load_config(test_bool):
    path = local_db_config_path_test if test_bool else local_db_config_path
    with open(path, 'r') as file:
        config_dict = json.load(file)
    return config_dict['MAIL']['TO'], config_dict['MAIL']['CC'], config_dict['MKT_DICT']


@task(log_prints=True, retries=3, retry_delay_seconds=5)
def merge(db, schema, table):
    logger = get_run_logger()
    rows = db.merge_from_staging_to_prod_enum(schema, table)
    logger.info(f"merge func rows {rows}")

@task(task_run_name="scrape_country_{country}",
    log_prints=True, retries=3, retry_delay_seconds=5)
def scrape_country(country):
    db_w = db_writer()
    return db_w.spot_write(country)

@task(log_prints=True)
def send_geo_image(test):
    RECIPIENT, CC, mkt_dict = load_config(test)
    try:
        # Always use the correct UNC path for base_path
        base_path = r"\\192.168.10.91\data\Data"
        sD = process(mkt_dict, base_path)
        # Example usage
        file_path = r'\\192.168.10.91\data\Data\Spot\Map\spot_map.png'
        # email sending in case of success, also sending number of records uploaded
        html_content = """\
        <html>
            <body>
                <h1>Hello from Algosrv</h1>
                <p>The daily run of the spot job was successful. Please see the attached map with baseload prices.</p>\n\n
            </body>
        </html>
        """
        subject = f"Daily spot job for date: {sD.strftime('%a, %Y/%m/%d')}"
        send_html_email(
            RECIPIENT, 
            subject, "This is a plain text fallback content.", html_content, attachment_path=file_path,
            email_password=EMAIL_PASSWORD
        )
    except Exception as err:
        send_plain_email(
            CC, 
            "FAIL: Spot image", f'{err}',
            email_password=EMAIL_PASSWORD
        )

@flow(log_prints=True, retries=3, retry_delay_seconds=600)
def spot_daily(countries, test):
    logger = get_run_logger()
    db_r = Database()

    result = {c: "No data" for c in countries}

    for country in countries:
        try:
            status = scrape_country(country)
            if status == -1:
                merge(db_r, 'spot', country)
                result[country] =  "Spot prices contains NULL value(s)."
                continue
            elif status == -2:
                result[country] = "Error during data extraction."
                continue
            elif status == 1:
                merge(db_r, 'spot', country)
                result[country] = "Success"
            elif status == 2:
                result[country] = 'No info'

        # Format dictionary items for HTML content
        except Exception as e:
            logger.error(e)

    markdown_report = f"""
| Country        | status |
|:--------------|-------:|
"""

    for key, value in result.items():
        markdown_report += f"| {key} | {value} |\n"

    send_geo_image(test)

    create_markdown_artifact(
        key="spot-report",
        markdown=markdown_report,
        description="Spot result report",
    )