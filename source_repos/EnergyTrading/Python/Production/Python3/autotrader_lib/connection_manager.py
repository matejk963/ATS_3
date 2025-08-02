#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import division

import calendar
import datetime as DT
import errno
import gzip
import itertools as IT
import logging
import random
import socket
import ssl
import textwrap
import threading
import time
import six
from six.moves import queue
if six.PY3:
    from io import BytesIO as MsgBodyIO
else:
    from cStringIO import StringIO as MsgBodyIO

import amqpstorm
import lxml.etree
import pyotp
import zmq.error

import autotrader_lib.common as COMMON
import autotrader_lib
import autotrader_lib.codec.msgpackcodec
import autotrader_lib.config_helper as ATCONF
import autotrader_lib.mongo_manager as MONGOMANA
import autotrader_lib.sockets as ATSOCK
import autotrader_lib.spy_database as SPYDB
import autotrader_lib.standard_message_adapter as SMA
import autotrader_lib.status
import autotrader_lib.util as ALU


def wait_for_event(obj, action, attrib, error, retry_interval=0.1, max_seconds=60, logger=None):
    # type: (object, str, str, any, float, int, logging.Logger) -> None
    """Base function to wait for custom events until success or max number of retries is reached

    :param obj: object to check for attribute
    :type obj: object
    :param action: description of the action, this will appear in the error if the to time wait is exceeded
    :type action: str
    :param attrib: attribute to check for
    :type attrib: str
    :param error: Error to raise if time is exceeded or another error occurs
    :type error: Error or Exception
    :param retry_interval: time in seconds between retries
    :type retry_interval: int or float
    :param max_seconds: maximal waiting time
    :type max_seconds: int or float
    :param logger: log handler
    :type logger: logging.Logger
    :return:
    """
    if not logger:
        logger = logging
    start_ts = time.time()
    if not hasattr(obj, attrib):
        raise AttributeError("Instance has no attribute %s", attrib)

    while not getattr(obj, attrib):
        now_ts = time.time()
        if six.PY3:
            thread_event = threading.Event
        else:
            thread_event = threading._Event
        if hasattr(obj, "should_die") and isinstance(obj.should_die, thread_event) and obj.should_die.is_set():
            raise error("Not waiting for login reply, because should_die is set...")
        elif now_ts < start_ts + max_seconds:
            logger.debug("waiting for %s (%s seconds now)..", action, int(now_ts - start_ts))
        else:
            raise error("tired of waiting for {}".format(action))
        time.sleep(retry_interval)


def wait_for_login(obj, action="login reply", attrib="connected", retry_interval=0.1, max_seconds=60, logger=None):
    # type: (object, str, str, float, int, logging.Logger) -> None
    """Wait for Login event and raise Login Error if it fails"""
    wait_for_event(obj, action, attrib, ALU.LoginError, retry_interval, max_seconds, logger=logger)


class SpyWorker(ALU.StoppableThread):
    """Stores exchange messages from a queue."""

    def __init__(
            self,
            manager_config,  # type: ATCONF.ManagerConfig
            db_config,  # type: ATCONF.ManagerConfig or None
            spy_queue,  # type: queue.Queue
            logger,  # type: logging.Logger
            *args,
            **kwargs
    ):
        """

        :param manager_config: config of the corresponding connection manager
        :type manager_config: ATCONF.ManagerConfig
        :param db_config: config of the databse used from spying
        :type db_config: ATCONF.MongoConfig or None
        :param spy_queue: queue object holding market messages
        :type spy_queue: queue.Queue
        :param logger: logger object with the logging handlers
        :type logger: logging.Logger
        """
        self._spy_queue = spy_queue
        self._logger = logger
        self._config = manager_config
        self._db_config = db_config
        super(SpyWorker, self).__init__(*args, **kwargs)

    def run(self):
        spy_cls = SPYDB.MongoSpyDatabase
        spy_db = spy_cls(self.__class__.__name__, self._config, self._db_config, self._logger)

        while not self._should_stop.wait(1):
            spy_db.handle_rotation()
            if not self._spy_queue.empty():
                messages = []
                self._logger.info("SpyWorker: Messages in spy_queue %s", self._spy_queue.qsize())
                while not self._spy_queue.empty():
                    message = self._spy_queue.get_nowait()
                    messages.append(message.to_dict())
                    self._spy_queue.task_done()
                    if len(messages) >= 1000:
                        break
                try:
                    spy_db.store(messages)
                except Exception:  # pylint: disable=W0703
                    self._logger.exception("SpyWorker: Exception in SpyWorker while storing messages")


