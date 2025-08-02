from abc import ABC, abstractmethod
import numpy as np
import pandas as pd

# Define constants for closing reasons for clarity
TAKE_PROFIT = 'TAKE_PROFIT'
STOP_LOSS = 'STOP_LOSS'
BURNOUT = 'BURNOUT'
TRAILING_STOP = 'TRAILING_STOP' # Example of another type
TIME_EXPIRY = 'TIME_EXPIRY' # For positions that should close by EOD

class BaseClosingStrategy(ABC):
    def __init__(self, strategy_params: dict):
        self.params = strategy_params

    @abstractmethod
    def check_and_get_close_details(self, strategy_instance, current_data: dict, open_trade_details: dict, trade_index: int):
        """
        Determines if a trade should be closed based on the strategy's logic.

        Args:
            strategy_instance: The instance of the main strategy (e.g., ModularStrategy).
                               This provides access to broader strategy context if needed (e.g. self.param_dict).
            current_data (dict): The current market data (e.g., tick, bar).
                                 Expected to contain keys like 'timestamp', 'b_price', 'a_price', 'trd_price'.
            open_trade_details (dict): Details of the open trade.
                                       Expected keys: 'open_price', 'true_open_price', 'position_type' ('LONG'/'SHORT'),
                                       'open_timestamp', 'volume', 'entry_index' (optional, for burnout).
            trade_index (int): An identifier for the trade, useful if managing multiple trades.

        Returns:
            tuple: (should_close (bool), reason (str/None), closing_price (float/None), conditions_met (dict/None))
                   - should_close: True if the trade should be closed.
                   - reason: A string indicating why the trade is closed (e.g., TAKE_PROFIT, STOP_LOSS).
                   - closing_price: The price at which to close the trade.
                   - conditions_met: Optional dict with specific conditions that triggered the close.
        """
        pass

    def on_trade_opened(self, strategy_instance, trade_details: dict, trade_index: int):
        """
        Optional: Called when a new trade is opened. Can be used to initialize
        state specific to this closing strategy for that trade (e.g., trailing stop start price).
        """
        pass

    def on_trade_closed(self, strategy_instance, closed_trade_info: dict):
        """
        Optional: Called after a trade is closed. Can be used for cleanup or logging.
        Args:
            strategy_instance: The instance of the main strategy.
            closed_trade_info (dict): Information about the trade that was just closed.
                                      This could be the trade object or relevant parts from strategy.stats_dict.
        """
        pass


