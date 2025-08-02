import datetime
import os.path
import unittest
import csv

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (create_strategy_config_message,
                                                       create_per_products_limit_message,
                                                       create_synthetic_order_message)
from .mm_strategy.constants import (BROKER_ID, BROKER_ID_2, GAS_YEARS, GAS_YR22_ITEM_ID, TTF_ICE, TTF_PRODUCT_ID,
                                   POWER_YEARS, POWER_2023_ITEM_ID, ITALY_BASELOAD, ITALY_PRODUCT_ID,
                                   DE_EEX, M1_PRODUCT_ID, M2_PRODUCT_ID, POWER_MONTHS)
# from mm_strategy.constants import (BROKER_ID, DE_EEX, M1_PRODUCT_ID, M2_PRODUCT_ID, M1M2_PRODUCT_ID,
#                                    POWER_MONTHS)


PACKAGE_NAME = "mm_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
# INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
#                               "assets", "init_files_2023-12-31-1.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
STRATEGY_ID = "synthetic_order_arbitrage"

file_path_ba = r'Z:\Data\Spot\Model\Inputs\de_w1_w2_20240801_ba.csv'
file_path_tr = r'Z:\Data\Spot\Model\Inputs\de_w1_w2_20240801_tr.csv'

def create_add_order(
        timestamp,
        broker_id,
        instrument_id,
        item_id,
        term_format_id,
        sequence_id,
        direction,
        order_id,
        price,
        quantity,
):
    return {"timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": [
                {"counter_party_ok": False, "system_rank": "487290945", "broker_id": broker_id, "txt": False,
                 "user_id": "0", "old_engine_id": "1", "state": "ACTI",
                 "inst_specifier": [
                     {"instrument_id": instrument_id, "first_item_id": item_id, "term_format_id": term_format_id,
                      "second_item_id": "0", "sequence_span": "Single", "first_sequence_id": sequence_id}],
                 "type": "O", "old_broker_id": broker_id, "direction": direction, "initial_order_id": order_id,
                 "engine_id": "1", "order_id": order_id, "timestamp": timestamp, "price": price,
                 "validity_date": None, "terms": [], "validity_restriction": "NON", "account": "0",
                 "is_tradable": True, "execution_restriction": "NON", "implied": False, "action": "ADD",
                 "traded": False, "quantity": quantity}]
            }
def create_feed2():
    feed = []
    counter = 1 # Initial counter for order_id
    QUANTITY = 10 # Example quantity, adjust as needed

    # Constants for the order creation
    broker_id = BROKER_ID
    instrument_id = POWER_YEARS
    instrument_id = POWER_YEARS
    item_id = POWER_2023_ITEM_ID

    # Open the CSV file and read the data
    with open(file_path_ba, 'r') as file:
        csv_reader = csv.DictReader(file)

        for row in csv_reader:
            # timestamp = row['timestamp']
            timestamp = datetime.datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S').timestamp()
            bid_price = round(float(row['bid']),2)
            ask_price = round(float(row['ask']),2)

            # Create the buy order (using bid price)
            buy_order = create_add_order(
                timestamp=timestamp,
                broker_id=broker_id,
                instrument_id=ITALY_BASELOAD,
                item_id=POWER_2023_ITEM_ID,
                term_format_id=None,  # Adjust if needed
                sequence_id=POWER_YEARS,  # Adjust if needed
                direction=COMMON.Direction.buy,
                order_id=str(counter).zfill(8),  # Creates a zero-padded order_id
                price=bid_price,
                quantity=QUANTITY
            )

            # Append the buy order to the feed list
            feed.append(buy_order)

            # Increment the counter for the next order_id
            counter += 10

            # Create the sell order (using ask price)
            sell_order = create_add_order(
                timestamp=timestamp,
                broker_id=broker_id,
                instrument_id=ITALY_BASELOAD,
                item_id=POWER_2023_ITEM_ID,
                term_format_id=None,  # Adjust if needed
                sequence_id=POWER_YEARS,  # Adjust if needed
                direction=COMMON.Direction.sell,
                order_id=str(counter).zfill(8),  # Creates a zero-padded order_id
                price=ask_price,
                quantity=QUANTITY
            )

            # Append the sell order to the feed list
            feed.append(sell_order)

            # Increment the counter for the next order_id
            counter += 10
    return feed

