#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import logging
import autotrader_core.api as API
import autotrader_core.exchange_trading as APITR
import autotrader_lib.common as COMMON
import autotrader_core.simulation_data
import copy


log = logging.getLogger('autotrader.nasty_orders_generator')


class FixedNastyOrderGenerator(object):

    """
    This Class generates public orders right in front of your simulated order to test OTR behavior.
    It can be considered a stress test for the strategy to be tested.
    To be used with `simulation_definition_executor.simulate`.
    """

    def __init__(self, front_shift, quantity):
        """
        :param front_shift: How far away the nasty order is from the own order.
        :type front_shift: float
        :param quantity: Nasty order quantity
        :type quantity: float
        """
        self.front_shift = front_shift
        self.quantity = quantity

    def generate_messages(self, autotrader, product, area, exchange_id, timestamp):
        # type: (API.AutoTrader, APITR.Product, str, str, int) -> list[dict[str, any]]

        order_mods = []
        nasty_name_start = "NASTY" + str(id(self))
        nasty_public_orders = dict((nasty.order_id, nasty) for nasty in
                                   product.orders.get(area, COMMON.OrderFilter.public) if
                                   nasty.order_id.startswith(nasty_name_start))
        # iterate through Own Orders in product and generate a public order
        for own_order in product.orders.get(area, COMMON.OrderFilter.own):
            if not hasattr(own_order, "order_id"):
                # new orders in book don't have an order_id
                continue
            nasty_name = nasty_name_start + "_" + own_order.order_id
            shift = self.front_shift if own_order.direction == COMMON.Direction.buy else -self.front_shift
            nasty_price = own_order.price + shift
            # produce an update for that public order
            mod_order = copy.deepcopy(own_order)
            mod_order.order_id = nasty_name

            simulation_data = autotrader_core.simulation_data.SimulationDataPublicOrder(mod_order, nasty_name)
            revision = product.orders._last_area_revision[mod_order.delivery_area_id]
            simulation_data.update(price=nasty_price, quantity=self.quantity, revision=revision)

            order_mods.append({"data": [simulation_data.data],
                               "message_type": COMMON.Response.order_book,
                               "timestamp": timestamp,
                               "exchange": exchange_id,
                               })
            # remove the nasty order from the list
            nasty_public_orders.pop(nasty_name, None)

        # iterate through all the unaddressed nasty orders and ...
        for key, public_order in nasty_public_orders.items():
            # ... remove those
            mod_order = copy.deepcopy(public_order)
            simulation_data = autotrader_core.simulation_data.SimulationDataPublicOrder(mod_order, key)
            revision = product.orders._last_area_revision[mod_order.delivery_area_id]
            simulation_data.update(quantity=0., revision=revision)
            order_mods.append({"data": [simulation_data.data],
                               "message_type": COMMON.Response.order_book,
                               "timestamp": timestamp,
                               "exchange": exchange_id,
                               })

        return order_mods
