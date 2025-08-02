# coding: utf-8

import os.path
import errno

import logging
import autotrader_lib.config_helper as ATCONF


def _create_handler(application, log_console, default_level):
    log_handler = {}
    if log_console is not None:
        log_file = os.path.join(ATCONF.LOGSPATH, "{}.log".format(application))
        log_handler[application] = {"formatter": "plain", "class": "logging.handlers.TimedRotatingFileHandler",
                                    "level": default_level,
                                    "filename": log_file, "interval": 1, "backupCount": 120}
        if log_console:
            console = "{}_console".format(application)
            log_handler[console] = {"class": "logging.StreamHandler",
                                    "level": default_level,
                                    "formatter": "plain"}
    return log_handler


def _get_logger_config(log_handler):
    handlers = {}
    loggers = {}
    for application, handler_definition in log_handler:
        loggers[application] = {"handlers": handler_definition.keys()}
        handlers.update(handler_definition)

    log_def = {"version": 1, "disable_existing_loggers": False,
               "formatters": {"plain": {"format": "%(asctime)s.%(msecs)03d [%(name)s] %(levelname)-8s %(message)s",
                                        "datefmt": "%Y-%m-%dT%H:%M:%S"}},
               "handlers": handlers,
               "loggers": loggers}
    return log_def


def create_logspath():
    try:
        os.makedirs(ATCONF.LOGSPATH)
        logging.warning("Created log directory in: %s", ATCONF.LOGSPATH)
    except OSError as err:
        if err.errno != errno.EEXIST:
            logging.warning("Cannot create log directory: %s", err)
    return ATCONF.LOGSPATH


def configure(application, log_console=False, default_level=None):
    """Configures logging of the passed application to the same named log file

    Logging happens in the format: <DATA> <TIME> [<application>] <LEVEL>

    e.g. 2018-03-27 17:02:58 [autotrader_core] DEBUG Startup

    :param application: Identification of the application
    :type application: str
    :param log_console: Flag if logging should additionally be done to the console
    :type log_console: bool
    :param default_level: Maximal level of logging (default: DEBUG)
    :type default_level: str
    """
    multi_configure([(application, default_level)], log_console)


def multi_configure(applications, log_console=False):
    """Configures logging of the passed applications to the same named log files

    Logging happens in the format: <DATA> <TIME> [<application>] <LEVEL>

    e.g. 2018-03-27 17:02:58 [autotrader_core] DEBUG Startup

    :param applications: Identification of the application
    :type applications: list[tuple[str, str]]
    :param log_console: Flag if logging should additionally be done to the console
    :type log_console: bool
    """
    import logging.config  # pylint: disable=W0621

    appl_logger = []

    create_logspath()

    for application, log_level in applications:
        if log_level is None:
            log_level = "DEBUG"
        handler = _create_handler(application, log_console, log_level)
        appl_logger.append((application, handler))
    logging.root.handlers = []  # remove root handlers (from basicConfig) so only logger-specific handlers are used
    logging.config.dictConfig(_get_logger_config(appl_logger))
