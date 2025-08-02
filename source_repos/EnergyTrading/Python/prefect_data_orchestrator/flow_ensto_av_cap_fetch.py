from prefect import flow, task
import logging

import os
import sys

# Get the directory of the script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the directory of Utilities to sys.path
sys.path.append(os.path.join(current_dir, '..', 'Utilities', 'EntsoData', 'AvailCap'))


# Assuming EntsoeOutagesMaster is already imported
from Utilities.entso_data.AvailCap.entso_avail_cap_manager import EntsoeOutagesMaster  

from prefect import get_run_logger

@task(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def initialize_parameters():
    """Initializes configuration parameters."""
    logger = get_run_logger()
    logger.info("Initializing configuration parameters...")  # Use Prefect logging

    base_inst_cap_dir = '//192.168.10.91/d/data/Data/Spot/Entso/InstCap'
    outage_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages'
    output_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/Curves'

    api_token = "0e829f02-4563-482b-8a57-802b1e685c67"

    grid_mapping = {
        "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
        "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
        "10YCZ-CEPS-----N": {'column_suffix': '_cz', 'table_name': 'CZE'},
        "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
        "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
        "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},
        "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
    }

    config = {
        "base_inst_cap_dir": base_inst_cap_dir,
        "outage_dir": outage_dir,
        "output_dir": output_dir,
        "api_token": api_token,
        "grid_mapping": grid_mapping
    }

    logger.info("Configuration initialized successfully.")
    return config



@task(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def process_grid(grid, config):
    """Runs EntsoeOutagesMaster for a given grid."""
    logger = get_run_logger()
    logger.info(f"🔄 Starting processing for grid: {grid}")

    try:
        master = EntsoeOutagesMaster(
            config["base_inst_cap_dir"],
            config["outage_dir"],
            config["output_dir"],
            grid,
            config["grid_mapping"],
            config["api_token"]
        )

        logger.info(f"🔍 Calling EntsoeOutagesMaster.run() for {grid}...")
        master.run()  # <-- If this runs too fast, check its implementation.
        logger.info(f"✅ Completed processing for grid: {grid}")

    except Exception as e:
        logger.error(f"❌ Error processing grid {grid}: {e}")
        raise  # Ensures Prefect retries




from prefect import flow, task, get_run_logger

@flow(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def entsoe_av_cap_flow(selected_grids: list = None):
    """Prefect flow to process specified grids."""
    logger = get_run_logger()
    logger.info("🚀 Starting ENTOS-E Outages Flow...")

    config = initialize_parameters()

    # If no grids are specified, process all available ones
    available_grids = config["grid_mapping"].keys()
    grids_to_process = selected_grids if selected_grids else available_grids

    grid_tasks = []  # Store task futures to ensure they execute fully
    for grid in grids_to_process:
        if grid in available_grids:
            future = process_grid.submit(grid, config, wait_for=[config])
            grid_tasks.append(future)
        else:
            logger.warning(f"⚠️ Grid {grid} is not in the predefined mapping, skipping.")

    # 🔥 Ensure all tasks complete before finishing the flow
    for future in grid_tasks:
        future.result()  # 🔑 This prevents garbage collection issues

    logger.info("✅ Processing completed.")




if __name__ == "__main__":
    # Example: Run for specific grids
    selected_grids = ["10YHU-MAVIR----U"]  # Customize here
    entsoe_av_cap_flow(selected_grids)
