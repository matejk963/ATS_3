from __future__ import absolute_import
import datetime
import uuid

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU


def create_steering_call(strategy_id, steering_msg, timestamp):
    """
    Wrap a steering_msg (payload) in an envelop understood by autoTRADER's backtesting framework.

    :param strategy_id: The internal_id of the strategy
    :type strategy_id: str
    :param steering_msg: The steering dictionary that will be forwarded to the strategy
    :type steering_msg: dict
    :param timestamp: The simulation time at which the steering call shall be placed. In UTC
    :type timestamp: int | float | datetime.datetime
    :return: Ths steering_msg wrapped in an envelope which the Simulator understands
    :rtype: dict
    """
    if isinstance(timestamp, datetime.datetime):
        timestamp = ALU.convert_dt_to_float_timestamp(timestamp)

    return {
        "message_type": "strategy_steering_call",
        "exchange": "PERIOTHEUS",
        "data": {"strategy_objects": {strategy_id: steering_msg}},
        "timestamp": timestamp
    }


def create_strategy_config_message(timestamp, strategy_id, strategy_configuration):
    return dict(message_type="strategy",
                object_type=COMMON.MongoDBObjects.strategy_configuration,
                timestamp=timestamp,
                data={"strategy_objects": {strategy_id: strategy_configuration.to_mongo_dict()}})


def create_per_products_limit_message(timestamp, strategy_id, limits_dict):
    copied_limits_dict = limits_dict.copy()
    copied_limits_dict.update(user_login="BACKTESTING")
    return dict(message_type="per_products_limits",
                object_type=COMMON.MongoDBObjects.per_product_limits,
                timestamp=timestamp,
                data={"limits_message": {strategy_id: copied_limits_dict}})


def create_synthetic_order_message(timestamp, strategy_id, synthetic_orders_payload):
    return dict(message_type="synthetic_orders",
                object_type=COMMON.MongoDBObjects.synthetic_order,
                timestamp=timestamp,
                data={"synthetic_orders": {strategy_id: synthetic_orders_payload}})


def create_halt_message(timestamp, is_halted=True, remove_orders=True, exchange_id=None):
    return dict(
        message_type="emergency_halt_state_info",
        data={
            "is_halted": is_halted,
            "remove_orders": remove_orders,
            "exchange_id": exchange_id,
            "halting_user": "visotech"
        },
        properties={"correlation_id": str(uuid.uuid4())},
        exchange="PERIOTHEUS",
        timestamp=timestamp
    )