class Connection(ALU.StoppableThread):
    skipped_messages = []

    """Baseclass for connection managers"""

    def __init__(self, manager_config, exchange_config, db_config=None, abort_event=None, logger=None):
        """
        :param manager_config: internal configs for communication with autotrader and for storing market data with spy
        :type manager_config: ATCONF.ManagerConfig
        :param exchange_config: config with all credentials to login to exchange
        :type exchange_config: ATCONF.Config
        :param db_config: config of the database used for Spy (e.g. mongo DB)
        :type db_config: ATCONF.MongoConfig
        :param abort_event: Might set an abort event
        :type abort_event: threading.Event
        :param logger: logger with respective handle
        :type logger: logging.Logger
        :rtype: None
        """
        super(Connection, self).__init__()
        self.logger = logger if logger else logging
        self.init_sockets(manager_config)
        self._configs = exchange_config
        self.nagios = manager_config.nagios
        self.args = manager_config
        self.manager_config = manager_config
        self.db_config = db_config
        self._pub_msg_no = 0
        self.connected = False
        self.connected_since_utc_dt = None              # type: DT.datetime
        self.next_heartbeat_unix_ts = 0
        if not hasattr(self, "should_die"):
            self.should_die = threading.Event() if abort_event is None else abort_event

        self.spy_worker = None
        self.spy_queue = None

        # The following two attributes are for periodically logging the number of received messages.
        self._last_log_timestamp = time.time()
        self._received_message_count = 0

        self.send_to_autotrader_lock = threading.Lock()

    def init_sockets(self, manager_config):
        self.sockets = ATSOCK.ConnectionManagerSockets(
            manager_config.host,
            manager_config.publisher_port,
            manager_config.status_port,
            manager_config.submission_port,
            self.logger
        )
        self._publish_socket = self.sockets.msg_publisher

    def tear_down(self):
        if self.spy_worker:
            self.logger.info("Stopping the spy_worker thread")
            self.logger.info("messages in spy queue: %s", self.spy_queue.qsize())
            self.spy_queue.join()
            self.spy_worker.stop()
            self.spy_worker = None

    def establish(self):
        """
        Enable and start the SPY thread if configured, to capture messages from the exchange and save them in the db.
        """
        if self.manager_config.spy_db:
            self.spy_queue = queue.Queue()
            self.spy_worker = SpyWorker(self.manager_config, self.db_config, self.spy_queue, self.logger)
            self.spy_worker.start()

    def logout(self):
        raise NotImplementedError("")

    def _send_status(self, status, topic):
        """Send status via status socket to autotrader

        :type status: dict[str, any]
        :type topic: str
        :return:
        """
        if not self.sockets:
            self.logger.debug("Could not send status because of missing sockets")
            self.should_die.set()
            return
        payload = dict(timestamp=DT.datetime.utcnow(),
                       type=topic,
                       status=status)  # TO DO payload should be similar to each other
        packed_msg = autotrader_lib.codec.msgpackcodec.serialize(payload)
        self.sockets.status_publisher.send(packed_msg)
        self.logger.debug("sent status %s: %s", topic, status["text"])

    def send_status_change(self, status):
        """wrapper to send status if status is changing via status socket to autotrader

        :type status: dict[str, any]
        """
        self._send_status(status, "change")

    def send_heartbeat(self):
        """Send heartbeat if time interval to wait has passed"""
        now = time.time()
        if now >= self.next_heartbeat_unix_ts:
            try:
                self._send_status(
                    dict(autotrader_lib.status.Status.ONLINE, since=self.connected_since_utc_dt), "heartbeat"
                )
            except zmq.error.ZMQError as err:
                if err.errno != errno.EINTR:
                    raise
            self.next_heartbeat_unix_ts = now + self.args.heartbeat_interval_sec
            self.logger.debug("Sent heartbeat update to autoTRADER.")

    def send_json_to_autotrader(self, properties, body):
        """Send message to autotrader via zmq socket as multipart

        :type properties: dict
        :type body: dict
        """
        with self.send_to_autotrader_lock:
            header = properties.get("headers", {})
            self._received_message_count += 1
            now_ts = time.time()
            # Every ~60 seconds, log the number of messages
            if now_ts > self._last_log_timestamp + COMMON.MINUTE:
                self.logger.info("Received %d messages in the last %.1f seconds",
                                 self._received_message_count,
                                 now_ts - self._last_log_timestamp)
                self._last_log_timestamp = now_ts
                self._received_message_count = 0

            self._pub_msg_no = (self._pub_msg_no + 1) % 4294967296  # 2**32
            payload = dict(pub_msg_no=self._pub_msg_no,
                           timestamp=DT.datetime.utcnow(),
                           header=header,
                           properties=properties,
                           body=body)
            packed_msg = autotrader_lib.codec.msgpackcodec.serialize(payload)
            self._publish_socket.send(packed_msg)

    def wait_for_login(self, action="login reply", attrib="connected", retry_interval=0.1, max_seconds=60):
        """Wait for Login event and raise Login Error if it fails"""
        wait_for_event(
            self, action, attrib, ALU.LoginError, retry_interval, max_seconds, logger=self.logger
        )


