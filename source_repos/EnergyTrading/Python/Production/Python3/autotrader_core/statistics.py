#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Module with the functions used to calculate various statistics values """
from __future__ import absolute_import
import collections
import itertools

import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_lib.util as ALTU
from six.moves import range
from six.moves import zip


def _regions_generator(trades, exchange_id):
    """generator yielding a trades regions together with the trade given an exchange id"""
    for trade in trades:
        regions = ALTU.get_regions(sell_delivery_area=trade.sell_delivery_area,
                                   buy_delivery_area=trade.buy_delivery_area, exchange_id=exchange_id)
        for region in regions:
            yield trade, region


def calculate_volume_weighted_average_price(trades, exchange_id):
    """calculates vwap for the given trades and exchange id"""
    quantity_pub = collections.defaultdict(float)
    quantity_own = collections.defaultdict(float)
    weighted_quantity_pub = collections.defaultdict(float)
    weighted_quantity_own = collections.defaultdict(float)
    for trade, region in _regions_generator(trades, exchange_id):
        if isinstance(trade, APITR.PublicTrade):
            quantity_pub[region] += trade.quantity
            weighted_quantity_pub[region] += trade.price * trade.quantity
        else:
            quantity_own[region] += trade.quantity
            weighted_quantity_own[region] += trade.price * trade.quantity

    assert list(quantity_pub.keys()) == list(weighted_quantity_pub.keys())
    assert list(quantity_own.keys()) == list(weighted_quantity_own.keys())
    weighted_price = {}
    for owner, quantity, weighted_quantity in zip(["pub", "own"], [quantity_pub, quantity_own],
                                                  [weighted_quantity_pub, weighted_quantity_own]):
        for region in quantity:
            if quantity[region] == 0:
                continue
            weighted_price["vwap_{}_{}".format(owner, region)] = round(weighted_quantity[region] / quantity[region], 2)
    return weighted_price


def calculate_statistics_for_trades(trades, exchange_id):
    """calculates the trade statistics for given trades and exchange id"""
    date_format = "%Y-%m-%dT%H:%M:%S.%f"
    vol_zone_pub = collections.defaultdict(float)
    vol_zone_own = collections.defaultdict(float)
    high_price_zone = collections.defaultdict(lambda: -20000.)
    low_price_zone = collections.defaultdict(lambda: 20000.)
    last_price = collections.defaultdict(lambda: -20000.)
    last_quantity = collections.defaultdict(lambda: -20000.)
    default_date = ALTU.convert_from_timestamp(0, date_format)
    last_trade_time = collections.defaultdict(lambda: default_date)
    for trade, region in _regions_generator(trades, exchange_id):
        if isinstance(trade, APITR.PublicTrade):
            vol_zone_pub["traded_volume_pub_{}".format(region)] += trade.quantity
        else:
            vol_zone_own["traded_volume_own_{}".format(region)] += trade.quantity
        high_price_zone["high_price_{}".format(region)] = max(
            high_price_zone["high_price_{}".format(region)], trade.price)
        low_price_zone["low_price_{}".format(region)] = min(
            low_price_zone["low_price_{}".format(region)], trade.price)
        # the execution_time of a trade is saved as int in the trade object.
        exec_time = ALTU.convert_from_timestamp(trade.execution_time, date_format)
        if last_trade_time["last_trade_time_{}".format(region)] < exec_time:
            last_price["last_price_{}".format(region)] = trade.price
            last_quantity["last_quantity_{}".format(region)] = trade.quantity
            last_trade_time["last_trade_time_{}".format(region)] = exec_time
    for key, value in low_price_zone.items():
        if value == 20000.:
            low_price_zone[key] = None
    for key, value in high_price_zone.items():
        if value == -20000.:
            high_price_zone[key] = None

    statistics = vol_zone_pub
    statistics.update(vol_zone_own)
    statistics.update(high_price_zone)
    statistics.update(low_price_zone)
    statistics.update(last_trade_time)
    statistics.update(last_quantity)
    statistics.update(last_price)

    return statistics


def _calculate_value_sum(ind_index, product, area, dir_index):
    """calculate the volume sum taking into account missing values and the index range"""
    value_sum = 0.
    for i in range(ind_index + 1):
        try:
            value = (product.orders.indicators(area)[0].eur_quantities[dir_index][i])
        except IndexError:
            value = 0.
        value_sum += value
    return value_sum


def calculate_indicators_data(products, areas, amount_indexes_to_serialize, timestamp):
    """Calculate the indicators' data for selected products given areas and amount of indexes."""
    indicators_data = {}
    iter_object = itertools.product(products, amount_indexes_to_serialize, areas,
                                    enumerate((COMMON.Direction.buy, COMMON.Direction.sell)))
    for product, ind_index, area, (dir_index, direction) in iter_object:
        key = "ind_{}_{}_{}".format(area, ind_index, direction)
        if product.state(area) == COMMON.DeliveryAreaState.inactive or \
                (timestamp is not None and timestamp > product.delivery_start):
            # The inactive check is for local vs xbid products: Only one of them can be active at a time.
            # Additionally, we check by delivery start, because we delete the orderbook at delivery start,
            # but the product is not always set to inactive at delivery start.
            if key not in list(indicators_data.keys()):
                indicators_data[key] = None
        else:
            value_sum = _calculate_value_sum(ind_index, product, area, dir_index)
            if key in indicators_data and value_sum == 0. and indicators_data[key] is not None:
                continue
            indicators_data[key] = value_sum

    return indicators_data


def calculate_price_indicators(products, areas, timestamp):
    """calculates the price indicators for the products given areas"""
    price_indicators = {}
    iter_object = itertools.product(products, areas, enumerate((COMMON.Direction.buy, COMMON.Direction.sell)))
    for product, area, (dir_index, direction) in iter_object:
        # we only want the spread (0eur index for buy and sell)
        indicator_index = 0
        key = "pr_ind_{}_{}_{}".format(area, indicator_index, direction)
        if product.state(area) == COMMON.DeliveryAreaState.inactive or \
                (timestamp is not None and timestamp > product.delivery_start):
            if key not in price_indicators:
                price_indicators[key] = None
        else:
            try:
                value = (product.orders.indicators(area)[0].mw_prices[dir_index][indicator_index])
            except IndexError:
                continue
            if key in price_indicators and value is None:
                continue
            price_indicators[key] = value

    return price_indicators


def calculate_pnl(prices, quantities, buy_delivery_areas, sell_delivery_areas, time_delta):
    """Helper function calculating the pnl doing the right directions and the right unit scaling"""
    if time_delta <= 0:
        raise ValueError("Time delta should not be negative or zero in this context")
    scaling_factor = time_delta / float(COMMON.HOUR)

    total_sum = 0
    for price, qty, buy_del_area, sell_del_area in zip(prices, quantities, buy_delivery_areas, sell_delivery_areas):
        direction = 1. if buy_del_area == "" else -1.  # if buy delivery area is empty we are selling
        scaled_quantity = qty * scaling_factor * direction
        total_sum += scaled_quantity * price

    return total_sum
