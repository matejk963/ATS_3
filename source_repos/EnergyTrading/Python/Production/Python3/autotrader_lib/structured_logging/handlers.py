import json
import logging.handlers
import logging
import socket


class AutotraderSysLogHandler(logging.handlers.SysLogHandler):
    """
    Logging.handler which extends the existing SysLogHandler, but formats the message with additional fields in
    accordance with the behaviour defined in autotrader.conf file (can be found in dist.autotrader_rest.files.syslog).
    Makes sure that the output log has a **programname** and **procid** which our rsyslog rules use to route the logs to
    appropriate files.
    """
    def emit(self, record):
        """
        Emit a record.

        The record is formatted, and then sent to the syslog server. If
        exception information is present, it is NOT sent to the server.

        :param record: A log record to extract data from
        :type record: logging.LogRecord
        """
        try:
            data = self.format_for_syslog(record)

            if self.unixsocket:
                try:
                    self.socket.send(data)
                except OSError:
                    self.socket.close()
                    self._connect_unixsocket(self.address)
                    self.socket.send(data)
            elif self.socktype == socket.SOCK_DGRAM:
                self.socket.sendto(data, self.address)
            else:
                self.socket.sendall(data)
        except Exception:
            self.handleError(record)

    @staticmethod
    def flatten_dict(d):
        """
        Removes one level of dict nesting.

        Example: {a: {b: c, d: e}, f: g} becomes: {b: c, d: e, f: g}

        :param d: A dictionary to flatten
        :type d: dict
        :return: Flattened dict
        :rtype: dict
        """
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result.update(value)  # add subdict directly into the dict
            else:
                result[key] = value  # non-subdict elements are just copied

        return result

    def format_for_syslog(self, record):
        """
        Extract relevant data from log record, and format it to a string which rsyslog knows how to parse.

        RSYSLOG rules:
        It goes something like this:
        Example: Consider the following message:
        <15>autotrader_restapi_compliance[autotrader_child_420]: {"dict": "with", "some": "useful data"}

        1) First thing in the message is **priority** enclosed in angle brackets: <15>
        2) It is immediatelly followed by **programname**: autotrader_restapi_compliance
        Programname streches until "[" or ":". Whatever comes first. Since our logger constructs messages with [], we
        expect the [ to come first.:
        3) What ever is inside the square brackets is **procid**: [autotrader_child_420]
        4) Anything after the first ":" is our **message**: {"dict": "with", "some": "useful data"}
        This message is what is going to be saved to the log file

        :param record: A log record to extract data from
        :type record: logging.LogRecord
        :return: Utf-8 encoded string that rsyslog knows how to parse
        :rtype: str
        """
        prio = '<%d>' % self.encodePriority(self.facility, self.mapPriority(record.levelname))
        msg = json.dumps(self.flatten_dict(self.format(record)), default=str)

        programname = record.origin
        procid = "[{}]".format(record.child_id)
        syslogtag = programname + procid + ": "

        data = (prio + syslogtag + msg).encode('utf-8') + b'\000'

        return data