class M7Consumer(threading.Thread):
    def __init__(self, amqp_channel, connection_failure_signal, logger, connection):
        super(M7Consumer, self).__init__()
        self._connection = connection
        self._channel = amqp_channel  # type: amqpstorm.Channel
        self._connection_failure_signal = connection_failure_signal
        self.logger = logger
        self.pwd_changed = threading.Event()

    def run(self):
        try:
            self._channel.start_consuming(auto_decode=False)  # this blocks
        except amqpstorm.AMQPError as err:
            self._handle_amqp_error(err)
        except COMMON.GapDetectedException as e:
            self.logger.error("Scheduling a restart of exchange: {}".format(str(e.exchange_id)))
        except Exception as err:
            self.logger.exception("consumer")
            self.logger.critical("unknown error in consumer: %r", err)
        finally:
            self.logger.warning("Connection failed while consuming")
            self._connection_failure_signal.set()

    def _handle_amqp_error(self, err):
        """
        Handles AMQP errors. We will get an error message on successfully changing the exchange password

        :param err: error to be handled
        :type err: amqpstorm.AMQPError
        :rtype: None
        """

        self.logger.error("connection failed while consuming: %r", err)
        if COMMON.ErrorMsgs.pwd_changed in str(err):
            try:
                self._connection.close()
            except Exception:
                self.logger.exception("cannot close amq channel in Consumer")
            finally:
                self.pwd_changed.set()

    def stop(self):
        self.logger.info("stopping consumer...")
        try:
            self._channel.stop_consuming()
        except Exception:
            self.logger.exception("consumer cannot be stopped, hopefully already dead")


