import datetime
import json
import os
import logging
import logging.handlers

import autotrader_lib.version as ATVER
import autotrader_lib.config_helper as ATCONF

import autotrader_lib.common as COMMON

TRAYPORT_COMPLIANCE_LOG_FILENAME = "trayport-conmgr-compliance.log"
TRAYPORT_LOG_ROLLOUT_PERIOD = COMMON.DAY


class ComplianceLogger(logging.Logger):
    """ Because the connection Managers do not use fast_logging, we for now make a simple
    co-implementation of the logging """

    def __init__(self, *args, **kwargs):
        super(ComplianceLogger, self).__init__(*args, **kwargs)
        self._at_version = ATVER.VERSION
        self._server_role = None

        # we cannot initialize the handler on the init, since we do not yet know nbroot path
        self._compl_handler = None

        # because of the tricky logging libary, we need to make sure to register our logger so that
        # autotrader_lib.log.config can configure the handlers for the normal logging
        logging.Logger.manager.loggerDict[self.name] = self

    def set_server_role(self, role):
        self._server_role = role

    def initiate_compl_file_handler(self):
        """ This step needs to happen later, because we only know the NBROOT from the command line arguments """
        filename = os.path.join(ATCONF.LOGSPATH, TRAYPORT_COMPLIANCE_LOG_FILENAME)

        # we need to handle the compliance file with rotations as well so we use a handler to no reinvent the wheel
        self._compl_handler = logging.handlers.TimedRotatingFileHandler(filename=filename, when="S",
                                                                        interval=TRAYPORT_LOG_ROLLOUT_PERIOD,
                                                                        utc=True, delay=True)
        self._compl_handler.doRollover()

    def compliance_log(self, log_mapping):
        log_code, log_level, log_message = log_mapping
        default_log_entry = {u"utc_timestamp": str(datetime.datetime.utcnow().isoformat()),
                             u"component": self.name,
                             u"level": log_level,
                             u"at_version": self._at_version,
                             u"server_role": self._server_role,
                             u"log_code": log_code,
                             u"text": log_message}

        log_message = json.dumps(default_log_entry)

        # we need to handle emiting the log ourselves because we do not want it in both logfiles
        try:
            fn, lno, _ = self.findCaller()
        except ValueError:
            fn, lno = "(unknown file)", 0

        record = logging.LogRecord(name=self.name,
                                   level=log_level,
                                   pathname=fn,
                                   lineno=lno,
                                   msg=log_message,
                                   args=(),
                                   exc_info=None)  # compliance logging does not allow exception logging

        # It might be we try to log too early
        if self._compl_handler is not None:

            # we want only compliance logs in the compliance file
            self._compl_handler.handle(record)

        else:
            self.warning("Compliance handler has not been initialized with the call to: initiate_compl_file_handler")


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly")
