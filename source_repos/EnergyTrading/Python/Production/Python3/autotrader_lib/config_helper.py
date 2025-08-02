# coding: utf-8
import abc
import argparse
import base64
import copy
import glob
import logging
import os
import re

import six
from six.moves import configparser

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU


ROOT = os.getenv("NBROOT", os.path.expanduser("~"))
PERIOTHEUSROOT = os.path.join(ROOT, "etc")
NAGIOSPATH = os.path.join(ROOT, "var", "run", "autotrader")
LOGSPATH = os.path.join(ROOT, "var", "log", "autotrader")
CERTSPATH = os.path.join(PERIOTHEUSROOT, "certs")
CONFIG_LOG_BLACKLIST = ("password", "logger")
ACTION_LIMIT_CONFIG = os.path.join(PERIOTHEUSROOT, "autotrader", COMMON.ActionLimits.filename)
BROKER_SPEC_CONFIG = os.path.join(PERIOTHEUSROOT, "autotrader", COMMON.BrokerSpecs.filename)


def _get_obj_properties(current_obj):
    """This function takes an object and yields all of its properties by name, value pairs"""
    for property_name, property_value in current_obj.__dict__.items():
        yield property_name, property_value


def properties_log_dump(objects_list, base_log_message, log, property_names_blacklist=CONFIG_LOG_BLACKLIST):
    """This function logs all the properties of objects in a list"""
    for current_obj in objects_list:
        current_obj_name = current_obj.__class__.__name__
        for property_name, property_value in _get_obj_properties(current_obj):
            # skip the blacklisted configs
            if property_name not in property_names_blacklist:
                log.debug("{base_log_message} {obj_name} -> {prop_name}: {prop_value}".format(
                    base_log_message=base_log_message, obj_name=current_obj_name, prop_name=property_name,
                    prop_value=property_value))


def set_nbroot(nbroot):
    global ROOT, PERIOTHEUSROOT, NAGIOSPATH, LOGSPATH, CERTSPATH, ACTION_LIMIT_CONFIG, BROKER_SPEC_CONFIG
    ROOT = nbroot
    os.environ["NBROOT"] = ROOT
    PERIOTHEUSROOT = os.path.join(ROOT, "etc")
    NAGIOSPATH = os.path.join(ROOT, "var", "run", "autotrader")
    LOGSPATH = os.path.join(ROOT, "var", "log", "autotrader")
    CERTSPATH = os.path.join(PERIOTHEUSROOT, "certs")
    ACTION_LIMIT_CONFIG = os.path.join(PERIOTHEUSROOT, "autotrader", COMMON.ActionLimits.filename)
    BROKER_SPEC_CONFIG = os.path.join(PERIOTHEUSROOT, "autotrader", COMMON.BrokerSpecs.filename)


def get_at_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config(six.with_metaclass(abc.ABCMeta, object)):
    """Base Class for Config Settings"""

    # holds system.cfg section name in concrete implementation, thus providing the needed mapping when loading
    # system.cfg automatically via introspection.
    _cfg_section = "UNDEFINED"

    @abc.abstractmethod
    def __init__(self, logger):
        # type: (logging.Logger) -> None
        """abstract method to define all available fields of a config class"""
        self.logger = logger                                # type: logging.Logger

    @abc.abstractmethod
    def _get_defaults(self):
        # type: () -> dict
        """abstract method to get default values of specific config class"""
        pass

    def get_defaults(self):
        return self.set_configs_from_dict(self._get_defaults())

    @abc.abstractmethod
    def check_config_validity(self):
        """abstract method to check config entry validity"""
        pass

    @abc.abstractmethod
    def _set_configs_from_dict(self, config_dict):
        # type: (dict) -> None
        """abstract method to set attributes from config dictionary"""
        pass

    def set_configs_from_dict(self, config_dict):
        # type: (dict) -> Config
        """Set config attributes from defaults dict"""
        section_configs = self._get_defaults()
        section_configs.update(config_dict)
        self._set_configs_from_dict(section_configs)
        return self

    @staticmethod
    def get_bool(setting):
        # type: (str) -> bool
        """static method to get bool from config, assuring original input is 'true' or 'false'"""
        if isinstance(setting, bool):
            return setting
        setting = setting.lower()
        if setting not in ["true", "false"]:
            raise ValueError("bool setting must be 'true' or 'false' string, but is {}".format(setting))
        else:
            return setting == "true"

    def __repr__(self):
        pretty_repr = ""
        for k, v in self.__dict__.items():
            pretty_repr += "    {k}: {v},\n".format(k=k, v=v)
        return pretty_repr


class FileConfig(six.with_metaclass(abc.ABCMeta, Config)):
    """Base Class for Config Settings"""

    def parse_section(self, config_file, config_section):
        if config_file is None:
            return {}
        if not os.path.exists(config_file):
            raise IOError("File not Found: {}, Root set to: {}".format(config_file, ROOT))
        try:
            parser = configparser.SafeConfigParser()
            parser.optionxform = str  # enable case-sensitivity
            parser.read([config_file])
            return dict(parser.items(config_section))
        except configparser.NoSectionError as err:
            self.logger.warning(
                "Could not find section %s in configfile %s (Default Configs will be used where possible). "
                "Root set to: %s", config_section, config_file, ROOT
            )
            self.logger.warning(err)
            return {}

    def _get_configs_from_file(self, config_file, config_section):
        # type: (str, str) -> None
        """abstract method to set configs from file and section and return configs dict"""
        custom_configs = self.parse_section(config_file, config_section)
        self.set_configs_from_dict(custom_configs)

    def get_configs_from_file(self, config_file, config_section=None, use_defaults=False):
        # type: (str, str, bool) -> None
        """wrapper to set configs from file and section and return configs dict"""
        if config_file is None or not os.path.isfile(config_file):
            self.logger.warning("Could not find configfile %s. Root set to: %s", config_file, ROOT)
            if use_defaults:
                self.get_defaults()
                return
        self._get_configs_from_file(config_file, config_section or self._cfg_section)

    def load_config(self, required_fields=None):
        """
        Find the first valid config file or load the default config.

        :param self: autotrader configuration object
        :type self: FileConfig
        :param required_fields: if any are missing, load the default config for this object
        :type required_fields: [str]
        :returns: self
        :rtype: FileConfig
        """
        configuration_path = os.environ.get("SYSTEMCFG_PATH", "/opt/vtse/neurobase/etc/system.cfg")
        for cfg_path in glob.glob(configuration_path):
            if os.path.exists(cfg_path):
                self.get_configs_from_file(cfg_path)
                if (required_fields is None
                        or all([hasattr(self, required) for required in required_fields])):
                    break
        else:
            self.get_defaults()
        return self


