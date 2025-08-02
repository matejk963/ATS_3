import sys
import os
import json
from Common.config_load import get_config_path as CONFIG_PATH

with open(CONFIG_PATH(), 'r') as file:
    config = json.load(file)['PrefectPostgres']
prefect_postgres_pass = config['matej']


os.environ["PREFECT_API_DATABASE_CONNECTION_URL"] = f"postgresql+asyncpg://prefect_user:{prefect_postgres_pass}@localhost:5432/prefect"

# Get the current script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Add the correct module path
OUTAGE_FETCH_PATH = os.path.join(PROJECT_ROOT, "Utilities", "entso_data", "AvailCap")
sys.path.insert(0, OUTAGE_FETCH_PATH)

print(f"✅ Added {OUTAGE_FETCH_PATH} to sys.path for module lookup.")

import subprocess
import asyncio
import psutil
import socket
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import RRuleSchedule, CronSchedule
from prefect.types.entrypoint import EntrypointType
from datetime import timedelta, datetime
import pandas as pd



# Ensure the script directory is in Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

print(f"📂 Added {SCRIPT_DIR} to sys.path for module lookup.")

# Import Prefect flows
try:
    from flow_fut_price_fetch import fut_price_fetch
    from flow_projected_settle_fetch import ps_db_fill
    from flow_fund_fetch import fund_fetch
    from flow_eikon_spot import eikon_spot_fetch
    from flow_av_inst_cap_fetch import entsoe_inst_cap_flow
    from flow_ensto_av_cap_fetch import entsoe_av_cap_flow
    from flow_model_fut_data import update_all_futures_flow
    from flow_fund_model_run import fund_model_run
    from prefect_data_orchestrator.flow_spot_daily import spot_daily
    from prefect_data_orchestrator.flow_cot import commitments_of_traders
except ModuleNotFoundError as e:
    print(f"❌ ERROR: Missing module: {e}. Ensure all flow files are in the same directory.")
    exit(1)

# Configurations
WORK_POOL_MATEJ = "conda-develop_matej"
WORK_POOL_FUND = "conda-develop_fund_model"
WORK_POOL_DEFAULT = "conda-develop"
CONDA_ENV_MATEJ = "develop_matej"
CONDA_ENV_FUND = "develop_fund_model"
CONDA_ENV_DEFAULT = "develop"
PREFECT_API_URL = "http://127.0.0.1:4200/api"

# Ensure Prefect API URL is set
os.environ["PREFECT_API_URL"] = PREFECT_API_URL


