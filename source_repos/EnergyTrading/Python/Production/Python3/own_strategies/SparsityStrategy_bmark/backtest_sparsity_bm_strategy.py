import datetime
import os.path
import unittest
import time
import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (create_strategy_config_message,
                                                       create_per_products_limit_message)
from spbmark_strategy.constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID_1, POWER_MONTHS, \
    POWER_ITEM_ID_1

PACKAGE_NAME = "spbmark_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
SLOT_NAME_LEAD = "SpBMarkLead"
STRATEGY_ID = "strategy_sparsity_bmark"




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
def create_feed(timestamp, counter_list):
    feed = []
    QUANTITY = 1

    for counter, seq_id, instr_id, item_id, broker_id, price, direction in [

        # (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID, BROKER_ID_2, 56, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID, BROKER_ID_1, 55.85, COMMON.Direction.buy),
        (counter_list[-4], POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 56, COMMON.Direction.sell),
        (counter_list[-3], POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 56, COMMON.Direction.sell),
        (counter_list[-2], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 55.8, COMMON.Direction.sell),
        (counter_list[-1], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 55.2, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 56, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 50, COMMON.Direction.buy),
        # (POWER_MONTHS, INST_ID_2, POWER_ITEM_ID_1, BROKER_ID_2, 55, COMMON.Direction.buy),

        #(POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 56.1, COMMON.Direction.sell),
        # Gas: item id 20 -> Gas Yr 21 (OCT21-OCT22), # item id 21 -> "Gas Yr 22"

    ]:
        feed.append(
            create_add_order(
                timestamp=timestamp+counter,
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
    return feed

def create_order_feed(timestamp,  feed_list):
    feed = []
    QUANTITY = 1

    for counter, broker, price, direction in feed_list:
        feed.append(
            create_add_order(
                timestamp=timestamp+counter,
                broker_id= BROKER_ID_2 if broker else BROKER_ID_1,
                instrument_id= INST_ID_2 if broker else INST_ID_1,
                item_id= POWER_ITEM_ID_1,
                term_format_id=None,
                sequence_id=POWER_MONTHS,
                direction=direction,
                order_id=str(counter).zfill(8),
                price= price,
                quantity=QUANTITY
            )
        )
    return feed


def create_trade_feed(timestamp, feed_list):
    feed = []
    QUANTITY = 1

    for counter, broker, price, direction in feed_list:
        feed.append(
            create_add_trade(
                timestamp=timestamp + counter,
                broker_id= BROKER_ID_2 if broker else BROKER_ID_1,
                instrument_id= INST_ID_2 if broker else INST_ID_1,
                item_id=POWER_ITEM_ID_1,
                term_format_id=None,
                sequence_id=POWER_MONTHS,
                direction=direction,
                trade_id=str(counter).zfill(8),
                price=price,
                quantity=QUANTITY
            )
        )
    return feed

class StrategyTest():
    def setUp(self):
        self.strategy_id = "strategy_sparsity_bmark"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[INST_ID_1],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="SPB",
            package_name="spbmark_strategy",
            product_ids=[PRODUCT_ID_1],
            broker_list=[BROKER_ID_1, BROKER_ID_2],

            hard_stop_loss = 2.,

            trd_gap = 0.10,
            make_profit_margin = 0.25,
            loss_making_thold = 0.07,
            stop_loss_margin = 0.3,
            makeagg_ratio_thold = 0.5,
            burnout_period = 2,
            bid_ask = 1,
            max_position=1,
            lead_closing=False,
            thold_dense=0.15,
            thold_sparse=0.25,

            ql_max=100000000000000000
        )

    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {POWER_MONTHS: 10},
                                    "minimum_sales_price": {POWER_MONTHS: 0},
                                    "maximum_sales_volume": {POWER_MONTHS: 10},
                                    "maximum_purchase_price": {POWER_MONTHS: 1000}},
        }

    def feed_scenario_1(self):
        # branchflag 1
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price < open_price - self.stop_loss_margin:
        #                     if ask_price < open_price - self.loss_making_thold:
        #                         if make_agg_ratio > self.makeagg_ratio:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell], # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy], # best bid
            [20, True, 59.7, COMMON.Direction.sell], # target ask
            ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
            ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.2, COMMON.Direction.sell],
        ])
        # trade_feed += create_trade_feed(self.first_transfer, [
        #     [28, False, 58.0, COMMON.Direction.buy]
        # ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_2(self):
        # branchflag 2
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price < open_price - self.stop_loss_margin:
        #                     if ask_price < open_price - self.loss_making_thold:
        #              !           if make_agg_ratio <= self.makeagg_ratio:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.5, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_3(self):
        # branchflag 3
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price < open_price - self.stop_loss_margin:
        #        !             if ask_price >= open_price - self.loss_making_thold:
        #                         if burnout:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [2000, False, 60.0, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_4(self):
        # branchflag 4
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price < open_price - self.stop_loss_margin:
        #                     if ask_price >= open_price - self.loss_making_thold:
        #        !                 if not burnout:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [2000, False, 60.0, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_5(self):
        # branchflag 5
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #        !       if bid_price >= open_price - self.stop_loss_margin:
        #                     if ask_price < open_price - self.loss_making_thold:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [26, False, 59.45, COMMON.Direction.buy],
            [30, False, 59.6, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_6(self):
        # branchflag 6
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price >= open_price - self.stop_loss_margin:
        #                     if ask_price >= open_price - self.loss_making_thold:
        #       !                  if burnout:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [2000, False, 59.45, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_7(self):
        # branchflag 7
        # LEAD aggress ask
        # LONG ---
        #             if open_position > 0.1:
        #                if bid_price >= open_price - self.stop_loss_margin:
        #                     if ask_price >= open_price - self.loss_making_thold:
        #       !                  if not burnout:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.7, COMMON.Direction.sell],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 60.0, COMMON.Direction.buy]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.45, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_8(self):
        # branchflag 8
        # LEAD aggress bid
        # SHORT ---
        #        !     if open_position < -0.1:
        #                if ask_price > open_price + self.stop_loss_margin:
        #                     if bid_price > open_price + self.loss_making_thold:
        #       !                  if make_agg_ratio > self.makeagg_ratio_thold:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.8, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_9(self):
        # branchflag 9
        # LEAD aggress bid
        # SHORT ---
        #        !     if open_position < -0.1:
        #                if ask_price > open_price + self.stop_loss_margin:
        #                     if bid_price > open_price + self.loss_making_thold:
        #       !                  if make_agg_ratio <= self.makeagg_ratio_thold:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.45, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_10(self):
        # branchflag 10
        # LEAD aggress bid
        # SHORT ---
        #             if open_position < -0.1:
        #                if ask_price > open_price + self.stop_loss_margin:
        #       !             if bid_price <= open_price + self.loss_making_thold:
        #       !                  if burnout
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [2000, False, 59.0, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_11(self):
        # branchflag 11
        # LEAD aggress bid
        # SHORT ---
        #        !     if open_position < -0.1:
        #                if ask_price > open_price + self.stop_loss_margin:
        #                     if bid_price <= open_price + self.loss_making_thold:
        #       !                  if not burnout
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.0, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_12(self):
        # branchflag 12
        # LEAD aggress bid
        # SHORT ---
        #             if open_position < -0.1:
        #        !        if ask_price <= open_price + self.stop_loss_margin:
        #                     if bid_price > open_price + self.loss_making_thold:
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [30, False, 59.6, COMMON.Direction.sell],
            [30, False, 59.45, COMMON.Direction.buy],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_13(self):
        # branchflag 13
        # LEAD aggress bid
        # SHORT ---
        #             if open_position < -0.1:
        #                if ask_price <= open_price + self.stop_loss_margin:
        #          !           if bid_price <= open_price + self.loss_making_thold:
        #          !               if burnout
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [2000, False, 59.6, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def feed_scenario_14(self):
        # branchflag 14
        # LEAD aggress bid
        # SHORT ---
        #             if open_position < -0.1:
        #                if ask_price <= open_price + self.stop_loss_margin:
        #          !           if bid_price <= open_price + self.loss_making_thold:
        #          !               if not burnout
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 60.0, COMMON.Direction.sell],
            [2, False, 60.0, COMMON.Direction.sell],  # best ask
            [3, False, 59.0, COMMON.Direction.buy],
            [5, False, 59.0, COMMON.Direction.buy],  # best bid
            [20, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [35, False, 59.6, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])
    def feed_scenario_dense_sparse(self):
        # branchflag 14
        # LEAD aggress bid
        # SHORT ---
        #             if open_position < -0.1:
        #                if ask_price <= open_price + self.stop_loss_margin:
        #          !           if bid_price <= open_price + self.loss_making_thold:
        #          !               if not burnout
        # open feed
        order_feed = create_order_feed(self.first_transfer, [
            [1, False, 61.06, COMMON.Direction.sell],
            [2, False, 60.05, COMMON.Direction.sell],
            [3, False, 60.04, COMMON.Direction.sell],
            [4, False, 60.03, COMMON.Direction.sell],
            [5, False, 60.02, COMMON.Direction.sell],
            [6, False, 60.01, COMMON.Direction.sell],
            [7, False, 60.0, COMMON.Direction.sell],  # best ask

            [8, False, 58.5, COMMON.Direction.buy],
            [9, False, 58.7, COMMON.Direction.buy],
            [10, False, 58.75, COMMON.Direction.buy],
            [11, False, 59.0, COMMON.Direction.buy],  # best bid
            [12, True, 59.3, COMMON.Direction.buy],  # target ask
        ])
        trade_feed = create_trade_feed(self.first_transfer, [
            [25, False, 59.0, COMMON.Direction.sell]
        ])

        # close feed
        order_feed += create_order_feed(self.first_transfer, [
            [35, False, 59.6, COMMON.Direction.sell],
        ])
        feed = [*order_feed, *trade_feed]
        return sorted(feed, key=lambda x: x['timestamp'])

    def test(self, feed_func):
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

        feed = feed_func()
        print("### FEED LIST ###")
        print(*([(x['timestamp'], x['message_type']) for x in feed]), sep='\n')

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

def main():
    test_class = StrategyTest()
    test_class.setUp()
    test_class.test(test_class.feed_scenario_dense_sparse)

if __name__ == '__main__':
    main()

