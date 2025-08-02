# -*- coding: utf-8 -*-

"""
This strategy allows placement, modification and deletion of orders.

The strategy reacts to steering messages holding a "manual_order" object. The three operations implemented
by this strategy can be accessed as follows:

Order creation
===============
request = {
    "manual_order": {
        "operation": "create",
        "product_id": "the product id to place an order for", # required.
        "price": 123.45, # required. floating point price in euro
        "quantity": 123.45, # required. floating point quantity in MW
        "buy": true, # required. ... or false for sell
        "delivery_area": "10YAT-APG------L", # required.
        "text": "free text to place in the stats field" # optional.
    }
}

response = {
    "status": "OK",
    "slot_id": "the slot id of the newly created order",
}

Order creation returns the slot ID of the newly created order. This ID, along with the product id, has to be passed
into potential subsequent modify and delete calls.
Return of order creation:


Order modification
===================
request = {
    "manual_order": {
        "operation": "modify",
        "slot_id": "your slot id", # mandatory to identify the order.
        "product_id": "the product the order was placed for", # mandatory to identify the order.
        "price": 123.45, # optional. floating point price in Euro. Only include if you want to change it.
        "quantity": 123.45, # optional. floating point quantity in MW. Only include if you want to change it.
        "text": "free text to place in the stats field" # optional. Only include if you want to change it.
    }
}

response = {
    "status": "OK",
}

Order deletion
===============
request = {
    "manual_order": {
        "operation": "delete",
        "slot_id": "your slot id here", # mandatory to identify the order.
        "product_id": "the product the order was placed for" # mandatory to identify the order.
    }
}

response = {
    "status": "OK",
}

Error responses
================
If any error happens while processing the request, the "status" attribute of the response will be set to "ERROR".
The "msg" field provides further details.

"""


import logging
import numbers
import time

import autotrader_core.strategy as strategy
import autotrader_lib.common as COMMON

log = logging.getLogger('autotrader.manual_trading_strategy')

_id_generator = COMMON.UniqueIDGenerator()


def _create_error_response(msg):
    """Create an error response dictionary with the given message"""
    return dict(status="ERROR", msg=msg)


def _create_ok_response(**kwargs):
    """Create a success response dictionary"""
    return dict(status="OK", **kwargs)


