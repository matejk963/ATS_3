import numpy as np
from datetime import datetime, time, timedelta
import pytz
import logging
import math
import time as tm


def calculate_dti_time(trades, interval='300s'):
    # --- Parse interval ---
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == 's':
        interval_seconds = value
    elif unit == 'm':
        interval_seconds = value * 60
    elif unit == 'h':
        interval_seconds = value * 3600
    else:
        raise ValueError("Unsupported interval format. Use 's', 'm', or 'h' suffix.")

    if not trades:
        return None

        # --- Filter trades within the time window ---
    now = max([t['execution_time'] for t in trades])  # datetime.utcnow().timestamp()
    start_time = now - interval_seconds
    recent_trades = [
        (t['price'], t['quantity'], t['execution_time'])
        for t in trades
        if start_time < t['execution_time'] <= now
    ]
    if not recent_trades:
        return None

    # --- Aggregate trades with same timestamp using VWAP ---
    trade_dict = {}  # timestamp -> (sum_price_qty, sum_qty)
    for price, qty, ts in recent_trades:
        if ts not in trade_dict:
            trade_dict[ts] = [price * qty, qty]
        else:
            trade_dict[ts][0] += price * qty
            trade_dict[ts][1] += qty

    # Convert to list of (timestamp, vwap_price)
    aggregated = [(ts, total / qty) for ts, (total, qty) in trade_dict.items()]
    aggregated.sort()  # sort by timestamp

    if len(aggregated) < 2:
        return None

    # --- Calculate DTI ---
    open_price = aggregated[0][1]
    close_price = aggregated[-1][1]
    direction = math.copysign(1, close_price - open_price) if close_price != open_price else 0

    # Count number of price changes
    unique_prices = 0
    last_price = None
    for _, price in aggregated:
        if price != last_price:
            unique_prices += 1
            last_price = price

    dti = direction * unique_prices / interval_seconds
    return dti