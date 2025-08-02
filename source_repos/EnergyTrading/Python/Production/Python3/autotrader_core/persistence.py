#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import collections
import datetime
import time

import six
from six.moves import queue
from six.moves import range

import autotrader_lib.common as COMMON
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.utils as UTIL
import autotrader_lib.util
import autotrader_lib.version

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
log = FLOG.getLogger("autotrader.persistence")

# catch pymongo import error
# if the api just runs a simulation (for example the simulation tests),
# using the MongoDB would slow down the tests
try:
    from bson.son import SON
    from bson import BSON
    from bson.errors import InvalidDocument
    import pymongo
    import pymongo.errors

    # this should contain all pymongo operations (can be found in operations.py in the pymongo library)
    # NOTE: insert_many is not a single operation, but just a wrapper around many Insert Ones
    _ACTION_MAPPING = {"insert_one": pymongo.InsertOne,
                       "update_one": pymongo.UpdateOne,
                       "update_many": pymongo.UpdateMany,
                       "replace_one": pymongo.ReplaceOne,
                       "delete_one": pymongo.DeleteOne,
                       "delete_many": pymongo.DeleteMany}

except ImportError:
    # in this case, we don't initialize pymongo and SON
    # if MongoDB is used in this case, MongoDBConnector.initialize will fail
    print("Warning: pymongo is not installed")
    log.error("pymongo is not installed")

_EXPIRY_INTERVAL = COMMON.DAY * 3  # 3 days
_HISTORY_SIZE = 20

# cap the maximum size of the public order history to the 100 most recent updates.
_HISTORY_SIZE_PUBLIC_ORDER = 100


def to_unicode(s):
    """
    Function which ensures a 'text' value is properly decoded into unicode

    This function is used to sanitize customer input, so we try to make it foolproof
    """
    if isinstance(s, six.text_type):
        return s
    elif isinstance(s, str):
        return s.decode("utf-8", errors="replace")
    else:
        return six.text_type(s)


def function_guard(parent_only=True, child_only=False):
    """returns a decorator which can be used to protect functions from being executed by a child process"""

    def _guard_decorator(f):
        """This decorator factory outputs a different decorator based on whether a function is only allowed
        to be run by the parent. In both cases functions are only allowed to run if persistence is initialized"""
        if parent_only:
            def decorated(self, *args, **kwargs):
                if self.is_initialized and self.is_parent:
                    return f(self, *args, **kwargs)
        elif child_only:
            def decorated(self, *args, **kwargs):
                if self.is_initialized and not self.is_parent:
                    return f(self, *args, **kwargs)
        else:
            def decorated(self, *args, **kwargs):
                if self.is_initialized:
                    return f(self, *args, **kwargs)

        return decorated

    return _guard_decorator


class WriterThread(autotrader_lib.util.StoppableThread):
    """This thread class implements the mongodb writing thread placing write requests on a queue and executing them"""
    max_retries = 5
    flush_timeout = 1

    def __init__(self, database_object, writer_queue):
        super(WriterThread, self).__init__(name=self.__class__.__name__)
        # daemon is very necessary since it ensures the thread dies together with the processes that created it
        self.daemon = True
        self._db = database_object
        self._writer_queue = writer_queue

    def run(self):
        """Processes items from the queue and performs the (write) method calls on the database"""

        accumulator = collections.defaultdict(list)
        last_flush = time.time()
        pulled_num = 0

        while not self._should_stop.is_set():
            current_time = time.time()

            # get the write request from the queue, since this is a separate thread
            try:
                # we need to have some sort of timeout so that the thread can loop and actually stop when requested to
                # however to avoid just looping all the time, we put a small timeout so that we block a bit waiting
                # for an item to occur
                collection_name, action_object = self._writer_queue.get(timeout=0.01)
            except queue.Empty:
                # if the queue is empty we just pass because we dont know if the writing has been done
                if pulled_num == 0:
                    continue

            else:
                pulled_num += 1
                accumulator[collection_name].append(action_object)

            time_condition = (current_time - last_flush) >= self.flush_timeout

            if not time_condition:
                continue

            try:
                self.execute_write_request(accumulator)

            except Exception:
                log.exception("Thread is exiting since an exception occurred during executing write request.")
                self.stop()

            # if it all passes re-init the default dict
            else:
                accumulator = collections.defaultdict(list)
                last_flush = time.time()
                # By issuing task_done() pulled_num times, we decrease Queue.unfinished_tasks counter down to 0.
                # pulled_num is the number how many times Queue.put() was called before (<= Queue.get() was successful.)
                # That is necessary for consistent queue administration in case somebody uses Queue.join() later.
                for _ in range(0, pulled_num):
                    self._writer_queue.task_done()
                pulled_num = 0

    def execute_write_request(self, accumulator):
        # keep the last used collection name, so it can be used in case of failure
        collection_name = ""
        try:
            # AUT-3196: sort accumulator so that 'own_trades' is written before 'state'
            for collection_name, actions_list in sorted(accumulator.items()):
                before = time.time()
                log.debug("Bulk write operation started on collection: %s", collection_name)
                bulk_write_result = self._db[collection_name].bulk_write(actions_list, ordered=True)
                write_result = bulk_write_result.bulk_api_result
                write_result.pop("upserted", None)  # remove all the changed object ids
                log.debug("Bulk write operation took %s on collection: %s ,succeeded with result: %s",
                          time.time() - before, collection_name, write_result)

        except pymongo.errors.BulkWriteError as bwe:

            # Delete all the public orders due to which the operation might have failed
            # still raise the error later to force a restart, so autotrader can be initialized correctly
            # with the new set of orders
            log.error("Details of the bulk_write error on collection %s are: %s", collection_name, bwe.details)

            if collection_name == COMMON.MongoCollections.state:
                failed_public_order_ids = [
                    b["op"]["q"]["_id"] for b in bwe.details.get("writeErrors", [])
                    if "PublicOrder" in b["op"]["q"]["_id"]
                ]
                for oid in failed_public_order_ids:
                    log.warning("Removing public order with id: %s to avoid update issue", oid)
                    self._db[collection_name].bulk_write([pymongo.DeleteOne(filter={"_id": oid})])
            raise

        except Exception:
            log.error("A bulk_write error occurred, the values in the accumulator were: %s", accumulator)
            raise

        else:
            # get the last operation of the state
            if accumulator["state"]:
                last_action_element = accumulator["state"][-1]

                # get the message counter. If not present (on child), we do not want to log anything
                if hasattr(last_action_element, "_doc") and isinstance(last_action_element._doc, dict):
                    message_counter = last_action_element._doc.get("message_counter")
                    alteration_time = last_action_element._doc.get("alteration_time")
                    if alteration_time and message_counter:
                        log.debug("Mongo Writer Thread message with counter: %s has queue lag: %s",
                                  message_counter, (datetime.datetime.utcnow() - alteration_time).total_seconds())


