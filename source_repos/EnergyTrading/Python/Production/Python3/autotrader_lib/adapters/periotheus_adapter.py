# -*- coding: utf-8 -*-

import datetime
import pprint
import uuid

import zmq
import autotrader_lib.common as COMMON
import autotrader_lib
import autotrader_lib.adapters.base_adapter as BA


class PeriotheusAdapter(BA.BaseAdapter):
    """
    Adapter class connection the autotrader core to Periotheus

    The submission service is a ROUTER socket, connected to 2 DEALERS: PT and REST-API.
    The first part of the envelop is the routing key, which we need to distinguish where to send the
    message to.

    The Periotheus submission service is a DEALER socket, which is connected to a single ROUTER socket
    in Periotheus. That ROUTER in Periotheus talks with multiple DEALERs (AT and RestAPI)
    """

    def __init__(self, log, on_message_callback, autotrader_config, sockets):
        """

        :param log: see BA.BaseAdapter
        :param on_message_callback: see BA.BaseAdapter
        :param autotrader_config: autotrader configuration
        :type autotrader_config: autotrader_lib.config_helper.ATConfig
        """
        super(PeriotheusAdapter, self).__init__(log, "PeriotheusAdapter", on_message_callback)
        self._autotrader_config = autotrader_config
        self._periotheus_submission_service = None
        self._submission_service = None
        self.socket_spec = None

        sockets.add_adapter(self)

    def send(self, body_dict, want_reply, properties=None):
        """
        Send data to periotheus. If the body_dict contains a message_type of password_changed or the data is send
        to the restapi socket
        is used instead

        :param body_dict: data to send
        :type body_dict: dict
        :param want_reply: True if we want to reply to periotheus' messages, False otherwise
        :type want_reply: bool
        :param properties: property of the message
        :type properties: dict
        """
        expiration_ts = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        payload = dict(expiration_timestamp=expiration_ts,
                       properties=properties or {},
                       correlation_id=str(uuid.uuid4()) if want_reply else "",  # correlation_id
                       body=body_dict)
        envelope = [autotrader_lib.codec.msgpackcodec.serialize(payload)]
        if body_dict["message_type"] == COMMON.Response.password_changed:
            envelope.insert(0, COMMON.RoutingKey.rest_api)
            # The submission service is a ROUTER socket, connected to 2 DEALERS: PT and REST-API.
            # The first part of the envelop is the routing key, which we need to distinguish where to send the
            # message to.
            self._submission_service.send_multipart(envelope)
            self._log.debug("send to rest: body: %s, properties: %s", pprint.pformat(body_dict, depth=1), properties)
        else:
            # The Periotheus submission service is a DEALER socket, which is connected to a single ROUTER socket
            # in Periotheus. That ROUTER in Periotheus talks with multiple DEALERs (AT and RestAPI)
            self._periotheus_submission_service.send_multipart(envelope)
            self._log.debug("send to pt: body: %s, properties: %s", pprint.pformat(body_dict, depth=1), properties)

    def create_socket_spec(self, zmq_context):
        """Returns a socket specification dictionary that works with SOCK.SocketsBase.

        :param zmq_context: The ZeroMQ context
        :type zmq_context: zmq.Context
        :return: A dict mapping socket names to socket specifications
        :rtype: dict[str, dict[str, any]]
        """
        spec = {}

        if self._autotrader_config.periotheus_host is None:
            raise autotrader_lib.SocketConfigurationError(
                "No host configured for periotheus adapter")
        if self._autotrader_config.periotheus_submission_port is None:
            raise autotrader_lib.SocketConfigurationError(
                "No publisher_port configured for periotheus adapter")

        self._periotheus_submission_service = zmq_context.socket(zmq.DEALER)
        connect_address = "tcp://{}:{}".format(self._autotrader_config.periotheus_host,
                                               self._autotrader_config.periotheus_submission_port)
        spec["periotheus_submission_service"] = dict(socket=self._periotheus_submission_service,
                                                     connect_address=connect_address,
                                                     use_poller=True)

        self._submission_service = zmq_context.socket(zmq.ROUTER)
        bind_address = "tcp://{}:{}".format(self._autotrader_config.host,
                                            self._autotrader_config.submission_port)
        spec["submission_service"] = dict(socket=self._submission_service,
                                          bind_address=bind_address,
                                          use_poller=True)
        self.socket_spec = spec
        return spec

    def step(self, events, timestamp=None):
        """ Check if we got some messages from periotheus and forward messages to autotrader_core

        :param events: see BA.BaseAdapter
        """
        if self._periotheus_submission_service in events:
            # we got message from PT
            routing_key, packed_msg = self._periotheus_submission_service.recv_multipart()
            msg = autotrader_lib.codec.msgpackcodec.deserialize(packed_msg)
            self._on_message_callback(msg)
        if self._submission_service in events:
            # PT or REST-API sent message to us and maybe we shall respond
            routing_key, packed_msg = self._submission_service.recv_multipart()
            msg = autotrader_lib.codec.msgpackcodec.deserialize(packed_msg)
            want_reply = msg["properties"].get("correlation_id")
            response = self._on_message_callback(msg)
            if want_reply and response:
                msg = autotrader_lib.codec.msgpackcodec.serialize(response)
                envelope = [routing_key, msg]
                self._submission_service.send_multipart(envelope)
                self._log.debug("send to pt: body: %s", pprint.pformat(response, depth=1))
