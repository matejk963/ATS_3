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
from mm_strategy.constants import (BROKER_ID, BROKER_ID_0, BROKER_ID_1, DE_EEX, M1_PRODUCT_ID, M2_PRODUCT_ID, M1M2_PRODUCT_ID,
                                   POWER_MONTHS)

PACKAGE_NAME = "mm_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2023-12-31-1.zip")
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


class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = "mm_ord_strategy"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2023, 11, 28, 9, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[DE_EEX, DE_EEX],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="MarketMaking Synth Strategy",
            package_name="mm_strategy",
            product_ids=[M1_PRODUCT_ID, M2_PRODUCT_ID],
            leg1_clip=1,
            leg2_clip=1,
            broker_ids=[BROKER_ID, BROKER_ID_0, BROKER_ID_1],
            fix_margin=0.1,
            preferred_clips=1,
            max_clips=1,
            take_profit=0.1,
            stop_loss=1,
            hard_stop_loss=1.5,
            mtm_bool=True,
            model_type="MSTD_x",
            model_params=[20., .025],
            eql_weight=0.,
            eql_price=-0.5,
            mrg_weight=0.4,
            std_weight=2.05
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

        sim = Simulator(
            event_messages=[rest_strat_msg_create, limits_setup_message, rest_strat_msg_activate],
            # json_feed=feed,
            feed_paths=["//etc-dc2k19/net/Algo/Files/backtestProd/MAR-231201_f12.jsonl"],
            # feed_paths=["S:\Algo\Files\MAR-231127\MAR-231127.jsonl"],
            use_persistence=False,
            trayport_init_directory=INIT_FILES_ZIP,
            trayport_config={"venues": "EEX, EEX A, EEX F",
                             "commodities": "Gas, Euro, Emissions",
                             "product_subscription_max_years": 2,
                             "product_subscription_shortterm_days": 0,
                             "product_subscription_midterm_count": 3,
                             "product_subscription_longterm_count": 2},
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