class MongoConfig(FileConfig):
    """
    Class to parse MongoDB configs
    Config Section: autotrader_mongo
    """

    _cfg_section = "autotrader_mongo"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger            # type: logging.Logger
        self.host = None                # type: str or None
        self.port = None                # type: int or None
        self.database = None            # type: str or None
        self.username = None            # type: str or None
        self.password = None            # type: str or None
        self.encryption_key = None      # type: str or None
        self.auth_source = None         # type: str or None

    def check_config_validity(self):
        assert isinstance(self.host, six.string_types) and self.host
        assert isinstance(self.port, int) and self.port
        assert isinstance(self.database, six.string_types)
        assert isinstance(self.username, six.string_types)
        assert isinstance(self.password, six.string_types)
        assert isinstance(self.auth_source, six.string_types)
        if self.encryption_key:
            assert isinstance(self.encryption_key, six.string_types)
            assert len(self.encryption_key) == 44  # 32 bytes encoded as urlsafe base64 has length 44
            assert self.encryption_key.endswith("=")
            byte_encryption_key = self.encryption_key.encode('utf-8')
            assert base64.urlsafe_b64encode(base64.urlsafe_b64decode(byte_encryption_key)) == byte_encryption_key

    def _get_defaults(self):
        return {
            "host": "localhost",
            "port": "27017",
            "database": "autoTRADER",
            "username": "vt",
            "password": "vt",
            "encryption_key": None,
            "auth_source": "autoTRADER",
        }

    def _set_configs_from_dict(self, config_dict):
        self.host = config_dict["host"]
        self.port = int(config_dict["port"])
        self.database = config_dict["database"]
        self.username = config_dict["username"]
        self.password = config_dict["password"]
        self.encryption_key = config_dict["encryption_key"]
        self.auth_source = config_dict.get("auth_source", "autoTRADER")

        self.check_config_validity()


class PromptConfig(FileConfig):
    """
    Class to parse Prompt configs
    Config Section: prompt
    """

    _cfg_section = "prompt"

    # mapping for roles
    roles_map = {"1": "primary",
                 "2": "emergency",
                 "3": "test",
                 "4": "integration",
                 "100": "unit_test",
                 "500": "backtesting",
                 "999": "docker"}

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                   # type: logging.Logger
        self.role = None                       # type: str
        self.desc = None                       # type: str
        self.bgcolor = None                    # type: str
        self.color = None                      # type: str
        self.text = None                       # type: str
        self.role_str = None                   # type: str

    def check_config_validity(self):
        assert isinstance(self.role, six.string_types) and self.role
        assert isinstance(self.desc, six.string_types) and self.desc
        assert isinstance(self.bgcolor, six.string_types)
        assert isinstance(self.color, six.string_types)
        assert isinstance(self.text, six.string_types)
        assert isinstance(self.role_str, six.string_types)

    def _get_defaults(self):
        return {
            "role": "unset",
            "desc": "unset",
            "bgcolor": "unset",
            "color": "unset",
            "text": "unset"
        }

    def _set_configs_from_dict(self, config_dict):
        self.role = config_dict["role"]
        self.desc = config_dict["desc"]
        self.bgcolor = config_dict["bgcolor"]
        self.color = config_dict["color"]
        self.text = config_dict["text"]
        if self.role in self.roles_map:
            self.role_str = "{}: {}".format(self.role, self.roles_map[self.role])
        else:
            self.role_str = "unset"

        self.check_config_validity()


