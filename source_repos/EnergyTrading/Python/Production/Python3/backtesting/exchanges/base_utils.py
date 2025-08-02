"""
Util Classes for:
 - Generating JSON Feeds for simulations
 - Checking Simulation Results (via MongoDB) for details on trading history about orders and trades

product messages are built based on the timeline shown for products on 2019-11-25 between 12:00-13:00
"""
from __future__ import absolute_import
from __future__ import print_function
import collections
import datetime
import itertools
import json
import os
import types as T

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as ALCU
import autotrader_lib.util as ALU
import backtesting.exchanges.epex.prepare_backtesting_builder_maps_to_product_msg as PROD_MSG
import backtesting.strategy_definition as SD
import backtesting.synchronous_backtesting_utils as SBU
from six.moves import zip


def own_strategies_dir():
    return os.path.join(os.path.abspath(os.path.join(__file__, "../../..")), "own_strategies")


# types for strategy generator
SimuProductDefinition = collections.namedtuple("SimuProductDefinition", ["delivery_start", "delivery_end",
                                                                         "product_id_local", "product_id_xbid"])

# types for json feed generation
OrderDefinition = collections.namedtuple("OrderDefinition", ["direction", "product_id", "price", "quantity",
                                                             "delivery_area", "timestamp", "order_id"])
BoxedOrderDefinition = collections.namedtuple("BoxedOrderDefinition", ["direction", "product_id", "price_start",
                                                                       "price_end", "quantity_start", "quantity_end",
                                                                       "delivery_area", "timestamp_from",
                                                                       "timestamp_to", "order_id"])
TradeDefinition = collections.namedtuple("TradeDefinition", ["direction", "quantity", "price", "order_id",
                                                             "delivery_area", "trade_id", "user", "txt", "product_id",
                                                             "aggressor", "execution_time", "state"]
                                         )

CutoverDef = collections.namedtuple("CutoverDef", ["first_local_to_xbid", "second_xbid_to_local", "third_local_close"])

# types for evaluation
OrderInfoTuple = collections.namedtuple("orderinfo", ["quantity", "direction", "start_timestamp", "end_timestamp",
                                                      "price", "own_public", "order_id", "slot_type",
                                                      "trading_portfolio"])

OrderInfo = collections.namedtuple("OrderInfo", ["price", "quantity", "direction", "delivery_area_id", "portfolio_key",
                                                 "start_timestamp", "end_timestamp", "product_id"])


class IdGenerator(object):
    """Class to automatically generate unique incremental product and order ids

    used for generated products and orders in the json feed

    Because each exchange has their own way to create product and order ids,
    each exchange needs to make their own IdGenerator, e.g. EpexIdGenerator
    """

    def __init__(self):
        self.product_id_counter = itertools.count(0, 1)
        self.order_id_counter = itertools.count(0, 1)
        self.order_revision_counter = collections.defaultdict(itertools.count)
        self.trade_revision_counter = collections.defaultdict(itertools.count)

    def next_order_revision(self, order_id):
        # type: (T.Union[int, str]) -> int
        return next(self.order_revision_counter[order_id])

    def next_trade_revision(self, trade_id):
        # type: (T.Union[int, str]) -> int
        return next(self.trade_revision_counter[trade_id])

    def next_prod_id(self):
        # type: () -> any
        return self._get_next_product_id()

    def next_order_id(self):
        # type: () -> any
        return self._get_next_order_id()

    def _get_next_product_id(self):
        # type: () -> int
        return self._int2product_id(next(self.product_id_counter))

    def _get_next_order_id(self):
        # type: () -> int
        return self._int2order_id(next(self.order_id_counter))

    @staticmethod
    def _int2order_id(number):
        # type: (int) -> T.Union[int, str]
        raise NotImplementedError("Need to implement _int2order_id")

    @staticmethod
    def _int2product_id(number):
        # type: (int) -> T.Union[int, str]
        raise NotImplementedError("Need to implement _int2product_id")


