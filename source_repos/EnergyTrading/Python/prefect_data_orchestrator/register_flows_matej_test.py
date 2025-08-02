import sys
import os
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
    from flow_gas_fut_price_fetch import gas_fut_price_fetch
    from flow_eua_fut_price_fetch import eua_fut_price_fetch
    from flow_fund_fetch import fund_fetch
    from flow_eod_fut_price_process import EoD_fut_price_process
    from flow_eikon_spot import eikon_spot_fetch
except ModuleNotFoundError as e:
    print(f"❌ ERROR: Missing module: {e}. Ensure all flow files are in the same directory.")
    exit(1)

# Configurations
WORK_POOL_NAME = "conda-develop"
PREFECT_API_URL = "http://127.0.0.1:4200/api"
CONDA_ENV_NAME = "develop_fund_model"

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
        f'start cmd /k "conda activate {CONDA_ENV_NAME} && prefect server start"',
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


async def reset_work_pool():
    """Deletes and recreates the work pool only after clearing flow runs."""
    try:
        # Check if the work pool exists
        result = subprocess.run(["prefect", "work-pool", "ls"], capture_output=True, text=True)

        if result.stdout and WORK_POOL_NAME in result.stdout:
            print(f"🗑️ Deleting work pool: {WORK_POOL_NAME}...")
            subprocess.run(["prefect", "work-pool", "delete", WORK_POOL_NAME], check=True)
        else:
            print(f"✅ Work pool {WORK_POOL_NAME} does not exist, skipping delete...")

    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error deleting work pool: {e}")

    # Recreate the work pool with --overwrite
    print(f"✅ Creating new work pool: {WORK_POOL_NAME}...")
    subprocess.run(["prefect", "work-pool", "create", WORK_POOL_NAME, "--type", "process", "--overwrite"], check=True)

    # Start the work pool in a new terminal window
    print(f"🚀 Starting work pool '{WORK_POOL_NAME}' in a new terminal...")
    subprocess.Popen(
        f'start cmd /k "conda activate {CONDA_ENV_NAME} && set PYTHONPATH={SCRIPT_DIR} && prefect worker start --pool {WORK_POOL_NAME}"',
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

    await reset_work_pool()  # Reset work pool
    await asyncio.sleep(5)  # Allow the work pool to fully start before proceeding
    await delete_existing_deployments()  # Delete all deployments

if __name__ == "__main__":
    os.environ["PREFECT_API_URL"] = "http://127.0.0.1:4200/api"

    # Delete existing deployments before deploying new ones
    asyncio.run(main())
    # Forecast AvCap fetch 
    # Power futures price fetch
    eikon_spot_fetch.deploy(
        name="eikon-spot-fetch",  
        work_pool_name=WORK_POOL_NAME,  
        parameters={"countries": ['it', 'it_nord', 'es', 'hr', 'gr'],
                    'start_date': datetime(2019,1,1),
                    'end_date': (pd.Timestamp.today().normalize() + timedelta(days=1))},
        schedules=[
            DeploymentScheduleCreate(
                schedule=CronSchedule(cron='55 11 * * *', timezone='Europe/Berlin')),
            ],
        entrypoint_type=EntrypointType.MODULE_PATH
    )



    # parser = argparse.ArgumentParser(description="Example script with arguments")
    
    # # Adding arguments
    # parser.add_argument("--run", type=bool, required=True, help="Your name")
    #  # Parse the arguments
    # args = parser.parse_args()

    # if args.run:
    # fut_price_fetch(countries=['at','de', 'fr', 'fr', 'hu','hu',
    #             'cz', 'cz', 'sk', 'sk', 'it', 'it',
    #             'at', 'at', 'nl','nl', 'be', 'be',
    #             'ro', 'ro', 'ro'],
    #                 base_date=datetime(2019,1,1))
    # gas_fut_price_fetch(countries=['ttf']*3,
    #                 base_date=datetime(2019,1,1))
    # eua_fut_price_fetch(countries=['eua']*3,
    #                 base_date=datetime(2019,1,1))
    # fund_fetch(fund_list= ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
    #         grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
    #         hour= '00')
    # fund_fetch(fund_list= ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
    #         grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
    #         hour= '12')
    # fund_fetch(fund_list= ['Temp_mnd', 'Wind_mnd', 'Solar_mnd', 'CON_mnd'],
    #         grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
    #         hour= '00')
    # fund_fetch(fund_list= ['AvailCap'],
    #         grid_list= ['DEU', 'FRA'],
    #         hour= '00')
    # eikon_spot_fetch(countries=['it','it_nord', 'es', 'hr', 'gr'],
    #                     start_date=datetime(2019,1,1),
    #                     end_date=(pd.Timestamp.today().normalize()+timedelta(days=1)))
    # Power futures price fetch
    # eikon_spot_fetch.deploy(
    #     name="eikon-spot-fetch",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool,
    #     parameters={"countries": ['it','it_nord', 'es', 'hr', 'gr'],
    #                 'start_date': datetime(2019,1,1),
    #                 'end_date': (pd.Timestamp.today().normalize()+timedelta(days=1))},
                    
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(13, 15)))};BYMINUTE=01,05,10,15",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )
    
    # # Power futures price fetch
    # fut_price_fetch.deploy(
    #     name="fut-price-fetch",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool,
    #     parameters={"countries": ['at','de', 'fr', 'fr', 'hu','hu',
    #                 'cz', 'cz', 'sk', 'sk', 'it', 'it',
    #                 'at', 'at', 'nl','nl', 'be', 'be',
    #                 'ro', 'ro', 'ro', ],
    #                 'base_date': datetime(2019,1,1)},
                    
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 01 * * *', timezone='Europe/Berlin')),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 04 * * *', timezone='Europe/Berlin')),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 21 * * *', timezone='Europe/Berlin'))
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # TTF futures price fetch
    # gas_fut_price_fetch.deploy(
    #     name="fut-gas-price-fetch",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool,
    #     parameters={"countries": ['ttf', 'ttf', 'ttf'],
    #                 'base_date': datetime(2019,1,1)},
                    
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 01 * * *', timezone='Europe/Berlin')),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 04 * * *', timezone='Europe/Berlin')),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 21 * * *', timezone='Europe/Berlin'))
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # TTF futures price fetch
    # eua_fut_price_fetch.deploy(
    #     name="fut-eua-price-fetch",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool,
    #     parameters={"countries": ['eua'],
    #                 'base_date': datetime(2019,1,1)},
                    
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 01 * * *', timezone='Europe/Berlin'),
    #             active=True
    #         ),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 04 * * *', timezone='Europe/Berlin'),
    #             active=True
    #         ),
    #         DeploymentScheduleCreate(
    #             schedule=CronSchedule(cron='00 21 * * *', timezone='Europe/Berlin'),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # Mid forecast fundamentals fetch EC Ens00
    # fund_fetch.deploy(
    #     name="fund_fetch-mid-00",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "fund_list": ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
    #         "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
    #         "hour": '00'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(6, 22)))};BYMINUTE=0,30",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # Mid forecast percentiles fundamentals fetch EC Ens00
    # fund_fetch.deploy(
    #     name="fund_fetch-mid-perc-00",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "fund_list": [f"ResidualDemand_{a}th" for a in [10,25,75,90]],
    #         "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
    #         "hour": '00'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(6, 22)))};BYMINUTE=0,30",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # Mid forecast fundamentals fetch EC Ens12
    # fund_fetch.deploy(
    #     name="fund_fetch-mid-12",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "fund_list": ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
    #         "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
    #         "hour": '12'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(6, 22)))};BYMINUTE=0,30",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # Monthly forecast fundamentals fetch EC Ens00
    # fund_fetch.deploy(
    #     name="fund_fetch-mnd-00",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "fund_list": ['Temp_mnd', 'Wind_mnd', 'Solar_mnd', 'CON_mnd'],
    #         "grid_list": ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
    #         "hour": '00'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(21, 23)))};BYMINUTE=0,30",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # # Forecast AvCap fetch 
    # fund_fetch.deploy(
    #     name="AvCap-fetch",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "fund_list": ['AvailCap'],
    #         "grid_list": ['DEU', 'FRA'],
    #         "hour": '00'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(6, 13)))};BYMINUTE=30",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )

    # Forecast AvCap fetch 
    # EoD_fut_price_process.deploy(
    #     name="EoD-fut-price-process",  # Name of the deployment
    #     work_pool_name="conda-develop",  # Specify the work pool
    #     parameters={
    #         "base_products": ['M_1', 'M_2', 'M_3', 'M_4', 'M_5',
    #                           'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7', 'Q_8',
    #                           'Y_1', 'Y_2', 'Y_3'],
    #         "market_list": ['de', 'fr', 'at', 'hu', 'cz', 'sk', 'hu', 'ro'],
    #         "delivery_list": ['base', 'peak'],
    #         'file_path' : '//192.168.10.91/data/Data/Data/Futures/data_dict.pkl'
    #     },
    #     schedules=[
    #         DeploymentScheduleCreate(
    #             schedule=RRuleSchedule(
    #                 rrule=f"FREQ=HOURLY;INTERVAL=1;BYHOUR={','.join(map(str, range(0, 2)))};BYMINUTE=37",
    #                 timezone="Europe/Berlin"
    #             ),
    #             active=True
    #         )
    #     ],
    #     entrypoint_type=EntrypointType.MODULE_PATH
    # )
    