class ATConfig(FileConfig):
    """
    Class to parse Autotrader Configs for Connection Manager
    Config Section: autotrader
    """

    _cfg_section = "autotrader"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                                       # type: logging.Logger
        self.console = None                                        # type: bool or None
        self.host = None                                           # type: str or None
        self.publisher_port = None                                 # type: int or None
        self.submission_port = None                                # type: int or None
        self.status_port = None                                    # type: int or None
        self.periotheus_host = None                                # type: str or None
        self.periotheus_submission_port = None                     # type: int or None
        self.epex_conmgr_host = None                               # type: str or None
        self.nordpool_conmgr_host = None                           # type: str or None
        self.trayport_conmgr_host = None                           # type: str or None
        self.heartbeat_interval_sec = None                         # type: int or None
        self.manager_timeout_sec = None                            # type: int or None
        self.nagios_interval_sec = None                            # type: int or None
        self.nagios_init_pt = None                                 # type: str or None
        self.nagios_init_epex = None                               # type: str or None
        self.nagios_init_trayport = None                           # type: str or None
        self.nagios_init_nordpool = None                           # type: str or None
        self.simulation_mode = None                                # type: bool or None
        # backtesting must never be set on live systems.
        # Used to run autoTRADER locally with a file instead an exchange connection
        self.backtesting = None                                    # type: bool or None
        # Unused on live-systems.
        # Used in conjunction with backtesting to set the speed of the simulation
        self.playback_speed = None                                 # type: float or None

        self.nagios_strategy = None                                # type: str or None
        self.nagios = None                                         # type: str or None
        self.hwm_queue_lag = None                                  # type: int or None
        self.external_simulation_queue = None                      # type: bool or None
        self.start_file = None                                     # type: str or None
        self.autotrader_user = None                                # type: str or None
        self.use_persistence = None                                # type: bool or None
        self.epex = None                                           # type: bool or None
        self.nordpool = None                                       # type: bool or None
        self.trayport = None                                       # type: bool or None
        self.num_child_processes = None                            # type: int or None
        self.parent_to_child_sub_port = None                       # type: int or None
        self.parent_to_child_pub_port = None                       # type: int or None
        self.keep_strategy_history = None                          # type: int or None
        self.compliance_log_silence_period = None                  # type: int or None
        self.update_indicators_on_parent = None                    # type: bool or None
        self.automatic_maintenance_time = None                     # type: str or None
        self.write_public_orders_to_db = None                      # type: bool or None
        self.epex_child_ids = []                                   # type: list[str]
        self.trayport_child_ids = []                               # type: list[str]
        self.nordpool_child_ids = []                               # type: list[str]

        self.child_id_per_exchange = {
            COMMON.Exchange.epex: self.epex_child_ids,
            COMMON.Exchange.trayport: self.trayport_child_ids,
            COMMON.Exchange.nordpool: self.nordpool_child_ids
        }

    def check_config_validity(self):
        assert isinstance(self.console, bool)
        assert isinstance(self.host, six.string_types) and self.host
        assert isinstance(self.publisher_port, int)
        assert isinstance(self.submission_port, int)
        assert isinstance(self.status_port, int)
        assert isinstance(self.periotheus_host, six.string_types) and self.periotheus_host
        assert isinstance(self.periotheus_submission_port, int)
        assert isinstance(self.epex_conmgr_host, six.string_types) or not self.epex
        assert isinstance(self.nordpool_conmgr_host, six.string_types) or not self.nordpool
        assert isinstance(self.trayport_conmgr_host, six.string_types)
        assert isinstance(self.heartbeat_interval_sec, int)
        assert isinstance(self.manager_timeout_sec, int)
        assert isinstance(self.nagios_interval_sec, int)
        assert isinstance(self.simulation_mode, bool)
        assert isinstance(self.backtesting, bool)
        assert isinstance(self.playback_speed, float)

        assert isinstance(self.nagios, six.string_types)
        assert isinstance(self.nagios_init_pt, six.string_types)
        assert isinstance(self.nagios_init_epex, six.string_types)
        assert isinstance(self.nagios_init_trayport, six.string_types)
        assert isinstance(self.nagios_init_nordpool, six.string_types)

        assert isinstance(self.nagios_strategy, six.string_types)
        assert isinstance(self.hwm_queue_lag, int)
        assert isinstance(self.external_simulation_queue, bool)
        assert isinstance(self.start_file, six.string_types)
        assert isinstance(self.autotrader_user, six.string_types)
        assert isinstance(self.use_persistence, bool)
        assert isinstance(self.epex, bool)
        assert isinstance(self.nordpool, bool)
        assert isinstance(self.trayport, bool)
        assert isinstance(self.num_child_processes, int)
        assert isinstance(self.parent_to_child_sub_port, int)
        assert isinstance(self.parent_to_child_pub_port, int)
        assert isinstance(self.keep_strategy_history, int)
        assert isinstance(self.compliance_log_silence_period, int)
        assert isinstance(self.update_indicators_on_parent, bool)
        assert isinstance(self.epex_child_ids, list)
        assert isinstance(self.trayport_child_ids, list)
        assert isinstance(self.nordpool_child_ids, list)
        assert isinstance(self.automatic_maintenance_time, str)
        assert isinstance(self.write_public_orders_to_db, bool)

    def _get_defaults(self):
        return {
            "console": "False",
            "host": "127.0.0.1",
            "publisher_port": "45077",                  # exch2ad_msg_port
            "submission_port": "45002",                 # ad2exch_msg_port
            "status_port": "45001",                     # exch2at_status_port
            "periotheus_host": "localhost",
            "periotheus_submission_port": "55099",      # at2pt_msg_port
            "epex_conmgr_host": "localhost",
            "nordpool_conmgr_host": "localhost",
            "trayport_conmgr_host": "localhost",
            "heartbeat_interval_sec": "10",
            "manager_timeout_sec": "120",
            "nagios_interval_sec": "59",
            "simulation_mode": "False",
            "backtesting": "False",
            "playback_speed": "1.0",
            "nagios_strategy": "",
            "nagios": "",
            "nagios_init_pt": "",
            "nagios_init_epex": "",
            "nagios_init_nordpool": "",
            "nagios_init_trayport": "",
            "hwm_queue_lag": "5",
            "external_simulation_queue": "False",
            "start_file": "/tmp/autotrader.start",
            "autotrader_user": "",
            "use_persistence": "True",
            "epex": "False",
            "nordpool": "False",
            "trayport": "False",
            "num_child_processes": "1",
            "parent_to_child_sub_port": "13456",
            "parent_to_child_pub_port": "13457",
            "keep_strategy_history": "0",
            "compliance_log_silence_period": "60",
            "update_indicators_on_parent": "False",
            "epex_child_ids": "",
            "trayport_child_ids": "",
            "nordpool_child_ids": "",
            "automatic_maintenance_time": "",
            "write_public_orders_to_db": "True" if six.PY2 else "False",
        }

    def _set_configs_from_dict(self, config_dict):
        self.console = self.get_bool(config_dict["console"])
        self.host = config_dict["host"]
        self.publisher_port = int(config_dict["publisher_port"])
        self.submission_port = int(config_dict["submission_port"])
        self.status_port = int(config_dict["status_port"])
        self.periotheus_host = config_dict["periotheus_host"]
        self.periotheus_submission_port = int(config_dict["periotheus_submission_port"])
        self.epex_conmgr_host = config_dict["epex_conmgr_host"]
        self.nordpool_conmgr_host = config_dict["nordpool_conmgr_host"]
        self.trayport_conmgr_host = config_dict["trayport_conmgr_host"]
        self.heartbeat_interval_sec = int(config_dict["heartbeat_interval_sec"])
        self.manager_timeout_sec = int(config_dict["manager_timeout_sec"])
        self.nagios_interval_sec = int(config_dict["nagios_interval_sec"])
        self.simulation_mode = self.get_bool(config_dict["simulation_mode"])
        self.backtesting = self.get_bool(config_dict["backtesting"])
        self.playback_speed = float(config_dict["playback_speed"])
        self.nagios = config_dict["nagios"] or os.path.join(NAGIOSPATH, "nagios-autotrader")
        self.nagios_init_pt = config_dict["nagios_init_pt"] or os.path.join(NAGIOSPATH, "nagios-autotrader-pt")
        self.nagios_init_epex = config_dict["nagios_init_epex"] or os.path.join(NAGIOSPATH, "nagios-autotrader-epex")
        self.nagios_init_nordpool = config_dict["nagios_init_nordpool"] or os.path.join(
            NAGIOSPATH, "nagios-autotrader-nordpool"
        )
        self.nagios_init_trayport = config_dict["nagios_init_trayport"] or os.path.join(
            NAGIOSPATH, "nagios-autotrader-trayport"
        )
        self.nagios_strategy = config_dict["nagios_strategy"] or os.path.join(
            NAGIOSPATH, "nagios-autotrader-strategy"
        )
        self.hwm_queue_lag = int(config_dict["hwm_queue_lag"])
        self.external_simulation_queue = self.get_bool(config_dict["external_simulation_queue"])
        self.start_file = str(config_dict["start_file"])
        self.autotrader_user = str(config_dict["autotrader_user"])
        self.use_persistence = self.get_bool(config_dict["use_persistence"])
        self.epex = self.get_bool(config_dict["epex"])
        self.nordpool = self.get_bool(config_dict["nordpool"])
        self.trayport = self.get_bool(config_dict["trayport"])
        self.num_child_processes = int(config_dict["num_child_processes"])
        self.parent_to_child_sub_port = int(config_dict["parent_to_child_sub_port"])
        self.parent_to_child_pub_port = int(config_dict["parent_to_child_pub_port"])
        self.keep_strategy_history = int(config_dict["keep_strategy_history"])
        self.compliance_log_silence_period = int(config_dict["compliance_log_silence_period"])
        self.update_indicators_on_parent = self.get_bool(config_dict["update_indicators_on_parent"])
        self.epex_child_ids = config_dict["epex_child_ids"]
        self.trayport_child_ids = config_dict["trayport_child_ids"]
        self.nordpool_child_ids = config_dict["nordpool_child_ids"]
        exchange_child_distribution = ALU.get_exchange_child_distribution(self)
        self.epex_child_ids = exchange_child_distribution[COMMON.Exchange.epex]
        self.trayport_child_ids = exchange_child_distribution[COMMON.Exchange.trayport]
        self.nordpool_child_ids = exchange_child_distribution[COMMON.Exchange.nordpool]
        self.child_exchange_distribution = ALU.swap_to_child_exchange_dist(self.num_child_processes,
                                                                           exchange_child_distribution)
        self.write_public_orders_to_db = self.get_bool(config_dict["write_public_orders_to_db"])
        self.child_id_per_exchange = {
            COMMON.Exchange.epex: self.epex_child_ids,
            COMMON.Exchange.trayport: self.trayport_child_ids,
            COMMON.Exchange.nordpool: self.nordpool_child_ids
        }
        self.logger.warning("Simulation Mode is set to: %s", self.simulation_mode)
        self.automatic_maintenance_time = str(config_dict["automatic_maintenance_time"])

        self.check_config_validity()


