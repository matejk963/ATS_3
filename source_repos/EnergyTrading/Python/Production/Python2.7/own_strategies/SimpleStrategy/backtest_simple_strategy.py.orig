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
from simple_strategy.constants import BROKER_ID, GAS_YEARS, GAS_YR22_ITEM_ID, TTF_ICE, TTF_PRODUCT_ID

PACKAGE_NAME = "simple_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
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
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 50, COMMON.Direction.buy),
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 55, COMMON.Direction.sell),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 49, COMMON.Direction.buy),
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, BROKER_ID, 56, COMMON.Direction.sell),
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


class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = "simple_ord_strategy"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 06, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[TTF_ICE],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="Simple Synth Strategy",
            package_name="simple_strategy",
            product_ids=[TTF_PRODUCT_ID],
            broker_id=BROKER_ID,
            fix_margin=0.1,
            preferred_quantity=1,
            max_quantity=3,
        )

    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {GAS_YEARS: 1000},
                                    "minimum_sales_price": {GAS_YEARS: 0},
                                    "maximum_sales_volume": {GAS_YEARS: 1000},
                                    "maximum_purchase_price": {GAS_YEARS: 1000}},
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
        feed.extend(create_feed(self.first_transfer + 15))

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

        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=True, only_traded=False)

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