class _ManualTradingCommandBase(object):
    """Base class for one of the possible commands the strategy handles. Implements common tasks such as validation."""

    mandatory_fields = []
    invalid_fields = []
    mifid_fields_name = ["decision_maker", "execution_maker", "liquidity_provision",
                         "dea", "dea_client_id", "trading_capacity", "derivative_indicator"]

    def __init__(self, strategy_obj, manual_order):
        """

        :param strategy_obj: The strategy object owning this command object
        :type strategy_obj: strategy.Strategy
        :param manual_order: The parsed JSON data sent to the strategy
        :type manual_order: dict[str, any]
        """
        self._strategy = strategy_obj
        self._manual_order = manual_order
        self._error_response = None

    def _validate(self):
        """Checks that the command has all mandatory fields, and no additional fields are present.

        Sets self.error_response on error.

        :return: A boolean success status
        :rtype: tuple(bool, dict[str, Any])
        """
        missing_mandatory_fields = [f for f in self.mandatory_fields if f not in self._manual_order]
        if missing_mandatory_fields:
            self._error_response = _create_error_response(
                "Missing mandatory field(s): {}".format(",".join(missing_mandatory_fields)))
            return False

        if not self._strategy.exchange.init_files_ready():
            self._error_response = _create_error_response("The exchange is not yet initialized")
            return False

        if self._strategy.exchange.halted:
            self._error_response = _create_error_response("The exchange is halted")
            return False

        if self._strategy.autotrader.halted:
            self._error_response = _create_error_response("Autotrader is halted")
            return False

        if self._strategy.halted:
            self._error_response = _create_error_response("This strategy is halted")
            return False

        if not self._strategy.active and self._manual_order["operation"] != "delete":
            self._error_response = _create_error_response("This strategy is not active")
            return False

        invalid_fields = [f for f in self.invalid_fields if f in self._manual_order]
        if invalid_fields:
            self._error_response = _create_error_response("Invalid field(s) for "
                                                          "operation {}: {}".format(self._manual_order["operation"],
                                                                                    ",".join(invalid_fields)))
            return False
        if "price" in self._manual_order and not isinstance(self._manual_order["price"], numbers.Number):
            self._error_response = _create_error_response("price must be a number")
            return False
        if "quantity" in self._manual_order and not isinstance(self._manual_order["quantity"], numbers.Number):
            self._error_response = _create_error_response("quantity must be a number")
            return False
        if "text" in self._manual_order:
            try:
                # Non-ascii characters can cause a critical halt of autoTRADER.
                try:
                    self._manual_order["text"].decode("ascii")
                except AttributeError:  # In Python3 string has no decode attribute
                    pass
            except UnicodeError:
                self._error_response = _create_error_response("Text field contains non-ASCII characters")
                return False

        return True

    @staticmethod
    def _get_timestamp():
        """Get the timestamp to use in the place_slots call"""
        return time.time()

    def _get_product(self):
        """Get the product the manual order data is referencing"""
        product_id = self._manual_order.get("product_id", "")
        try:
            product = self._strategy.exchange.products.get_by_id(product_id)
        except COMMON.ProductNotFound:
            product = None
        return product

    @staticmethod
    def _find_order(product, slot_id):
        """
        Find an order by its slot id

        :param product: the product the order is for
        :type product: autotrader_core.exchange_trading.Product
        :param slot_id: The id assigned to the slot
        :type slot_id: str
        :return: the order matching the given ids
        :rtype: autorader_core.exchange_trading.OwnOrder
        """
        own_orders = product.orders.get(order_filter=COMMON.OrderFilter.own)
        for order in own_orders:
            if order.tags.get("strategy_slot", "") == slot_id:
                return order
        return None

    def validate_and_run(self):
        """Validate and run the command.

        :return: The return value to be returned through the API
        :rtype: dict[str, Any]
        """
        valid = self._validate()
        if valid:
            product = self._get_product()
            if product:
                ret = self._run(product)
            else:
                ret = _create_error_response("Product not found")
        else:
            if self._error_response:
                ret = self._error_response
            else:
                ret = _create_error_response("Unknown validation error")

        return ret

    def _run(self, product):
        """Execute the given command and return an appropriate response."""
        raise NotImplementedError()

    def place_slot(self, slot, product, delivery_area, stat):
        if stat:
            stats = [stat]
        else:
            stats = None
        response = self._strategy.place_slots({}, product, self._get_product(), delivery_area, [slot], stats=stats)[0]
        if response:
            return _create_ok_response()
        else:
            return _create_error_response("The order was {} for the following reason: {}".format(response.action,
                                                                                                 response.reason))


class _CreateOrderCommand(_ManualTradingCommandBase):
    """Place a new slot"""
    mandatory_fields = ["product_id", "buy", "quantity", "price", "delivery_area"]
    invalid_fields = ["slot_id"]

    def _run(self, product):
        direction = COMMON.Direction.buy if self._manual_order["buy"] else COMMON.Direction.sell
        slot_id = _id_generator.get_uid()
        terms = self._manual_order.get("terms")
        kwargs = {key: self._manual_order.get(key) for key in self.mifid_fields_name}
        kwargs.update({"terms": terms})
        slot = strategy.PositionSlot(
            slot_id,
            direction,
            self._manual_order["quantity"],
            self._manual_order["price"],
            broker_id=self._manual_order.get("broker_id"),
            tick_size=0.001,
            trading_account=self._manual_order.get("trading_account", ""),
            execution_restriction=self._manual_order.get("execution_restriction", COMMON.ExecutionRestriction.non),
            **kwargs)
        stat = self._manual_order.get("text", "")
        response = self.place_slot(slot, product, self._manual_order["delivery_area"], stat)
        if response["status"] == "OK":
            response["slot_id"] = slot_id
        return response

    def _validate(self):
        if not super(_CreateOrderCommand, self)._validate():
            return False
        if not isinstance(self._manual_order["buy"], bool):
            self._error_response = _create_error_response("'buy' Flag must be of boolean type")
            return False

        delivery_area_id = self._manual_order["delivery_area"]
        if self._strategy.exchange.internal_id == COMMON.Exchange.trayport:
            if delivery_area_id not in self._strategy.exchange.trayport_areas:
                self._error_response = _create_error_response("Unsupported area: {}".format(repr(delivery_area_id)))
                return False
            product = self._get_product()
            if product and delivery_area_id not in list(product.delivery_area_states.keys()):
                self._error_response = _create_error_response("Area: {} is not supported for product: "
                                                              "{}".format(delivery_area_id,
                                                                          self._manual_order["product_id"]))
                return False
            # Note: The broker_id is checked inside place_slots, so no check is needed here.
        else:
            exchange_from_area = COMMON.Area.get_exchanges(delivery_area_id)
            if self._strategy.exchange.internal_id not in exchange_from_area:
                self._error_response = _create_error_response("Unsupported area: {}".format(delivery_area_id))
                return False
        return True