class ManagerConfig(FileConfig):
    """Class to parse Autotrader Configs for Connection Manager and Connection Manager Adapter"""

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                    # type: logging.Logger
        self.console = None                     # type: bool or None
        self.host = None                        # type: str or None
        self.publisher_port = None              # type: int or None
        self.submission_port = None             # type: int or None
        self.status_port = None                 # type: int or None
        self.nagios = None                      # type: str or None
        self.never_reconnect = None             # type: bool or None
        self.start_file = None                  # type: str or None
        self.heartbeat_interval_sec = None      # type: int or None
        self.spy_data_path = None               # type: str or None
        self.spy_delete_collection_after_days = None  # type: int or None
        self.spy_mongo_db_name = None           # type: str or None
        self.spy_rotation_hour = None           # type: int or None
        self.spy_db = None                      # type: str or None
        self.simulation_mode = None             # type: bool or None
        # The exchangefeed_file is used in conjunction with backtesting (section autotrader) to point to the
        # file used as replacement for an exchange connection.
        # It should be an absolute path
        self.exchangefeed_file = None           # type: str or None

    def check_config_validity(self):
        assert isinstance(self.host, six.string_types)
        assert isinstance(self.publisher_port, int)
        assert isinstance(self.submission_port, int)
        assert isinstance(self.status_port, int)
        assert isinstance(self.never_reconnect, bool)
        assert isinstance(self.nagios, six.string_types)
        assert isinstance(self.start_file, six.string_types)
        assert isinstance(self.spy_data_path, six.string_types)
        assert isinstance(self.spy_delete_collection_after_days, int)
        assert isinstance(self.spy_rotation_hour, int)
        assert isinstance(self.spy_db, six.string_types)
        if self.spy_db and self.spy_db != "mongo":
            error_msg = "Config for spy_db should specify mongo, found {}".format(self.spy_db)
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        assert isinstance(self.simulation_mode, bool)
        assert isinstance(self.exchangefeed_file, six.string_types)

    def _set_configs_from_dict(self, config_dict):
        self.console = self.get_bool(config_dict["console"])
        self.host = config_dict["host"]
        self.publisher_port = int(config_dict["publisher_port"])
        self.submission_port = int(config_dict["submission_port"])
        self.status_port = int(config_dict["status_port"])
        self.never_reconnect = self.get_bool(config_dict["never_reconnect"])
        self.start_file = config_dict["start_file"]
        self.heartbeat_interval_sec = int(config_dict["heartbeat_interval_sec"])
        self.spy_data_path = config_dict["spy_data_path"]
        self.spy_delete_collection_after_days = int(config_dict["spy_delete_collection_after_days"])
        self.spy_mongo_db_name = config_dict["spy_mongo_db_name"]
        self.spy_rotation_hour = int(config_dict["spy_rotation_hour"])
        self.spy_db = config_dict["spy_db"]
        self.simulation_mode = self.get_bool(config_dict["simulation_mode"])
        self.exchangefeed_file = config_dict["exchangefeed_file"]
        self.check_config_validity()

    def _get_defaults(self):
        return {"spy_data_path": "",
                "spy_mongo_db_name": "SPY",
                "spy_rotation_hour": "12",
                "spy_delete_collection_after_days": "182",
                "spy_db": "",
                "simulation_mode": "False",
                "exchangefeed_file": ""}


class M7ManagerConfig(ManagerConfig):
    exchange = None

    def _get_defaults(self):
        defaults = super(M7ManagerConfig, self)._get_defaults()
        defaults.update({
            "console": "False",
            "host": "127.0.0.1",
            "publisher_port": "45077",
            "submission_port": "45088",
            "status_port": "45078",
            "never_reconnect": "False",
            "heartbeat_interval_sec": "10",
            "nagios": "",
            "start_file": "/tmp/{}-manager.start".format(self.exchange),
        })
        return defaults

    def _set_configs_from_dict(self, config_dict):
        self.nagios = config_dict["nagios"] or os.path.join(NAGIOSPATH, "nagios-{}-manager".format(self.exchange))
        super(M7ManagerConfig, self)._set_configs_from_dict(config_dict)


class EpexManagerConfig(M7ManagerConfig):
    _cfg_section = "autotrader_epex-manager"

    exchange = "epex"


class NordpoolManagerConfig(ManagerConfig):
    _cfg_section = "autotrader_nordpool-manager"

    def _get_defaults(self):
        defaults = super(NordpoolManagerConfig, self)._get_defaults()
        defaults.update({
            "console": "False",
            "host": "127.0.0.1",
            "publisher_port": "46077",
            "submission_port": "46088",
            "status_port": "46078",
            "never_reconnect": "False",
            "heartbeat_interval_sec": "10",
            "nagios": "",
            "start_file": "/tmp/nordpool-manager.start",
        })
        return defaults

    def _set_configs_from_dict(self, config_dict):
        self.nagios = config_dict["nagios"] or os.path.join(NAGIOSPATH, "nagios-nordpool-manager")
        super(NordpoolManagerConfig, self)._set_configs_from_dict(config_dict)


class TrayportManagerConfig(ManagerConfig):
    """Trayport Manager Config, extends base class by adding fake exchange settings"""

    _cfg_section = "autotrader_trayport-manager"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.fake_exchange = False                                   # type: bool
        self.fake_exchange_port = None                               # type: int or None
        # The tp init file is used for backtesting. It can contain the files:
        # inst_definitions.json, inst_properties.jsonl and sequence_items.json
        self.tp_initfile_directory = None                            # type: str or None
        super(TrayportManagerConfig, self).__init__(logger)

    def check_config_validity(self):
        assert isinstance(self.fake_exchange, bool)
        assert isinstance(self.fake_exchange_port, int)
        super(TrayportManagerConfig, self).check_config_validity()

    def _set_configs_from_dict(self, config_dict):
        self.nagios = config_dict["nagios"] or os.path.join(NAGIOSPATH, "nagios-trayport-manager")
        self.fake_exchange = self.get_bool(config_dict["fake_exchange"])
        self.fake_exchange_port = int(config_dict["fake_exchange_port"])
        self.tp_initfile_directory = config_dict["tp_initfile_directory"]
        super(TrayportManagerConfig, self)._set_configs_from_dict(config_dict)

    def _get_defaults(self):
        defaults = super(TrayportManagerConfig, self)._get_defaults()
        defaults.update({
            "console": "False",
            "host": "127.0.0.1",
            "publisher_port": "47077",
            "submission_port": "47088",
            "status_port": "47078",
            "never_reconnect": "true",
            "heartbeat_interval_sec": "10",
            "nagios": "",
            "start_file": "/tmp/trayport-manager.start",
            "fake_exchange": "False",
            "fake_exchange_port": "55557",
            "tp_initfile_directory": ""
        })
        return defaults


class ExchangeConfig(FileConfig):

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                                            # type: logging.Logger
        self.autotrader_user = None                                     # type: str or None
        self.internal_market_mode = None                                # type: int or None
        self.read_only = None                                           # type: bool or None

    def check_config_validity(self):
        assert isinstance(self.internal_market_mode, int)
        assert isinstance(self.read_only, bool)

    def _get_defaults(self):
        return dict(internal_market_mode=COMMON.GlobalInternalMarketMode.default,
                    read_only="False")

    def _set_configs_from_dict(self, config_dict):
        self.internal_market_mode = int(config_dict["internal_market_mode"])
        self.read_only = self.get_bool(config_dict["read_only"])