class M7Connection(Connection, SMA.M7TranslatorMixIn):
    # Only log every 1000th timeout WARNING log for OMT status response timeout
    SILENCE_OMT_TIMEOUT_LOG = 10000
    OMT_STATUS_RESPONSE_TIMEOUT = 60
    THROTTLING_TIMEOUT_MESSAGE = "No ThrottlingStatusResponse has been received for more than {} seconds".format(
        OMT_STATUS_RESPONSE_TIMEOUT)
    # avoid logging the body of the message if it contains one of the following messages in the body
    skipped_messages = [b"PblcOrdrBooksDeltaRprt", b"MsgRprt", b"PblcTradeConfRprt", b"SYSTEM_ALIVE",
                        b"HubToHubHeartbeat", b"HubToHubNtf"]
    exchange_id = None  # This ID will be used in the sent messages
    _broadcast_queue_name_template = "m7.broadcastQueue.{}"
    _response_queue_name_template = "m7.private.responseQueue.{}.queue1"

    def __init__(self, manager_config, m7_config, mongo_config, fernet, abort_event=None, logger=None):
        """
        :param manager_config: Configurations to connect to Autotrader via zmq sockets
        :type manager_config: ATCONF.ManagerConfig
        :param m7_config: Configurations to connect to M7 type exchange (M7ManagerConfig or derived)
        :type m7_config: ATCONF.EpexConfig
        :param mongo_config: config of the Mongo DB
        :type mongo_config: ATCONF.MongoConfig
        :param fernet: cryptography class
        :type fernet: type[cryptography.fernet.Fernet]
        :param abort_event: threading.event set in case of abort
        :type abort_event: threading.Event
        :param logger: log handler
        :type logger: logging.Logger
        :rtype: None
        """
        super(M7Connection, self).__init__(manager_config, m7_config, mongo_config, abort_event, logger)
        self._config_no = 1
        # the first call to establish will then use the first config:
        self._connection = None
        self._channel = None
        self._channel_no_ack = None
        self._response_queue_name = None
        self._broadcast_queue_name = None
        self._last_gap_detection_ts = time.time()
        self._gap_detection_dict = {}
        self._last_throttling_status_ts = None
        self._log_silencer = 0
        self.session_id = None
        configs = (self._configs.first_connection, self._configs.second_connection)
        logger.debug("available connections:\n  {}" .format("\n  ".join([str(x) for x in configs])))
        self.earliest_reconnection_time = 0
        self.reconnect_delay_s = 1
        self.logger = logger
        self.user_id = None
        self.account_id = None
        self.consumer = None
        self.allowed_products = {}

        # When non-empty halts login requests when an "Auth error" is received with kept halt reason
        # due to a missing/invalid TOTP key or possibly low AMQP performance
        self._login_on_hold = ""  # type: str
        self._last_totp_key_hash = hash(None)  # type: int or None
        # If we have requested a password change but not yet received confirmation,
        # then we store the new password in this field.
        self.changed_password = None
        # self.db_config is set to be mongo_config in super
        self.mongo_manager = MONGOMANA.MongoManager(self.db_config, fernet, epex_config=m7_config, logger=self.logger)

    def _select_next_config(self):
        self._config_no = (self._config_no + 1) % self._configs.n_configs
        return self._configs.get_by_id(self._config_no)

    def _get_current_config(self):
        """

        :rtype: AmqpConnectionConfig
        """
        return self._configs.get_by_id(self._config_no)

    @property
    def password(self):
        """
        Read the password from MongoDB or system.cfg.
        Reading from system.cfg serves as fallback mechanism.

        :return: The password
        :rtype: str
        """

        pwd = self.mongo_manager.get_exchange_password(self.exchange_id)
        if six.PY3 and type(pwd) == six.binary_type:
            return str(self.mongo_manager.get_exchange_password(self.exchange_id), 'utf-8')
        return self.mongo_manager.get_exchange_password(self.exchange_id)

    def get_totp_key(self):
        """
        Read the TOTP key from MongoManager (MongoDB or system.cfg).

        :return: The TOTP key
        :rtype: str or None
        """
        return self.mongo_manager.get_exchange_totp_key(self.exchange_id)

    @staticmethod
    def generate_totp_code(totp_key):
        """
        Generate authentication TOTP code based on current time.

        :param totp_key: TOTP key
        :type totp_key: str
        :return: The TOTP code or None if TOTP key
        :rtype: str
        """
        return pyotp.TOTP(totp_key).now()

    def set_exchange_password(self, exchange, user, password):
        """
        Encrypt and write password to mongo.

        :param exchange: exchange id
        :type exchange: str
        :param user: user id
        :type user: str
        :param password: new exchange password as plain
        :type password: str
        :rtype: None
        """
        self.mongo_manager.set_exchange_password(exchange, user, password)
        self.changed_password = None

    def handle_pwd_change_request(self):
        """
        Saves the password on success exchange response and informs aT.

        :rtype: None
        """
        if self.changed_password:
            self.set_exchange_password(self.exchange_id, self.user_id, self.changed_password)
            self.send_password_change_response(success=True)
        else:
            # this probably could happen, if someone changes the password via ComTrader.
            # We cannot store the new password in that case.
            self.logger.error("Received password change notification, without having issued a change password request!")

    def send_password_change_response(self, success):
        """
        Send password change response to autotrader.

        :param success: Flag if the password change was successful
        :type success: bool
        :rtype: None
        """

        self.send_json_to_autotrader({}, {  # AutotraderCoreMainParent._core_update_from_json_callback
            "exchange": self.exchange_id,
            "message_type": COMMON.Response.password_changed,
            "success": success,
        })

    def tear_down(self):
        if self.consumer:
            self.logger.debug("Stopping consumer...")
            self.consumer.stop()
            self.consumer.join()
            self.consumer = None

        if self.connected:
            try:
                self.logout()
            except Exception as err:
                self.logger.warning("logout failed: {}".format(err))

        # if we close the connection but not the channel, an IO thread remains
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                self.logger.exception("channel_close")
        if self._channel_no_ack:
            try:
                self._channel_no_ack.close()
            except Exception:
                self.logger.exception("channel_no_ack_close")

        if self._connection:
            try:
                self._connection.close()
            except Exception:
                self.logger.exception("connection_close")

        self._channel = self._channel_no_ack = self._connection = self._response_queue_name = None
        self._broadcast_queue_name = None
        self.connected = False
        self.send_status_change(autotrader_lib.status.Status.NO_CONNECTION)
        self.send_status_change(autotrader_lib.status.Status.HALT)

        self._gap_detection_dict.clear()

        super(M7Connection, self).tear_down()

    def start_consumer(self, amqp_channel, abort_event):
        self.logger.debug("Starting consumer thread.")
        consumer = M7Consumer(amqp_channel, abort_event, self.logger, self._connection)
        consumer.start()
        self.consumer = consumer
        return consumer

    def _wait_for_login_success(self):
        """Waits until the confirmation for the login is received"""
        self.logger.debug("waiting for the login reply...")
        self.wait_for(
            self._receive_login_message,
            debug_msg_meanwhile="waiting for the login reply",
            timeout_exception=ALU.LoginError("tired of waiting for login reply")
        )

    def _wait_for_account_information_report(self):
        """After the Account information request is sent out this function waits for 60 seconds to receive the
        Account information report as a response for it, and stores its content in self.allowed_products"""
        self.logger.debug("waiting for account information report...")
        self.wait_for(
            self._receive_account_info,
            debug_msg_meanwhile="waiting for the account information report",
            timeout_warning="Account information report is not received, using default allowed product list...",
        )

    def _await_reconnection_delay(self):
        """M7 exchanges needs us to use exponential back-off when reconnection fails repeatedly. Each
        time the reconnect delay is roughly quadrupled, with some random deviation thrown in to
        counter DDOS, up to roughly 300s."""
        if self.earliest_reconnection_time == 0:
            # first time - we don't wait at all
            self.earliest_reconnection_time = time.time()
        if self._config_no != 0:
            return
        # the first config of at least the second round..
        current_delay = self.earliest_reconnection_time - time.time()
        if current_delay > 0:
            self.logger.info("reconnect delayed by %s seconds", current_delay)
        elif current_delay < -10 * COMMON.MINUTE:
            # The connection has not failed for 10 minutes. Reset delay.
            # The 10 minutes is an arbitrary value to indicate a period of normal operation
            # The only thing I could find in the M7 documentation is one sentence:
            # "Clients must use an exponential back-off when the re-connection repeatedly fails."
            self.reconnect_delay_s = 1
        while time.time() < self.earliest_reconnection_time:
            time.sleep(.1)
            if self.should_die.is_set():
                return
        # increase delay:
        self.reconnect_delay_s = min(
            random.uniform(3.6, 4.4) * self.reconnect_delay_s,
            random.uniform(0.8, 1.2) * 300)
        self.earliest_reconnection_time = time.time() + self.reconnect_delay_s
        self.logger.debug("next use of connection 0 will be permitted in %s seconds",
                          int(round(self.reconnect_delay_s)))

    def _connect(self, cfg):
        """Connect to the exchange and log in using the provided configuration

        :param cfg: the exchange config to use for the connection
        """
        self.logger.debug("connecting to (%s) %s...", self._config_no, cfg)
        self._await_reconnection_delay()
        if self.should_die.is_set():
            self.logger.info("connecting aborted")
            return
        if cfg.certificate and cfg.ca_certificate:
            if six.PY2:
                ssl_options = dict(ca_certs=cfg.ca_certificate,
                                   certfile=cfg.certificate,
                                   keyfile=cfg.certificate,
                                   cert_reqs=ssl.CERT_NONE,
                                   ssl_version=ssl.PROTOCOL_TLSv1_2)
            else:
                ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLSv1_2)
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_context.load_cert_chain(certfile=cfg.certificate, keyfile=cfg.certificate)
                ssl_context.load_verify_locations(cafile=cfg.ca_certificate)
                ssl_options = {"context": ssl_context}
        else:
            self.logger.debug("No certificate configured. "
                              "Trying to connect without custom ssl options.")
            ssl_options = None
        self._connection = amqpstorm.Connection(
            cfg.host, cfg.username, self.password, cfg.port,
            virtual_host=cfg.virtual_host, heartbeat=30, timeout=15,
            ssl=ssl_options is not None, ssl_options=ssl_options)
        self.logger.info("connected to %s", cfg)
        self.logger.info("server props: %s", self._connection.server_properties)

        self._channel = self._connection.channel()
        self._channel.confirm_deliveries()
        # Create a channel without consumer to send out non-essential messages towards EPEX
        self._channel_no_ack = self._connection.channel()

        name = self._response_queue_name_template.format(cfg.username)
        self._response_queue_name = self._channel.queue.declare(queue=name,
                                                                exclusive=True,
                                                                auto_delete=True)["queue"]
        broadcast_queue_name = self._broadcast_queue_name_template.format(cfg.username)
        self._broadcast_queue_name = self._channel.queue.declare(
            queue=broadcast_queue_name,
            exclusive=False,
            auto_delete=True,
            arguments={"x-queue-master-locator": "client-local",
                       # If messages are not consumed
                       # after x-message-ttl milliseconds,
                       # epex may drop them (in which case we expect gap-detection
                       # to kick in)
                       "x-message-ttl": 10000,
                       }
        )["queue"]
        self.logger.debug("broadcast queue declared: %r, %s", broadcast_queue_name, self._broadcast_queue_name)

        self._send_login()
        self._wait_for_login_success()
        self.connected = True

    def _initialise(self):
        """Initialisation of the exchange connection after the connection and login were successful"""
        self._send_account_information()
        self._wait_for_account_information_report()
        # we're logged in, which means that the broadcast queue should be present now:

        self._channel.basic.consume(self._on_broadcast, self._broadcast_queue_name, no_ack=True)
        self._channel.basic.consume(self._on_private_message, self._response_queue_name, no_ack=False)
        self._send_delete_all_orders()
        # M7 exchanges sometimes (mostly after a market halt) needs time
        # to process incoming messages of all market participants.
        # We have to give them this time.
        time.sleep(5)
        self.send_status_change(autotrader_lib.status.Status.ONLINE)
        self.connected_since_utc_dt = DT.datetime.utcnow()

    def establish(self, never_reconnect=False, use_next_config=True):
        """Does not return until there is a connection and the user is logged in (except should_die).

        :param never_reconnect: sets should_die after the first failed connection attempt.
        """
        # enable SPY if set in system.cfg
        super(M7Connection, self).establish()

        # we manage be-nice-and-wait-a-little delays for making connections:
        while not self.should_die.is_set():
            try:
                if use_next_config:
                    cfg = self._select_next_config()
                else:
                    cfg = self._get_current_config()
                self._connect(cfg)
                self._initialise()

                return self._channel
            except (ALU.ConnectionError, amqpstorm.AMQPError, ALU.LoginError, socket.error) as err:
                self.logger.exception("connection error")
                self.logger.error("failed to connect: %s", err)
                try:
                    self._channel.queue.delete(self._response_queue_name)
                except Exception:
                    self.logger.exception("queue_delete")
                if self._channel:
                    try:
                        self._channel.close()
                    except Exception:
                        self.logger.exception("channel_close")
                if self._channel_no_ack:
                    try:
                        self._channel_no_ack.close()
                    except Exception:
                        self.logger.exception("channel_no_ack_close")
                if self._connection:
                    try:
                        self._connection.close()
                    except Exception:
                        self.logger.exception("connection_close")
                if never_reconnect:
                    self.should_die.set()

    def _process_heartbeat(self, properties):
        """Process a heartbeat message from EPEX."""
        queue_lag = "%.5f" % (time.time() - properties["headers"]["server-timestamp"] / 1000)
        self.logger.debug("EPEX heartbeat queue_lag: %s", queue_lag)
        self.mongo_manager.update_queue_lag("EPEX", float(queue_lag))

        if self.nagios is not None:
            ALU.touch_nagios_file(self.nagios)

    def _try_translate_body(self, body, properties):
        """Try to parse the message from EPEX and forward the message to autotrader parent.

        :param body: raw xml body of the message
        :type body: bytes
        :param properties: properties of the amqp message
        :type properties: dict
        :return: translated body if successful or None
        :rtype: dict or None
        """
        try:
            skip_log = any([msg_type in body for msg_type in self.skipped_messages])
            if not skip_log:
                self.logger.debug("received message: %s", body)

            translated_body = self.from_xml_to_json(body)
            if properties.get("timestamp") is not None:
                # properties["timestamp"] is a time struct without milliseconds
                # properties also contains headers with the same timestamp but ms information
                # first we try to get the more accurate info from the header
                # if not present, we fall back on the less accurate timestamp in the properties
                header_timestamp_ms = properties.get("headers", {}).get("server-timestamp")
                properties["timestamp"] = calendar.timegm(properties["timestamp"])
                if header_timestamp_ms is not None:
                    translated_body["timestamp"] = header_timestamp_ms / 1000.
                else:
                    translated_body["timestamp"] = properties["timestamp"]
            else:
                translated_body["timestamp"] = time.time()

            self.send_json_to_autotrader(properties, translated_body)
        except ALU.MessageTypeNotImplemented as err:
            translated_body = None
        except Exception as err:
            translated_body = None
            self.logger.warning("Cannot parse xml due to the following error: %s: %s", err.__class__.__name__, err)
        return translated_body

    def _try_ack_message(self, amqp_msg):
        """Try to send an Ack for the received message from EPEX.

        :param amqp_msg: received amqpstorm message object
        :type amqp_msg: amqpstorm.Message
        """
        try:
            # we are required to ack the message so as to keep our server-side queue clean:
            amqp_msg.ack()
        except Exception as err:
            if COMMON.ErrorMsgs.pwd_changed in str(err):
                self.logger.debug("cannot ack message. connection closed due to password change.")
                self.handle_pwd_change_request()
            else:
                self.logger.exception("on message ack")
                split_body = textwrap.wrap(amqp_msg.body, 10000)
                body_fragments = len(split_body)
                for i, line in enumerate(split_body):
                    self.logger.critical("failed to ack message (%d/%d): %r, %r: %s",
                                         i + 1, body_fragments, line, amqp_msg.properties, err)

    def _try_save_spy_message(self, body, properties, translated_body):
        """Try to save the raw message and the corresponding translated message in the spy DB.

        :param body: the raw amqp message body (xml)
        :type body: string
        :param properties: properties of the amqp message
        :type properties: dict
        :param translated_body: translated message dict
        :type translated_body: dict
        """
        try:
            message = SPYDB.Message(self.connected_since_utc_dt,
                                    DT.datetime.utcfromtimestamp(translated_body["timestamp"]),
                                    properties.get("headers", {}),
                                    properties,
                                    translated_body.get("message_type", ""),
                                    body,
                                    translated_body)
            self.spy_queue.put(message)
        except Exception as ex:
            self.logger.exception("failed to save message: %s", ex)

    def _get_message(self, resp_message):  # type: (amqpstorm.Message) -> tuple[str, dict]
        """Retrieves the body and properties from an amqpstorm message"""
        body = resp_message.body
        properties = resp_message.properties
        return body, properties

    def _on_broadcast(self, resp_message):
        """
        Process messages that arrived on the Broadcast queue. Differs from private messages in the fact that this method
        triggers a gap detection, and does not acknowledge the message, unlike the one for private messages.

        :param resp_message: A message that has a body and a header.
        :type resp_message:
        """
        body, properties = self._get_message(resp_message)
        sent_to_at = self._on_message(body, properties)
        self._detect_gaps(properties.get("headers", {}), restart_on_gap=sent_to_at)

    def _on_private_message(self, resp_message):
        """
        Process messages that arrived on the private queue. It differs from broadcast in the fact that it tries to
        acknowledge the message, and does not trigger gap detection.

        :param resp_message: A message that has a body and a header.
        :type resp_message:
        """
        body, properties = self._get_message(resp_message)
        self._on_message(body, properties)
        self._try_ack_message(resp_message)

    def _on_message(self, body, properties):
        """
        Process incoming messages.

        :param body: Message body
        :param properties: Message properties
        :returns: True, if a non-empty data-message was sent to autoTRADER, False otherwise.
                  Note: This means that we return False for heartbeats
        :rtype: bool
        """
        current_timestamp = time.time()
        if (
                self._last_throttling_status_ts
                and self._last_throttling_status_ts + self.OMT_STATUS_RESPONSE_TIMEOUT < current_timestamp
        ):
            self._log_silencer = ALU.silence_logs(self._log_silencer,
                                                  self.THROTTLING_TIMEOUT_MESSAGE,
                                                  self.logger,
                                                  maximum_counter=self.SILENCE_OMT_TIMEOUT_LOG)

        if properties.get("content_encoding") == "gzip":
            body = gzip.GzipFile(fileobj=MsgBodyIO(body)).read()
            properties["content_encoding"] = ""

        translated_body = None
        if body.startswith(b"SYSTEM_ALIVE") and "heartbeat" in properties.get("content_type", ""):
            self._process_heartbeat(properties)
        else:
            translated_body = self._try_translate_body(body, properties)
            if translated_body and translated_body.get("message_type") == COMMON.EpexResponse.omt_status:
                # Using time.time() to include queue lag in the time difference calculation
                self._last_throttling_status_ts = time.time()
                self._log_silencer = 0  # Initialize the log silencer

        if self.spy_worker and translated_body:
            self._try_save_spy_message(body, properties, translated_body)
        return translated_body is not None

    def _send_login(self):
        """
        Send a request for a login to the queue.
        If the TOTP key is specified, add the code to the request.
        If the login is held up due to waiting for the key, return an exception.
        Once the key is received, restore the login procedure.
        """
        totp_key = self.get_totp_key()
        self._totp_key_available = bool(totp_key)

        # Disables the halt if a new TOTP key appears
        if hash(totp_key) != self._last_totp_key_hash:
            self._login_on_hold = ""

        if self._login_on_hold:
            self._send_exchange_halt()
            raise ALU.LoginError(
                "login on hold due to previous authentication error. "
                "Set TOTP key via REST API or restart with the proper key in the config file."
            )
        self._last_totp_key_hash = hash(totp_key)

        login_body_templ = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<LoginReq"
            " xmlns=\"http://www.deutsche-boerse.com/m7/v6\""
            " user=\"{user}\""
            " force=\"true\""
            " disconnectAction=\"{disc_action}\""
            + (" authVerificationCode=\"{totp_code}\"" if self._totp_key_available else "")
            + " throttlingUserAction=\"HIBE_USER_ORDERS\">"
            "<StandardHeader marketId=\"{exchange}\"/>"
            "</LoginReq>"
        )
        login_body = login_body_templ.format(
            user=self._get_current_config().username,
            disc_action=self._get_current_config().disconnect_action,
            totp_code=self.generate_totp_code(totp_key) if self._totp_key_available else None,
            exchange=self.exchange_id
        )
        self._send_inquiry("login", login_body)

    def _send_account_information(self):
        account_info_request_body_templ = """<AcctInfoReq xmlns="http://www.deutsche-boerse.com/m7/v6">
                <StandardHeader marketId="EPEX"/>
                <acctId>{}</acctId>
            </AcctInfoReq>""".format(self.account_id)
        self._send_inquiry("acc_info", account_info_request_body_templ)

    def logout(self):
        logout_body_templ = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<LogoutReq xmlns=\"http://www.deutsche-boerse.com/m7/v6\""
            "        sessionId=\"{session}\">"
            "    <StandardHeader marketId=\"{exchange}\" />"
            "</LogoutReq>")
        self._send_inquiry("logout", logout_body_templ.format(session=self.session_id, exchange=self.exchange_id))

    def _send_delete_all_orders(self):
        body = autotrader_lib.templates.epex_modify_all_orders("DELE", self.user_id)
        self.logger.debug("forwarding delete all orders to %s %s", self.exchange_id, body)
        corr_id = "omt.{}.1".format(COMMON.Request.order_delete_all)
        self.send_request({"correlation_id": corr_id}, body, "m7.request.management")
        self.logger.info("delete all autotrader orders forwarded to %s", self.exchange_id)

    def _send_inquiry(self, correlation_id, body):
        self.logger.debug("sending inquiry %r: %r", correlation_id, body)
        properties = dict(correlation_id=correlation_id)
        self.send_request(properties, body, routing_key="m7.request.inquiry")

    def _detect_gaps(self, header, restart_on_gap):
        """
        Stores the current message's header information for later gap detection, and checks if the message is in
        the correct order.
        :type header: dict
        :param restart_on_gap: Whether we should restart on a gap (if False, we just log the gap)
        :type restart_on_gap: bool

        """
        current_group = header.get("x-m7-group-id")
        current_sequence = header.get("x-m7-group-sequence")
        if current_sequence is not None:  # Rarely, but sometimes the group sequence is missing, so it should be checked
            if current_group not in self._gap_detection_dict:
                self._gap_detection_dict.update({current_group: current_sequence})
            elif current_group:
                self._gap_detection_dict[current_group] += 1
                if current_sequence != self._gap_detection_dict[current_group]:
                    self.logger.debug("Gap detection: Expected sequence for group %s is %s, but we received %s",
                                      current_group, self._gap_detection_dict[current_group], current_sequence)
                    self.logger.debug("Gap detection: Full header of unexpected message is %s",
                                      header)
                    if restart_on_gap:
                        self.logger.error("Gap in sequence id detected, restart needed")
                        raise COMMON.GapDetectedException(self.exchange_id)
                    else:
                        self.logger.info("Found a gap in the sequence_id of a non-critical message; "
                                         "we can safely resume normal operation without further handling.")
                        self._gap_detection_dict[current_group] = current_sequence
        else:
            self.logger.debug("Received message without sequence number for gap detection. Full header %s", header)

    def send_request(self, properties, body, routing_key):
        """Send to exchange. NOT thread-safe!"""
        if self._channel is None:
            raise ALU.ConnectionError("M7Channel was not created (should_die is {})".format(self.should_die.is_set()))
        assert self._channel is not None
        cfg = self._get_current_config()
        random_correlation_id = str(random.randint(767554011, 2342986374))
        default_properties = dict(app_id=cfg.app_id, user_id=cfg.username,
                                  content_type="x-m7/request; version=6.0",
                                  headers={}, delivery_mode=1,
                                  correlation_id=random_correlation_id,
                                  reply_to=self._response_queue_name)
        amqp_message = {"exchange": "m7.requestExchange.{}".format(cfg.username),
                        "routing_key": routing_key,
                        "body": body,
                        "mandatory": True,
                        "properties": dict(default_properties, **properties)}
        delivery_failed = False
        if routing_key == COMMON.M7RoutingKey.throttling:
            self._channel_no_ack.basic.publish(**amqp_message)
        else:
            delivery_failed = not self._channel.basic.publish(**amqp_message)
        if delivery_failed:
            if b"ChgPwdReq" in body:
                # We don't log any passwords
                self.logger.error("message delivery failed (properties=%r, message_type=%s)",
                                  properties, COMMON.Request.change_password)
            else:
                self.logger.error("message delivery failed (properties=%r, body=%r)", properties, body)
            raise ALU.ConnectionError()

    @staticmethod
    def parse_account_information_report(body):
        tree = lxml.etree.fromstring(body)
        standard_map = "{{{}}}".format(tree.nsmap[None])
        account_tree = tree.find("{0}AcctList/{0}Acct".format(standard_map))
        allowed_products = {}
        if account_tree is not None:
            allowed_products = {
                "state": account_tree.attrib["state"],
                "name": account_tree.attrib["name"],
                "products": [product.text for product in
                             account_tree.findall("{}prodName".format(standard_map))]
            }
        return allowed_products

    def wait_for(self, func, timeout=60, debug_msg_meanwhile="waiting", timeout_warning="timeout",
                 timeout_exception=None):
        """Repeat the execution of the function until it returns True or the time expires.

        If the timeout is reached, raises an exception, if specified, or only logs a warning message.

        :param func: Function to execute
        :type func: () -> bool
        :param timeout: Timeout (in seconds) after which the repetition ends
        :type timeout: int
        :param debug_msg_meanwhile: Message to the debugger, which will be displayed each time func is called
        :type debug_msg_meanwhile: str
        :param timeout_warning: Warning message to the logger when the timeout is reached and an exception is not raised
        :type timeout_warning: str
        :param timeout_exception: If specified, raises this particular exception when the timeout is reached
        :type timeout_exception: Exception or None
        """
        start_ts = time.time()

        for attempt in IT.count(1):
            if func():
                break

            if attempt % 50 == 0:
                now_ts = time.time()
                if now_ts < start_ts + timeout:
                    self.logger.debug("%s (%.0f seconds now)...", debug_msg_meanwhile, now_ts - start_ts)
                else:
                    if timeout_exception:
                        raise timeout_exception
                    self.logger.warning(timeout_warning)
                    break

            time.sleep(.1)  # wait a bit before polling again

    def _receive_account_info(self):
        """Receive acc_info message from AMQP channel."""
        msg = self._channel.basic.get(queue=self._response_queue_name, no_ack=False, to_dict=False, auto_decode=False)
        if msg and msg.correlation_id == "acc_info":
            msg.ack()
            if msg.properties.get("content_encoding") == "gzip":
                body = gzip.GzipFile(fileobj=MsgBodyIO(msg.body)).read()
            else:
                body = msg.body
            self.allowed_products = self.parse_account_information_report(body)
            self.logger.debug("Allowed products: %s", self.allowed_products)
            return True
        return False

    def _receive_login_message(self):
        """Receive login message from AMQP channel or raise the exception when receive an auth error or should die."""
        if self.should_die.is_set():
            raise ALU.LoginError("should_die is set...")

        msg = self._channel.basic.get(queue=self._response_queue_name, no_ack=False, to_dict=False, auto_decode=False)

        if not msg or msg.correlation_id != "login":
            return False

        msg.ack()
        if msg.properties.get("content_encoding") == "gzip":
            body = gzip.GzipFile(fileobj=MsgBodyIO(msg.body)).read()
        else:
            body = msg.body

        if b"UserRprt" in body:
            try:
                tree = lxml.etree.fromstring(body)
                for child in tree.getchildren():
                    if "Usr" in child.tag:
                        self.session_id = (child.attrib.get("sessionId"))
                        self.user_id = (child.attrib.get("usrId"))
                        self.account_id = (child.attrib.get("defaultAcctId"))
                    else:
                        self.session_id = None
                        self.user_id = None
                        self.account_id = None
            except Exception as err:
                raise ALU.LoginError(err)

            self.logger.info("successfully logged in with session ID %s. msg: %s",
                             self.session_id, body)
            if not self._totp_key_available:
                self.logger.warning("enable 2FA on your account and send the TOTP key")
            return True

        if b"ErrResp" in body and b"Auth error" in body:
            #  When an "Auth error" occurs logging into the account is halted until the key is changed
            #  and an error message is passed to aT
            if self._last_totp_key_hash == hash(None):
                error_msg = "TOTP authentication error due to missing TOTP key."
                self._login_on_hold = "missing TOTP key"
            else:
                error_msg = "TOTP authentication error due to invalid TOTP key or low message transfer performance."
                self._login_on_hold = "invalid TOTP key"

            raise ALU.LoginError(error_msg)
        else:
            raise ALU.LoginError(body)

    def _send_exchange_halt(self):
        self.send_json_to_autotrader({}, {
            "exchange": self.exchange_id,
            "message_type": COMMON.Response.exchange_halt,
            "data": {"remove_orders": True, "critical": True, "halt_reason": self._login_on_hold}
        })
