import datetime
import os.path
import sys
import time

# Change to the root directory to ensure proper module resolution
root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
os.chdir(root_dir)
sys.path.insert(0, root_dir)

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting
from backtesting.simulate import Simulator
from backtesting.strategy_configuration import StrategyConfiguration
from backtesting.synchronous_backtesting_utils import (create_strategy_config_message,
                                                       create_per_products_limit_message)
from own_strategies.ObserverStrategy.observer_strategy.constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID_1, POWER_MONTHS, \
    POWER_ITEM_ID_1

PACKAGE_NAME = "observer_strategy"
EXAMPLE_FOLDER = os.path.dirname(__file__)
INIT_FILES_ZIP = os.path.join(backtesting.ROOT_PATH, "own_strategies", "workshop_examples",
                              "assets", "init_files_2022_08_23.zip")
STRATEGY_FOLDER = os.path.join(EXAMPLE_FOLDER, "BacktestResults")
STRATEGY_ID = "observer_strategy"

def create_add_order(timestamp, broker_id, instrument_id, item_id, term_format_id, sequence_id, 
                     direction, order_id, price, quantity):
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

def create_add_trade(timestamp, broker_id, instrument_id, item_id, term_format_id, sequence_id,
                     direction, trade_id, price, quantity):
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