class RestApiConfig(FileConfig):
    _cfg_section = "autotrader_rest_api"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                                            # type: logging.Logger
        self.serverName = None                                          # type: str or None
        self.serverPort = None                                          # type: str or None
        self.allowed_user = None                                        # type: str or None
        self.autotrader_host = None                                     # type: str or None
        self.persistence_host = None                                    # type: str or None
        self.query_limit = None                                         # type: int or None
        self.internal_api_users = []                                    # type: list[str]
        self.tim_server_host = None                                     # type: str or None
        self.tim_audience = None                                        # type: int or None
        self.tim_company_id = None                                      # type: str or None
        self.tim_keys_expiry = None                                     # type: int or None
        self.tim_keys_grace_period = None                               # type: int or None
        self.openid_verification_pattern = None                         # type: str or None
        self.use_periotheus_compliant_api = None                        # type: bool or None
        self.use_periotheus_independent_api = None                      # type: bool or None

    def check_config_validity(self):
        assert isinstance(self.serverName, six.string_types) and self.serverName
        assert isinstance(self.serverPort, six.string_types) and self.serverPort
        assert isinstance(self.allowed_user, six.string_types)
        assert isinstance(self.autotrader_host, six.string_types)
        assert isinstance(self.persistence_host, six.string_types) and self.persistence_host
        assert isinstance(self.query_limit, int)
        assert isinstance(self.internal_api_users, list)
        assert isinstance(self.tim_server_host, six.string_types) and self.tim_server_host
        assert isinstance(self.tim_audience, six.string_types) and self.tim_audience
        assert isinstance(self.tim_company_id, six.string_types)
        assert isinstance(self.tim_keys_expiry, int)
        assert isinstance(self.tim_keys_grace_period, int)
        assert isinstance(self.openid_verification_pattern,
                          six.string_types) and re.compile(self.openid_verification_pattern)
        assert isinstance(self.use_periotheus_compliant_api, bool)
        assert isinstance(self.use_periotheus_independent_api, bool)

    def _get_defaults(self):
        return {
            "serverName": "127.0.0.1",
            "serverPort": "8088",
            "allowed_user": "",
            "autotrader_host": "localhost",
            "persistence_host": "localhost",
            "query_limit": "200000",
            "internal_api_users": "visotech, TrayportAutomation, TrayportCICD",
            "tim_server_host": "https://accounts.trayport.com",
            "tim_audience": "https://autotrader.trayport.com/company/:instanceId",
            "tim_company_id": "",
            "tim_keys_expiry": COMMON.DAY,
            "tim_keys_grace_period": COMMON.HOUR,
            "openid_verification_pattern": "^https://.*",
            "use_periotheus_compliant_api": "True",
            "use_periotheus_independent_api": "False",
        }

    def _set_configs_from_dict(self, config_dict):
        self.serverName = config_dict["serverName"]
        self.serverPort = config_dict["serverPort"]
        self.allowed_user = config_dict["allowed_user"]
        self.autotrader_host = config_dict["autotrader_host"]
        self.persistence_host = config_dict["persistence_host"]
        self.query_limit = int(config_dict["query_limit"])
        self.internal_api_users = config_dict["internal_api_users"].replace(' ', '').split(',')
        self.tim_server_host = config_dict["tim_server_host"]
        self.tim_audience = config_dict["tim_audience"]
        self.tim_company_id = config_dict["tim_company_id"]
        self.tim_keys_expiry = int(config_dict["tim_keys_expiry"])
        self.tim_keys_grace_period = int(config_dict["tim_keys_grace_period"])
        self.openid_verification_pattern = config_dict["openid_verification_pattern"]
        self.use_periotheus_compliant_api = self.get_bool(config_dict["use_periotheus_compliant_api"])
        self.use_periotheus_independent_api = self.get_bool(config_dict["use_periotheus_independent_api"])

        self.check_config_validity()


class RestConnectConfig(ExchangeConfig):
    """Class to parse REST Configs for Connection Manager"""

    _cfg_section = "autotrader_rest_connection"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        super(RestConnectConfig, self).__init__(logger)
        self.login = None                                               # type: str or None
        self.password = None                                            # type: str or None
        self.steering_strategy = None                                   # type: str or None
        self.rest_api_host = None                                       # type: str or None
        self.rest_api_port = None                                       # type: int or None

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        super(RestConnectConfig, self).check_config_validity()
        if not (isinstance(self.login, six.string_types) and self.login):
            raise ValueError("Please provide a 'login' in your rest config section")

        assert isinstance(
            self.password, six.string_types
        ) and self.password, "Please provide a 'password' for your user in your rest config section"
        assert isinstance(self.steering_strategy, six.string_types)
        assert isinstance(
            self.rest_api_host, six.string_types
        ) and self.rest_api_host, "Please provide a 'rest_api_host' for your user in your rest config section"
        assert isinstance(
            self.rest_api_port, int
        ) and self.rest_api_port, "Please provide a 'rest_api_port' for your user in your rest config section"

    def _get_defaults(self):
        ret_dict = super(RestConnectConfig, self)._get_defaults()
        ret_dict.update({
            "login": "",
            "password": "",
            "steering_strategy": "",
            "rest_api_host": "localhost",
            "rest_api_port": "8088",
        })
        return ret_dict

    def _set_configs_from_dict(self, config_dict):
        super(RestConnectConfig, self)._set_configs_from_dict(config_dict)
        self.login = config_dict["login"]
        self.password = config_dict["password"]
        self.steering_strategy = config_dict["steering_strategy"]
        self.rest_api_host = config_dict["rest_api_host"]
        self.rest_api_port = int(config_dict["rest_api_port"])
        self.check_config_validity()


class NordpoolConfig(ExchangeConfig):
    """Class to parse Nord Pool Configs for Connection Manager"""

    _cfg_section = "autotrader_nordpool"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        super(NordpoolConfig, self).__init__(logger)
        self.host = None                            # type: str or None
        self.ws_host = None                         # type: str or None
        self.ws_port = None                         # type: int or None
        self.password = None                        # type: str or None
        self.auth_endpoint_host = None              # type: str or None
        self.auth_endpoint_port = None              # type: int or None
        self.max_heartbeat_timeout_seconds = None   # type: int or None
        self.capacities_area = []                   # type: list[str]

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        super(NordpoolConfig, self).check_config_validity()
        assert isinstance(self.host, six.string_types) and self.host.startswith(("https://", "http://")), \
            "Please provide a rest api endpoint in the nordpool config file which starts with 'https://' or 'http://'"
        assert '/v1' not in self.host, \
            "New API host do not include '/v1'. Please update 'host' in nordpool config file"
        assert isinstance(self.ws_host, six.string_types) and self.ws_host.startswith(("wss://", "ws://")), \
            "Please provide an 'ws_host' in the nordpool config file which starts with 'ws://' or 'wss://'"
        assert isinstance(self.ws_port, int) and self.ws_port
        assert isinstance(self.autotrader_user, six.string_types) and self.autotrader_user, \
            "Please provide an 'autotrader_user' in the nordpool config file"
        assert isinstance(self.password, six.string_types) and self.password, \
            "Please provide a 'password' for your user in the nordpool config file"
        assert isinstance(self.auth_endpoint_host, six.string_types) and self.auth_endpoint_host
        assert isinstance(self.auth_endpoint_port, int)
        assert isinstance(self.max_heartbeat_timeout_seconds, int)
        assert isinstance(self.capacities_area, list)

    def _get_defaults(self):
        ret_dict = super(NordpoolConfig, self)._get_defaults()
        ret_dict.update({
            # test host: https://intraday2-api.test.nordpoolgroup.com/api
            "host": "https://intraday2-api.nordpoolgroup.com/api",
            "ws_host": "wss://intraday2-ws.nordpoolgroup.com",  # test: "wss://intraday2-ws.test.nordpoolgroup.com"
            "ws_port": "443",
            "autotrader_user": "",
            "password": "",
            "auth_endpoint_host": "sts.nordpoolgroup.com",  # test: sts.test.nordpoolgroup.com
            "auth_endpoint_port": "443",
            "max_heartbeat_timeout_seconds": "120",
            "capacities_area": ""
        })
        return ret_dict

    def _set_configs_from_dict(self, config_dict):
        super(NordpoolConfig, self)._set_configs_from_dict(config_dict)
        self.host = config_dict["host"]
        self.ws_host = config_dict["ws_host"]
        self.ws_port = int(config_dict["ws_port"])
        self.autotrader_user = config_dict["autotrader_user"]
        self.password = config_dict["password"]
        self.auth_endpoint_host = config_dict["auth_endpoint_host"]
        self.auth_endpoint_port = int(config_dict["auth_endpoint_port"])
        self.max_heartbeat_timeout_seconds = int(config_dict["max_heartbeat_timeout_seconds"])
        capacities_area_helper = config_dict["capacities_area"].split(",") if config_dict["capacities_area"] else []
        self.capacities_area = [x.strip() for x in capacities_area_helper]

        self.check_config_validity()


