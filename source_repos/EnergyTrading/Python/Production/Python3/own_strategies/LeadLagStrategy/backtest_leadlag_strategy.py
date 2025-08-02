    import datetime
import os.path
import unittest

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (create_strategy_config_message,
                                                       create_per_products_limit_message,
                                                       create_synthetic_order_message)
from leadlag_strategy.constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID_1, PRODUCT_ID_2, POWER_MONTHS, \
    POWER_ITEM_ID_1, POWER_ITEM_ID_2

PACKAGE_NAME = "leadlag_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
STRATEGY_ID = "leadlag_strategy"


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

def create_add_trade(
         timestamp,
         broker_id,
         instrument_id,
         item_id,
         term_format_id,
         sequence_id,
         direction,
         trade_id,
         price,
         quantity,
):
 return {"timestamp": timestamp,
         "exchange": "TRAYPORT",
         "message_type": "trade_list",
         "data": [
         {"quantity": quantity,
         "price": price,
         "initiator_user_id": "0", "initiator_broker_id": broker_id,
         "initiator_company_id": "0", "initiator_company": "",
         "initiator_action": "buy" if direction == "sell" else "sell",
         "aggressor_user_id": "0", "aggressor_broker_id": broker_id,
         "aggressor_action": "sell" if direction == "sell" else "buy",
         "aggressor_company_id": "0", "aggressor_company": "",
         "buy_delivery_area": instrument_id,
         "sell_delivery_area": instrument_id,
         "term": [],
         "order_id": trade_id,
         "execution_time": timestamp,
         "state": "ACTI",
         "trade_id": trade_id,
         "inst_specifier": [
         {"instrument_id": instrument_id, "first_item_id": item_id,
         "term_format_id": term_format_id,
         "second_item_id": "0", "sequence_span": "Single", "first_sequence_id": sequence_id}],

         "txt": None,
         "annotations": []
         }
         ]}
def create_feed(timestamp):
    feed = []
    counter = 1
    QUANTITY = 1

    for seq_id, instr_id, item_id, broker_id, price, direction in [

        # (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID, BROKER_ID_2, 56, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID, BROKER_ID_1, 55.85, COMMON.Direction.buy),

        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 40.0, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 39.9, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 39.8, COMMON.Direction.buy),
        #
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 41.0, COMMON.Direction.sell),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 41.1, COMMON.Direction.sell),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 41.2, COMMON.Direction.sell),

        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 59.6, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 60.0, COMMON.Direction.sell),
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


def create_feed2(timestamp):
    feed = []
    counter = 1
    QUANTITY = 1

    for seq_id, instr_id, item_id, broker_id, price, direction in [

        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 59.9, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 60.0, COMMON.Direction.sell),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 60.4, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 60.9, COMMON.Direction.sell),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 60.8, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_2, BROKER_ID_1, 61.3, COMMON.Direction.sell)
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
    counter = 100
    QUANTITY = 1.0

    for seq_id, instr_id, item_id, broker_id, price, direction in [
        # Trade
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 40.0, COMMON.Direction.sell),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 41.0, COMMON.Direction.buy),
        (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 41.1, COMMON.Direction.buy),


    ]:
        feed.append(
            create_add_trade(
                timestamp=timestamp + counter,
                broker_id=broker_id,
                instrument_id=instr_id,
                item_id=item_id,
                term_format_id=None,
                sequence_id=seq_id,
                direction=direction,
                trade_id=str(counter).zfill(8),
                price=price,
                quantity=QUANTITY
            )
        )
        counter += 10
    return feed


class SynthStratConfigTest(unittest.TestCase):
    def setUp(self):
        self.strategy_id = STRATEGY_ID
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[INST_ID_1, INST_ID_2],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="LeadLag Strategy",
            package_name=PACKAGE_NAME,
            lead_product_id=PRODUCT_ID_1,
            lag_product_id=PRODUCT_ID_2,
            broker_id=BROKER_ID_1,
            lead_brokers_list=[BROKER_ID_1],

            take_profit=0.5,
            stop_loss=-0.5,
            aggloss_thres=0.04,

            ba_max=0.5,

            MACD_long_threshold =0.1,
            MACD_short_threshold =-0.1,
            price_diff_long_threshold = 0.05,
            price_diff_short_threshold = -0.05,

            combined_long_threshold=0.25,
            combined_short_threshold=0.25,

            reg_model_coef1 = 0,
            reg_model_coef2 = 0.8,

            combined_mode = False,

            minimum_intensity = 1,

            burnout_period=60,
            stop_profit = 0.3,
            makeagg_ratio = 0.6,
            trail_stop = 100,

            preferred_quantity=1,
            max_quantity=1,
            hard_stop_loss=5,

            ql_max=10000000000000000000000
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
        feed.extend(create_feed2(self.first_transfer + 200))


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

        sim.run(write_logfiles=True)

        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)


        print('Public Trades : ' + str(sim.get_public_trades()))

        # check traded amount for a specific product
        traded = traded_by_strategy[self.strategy_id]




if __name__ == '__main__':
    unittest.main()