def create_feed(timestamp):
    feed = []
    counter = 1
    QUANTITY = 10

    for seq_id, instr_id, item_id, broker_id, price, direction in [
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID_2, 50, COMMON.Direction.buy),
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID_2, 52, COMMON.Direction.sell),
        # Power: item id 19 => 2022 (JAN22-JAN23), # item id 20 => 2023
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID_2, 47, COMMON.Direction.buy),
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID_2, 57, COMMON.Direction.sell),
        # Mkt3:
        (POWER_MONTHS, DE_EEX, POWER_2023_ITEM_ID, BROKER_ID, -5, COMMON.Direction.buy),
        (POWER_MONTHS, DE_EEX, POWER_2023_ITEM_ID, BROKER_ID, 3, COMMON.Direction.sell),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 40, COMMON.Direction.buy),
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 60, COMMON.Direction.sell),
        # Power: item id 19 => 2022 (JAN22-JAN23), # item id 20 => 2023
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 40, COMMON.Direction.buy),
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 60, COMMON.Direction.sell),
    ]:
        feed.append(
            create_add_order(
                timestamp=timestamp,
                broker_id=broker_id,
                instrument_id=instr_id,
                item_id=item_id,
                term_format_id=None,
                sequence_id=seq_id,
                direction=direction,
                order_id=str(counter).zfill(8),
                price=price,
                quantity=QUANTITY
            )
        )
        counter += 10
    return feed

def create_trade_feed2():
    feed = []
    counter = 1  # Initial counter for order_id
    QUANTITY = 1  # Example quantity, adjust as needed

    # Constants for the order creation
    broker_id = BROKER_ID
    instrument_id = POWER_YEARS
    item_id = ITALY_PRODUCT_ID

    # Open the CSV file and read the data
    with open(file_path_tr, 'r') as file:
        csv_reader = csv.DictReader(file)

        for row in csv_reader:
            timestamp = datetime.datetime.strptime(row[''], '%Y-%m-%d %H:%M:%S').timestamp()
            price = round(float(row['price']),2)
            action = int(row['action'])  # Convert action to an integer

            # Determine the direction based on the action value
            if action == 1:
                direction = COMMON.Direction.buy
            elif action == -1:
                direction = COMMON.Direction.sell
            else:
                raise ValueError(f"Invalid action value: {action}")

            # Create the order using the extracted data
            order = create_add_order(
                timestamp=timestamp + counter,
                broker_id=broker_id,
                instrument_id=ITALY_BASELOAD,
                item_id=POWER_2023_ITEM_ID,
                term_format_id=None,  # Adjust if needed
                sequence_id=POWER_YEARS,  # Adjust if needed
                direction=direction,
                order_id=str(counter).zfill(8),  # Creates a zero-padded order_id
                price=price,
                quantity=QUANTITY
            )

            # Append the order to the feed list
            feed.append(order)

            # Increment the counter for the next order_id
            counter += 10
    return feed
def create_trade_feed(timestamp):
    feed = []
    counter = 1
    QUANTITY = 1

    for seq_id, instr_id, item_id, broker_id, price, direction in [
        # Trade
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 47.3, COMMON.Direction.sell),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 56.7, COMMON.Direction.buy),
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 56.7, COMMON.Direction.buy),
        (POWER_YEARS, ITALY_BASELOAD, POWER_2023_ITEM_ID, BROKER_ID, 56.7, COMMON.Direction.buy),
    ]:
        feed.append(
            create_add_order(
                timestamp=timestamp + counter,
                broker_id=broker_id,
                instrument_id=instr_id,
                item_id=item_id,
                term_format_id=None,
                sequence_id=seq_id,
                direction=direction,
                order_id=str(counter).zfill(8),
                price=price,
                quantity=QUANTITY
            )
        )
        counter += 10
    return feed