class EpexConfig(ExchangeConfig):
    """
    Class to parse EPEX Configs for Connection Manager
    Config Section: autotrader_comxerv
    """

    _cfg_section = "autotrader_comxerv"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        super(EpexConfig, self).__init__(logger)
        self.username = None                        # type: str or None
        self.password = None                        # type: str or None
        self.totp_key = None                        # type: str or None
        self.host = None                            # type: str or None
        self.port = None                            # type: int or None
        self.host1 = None                           # type: str or None
        self.host2 = None                           # type: str or None
        self.port1 = None                           # type: int or None
        self.port2 = None                           # type: int or None
        self.virtual_host = None                    # type: str or None
        self.app_id = None                          # type: str or None
        self.certificate = None                     # type: str or None
        self.ca_certificate = None                  # type: str or None
        self.disconnect_action = None               # type: str or None
        self.epex_account_id = None                 # type: str or None
        self.epex_user_id = None                    # type: str or None
        self.n_configs = 2                          # type: int or None
        self.local_products = None                  # type: bool or None
        self.xbid_products = None                   # type: bool or None
        self.uk_products = None                     # type: bool or None
        self.half_hour_products = None              # type: bool or None
        self.quarter_hour_products = None           # type: bool or None
        self.enable_throttling = None               # type: bool or None
        # placeholders to get specific setting
        self._first_connection = None
        self._second_connection = None
        self.short_throttling_limit = None          # type: int or None
        self.long_throttling_limit = None           # type: int or None

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        super(EpexConfig, self).check_config_validity()
        if not os.environ.get("CI"):
            assert (isinstance(self.username, six.string_types)
                    and self.username), "No EPEX username specified in system.cfg"
        assert isinstance(self.password, six.string_types) and self.password
        assert isinstance(self.totp_key, six.string_types)
        assert isinstance(self.host1, six.string_types) and self.host1
        assert isinstance(self.port1, int)
        assert isinstance(self.host2, six.string_types) and self.host2
        assert isinstance(self.port2, int)
        assert isinstance(self.app_id, six.string_types) and self.app_id
        assert isinstance(self.certificate, six.string_types)
        assert isinstance(self.ca_certificate, six.string_types)
        assert isinstance(self.disconnect_action,
                          six.string_types) and self.disconnect_action in ("NO", "DEACT_USER_ORDRS", "DEACT_ACCT_ORDRS")
        assert isinstance(self.autotrader_user, six.string_types)
        assert isinstance(self.epex_account_id, six.string_types)
        assert isinstance(self.epex_user_id, six.string_types)
        assert isinstance(self.local_products, bool)
        assert isinstance(self.xbid_products, bool)
        assert isinstance(self.uk_products, bool)
        assert isinstance(self.half_hour_products, bool)
        assert isinstance(self.quarter_hour_products, bool)
        assert isinstance(self.enable_throttling, bool)
        assert isinstance(self.short_throttling_limit, int)
        assert isinstance(self.long_throttling_limit, int)

    def _get_defaults(self):
        ret_dict = super(EpexConfig, self)._get_defaults()
        ret_dict.update({
            "user": "guest",  # CXVITS03
            "password": "guest",
            "totp_key": "",
            "server1": "simu2.epex.m7.deutsche-boerse.com",  # advsimu2.epex.m7.deutsche-boerse.com
            "port1": "50140",  # 50240
            "server2": "simu1.epex.m7.deutsche-boerse.com",  # advsimu1.epex.m7.deutsche-boerse.com
            "port2": "50140",  # 50240
            "virtual_host": "app",
            "app_id": "VKYASP_0",
            "cert_path": None,
            "ca_cert_path": None,
            "disconnect_action": "NO",
            "autotrader_user": "AT_USER",  # TRD003  # get from atconfig
            "epex_account_id": "",
            "epex_user_id": "",
            "local_products": "True",
            "xbid_products": "True",
            "uk_products": "True",
            "half_hour_products": "True",
            "quarter_hour_products": "True",
            "enable_throttling": "True",
            "short_throttling_limit": "90",
            "long_throttling_limit": "95",
        })
        return ret_dict

    def _set_configs_from_dict(self, config_dict):
        super(EpexConfig, self)._set_configs_from_dict(config_dict)
        self.username = config_dict["user"]
        self.password = config_dict["password"]
        self.totp_key = config_dict["totp_key"]
        self.host = self.host1 = config_dict["server1"]
        self.port = self.port1 = int(config_dict["port1"])
        self.host2 = config_dict["server2"]
        self.port2 = int(config_dict["port2"])
        self.virtual_host = config_dict["virtual_host"]
        self.app_id = config_dict["app_id"]
        self.certificate = config_dict["cert_path"] if config_dict["cert_path"] is not None else os.path.join(
            CERTSPATH, "vt42.pem"
        )
        self.ca_certificate = config_dict["ca_cert_path"] if config_dict["cert_path"] is not None else os.path.join(
            CERTSPATH, "vt42.ca.crt"
        )
        self.disconnect_action = config_dict["disconnect_action"]
        self.autotrader_user = config_dict["autotrader_user"]
        self.epex_account_id = config_dict["epex_account_id"]
        self.epex_user_id = config_dict["epex_user_id"]
        self.local_products = self.get_bool(config_dict["local_products"])
        self.xbid_products = self.get_bool(config_dict["xbid_products"])
        self.uk_products = self.get_bool(config_dict["uk_products"])
        self.half_hour_products = self.get_bool(config_dict["half_hour_products"])
        self.quarter_hour_products = self.get_bool(config_dict["quarter_hour_products"])
        self.enable_throttling = self.get_bool(config_dict["enable_throttling"])
        self.short_throttling_limit = int(config_dict["short_throttling_limit"])
        self.long_throttling_limit = int(config_dict["long_throttling_limit"])

        self.check_config_validity()

    def get_by_id(self, id):
        if id == 0:
            return self._first_connection
        elif id == 1:
            return self._second_connection
        else:
            raise ValueError("Cannot find a connection config for id {}, valid ids are: 0 and 1".format(id))

    @property
    def first_connection(self):
        if not self._first_connection:
            self._first_connection = copy.copy(self)
            self._first_connection.host = self.host1
            self._first_connection.port = self.port1
        return self._first_connection

    @property
    def second_connection(self):
        if not self._second_connection:
            self._second_connection = copy.copy(self)
            self._second_connection.host = self.host2
            self._second_connection.port = self.port2
        return self._second_connection

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return u"{}:{}".format(self.host, self.port)


