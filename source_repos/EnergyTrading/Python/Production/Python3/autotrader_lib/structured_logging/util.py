import logging
import logging.config
import os

import autotrader_lib.config_helper as ATCONF
import yaml


log = logging.getLogger("autotrader_lib.structured_logging")


def load_config(config):
    """
    Fill in logger configuration based on the logging.yaml file and the LoggingConfig passed to this method (if any).

    If we specify a **type** in config we pass, that type should be a path to logging.yaml file which will be used
    instead of the basic one provided in ./logging.yml

    :param config: Instance of config_helper.LoggingConfig
    :type config: config_helper.LoggingConfig
    :return: Logging configuration extracted from logging.yml and system.cfg
    :rtype: dict
    """
    base_path = os.path.dirname(os.path.abspath(__file__))

    if config.type in [None, "syslog"]:
        config_file_path = os.path.join(base_path, "logging.yml")
    else:
        config_file_path = config.type

    address = config.address

    if not os.path.exists(config_file_path):
        raise IOError("Logging config file does not exist. Expected a config file at: {}".format(config_file_path))

    with open(config_file_path) as config_file:
        config = yaml.safe_load(config_file)
        config["logging"]["disable_existing_loggers"] = False

    for handler, options in config["logging"]["handlers"].items():
        if "address" in options:
            options["address"] = address

    return config


def init_loggers(config=None):
    """
    Instantiate and return a main structured logging logger.

    :param config: Instance of config_helper.LoggingConfig
    :type config: config_helper.LoggingConfig
    :return: sautotrader logger
    :rtype: logging.Logger
    """
    logging.config.dictConfig(load_config(config)["logging"])

    structured = logging.getLogger("sautotrader")

    return structured


def get_component_logger(
        base_logger_name="sautotrader",
        component="autotrader",
        origin="autotrader",
        child_id="",
        config=None,
        filters=[]
):
    """
    Helper method to create a logger adapter from the main structured logger defined in logging.yaml

    :param base_logger_name: From which logger to create this component logger. Base logger is one of the loggers
        defined in the logging.yaml file.
    :type base_logger_name: str
    :param component: Will be displayed in the log output, helps determine where log comes from
    :type component: str
    :param origin: Used to dispatch logs to proper files
    :type origin: str
    :param child_id: Set to a not-None to dispatch to child specific files
    :type child_id: str
    :param config: Instance of config_helper.LoggingConfig
    :type config: config_helper.LoggingConfig
    :param filters:
    :type filters: list[type[logging.Filter]]
    :return: Instance of LoggerAdapter which implements all logging methods (debug, info, warning, error, critical) and
        can be used just like a logger, but allows for defining component specific fields (i.e - component, destination,
        child from logging.yaml -> formatters -> structured_sys_log
    :rtype: logging.LoggerAdapter
    """
    if config is None:
        config = ATCONF.LoggingConfig(log).load_config()

    init_loggers(config)
    base_logger = logging.getLogger(base_logger_name)

    component_logger = logging.LoggerAdapter(
        base_logger,
        extra={
            "component": component,
            "origin": origin,
            "child_id": child_id
        }
    )

    if filters:
        for log_filter_class in filters:
            add = True
            for installed_filter in component_logger.logger.filters:
                if type(installed_filter) == log_filter_class:
                    add = False
            if add:
                component_logger.logger.addFilter(
                    log_filter_class(handlers=component_logger.logger.handlers)
                )

    return component_logger
