import unittest
import os.path
import datetime
import autotrader_lib.cet_util as CETUTIL

import autotrader_core.common as COMMON
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import create_strategy_config_message, create_per_products_limit_message, create_synthetic_order_message

GAS_YEARS = "10000301"
TTF_BROKER_ID = "37"
BROKER_ID = "37"
TTF_ICE = "10002196"
THE_ICE = "10002220"
GAS_YR22_ITEM_ID = "21"
GAS_PRODUCT_ID = GAS_YEARS + "_" + GAS_YR22_ITEM_ID


def create_add_order(timestamp, broker_id, instrument_id, item_id, term_format_id, sequence_id, direction, order_id,
                     price, quantity, ): return {"timestamp": timestamp, "exchange": "TRAYPORT",
                                                 "message_type": "order_book", "data": [
        {"counter_party_ok": False, "system_rank": "487290945", "broker_id": broker_id, "txt": False,
         "user_id": "0", "old_engine_id": "1", "state": "ACTI", "inst_specifier": [
            {"instrument_id": instrument_id, "first_item_id": item_id, "term_format_id": term_format_id,
             "second_item_id": "0", "sequence_span": "Single", "first_sequence_id": sequence_id}], "type": "O",
         "old_broker_id": broker_id, "direction": direction, "initial_order_id": order_id, "engine_id": "1",
         "order_id": order_id, "timestamp": timestamp, "price": price, "validity_date": None, "terms": [],
         "validity_restriction": "NON", "account": "0", "is_tradable": True, "execution_restriction": "NON",
         "implied": False, "action": "ADD", "traded": False, "quantity": quantity}]}


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

class BacktestingTest(unittest.TestCase):

    def test(self):


        timestamp_first = CETUTIL.utc_dt2ts(datetime.datetime(2022, 8, 23, 12, 0,0))
        strategy_id = "strategy_1"

        strategy_config = StrategyConfiguration(
            strategy_id=strategy_id,
            instrument_ids=["10002196"],
            strategies_folder=os.path.dirname(__file__),
            caption="Strategy",
            package_name="so_strategy"
        )

        rest_strategy_create = create_strategy_config_message(
            strategy_configuration=strategy_config,
            strategy_id=strategy_id,
            timestamp=timestamp_first
        )

        strategy_config.update({"active": True})
        rest_strategy_activate = create_strategy_config_message(
            strategy_configuration=strategy_config,
            strategy_id=strategy_id,
            timestamp=timestamp_first+1
        )

        limit_message = {
            "limits_per_sequence": {
                "maximum_purchase_volume": {"10000308": 1000},
                "maximum_sales_volume": {"10000308": 0},
                "maximum_purchase_price": {"10000308": 1000},
                "minimum_sales_price": {"10000308": 1000}},
        }
        rest_limits_create = create_per_products_limit_message(
            limits_dict=limit_message,
            strategy_id=strategy_id,
            timestamp=timestamp_first+2
        )

        # POST
        synthetic_order_payload = {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": GAS_PRODUCT_ID,
            "message_type": "synthetic_order",
            "synthetic_order_type": "ArbitrageOrder",
            "identifier": "identifier_so_1",
            "configuration": {
                "slot_name": "identifier_so_1",
                "market_area": TTF_ICE,
                "broker_id": BROKER_ID,
                "direction": COMMON.Direction.buy,
                "quantity": 10,
                "new_additional_view": THE_ICE
            }
        }
        rest_so_create = create_synthetic_order_message(
            timestamp=timestamp_first+3,
            strategy_id=strategy_id,
            synthetic_orders_payload=synthetic_order_payload
        )

        simulator = Simulator(
            event_messages=[rest_strategy_create,
                            rest_strategy_activate,
                            rest_limits_create,
                            rest_so_create],
            use_persistence=False,
            simulated_exchanges=(COMMON.Exchange.trayport),
            strategies_folder=os.path.dirname(__file__),
            json_feed=create_feed(timestamp_first),
            trayport_init_directory="X:/Production/Python2.7/own_strategies/workshop_examples/assets/init_files_2022_08_23.zip"
            #feed_paths=["X:/Production/Python2.7/own_strategies/workshop_examples/assets/ttf/20210615T14-15_ttfhical_gas_wd.zip"]
        )

        simulator.run(write_logfiles=False)

        traded = simulator.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)


if __name__ == '__main__':
    unittest.main()