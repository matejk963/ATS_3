# -*- coding: utf-8 -*-
""" This module contains the persistance adapter class, which implements change stream watching
and is planned to be the main communication between aT and MongoDB in the future"""

from six.moves import queue

import pymongo.errors as mongoerr

import autotrader_lib.util as UTIL
import autotrader_lib.adapters.base_adapter as BA
import autotrader_lib.common as COMMON


class ChangeStreamThread(UTIL.StoppableThread):
    """ A thread class implementing the Change Stream watching and ensuring proper stopping of the thread"""
    poll_on_init = [COMMON.MongoDBObjects.strategy,
                    COMMON.MongoDBObjects.strategy_configuration]
    watched_objects = [COMMON.MongoDBObjects.strategy,
                       COMMON.MongoDBObjects.strategy_steering,
                       COMMON.MongoDBObjects.strategy_configuration,
                       COMMON.MongoDBObjects.market_state_timeseries,
                       COMMON.MongoDBObjects.dump_strategy_request,
                       COMMON.MongoDBObjects.per_product_limits,
                       COMMON.MongoDBObjects.synthetic_order]

    def __init__(self, persistence, changes_queue, log):
        super(ChangeStreamThread, self).__init__(name="ChangeStream Thread")
        self.daemon = True
        self._persistence = persistence
        self._changes_queue = changes_queue
        self._log = log
        self._poll_done = False  # Used in tests to make them non-flaky

        self._change_watch_pipeline = self._construct_watch_pipeline()

        # the max_await_time_ms manages how long does the database call actually waits for detecting changes
        # during this time the GIL is released, if anything gets updated it returns right away, therefore
        # having a longer time where the GIL is released and not just a very busy loop is very beneficial
        self._change_stream = self._persistence.db.strategies.watch(pipeline=self._change_watch_pipeline,
                                                                    max_await_time_ms=10000,
                                                                    full_document="updateLookup")

        self.restart_change_stream = False   # if set to True, PA will recreate this object in next step iteration

        self._log.info("ChangeStreamThread started")

    def stop(self):
        """The stop call would set an event flag and close the change stream ensuring proper closing"""
        self._change_stream.close()
        super(ChangeStreamThread, self).stop()

    def run(self):
        # poll first when the change stream thread starts
        self._poll()

        while not self._should_stop.is_set():  # wait in python2 is more CPU intense then desired
            try:
                with self._change_stream as change_stream:
                    for incoming_change in change_stream:
                        obj_type = incoming_change["fullDocument"]["object_type"]
                        is_strategy_config = obj_type == COMMON.MongoDBObjects.strategy_configuration
                        if is_strategy_config and incoming_change["operationType"] == "update":
                            update_change = incoming_change["updateDescription"].get("updatedFields", {})
                            if not set(update_change) - {"halted", "halt_reason"}:
                                # we skip updates for strategy config when only halted flag and halt_reason are updated
                                continue
                        self._put_on_queue(incoming_change["fullDocument"])

            except StopIteration:
                self._log.exception("Change stream was closed and raised StopIteration")
                self.stop()

            except mongoerr.OperationFailure as err:
                exception_message = "The change stream thread encountered an OperationFailure. " \
                                    "\nServer returned code: {}\nDetails of the error:\n {}".format(err.code,
                                                                                                    err.details)
                self._log.exception(exception_message)
                self.restart_change_stream = True

            except Exception:
                # this return allows us to exit the stream normally
                self._log.exception("The change stream thread encountered an unexpected error.")
                self.stop()

        self._log.info("Change Stream Thread now exiting")
        return

    def _poll(self):
        """get all the objects that we wish to watch to ensure synchronicity"""
        for document in self._persistence.db.strategies.find({"object_type": {"$in": self.poll_on_init}}):
            self._put_on_queue(document)
        self._poll_done = True

    def _put_on_queue(self, item):
        """a helper function that should be used for putting items on the queue, in order to log putting events"""
        try:
            self._changes_queue.put_nowait(item=item)  # Do not block, rather raise exception Full
        except Exception:
            self._log.exception("Putting on queue failed with item: %s", item)
            raise
        else:
            self._log.debug("Item was put on queue: Type: %s, internal_number: %s, request_hash: %s",
                            item["object_type"], item.get("internal_number"), item.get("request_hash"))

    def _construct_watch_pipeline(self):
        """constructs a pipeline object in the appropriate format using the list of objects to be watched
        the pipeline is used for the watch stream"""
        watch_inserts_and_updates = {"operationType": {'$in': ["insert", "update", "replace"]}}

        if self.watched_objects is not None:
            watch_objects = {"fullDocument.object_type": {"$in": self.watched_objects}}
            match_statement = {"$and": [watch_inserts_and_updates, watch_objects]}
        else:
            match_statement = watch_inserts_and_updates

        return [{"$match": match_statement}]


class PersistenceAdapter(BA.BaseAdapter):
    """Base class for adapters connecting various components to the autotrader core."""

    def __init__(self, log, on_message_callback, persistence, on_change_callback):
        """initialization function for the adapter

        :param log: the python log to log messages to
        :type log: logging.log
        :param on_message_callback: callback function taking (adapter, msg_dict) as arguments. Will be called when
            the adapter has received data that should be forwarded to the autotrader core.
        :type on_message_callback: callable(adapter, data)
        :param persistence: passed persistence object
        :type persistence: mongodb client connection
        :param on_change_callback: callback function taking (message) as the argument.
            Will process the message accordingly in the core
        :type on_change_callback: callable(adapter, data)
        """
        name = "Persistence_Adapter"
        super(PersistenceAdapter, self).__init__(log, name, on_message_callback)
        self._log = log
        self._persistence = persistence
        self._on_change_callback = on_change_callback

        # make the queue and poll for initial state
        self._changes_queue = queue.Queue()

        self._change_stream_thread = None    # initializing attribute for change stream thread
        self.start_stream()

        self._log.info("Persistence Adapter initialized. Watching for: [%s]",
                       ", ".join(self._change_stream_thread.watched_objects))

    def __str__(self):
        return "Adapter {}".format(self.name)

    def step(self, events, timestamp=None):
        """Called on events by the autotrader core.

        - checks for thread liveness
        - gets items from queue
        - processes ALL items from queue by use of callback

        :param events: The events returned by zmq.Poller.poll as a dictionary
        :type events: dict[zmq socket, event]
        """
        # if thread dies due to an exception, throw an error
        if not self._change_stream_thread.is_alive():
            raise COMMON.ChangeStreamException("Change stream thread died.")

        while True:
            try:
                if self._change_stream_thread.restart_change_stream:
                    self.start_stream(restart=True)
                    self._change_stream_thread.restart_change_stream = False
                message = self._changes_queue.get_nowait()
                self._log.debug("Item was taken from queue to process: Type: %s, internal_number: %s",
                                message["object_type"], message.get("internal_number"))
                self._on_change_callback(message)
                self._changes_queue.task_done()
            except queue.Empty:
                break

    def start_stream(self, restart=False):
        if restart:
            self._log.info("Change stream thread is going to restart")
            self.close()
        self._log.info("Starting change stream thread")
        self._change_stream_thread = ChangeStreamThread(persistence=self._persistence,
                                                        changes_queue=self._changes_queue,
                                                        log=self._log)
        self._change_stream_thread.start()

    def close(self):
        """the closing function for the adapter, closes the change stream, closes the queue and joins the thread"""
        self._log.info("Closing change stream thread")
        self._change_stream_thread.stop()
        self._change_stream_thread.join(timeout=1)
        self._log.info("Closed change stream thread")

    def send(self, data):
        raise NotImplementedError()
