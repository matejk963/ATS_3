import datetime
import os.path
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (
    create_strategy_config_message,
    create_per_products_limit_message,
    create_synthetic_order_message
)
from synth_ord_strategy.constants import GAS_YEARS, TTF_ICE, THE_ICE, GAS_PRODUCT_ID, TTF_BROKER_ID, GAS_YR22_ITEM_ID

PACKAGE_NAME = "synth_ord_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "tutorial_ff_arbitrage_09_multi_products")

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
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, TTF_BROKER_ID, 10, COMMON.Direction.buy),
        (GAS_YEARS, THE_ICE, GAS_YR22_ITEM_ID, TTF_BROKER_ID, 400, COMMON.Direction.buy),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (GAS_YEARS, TTF_ICE, GAS_YR22_ITEM_ID, TTF_BROKER_ID, 200, COMMON.Direction.sell),
        (GAS_YEARS, THE_ICE, GAS_YR22_ITEM_ID, TTF_BROKER_ID, 500, COMMON.Direction.sell),
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
        counter += 1
    return feed


def get_synth_order_payload():
    return {
        # register stands for the POST
        "operation": COMMON.SyntheticOrderOperations.register,
        # product_id would usually be filled based on the url
        "product_id": GAS_PRODUCT_ID,

        "message_type": "synthetic_order",
        "synthetic_order_type": "ArbitrageOrder",
        "identifier": SLOT_NAME_LEAD,
        "configuration": {
            # slot_name must be equal to identifier.
            # try to run this with different slotname and identifier to see the difference
            "slot_name": SLOT_NAME_LEAD,

            # market area and slot_name are required parameters
            # synthetic order will only be able to place slots for this instrument
            # the localview in the synthetic order will be based on this instrument
            "market_area": TTF_ICE,

            # broker id, as defined in the base synthetic order class
            "broker_id": TTF_BROKER_ID,

            # here we refer to the other view as named in the strategy template
            "lift_instrument_id": THE_ICE,
        }
    }


class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = "synth_ord_strategy"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 06, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[TTF_ICE, THE_ICE],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="Synth Strategy",
            package_name="synth_ord_strategy"
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

        # simulate call to the endoint:
        # POST "/synthetic/<strategy_id>/<product_id>/<synth_identifier>"
        synthetic_orders_payload = get_synth_order_payload()
        so_register_msg = create_synthetic_order_message(
            timestamp=self.first_transfer + 3,
            strategy_id=self.strategy_id,
            synthetic_orders_payload=synthetic_orders_payload
        )

        feed = create_feed(self.first_transfer + 5)
        feed.extend(create_feed(self.first_transfer + 15))

        sim = Simulator(
            event_messages=[rest_strat_msg_create, limits_setup_message, rest_strat_msg_activate, so_register_msg],
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
            timer_timestep=3600
        )

        sim.run(write_logfiles=False)

        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)

        # check traded amount for a specific product
        traded = traded_by_strategy[self.strategy_id]
        self.assertEqual(traded[GAS_PRODUCT_ID]['net_volume'], 0)
        self.assertEqual(traded[GAS_PRODUCT_ID]['total_volume'], 40)
        self.assertEqual(traded[GAS_PRODUCT_ID]["areas"][TTF_ICE]['net_volume'], 20)
        self.assertEqual(traded[GAS_PRODUCT_ID]["areas"][THE_ICE]['net_volume'], -20)


if __name__ == '__main__':
    unittest.main()