class TrayportConfig(ExchangeConfig):
    """Class to parse Trayport Configs"""

    _cfg_section = "autotrader_trayport"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        super(TrayportConfig, self).__init__(logger)
        self.trayport_host = None                      # type: str or None
        self.trayport_port = None                      # type: int or None
        self.user = None                               # type: str or None
        self.password = None                           # type: str or None
        self.venues = []                               # type: list[str]
        self.commodities = []                          # type: list[str]
        self.calculated_prices = False                 # type: bool or None
        # We do not subscribe to any products further in the future than this many years.
        self.product_subscription_max_years = 2        # type: int
        # For products that deliver less than one day, how many days in advance should we subscribe at most
        self.product_subscription_shortterm_days = 3   # type: int
        # For products that deliver between a day and 2 months,
        # how many times the delivery period in the future should we subscribe at most
        self.product_subscription_midterm_count = 10   # type: int
        # For products that deliver more than 80 days,
        # how many times the delivery period in the future should we subscribe at most
        self.product_subscription_longterm_count = 10  # type: int
        # if order matching is restricted to the broker of the order or not
        self.aggress_other_brokers = True
        # throughout the code literals `routes_to_market` and `routes` should be considered as being the same
        self.routes_to_market = []  # type: list[str]
        # needed for tests to generate specified routes to market (normally this setting should not appear in
        # production system)
        self.fake_exchange_num_routes_to_generate = 1  # type: int

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        super(TrayportConfig, self).check_config_validity()
        assert isinstance(self.trayport_host, six.string_types)
        assert isinstance(self.trayport_port, int)
        assert isinstance(self.user, six.string_types)
        assert isinstance(self.password, six.string_types)
        assert isinstance(self.venues, list)
        assert isinstance(self.commodities, list)
        assert isinstance(self.autotrader_user, six.string_types)
        assert isinstance(self.calculated_prices, bool)
        assert isinstance(self.product_subscription_max_years, int), type(self.product_subscription_max_years)
        assert isinstance(self.product_subscription_shortterm_days, int)
        assert isinstance(self.product_subscription_midterm_count, int)
        assert isinstance(self.product_subscription_longterm_count, int)
        assert isinstance(self.aggress_other_brokers, bool)
        assert isinstance(self.routes_to_market, list)
        assert isinstance(self.fake_exchange_num_routes_to_generate, int)

    def _get_defaults(self):
        ret_dict = super(TrayportConfig, self)._get_defaults()
        ret_dict.update({
            "trayport_host": "trayport",
            "trayport_port": "443",
            "user": "guest",
            "password": "guest",
            "autotrader_user": "1",
            "venues": "OTC, EEX, EEXWD",
            "commodities": "Gas",
            "calculated_prices": "false",
            "product_subscription_max_years": 2,
            "product_subscription_shortterm_days": 3,
            "product_subscription_midterm_count": 10,
            "product_subscription_longterm_count": 10,
            "aggress_other_brokers": "True",
        })
        return ret_dict

    def _set_configs_from_dict(self, config_dict):
        super(TrayportConfig, self)._set_configs_from_dict(config_dict)
        self.trayport_host = config_dict["trayport_host"]
        self.trayport_port = int(config_dict["trayport_port"])
        self.user = config_dict["user"]
        self.password = config_dict["password"]
        self.autotrader_user = config_dict["autotrader_user"]
        self.venues = config_dict["venues"].split(",")
        self.commodities = config_dict["commodities"].split(",")
        # clean potential leftovers from the string split
        self.venues = [x.strip() for x in self.venues if len(x) > 0]
        self.commodities = [x.strip() for x in self.commodities if len(x) > 0]
        self.calculated_prices = self.get_bool(config_dict.get("calculated_prices", self.calculated_prices))
        self.product_subscription_max_years = int(config_dict.get("product_subscription_max_years",
                                                                  self.product_subscription_max_years))
        self.product_subscription_shortterm_days = int(config_dict.get("product_subscription_shortterm_days",
                                                                       self.product_subscription_shortterm_days))
        self.product_subscription_midterm_count = int(config_dict.get("product_subscription_midterm_count",
                                                                      self.product_subscription_midterm_count))
        self.product_subscription_longterm_count = int(config_dict.get("product_subscription_longterm_count",
                                                                       self.product_subscription_longterm_count))
        self.aggress_other_brokers = self.get_bool(config_dict.get("aggress_other_brokers", self.aggress_other_brokers))
        self.routes_to_market = config_dict.get("trayport_routes_to_market", "").split(",")
        self.fake_exchange_num_routes_to_generate = int(config_dict.get("fake_exchange_num_routes_to_generate", 1))
        self.check_config_validity()


class GuardConfig(FileConfig):
    _cfg_section = "autotrader_guard"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                                  # type: logging.Logger
        self.console = None                                   # type: bool or None
        self.check_every = None                               # type: int or None

        self.autotrader_pt_timeout = None                     # type: int or None
        self.autotrader_pt_process = None                     # type: str or None

        # EPEX connection manager
        self.manager_timeout = None                           # type: int or None
        self.manager_process = None                           # type: str or None
        # EPEX exchange object
        self.autotrader_epex_timeout = None                   # type: int or None
        self.autotrader_epex_process = None                   # type: str or None

        # NORDPOOL connection manager
        self.autotrader_nordpool_timeout = None               # type: int or None
        self.autotrader_nordpool_process = None               # type: str or None
        # NORDPOOL exchange object
        self.nordpool_exchange_timeout = None               # type: int or None
        self.nordpool_exchange_process = None               # type: str or None

        # TRAYPORT connection manager
        self.autotrader_trayport_timeout = None               # type: int or None
        self.autotrader_trayport_process = None               # type: str or None
        # TRAYPORT exchange object
        self.trayport_exchange_timeout = None               # type: int or None
        self.trayport_exchange_process = None               # type: str or None

        self.stats_path = None                                # type: str or None

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        assert isinstance(self.console, bool)
        assert isinstance(self.check_every, int)
        assert isinstance(self.autotrader_pt_timeout, int)
        assert isinstance(self.autotrader_pt_process, six.string_types)

        assert isinstance(self.manager_timeout, int)
        assert isinstance(self.manager_process, six.string_types)
        assert isinstance(self.autotrader_epex_timeout, int)
        assert isinstance(self.autotrader_epex_process, six.string_types)

        assert isinstance(self.autotrader_nordpool_timeout, int)
        assert isinstance(self.autotrader_nordpool_process, six.string_types)
        assert isinstance(self.nordpool_exchange_timeout, int)
        assert isinstance(self.nordpool_exchange_process, six.string_types)

        assert isinstance(self.autotrader_trayport_timeout, int)
        assert isinstance(self.autotrader_trayport_process, six.string_types)
        assert isinstance(self.trayport_exchange_timeout, int)
        assert isinstance(self.trayport_exchange_process, six.string_types)

        assert isinstance(self.stats_path, six.string_types)

    def _get_defaults(self):
        return {
            "console": "False",
            "check_every": "120",
            "autotrader_pt_timeout": "1800",
            "autotrader_pt_process": "(py.*autotrader_core_main.py)((?!.*child_id.*).)+",
            "manager_timeout": "180",
            "manager_process": "python.*epex_conmgr_main.py",
            "autotrader_epex_timeout": "600",
            "autotrader_epex_process": "python.*epex_conmgr_main.py",

            "autotrader_nordpool_timeout": "600",
            "autotrader_nordpool_process": "python.*nordpool_conmgr_main.py",
            "nordpool_exchange_timeout": "180",
            "nordpool_exchange_process": "python.*nordpool_conmgr_main.py",

            "autotrader_trayport_timeout": "600",
            "autotrader_trayport_process": ".*jd_conmgr",
            "trayport_exchange_timeout": "180",
            "trayport_exchange_process": ".*jd_conmgr",

            "stats_path": "",
        }

    def _set_configs_from_dict(self, config_dict):
        self.console = self.get_bool(config_dict["console"])
        self.check_every = int(config_dict["check_every"])
        self.autotrader_pt_timeout = int(config_dict["autotrader_pt_timeout"])
        self.autotrader_pt_process = config_dict["autotrader_pt_process"]

        self.manager_timeout = int(config_dict["manager_timeout"])
        self.manager_process = config_dict["manager_process"]
        self.autotrader_epex_timeout = int(config_dict["autotrader_epex_timeout"])
        self.autotrader_epex_process = config_dict["autotrader_epex_process"]

        self.autotrader_nordpool_timeout = int(config_dict["autotrader_nordpool_timeout"])
        self.autotrader_nordpool_process = config_dict["autotrader_nordpool_process"]
        self.nordpool_exchange_timeout = int(config_dict["nordpool_exchange_timeout"])
        self.nordpool_exchange_process = config_dict["nordpool_exchange_process"]

        self.autotrader_trayport_timeout = int(config_dict["autotrader_trayport_timeout"])
        self.autotrader_trayport_process = config_dict["autotrader_trayport_process"]
        self.trayport_exchange_timeout = int(config_dict["trayport_exchange_timeout"])
        self.trayport_exchange_process = config_dict["trayport_exchange_process"]

        self.stats_path = config_dict["stats_path"] or NAGIOSPATH

        self.check_config_validity()


