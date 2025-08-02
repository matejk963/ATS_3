import sys, os
import traceback
import json
import gc
from contextlib import contextmanager
from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
from prefect.task_runners import ConcurrentTaskRunner

from Database.DB_writer import db_writer
from Database.DB_reader import Database
from Utilities.email_sending import send_plain_email, send_html_email
from Spot.geo_map import process

EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
if EMAIL_PASSWORD is None:
    raise ValueError("EMAIL_PASSWORD environment variable not set")

local_db_config_path = '//192.168.10.91/data/EnergyTrading/configSpot.json'
local_db_config_path_test = '//192.168.10.91/data/EnergyTrading/configSpot_test.json'

def load_config(test_bool):
    path = local_db_config_path_test if test_bool else local_db_config_path
    with open(path, 'r') as file:
        config_dict = json.load(file)
    return config_dict['MAIL']['TO'], config_dict['MAIL']['CC'], config_dict['MKT_DICT']

@contextmanager
def managed_database_connection():
    """Context manager for database connections with proper cleanup"""
    db_w = None
    try:
        db_w = db_writer()
        yield db_w
    finally:
        if db_w and hasattr(db_w, 'engine') and db_w.engine:
            db_w.engine.dispose()
        gc.collect()

@task(
    log_prints=True, 
    retries=2, 
    retry_delay_seconds=10,
    timeout_seconds=300  # 5 minute timeout per country
)
def merge(db, schema, table):
    logger = get_run_logger()
    try:
        rows = db.merge_from_staging_to_prod_enum(schema, table)
        logger.info(f"merge func rows {rows}")
        return rows
    except Exception as e:
        logger.error(f"Error in merge for {table}: {e}")
        raise

@task(
    task_run_name="scrape_country_{country}",
    log_prints=True, 
    retries=2, 
    retry_delay_seconds=10,
    timeout_seconds=180  # 3 minute timeout per country
)
def scrape_country(country):
    logger = get_run_logger()
    try:
        with managed_database_connection() as db_w:
            result = db_w.spot_write(country)
            logger.info(f"Scrape result for {country}: {result}")
            return result
    except Exception as e:
        logger.error(f"Error scraping {country}: {e}")
        return -2
    finally:
        # Force garbage collection after each country
        gc.collect()

@task(
    log_prints=True, 
    retries=1, 
    retry_delay_seconds=30,
    timeout_seconds=120  # 2 minute timeout for image generation
)
def send_geo_image(test):
    RECIPIENT, CC, mkt_dict = load_config(test)
    logger = get_run_logger()
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        
        # Always use the correct UNC path for base_path
        base_path = r"\\192.168.10.91\data\Data"
        sD = process(mkt_dict, base_path)
        
        file_path = r'\\192.168.10.91\data\Data\Spot\Map\spot_map.png'
        
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
        logger.info("Successfully sent geo image email")
        
    except Exception as err:
        logger.error(f"Error in send_geo_image: {err}")
        try:
            send_plain_email(
                CC, 
                "FAIL: Spot image", f'{err}',
                email_password=EMAIL_PASSWORD
            )
        except Exception as email_err:
            logger.error(f"Failed to send error email: {email_err}")
    finally:
        # Clean up matplotlib resources
        import matplotlib.pyplot as plt
        plt.close('all')
        gc.collect()

@flow(
    log_prints=True, 
    retries=1, 
    retry_delay_seconds=300,
    timeout_seconds=3600,  # 1 hour total timeout
    task_runner=ConcurrentTaskRunner(max_workers=1)  # Process countries sequentially to reduce load
)
def spot_daily_improved(countries, test):
    logger = get_run_logger()
    logger.info(f"Starting spot_daily_improved for {len(countries)} countries")
    
    # Create a single database reader instance
    db_r = Database()
    result = {c: "No data" for c in countries}
    
    # Process countries in smaller batches to reduce memory pressure
    batch_size = 5
    for i in range(0, len(countries), batch_size):
        batch = countries[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}: {batch}")
        
        for country in batch:
            try:
                status = scrape_country(country)
                
                if status == -1:
                    merge(db_r, 'spot', country)
                    result[country] = "Spot prices contains NULL value(s)."
                elif status == -2:
                    result[country] = "Error during data extraction."
                elif status == 1:
                    merge(db_r, 'spot', country)
                    result[country] = "Success"
                elif status == 2:
                    result[country] = 'No info'
                else:
                    result[country] = f"Unknown status: {status}"
                    
            except Exception as e:
                logger.error(f"Error processing {country}: {e}")
                result[country] = f"Error: {str(e)[:100]}"
        
        # Force garbage collection between batches
        gc.collect()
        logger.info(f"Completed batch {i//batch_size + 1}")
    
    # Generate markdown report
    markdown_report = """
| Country        | Status |
|:--------------|-------:|
"""
    for key, value in result.items():
        markdown_report += f"| {key} | {value} |\n"

    # Send geo image (this is the most resource-intensive part)
    try:
        send_geo_image(test)
    except Exception as e:
        logger.error(f"Failed to send geo image: {e}")
        result["geo_image"] = f"Failed: {str(e)[:100]}"

    # Create artifact
    create_markdown_artifact(
        key="spot-report-improved",
        markdown=markdown_report,
        description="Improved spot result report with resource management",
    )
    
    # Final cleanup
    if hasattr(db_r, 'engine') and db_r.engine:
        db_r.engine.dispose()
    gc.collect()
    
    logger.info("Completed spot_daily_improved flow")
    return result

if __name__ == '__main__':
    # Test with a smaller subset
    test_countries = ['at', 'be', 'cz', 'de', 'dkw', 'dke',
                             'fr', 'hu', 'nl', 'sk', 'si', 'ro',
                             'bg', 'hr', 'gr', 'es', 'it']
    result = spot_daily_improved(test_countries, test=True)
    print(f"Test result: {result}")