def create_test_feed(timestamp):
    feed = []
    QUANTITY = 1
    
    counter_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    
    # Build a realistic order book first
    for counter, seq_id, instr_id, item_id, broker_id, price, direction in [
        # Initial order book setup - spread around 60.0
        (counter_list[0], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 60.10, COMMON.Direction.sell),  # Ask
        (counter_list[1], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 60.15, COMMON.Direction.sell),  # Ask
        (counter_list[2], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_2, 60.20, COMMON.Direction.sell),  # Ask
        (counter_list[3], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 59.90, COMMON.Direction.buy),   # Bid
        (counter_list[4], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 59.85, COMMON.Direction.buy),   # Bid
        (counter_list[5], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_2, 59.80, COMMON.Direction.buy),   # Bid
        
        # Add more depth for sparsity calculations
        (counter_list[6], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_2, 60.25, COMMON.Direction.sell),  # Ask
        (counter_list[7], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_2, 60.30, COMMON.Direction.sell),  # Ask
        (counter_list[8], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 59.75, COMMON.Direction.buy),   # Bid
        (counter_list[9], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 59.70, COMMON.Direction.buy),   # Bid
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
                quantity=QUANTITY + (counter % 3)  # Varying quantities
            )
        )
    
    # Add multiple realistic trades to trigger observer analysis
    # Note: Strategy expects BROKER_ID_1 (38) to be involved for EEX trades
    trade_scenarios = [
        # Trade 1: Market buy hitting ask - EEX trade with BROKER_ID_1
        (counter_list[10], BROKER_ID_1, 60.10, COMMON.Direction.buy, "T0001"),
        
        # Trade 2: Market sell hitting bid - EEX trade with BROKER_ID_1
        (counter_list[11], BROKER_ID_1, 59.90, COMMON.Direction.sell, "T0002"),
        
        # Trade 3: Aggressive buy above ask - gap trade scenario with BROKER_ID_1
        (counter_list[12], BROKER_ID_1, 60.25, COMMON.Direction.buy, "T0003"),
        
        # Trade 4: Aggressive sell below bid - gap trade scenario with BROKER_ID_1
        (counter_list[13], BROKER_ID_1, 59.75, COMMON.Direction.sell, "T0004"),
        
        # Trade 5: Mid-market trade - EEX trade with BROKER_ID_1
        (counter_list[14], BROKER_ID_1, 60.00, COMMON.Direction.buy, "T0005"),
    ]
    
    for counter, broker_id, price, direction, trade_id in trade_scenarios:
        feed.append(
            create_add_trade(
                timestamp=timestamp+counter,
                broker_id=broker_id,
                instrument_id=INST_ID_1,
                item_id=POWER_ITEM_ID_1,
                term_format_id=None,
                sequence_id=POWER_MONTHS,
                direction=direction,
                trade_id=trade_id,
                price=price,
                quantity=QUANTITY
            )
        )
    
    # Add some more orders after trades to update the book
    for counter, seq_id, instr_id, item_id, broker_id, price, direction in [
        (counter_list[15], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_1, 60.05, COMMON.Direction.sell),
        (counter_list[16], POWER_MONTHS, INST_ID_1, POWER_ITEM_ID_1, BROKER_ID_2, 59.95, COMMON.Direction.buy),
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

class ObserverStrategyTest:
    def setUp(self):
        self.strategy_id = STRATEGY_ID
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 6, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[INST_ID_1],
            strategies_folder=EXAMPLE_FOLDER,
            caption="OBSERVER",
            package_name=PACKAGE_NAME,
            product_ids=[PRODUCT_ID_1],
            broker_list=[BROKER_ID_1, BROKER_ID_2],
        )

    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {POWER_MONTHS: 10},
                                    "minimum_sales_price": {POWER_MONTHS: 0},
                                    "maximum_sales_volume": {POWER_MONTHS: 10},
                                    "maximum_purchase_price": {POWER_MONTHS: 1000}},
        }

    def test_observer_scenario(self):
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
        limits_setup_message = create_per_products_limit_message(
            timestamp=self.first_transfer + 2,
            strategy_id=self.strategy_id,
            limits_dict=limits_payload
        )

        feed = create_test_feed(self.first_transfer)
        
        print("### OBSERVER STRATEGY TEST FEED ###")
        print("Feed contains:")
        order_count = sum(1 for x in feed if x['message_type'] == 'order_book')
        trade_count = sum(1 for x in feed if x['message_type'] == 'trade_list')
        print(f"- {order_count} order book updates")
        print(f"- {trade_count} trade events")
        print("\nTrade scenarios included:")
        for i, x in enumerate([msg for msg in feed if msg['message_type'] == 'trade_list']):
            trade_data = x['data'][0]
            print(f"  Trade {i+1}: {trade_data['trade_id']} - {trade_data['price']} ({trade_data['aggressor_action']})")
        print()

        sim = Simulator(
            event_messages=[rest_strat_msg_create, limits_setup_message, rest_strat_msg_activate],
            json_feed=feed,
            use_persistence=False,
            trayport_init_directory=INIT_FILES_ZIP,
            trayport_config={"venues": "EEX, ICE, EEXWD, EEX A, EEX F, IENX, IENX F, OTC",
                             "commodities": "Euro, Gas, Emissions",
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

        # Observer strategy should not trade anything
        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)
        
        print("### OBSERVER STRATEGY RESULTS ###")
        print(f"Traded by strategy: {traded_by_strategy}")
        print("Observer strategy completed - no trades should be executed")
        
        # Extract actual metrics from log files
        print("\n### ACTUAL STRATEGY RESULTS ###")
        
        try:
            # Find the most recent log file with actual content
            import glob
            log_files = glob.glob('autotrader_backtesting.log*')
            log_content = ""
            
            for log_file in sorted(log_files, reverse=True):
                try:
                    with open(log_file, 'r') as f:
                        content = f.read()
                        if len(content) > 100:  # File has some content
                            log_content = content
                            print(f"Reading from: {log_file}")
                            break
                except:
                    continue
                    
            if not log_content:
                print("No log files with content found")
                return traded_by_strategy
            
            # Extract real data from logs
            import re
            
            # Find all trades that were processed
            trade_logs = re.findall(r'On Public Trade Update', log_content)
            print(f"Trades processed by strategy: {len(trade_logs)}")
            
            # Find observations that succeeded  
            observe_success = re.findall(r"'can_observe': True", log_content)
            print(f"Successful observations: {len(observe_success)}")
            
            # Find actual comprehensive metrics
            comprehensive_logs = re.findall(r'OBSERVER_COMPREHENSIVE.*Trade (T\d+):', log_content)
            print(f"Comprehensive metrics collected for: {len(comprehensive_logs)} trades")
            if comprehensive_logs:
                print(f"Trade IDs with metrics: {comprehensive_logs}")
            
            # Extract actual observed decisions
            observed_decisions = re.findall(r"'observation_decision': 'observed'", log_content)
            print(f"Trades successfully observed: {len(observed_decisions)}")
            
            # Extract actual market data from logs
            market_data_pattern = r"'market_data': \{([^}]*'trd_price': ([^,]*)[^}]*)\}"
            market_data_matches = re.findall(market_data_pattern, log_content)
            
            if market_data_matches:
                print(f"\nActual market data collected:")
                for i, (full_data, trade_price) in enumerate(market_data_matches[:3]):
                    print(f"  Entry {i+1}: Trade price {trade_price}")
                    
                    # Extract key metrics from the market data
                    bid_match = re.search(r"'b_price': ([^,]*)", full_data)
                    ask_match = re.search(r"'a_price': ([^,]*)", full_data)
                    spread_match = re.search(r"'ba_spread': ([^,]*)", full_data)
                    
                    if bid_match and ask_match and spread_match:
                        print(f"    Bid: {bid_match.group(1)}, Ask: {ask_match.group(1)}, Spread: {spread_match.group(1)}")
                        
                    # Extract sparsity
                    bid_sparsity = re.search(r"'b_price_sparsity': ([^,]*)", full_data)
                    ask_sparsity = re.search(r"'a_price_sparsity': ([^,]*)", full_data)
                    if bid_sparsity and ask_sparsity:
                        print(f"    Sparsity - Bid: {bid_sparsity.group(1)}, Ask: {ask_sparsity.group(1)}")
            
            # Find trading conditions
            long_conditions = re.findall(r"'long_conditions': True", log_content)
            short_conditions = re.findall(r"'short_conditions': True", log_content)
            print(f"\nTrading conditions analysis:")
            print(f"LONG conditions met: {len(long_conditions)} times")
            print(f"SHORT conditions met: {len(short_conditions)} times")
            
            # Check for any errors
            errors = re.findall(r'ERROR.*', log_content)
            observer_errors = re.findall(r'ERROR.*OBSERVER.*', log_content)
            warnings = re.findall(r'WARNING.*', log_content)
            
            print(f"\nError Analysis:")
            print(f"Total errors in log: {len(errors)}")
            print(f"Observer-specific errors: {len(observer_errors)}")
            print(f"Warnings: {len(warnings)}")
            
            if observer_errors:
                print(f"\nObserver Strategy Errors:")
                for i, error in enumerate(observer_errors[:5]):
                    print(f"  {i+1}: {error}")
            
            if errors and not observer_errors:
                print(f"\nGeneral Errors (first 3):")
                for i, error in enumerate(errors[:3]):
                    print(f"  {i+1}: {error}")
            
            if warnings:
                print(f"\nWarnings (first 3):")
                for i, warning in enumerate(warnings[:3]):
                    print(f"  {i+1}: {warning}")
            
            # Check for specific strategy issues
            exceptions = re.findall(r'Exception.*observer.*', log_content, re.IGNORECASE)
            if exceptions:
                print(f"\nExceptions related to observer:")
                for exc in exceptions[:3]:
                    print(f"  {exc}")
            
            # Check for filtered trades
            filtered_trades = re.findall(r"'entry_decision': 'filtered'", log_content)
            if filtered_trades:
                print(f"\nFiltered trades: {len(filtered_trades)} (trades that didn't meet criteria)")
                
                # Get filter reasons
                filter_reasons = re.findall(r"'reason': '([^']*)'", log_content)
                if filter_reasons:
                    reason_counts = {}
                    for reason in filter_reasons:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    print("Filter reasons:")
                    for reason, count in reason_counts.items():
                        print(f"  {reason}: {count} times")
            
        except Exception as e:
            print(f"Could not read log file: {e}")
            print("No actual metrics available")
        
        return traded_by_strategy

def main():
    test = ObserverStrategyTest()
    test.setUp()
    test.test_observer_scenario()

if __name__ == '__main__':
    main()