class MongoDBConnector(six.with_metaclass(UTIL.Singleton, object)):
    def __init__(self):
        self.db = None
        self.client = None
        self.is_initialized = False
        self.message_counter = 0
        self.is_parent = True

    @autotrader_lib.util.wait_for_it(10)
    def connect(self, username, password):
        """Waits for mongo to be initialized and sets the connection.

        :raise autotrader_lib.util.TimeoutError if the database has not been initialized after 10 seconds.
        """
        # Let's connect and wait that mongo is initialized
        self.client = pymongo.MongoClient(self.host, self.port, username=username, password=password,
                                          authSource=self.auth_source)
        if self.client.admin.command("ismaster")["ismaster"]:
            log.info("Mongo client is connected.")
            return True
        return False

    def initialize(self, host=None, port=None, write_concern=1, database_name="autoTRADER",
                   expiry_interval=None, reset_counter=False, is_parent=True, username="", password="",
                   keep_strategy_history=0, auth_source="autoTRADER", store_public_orders=None):
        self.host = host
        self.port = int(port) if port is not None else None
        self.write_concern = write_concern
        self.database_name = database_name
        self.is_parent = is_parent
        self.keep_strategy_history = keep_strategy_history
        self.auth_source = auth_source
        self.store_public_orders = store_public_orders if store_public_orders is not None else True

        log.info("Initializing persistence with host: %s, port: %s, database: %s, username: %s,"
                 " store_public_orders: %s",
                 self.host, self.port, self.database_name, username, store_public_orders)

        if expiry_interval is None:
            expiry_interval = _EXPIRY_INTERVAL

        log.info("Connecting to Mongo client ...")
        self.connect(username=username, password=password)

        # write concern 0 means: asynchronous without acknowledgement
        # write concern 1 means: wait for ack from database server
        # Since we use the bulk writes, the write concern should always be 1
        self.db = self.client.get_database(self.database_name,
                                           write_concern=pymongo.write_concern.WriteConcern(self.write_concern))

        transaction_docs = self.db.state.find({}).sort([("message_counter", -1)]).limit(1)
        if reset_counter:
            self.message_counter = 0
        else:
            try:
                doc = next(transaction_docs)
                self.message_counter = int(doc["message_counter"])
                log.debug("Getting last message counter from database: %s", self.message_counter)
            except StopIteration:
                pass

        # Set autoTRADER and all exchanges to uninitialized before performing long-running database actions.
        self.update_db_set_uninitialized()

        log.info("Searching in database for collection own_trades and strategy_history ...")
        # check if "own_trades" collection is there
        if COMMON.MongoCollections.own_trades not in self.db.list_collection_names():
            # duplicate OwnTrades content from state collection into new collection
            log.info("own_trades collection not found, creating collection with OwnTrade objects")
            self.db.create_collection(COMMON.MongoCollections.own_trades)
            self.db.state.aggregate([{"$match": {"object_type": "OwnTrade"}}, {"$out": "own_trades"}])
        log.info("own_trades collection exists in the database")
        if self.keep_strategy_history and COMMON.MongoCollections.strat_history not in self.db.list_collection_names():
            log.info("strategy_history collection not found, creating empty collection")
            self.db.create_collection(COMMON.MongoCollections.strat_history)
        if COMMON.MongoCollections.strat_history in self.db.list_collection_names():
            log.info("strategy_history collection exists in the database")

        if self.is_parent:
            self._prepare_indices(expiry_interval, keep_strategy_history)
            self._cleanup_trayport_properties()
            self._include_meta_data_in_packages()
            self._include_json_repr()

        # enable performance logging
        pstatus = self.db.profiling_level()
        log.info("Database Profiling level %s", pstatus)
        if pstatus != pymongo.ALL:
            self.db.set_profiling_level(pymongo.OFF)
            self.db.system.profile.drop()
            self.db.create_collection("system.profile", capped=True, size=10000000)
            self.db.set_profiling_level(pymongo.ALL)
            log.info("Increased system.profile collection size to 10 MB")
        # set is_initialized to true so that the next functions will be called successfully
        self.is_initialized = True

        # run startup cleanups in order to enter with a fresh state
        # reset of orders to 0 quantity
        log.info("Entering database cleanup section")
        self.close_all_orders()
        # turn off trading portfolios
        self.delete_db_all_trading_portfolios()

        # Update old package structures
        self.migrate_old_packages()

        if store_public_orders is False:
            public_orders_count = self.db.state.count_documents({"object_type": "PublicOrder"})
            if public_orders_count > 0:
                log.info("Removing Public Orders from DB as write_public_orders_to_db is set to False")
                self.db.state.delete_many({"object_type": "PublicOrder"})

        log.info("Writer queue and writer thread initialization ...")
        self._writer_queue = queue.Queue()
        self._writer_thread = WriterThread(database_object=self.db, writer_queue=self._writer_queue)
        self._writer_thread.start()
        log.info("Created and started writer thread, now waiting")
        count_sleep = 0
        while not self.is_writer_alive():
            time.sleep(0.1)
            count_sleep += 0.1
            if count_sleep % 1 == 0:
                log.info("Writer thread is initializing for %s seconds", count_sleep)
        log.info("Writer thread is alive")

        log.info("Persistence initialized, is_parent=%s", self.is_parent)

    def _prepare_indices(self, expiry_interval, keep_strategy_history):
        """
        Prepare indices for the mongoDB tables used by autoTRADER

        :param expiry_interval: The expiry interval for the state table (in seconds, approximate)
        :type expiry_interval: int
        :param keep_strategy_history: Whether or not we use the strategy history table.
        :type keep_strategy_history: bool
        """
        # prepare indexes
        # cleanup of tables
        # if the creation of the index fails here (because the expiry has changed), the second command immediately sets
        # it right
        log.info("Preparing delivery_end index, with expire time: %s seconds", expiry_interval)
        try:
            self.db.state.create_index([("_delivery_end", 1)], name="state_expire", expireAfterSeconds=expiry_interval)
            self.db.strategies.create_index([("alteration_time", 1)],
                                            name="strategies_expire",
                                            expireAfterSeconds=expiry_interval)
            self.db.sessions.create_index([("_last_access", 1)],
                                          name="sessions_expire",
                                          expireAfterSeconds=expiry_interval)
            self.db.strategy_persistence.create_index([("updated_at", 1)],
                                                      name="strategy_persistence_expire",
                                                      expireAfterSeconds=expiry_interval)
        except pymongo.errors.OperationFailure:
            self.db.command(SON([("collMod", "state"),
                                 ("index", {"keyPattern": {"_delivery_end": 1},
                                            "expireAfterSeconds": expiry_interval
                                            })
                                 ]))
        log.info("delivery_end index with expire time prepared")

        if self.keep_strategy_history:
            log.info("Preparing strategy_history index")
            keep_strategy_history_seconds = keep_strategy_history * 60 * 60
            try:
                # keep strategy history is in hours
                self.db.strategy_history.create_index([("_strategy_update_timestamp", 1)],
                                                      name="strategy_history_expire",
                                                      expireAfterSeconds=keep_strategy_history_seconds)
            except pymongo.errors.OperationFailure:
                self.db.command(SON([("collMod", COMMON.MongoCollections.strat_history),
                                     ("index", {"keyPattern": {"_strategy_update_timestamp": 1},
                                                "expireAfterSeconds": keep_strategy_history_seconds
                                                })
                                     ]))

            # since the strategy transfer runs every minute or more,
            # this will have a lot of records especially in case of many strategies
            # likewise this will be used by REST API and on trades import to get information,
            # so it has to be able to get the information fast therefore we add the index
            self.db.strategy_history.create_index([("internal_number", 1), ("_strategy_update_timestamp", 1)],
                                                  name="strategy_history_index_int_num_time")
            log.info("strategy_history index prepared")

        # product_indices
        log.info("Preparing product indices ...")
        self.db.state.create_index([("exchange", 1), ("product_id", 1)], name="state_product")
        self.db.state.create_index([("object_type", 1), ("exchange", 1), ("product_id", 1)], name="state_type_product")
        self.db.state.create_index([("message_counter", 1)], name="state_message_counter")
        self.db.state.create_index([("object_type", 1), ("quantity", 1)], name="state_type_quantity")
        log.info("Product indices prepared")
        # Indices on the own_trades collection
        log.info("Preparing own_trades index ...")
        own_trades_indexes = {
            "own_trades_product": [("product_id", 1)],
            "own_trades_ids": [("trade_id", 1)],
            "own_trades_executiontime": [("execution_time", 1)],
            "own_trades_area_buy": [("sell_delivery_area", 1)],
            "own_trades_area_sell": [("buy_delivery_area", 1)],
            "own_trades_delivery_period": [("delivery_end", -1), ("delivery_start", -1)]
        }
        for name, keys in own_trades_indexes.items():
            self.db.own_trades.create_index(keys, name=name)

        log.info("own_trades index prepared")
        # Indices on the strategies collection
        log.info("Preparing strategies index ...")
        self.db.strategies.create_index([("object_type", 1)], name="strategies_object_type")
        log.info("strategies index prepared")

    def _cleanup_trayport_properties(self):
        """
        This function is created to remove already existing TrayportProperties from MongoDB (AUT-2363).
        If this function has been executed in every system at least once, it should be removed.
        """
        object_type = "TrayportProperties"
        if self.db.state.find_one({"object_type": object_type}):
            log.debug("Deleting TrayportProperties from database...")
            result = self.db.state.delete_many({"object_type": object_type})
            if result.deleted_count:
                log.debug("%s TrayportProperties document(s) were deleted from MongoDB", result.deleted_count)

    def put_on_write_queue(self, collection_name, action_type, *args, **kwargs):
        # Note: modulo by powers of 2 seems to be slightly faster than by other numbers.
        if self.is_parent and self.message_counter % 2048 == 0:
            current_queue_size = self._writer_queue.qsize()
            if current_queue_size > 5000:
                log.warning("Mongo Writer Thread queue is getting overflown. Current size %s", current_queue_size)
            else:
                log.debug("Mongo Writer Thread queue size is %s", current_queue_size)

        self._writer_queue.put((collection_name,
                                self.write_command_factory(action_type=action_type, *args, **kwargs)))

    @staticmethod
    def write_command_factory(action_type, *args, **kwargs):
        action_class = _ACTION_MAPPING[action_type]

        # if the wrong arguments are provided for the class, the error should be raised immediately here
        try:
            action_obj = action_class(*args, **kwargs)

        except Exception as err:
            log.exception("An error occurred when calling the write command factory for action_type: %s "
                          "with action_class: %s, using arguments: %s", action_type, action_class.__name__, locals())
            raise

        return action_obj

    def is_writer_alive(self):
        return self._writer_thread.is_alive()

    def stop(self):
        self._writer_thread.stop()

    def get_counter(self):
        self.message_counter += 1
        return self.message_counter

    def migrate_old_packages(self):
        """ Function created to update the existing old package structures.

        Note: As a followup this function can be removed, once every system has the updated packages only"""
        last_update_time = datetime.datetime.utcnow()
        update_result = self.db.strategies.update_many({"object_type": COMMON.MongoDBObjects.package,
                                                        "$and": [{"approval_time": {"$exists": True}},
                                                                 {"deprecation_time": {"$exists": True}}]},
                                                       {
                                                           "$rename": {
                                                               "approval_time": "approval_utc",
                                                               "deprecation_time": "deprecation_utc"
                                                           },
                                                           "$set": {"last_updated_utc": last_update_time}})
        log.debug("%s package(s) has been updated to the new format", update_result.modified_count)

    def _include_meta_data_in_packages(self):
        """
        Migrate the Package objects in MongoDB to include the meta_data_groups

        Old versions of the REST-API would call 'get_meta_data' on the package template everytime the
        GET packages/<package_name> function was called. Now we store this meta-data in MongoDB, so we do not
        have to unzip and load the package every time.
        """
        import autotrader_core.strategy_template as TEMPLATE  # We need to import locally to prevent a circular import

        for package in self.db.strategies.find({"object_type": COMMON.MongoDBObjects.package,
                                                "meta_data_groups": None}):
            try:
                template = TEMPLATE.get_template_from_package(TEMPLATE.load_package_from_zip(package["package_name"],
                                                                                             package["package"]))
                meta_data = template.get_meta_data()
                self.db.strategies.update_one({"_id": package["_id"]},
                                              {"$set": {"meta_data_groups": meta_data["groups"]}})
            except Exception:
                log.exception("Cannot migrate package %s", package["package_name"])
            else:
                log.debug("Cached meta-data for package %s.", package["package_name"])

    def _include_json_repr(self):
        """
        Migrates old StrategyConfiguration objects to the new one with
        - an updated _id := StrategyConfigurationObject.<strategy_id>
        - _json_repr field with configuration info
        """
        import autotrader_core.strategy_template as TEMPLATE  # We need to import locally to prevent a circular import
        created_utc = datetime.datetime.utcnow()
        for strategy_config in self.db.strategies.find({"object_type": COMMON.MongoDBObjects.strategy_configuration,
                                                        "_json_repr": None}):
            if strategy_config.get("deleted"):
                log.debug("Strategy %s has been soft deleted. Hard deleting it, because no database migration "
                          "is possible for deleted strategies. It was: %s",
                          strategy_config["_id"], strategy_config)
                self.db.strategies.delete_one({"_id": strategy_config["_id"]})
                continue
            if "package_name" not in strategy_config:
                log.warning("Strategy %s still includes the package instead of linking to an external package. "
                            "This means that the strategy was created long ago by a now outdated version "
                            "of the autoTRADER REST-API. Deleting the strategy.", strategy_config["_id"])
                log.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_deleted,
                                   strategy_id=strategy_config.get("internal_number", strategy_config["_id"]),
                                   full_database_document=strategy_config,
                                   reason="Outdated strategy format no longer supported "
                                          "by the current autoTRADER version",
                                   old_configuration=strategy_config,
                                   username=COMMON.PeriotheusSystemUsers.system)
                self.db.strategies.delete_one({"_id": strategy_config["_id"]})
                continue

            mongo_package = self.db.strategies.find_one({"_id": "Package.{}".format(strategy_config["package_name"])})
            if mongo_package is None:
                log.debug("Package %s does not exist, skipping database migration for strategy %s",
                          strategy_config["package_name"],
                          strategy_config["internal_number"])
                continue
            try:
                class_template = TEMPLATE.get_template_from_package(
                    TEMPLATE.load_package_from_zip(mongo_package["package_name"],
                                                   mongo_package["package"]))
                template_object = class_template.from_mongo_object(strategy_config)
                mongo_object = template_object.to_mongo_object(strategy_config["package_name"],
                                                               strategy_config["username"],
                                                               strategy_config["child_id"])
                mongo_object["created_utc"] = created_utc
                self.db.strategies.delete_one(strategy_config)
                self.db.strategies.insert_one(mongo_object)
            except Exception as err:
                log.exception("Cannot migrate strategy %s; reason: %s",
                              strategy_config["internal_number"],
                              err)
            else:
                log.debug("Strategy %s was successfully migrated to the new format",
                          strategy_config["internal_number"])

    @staticmethod
    def get_history_query(history_fields):
        """ Return a mongo query to add element to a _history field in a list of fixed size.

        :param history_fields: the object we should add in the list
        :type history_fields: dict
        :return: the query to use in mongo
        :rtype: dict
        """
        ret = dict()
        if history_fields:
            history_fields.update(insertion_time=datetime.datetime.utcnow())
            ret = {"$push": {"_history": {"$each": [history_fields],
                                          "$slice": _HISTORY_SIZE,
                                          "$position": 0}}}

        return ret

    @staticmethod
    def _get_db_old_trade_id(trade, trade_type):
        """
        This is needed for gradually migrating the own_trades table to a new _id format that includes the broker_id.

        We delete trades with the old id on trade updates (which for OTC are not uncommon),
        as soon as we insert trades with the new id.
        """
        if trade_type == "OwnTrade":
            direction = ""
            if trade.sell_delivery_area:
                direction += "S"
            if trade.buy_delivery_area:
                direction += "B"
            return "{}.{}.{}.{}".format(trade_type, trade.exchange, trade.trade_id, direction)
        else:
            return "{}.{}.{}".format(trade_type, trade.exchange, trade.trade_id)

    @staticmethod
    def _get_db_trade_id(trade, trade_type):
        # Note: For compatibility with old data in the database,
        # we only append the broker to the _id column where it is set (currently only Trayport).
        fields = [trade_type, trade.exchange, trade.trade_id]
        if trade_type == "OwnTrade":
            direction = "B" if trade.buy_delivery_area else "S"
            fields.append(direction)
        if trade.initiator_broker_id is not None:
            fields.append(trade.initiator_broker_id)
        return ".".join(fields)

    @staticmethod
    def _get_db_order_id(order, order_type):
        """"
        For compatibility with old data in the database. We append the broker_id to the _id column if set
        This currently only affects Trayport
        """

        fields = [order_type, order.exchange]
        if order_type == "PublicOrder":
            fields.append(order.delivery_area_id)
        fields.append(order.order_id)
        if order.broker_id is not None:
            fields.append(order.broker_id)
        return ".".join(fields)

    @function_guard()
    def update_db_record(self, record):
        counter = self.get_counter()
        object_type = record["object_type"]
        db_record = record.copy()
        db_record["message_counter"] = counter
        obj_id = record["obj_id"]
        try:
            self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                    action_type="replace_one",
                                    filter={"_id": "{}_{}".format(object_type, obj_id)},
                                    replacement=db_record,
                                    upsert=True)
        except Exception:
            log.exception("%s", record)
            raise

    @function_guard()
    def update_db_record_collection(self, record_collection):
        counter = self.get_counter()
        object_type = record_collection["object_type"]
        obj_id = record_collection["obj_id"]
        to_insert = SON([("message_counter", counter),
                         ("object_type", object_type),
                         ("obj_id", obj_id)])
        to_insert.update(record_collection["collection"])
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}_{}".format(object_type, obj_id)},
                                update={"$set": to_insert},
                                upsert=True)

    @function_guard(parent_only=False)
    def load_package(self, package_name):
        return self.db.strategies.find_one({"_id": "Package.{}".format(package_name)})

    @function_guard()
    def update_db_public_trades(self, trade, timestamp):
        counter = self.get_counter()
        otype = "PublicTrade"
        replacement = SON([
            ("message_counter", counter),
            ("_delivery_end", datetime.datetime.utcfromtimestamp(trade.product.delivery_end)),
            ("object_type", otype),
            ("execution_time", datetime.datetime.utcfromtimestamp(trade.execution_time)),
            ("exchange", trade.exchange),
            ("trade_id", trade.trade_id),
            ("product_id", trade.product.product_id),
            ("product_type", trade.product.product_type),
            ("delivery_start", datetime.datetime.utcfromtimestamp(trade.product.delivery_start)),
            ("delivery_end", datetime.datetime.utcfromtimestamp(trade.product.delivery_end)),
            ("buy_delivery_area", trade.buy_delivery_area),
            ("sell_delivery_area", trade.sell_delivery_area),
            ("quantity", trade.quantity),
            ("price", trade.price),
            ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
            ("aggressor_broker_id", trade.aggressor_broker_id),
            ("initiator_broker_id", trade.initiator_broker_id),
            ("aggressor_trading_account", trade.aggressor_trading_account),
            ("initiator_trading_account", trade.initiator_trading_account),
            ("_id_version", 2),  # version 2: After AUT-1163
            ("route_id", trade.route_id),
        ])
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="replace_one",
                                filter={"_id": self._get_db_trade_id(trade, otype)},
                                replacement=replacement,
                                upsert=True)

    def _get_owntrade_bson(self, trade, counter, timestamp):
        return SON([
            ("message_counter", counter),
            ("_delivery_end", datetime.datetime.utcfromtimestamp(trade.product.delivery_end)),
            ("object_type", "OwnTrade"),
            ("execution_time", datetime.datetime.utcfromtimestamp(trade.execution_time)),
            ("exchange", trade.exchange),
            ("trade_id", trade.trade_id),
            ("revision", trade.revision),
            ("state", trade.state),
            ("order_id", trade.order_id),
            ("user", trade.user),
            ("trader_id", trade.trader_id),
            ("trader_name", trade.trader_name),
            ("product_id", trade.product.product_id),
            ("product_type", trade.product.product_type),
            ("product_name", trade.product.name),
            ("delivery_start", datetime.datetime.utcfromtimestamp(trade.product.delivery_start)),
            ("delivery_end", datetime.datetime.utcfromtimestamp(trade.product.delivery_end)),
            ("buy_delivery_area", trade.buy_delivery_area),
            ("sell_delivery_area", trade.sell_delivery_area),
            ("internal", trade.trade_id.startswith("internal_")),
            ("quantity", trade.quantity),
            ("price", trade.price),
            ("trading_portfolio", trade.portfolio_key or ""),
            ("slot_type", trade.tags.get("strategy_slot", "")),
            ("slot_information", trade.tags.get("stats", "")),
            ("tags", trade.tags),
            ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
            ("counterparty", trade.counterparty),
            ("aggressor", trade.aggressor),
            ("initiator", trade.initiator),
            ("aggressor_broker_id", trade.aggressor_broker_id),
            ("initiator_broker_id", trade.initiator_broker_id),
            ("aggressor_trading_account", trade.aggressor_trading_account),
            ("initiator_trading_account", trade.initiator_trading_account),
            ("annotations", trade.annotations),
            ("regulatory_data", trade.regulatory_data),
            ("terms", trade.terms),
            ("_id_version", 2),  # v2: The new format after AUT-1163 of the _id column (only changes for TRAYPORT)
            ("route_id", trade.route_id),
            ("from_broken_spread", trade.from_broken_spread),
            ("init_sleeve", trade.init_sleeve),
            ("agg_sleeve", trade.agg_sleeve),
            ("voice_deal", trade.voice_deal),
        ])

    @function_guard()
    def update_db_own_trades(self, trade, timestamp):
        counter = self.get_counter()
        otype = "OwnTrade"
        filter_key = {"_id": self._get_db_trade_id(trade, otype)}
        if trade.initiator_broker_id is not None:
            # Gradual migration from old _ids to new _ids on updates.
            # Delete stale entries before inserting the new ones.
            delete_filter_key = {"_id": self._get_db_old_trade_id(trade, otype)}
            for collection_name in [COMMON.MongoCollections.own_trades, COMMON.MongoCollections.state]:
                self.put_on_write_queue(collection_name=collection_name,
                                        action_type="delete_one",
                                        filter=delete_filter_key)
        replacement_doc = self._get_owntrade_bson(trade, counter, timestamp)
        for collection_name in [COMMON.MongoCollections.own_trades, COMMON.MongoCollections.state]:
            # This removes the _imported flag.
            self.put_on_write_queue(collection_name=collection_name,
                                    action_type="replace_one",
                                    filter=filter_key,
                                    replacement=replacement_doc,
                                    upsert=True)

    @function_guard()
    def update_db_trade_on_cancellation(self, trade, timestamp, trade_type):
        """Updates DB trade upon its cancellation/recall

        In particular, the functon set the trade `_imported` value to False, so the
        trade is imported to PT with 0 quantity.

        :param trade: trade object, which was cancelled/recalled
        :param int timestamp: current timestamp
        :param trade_type: type of the trade object "OwnTrade" or "PublicTrade"
        """
        counter = self.get_counter()
        db_update = {"quantity": trade.quantity,
                     "state": trade.state,
                     "message_counter": counter,
                     "alteration_time": datetime.datetime.utcfromtimestamp(timestamp)}
        set_on_insert = None
        if trade_type == "OwnTrade":
            db_update.update({"_imported": False,
                              "revision": trade.revision})
            if trade.initiator_broker_id is not None:
                # Potentially, we need to migrate to the new _id column format (AUT-1163)
                # So we delete the old entry if it exists.
                delete_filter_key = {"_id": self._get_db_old_trade_id(trade, "OwnTrade")}
                for collection_name in [COMMON.MongoCollections.own_trades, COMMON.MongoCollections.state]:
                    self.put_on_write_queue(collection_name=collection_name,
                                            action_type="delete_one",
                                            filter=delete_filter_key)
                # In that case no entry with the new _id existed yet, so the cancellation is an upsert.
                # In this case, we setOnInsert the remaining fields.
                set_on_insert = self._get_owntrade_bson(trade, counter, timestamp)
                # Duplicate keys in set and setOnInsert are not allowed. $set wins.
                for key in db_update.keys():
                    set_on_insert.pop(key, None)

        update_operation = {"$set": db_update,
                            "$currentDate": {"insertion_time": True}}
        if set_on_insert:
            update_operation["$setOnInsert"] = set_on_insert
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": self._get_db_trade_id(trade, trade_type)},
                                update=update_operation,
                                upsert=True)
        if trade_type == "OwnTrade":
            # For own trades, we have to update the own_trades collection as well.
            self.put_on_write_queue(collection_name=COMMON.MongoCollections.own_trades,
                                    action_type="update_one",
                                    filter={"_id": self._get_db_trade_id(trade, trade_type)},
                                    update=update_operation,
                                    upsert=True)

    @function_guard()
    def update_db_public_orders(self, order, timestamp):
        if not self.store_public_orders:
            return
        counter = self.get_counter()
        otype = "PublicOrder"
        date = datetime.datetime.utcfromtimestamp(timestamp)
        if order.quantity > 0:
            expiry_time = datetime.datetime.utcfromtimestamp(order.product.delivery_end)
        else:
            # If the PublicOrder quantity is 0, set the expiry timer, so we only keep these objects for 1 day in DB
            expiry_time = datetime.datetime.utcfromtimestamp(timestamp - (_EXPIRY_INTERVAL / 3.0 * 2))

        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": self._get_db_order_id(order, otype)},
                                update={
                                    "$set": SON([("message_counter", counter),
                                                 ("_delivery_end", expiry_time),
                                                 ("object_type", otype),
                                                 ("exchange", order.exchange),
                                                 ("order_id", order.order_id),
                                                 ("product_id", order.product.product_id),
                                                 ("delivery_start",
                                                  datetime.datetime.utcfromtimestamp(order.product.delivery_start)),
                                                 ("delivery_end",
                                                  datetime.datetime.utcfromtimestamp(order.product.delivery_end)),
                                                 ("delivery_area", order.delivery_area_id),
                                                 ("direction", order.direction),
                                                 ("quantity", order.quantity),
                                                 ("price", order.price),
                                                 ("system_rank", order.system_rank),
                                                 ("is_tradable", order.is_tradable),
                                                 ("counter_party_ok", order.counter_party_ok),
                                                 ("implied", order.implied),
                                                 ("alteration_time", date),
                                                 ("broker_id", order.broker_id),
                                                 ("_id_version", 2),  # version 2: After AUT-1168
                                                 ("route_id", order.route_id),
                                                 ]),
                                    "$currentDate": {"insertion_time": True},
                                    "$push": {
                                        "history": {
                                            "$each": [
                                                SON([("message_counter", counter),
                                                     ("alteration_time", date),
                                                     ("quantity", order.quantity),
                                                     ("price", order.price)])
                                            ],
                                            "$slice": -_HISTORY_SIZE_PUBLIC_ORDER
                                        }
                                    }
                                },
                                upsert=True)

    @function_guard()
    def update_db_own_orders(self, order, timestamp):
        if not hasattr(order, "order_id"):
            return
        counter = self.get_counter()
        otype = "OwnOrder"
        filter_key = {"_id": self._get_db_order_id(order, otype)}
        date = datetime.datetime.utcfromtimestamp(timestamp)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter=filter_key,
                                update={"$set": SON([("message_counter", counter),
                                                     ("_delivery_end",
                                                      datetime.datetime.utcfromtimestamp(order.product.delivery_end)),
                                                     ("object_type", otype),
                                                     ("client_order_id", order.client_order_id),
                                                     ("exchange_portfolio_id", order.exchange_portfolio_id),
                                                     ("exchange", order.exchange),
                                                     ("order_id", order.order_id),
                                                     ("initial_order_id", order.initial_order_id),
                                                     ("product_id", order.product.product_id),
                                                     ("product_name", order.product.name),
                                                     ("delivery_start",
                                                      datetime.datetime.utcfromtimestamp(order.product.delivery_start)),
                                                     ("delivery_end",
                                                      datetime.datetime.utcfromtimestamp(order.product.delivery_end)),
                                                     ("delivery_area", order.delivery_area_id),
                                                     ("type", "O"),  # TODO: fill here when implementing ICB, Block
                                                     ("direction", order.direction),
                                                     ("quantity", order.quantity),
                                                     ("peak_quantity", 10000.),  # TODO: fill here when implementing ICB
                                                     ("price", order.price),
                                                     ("trading_portfolio", order.portfolio_key or ""),
                                                     ("slot_type", order.tags.get("strategy_slot", "")),
                                                     ("slot_information", order.tags.get("stats", "")),
                                                     ("alteration_time", date),
                                                     ("broker_id", order.broker_id),
                                                     ("regulatory_data", order.regulatory_data),
                                                     ("trading_account", order.trading_account),
                                                     ("terms", order.terms),
                                                     ("execution_restriction", order.execution_restriction),
                                                     ("_id_version", 2),  # version 2: The new format after AUT-1168
                                                     ("route_id", order.route_id),
                                                     ]),
                                        "$currentDate": {"insertion_time": True},
                                        "$push": {"history": SON([
                                            ("message_counter", counter),
                                            ("alteration_time", date),
                                            ("quantity", order.quantity),
                                            ("price", order.price),
                                            ("slot_information", order.tags.get("stats", ""))])}
                                        }, upsert=True)

    @function_guard()
    def update_db_capacities(self, capacity, timestamp):
        otype = "Capacity"
        counter = self.get_counter()
        dend = datetime.datetime.utcfromtimestamp(capacity.delivery_end)
        filter_dict = {"_id": "{}.{}.{}.{}.{}.{}".format(otype,
                                                         capacity.exchange,
                                                         capacity.delivery_area_from,
                                                         capacity.delivery_area_to,
                                                         capacity.delivery_start,
                                                         capacity.delivery_end)}
        update_dict = {"$set": SON([("message_counter", counter),
                                    ("object_type", otype),
                                    ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
                                    ("exchange", capacity.exchange),
                                    ("in_capacity", capacity.in_capacity),
                                    ("out_capacity", capacity.out_capacity),
                                    ("publication_time", datetime.datetime.utcfromtimestamp(capacity.publication_time)),
                                    ("delivery_start", datetime.datetime.utcfromtimestamp(capacity.delivery_start)),
                                    ("delivery_end", dend),
                                    ("_delivery_end", dend),
                                    ("delivery_area_from", capacity.delivery_area_from),
                                    ("delivery_area_to", capacity.delivery_area_to),
                                    ("internal", capacity.internal),
                                    ("sequence_number", capacity.sequence_number)
                                    ]),
                       "$currentDate": {"insertion_time": True}}
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter=filter_dict,
                                update=update_dict,
                                upsert=True)

    @function_guard()
    def update_db_products(self, product, timestamp):
        counter = self.get_counter()
        otype = "Product"
        dend = datetime.datetime.utcfromtimestamp(product.delivery_end)
        update_dict = {
            "$set": SON([("message_counter", counter),
                         ("_delivery_end", dend),
                         ("object_type", otype),
                         ("product_id", product.product_id),
                         ("exchange", product.exchange),
                         ("name", product.name),
                         ("type", product.product_type),
                         ("delivery_start", datetime.datetime.utcfromtimestamp(product.delivery_start)),
                         ("delivery_end", dend),
                         ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
                         ("delivery_area_states",
                          [SON([("area", area), ("state", state)])
                           for area, state in sorted(product._delivery_area_states.items())]),
                         ("trading_intervals", [
                             SON([("area", area),
                                  ("state", state),
                                  ("trading_start", datetime.datetime.utcfromtimestamp(start)),
                                  ("trading_end", datetime.datetime.utcfromtimestamp(end))])
                             for area, (start, end, state) in sorted(product._trading_phases.items())]),
                         ("order_lock", [
                             SON([("internal_order_id", locking_object.object_id),
                                  ("state", locking_object.state),
                                  ("timestamp", datetime.datetime.utcfromtimestamp(locking_object.timestamp))])
                             for locking_object in product.order_lock
                         ]),
                         ("trade_lock", [
                             SON([("order_id", locking_object.object_id),
                                  ("state", locking_object.state),
                                  ("timestamp", datetime.datetime.utcfromtimestamp(locking_object.timestamp))])
                             for locking_object in product.trade_lock
                         ]),
                         ("market_meta_information",
                          [SON([(key, value)]) for key, value in product.market_meta_information.items()])
                         ]),
            "$currentDate": {"insertion_time": True},
        }
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}.{}.{}".format(otype, product.exchange, product.product_id)},
                                update=update_dict,
                                upsert=True)

    @staticmethod
    def _get_exchange_bson(counter, timestamp, **kwargs):
        return SON([("message_counter", counter),
                    ("object_type", "Exchange"),
                    ("name", kwargs["internal_id"]),
                    ("caption", kwargs["caption"]),
                    ("connected", kwargs["connected"]),
                    ("simulation_mode", kwargs["simulation_mode"]),
                    ("halted", kwargs["halted"]),
                    ("halt_reason", kwargs["halt_reason"]),
                    ("critical_exchange_halt", kwargs["critical_exchange_halt"]),
                    # initialized is recalculated in exchanges.ExchangeBase.update_db
                    ("initialized", kwargs["initialized"]),
                    ("last_incoming_message_ago",
                     time.time() - kwargs["last_incoming_message_timestamp"]),
                    ("market_state", kwargs["market_state"]),
                    ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
                    ("areas", [SON([("name", area), ("caption", caption)])
                               for area, caption in sorted(kwargs["areas"])]),
                    ("_init_timestamp", kwargs["initialized_dt"]),
                    ("routes", kwargs["routes"]),
                    ])

    @function_guard()
    def update_db_exchanges(self, exchange, timestamp, history_fields=None):
        otype = "Exchange"
        if history_fields is None:
            history_fields = []

        son_data = self._get_exchange_bson(self.get_counter(), timestamp, **exchange.__dict__)
        update_operations = {"$set": son_data}
        history = {field: getattr(exchange, field) for field in history_fields}
        update_operations.update(self.get_history_query(history))

        params = dict(filter={"_id": "{}.{}".format(otype, exchange.internal_id)},
                      update=update_operations, upsert=True)
        response = self.db.state.update_one(**params)
        log.debug("Wrote Exchange %s object to mongoDB while bypassing the queue. Result acknowledged: %s",
                  exchange.internal_id, response.acknowledged)

    @function_guard()
    def update_db_action_limits(self, broker_actions, product_actions, exchange_id):
        """
        Save the ActionLimits object in the state collection from the database.
        """
        otype = COMMON.MongoDBObjects.action_limits
        action_list = []
        action_list.extend(("actions_count.{}".format(year_month), actions)
                           for year_month, actions in
                           broker_actions.items())
        action_list.extend(("actions_per_product_count.{}".format(year_month), actions)
                           for year_month, actions in
                           product_actions.items())

        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}.{}".format(otype, exchange_id)},
                                update={"$set": SON([("object_type", otype), ("name", exchange_id)] + action_list)},
                                upsert=True)

    @function_guard(parent_only=False)
    def load_db_action_limits(self, exchange_id):
        """
        Load the ActionLimits object in the state collection from the database.
        """
        return self.db.state.find_one({"object_type": COMMON.MongoDBObjects.action_limits,
                                       "_id": "{}.{}".format(COMMON.MongoDBObjects.action_limits, exchange_id)})

    @function_guard()
    def update_db_rate_limit(self, data, exchange):
        """Update the action rate limit object in mongodb

        :param data: data dict generated by RateLimitManager.to_dict
        :type data: dict
        :param exchange: The exchange the rate limit is for
        :type exchange: str
        """
        limit_type = data.get("limit_type", "")
        data["object_type"] = COMMON.MongoDBObjects.action_limits
        data["name"] = COMMON.Exchange.epex
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}.{}.{}".format(COMMON.MongoDBObjects.action_limits,
                                                                 exchange, limit_type)},
                                update={"$set": data, "$currentDate": {"alteration_time": True}},
                                upsert=True)

    @function_guard(parent_only=False)
    def load_db_rate_limit(self, limit_type, exchange):
        """Load the action rate limit status from mongo.

        :param limit_type: The limit_type
        :type limit_type: str
        :param exchange: The exchange the rate limit is for
        :type exchange: str
        :return: data dict to be loaded by a RateLimitManager
        :rtype: dict or None
        """
        return self.db.state.find_one({
            "object_type": COMMON.MongoDBObjects.action_limits,
            "_id": "{}.{}.{}".format(COMMON.MongoDBObjects.action_limits, exchange, limit_type)
        })

    @function_guard()
    def update_db_set_uninitialized(self):
        """
        Called at startup /shutdown to set the autoTRADER object in the persistence to uninitialized.
        """
        log.debug("Setting autoTRADER and Exchange(s) states to not initialized")
        update_operation = {
            "$set": {"message_counter": self.get_counter(), "initialized": False},
        }
        update_operation.update(self.get_history_query({"initialized": False}))
        self.db.state.update_one({"_id": "AutoTrader"}, update_operation)

        exchange_update_operations = {
            "$set": {"initialized": False, "connected": False},
        }
        exchange_update_operations.update(self.get_history_query({"initialized": False, "connected": False}))
        for exchange_name in COMMON.Exchange.get_external():
            exchange_update_operations["$set"]["message_counter"] = self.get_counter()
            # Note: No upsert here, only update existing exchanges!
            result = self.db.state.update_one({"object_type": "Exchange", "name": exchange_name},
                                              exchange_update_operations)
            # if the previous update did not match any object, we reverse the increment of counter made in get_counter
            if not result.matched_count:
                self.message_counter -= 1

    @staticmethod
    def _get_autotrader_bson(counter, pending_correlation_ids, **kwargs):
        now = time.time()
        return SON([("message_counter", counter),
                    ("object_type", "AutoTrader"),
                    ("last_incoming_message_ago", now - kwargs["last_incoming_message_timestamp"]),
                    ("queue_lag", kwargs["max_queue_lag"]),
                    ("uptime", now - kwargs["initialization_timestamp"]),
                    ("halted", kwargs["halted"]),
                    ("critical_halt", kwargs["critical_halt"]),
                    ("halt_reason", kwargs["halt_reason"]),
                    ("remove_orders", kwargs["remove_orders"]),
                    ("initialized", kwargs["initialized"]),
                    ("last_cleanup_run", kwargs["last_cleanup_run"]),
                    ("pending_initialization_correlations", pending_correlation_ids),
                    ("version", autotrader_lib.version.VERSION)
                    ])

    @function_guard()
    def update_db_autotrader(self, autotrader, history_fields=None):
        otype = "AutoTrader"
        if history_fields is None:
            history_fields = []

        counter = self.get_counter()
        pending_correlation_ids = []
        for ex in autotrader.all_exchanges:
            pending_correlation_ids += [k for k, v in ex.init_files_correlation_ids.items() if not v]

        son_data = self._get_autotrader_bson(counter, pending_correlation_ids, **autotrader.__dict__)
        update_operations = {"$set": son_data, "$currentDate": {"alteration_time": True}}
        history_operation = self.get_history_query({field: getattr(autotrader, field) for field in history_fields})
        update_operations.update(history_operation)
        # For the autoTRADER object we always bypass the queue, to ensure that the halted state is always
        # correctly reflected in MongoDB immediately. If we bypass the queue only sometimes, we risk that older data
        # from the queue overwrites newer data.
        # In contrast to trading data, this object is written so infrequently (every 10 seconds and on halt/resume)
        # that bypassing the write queue is fine.
        response = self.db.state.update_one(
            filter={"_id": "{}".format(otype)},
            update=update_operations,
            upsert=True
        )
        log.debug("Wrote AutoTRADER object to mongoDB while bypassing the queue. Result acknowledged: %s",
                  response.acknowledged)

    @staticmethod
    def _get_autotrader_child_bson(counter, **kwargs):
        return SON([("message_counter", counter),
                    ("object_type", "AutoTraderChild"),
                    ("initialized", kwargs.get("initialized")),
                    ("child_id", kwargs.get("child_id")),
                    ("exchanges", kwargs.get("exchanges")),
                    ("queue_lag", kwargs.get("max_queue_lag"))
                    ])

    @function_guard(parent_only=False, child_only=True)
    def update_db_autotrader_child(self, autotrader):
        otype = "AutoTraderChild"
        counter = self.get_counter()
        child_id = autotrader.child_id
        config = autotrader.config
        exchanges = None
        if config:
            exchanges = list(getattr(config, "child_exchange_distribution", {}).get(child_id, []))

        son_data = self._get_autotrader_child_bson(counter, exchanges=exchanges, **autotrader.__dict__)
        update_operations = {"$set": son_data, "$currentDate": {"alteration_time": True}}

        response = self.db.state.update_one(
            filter={"_id": "{}.{}".format(otype, autotrader.child_id)},
            update=update_operations,
            upsert=True)
        log.debug("Wrote AutoTraderChild object to mongoDB while bypassing the queue. Result acknowledged: %s",
                  response.acknowledged)

    @function_guard(parent_only=False)
    def update_db_timeseries(self, domain, domain_key, domain_caption, timeseries_packets, timestamp):
        # type: (str, str, str, dict, float) -> None
        otype = "TimeSeries"

        domain = to_unicode(domain)
        domain_key = to_unicode(domain_key)
        domain_caption = to_unicode(domain_caption)

        # timeseries_packets must be a dict of
        # { timeseries_name -> (caption, unit, unit_caption, resolution (seconds), { ts_from -> value } }
        for timeseries_name, (caption, unit, unit_caption, resolution, data) in timeseries_packets.items():
            timeseries_name = to_unicode(timeseries_name)
            caption = to_unicode(caption)
            unit = to_unicode(unit)
            unit_caption = to_unicode(unit_caption)

            # packet should always consist of 100 values
            packetsize = resolution * 100
            packets = collections.defaultdict(list)
            for ts, value in data.items():
                packets[int(ts // packetsize * packetsize)].append(
                    ("values.{}".format(int(ts % packetsize / resolution)), value)
                )

            for ts, values in packets.items():
                self.put_on_write_queue(
                    collection_name=COMMON.MongoCollections.state,
                    action_type="update_one",
                    filter={"_id": u"{}.{}.{}.{}.{}".format(otype, domain, domain_key, timeseries_name, ts)},
                    update={
                        "$set": SON(
                            [
                                ("_delivery_end", datetime.datetime.utcfromtimestamp(ts + packetsize)),
                                ("object_type", otype),
                                (domain, domain_key),
                                ("caption", domain_caption),
                                ("timeseries_name", timeseries_name),
                                ("timeseries_caption", caption),
                                ("unit", unit),
                                ("unit_caption", unit_caption),
                                ("resolution", int(resolution)),
                                ("packet_start", datetime.datetime.utcfromtimestamp(ts)),
                                ("alteration_time", datetime.datetime.utcfromtimestamp(timestamp)),
                            ] + values
                        ),
                        "$currentDate": {"insertion_time": True}
                    },
                    upsert=True
                )

    @function_guard(parent_only=False)
    def update_db_product_info(self, domain, domain_key, domain_caption, product, text, data_object, timestamp):
        otype = "Product"
        key_str = "{}.{}".format(domain, domain_key)
        date = datetime.datetime.utcfromtimestamp(timestamp)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": u"{}.{}.{}".format(otype, product.exchange, product.product_id)},
                                update={"$set": SON([("alteration_time", date),
                                                     ("object_type", otype),
                                                     # Just in case: Set object_type - REST API needs this field
                                                     (
                                                         key_str,
                                                         SON([("caption", domain_caption), ("text", to_unicode(text)),
                                                              ("alteration_time", date), ("data", data_object)]))]),
                                        "$currentDate": {"insertion_time": True, "info_insertion_time": True}
                                        }, upsert=True)

    @function_guard(parent_only=False)
    def update_db_global_log(self, is_error, domain, domain_key, domain_caption, text, data_object, timestamp):
        otype = "GlobalLog"
        if not self.is_parent and domain != "trading_portfolio":
            # The exchange (domain="exchange") should not write its COMMON.Response.error_response on the child,
            # otherwise we get duplicate entries.
            # The strategy (domain="trading_portfolio") only exists on the child and must be allowed to wrtie.
            return
        # now add message to array
        key_str = "{}.{}".format(domain, domain_key)
        date = datetime.datetime.utcfromtimestamp(timestamp)
        document_id = "{}.{}".format(otype, key_str)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": document_id},
                                update={"$set": SON(
                                    [("object_type", otype), (domain, domain_key),
                                     ("caption", domain_caption), ("alteration_time", date)]),
                                    "$currentDate": {"insertion_time": True},
                                    "$push":
                                        {"errors" if is_error else "infos": {"$each": [
                                            SON([("push_time", date), ("text", to_unicode(text)),
                                                 ("data", data_object)])],
                                            "$slice": -50}}
                                }, upsert=True)

    @function_guard(parent_only=False)
    def update_db_global_log_state(self, domain, domain_key, domain_caption, text, data_object, timestamp):
        otype = "GlobalLog"
        # now add message to array
        key_str = "{}.{}".format(domain, domain_key)
        document_id = "{}.{}".format(otype, key_str)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": document_id},
                                update={"$set": SON([("object_type", otype),
                                                     (domain, domain_key),
                                                     ("caption", domain_caption),
                                                     ("state_text", to_unicode(text)),
                                                     ("state_data", data_object),
                                                     ("alteration_time",
                                                      datetime.datetime.utcfromtimestamp(timestamp))]),
                                        "$currentDate": {"insertion_time": True},
                                        },
                                upsert=True)

    @function_guard(parent_only=False)
    def load_db_trading_portfolio(self, strategy_id):
        """
        Load the TradingPortfolio object representing a strategy in the state collection from the database.
        """
        otype = "TradingPortfolio"
        return self.db.state.find_one({"object_type": otype,
                                       "_id": "{}.{}".format(otype, strategy_id)})

    @staticmethod
    def _get_trading_portfolio_bson(_timestamp, **kwargs):
        return SON([("object_type", "TradingPortfolio"),
                    ("trading_portfolio", kwargs.get("strategy_id")),
                    ("caption", kwargs.get("caption")),
                    ("deleted", False),
                    ("active", bool(kwargs.get("active"))),
                    ("halted", bool(kwargs.get("halted"))),
                    ("halt_reason", kwargs.get("halt_reason")),
                    ("_remove_orders", bool(kwargs.get("_remove_orders"))),
                    ("algorithm_package_name", kwargs.get("strategy_package_name")),
                    ("alteration_time", datetime.datetime.utcfromtimestamp(_timestamp)),
                    ])

    @function_guard(parent_only=False)
    def update_db_trading_portfolios(self, strategy, timestamp, history_fields=None):
        otype = "TradingPortfolio"
        if history_fields is None:
            history_fields = []

        son_data = self._get_trading_portfolio_bson(timestamp, **strategy.__dict__)
        history = {field: getattr(strategy, field, None) for field in history_fields}

        update_operations = {"$set": son_data, "$currentDate": {"insertion_time": True}}
        update_operations.update(self.get_history_query(history))

        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}.{}".format(otype, strategy.strategy_id)},
                                update=update_operations,
                                upsert=True)

    @function_guard(parent_only=False)
    def delete_db_trading_portfolios(self, key, timestamp):
        counter = self.get_counter()
        otype = "TradingPortfolio"
        update_operations = {
            "$set": SON([("message_counter", counter),
                         ("object_type", otype),
                         ("deleted", True),
                         ("active", False),
                         ("halted", False),
                         ("halt_reason", ""),
                         ("_remove_orders", False),
                         ("alteration_time",
                          datetime.datetime.utcfromtimestamp(timestamp))]),
            "$currentDate": {"insertion_time": True}
        }
        update_operations.update(self.get_history_query({"deleted": True, "active": False}))
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": "{}.{}".format(otype, key)},
                                update=update_operations)

    @function_guard()
    def delete_db_all_trading_portfolios(self):
        # NOTE: Since this function is used in the initialization
        # before the writer thread starts it needs to directly write to mongo
        log.info("Turn off trading portfolios")
        counter = self.get_counter()
        otype = "TradingPortfolio"
        update_operations = {
            "$set": SON([("message_counter", counter),
                         ("object_type", otype),
                         ("deleted", True),
                         ("active", False),
                         ("alteration_time", datetime.datetime.utcnow())]),
            "$currentDate": {"insertion_time": True}
        }
        update_operations.update(self.get_history_query({"deleted": True, "active": False}))

        self.db.state.update_many(filter={"object_type": otype},
                                  update=update_operations)
        log.info("Turned off trading portfolios")

    @function_guard(parent_only=False)
    def load_db_autotrader_state(self):
        return self.db.state.find_one({"object_type": "AutoTrader"})

    @function_guard(parent_only=False)
    def load_db_exchange(self, name, caption):
        return self.db.state.find_one({"object_type": "Exchange", "name": name, "caption": caption})

    @function_guard(parent_only=False)
    def load_db_own_trades(self, exchange, product_id):
        return self.db.state.find({"exchange": exchange, "product_id": product_id, "object_type": "OwnTrade"})

    @function_guard(parent_only=False)
    def load_tags_for_order_id(self, exchange_id, order_id, broker_id):
        """
        For the given order, load the trading_portfolio, slot_type and slot_information

        :type exchange_id: str
        :type order_id: str
        :type broker_id: str
        :rtype: dict or None
        """
        database_id = "OwnOrder.{}.{}".format(exchange_id, order_id)
        if broker_id is not None:
            database_id += ".{}".format(broker_id)
        order_info = self.db.state.find_one({"_id": database_id},
                                            projection={"trading_portfolio": 1, "slot_information": 1, "slot_type": 1})
        if order_info:
            return {"portfolio_key": order_info["trading_portfolio"],
                    "strategy_slot": order_info["slot_type"],
                    "stats": order_info["slot_information"]}
        else:
            return None

    @function_guard(parent_only=False)
    def are_all_orders_removed(self):
        """Checks if orders are removed, having no non-zero quantity orders"""
        return self.db.state.count_documents({"object_type": "OwnOrder", "trading_portfolio": {"$ne": ""},
                                              "quantity": {"$gt": 0}}) == 0

    @function_guard(parent_only=False)
    def find_unremoved_orders(self):
        return self.db.state.find({"object_type": "OwnOrder", "quantity": {"$gt": 0}})

    @function_guard(parent_only=False)
    def load_strategies(self, child_id):
        """Load all strategies that are assigned to the given child id"""
        criteria = {
            "object_type": COMMON.MongoDBObjects.strategy,
        }
        if child_id > 0:
            criteria["child_id"] = child_id
        else:
            # child id 0 takes on all unassigned strategies
            criteria["child_id"] = {"$in": [child_id, None]}
        return self.db.strategies.find(criteria)

    @function_guard(parent_only=False)
    def store_strategy_history(self, strategy_data, current_timestamp):
        """Strategy history storage helper function

        Originally the _id is the internal_number of the strategy, in this case this is not useful because we will have
        many records of the same strategy from different times. That's why we create random ids

        We use the threaded option because we want to make sure not to block for too long so the
        strategy gets the update right away, timestamp is stored at the previous point so even
        if the record gets written later its not a problem

        Skipping the package:
            We skip the package since this would conserve space and we can usually find the code
            in the custom_strategies folder, where the same name guarantees us the same code so we can
            easily get the correct code by the field package_name

        Precision of _strategy_update_timestamp:
            Since MongoDB uses BSON which only has precision of microseconds, the _strategy_update_timestamp,
            will have rounded datetimes with only millisecond and not microsecond precision


        :param strategy_data: The dictionary of the strategy configuration data
        :type strategy_data: dict
        :param current_timestamp: The timestamp for the time at which the configuration was loaded
        :type current_timestamp: datetime.datetime
        :return:
        """
        # copy over the data, just so we do not run into any mutability issues
        saved_strategy_data = {key: strategy_data[key] for key in strategy_data.keys()
                               if key not in ["_id",  # skip the _id field because we want them to be unique
                                              "package"]}  # skip the package to save space (see docstring for more)
        saved_strategy_data.update(_strategy_update_timestamp=current_timestamp)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.strat_history,
                                action_type="insert_one", document=saved_strategy_data)

    @function_guard()
    def close_all_orders(self, exchange_id=None):
        """Used on startup of the autoTrader in order to clean up garbage by closing all
        open orders (with quantity > 0)"""
        # NOTE: Since this function is crucial (needs to block until completion)
        # and used in the initialization before the writer thread starts it needs to directly write to mongo
        log.info("Closing all open orders (with quantity > 0)")
        now = time.time()
        counter = self.get_counter()
        search_dict = {"object_type": "OwnOrder", "quantity": {"$gt": 0.}}
        if exchange_id:
            search_dict["exchange"] = exchange_id
        self.db.state.update_many(filter=search_dict,
                                  update={
                                      "$set": SON([("message_counter", counter),
                                                   ("quantity", 0.)]),
                                      "$push": {"history": SON([
                                          ("message_counter", counter),
                                          ("alteration_time", datetime.datetime.utcfromtimestamp(now)),
                                          ("quantity", 0.),
                                          ("price", 0.),
                                          ("slot_information", "automatic close on startup")])}
                                  })

        search_dict["object_type"] = "PublicOrder"
        update_dict = {
            "$set": SON([("message_counter", counter), ("quantity", 0.)]),
            "$push": {
                "history": {
                    "$each": [
                        SON([("message_counter", counter),
                             ("alteration_time", datetime.datetime.utcfromtimestamp(now)),
                             ("quantity", 0.),
                             ("price", 0.)])
                    ],
                    "$slice": -_HISTORY_SIZE_PUBLIC_ORDER
                }
            }
        }
        self.db.state.update_many(filter=search_dict, update=update_dict)
        log.info("Closed all open orders (with quantity > 0)")

    @function_guard(parent_only=False)
    def load_db_products(self, exchange):
        return self.db.state.find({"exchange": exchange, "object_type": "Product"})

    @function_guard(parent_only=False)
    def write_response_into_mongo(self, object_id, response, upsert):
        """Writes a response for strategy steering calls to mongo"""
        query = {"_id": object_id}
        self.db.strategies.update_one(filter=query, update={"$set": {"response": response}}, upsert=upsert)

    @function_guard(parent_only=False)
    def update_db_per_product_limits(self, limit_container, update_timestamp):
        """
        Store a LimitContainer (used for storing the per-product limits of a strategy) in MongoDB.

        There can only be one LimitContainer per Strategy

        :param limit_container: The LimitContainer to store
        :type limit_container: autotrader_core._strategy_datastructures.LimitContainer
        :param update_timestamp: The epoch timestamp when the limit container was last updated
        :type update_timestamp: float
        """
        object_id = "ProductLimits.{}".format(limit_container._strategy_id)
        self.db.strategies.replace_one(
            {"_id": object_id},
            replacement={
                "_id": object_id,
                "strategy_id": limit_container._strategy_id,
                "exchange_id": limit_container._exchange_id,
                "limits_per_sequence": limit_container._per_sequence,
                "limits_per_sequence_item": limit_container._per_product,
                "update_time": datetime.datetime.utcfromtimestamp(update_timestamp),
            },
            upsert=True)

    @function_guard(parent_only=False)
    def load_db_per_product_limits(self, strategy_id):
        """
        Load a LimitContainer from the database
        :param strategy_id: The id of the strategy for which to load the limit container
        :type strategy_id: str
        :return: A MongoDocument representing the LimitContainer
        :rtype: dict | None
        """
        object_id = "ProductLimits.{}".format(strategy_id)
        return self.db.strategies.find_one({"_id": object_id})

    @function_guard(parent_only=False)
    def delete_db_per_product_limits(self, strategy_id):
        """
        Delete the per_product limits for a strategy
        :param strategy_id: The id of the strategy for which to delete the limits
        :type strategy_id: str
        """
        # Just delete it, there is no need to set it to deleted...
        object_id = "ProductLimits.{}".format(strategy_id)
        self.put_on_write_queue(collection_name="strategies",
                                action_type="delete_one",
                                filter={"_id": object_id})

    @function_guard(parent_only=False)
    def load_db_exchange_configuration(self, exchange_id):
        return self.db.configuration.find_one({"_id": "ExchangeConfiguration.{}".format(exchange_id),
                                               "object_type": "ExchangeConfiguration",
                                               "exchange": exchange_id})

    @function_guard(parent_only=False)
    def update_db_synthetic_order(self, synthetic_order, product_id, strategy, synthetic_object_type=None):
        """
        Stores a new or updates an existing synthetic order in MongoDB
        :param synthetic_order: The synthetic order object to be saved
        :type synthetic_order: SYBASE.SyntheticOrderStrategyBase
        :param product_id: The product ID stored as sequence_item_id
        :type product_id: str
        :param strategy: The strategy
        :type strategy:
            autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base.SyntheticOrderStrategyBase
        :param synthetic_object_type: The type of synthetic order later used to identify the class of the object
        :type synthetic_object_type: str
        :return: None
        """
        can_be_reconfigured = COMMON.SyntheticOrderOperations.modify in strategy.allowed_synthetic_order_operations
        can_be_deleted = COMMON.SyntheticOrderOperations.delete in strategy.allowed_synthetic_order_operations
        otype = COMMON.MongoDBObjects.synthetic_order_state
        document_id = "{}.{}.{}.{}".format(otype, strategy.strategy_id, product_id, synthetic_order.identifier)
        configuration = synthetic_order.get_configuration()
        synthetic_order_content = [("object_type", otype),
                                   ("status", synthetic_order.status),
                                   ("synthetic_order_id", synthetic_order.identifier),
                                   ("tick_size", synthetic_order.tick_size),
                                   ("strategy_internal_number", strategy.strategy_id),
                                   ("sequence_item_id", product_id),
                                   ("configuration", configuration),
                                   ("status_text", synthetic_order.status_text),
                                   ("can_be_reconfigured", can_be_reconfigured),
                                   ("can_be_deleted", can_be_deleted),
                                   ]
        if synthetic_object_type:
            synthetic_order_content.append(("synthetic_order_type", synthetic_object_type))
        synthetic_order_content.append(("_package_name", strategy.strategy_package_name))
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="update_one",
                                filter={"_id": document_id},
                                update={"$set": SON(synthetic_order_content),
                                        "$currentDate": {"last_updated_utc": True},
                                        "$setOnInsert": {"created_utc": datetime.datetime.utcnow()}},
                                upsert=True if synthetic_object_type else False)

    @function_guard(parent_only=False)
    def delete_db_synthetic_order(self, strategy_id, identifier, product_id):
        """
        After setting the deleted flag to true and the synthetic order expires this function removes its corresponding
        MongoDB document
        :param strategy_id: The strategy ID used as part of the _id field
        :type strategy_id: str
        :param identifier: The synthetic order ID used as part of the _id field
        :type identifier: str
        :param product_id: The product ID used as part of the _id field
        :type product_id: str
        :return: None
        """
        object_id = "{}.{}.{}.{}".format(COMMON.MongoDBObjects.synthetic_order_state,
                                         strategy_id, product_id, identifier)
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="delete_one",
                                filter={"object_type": COMMON.MongoDBObjects.synthetic_order_state,
                                        "_id": object_id})

    @function_guard(parent_only=False)
    def delete_db_all_synthetic_orders(self, strategy_id):
        """
        Deletes every SyntheticOrderState objects from the state collection with the corresponding strategy_id
        :param strategy_id: The strategy ID connected to every synthetic orders to be deleted
        :type strategy_id: str
        :return: None
        """
        self.put_on_write_queue(collection_name=COMMON.MongoCollections.state,
                                action_type="delete_many",
                                filter={"object_type": COMMON.MongoDBObjects.synthetic_order_state,
                                        "strategy_internal_number": strategy_id})

    @function_guard(parent_only=False)
    def load_db_synthetic_order(self, strategy_id):
        """
        Loads currently stored synthetic orders from MongoDB for a specific strategy ID
        :param strategy_id: Strategy ID to filter the queried synthetic orders
        :type strategy_id: str
        :return: pyMongo cursor containing every synthetic order with correct strategy ID
        :rtype: pymongo.cursor.Cursor
        """
        return self.db.state.find({"object_type": COMMON.MongoDBObjects.synthetic_order_state,
                                   "strategy_internal_number": strategy_id})

    @function_guard(parent_only=False)
    def update_db_strategy_config(self, strategy):
        """
        Updates StrategyConfigurationObject halted state and reason.

        Currently, only two fields are updated: "halted" and "halt_reason".
        :param strategy: Strategy object
        :type strategy: autotrader_core.strategy.Strategy
        :return: None
        """
        strategy_data = SON([("halted", strategy.halted),
                             ("halt_reason", "" if strategy.halt_reason is None else strategy.halt_reason)])
        update_operations = {"$set": strategy_data}
        self.put_on_write_queue(collection_name="strategies",
                                action_type="update_one",
                                filter={"_id": "StrategyConfigurationObject.{}".format(strategy.strategy_id)},
                                update=update_operations,
                                upsert=False)

    @function_guard(parent_only=False)
    def update_db_optimization(self, solver_name, model, solver_args, strategy_id, document_id):
        """
        Stores a new or updates an existing model to optimize in MongoDB
        :param solver_name: The name of the solver we wish to use ("CBC", "GUROBI")
        :type solver_name: str
        :param model: The pulp model as a dict we wish to solve
        :type model: dict
        :param solver_args: The arguments to be passed to the solver.
        :type solver_args: dict
        :param strategy_id: The strategy ID stored as interal_number
        :type strategy_id: str
        :param document_id: Document_id to insert
        :type document_id: str
        :return: None
        """
        otype = COMMON.MongoDBObjects.solver
        optimization_content = [("name", solver_name),
                                ("strategy_id", strategy_id),
                                ("strategy_internal_number", strategy_id),
                                ("kwargs", solver_args),
                                ("model", model),
                                ]
        self.put_on_write_queue(collection_name=otype,
                                action_type="update_one",
                                filter={"_id": document_id},
                                update={"$set": SON(optimization_content),
                                        "$currentDate": {"updated_at": True},
                                        "$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                                upsert=True)

    @function_guard(parent_only=False)
    def persist_ai_strategy_object(self, payload, name, strategy_id):
        """
        Stores a new or updates the persistence information to MongoDB for a specific strategy ID.
        :param payload: Information we want to persist.
        :type payload: dict
        :param name: The name of the information we want to persist (E.g. steering_call,
        internal_reference_storage_level, ...)
        :type name: str
        :param strategy_id: The name of strategy.
        :type strategy_id: str
        :return: True if successfully put on queue
        :rtype: bool
        """
        otype = COMMON.MongoDBObjects.strategy_persistence
        document_id = "{}.{}.{}".format(otype, strategy_id, name)
        payload_enriched = [
            ("object_type", otype),
            ("name", name),
            ("strategy_id", strategy_id),
            ("strategy_internal_number", strategy_id),
            ("payload", payload),
        ]
        payload_enriched_son = SON(payload_enriched)

        # check if we can bson serialize the payload for mongo
        try:
            BSON.encode(payload_enriched_son)
        except InvalidDocument:
            log.error("Could not bson-serialize the payload: {}".format(payload_enriched_son))
            return False

        self.put_on_write_queue(
            collection_name="strategy_persistence",
            action_type="update_one",
            filter={"_id": document_id},
            update={
                "$set": payload_enriched_son,
                "$currentDate": {"updated_at": True},
                "$setOnInsert": {"created_at": datetime.datetime.utcnow()},
            },
            upsert=True,
        )
        return True

    @function_guard(parent_only=False)
    def load_ai_strategy_object(self, name, strategy_id):
        """
        Loads currently stored persistent information from MongoDB for a specific strategy ID.
        :param name: The name of the information we want to retrieve from persistence (E.g. steering_call,
        internal_reference_storage_level, ...)
        :type name: str
        :param strategy_id: The name of strategy.
        :type strategy_id: str
        :return: pyMongo cursor containing the latest ai_strategy_object with the correct strategy_id.
        :rtype: pymongo.cursor.Cursor
        """
        otype = COMMON.MongoDBObjects.strategy_persistence
        document_id = "{}.{}.{}".format(otype, strategy_id, name)
        query = {"_id": document_id}
        strategy_object_results = self.db.strategy_persistence.find_one(query)
        return strategy_object_results.get("payload", None) if strategy_object_results else None
