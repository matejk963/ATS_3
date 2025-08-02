# coding: utf-8

from __future__ import absolute_import
import autotrader_lib.util
import autotrader_lib.common as COMMON
import logging
import six

AT_USER = "AT_USER"

log = logging.getLogger("autotrader.simulator")


class _MockOrder(dict):
    """
    Allow treating order_entry_request and order_modify_request data dictionaries like Order Objects for this module.
    """

    def __getattr__(self, key):
        try:
            if key == "direction" and key not in self:
                return self["side"]
            return self[key]
        except KeyError:
            raise AttributeError(key)


class SimulationData(object):
    def __init__(self, order, order_id, quantity=None):
        if hasattr(order, "product_id"):
            product_id = order.product_id
            delivery_area_id = order.delivery_area_id
        else:
            if hasattr(order, "inst_specifier"):
                product_id = u"{}_{}".format(order["inst_specifier"][0]["first_sequence_id"],
                                             order["inst_specifier"][0]["first_item_id"])
                delivery_area_id = order["inst_specifier"][0]["instrument_id"]
            else:
                product_id = order.product.product_id
                delivery_area_id = order.delivery_area_id

        if hasattr(order, "txt"):
            txt = order.txt
        else:
            txt = autotrader_lib.util.serialize_order_tags(order.tags)

        self.data = {"direction": order.direction,
                     "order_id": order_id,
                     "product_id": product_id,
                     "price": order.price,
                     "quantity": order.quantity if quantity is None else quantity,
                     "delivery_area_id": delivery_area_id,
                     "state": getattr(order, "state", "ACTI"),
                     "user": getattr(order, "original_user", "INTERNAL"),
                     "last_update_user": "INTERNAL",
                     "txt": txt,
                     "revision": 0}
        if hasattr(order, "exchange"):
            if order.exchange == COMMON.Exchange.trayport:
                self.data["implied"] = False

    @classmethod
    def from_order_request(cls, line, order_id, **kwargs):
        order = _MockOrder(**line)
        return cls(order, order_id, **kwargs)

    def update(self, **kwargs):
        self.data.update(kwargs)


class SimulationDataOrder(SimulationData):
    # this is the message an exchange sends to us when we give them an action
    def __init__(self, order, order_id, quantity=None, action="UDEL"):
        super(SimulationDataOrder, self).__init__(order, order_id, quantity=quantity)
        if hasattr(order, "inst_specifier"):
            # trayport specific handling of orders
            order_type = COMMON.OrderType.order
            self.data.update({"broker_id": order.broker_id, "inst_specifier": order.inst_specifier})
            if action == "UADD":
                self.data["engine_id"] = "99"
                self.data["implied"] = False
        else:
            order_type = order.order_type if hasattr(order, "order_type") else order.type

        if hasattr(order, "broker_id"):
            # trayport specific handling of orders
            self.data.update({"broker_id": getattr(order, "broker_id"), "engine_id": getattr(order, "engine_id")})
            self.data["implied"] = getattr(order, "implied", False)

        if getattr(order, "exchange_portfolio_id", None):
            # On Nordpool, we need an exchange portfolio id
            self.data["exchange_portfolio_id"] = order.exchange_portfolio_id

        self.data.update({"initial_order_id": order_id,
                          "action": action,
                          "visible_quantity": getattr(order, "visible_quantity", None),
                          "type": order_type,
                          "revision": (getattr(order, "revision", -1) or -1) + 1,
                          "initial_quantity": 99999.,
                          "execution_restriction": getattr(order, "execution_restriction",
                                                           COMMON.ExecutionRestriction.non),
                          "validity_restriction": "GFS",
                          "validity_date": None,
                          "terms": None,
                          })


class SimulationDataPublicOrder(SimulationData):
    def __init__(self, order, order_id):
        super(SimulationDataPublicOrder, self).__init__(order, order_id)
        if order.exchange == COMMON.Exchange.trayport:
            first_sequence_id, first_item_id = order.product.product_id.split('_')
            self.data["inst_specifier"] = [{'instrument_id': order.delivery_area_id,
                                            'first_item_id': first_item_id,
                                            'term_format_id': '1427494634',
                                            'second_item_id': '0',
                                            'sequence_span': 'Single',
                                            'first_sequence_id': first_sequence_id}]

            self.data["timestamp"] = order.creation_timestamp
            self.data["initial_order_id"] = getattr(order, "initial_order_id", None)
            self.data["engine_id"] = order.engine_id
            self.data["system_rank"] = order.system_rank
            self.data["is_tradable"] = order.is_tradable
            self.data["counter_party_ok"] = order.counter_party_ok
            self.data["execution_restriction"] = order.execution_restriction
            self.data["broker_id"] = order.broker_id
            self.data["action"] = getattr(order, 'action', COMMON.OrderAction.modified)
            self.data["type"] = 'O'
            self.data["txt"] = getattr(order, 'txt', "")
            self.data["account"] = getattr(order, 'account', '0')
            self.data["terms"] = None
            del self.data["delivery_area_id"]

        else:
            del self.data["txt"]
            if hasattr(self.data, "account"):
                del self.data["account"]

        del self.data["user"]
        del self.data["last_update_user"]


class SimulationDataTrade(SimulationData):
    def __init__(self, order, order_id, trade_id, quantity, user, execution_time, exchange, price=None,
                 is_aggressor="U"):
        super(SimulationDataTrade, self).__init__(order, order_id)
        if user == COMMON.SimulationUserExchange.trayport_user:
            self.data.update({
                "aggressor_broker_id": order.broker_id,
                "initiator_broker_id": order.broker_id,
                "terms": []})
            self.data.update(self._set_role(order, is_aggressor, user, exchange.company_id))

            first_sequence_id, first_item_id = order.product.product_id.split('_')
            self.data["inst_specifier"] = [{'instrument_id': order.delivery_area_id,
                                            'first_item_id': first_item_id,
                                            'term_format_id': '1427494634',
                                            'second_item_id': '0',
                                            'sequence_span': 'Single',
                                            'first_sequence_id': first_sequence_id}]
        self.data.update({"user": user,
                          "trade_id": trade_id,
                          "execution_time": execution_time,
                          "quantity": quantity,
                          "delivery_area": order.delivery_area_id,
                          })
        if price is not None:
            self.data.update({
                "price": price,
            })

    def _set_role(self, order, is_aggressor, user, company_id):
        """Set the attributes of the data properly according to the role in the market (i.e aggressor or initiator)"""
        data = dict()
        defaults = {"action": order.direction,
                    "trader_id": 'SIMULATION_TRADER_ID',
                    "trader_name": user,
                    "user_id": 'SIMULATION_ID',
                    "company_id": company_id,
                    "company": "SIMULATION_COMPANY"}
        if is_aggressor == "U":
            log.error("Agressor is undefined on Trayport. Assuming True")
        order_role = "aggressor" if is_aggressor else "initiator"
        for key, value in six.iteritems(defaults):
            data["{}_{}".format(order_role, key)] = value
            other_role = "aggressor" if order_role == "initiator" else "initiator"
            data["{}_{}".format(other_role, key)] = ""

        return data


def simulate_trayport_trade_order_error_response(line):
    """
    Simulate the reply for a failed trade_order request from the trayport exchange.
    Instead of a xml we return an already extracted dict.
    (see test_translator.py method: test_from_error)
    """
    trade_error = {'trade': [{'order_id': line["order_id"], 'txt': line["txt"]}],
                   'error_message': u'You have attempted to perform an action on an order that does not exist.',
                   'error_msg': u'The Order does not exist.', 'order': []}
    return trade_error
