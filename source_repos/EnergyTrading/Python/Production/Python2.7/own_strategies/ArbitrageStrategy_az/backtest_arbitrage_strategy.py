import datetime
import os.path
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (create_strategy_config_message,
                                                       create_per_products_limit_message,
                                                       create_synthetic_order_message)
from arbitrage_strategy.constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID_1, PRODUCT_ID_2, POWER_MONTHS, \
    POWER_ITEM_ID_1, POWER_ITEM_ID_2

PACKAGE_NAME = "arbitrage_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
SLOT_NAME_LEAD = "ArbitrageLead"
STRATEGY_ID = "synthetic_order_arbitrage"


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


def create_feed(timestamp):
    feed = []
    counter = 1
    QUANTITY = 10

    for seq_id, instr_id, item_id, broker_id, price, direction in [

        # (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID, BROKER_ID_2, 56, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID, BROKER_ID_1, 55.85, COMMON.Direction.buy),

        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 56, COMMON.Direction.sell),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 60, COMMON.Direction.sell),

        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 53, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 50, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 55, COMMON.Direction.buy),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"

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


def create_trade_feed(timestamp):
    feed = []
    counter = 1
    QUANTITY = 1

    for seq_id, instr_id, item_id, broker_id, price, direction in [
        # Trade
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 56.1, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 54.9, COMMON.Direction.sell)

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


def create_trade_feed2(timestamp):
    feed = []
    counter = 1
    QUANTITY = 1

    for seq_id, instr_id, item_id, broker_id, price, direction in [
        # Trade
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 54.9, COMMON.Direction.sell),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 56.1, COMMON.Direction.buy),

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


# def get_synth_order_payload():
#     return {
#         # register stands for the POST
#         "operation": COMMON.SyntheticOrderOperations.register,
#         # product_id would usually be filled based on the url
#         "product_id": PRODUCT_ID,
#
#         "message_type": "synthetic_order",
#         "synthetic_order_type": "ArbitrageOrder",
#         "identifier": SLOT_NAME_LEAD,
#         "configuration": {
#             # slot_name must be equal to identifier.
#             # try to run this with different slotname and identifier to see the difference
#             "slot_name": SLOT_NAME_LEAD,
#             "strategy_id": STRATEGY_ID,
#
#             # market area and slot_name are required parameters
#             # synthetic order will only be able to place slots for this instrument
#             # the localview in the synthetic order will be based on this instrument
#             "market_area": INST_ID_1,
#
#             # broker id, as defined in the base synthetic order class
#             "broker_id": BROKER_ID_1,
#
#             "own_product_id": PRODUCT_ID,
#             # here we refer to the other view as named in the strategy template
#             "lift_product_id": PRODUCT_ID,
#             "lift_instrument_id": INST_ID_2,
#             "lift_broker_id": BROKER_ID_2,
#         }
#     }

class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = "synthetic_order_arbitrage"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 06, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[INST_ID_1],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="Simple Arbitrage Strategy",
            package_name="arbitrage_strategy",
            product_ids=[PRODUCT_ID_1],
            broker_ids=[BROKER_ID_1, BROKER_ID_2],

            fix_margin=0.1,
            preferred_quantity=1,
            max_quantity=10,

            stop_loss=1,
            idle_thres=0.03,
            hard_stop_loss=1,

            market_volume_check_flag=0.0,
            ql_max=100000000000000000
        )

    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {POWER_MONTHS: 1000},
                                    "minimum_sales_price": {POWER_MONTHS: 0},
                                    "maximum_sales_volume": {POWER_MONTHS: 1000},
                                    "maximum_purchase_price": {POWER_MONTHS: 1000}},
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
        # synthetic_orders_payload = get_synth_order_payload()
        # so_register_msg = create_synthetic_order_message(
        #     timestamp=self.first_transfer + 3,
        #     strategy_id=self.strategy_id,
        #     synthetic_orders_payload=synthetic_orders_payload
        # )

        feed = create_feed(self.first_transfer + 5)
        feed.extend(create_trade_feed(self.first_transfer + 100))
        feed.extend(create_trade_feed2(self.first_transfer + 2000))


        sim = Simulator(
            event_messages=[rest_strat_msg_create, limits_setup_message, rest_strat_msg_activate],  # , so_register_msg
            json_feed=feed,
            use_persistence=False,
            trayport_init_directory=INIT_FILES_ZIP,
            trayport_config={"venues": "EEX, ICE, EEXWD, EEX A, EEX F, IENX, IENX F, OTC",
                             "commodities": "Euro, Gas, Emissions",  # "Gas, Euro, Emissions",
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