class SimuGenerator(object):
    """Generator class to produce json feed for simulation tests"""

    def __init__(self, exchange, id_gen):
        # type: (str, IdGenerator) -> None
        self.id_gen = id_gen
        self.exchange = exchange
        self.msgs = []

    def add_product_gb(self, simu_product):
        # type: (SimuProductDefinition) -> SimuGenerator
        ALU.duration_check(simu_product.delivery_start, simu_product.delivery_end)

        gb_msgs = PROD_MSG.generate(simu_product.delivery_start, simu_product.delivery_end,
                                    PROD_MSG.PRODUCT_TYPE_FILTER.uk, simu_product.product_id_xbid)

        gb_msgs.sort(key=lambda x: x["timestamp"])

        self.msgs.extend(gb_msgs)

        return self

    def add_product_local_xbid(self, simu_product):
        # type: (SimuProductDefinition) -> SimuGenerator
        ALU.duration_check(simu_product.delivery_start, simu_product.delivery_end)

        local_msgs = PROD_MSG.generate(simu_product.delivery_start, simu_product.delivery_end,
                                       PROD_MSG.PRODUCT_TYPE_FILTER.local, simu_product.product_id_local)
        xbid_msgs = PROD_MSG.generate(simu_product.delivery_start, simu_product.delivery_end,
                                      PROD_MSG.PRODUCT_TYPE_FILTER.xbid, simu_product.product_id_xbid)

        local_msgs.sort(key=lambda x: x["timestamp"])
        xbid_msgs.sort(key=lambda x: x["timestamp"])

        self.msgs.extend(local_msgs)
        self.msgs.extend(xbid_msgs)

        return self

    def add_order(self, order_definiton):
        # type: (OrderDefinition) -> SimuGenerator
        """Adds order_book message"""
        direction = order_definiton.direction
        product_id = order_definiton.product_id

        price = order_definiton.price
        quantity = order_definiton.quantity
        delivery_area = order_definiton.delivery_area
        timestamp = order_definiton.timestamp
        order_id = order_definiton.order_id

        self.msgs.append({"synchronisation_init": False,
                          "exchange": self.exchange,
                          "data": [{"direction": direction,
                                    "product_id": product_id,
                                    "order_id": order_id,
                                    "price": price,
                                    "delivery_area_id": delivery_area,
                                    "quantity": quantity,
                                    "revision": self.id_gen.next_order_revision(order_id)}],
                          "message_type": "order_book",
                          "timestamp": timestamp})

        return self

    def add_boxed_order(self, boxed_order_definiton):
        # type: (BoxedOrderDefinition) -> SimuGenerator
        """Adds order_book messages for initial and final order state"""
        direction = boxed_order_definiton.direction
        product_id = boxed_order_definiton.product_id
        price_start = boxed_order_definiton.price_start
        price_end = boxed_order_definiton.price_end
        quantity_start = boxed_order_definiton.quantity_start
        quantity_end = boxed_order_definiton.quantity_end
        delivery_area = boxed_order_definiton.delivery_area
        timestamp_from = boxed_order_definiton.timestamp_from
        timestamp_to = boxed_order_definiton.timestamp_to
        order_id = boxed_order_definiton.order_id

        self.msgs.extend([
            {"synchronisation_init": False,
             "exchange": self.exchange,
             "data": [{"direction": direction,
                       "product_id": product_id,
                       "order_id": order_id,
                       "price": price,
                       "delivery_area_id": delivery_area,
                       "quantity": quantity,
                       "revision": self.id_gen.next_order_revision(order_id)}],
             "message_type": "order_book",
             "timestamp": timestamp} for price, quantity, timestamp in
            zip([price_start, price_end], [quantity_start, quantity_end], [timestamp_from, timestamp_to])
        ])
        return self

    def add_own_trade_epex(self, trade_definition):
        # type: (TradeDefinition) -> SimuGenerator
        data = {key: getattr(trade_definition, key) for key in trade_definition._fields}
        data["revision"] = self.id_gen.next_trade_revision(trade_definition.trade_id)
        self.msgs.append({
            'message_type': COMMON.Response.own_trade,
            'timestamp': trade_definition.execution_time,
            'exchange': 'EPEX',
            'data': [data]
        })

    def sort(self):
        # type: () -> SimuGenerator
        self.msgs.sort(key=lambda x: x["timestamp"])
        return self

    def export_json(self):
        # type: () -> list
        return json.dumps(self.msgs)

    def export_json_file(self, path):
        # type: (str) -> None
        return json.dump(self.msgs, path)


