# -*- coding: utf-8 -*-
import datetime as DT
import time

import pymongo

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU
import six


class Message(object):
    """Message to be saved in the spy database"""

    def __init__(self,
                 session_dt=None, message_dt=None,
                 header=None, properties=None,
                 message_type=None, raw_payload=None, translated_payload=None):
        """
        :type session_dt: datetime.Datetime
        :type message_dt: datetime.Datetime
        :type header: dict
        :type properties: dict
        :type message_type: str
        :type raw_payload: str
        :type translated_payload: dict
        """

        self.session_dt = session_dt
        self.message_dt = message_dt
        self.header = header
        self.properties = properties
        self.message_type = message_type
        self.raw_payload = raw_payload
        self.translated_payload = translated_payload

    def to_dict(self):
        """Exports the message object to a dict"""
        return self.__dict__


class SpyDatabase(object):
    """Base class manager of database connection for spy

    The class is responsible for:
     * creating database records;
     * storing the records to the database files
    """

    def __init__(self, exchange_id, manager_config, db_config, logger):
        """

        :param exchange_id: identifyer of the exchange or connection manager used for spying
        :type exchange_id: str
        :param manager_config: configuration of the corresponding connection manager
        :type manager_config: :class:`autotrader_lib.config_helper.ManagerConfig`
        :param db_config: config of the database used for Spy (e.g. mongo DB)
        :type db_config: :class:`autotrader_lib.config_helper.MongoConfig` or None
        :param logger: logger object handling the corresponding logging
        :type logger: :class:`logging.Logger`
        """
        self._logger = logger
        self._db_collection_names = {}
        self._db = None
        self._path = manager_config.spy_data_path
        self._exchange_id = exchange_id
        self._rotation_hour = manager_config.spy_rotation_hour
        self._delete_after_days = manager_config.spy_delete_collection_after_days
        self._last_rotation = 0
        self.initialize(manager_config, db_config)
        self.handle_rotation()
        self._logger.info("%s: Spy database is initialized", self._exchange_id)

    def _get_utc_now(self):
        # This is a helper function for easier mocking
        return DT.datetime.utcnow()

    def _get_utc_date_today(self):
        return self._get_utc_now().date()

    def initialize(self, manager_config, db_config):
        """Initializes Spy database

        :param manager_config: configuration of the connection manager
        :type manager_config: :class:`autotrader_lib.config_helper.ManagerConfig`
        :param db_config: configuration of the database
        :type db_config: :class:`autotrader_lib.config_helper.MongoConfig` or None
        """
        raise NotImplementedError

    def handle_rotation(self):
        """Handles rotation of the database collections based on the rotation hour specified
        in the connection manager config
        """
        now = time.time()
        if now - self._last_rotation > COMMON.MINUTE:
            self._logger.debug("exchange_id: %s, Rotate", self._exchange_id)
            self._ensure_yesterday()
            self._ensure_today()
            self._ensure_tomorrow()
            self._finalize_old_collections(self._delete_after_days)
            self._last_rotation = now

    def _ensure_yesterday(self):
        """The function makes sure the collection for yesterday is still open for write access right after the midnight.
        The collection for yesterday closes at 0:45.
        """
        utc_yesterday = self._get_utc_date_today() - DT.timedelta(days=1)
        if self._get_utc_now().time() < DT.time(0, 45):
            self._open(utc_yesterday)

    def _ensure_today(self):
        """Opens a collection for today"""
        self._open(self._get_utc_date_today())

    def _ensure_tomorrow(self):
        """Opens a new collection for tomorrow after the rotation hour + 45m"""
        if self._get_utc_now().time() >= DT.time(self._rotation_hour, 45):
            utc_tomorrow = self._get_utc_date_today() + DT.timedelta(days=1)
            self._open(utc_tomorrow)

    def _finalize_old_collections(self, delete_after_days):
        """deletes the collections which are older than delete_after_days days

        :param delete_after_days: days after which the collections are deleted in mongodb
        :type delete_after_days: int
        """
        raise NotImplementedError

    def _unfinished(self):
        """Returns a list of collections, which are open for writing the market data

        :return:
        :rtype: List
        """
        raise NotImplementedError

    def _finalize_collection(self, date):
        """Stops a collection for storing of the market data based on the provided date followed by its dump

        :param date: date specifying a DB collection, which should be finalized
        :type data: :class:`DT.date`
        """
        raise NotImplementedError

    def _open(self, date):
        """Starts a new collection for storing of the market data

        :param date: date specifying a new DB collection
        :type data: :class:`DT.date`
        """
        raise NotImplementedError

    def store(self, messages):
        """Writes market data messages to all open database collections

        :param messages: list of messages being written to the DB. Each message is provided in a form of a dict
        :type messages: List[dict]
        """
        raise NotImplementedError

    def __repr__(self):
        return "Collections: {}".format([repr(x) for x in self._db_collection_names])

    def __len__(self):
        return len(self._db_collection_names)