def is_port_in_use(port):
    """Check if a given port is currently in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def stop_prefect_server():
    """Check if Prefect server is running, terminate it, and ensure the port is free."""
    print("🔍 Checking if Prefect server is running on port 4200...")

    try:
        # Check if Prefect server process is running
        result = subprocess.run(["prefect", "server", "status"], capture_output=True, text=True)

        if "UP" in result.stdout or is_port_in_use(4200):
            print("🛑 Prefect server is running. Stopping it now...")

            # Find and terminate Prefect server process
            for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and "prefect server start" in " ".join(proc.info['cmdline']):
                        print(f"🛑 Killing Prefect server process {proc.info['pid']}...")
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # Check if the port is still in use
            if is_port_in_use(4200):
                print("⚠️ Port 4200 is still occupied! Forcing shutdown...")
                os.system("taskkill /F /IM prefect.exe")  # Force kill Prefect if needed

            print("✅ Prefect server stopped successfully.")

        else:
            print("✅ Prefect server is not running.")

    except Exception as e:
        print(f"⚠️ Error checking Prefect server: {e}")


def start_prefect_server():
    """Start Prefect server in a new command prompt after ensuring the old one is gone."""
    if is_port_in_use(4200):
        print("❌ ERROR: Port 4200 is still in use. Server will not start.")
        return

    print("🚀 Starting a new Prefect server instance...")
    subprocess.Popen(
        f'start cmd /k "conda activate {CONDA_ENV_MATEJ} && prefect server start"',
        shell=True
    )



async def stop_all_workers():
    """Stops any running Prefect workers by forcefully killing their processes."""
    print(f"🔹 Stopping any running Prefect workers...")
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and "prefect worker start" in " ".join(proc.info['cmdline']):
                print(f"🛑 Killing Prefect worker process {proc.info['pid']}...")
                proc.terminate()
                proc.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    print("✅ All workers stopped.")


async def reset_work_pools():
    """Deletes and recreates three work pools for the three environments."""
    # Reset work pool for 'develop_matej'
    try:
        result = subprocess.run(["prefect", "work-pool", "ls"], capture_output=True, text=True)
        if result.stdout and WORK_POOL_MATEJ in result.stdout:
            print(f"🗑️ Deleting work pool: {WORK_POOL_MATEJ}...")
            subprocess.run(["prefect", "work-pool", "delete", WORK_POOL_MATEJ], check=True)
        else:
            print(f"✅ Work pool {WORK_POOL_MATEJ} does not exist, skipping delete...")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error deleting work pool {WORK_POOL_MATEJ}: {e}")

    print(f"✅ Creating new work pool: {WORK_POOL_MATEJ}...")
    subprocess.run(["prefect", "work-pool", "create", WORK_POOL_MATEJ, "--type", "process", "--overwrite"], check=True)

    # Reset work pool for 'develop_fund_model'
    try:
        result = subprocess.run(["prefect", "work-pool", "ls"], capture_output=True, text=True)
        if result.stdout and WORK_POOL_FUND in result.stdout:
            print(f"🗑️ Deleting work pool: {WORK_POOL_FUND}...")
            subprocess.run(["prefect", "work-pool", "delete", WORK_POOL_FUND], check=True)
        else:
            print(f"✅ Work pool {WORK_POOL_FUND} does not exist, skipping delete...")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error deleting work pool {WORK_POOL_FUND}: {e}")

    print(f"✅ Creating new work pool: {WORK_POOL_FUND}...")
    subprocess.run(["prefect", "work-pool", "create", WORK_POOL_FUND, "--type", "process", "--overwrite"], check=True)

    # Reset work pool for 'conda-develop' (default)
    try:
        result = subprocess.run(["prefect", "work-pool", "ls"], capture_output=True, text=True)
        if result.stdout and WORK_POOL_DEFAULT in result.stdout:
            print(f"🗑️ Deleting work pool: {WORK_POOL_DEFAULT}...")
            subprocess.run(["prefect", "work-pool", "delete", WORK_POOL_DEFAULT], check=True)
        else:
            print(f"✅ Work pool {WORK_POOL_DEFAULT} does not exist, skipping delete...")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error deleting work pool {WORK_POOL_DEFAULT}: {e}")

    print(f"✅ Creating new work pool: {WORK_POOL_DEFAULT}...")
    subprocess.run(["prefect", "work-pool", "create", WORK_POOL_DEFAULT, "--type", "process", "--overwrite"], check=True)

    # Start worker for the matej environment
    print(f"🚀 Starting work pool '{WORK_POOL_MATEJ}' in a new terminal...")
    subprocess.Popen(
        f'start cmd /k "conda activate {CONDA_ENV_MATEJ} && set PYTHONPATH={SCRIPT_DIR} && prefect worker start --pool {WORK_POOL_MATEJ}"',
        shell=True
    )

    # Start worker for the fund model environment
    print(f"🚀 Starting work pool '{WORK_POOL_FUND}' in a new terminal...")
    subprocess.Popen(
        f'start cmd /k "conda activate {CONDA_ENV_FUND} && set PYTHONPATH={SCRIPT_DIR} && prefect worker start --pool {WORK_POOL_FUND}"',
        shell=True
    )

    # Start worker for the default environment
    print(f"🚀 Starting work pool '{WORK_POOL_DEFAULT}' in a new terminal...")
    subprocess.Popen(
        f'start cmd /k "conda activate {CONDA_ENV_DEFAULT} && set PYTHONPATH={SCRIPT_DIR} && prefect worker start --pool {WORK_POOL_DEFAULT}"',
        shell=True
    )



async def delete_existing_deployments():
    """Deletes all deployments to ensure only new ones are used."""
    print("🗑️ Deleting all existing deployments...")
    async with PrefectClient(api=PREFECT_API_URL) as client:
        existing_deployments = await client.read_deployments()
        for dep in existing_deployments:
            print(f"🗑️ Removing deployment: {dep.name}")
            await client.delete_deployment(dep.id)

    print("✅ All deployments deleted. Ready to create fresh deployments.")


async def main():
    await stop_prefect_server()  # Ensure Prefect server is shut down first
    await stop_all_workers()  # Ensure all workers are shut down
    await asyncio.sleep(3)  # Allow processes to terminate

    start_prefect_server()  # Start Prefect server in a new terminal
    await asyncio.sleep(10)  # Wait for server to fully start before proceeding

    await reset_work_pools()  # Reset work pool
    await asyncio.sleep(5)  # Allow the work pool to fully start before proceeding
    await delete_existing_deployments()  # Delete all deployments

if __name__ == "__main__":
    os.environ["PREFECT_API_URL"] = "http://127.0.0.1:4200/api"

    # Delete existing deployments before deploying new ones
    asyncio.run(main())

    # Deployment for updating futures data for model calculation
    update_all_futures_flow.deploy(
        name="model-fuels-update",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={},  # No specific parameters needed
        schedules=[
            DeploymentScheduleCreate(
                schedule=CronSchedule(cron='5 0 * * *', timezone='Europe/Berlin')  # Runs daily at 00:05 AM
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH  # Ensures module-style execution
    )
    
    # Fut price update
    fut_price_fetch.deploy(
        name="fut-price-fetch",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool,
        parameters={"countries": ['de', 'fr', 'at', 'nl', 'be',
                                'it', 'hu', 'ro', 'es', 'cz', 'sk','ttf', 'eua']
                        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(1,2)))};BYMINUTE=7,37",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Fut price update
    ps_db_fill.deploy(
        name="ps-db-fill",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool,
        parameters={"countries": ['de', 'fr', 'at', 'nl', 'be',
                                'it', 'hu', 'ro', 'es', 'cz', 'sk','ttf'],
                    'base_start_date': datetime(2019,1,1)  # Start date for the data
                        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(1,2)))};BYMINUTE=0,30",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )
    
    # Inst_cap_fetch
    entsoe_av_cap_flow.deploy(
        name="entso-av-cap-fetch",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool,
        parameters={"selected_grids": ["10YHU-MAVIR----U", "10YRO-TEL------P"]
                        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(6, 22)))};BYMINUTE=0",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )
    
    # Inst_cap_fetch
    entsoe_inst_cap_flow.deploy(
        name="entso-inst-cap-fetch",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool,
        parameters={"grid_mapping": {
                            "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
                            "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
                            "10YCZ-CEPS-----N": {'column_suffix': '_cz', 'table_name': 'CZE'},
                            "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
                            "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"},
                            "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
                            "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},
                            "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
                            }
                        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=CronSchedule(cron='0 15 * * 6,7', timezone='Europe/Berlin'))
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )


    # parser = argparse.ArgumentParser(description="Example script with arguments")
    eikon_spot_fetch.deploy(
        name="eikon-spot-fetch",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool,
        parameters={"countries": ['it','it_nord', 'es', 'hr', 'gr'],
                    'start_date': datetime(2019,1,1)},
                    
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(13, 18)))};BYMINUTE=01,05,10,15,30,45",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Mid forecast fundamentals fetch EC Ens00
    fund_fetch.deploy(
        name="fund_fetch-mid-00",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            "hour": '00'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(5, 10)))};BYMINUTE=0,30",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Mid forecast percentiles fundamentals fetch EC Ens00
    fund_fetch.deploy(
        name="fund_fetch-mid-perc-00",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": [f"ResidualDemand_{a}th" for a in [10,25,75,90]],
            "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
            "hour": '00'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(5, 10)))};BYMINUTE=10,40",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Mid forecast percentiles fundamentals fetch EC Ens00
    fund_fetch.deploy(
        name="fund_fetch-mid-perc-12",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": [f"ResidualDemand_{a}th" for a in [10,25,75,90]],
            "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
            "hour": '12'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(5, 10)))};BYMINUTE=20,50",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Mid forecast fundamentals fetch EC Ens12
    fund_fetch.deploy(
        name="fund_fetch-mid-12",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            "hour": '12'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(14,22)))};BYMINUTE=30",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Monthly forecast fundamentals fetch EC Ens00
    fund_fetch.deploy(
        name="fund_fetch-mnd-00",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": ['Temp_mnd', 'Wind_mnd', 'Solar_mnd', 'CON_mnd'],
            "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            "hour": '00'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(21, 23)))};BYMINUTE=0,30",
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Forecast AvCap fetch 
    fund_fetch.deploy(
        name="AvCap-fetch",  # Name of the deployment
        work_pool_name=WORK_POOL_MATEJ,  # Specify the work pool
        parameters={
            "fund_list": ['AvailCap'],
            "grid_list": ['DEU', 'FRA'],
            "hour": '00'
        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=RRuleSchedule(
                    rrule=(
                        f"FREQ=HOURLY;INTERVAL=1;"
                        f"BYHOUR={','.join(map(str, list(range(6, 13)) + list(range(22, 24))))};"
                        f"BYMINUTE=30"
                    ),
                    timezone="Europe/Berlin"
                ),
                active=True
            )
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Fair value manager/fund model run
    fund_model_run.deploy(
        name="fund-model-run",  # Name of the deployment
        work_pool_name=WORK_POOL_FUND,  # Specify the work pool,
        parameters={"base_products": ['M_1', 'M_2', 'M_3', 'M_4', 'M_5', 'M_6',
                                    'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7', 'Q_8',
                                    'Y_1', 'Y_2'],
                    "market_list": ['de', 'fr', 'at', 'cz', 'nl', 'hu'],
                    "delivery_list": ['base', 'peak']
                        },
        schedules=[
            DeploymentScheduleCreate(
                schedule=CronSchedule(cron='30 1 * * 1-5', timezone='Europe/Berlin'))
        ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )

    # Daily spot
    try:
        spot_daily.deploy(
            name="spot-daily-all",  # Name of the deployment
            work_pool_name="conda-develop",  # Specify the work pool
            parameters={"countries": ['at', 'be', 'cz', 'de', 'dkw', 'dke',
                                    'fr', 'hu', 'nl', 'sk', 'si', 'ro',
                                        'bg', 'hr', 'gr', 'es', 'it_nord'],
                        'test': False},
            schedules=[
                DeploymentScheduleCreate(
                    schedule=CronSchedule(cron='15 13 * * *', timezone='Europe/Berlin')),
                DeploymentScheduleCreate(
                    schedule=CronSchedule(cron='50 15 * * *', timezone='Europe/Berlin')),
                DeploymentScheduleCreate(
                    schedule=CronSchedule(cron='05 18 * * *', timezone='Europe/Berlin'))
            ],
            entrypoint_type=EntrypointType.MODULE_PATH
        )
        print("✅ spot-daily-all deployment successful!")
    except Exception as e:
        print(f"❌ ERROR deploying spot-daily-all: {e}")

    # Commitments of traders update every tuesday at 8:25
    try:
        commitments_of_traders.deploy(
            name="cot-update",  # Name of the deployment
            work_pool_name="conda-develop",  # Specify the work pool
            schedules=[
                DeploymentScheduleCreate(
                    schedule=CronSchedule(cron='25 8 * * 2', timezone='Europe/Berlin'))
            ],
            entrypoint_type=EntrypointType.MODULE_PATH
        )
        print("✅ cot-update deployment successful!")
    except Exception as e:
        print(f"❌ ERROR deploying cot-update: {e}")