class EventGenerator(object):
    """
    This class is here to generate events with exchange=Periotheus such as strategy, steering calls, emergency halt etc.
    """

    def __init__(self):
        self._events = []
        self.strategies = {}

    @property
    def events(self):
        """ Return the events sorted by timestamp"""
        return sorted(self._events, key=lambda x: x["timestamp"])

    def create_strategy(self, strategy_parameters, timestamp, **kwargs):
        """ Create a strategy and insert the message in the _events list at a specific timestamp.

        :param strategy_parameters: all the attributes the strategy needs for setup
        :type strategy_parameters: dict
        :param timestamp: the timestamp when to insert the strategy in the events
        :type timestamp: float
        """
        strategy = SD.StrategyDefinition(**strategy_parameters)
        for field, value in kwargs.items():
            strategy.params[field] = value

        # we keep track of the strategy objects just in case we need it later
        self.strategies[strategy.strategy_id] = strategy
        self._events.append(strategy.export(timestamp))

    def steering_call(self, strategy_id, operation, payload, timestamp):
        """ Insert a steering call message into the events list at a certain timestamp"""
        self._events.append(SBU.create_steering_call(
            strategy_id=strategy_id,
            steering_msg={operation: payload},
            timestamp=timestamp
        ))

    def halt(self, timestamp, is_halted=True, remove_orders=True, exchange_id=None):
        """ Insert a emergency halt message into the events list at a certain timestamp

        :param timestamp: when to insert the message in the events list
        :type timestamp: float
        :param is_halted: the halt state to set on the autotrader
        :type is_halted: bool
        :param remove_orders: True if we should also remove the orders, False otherwise
        :type remove_orders: bool
        :param exchange_id: the exchange to halt or None if we want to stop the autotrader itself
        :type exchange_id: str or None
        """
        self._events.append(SBU.create_halt_message(timestamp, is_halted, remove_orders, exchange_id))

    def pretty(self):
        """ Prints the messages in the events with some specific handling according to the message type"""
        for event in self.events:
            message_type = event.get("message_type")
            if message_type == "strategy":
                # we don't want to show the timeseries of the strategies
                for strategy in event["data"]["strategy_objects"]:
                    to_print = {
                        strategy: {
                            field: value for field, value in event["data"]["strategy_objects"][strategy].items()
                            if not isinstance(value, list)
                        }
                    }
                    print((str(datetime.datetime.utcfromtimestamp(event.get("timestamp"))), to_print))
            else:
                print((str(datetime.datetime.utcfromtimestamp(event["timestamp"])), event["data"]))


def day_before_19_50_by_ts(start):
    # type: (float) -> float
    """Convert utc timestamp to previous day 19:50 local time of utc"""
    return ALCU.cet_dt2ts(ALU.delta_day_at(ALCU.utc_ts2cet_dt(start), -1, 19, 50))


CutoverTime = {
    COMMON.Area.apg: CutoverDef(first_local_to_xbid=day_before_19_50_by_ts,
                                second_xbid_to_local=ALU.hour_to_delivery_by_ts,
                                third_local_close=ALU.five_min_to_delivery_by_ts),
    COMMON.Area.rwe: CutoverDef(first_local_to_xbid=day_before_19_50_by_ts,
                                second_xbid_to_local=ALU.hour_to_delivery_by_ts,
                                third_local_close=ALU.five_min_to_delivery_by_ts)
}


def add_closing_order_at_cutover(prod, orderdef, area):
    # type: (SimuProductDefinition, OrderDefinition, str) -> T.TupleType[OrderDefinition, OrderDefinition]
    """Force close orders at the end of a local or xbid trading phase"""

    first_local_to_xbid_ts = CutoverTime[area].first_local_to_xbid(prod.delivery_start)
    second_xbid_to_local_ts = CutoverTime[area].second_xbid_to_local(prod.delivery_start)
    third_local_close = CutoverTime[area].third_local_close(prod.delivery_start)

    if orderdef.timestamp < first_local_to_xbid_ts:
        return (
            OrderDefinition(orderdef.direction, prod.product_id_local, orderdef.price, orderdef.quantity, area,
                            orderdef.timestamp,
                            orderdef.order_id),
            OrderDefinition(orderdef.direction, prod.product_id_local, orderdef.price, 0, area, first_local_to_xbid_ts,
                            orderdef.order_id)
        )
    elif first_local_to_xbid_ts <= orderdef.timestamp < second_xbid_to_local_ts:
        return (
            OrderDefinition(orderdef.direction, prod.product_id_xbid, orderdef.price, orderdef.quantity, area,
                            orderdef.timestamp,
                            orderdef.order_id),
            OrderDefinition(orderdef.direction, prod.product_id_xbid, orderdef.price, 0, area, second_xbid_to_local_ts,
                            orderdef.order_id)
        )
    elif second_xbid_to_local_ts <= orderdef.timestamp < third_local_close:
        return (
            OrderDefinition(orderdef.direction, prod.product_id_local, orderdef.price, orderdef.quantity, area,
                            orderdef.timestamp,
                            orderdef.order_id),
            OrderDefinition(orderdef.direction, prod.product_id_local, orderdef.price, 0, area, third_local_close,
                            orderdef.order_id)
        )
    else:
        raise ValueError("Cannot place order after trading is closed")