class MongoSpyDatabase(SpyDatabase):
    """Class utilizing mongo DB database as spy data storage"""

    def __init__(self, exchange_id, manager_config, db_config, logger):
        self._client = None
        super(MongoSpyDatabase, self).__init__(exchange_id, manager_config, db_config, logger)

    def initialize(self, manager_config, db_config):
        """Initializes Mongo DB database for Spy

        :param manager_config: configuration of the connection manager
        :type manager_config: :class:`autotrader_lib.config_helper.ManagerConfig`
        :param db_config: configuration of the database
        :type db_config: :class:`autotrader_lib.config_helper.MongoConfig`
        """
        self.connect(db_config)
        self._db = self._client.get_database(manager_config.spy_mongo_db_name,
                                             write_concern=pymongo.write_concern.WriteConcern(0))
        self._logger.info("%s: Spy database is initialized", self._exchange_id)

        for collection_name in self._db.list_collection_names():
            self._db_collection_names[DT.datetime.strptime(collection_name, "%Y-%m-%d").date()] = collection_name
        self._logger.info("%s: Spy already has %s collections", self._exchange_id, len(self._db_collection_names))

    @ALU.wait_for_it(10)
    def connect(self, db_config):
        """Waits for mongo to be initialized and sets the connection.

        :raise pymongo.errors.ConnectionFailure if the database has not been initialized after 10 seconds.
        """
        # Let's connect and wait that mongo is initialized
        self._client = pymongo.MongoClient(db_config.host, db_config.port,
                                           username=db_config.username, password=db_config.password,
                                           authSource=db_config.auth_source or "autoTRADER")
        if self._client.admin.command("ismaster")["ismaster"]:
            self._logger.info("Spy Mongo client is connected.")
            return True
        return False

    def _open(self, utc_date):
        """Starts a new collection for storing of the market data

        :param utc_date: date in utc specifying a new DB collection
        :type utc_data: :class:`DT.date`
        """
        if utc_date not in self._db_collection_names:
            self._logger.info("%s: Create collection for date %s", self._exchange_id, utc_date)
            self._db_collection_names[utc_date] = "{}".format(utc_date.isoformat())

    def _unfinished(self):
        """Returns a list of collections, which are open for writing the market data

        :return:
        :rtype: List
        """
        return list(self._db_collection_names.keys())

    def store(self, messages):
        """Writes market data messages to database collections not older than 1 day

        :param messages: list of messages being written to the DB. Each message is provided in a form of a dict
        :type messages: List[dict]
        """

        for utc_date, collection_name in six.iteritems(self._db_collection_names):
            if utc_date >= self._get_utc_date_today():
                try:
                    self._logger.debug("%s: Storing %s messages to collection: %s",
                                       self._exchange_id, len(messages),
                                       collection_name)
                    self._db[collection_name].insert_many(messages)
                except Exception:  # pylint: disable=W0703
                    self._logger.exception("%s: Spy error while storing message in DB for date %s in collection %s",
                                           self._exchange_id,
                                           utc_date,
                                           collection_name)

    def _finalize_old_collections(self, delete_after_days):
        """deletes the collections which are older than delete_after_days days

        :param delete_after_days: days after which the collections are deleted in mongodb
        :type delete_after_days: int
        """
        for utc_date in self._unfinished():
            if utc_date <= self._get_utc_date_today() - DT.timedelta(days=delete_after_days):
                self._finalize_collection(utc_date)

    def _finalize_collection(self, utc_date):
        """Finalizing a collection means removing it from the open collections dict and the mongodb

        :param utc_date: date specifying a DB collection, which should be finalized
        :type utc_date: :class:`DT.date`
        """

        try:
            self._db.drop_collection(self._db_collection_names[utc_date])
        except Exception:  # pylint: disable=W0703
            self._logger.exception("%s: Exception while deleting a collection for date %s", utc_date)
        # Remove date from the bookkeeping dict
        self._db_collection_names.pop(utc_date, None)