class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = "mm_ord_strategy"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
        # 2022 6 27
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[TTF_ICE, ITALY_BASELOAD],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="MarketMaking Synth Strategy",
            package_name="mm_strategy",
            product_ids=[TTF_PRODUCT_ID, ITALY_PRODUCT_ID],
            leg1_clip=1,
            leg2_clip=1,
            price_coeff=[1,1],
            broker_ids=[BROKER_ID, BROKER_ID_2],
            fix_margin=0.1,
            max_margin=0.3,
            preferred_clips=1,
            max_clips=1,
            take_profit=0.1,
            stop_loss=1,
            hard_stop_loss=1.5,
            mtm_bool=True,
            quote_leg1=True,
            quote_leg2=True,
            quote_buy=True,
            quote_sell=True,
            model_type="EMA",
            model_params=[.5, .025],
            eql_weight=0.1,
            eql_price=-0.5,
            mrg_weight=0.4,
            std_weight=1.,
            ql_max=1e10
        )

    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {GAS_YEARS: 1000, POWER_YEARS: 1000},
                                    "minimum_sales_price": {GAS_YEARS: 0, POWER_YEARS: 0},
                                    "maximum_sales_volume": {GAS_YEARS: 1000, POWER_YEARS: 1000},
                                    "maximum_purchase_price": {GAS_YEARS: 1000, POWER_YEARS: 1000}},
        }

    def test(self):
        # simulate POST to create strategy, referring to package, as defined in config
        rest_strat_msg_create = create_strategy_config_message(
            timestamp=self.first_transfer,
            strategy_id=self.strategy_id,
            strategy_configuration=self.config
        )

        self.config.update({"active": True})
        rest_strat_msg_activate = create_strategy_config_message(
            timestamp=self.first_transfer + 1,
            strategy_id=self.strategy_id,
            strategy_configuration=self.config
        )

        limits_payload = self._get_setup_limits()

        limits_setup_message = create_per_products_limit_message(timestamp=self.first_transfer + 2,
                                                                 strategy_id=self.strategy_id,
                                                                 limits_dict=limits_payload)

        feed = create_feed(self.first_transfer + 5)
        feed.extend(create_trade_feed(self.first_transfer + 15))
        # feed = create_feed2()
        # feed.extend(create_trade_feed2())

        sim = Simulator(
            event_messages=[rest_strat_msg_create, limits_setup_message, rest_strat_msg_activate],
            json_feed=feed,
            use_persistence=False,
            trayport_init_directory=INIT_FILES_ZIP,
            trayport_config={"venues": "EEX, ICE, EEXWD, EEX A, EEX F, IENX, IENX F",
                             "commodities": "Gas, Euro, Emissions",
                             "product_subscription_max_years": 5,
                             "product_subscription_shortterm_days": 0,
                             "product_subscription_midterm_count": 200,
                             "product_subscription_longterm_count": 100},
            simulated_exchanges=(COMMON.Exchange.trayport,),
            strategies_folder=EXAMPLE_FOLDER,
            timer_fast_timestep=3600,
            timer_timestep=3600,
        )

        sim.run(write_logfiles=False)

        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)

        # check traded amount for a specific product
        traded = traded_by_strategy[self.strategy_id]
        # self.assertEqual(traded[GAS_PRODUCT_ID]["net_volume"], 20)
        # self.assertEqual(traded[GAS_PRODUCT_ID]["areas"][TTF_ICE]["unit"], "MEGAWATTS")
        # self.assertEqual(traded[GAS_PRODUCT_ID]["areas"][TTF_ICE]["net_volume"], 20)
        # self.assertEqual(traded[POWER_PRODUCT_ID]["net_volume"], -20)
        # self.assertEqual(traded[POWER_PRODUCT_ID]["areas"][ITALY_BASELOAD]["unit"], "MEGAWATTS")
        # self.assertEqual(traded[POWER_PRODUCT_ID]["areas"][ITALY_BASELOAD]["net_volume"], -20)


if __name__ == '__main__':
    unittest.main()
