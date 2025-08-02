# coding: utf-8


import contextlib
import datetime
import logging
import bson
import bson.son as BSON
import pymongo
import pymongo.errors
import six

import cryptography

import autotrader_lib.common as COMMON
import autotrader_lib.config_helper as ATCONF


class MissingConfigError(ValueError):
    pass


class MongoManager(object):
    """
    Helper class for connection MongoDB to exchange managers
    since they don't have access to autotrader_core.persistence.MongoDBConnector class

    We need to import the cryptography module in epex_conmgr_main and pass it all the way down to here,
    since it is not compatible with the trayport_conmgr.

    """
    def __init__(
            self,
            mongo_config,  # type: ATCONF.MongoConfig
            fernet,  # type: type[cryptography.fernet.Fernet]
            epex_config=None,  # type: ATCONF.EpexConfig or None
            nordpool_config=None,  # type: ATCONF.NordpoolConfig or None
            trayport_config=None,  # type: ATCONF.TrayportConfig or None
            logger=None  # type: logging.Logger or None
    ):
        self.host = mongo_config.host
        self.port = mongo_config.port
        self.database_name = mongo_config.database
        self.username = mongo_config.username
        self.password = mongo_config.password
        self._encryption_key = (None if mongo_config.encryption_key is None
                                else mongo_config.encryption_key.encode("utf-8"))
        self._Fernet = fernet
        self._fernet = None
        self._exchange_config = {}
        self.auth_source = mongo_config.auth_source

        # Setup logging
        if logger is None:
            logger = logging.getLogger("mongo_manager")
        self.logger = logger

        # Setup encryption
        if self._encryption_key:
            self._fernet = self._setup_fernet()
        else:
            # aT REST rejects endpoint if encryption key was not set
            self.logger.warning("No encryption key set!")

        # Setup exchange configs
        if epex_config:
            self._exchange_config[COMMON.Exchange.epex] = epex_config
        if trayport_config:
            self._exchange_config[COMMON.Exchange.trayport] = trayport_config
        if nordpool_config:
            self._exchange_config[COMMON.Exchange.nordpool] = nordpool_config

    def get_exchange_password(self, exchange):
        """
        Get plain exchange password.

        :param exchange: target exchange identifier
        :type exchange: str
        :raises MissingConfigError: on retrieving an exchange password from cfg without exchange configuration set up
        :rtype: str or None
        """
        if self._fernet:
            credentials = self._get_exchange_credentials(exchange)
            if credentials and "password" in credentials:
                return self._fernet.decrypt(credentials["password"]).decode("utf-8")
        if exchange not in self._exchange_config:
            raise MissingConfigError("Cannot get password for not configured exchange {}".format(exchange))
        return self._exchange_config[exchange].password

    def set_exchange_password(self, exchange, user, password):
        """
        Save exchange password.
        Has to be called after getting the exchange response!

        :param exchange: exchange id
        :type exchange: str
        :param user: user id
        :type user: str
        :param password: new exchange password as plain
        :type password: str
        :rtype: None
        """
        if self._fernet:
            if isinstance(password, six.string_types):
                password = password.encode("utf-8")
            self._set_exchange_credentials(exchange, {"password": bson.Binary(self._fernet.encrypt(password))})
            self.logger.info("User {} changed password for {}".format(user, exchange))
        else:
            self.logger.error("Not able to set {} password for User {}: wrong/missing encryption_key!"
                              .format(exchange, user))

    def get_exchange_totp_key(self, exchange):  # type: (str) -> str or None
        """
        Get plain exchange TOTP key from Mongo DB or system config file.

        Reading from system.cfg serves as fallback mechanism. If the encryption key is not configured or TOTP is not
        found in the database, it retrieves TOTP from the system configuration.

        :param exchange: target exchange identifier
        :type exchange: str
        :raises MissingConfigError: on retrieving an exchange TOTP key from cfg without exchange configuration set up
        :rtype: str or None
        """
        if self._fernet:
            totp_key_encrypted = self._get_exchange_totp_key_encrypted(exchange)
            if totp_key_encrypted:
                if six.PY3:
                    return self._fernet.decrypt(totp_key_encrypted).decode('utf-8')
                return self._fernet.decrypt(totp_key_encrypted)
            self.logger.warning("TOTP key not found in database for {}".format(exchange))

        if exchange not in self._exchange_config:
            raise MissingConfigError("Cannot get TOTP key for not configured exchange {}".format(exchange))

        totp_key_from_config = self._exchange_config[exchange].totp_key
        return None if not totp_key_from_config else totp_key_from_config

    def set_exchange_totp_key(self, exchange, totp_key):
        # type: (str, bytes) -> None
        """
        Encrypts and sets exchange TOTP key.

        :param exchange: exchange id
        :type exchange: str
        :param totp_key: new exchange TOTP key as plain
        :type totp_key: bytes
        :rtype: None
        """
        if self._fernet:
            encrypted_totp_key = bson.Binary(self._fernet.encrypt(totp_key))
            self._set_exchange_totp_key(exchange, totp_key=encrypted_totp_key)
            self.logger.info("TOTP key was changed for {}".format(exchange))
        else:
            self.logger.error("Not able to set {} TOTP key: wrong/missing encryption_key!".format(exchange))

    @contextlib.contextmanager
    def db_connection_ctx(self):
        """
        Context manager to connect to mongodb.

        :yields: pymongo.MongoClient, database
        """
        client = pymongo.MongoClient(self.host, self.port,
                                     username=self.username, password=self.password, document_class=BSON.SON,
                                     authSource=self.auth_source)
        try:
            yield client, client.get_database(self.database_name)
        finally:
            client.close()

    def is_encryption_setup(self):
        """
        check if the encryption was setup
        """
        return bool(self._fernet)

    def _setup_fernet(self):
        """
        Get the Fernet instance, setup with the specified encryption key.

        :return: Returns a fernet instance or None on failure.
        :rtype: cryptography.fernet.Fernet or None
        """
        try:
            return self._Fernet(self._encryption_key)
        # I know of TypeError and ValueError
        except Exception:
            self.logger.exception("Not able to setup fernet encryption, wrong/missing encryption_key in system.cfg")

    def _get_exchange_credentials(self, exchange):
        """
        Gets EPEX login credentials.

        :param exchange: target exchange identifier
        :type exchange: str
        :rtype: dict
        """
        update_params = {"object_type": "Credentials", "exchange": exchange}
        with self.db_connection_ctx() as (_, db):
            return db["configuration"].find_one(update_params)

    def _set_exchange_credentials(self, exchange, credentials):
        """
        Sets exchange login credentials.
        The password will be stored encrypted.

        :param exchange: target exchange identifier
        :type exchange: str
        :param credentials: credentials to set
        :type credentials: dict
        :rtype: None
        """
        credentials["alteration_time"] = datetime.datetime.utcnow()
        update_params = {
            "filter": {"object_type": "Credentials", "exchange": exchange},
            "update": {"$set": credentials},
            "upsert": True,
        }

        with self.db_connection_ctx() as (_, db):
            db["configuration"].update_one(**update_params)

    def _get_exchange_totp_key_encrypted(self, exchange):  # type: (str) -> str or None
        """
        Gets EPEX login TOTP key encrypted.

        :param exchange: target exchange identifier
        :type exchange: str
        :rtype: str or None
        """
        get_params = {"object_type": "TotpCredentials", "exchange": exchange}
        with self.db_connection_ctx() as (_, db):
            totp_credentials = db["configuration"].find_one(get_params)
            return totp_credentials["totp_key"] if totp_credentials and totp_credentials["totp_key"] else None

    def _set_exchange_totp_key(self, exchange, totp_key):
        # type: (str, bson.Binary) -> None
        """
        Sets exchange login TOTP key.
        The TOTP key will be stored encrypted.

        :param exchange: target exchange identifier
        :type exchange: str
        :param totp_key: encrypted TOTP key
        :type totp_key: bson.Binary
        :rtype: None
        """
        upsert_params = {
            "filter": {"object_type": "TotpCredentials", "exchange": exchange},
            "update": {
                "$set": {
                    "alteration_time": datetime.datetime.utcnow(),
                    "totp_key": totp_key
                }
            },
            "upsert": True,
        }

        with self.db_connection_ctx() as (_, db):
            db["configuration"].update_one(**upsert_params)

    def update_queue_lag(self, exchange, queue_lag):
        """Update the queue lag value on the exchange object

        :param exchange: the name of the exchange to update the object for
        :type exchange: str
        :param queue_lag: the queue_lag value to add/update to the object
        :type queue_lag: float
        """
        with self.db_connection_ctx() as (_, db):
            db.state.update_one(
                {"object_type": "Exchange", "name": exchange},
                {"$set": {"queue_lag": queue_lag}, "$currentDate": {"alteration_time": True}}
            )
