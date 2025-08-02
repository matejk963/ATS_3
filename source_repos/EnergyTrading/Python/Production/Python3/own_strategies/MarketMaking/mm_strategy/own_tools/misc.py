import autotrader_lib.common as COMMON
from .instrument_key import InstrumentKey

def api_export_trade(self, trade):

    if trade.direction == 'sell':
        direction = COMMON.Direction.sell
        instrument_id = trade.sell_delivery_area
    else:
        direction = COMMON.Direction.buy
        instrument_id = trade.buy_delivery_area
    product_id = trade.product.product_id
    instrument_key = InstrumentKey(instrument_id, product_id).key

    export_dict = {
    'trade_id': trade.trade_id,
    'datetime': trade.execution_time,
    'algo_id':  self.strategy_id,
    'price':    trade.price,
    'quantity': trade.quantity,
    'side':     trade.direction,
    'init_aggress':     'agg' if trade.aggressor=='Y' else 'init',
    'inst_key': instrument_key,
    'broker_id': trade.aggressor_broker_id if trade.aggressor=='Y' else trade.initiator_broker_id

    }
    self.debug_log(
        "[{}] api_export_trade called on trade with ID: [{}]".format(
        self.strategy_id, trade.trade_id ))

    self.api_export_timeseries({
        "trades": ("Trades of algo strategy", "MW", "MW", COMMON.HOUR, {self.timestamp+3600*self.trade_counter: export_dict})}
    )

def round_to_tick(number, tick_size):
    # Step 1: Divide by tick size
    number_in_ticks = number / tick_size
    
    # Step 2: Round to nearest whole number
    rounded_ticks = round(number_in_ticks)
    
    # Step 3: Multiply back by tick size
    return rounded_ticks * tick_size

def max_with_none_check(d):
    # Filter out items where the value is None, then find the max based on remaining items' values
    filtered_d = {k: v for k, v in d.items() if v is not None}
    if not filtered_d:  # Check if the dictionary becomes empty after filtering
        return None, None  # Return None for both key and value if no suitable item is found
    max_key = max(filtered_d, key=filtered_d.get)
    return max_key, filtered_d[max_key]

def min_with_none_check(d):
    # Filter out items where the value is None, then find the min based on remaining items' values
    filtered_d = {k: v for k, v in d.items() if v is not None}
    if not filtered_d:  # Check if the dictionary becomes empty after filtering
        return None, None  # Return None for both key and value if no suitable item is found
    min_key = min(filtered_d, key=filtered_d.get)
    return min_key, filtered_d[min_key]