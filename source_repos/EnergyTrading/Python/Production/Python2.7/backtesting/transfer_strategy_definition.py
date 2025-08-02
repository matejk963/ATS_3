#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module contains util functions for transferring StrategyDefition objects or any valid dict objects to running
autotrader through ZMQ
"""
import base64
import datetime as DT
import time

import msgpack
import pymongo

import autotrader_lib.util as UTIL


class SerializationError(Exception):
    pass


class Timeout(Exception):
    pass


class InvalidResponse(Exception):
    pass


def _encoder(obj):
    if isinstance(obj, DT.datetime):
        return {"__datetime__": True, "as_str": obj.strftime("%Y%m%dT%H:%M:%S.%fZ")}
    return obj


def _decoder(obj):
    if "__datetime__" in obj:
        obj = UTIL.DTConv.str2ymd_h_m_s_f(obj["as_str"], "%Y%m%dT%H:%M:%S.%fZ")
    return obj


def serialize(obj):
    return msgpack.packb(obj, default=_encoder)


def deserialize(serialized):
    try:
        return msgpack.unpackb(serialized, object_hook=_decoder)
    except ValueError as err:
        raise SerializationError(err)


def transfer(data, host=None, port=None, username="vt", password="vt", database_name="autoTRADER",
             num_child_processes=1):
    """Transfer strategy data to Mongo DB avoiding Periotheus

    :param data: data with strategy to be transferred
    :type data: dict
    :param host: host of the Mongo DB, where the startegy should be transferred
    :type host: str or None
    :param port: port of the Mongo DB, where the startegy should be transferred
    :type port: str or None
    :param username: username for Mongo DB authentication
    :type username: str
    :param password: password for Mongo DB authentication
    :type password: str
    :param database_name: name of the database, where the startegy should be transferred
    :type database_name: str
    :param num_child_processes: number of child processes
    :type num_child_processes: int
    :return:
    """

    nb_child = num_child_processes

    mongodb = pymongo.MongoClient(host, port, username=username, password=password)

    database = mongodb.get_database(database_name)

    strategies = data["data"]

    to_export = {
        "strategy_objects": "StrategyObject",
        "global_objects": "MarketStateTimeseries",
    }

    for object_type, strategy_objects in strategies.iteritems():
        for strategy_int_num, strategy in strategy_objects.iteritems():
            if strategy is None:
                strategy = {"deleted": True, "internal_number": strategy_int_num}
            if "package" in strategy:
                strategy["package"] = base64.b64encode(strategy["package"])
            strategy["object_type"] = to_export[object_type]
            strategy["message_counter"] = time.time()
            if object_type == "strategy_objects":
                if "child_id" not in strategy:
                    strategy["child_id"] = (
                        hash(strategy_int_num) % nb_child if nb_child != 0 else 0
                    )
            database.strategies.replace_one(
                {"_id": strategy_int_num}, strategy, upsert=True
            )