class _ModifyOrderCommand(_ManualTradingCommandBase):
    """Modify an existing slot"""
    mandatory_fields = ["product_id", "slot_id"]
    invalid_fields = ["delivery_area", "broker_id", "buy", "execution_restriction"]
    invalid_fields += _ManualTradingCommandBase.mifid_fields_name
    invalid_fields.append("terms")

    def _run(self, product):
        slot_id = self._manual_order["slot_id"]
        order = self._find_order(product, slot_id)
        log.debug("dictionary : {}".format({key: self._manual_order.get(key) for key in self.mifid_fields_name}))
        if not order:
            return _create_error_response("Order {} for product {} not found".format(slot_id, product.product_id))
        elif (self._manual_order.get("quantity", order.quantity) == order.quantity
              and self._manual_order.get("price", order.price) == order.price):
            return _create_error_response("Order Modifications must change at least "
                                          "one of price and quantity.")
        else:
            slot = strategy.PositionSlot(
                slot_id,
                order.direction,
                self._manual_order.get("quantity", order.quantity),
                self._manual_order.get("price", order.price),
                broker_id=order.broker_id,
                tick_size=0.001,
                trading_account=self._manual_order.get("trading_account", order.trading_account),
            )
            stat = self._manual_order.get("text", order.tags["stats"])

            return self.place_slot(slot, product, order.delivery_area_id, stat)


class _DeleteOrderCommand(_ManualTradingCommandBase):
    """Delete an existing slot (i.e. set quantity to zero)"""
    mandatory_fields = ["product_id", "slot_id"]
    invalid_fields = ["direction", "delivery_area", "price", "quantity", "text", "broker_id", "trading_account"]

    def _run(self, product):
        slot_id = self._manual_order["slot_id"]
        order = self._find_order(product, slot_id)

        if not order:
            return _create_error_response("Order {} for product {} not found".format(slot_id, product.product_id))
        else:
            slot = strategy.PositionSlot(
                slot_id,
                order.direction,
                0.,
                order.price,
                broker_id=order.broker_id,
            )

            return self.place_slot(slot, product, order.delivery_area_id, None)


class CustomStrategy(strategy.Strategy):
    """This strategy executes manual trading commands."""

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self._trading_commands = dict(
            create=_CreateOrderCommand,
            modify=_ModifyOrderCommand,
            delete=_DeleteOrderCommand
        )

    def on_strategy_update(self, strategy_json):
        """
        Main function for this strategy. Parses the JSON and creates/modifies/deletes orders as requested

        :param strategy_json: The control data to act on. Should contain a "manual_order" object (see class doc).
        :type strategy_json: dict[str, any]
        :return: The data to send back to the caller
        :rtype: dict[str, any]
        """
        manual_order = strategy_json.pop("manual_order", None)
        if manual_order:
            operation = manual_order["operation"]

            if operation in self._trading_commands:
                cmd = self._trading_commands[operation](self, manual_order)
                return cmd.validate_and_run()
            else:
                return _create_error_response("Invalid operation for manual trading strategy: {}".format(operation))
        else:
            return super(CustomStrategy, self).on_strategy_update(strategy_json)