class CommandLineConfig(six.with_metaclass(abc.ABCMeta, Config)):
    """Class to parse Command Line Arguments"""

    @abc.abstractmethod
    def parse_from_command_line(self):
        pass


class AutotraderCommandLineConfig(CommandLineConfig):
    """Class to parse Command Line Arguments for Autotrader Binaries"""

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger                        # type: logging.Logger
        self.conf = None                            # type: str or None
        self.console = None                         # type: bool or None
        self.child_id = None                        # type: int or None

    def check_config_validity(self):
        """Simple validity checks for config entries"""
        if not isinstance(self.conf, six.string_types) and os.path.exists(self.conf):
            self.logger.error("Could not find Config File: %s", self.conf)
        assert isinstance(self.console, bool)
        assert isinstance(self.child_id, int) or self.child_id is None

    def _get_defaults(self):
        return {
            "conf": "",
            "console": "False",
        }

    def _set_configs_from_dict(self, config_dict):
        self.conf = config_dict["conf"] or os.path.join(PERIOTHEUSROOT, "system.cfg")
        self.console = self.get_bool(config_dict["console"])
        self.child_id = int(config_dict["child_id"]) if config_dict["child_id"] is not None else None
        self.check_config_validity()

    def parse_from_command_line(self):
        # type: () -> AutotraderCommandLineConfig
        """Get Common command line arguments

        This can be used to pass the NBROOT directory to autotrader:
        https://portal.visotech.com/confluence/pages/viewpage.action?pageId=1311333

        Example: if `root_dir` is set under a section called `[startup]`:
        Then, e.g. under `[startup.jobs.adapter]` add this:
            --nbroot %(startup.root_dir)s
        to the end of this:
            cmdline_args = /opt/vtse/bin/autotrader_adapter_main.py -c /opt/vtse/neurobase/etc/autotrader.conf
        """
        command_line_parser = argparse.ArgumentParser(
            description=__doc__,  # printed with -h/--help
            # Don't mess with format of description
            formatter_class=argparse.RawDescriptionHelpFormatter,
            # Turn off help, so we print all options in response to -h
            add_help=False)
        command_line_parser.add_argument(
            "-c", "--conf", default="", metavar="FILE", help="Path to the configuration file."
        )
        command_line_parser.add_argument("--console", action="store_true", help="Activate logging to console")
        command_line_parser.add_argument(
            "--nbroot", default="", metavar="PATH", help="Path to Neurobase Root directory"
        )
        command_line_parser.add_argument("--child_id", help="ID of the child process", nargs="?", default=None)
        args = command_line_parser.parse_args()
        args.nbroot = args.nbroot or ROOT

        if os.path.exists(args.nbroot) and not os.getenv("NBROOT") or args.nbroot != os.getenv("NBROOT"):
            self.logger.warning("Setting environment Variable NBROOT")
            set_nbroot(args.nbroot)

        self.logger.warning("NBROOT flag was set to path: %s", ROOT)

        args.conf = args.conf or os.path.join(PERIOTHEUSROOT, "system.cfg")
        self.set_configs_from_dict(dict(args._get_kwargs()))
        return self


class LoggingConfig(FileConfig):
    """
    Class to parse logging config. Logging is configured using the logging.yml file, and syslogHandler needs an address
    to connect to. Those are the two values specified in this section of the config.
    """
    _cfg_section = "autotrader.logging"

    def __init__(self, logger):
        super(LoggingConfig, self).__init__(logger)
        self.type = None
        self.address = None

    def _get_defaults(self):
        """
        Default values for logging configuration.

        :return: Returns a dict that specifies the paths for logging.yml file and socket where SyslogHandler will dump
        logs
        :rtype: dict
        """
        return {
            "type": "syslog",
            "address": "/opt/vtse/neurobase/var/run/autotrader/autotrader.sock"
        }

    def check_config_validity(self):
        """
        Check that both fields are strings and an existing files, since both of them are a path to a file.
        """
        assert isinstance(self.address, str) and os.path.exists(self.address) and self.type.endswith(".sock")
        assert isinstance(self.type, str) and ((self.type == "syslog")
                                               or (os.path.exists(self.type) and self.type.endswith(".yml")))

    def _set_configs_from_dict(self, config_dict):
        self.address = config_dict["address"]
        self.type = config_dict["type"]


class SolverConfig(FileConfig):
    """
    Class to parse configuration info for optimization solvers.

    This class is used to parse the configuration of mathematical optimization solvers, as used by the AI Team for the
    Storage Strategy.

    Example configuration:

    [solver]
    solver = GUROBI
    solver_path = /opt/gurobi951/linux64/bin/gurobi_cl
    solver_licence_path = /home/vt/gurobi/gurobi.lic
    """
    _cfg_section = "solver"

    def __init__(self, logger):
        # type: (logging.Logger) -> None
        self.logger = logger            # type: logging.Logger
        self.solver = None                # type: str or None
        self.solver_path = None                # type: str or None
        self.solver_licence_path = None            # type: str or None

    def check_config_validity(self):
        assert isinstance(self.solver, six.string_types) and self.solver
        assert isinstance(self.solver_path, six.string_types)
        assert isinstance(self.solver_licence_path, six.string_types)

    def _get_defaults(self):
        return {
            "solver": "GUROBI",
            "solver_path": "/opt/gurobi951/linux64/bin/gurobi_cl",
            "solver_licence_path": "/home/vt/gurobi/gurobi.lic",
        }

    def _set_configs_from_dict(self, config_dict):
        self.solver = config_dict["solver"]
        self.solver_path = config_dict.get("solver_path")
        self.solver_licence_path = config_dict.get("solver_licence_path")

        self.check_config_validity()
