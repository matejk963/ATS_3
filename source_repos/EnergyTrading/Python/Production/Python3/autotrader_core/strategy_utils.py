# coding: utf-8

from __future__ import absolute_import

import autotrader_lib.common as COMMON
import six


PREC_DIGITS = 8


class LastPriceNotFoundError(Exception):
    pass


def max_or_none(sequence):
    """
    Returns None if any value of x is None and the maximum otherwise

    :type sequence: list
    """
    return None if None in sequence else max(sequence)


def min_or_none(sequence):
    """
    Returns None if any value of x is None and the minimum otherwise

    :type sequence: list
    """
    return None if None in sequence else min(sequence)


def get_value_or_zero(value):
    """Function that changes None to zero"""
    return value or 0.


def log_locals(locals):
    """ Convert a dictionary to a string while ignoring all non-simple value types.

    :param locals: The dict to convert, usually the result of locals()
    :type locals: dict
    :return: A string representation
    :rtype: str
    """
    return ", ".join(["{}: {}".format(six.text_type(key), six.text_type(value)) for key, value in locals.items() if
                      isinstance(value, (str, six.text_type, float, int, int, type(None)))])


def get_trades_for_product(product, area, slot_name, strategy_id):
    """
    Get list of trades for one (synthetic) product.

    :param product: Target product object
    :type product: autotrader_core.exchange_trading.Product
    :param area: Target Area code
    :type area: str
    :param slot_name: Target slot name
    :type slot_name: str
    :param strategy_id:
    :type strategy_id: str
    :rtype: list[autotrader_core.exchange_trading.Trade]
    """
    trades = product.trades.get(trade_filter=COMMON.TradeFilter.own,
                                portfolio_key=strategy_id,
                                delivery_area=area)
    trades = [t for t in trades if t.tags.get("strategy_slot", "") == slot_name]
    trades.sort(key=lambda t: t.execution_time)
    return trades


def get_last_price_by_slot(exchange, base_product, area, slot_name, strategy_id):
    """
    Gets last traded price for target product.

    :param exchange: Trayport exchange object
    :type exchange: autotrader_core.exchanges.Trayport
    :param base_product: Target product to retrieve last price from
    :type base_product: autotrader_core.exchange_trading.Product
    :param area: Target Area code
    :type area: str
    :param slot_name: Target slot name
    :type slot_name: str
    :param strategy_id: Target strategy id
    :type strategy_id: str
    :return: Last traded price if there was a trade today
    :rtype: float or None
    """

    if base_product.product_type == "WD":
        # For WithinDay we need to iterate over past synthetic products.
        # This also finds other product types with matching delivery_end.
        delivery_start = base_product.delivery_end - COMMON.DAY - COMMON.HOUR  # 25h because of leap years
        products = exchange.products.get_by_timerange(delivery_start, base_product.delivery_end)
        products = [p for p in products if p.delivery_end == base_product.delivery_end]
        products.sort(key=lambda p: p.delivery_start, reverse=True)
    else:
        # For the rest we only care about the base_product itself, since there no overlapping dummy products
        # considering delivery period.
        products = [base_product]

    for product in products:
        trades = get_trades_for_product(product, area, slot_name, strategy_id)
        if trades:
            return trades[-1].price


def immediate_vesting(product, area, direction, immediate_execution_price, depth, cap_quantity):
    """ Check in the order book if an immediate vesting is possible

    If direction is sell, we would be placing a buy order therefore the immediate_execution_price parameter is the price
    on the buy side and vice versa
    :param product: Product for immediate vesting
    :type product: autotrader_core.exchange_trading.Product
    :param area: Area from COMMON.Area
    :type area: str
    :param direction: "sell" or "buy", to check for immediate execution
    :type direction: str
    :param immediate_execution_price: of the opposite side of "direction"
    :type immediate_execution_price: float
    :param depth: of the orderbook we want to have a look at (i.e first 5 * depth MW)
    :type depth: float
    :param cap_quantity: volume cap quantity
    :type cap_quantity: float
    :return: the price and volume of the slot to create on the other direction
    :rtype: (int, int) or (None, None) if there is not enough volume in the orderbook
    """
    index_direction = 0 if direction == "buy" else 1
    direction_factor = 1 if direction == "buy" else -1
    quantity, price = 0, 0
    indicators = product.orders.indicators(area)
    # if there is not enough volume, returns None or no indicators
    if not indicators or indicators[0].mw_prices[index_direction][depth] is None:
        return None, None

    front_order_price = indicators[0].mw_prices[index_direction][0]
    if direction_factor * front_order_price >= direction_factor * immediate_execution_price:
        front_order_quantity = indicators[0].eur_quantities[index_direction][0]
        quantity = round(min(front_order_quantity, cap_quantity), 0)
        price = front_order_price

    return quantity, price


def truncate(qty, digits):
    """cut quantity to floor of digits

    Example:
    truncate(qty=50.0345, digits=3) == 50.034

    :type qty: float
    :type digits: float
    :rtype: float
    """
    return int((qty * (10 ** digits)) // 1) / (10 ** digits)


def stepsize_rounder(price, stepsize):
    """round to the closes stepsize

    Example:
    stepsize_rounder(price=50.03, stepsize=0.025) == 50.025

    :type price: float
    :type stepsize: float
    :rtype: float
    """
    return round(round(float(price) / stepsize) * stepsize, PREC_DIGITS)


def load_rounder(qty, min_amount, step_size, digits=PREC_DIGITS, max_amount=None):
    """
    round quantity down to a value allowed by the instrument properties (min_amount and step_size)

    :param qty: quantity to be rounded
    :type qty: float
    :param min_amount: minimum amount, any amount under this is rounded to 0
    :type min_amount: float
    :param step_size: step size. If qty is bigger than min_amount, it is rounded down to the next value
                      of the form min_amount + n * step_size (where n is an integer)
    :type step_size: float
    :param digits: rounding digits
    :type digits: int
    :param max_amount: highest possible amount. WARNING: This must fit the step_size!
    :type max_amount: float
    :return: rounded quantity
    :rtype: float
    """
    assert step_size >= 0, "step_size cannot be negative"
    assert min_amount >= 0, "min_amount cannot be negative"

    if qty >= min_amount:
        to_trade = min_amount
        left_over = qty - min_amount
        if step_size > 0:
            to_trade += int(left_over // step_size * step_size)
        if max_amount is not None:
            to_trade = min(to_trade, max_amount)
        return truncate(to_trade, digits)
    else:
        return 0


def merge_overlapping(intervals):
    """Merge overlapping intervals of 2 numbers

    there must! be an overlap between intervals. The same start/end time is not enough to merge them
    the entered intervals do not need to be sorted, because this function sorts them before merging

    Example:
    [(1,5), (3, 10), (20, 40)] =>  [[1, 10], [20, 40]]

    :param intervals: list of pairs of 2 sorted numbers
    :type intervals: list[tuple[float]]
    :return: merged intervals
    :rtype: list[list[float]]
    """
    out = []
    for i in sorted(intervals, key=lambda i: i[0]):
        if out and i[0] < out[-1][1]:
            out[-1][1] = max(out[-1][1], i[1])
        else:
            out += list(i),
    return out