class StandardClosingStrategy(BaseClosingStrategy):
    def __init__(self, strategy_params: dict):
        super().__init__(strategy_params)
        # Extract specific parameters needed for this closing strategy
        self.stop_loss_pips = self.params.get('stop_loss', 0.3)  # Default SL if not in params
        self.take_profit_pips = self.params.get('stop_profit', 0.1) # Default TP if not in params
        self.burnout_period_minutes = self.params.get('burnout_period', 5)
        # 'closing_mode' and 'close_trade_info' might be used for more complex logic
        self.closing_mode = self.params.get('closing_mode', 'Standard') # e.g. 'Standard', 'Aggressive', 'Other'
        self.close_trade_info = self.params.get('close_trade_info', None)


    def check_and_get_close_details(self, strategy_instance, current_data: dict, open_trade_details: dict, trade_index: int):
        """
        Implements standard closing logic: Stop Loss, Take Profit, Burnout.
        """
        position_type = open_trade_details['position_type']
        # Use 'trailing_price' from ModularStrategy's position_dict for SL/TP checks,
        # which is passed as 'open_price' in open_trade_details by the refactored lift_act.
        # The 'true_open_price' is the original entry price.
        effective_open_price = open_trade_details['open_price'] # This is the trailing price for SL/TP
        true_open_price = open_trade_details['true_open_price'] # Original entry price

        current_timestamp = current_data['timestamp']
        open_timestamp = open_trade_details['open_timestamp']
        
        # Initialize default return values
        should_close = False
        reason = None
        closing_price = None
        conditions_met = {}

        # Determine potential closing prices based on current market data
        # For a long position, close by selling (use bid price or last trade if more aggressive)
        # For a short position, close by buying (use ask price or last trade if more aggressive)
        # This logic might need to be more nuanced based on how 'create_slot' works or if specific execution is desired.
        
        # Simplified closing price logic: use opposite side of book or trade price if available
        # This assumes the strategy aims to cross the spread to close.
        if position_type == 'LONG':
            potential_close_price_market = current_data['b_price'] # Sell at best bid
        else: # SHORT
            potential_close_price_market = current_data['a_price'] # Buy at best ask
        
        # If trade price is available and more favorable (or required by logic), consider it.
        # For now, let's assume closing at the current market's bid/ask is the primary mechanism.
        # The actual execution price will be determined/validated by `create_slot`.
        # The `closing_price` returned here is the *target* or *trigger* price.

        # 1. Stop Loss Check
        if position_type == 'LONG':
            sl_price = effective_open_price - self.stop_loss_pips
            if current_data['b_price'] <= sl_price: # Price dropped to or below SL
                should_close = True
                reason = STOP_LOSS
                closing_price = current_data['b_price'] # Close at current bid
                conditions_met['sl_price'] = sl_price
                conditions_met['market_price'] = current_data['b_price']
        else:  # SHORT
            sl_price = effective_open_price + self.stop_loss_pips
            if current_data['a_price'] >= sl_price: # Price rose to or above SL
                should_close = True
                reason = STOP_LOSS
                closing_price = current_data['a_price'] # Close at current ask
                conditions_met['sl_price'] = sl_price
                conditions_met['market_price'] = current_data['a_price']
        
        if should_close:
            return should_close, reason, closing_price, conditions_met

        # 2. Take Profit Check
        if position_type == 'LONG':
            tp_price = true_open_price + self.take_profit_pips # TP is often based on true_open_price
            if current_data['b_price'] >= tp_price: # Price rose to or above TP
                should_close = True
                reason = TAKE_PROFIT
                closing_price = current_data['b_price']
                conditions_met['tp_price'] = tp_price
                conditions_met['market_price'] = current_data['b_price']
        else:  # SHORT
            tp_price = true_open_price - self.take_profit_pips
            if current_data['a_price'] <= tp_price: # Price dropped to or below TP
                should_close = True
                reason = TAKE_PROFIT
                closing_price = current_data['a_price']
                conditions_met['tp_price'] = tp_price
                conditions_met['market_price'] = current_data['a_price']

        if should_close:
            return should_close, reason, closing_price, conditions_met

        # 3. Burnout Check (Time-based expiry for the trade)
        # Ensure timestamps are comparable; pandas Timestamps are good.
        if not isinstance(open_timestamp, pd.Timestamp):
            open_timestamp = pd.to_datetime(open_timestamp)
        if not isinstance(current_timestamp, pd.Timestamp):
            current_timestamp = pd.to_datetime(current_timestamp)

        time_since_open = current_timestamp - open_timestamp
        if time_since_open >= pd.Timedelta(minutes=self.burnout_period_minutes):
            should_close = True
            reason = BURNOUT
            # For burnout, close at the prevailing market price
            closing_price = potential_close_price_market 
            conditions_met['time_since_open_minutes'] = time_since_open.total_seconds() / 60
            conditions_met['burnout_threshold_minutes'] = self.burnout_period_minutes
        
        if should_close:
            return should_close, reason, closing_price, conditions_met
            
        # 4. End of Day Closing (if applicable, from main strategy params)
        # This demonstrates accessing params from the strategy_instance
        t_end = strategy_instance.param_dict.get('t_end')
        if t_end and current_data['timestamp'].time() >= t_end:
            if not strategy_instance._is_overnight: # Check if strategy allows overnight positions
                should_close = True
                reason = TIME_EXPIRY
                closing_price = potential_close_price_market
                conditions_met['end_of_day_time'] = t_end

        # If no conditions met, return defaults
        return should_close, reason, closing_price, conditions_met

    def on_trade_opened(self, strategy_instance, trade_details: dict, trade_index: int):
        # Example: Log or initialize something if needed
        # print(f"ClosingStrategy: Trade {trade_index} opened at {trade_details['open_price']}")
        pass

    def on_trade_closed(self, strategy_instance, closed_trade_info: dict):
        # Example: Log closure details from the perspective of the closing strategy
        # if closed_trade_info:
        #     print(f"ClosingStrategy: Trade closed. PnL (approx): {closed_trade_info.get('pnl_points', 'N/A')}")
        pass
