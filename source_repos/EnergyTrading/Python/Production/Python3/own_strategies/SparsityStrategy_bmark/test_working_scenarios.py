#!/usr/bin/env python3
"""
Quick test to create working scenarios that actually trigger trades
"""

import datetime
import os.path
from spbmark_strategy.test_wrap import *
from spbmark_strategy.test_global_vars import global_state
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

def create_add_order(timestamp, broker_id, instrument_id, item_id, term_format_id, sequence_id, direction, order_id, price, quantity):
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

def create_add_trade(timestamp, broker_id, instrument_id, item_id, term_format_id, sequence_id, direction, trade_id, price, quantity):
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

def create_order_feed(timestamp, feed_list):
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

def create_working_short_scenario():
    """Create a SHORT scenario that should definitely work"""
    first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
    
    # Deep order book with proper sparsity
    order_feed = create_order_feed(first_transfer, [
        # Dense ask side (sparsity < 0.70)
        [1, False, 60.00, COMMON.Direction.sell],   # EEX best ask
        [2, False, 60.01, COMMON.Direction.sell],   # EEX 
        [3, False, 60.02, COMMON.Direction.sell],   # EEX 
        [4, False, 60.03, COMMON.Direction.sell],   # EEX 
        [5, False, 60.04, COMMON.Direction.sell],   # EEX 
        
        # Sparse bid side (sparsity > 0.20)  
        [6, False, 59.00, COMMON.Direction.buy],    # EEX best bid
        [7, False, 57.00, COMMON.Direction.buy],    # EEX (gap creates sparsity)
        [8, False, 55.00, COMMON.Direction.buy],    # EEX (gap creates sparsity)
        [9, False, 53.00, COMMON.Direction.buy],    # EEX (gap creates sparsity)
        
        # Non-EEX target order (CRITICAL)
        [10, True, 59.3, COMMON.Direction.buy],     # Non-EEX target for SHORT
    ])
    
    # Trade that triggers SHORT conditions
    # Need: trd_price < bid - trd_gap = 59.0 - 0.10 = 58.9
    trade_feed = create_trade_feed(first_transfer, [
        [25, False, 58.80, COMMON.Direction.sell]   # Should trigger SHORT
    ])
    
    # Post-trade order book update (CRITICAL for triggering strategy)
    order_feed += create_order_feed(first_transfer, [
        [30, False, 60.00, COMMON.Direction.sell],  # Maintain market
        [31, False, 59.00, COMMON.Direction.buy],   # Maintain market  
        [32, True, 59.3, COMMON.Direction.buy],     # Maintain non-EEX target
    ])
    
    feed = [*order_feed, *trade_feed]
    return sorted(feed, key=lambda x: x['timestamp'])

def test_working_scenario():
    """Test our working SHORT scenario"""
    strategy_id = "strategy_sparsity_bmark"
    first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
    
    config = StrategyConfiguration(
        strategy_id=strategy_id,
        instrument_ids=[INST_ID_1],
        strategies_folder=os.path.dirname(__file__),
        caption="SPB",
        package_name="spbmark_strategy",
        product_ids=[PRODUCT_ID_1],
        broker_list=[BROKER_ID_1, BROKER_ID_2],
        hard_stop_loss=2.0,
        trd_gap=0.10,
        make_profit_margin=0.25,
        loss_making_thold=0.07,
        stop_loss_margin=0.3,
        makeagg_ratio_thold=0.5,
        burnout_period=2,
        bid_ask=1,
        max_position=1,
        lead_closing=False,
        thold_dense=0.70,
        thold_sparse=0.20,
        ql_max=100000000000000000
    )
    
    # Get setup limits
    limits = {
        "limits_per_sequence": {"maximum_purchase_volume": {POWER_MONTHS: 10},
                                "minimum_sales_price": {POWER_MONTHS: 0},
                                "maximum_sales_volume": {POWER_MONTHS: 10},
                                "maximum_purchase_price": {POWER_MONTHS: 1000}},
    }
    
    # Create test feed
    feed = create_working_short_scenario()
    
    print("TESTING WORKING SHORT SCENARIO")
    print("=" * 50)
    print(f"Feed events: {len(feed)}")
    
    # Reset global state
    global_state.LOG_LIST = []
    
    # Create and run simulation
    rest_strat_msg_create = create_strategy_config_message(
        timestamp=first_transfer,
        strategy_id=strategy_id,
        strategy_configuration=config,
    )
    
    rest_strat_msg_limits = create_per_products_limit_message(
        timestamp=first_transfer,
        strategy_id=strategy_id,
        **limits
    )
    
    # Run simulation
    with Simulator(
        show_progress=False,
        speed_up_messages_logging=True,
        init_files_zip=None,
        stop_on_exception=False,
        print_feed_list=True
    ) as simulator:
        
        simulator.add_message(rest_strat_msg_create)
        simulator.add_message(rest_strat_msg_limits)
        
        for message in feed:
            simulator.add_message(message)
        
        traded_by_strategy = simulator.run()
    
    # Analyze results
    if strategy_id in traded_by_strategy:
        traded = traded_by_strategy[strategy_id]
        total_traded = sum(product['total_volume'] for product in traded.values())
        net_traded = sum(product['net_volume'] for product in traded.values())
        print(f"✅ SUCCESS! Total traded: {total_traded}, Net: {net_traded}")
        
        if net_traded < 0:
            print("✅ SHORT trade executed as expected!")
        else:
            print(f"⚠️  Expected SHORT (negative net) but got net: {net_traded}")
    else:
        print("❌ NO TRADES - Need to debug further")
        print(f"Strategy logs: {len(global_state.LOG_LIST)} entries")
        for log in global_state.LOG_LIST[:5]:  # Show first 5 logs
            print(f"  {log}")

if __name__ == "__main__":
    set_testing_mode(True)
    test_working_scenario()