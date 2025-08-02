import pandas as pd
import numpy as np
from datetime import time, datetime
from Strategies.Base.feature_interface import FeatureInterface # Assuming this is the correct interface
from Strategies.Modular_strategy.closing_strategies import BaseClosingStrategy, StandardClosingStrategy, TAKE_PROFIT, STOP_LOSS, BURNOUT, TIME_EXPIRY

class ModularStrategyWithModularClose:
    def __init__(self, features_pool: dict, strategy_columns: list, param_dict: dict, 
                 closing_strategy: BaseClosingStrategy = None, lead_closing=False, max_position=1, _is_overnight=False):
        self.features = {}
        self.param_dict = param_dict
        self.strategy_columns = strategy_columns
        self.lead_closing = lead_closing
        self.max_position = max_position
        self._is_overnight = _is_overnight # Determines if positions can be held overnight

        self.active_features = []
        for feature_name, feature_config in param_dict.items():
            if feature_name in features_pool and isinstance(feature_config, dict) and feature_config.get('active', False):
                feature_class = features_pool[feature_name]
                # Pass only the 'params' sub-dictionary to the feature if it exists
                feature_params_dict = feature_config.get('params', {})
                self.features[feature_name] = feature_class(
                    self.strategy_columns,
                    **feature_params_dict,
                    suffix=feature_config.get('suffix', "")
                )
                self.active_features.append(self.features[feature_name])
        
        self.primary_signal_feature_key = param_dict.get('primary_signal_feature_key', 'entry_signal')
        self.idx_column_name = param_dict.get('idx_column_name', 'idx') # For extracting current_idx in process method

        # Initialize closing strategy
        if closing_strategy:
            self.closing_strategy = closing_strategy
        else:
            # Default to StandardClosingStrategy if none provided, passing relevant params
            self.closing_strategy = StandardClosingStrategy(param_dict) 

        self.position_dict = {}  # Stores details of open positions
        self.stats_dict = []  # For recording trade actions and reasons
        self.daily_profit = {} # For tracking daily PnL

    def calculate_features(self, df_row: pd.Series) -> dict:
        feature_values = {}
        for feature in self.active_features:
            feature_values.update(feature.calculate(df_row))
        return feature_values

    def generate_signal(self, feature_values: dict) -> int:
        final_signal = 0
        
        # Check if a primary signal feature (configurable via param_dict) provides the signal
        if self.primary_signal_feature_key in feature_values:
            try:
                signal_value = feature_values[self.primary_signal_feature_key]
                if pd.isna(signal_value): # Handle NaN values if they can occur
                    final_signal = 0
                else:
                    final_signal = int(signal_value)
            except (ValueError, TypeError):
                # Consider logging a warning if the primary signal is not a valid integer
                # print(f"Warning: Primary signal feature '{self.primary_signal_feature_key}' value '{feature_values[self.primary_signal_feature_key]}' could not be converted to int.")
                final_signal = 0 # Default to no signal if conversion fails
        else:
            # Fallback: aggregate signals from features ending with '_signal'
            aggregated_signal = 0.0 # Use float for summation
            has_signal_features = False
            for key, value in feature_values.items():
                if key.endswith('_signal'):
                    has_signal_features = True
                    try:
                        if not pd.isna(value): # Ensure value is not NaN before attempting conversion
                            aggregated_signal += float(value)
                    except (ValueError, TypeError):
                        # Consider logging a warning for non-numeric signals
                        # print(f"Warning: Feature '{key}' ends with '_signal' but value '{value}' is not numeric. Skipping.")
                        pass # Skip non-numeric signal values
            
            if has_signal_features and aggregated_signal != 0:
                final_signal = int(np.sign(aggregated_signal))
            # If no primary signal and no other *_signal features, or they sum to 0, or all signals were NaN, final_signal remains 0.

        return final_signal

    def create_slot(self, df_row: pd.Series, signal: int, idx: int):
        current_price_bid = df_row['b_price']
        current_price_ask = df_row['a_price']
        timestamp = df_row['timestamp']
        
        # Determine entry price based on signal
        entry_price = current_price_ask if signal == 1 else current_price_bid if signal == -1 else None
        if entry_price is None: return # No action if no valid entry price

        position_type = 'LONG' if signal == 1 else 'SHORT'
        trade_key = f"trade_{idx}" # Unique key for the trade

        self.position_dict[trade_key] = {
            'open_price': entry_price, # This will be used as the reference for SL/TP adjustments (trailing)
            'true_open_price': entry_price, # The actual original entry price
            'position_type': position_type,
            'open_timestamp': timestamp,
            'volume': 1, # Assuming unit volume
            'entry_index': idx # Store original entry index from df
        }
        self.stats_dict.append({
            'timestamp': timestamp,
            'action': signal,
            'price_level': entry_price,
            'position_type': position_type,
            'reason': 'ENTRY',
            'trade_key': trade_key
        })
        # Notify closing strategy about the new trade
        self.closing_strategy.on_trade_opened(self, self.position_dict[trade_key], trade_key)

    def lift_act(self, df_row: pd.Series, idx: int):
        current_data_dict = df_row.to_dict() # Pass current row data to closing strategy
        trades_to_close_this_tick = []

        # Check for closing conditions for all open trades
        for trade_key, trade_details in list(self.position_dict.items()): # list() for safe iteration if modifying dict
            should_close, reason, closing_price, conditions_met = \
                self.closing_strategy.check_and_get_close_details(self, current_data_dict, trade_details, trade_key)

            if should_close:
                trades_to_close_this_tick.append((trade_key, reason, closing_price, conditions_met))
        
        # Execute closures
        for trade_key, reason, closing_price, conditions_met in trades_to_close_this_tick:
            self._close_trade(trade_key, df_row['timestamp'], closing_price, reason, conditions_met)

        # Check for new entry signals if not at max position
        # Note: Current total position is implicitly len(self.position_dict)
        # For strategies allowing mixed long/short, this needs to be net position or separate counts.
        # Assuming self.max_position applies to total number of open trades regardless of direction.
        if len(self.position_dict) < self.max_position:
            feature_values = self.calculate_features(df_row)
            signal = self.generate_signal(feature_values)
            if signal != 0:
                # Check if a trade in the same direction already exists if max_position is 1 or specific rules apply
                # This logic might need to be more sophisticated based on strategy rules (e.g. no new long if long exists)
                can_open_new = True
                if self.max_position == 1 and len(self.position_dict) > 0:
                    can_open_new = False # Already have a position
                elif any(trade['position_type'] == ('LONG' if signal == 1 else 'SHORT') for trade in self.position_dict.values()):
                    # Example: if strategy doesn't allow multiple positions in the same direction
                    # This rule might be part of a more complex position management system
                    # For now, let's assume if not max_position, we can open unless it's a duplicate direction for single pos type limit
                    pass # Allow if max_position > 1, or refine this logic

                if can_open_new:
                    self.create_slot(df_row, signal, idx)

    def _close_trade(self, trade_key: str, timestamp: datetime, closing_price: float, reason: str, conditions_met: dict):
        if trade_key not in self.position_dict:
            return # Trade already closed or key invalid

        trade_details = self.position_dict.pop(trade_key)
        
        pnl_points = 0
        if trade_details['position_type'] == 'LONG':
            pnl_points = closing_price - trade_details['true_open_price']
        else: # SHORT
            pnl_points = trade_details['true_open_price'] - closing_price
        
        # Record the closing action
        self.stats_dict.append({
            'timestamp': timestamp,
            'action': -1 if trade_details['position_type'] == 'LONG' else 1, # Action is opposite of opening
            'price_level': closing_price,
            'position_type': trade_details['position_type'],
            'reason': reason,
            'pnl_points': pnl_points,
            'open_price': trade_details['true_open_price'],
            'open_timestamp': trade_details['open_timestamp'],
            'conditions_met': conditions_met, # Store what triggered the close
            'trade_key': trade_key
        })

        # Update daily profit
        trade_date = timestamp.date()
        self.daily_profit[trade_date] = self.daily_profit.get(trade_date, 0) + pnl_points

        # Notify closing strategy about the closure
        closed_info = self.stats_dict[-1] # Pass the most recent stat entry
        self.closing_strategy.on_trade_closed(self, closed_info)

    def get_open_positions(self):
        return list(self.position_dict.values())

    def get_trade_statistics(self):
        return pd.DataFrame(self.stats_dict)

    def get_daily_pnl(self):
        return pd.Series(self.daily_profit).sort_index()

    # Optional: Method to update trailing stops if the closing strategy supports it
    # This would typically be called by the closing strategy itself if it manages its own state
    # or by the main strategy if it orchestrates this.
    def update_trailing_stop_for_trade(self, trade_key: str, new_stop_price: float):
        if trade_key in self.position_dict:
            # The 'open_price' in position_dict is used as the reference for SL/TP by StandardClosingStrategy
            # So, updating it effectively trails the stop/profit target.
            self.position_dict[trade_key]['open_price'] = new_stop_price
            # print(f"Trailing stop for {trade_key} updated to {new_stop_price}")

    # New methods for BacktestModular compatibility
    def get_open_position(self) -> int:
        """Returns the net open position: 1 for long, -1 for short, 0 for flat."""
        if not self.position_dict:
            return 0
        
        net_position = 0
        for trade_details in self.position_dict.values():
            if trade_details['position_type'] == 'LONG':
                net_position += trade_details.get('volume', 1) # Consider volume
            elif trade_details['position_type'] == 'SHORT':
                net_position -= trade_details.get('volume', 1) # Consider volume
        
        if net_position > 0:
            return 1
        elif net_position < 0:
            return -1
        return 0

    def process(self, row_dict: dict) -> tuple[float | None, int]:
        """
        Processes a single row of data (tick) for the backtester (e.g., BacktestModular).
        Extracts the necessary index, calls lift_act, and returns price and volume indication.
        Args:
            row_dict: Dictionary representing the current data row.
                      It must contain a key for the current index (e.g., 'idx', 'index', or configured via 'idx_column_name').
        Returns:
            A tuple (price, vol):
            - price (float | None): Execution price of the last action, if any.
            - vol (int): 1 if a trade action occurred (open/close), 0 otherwise.
        """
        current_idx_val = row_dict.get(self.idx_column_name)
        if current_idx_val is None:
            # Try common default 'index' if custom one (or default 'idx') was not found
            if self.idx_column_name == 'idx': # Only try 'index' if default 'idx' failed
                current_idx_val = row_dict.get('index')

            if current_idx_val is None:
                raise ValueError(
                    f"Strategy requires an index column (tried '{self.idx_column_name}' and 'index') in row_dict. "
                    f"Please ensure your input DataFrame to the backtester has its index available as a column "
                    f"with one of these names, or specify 'idx_column_name' in strategy_params."
                )
        
        try:
            current_idx = int(current_idx_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Index column value (key: '{self.idx_column_name}' or 'index', value: {current_idx_val}) must be convertible to int.") from e

        df_row = pd.Series(row_dict)
        # df_row.name = current_idx # Optional: set if other parts of your strategy might use df_row.name

        num_stats_before = len(self.stats_dict)
        
        self.lift_act(df_row, current_idx) # Core logic execution
        
        num_stats_after = len(self.stats_dict)
        
        action_taken_this_tick = (num_stats_after > num_stats_before)
        
        activity_flag = 0
        execution_price = None
        
        if action_taken_this_tick:
            activity_flag = 1 # Indicates an action was taken
            last_action_stat = self.stats_dict[-1] # Assumes stats_dict is appended sequentially
            execution_price = last_action_stat.get('price_level')
            
        return execution_price, activity_flag
