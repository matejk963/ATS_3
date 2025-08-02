"""
Simulate the matching of own orders with public orders/Trades to mimic an exchange.

This is needed for the read-only simulation mode of AutoTrader and for backtesting (simulation mode).

The class ExchangeSimulator takes messages from the exchange and matches them with own orders
(creating multiple messages out of one), and it takes messages from AutoTrader and produces response messages.

The ExchangeSimulator does not keep its own OrderBook between subsequent invocations, but instead reads the OrderBook
from AutoTrader.
"""

from __future__ import division, print_function

from __future__ import absolute_import

import collections
import contextlib
import json
import logging
import os.path
import shutil
import time
import zipfile
from collections import defaultdict

import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.simulation_data as SIMDAT
import autotrader_lib.util as ATUTIL
from six.moves import range

log = logging.getLogger("autotrader.simulator")

QUANTITY_DIGITS = 5  # To avoid floating point problems, we round remaining quantities to this many digits.

DEFAULT_TP_ASSET_PATH = os.path.normpath(os.path.join(__file__, "..", "..", "backtesting",
                                                      "exchanges", "trayport", "default_backtesting_assets"))


class _SimulationOrderId(object):
    """Give created orders/ trades an id in the simulation"""

    def __init__(self):
        # time.time needed for read-only mode, so we get no conflicts if we load old trades from the database.
        self.order_id = 10000000 * int(time.time())

    def new_id(self):
        """
        Return a new id, which is just 1 higher than the last.

        :return: A new id
        :rtype: str
        """
        self.order_id += 1
        return str(self.order_id)


simulation_order_id = _SimulationOrderId()


class _QuantityLookup(object):
    """
    Like a dictionary that matches Orders to Quantities.

    It takes Orders or Trades as keys and maps them to floats.
    If a key is not present, it adds it and sets the value to the order's quantity
    (comparable to a defaultdict).
    """

    def __init__(self):
        self.dict = {}
        self._orders = defaultdict(set)

    @staticmethod
    def _getkey(order):
        """
        Convert an order to a hashable key used internally.

        We use either order_id or internal_id, depending on the Order type.
        :type order: APITR.Order
        :rtype: int | string
        """
        if isinstance(order, APITR.OwnOrder):
            return order.internal_id
        elif isinstance(order, APITR.PublicTrade):
            return order.trade_id
        # Track quantities per order_id, so we do not trade multiple times on mirrored orders within germany..
        return order.order_id

    def __getitem__(self, order):
        """
        :type order: APITR.Order
        """
        key = self._getkey(order)
        if key not in self.dict:
            self.dict[key] = order.quantity
            self._orders[key].add(order)
        return self.dict[key]

    def __setitem__(self, order, value):
        """
        :type order: APITR.Order
        :type value: float
        """
        key = self._getkey(order)
        self.dict[key] = value

    def items(self):
        out = []
        for key in self.dict:
            for order in self._orders[key]:
                out.append((order, self.dict[key]))
        return out


class NoopSimulator(object):
    """
    Can be used in place of Exchange Simulator for tests.
    Does not perform any simulation.
    """

    def __init__(self, autotrader=None, exchange_id=COMMON.Exchange.epex):  # pylint: disable=unused-argument
        pass

    @staticmethod
    def receive(data_dict):
        return [data_dict]

    @staticmethod
    def send(body_property_tuples):  # pylint: disable=unused-argument
        return []


class OMTSimulator(object):
    def __init__(self, short_omt_parameters=None, long_omt_parameters=None):
        # type: (ATUTIL.OMTParameters, ATUTIL.OMTParameters) -> None
        self._short = ATUTIL.OMTParameters(
            limit_type="short",
            received_omt=0,
            observation_period=10,
            tolerance_period=5,
            cooldown_period=10,
            lower_threshold=200,
            upper_threshold=400,
            status=COMMON.EpexOMTState.NO_RESTRICTION
        )
        if short_omt_parameters is not None:
            self._short.from_dict(short_omt_parameters.to_dict(True))

        self._long = ATUTIL.OMTParameters(
            limit_type="long",
            received_omt=0,
            observation_period=86400,
            tolerance_period=1800,
            cooldown_period=3600,
            lower_threshold=345600,
            upper_threshold=691200,
            status=COMMON.EpexOMTState.NO_RESTRICTION
        )
        if long_omt_parameters is not None:
            self._long.from_dict(long_omt_parameters.to_dict(True))

    @property
    def long_config(self):
        return self._long.to_dict(True)

    @property
    def short_config(self):
        return self._short.to_dict(True)


class ExchangeSimulator(object):
    """
    Perform matching based on a message and AutoTrader's OrderBook and deliver the results as messages.
    """
    intercept_messages = (COMMON.Response.order_book,
                          COMMON.Response.public_trade,
                          COMMON.Response.product,
                          COMMON.TrayportResponse.trade_list,
                          COMMON.EpexResponse.omt_status,
                          COMMON.EpexResponse.message_report,
                          COMMON.TrayportResponse.venue_connection)

    def __init__(self, autotrader, exchange_id=COMMON.Exchange.epex, trayport_init_directory=None, omt_simulator=None):
        """Initiate the ExchangeSimulator class

        :var collections.Counter executed_own_order_count: This instance variable tracks how many orders were
                                                           inserted/ modified by autoTRADER for each delivery interval.
                                                           WARNING: This does not include manual orders, but does count
                                                           the activation of manual orders by autotrader
        :param autotrader: the autotrader instance
        :type autotrader: autotrader_core.api.AutoTrader
        :param exchange_id: The exchange to simulate on, defaults to COMMON.Exchange.epex
        :type exchange_id: str, optional
        :param trayport_init_directory: path to trayport init files, defaults to None
        :type trayport_init_directory: str, optional
        :param omt_simulator: omt limit parameters for the simulation, defaults to None
        :type omt_simulator: OMTSimulator, optional
        """
        self.autotrader = autotrader
        self.exchange_id = exchange_id
        self.asset_path = trayport_init_directory
        self.omt_historical_data = []
        self.executed_own_order_count = collections.Counter()
        if self.exchange_id == COMMON.Exchange.epex:
            self.omt_simulator = omt_simulator if omt_simulator is not None else OMTSimulator()

        # specify special handling for state changing messages
        self.MESSAGE_HANDLER_BY_TYPE = {
            COMMON.EpexRequest.omt_status:
                self.__handle_omt_status_request,
            COMMON.Request.own_trade:
                ExchangeSimulator.__create_empty_response_handler(COMMON.Response.own_trade),
            COMMON.Request.own_orders:
                ExchangeSimulator.__create_empty_response_handler(COMMON.Response.order_execution),

            # EXCHANGE LOGIN MESSAGE HANDLING
            COMMON.TrayportRequest.relogin:
                lambda _: log.debug("Received Trayport relogin request. No answer is needed."),

            # TRAYPORT INIT MESSAGE HANDLING
            COMMON.TrayportRequest.inst_properties:
                self.__handle_inst_properties_request,
            COMMON.TrayportRequest.inst_definition:
                self.__create_single_line_trayport_init_file_handler(COMMON.TrayportInitFileNames.inst_definitions),
            COMMON.TrayportRequest.sequence_items:
                self.__create_single_line_trayport_init_file_handler(COMMON.TrayportInitFileNames.sequence_items),
            COMMON.TrayportRequest.term_format:
                self.__create_single_line_trayport_init_file_handler(COMMON.TrayportInitFileNames.term_format),
            COMMON.Request.order_delete_all: self._handle_trayport_delete_all
        }

    @staticmethod
    def __log_unimplemented_message(message):
        """Logs a message as unimpplemented.

        :param message: message from autotrader
        :type message: dict[str, any]
        """
        message_type = message["body"]["message_type"]
        log.debug("Messages of type %s are not yet implemented in simulation/read-only mode.", message_type)

    @staticmethod
    def __create_empty_response_handler(message_type):
        """Returns a function that generates an empty response of a given message_type.

        :param message_type: The message_type of the response
        :type message_type: str
        """
        def generate_response(_):
            return [(message_type, [])]
        return generate_response

    def __handle_omt_status_request(self, _):
        """Generates an omt status response using the simulated parameters.

        :return: OMT status response
        :rtype: list[tuple[str, any]]
        """
        return [
            (
                COMMON.EpexResponse.omt_status,
                {
                    COMMON.RateLimitType.Epex.short: self.omt_simulator.short_config,
                    COMMON.RateLimitType.Epex.long: self.omt_simulator.long_config,
                }
            )
        ]

    def __generate_message(self, incoming, outgoing_message_type, outgoing_data):
        if outgoing_data is None:
            outgoing_data = []
        return {
            "body": {
                "data": outgoing_data,
                "timestamp": self.autotrader.current_timestamp,
                "exchange": self.exchange_id,
                "message_type": outgoing_message_type
            },
            "properties": incoming["properties"]
        }

    def __handle_incoming_message(self, incoming, log_unimplemented=True):
        """Handles an incoming message and generates responses for it (need to be turned into valid autotrader messages)

        :param incoming: Incoming message from autotrader
        :type incoming: dict[str, any]
        :return: a list of responses
        :rtype: list[tuple[str, any]]
        """
        message_type = incoming["body"]["message_type"]
        default_handler = ExchangeSimulator.__log_unimplemented_message if log_unimplemented else lambda x: None
        handler = self.MESSAGE_HANDLER_BY_TYPE.get(message_type, default_handler)

        responses = handler(incoming)
        return [] if responses is None else responses

    def generate_responses_from_incoming(self, incoming, log_unimplemented):
        """Generates all appropriate responses in autotrader message format for one incoming autotrader message.

        :param incoming: Incoming message from autotrader (including body and properties fields)
        :type incoming: dict[str, any]
        :return: List of autotrader formatted responses
        :rtype: list[dict[str, any]]
        """
        responses = self.__handle_incoming_message(incoming, log_unimplemented)

        # Respond with ack_response message if:
        #  - The current exchange is epex, because epex acknowledges every request
        #  - It is an init-request, but no response would be generated otherwise. Doesn't need to be ack_response
        #    message, but it is used here, because it doesn't do much. Is needed to initialize the exchange.
        init_corr_id = ATUTIL.extract_data_from_correlation_id(incoming["properties"], "init")
        if self.exchange_id == COMMON.Exchange.epex or (init_corr_id is not None and len(responses) == 0):
            responses.insert(0, (COMMON.Response.ack_response, None))

        outgoing = [
            self.__generate_message(incoming, message_type, data)
            for message_type, data in responses
            if message_type is not None
        ]
        return outgoing

    def __handle_inst_properties_request(self, _):
        """Get instance properties from init files. Should only happen once per backtest at initialisation.

        :param _: incoming message to respond to
        :type _: dict[str, any]
        :return: response messages sent from exchange which contain the prepared instrument properties
        :rtype: list[tuple[str, any]]
        """
        # Special case, as we reply to the first message with all inst properties
        # and return empty responses to the other ones.
        # This way, we do not have to keep track which instruments autoTRADER requested,
        # and can give simply all instruments from the file to AT.
        responses = []
        if self.inst_properties_sent_on_current_message:
            responses.append((COMMON.TrayportResponse.inst_properties, []))
        else:
            with self._open_trayport_init_asset(COMMON.TrayportInitFileNames.inst_properties) as f:
                for line in f:
                    body = json.loads(line)
                    responses.append((str(body.get("message_type")), body.get("data")))
            self.inst_properties_sent_on_current_message = True
        return responses

    def __create_single_line_trayport_init_file_handler(self, asset_type):
        """Generates a function to retrieve the given asset as a message

        :param asset_type: Trayport init asset type
        :type asset_type: str
        """
        def retrieve_trayport_asset(_):
            with self._open_trayport_init_asset(asset_type) as f:
                for line in f:
                    # return the first line
                    body = json.loads(line)
                    return [(body.get("message_type"), body.get("data"))]
        return retrieve_trayport_asset

    def _handle_trayport_delete_all(self, incoming):
        if incoming["body"].get("exchange") == COMMON.Exchange.trayport:
            return [(COMMON.TrayportResponse.delete_all_succeeded, [])]
        else:
            return None

    @property
    def exchange(self):
        return self.autotrader.get_exchange(self.exchange_id)

    def receive(self, message):
        """Receive a message (with body and properties) from the exchange and forward simulation response messages

        This intercepts public_trade and order_book messages and performs a matching with own orders.
        In case of matching, the original message is modified or even removed, otherwise it is forwarded unmodified.
        It also intercepts product messages to issue SDLE messages for orders on expired products.

        :param message: A single message from the exchange, containing the keys "body" and "properties"
        :type message: dict
        :return: One or more messages
        :rtype: list[dict]
        """
        log.debug("'receive' intercepting message: %s", message)
        body = message["body"]
        properties = message["properties"]
        if body["message_type"] in self.intercept_messages:
            assert body["exchange"] == self.exchange_id
            step = SimulationStepReceive(self.autotrader.get_exchange(self.exchange_id), body["timestamp"])
            simulation_response_messages = step.intercept_incoming_message(body, properties)
            self.executed_own_order_count += step.executed_own_order_count
            log.debug("'receive' forwarding: %s", [msg["body"]["message_type"] for msg in simulation_response_messages])
            return simulation_response_messages
        log.debug("'receive' forwarding data_dict unmodified")
        return [message]

    def send(self, messages):
        """
        Instead of sending a message to an exchange, perform simulation and return simulated responses.

        :param messages: A list of message dictionaries with the keys body and properties.
        :type messages: list[dict[str,dict]]
        :return: A list of response messages containing the keys "body" and "properties"
        :rtype: list[dict]
        """
        log.debug("'send' to Exchange Simulator called with %s messages", len(messages))
        responses = []
        if self.exchange_id == COMMON.Exchange.epex:
            self.omt_historical_data.append({"timestamp": self.autotrader.current_timestamp,
                                             "short": self.autotrader.epex.short_omt.current_level,
                                             "long": self.autotrader.epex.long_omt.current_level})

        self.inst_properties_sent_on_current_message = False  # Only send the inst properties once per step.
        data_messages, other_messages = self._separate_messages(messages)

        for message in other_messages:
            try:
                responses.extend(self.generate_responses_from_incoming(message, True))
            except Exception as err:
                print("Failed to Handle: ", message)
                raise err

        # Generate ack_responses for all other messages if on Epex
        for message in data_messages:
            responses.extend(self.generate_responses_from_incoming(message, False))

        step = SimulationStepSend(self.autotrader.get_exchange(self.exchange_id), self.autotrader.current_timestamp)
        responses.extend(step.answer_outgoing_messages(data_messages))
        self.executed_own_order_count += step.executed_own_order_count
        log.debug("'send' responding: %s (properties: %s)",
                  [msg["body"]["message_type"] for msg in responses], [msg["properties"] for msg in responses])
        return responses

    @staticmethod
    def _separate_messages(messages):
        """
        Separate messages to the exchange into initialization messages (with properties, but empty data field)
        and regular messages with a data field and empty properties.

        :type messages: list[dict[str,dict]]
        :return: A list of messages for data-containing message types,
                 and a list of messages for initialization
        :rtype: (list[dict[str, any]],list[dict[str,any]])
        """
        msgs_with_data = []
        other = []
        for data_dict in messages:
            message = data_dict["body"]
            properties = data_dict["properties"]
            if message.get("message_type") in [COMMON.Request.own_trade,
                                               COMMON.Request.own_orders,
                                               COMMON.Request.order_deactivate_all,
                                               COMMON.Request.order_activate_all,
                                               COMMON.Request.trade_recall] + list(COMMON.READONLY_MESSAGES):
                other.append(data_dict)
            else:
                # Allow delete all requests with init corr-id
                if message.get("message_type") != COMMON.Request.order_delete_all:
                    is_init = "init" in properties.get("correlation_id", "") if properties else ""
                    assert not is_init, "message {} has {}".format(message["message_type"], properties)
                msgs_with_data.append(data_dict)
        return msgs_with_data, other

    @contextlib.contextmanager
    def _open_trayport_init_asset(self, filename):
        """
        Open an asset file for the trayport initialization.

        If a user-defined directory was specified in the class initialization (self.asset_path),
        the file is searched for there first. If it does not exist or no user-defined location was specified,
        fall-back to the default assets.

        :param filename:
        :type filename:
        :return:
        :rtype:
        """
        def unzip_to_init_folder(init_foldername):
            with zipfile.ZipFile(init_foldername + ".zip", "r") as f:
                f.extractall(init_foldername)

        if self.asset_path:
            if self.asset_path.endswith(".zip"):
                init_dir = self.asset_path[:-4]
                if not os.path.isdir(init_dir):
                    unzip_to_init_folder(init_dir)
                # check if zip was unpacked once more in the same foldername
                # then we have to move the init files back 1 level
                basename = os.path.basename(init_dir)
                if os.path.isdir(os.path.join(init_dir, basename)):
                    for f in os.listdir(os.path.join(init_dir, basename)):
                        shutil.move(os.path.join(init_dir, basename, f), os.path.join(init_dir, f))
                    shutil.rmtree(os.path.join(init_dir, basename))
                self.asset_path = init_dir
            if not os.path.isdir(self.asset_path) and os.path.isfile(self.asset_path + ".zip"):
                log.info("unzipping asset: %s to %s", self.asset_path + ".zip", self.asset_path + "/")
                with zipfile.ZipFile(self.asset_path + ".zip", "r") as f:
                    f.extractall(self.asset_path)
                log.info("Extracted assets to: %s", self.asset_path)
            userdefined_file = os.path.join(self.asset_path, filename)
        if self.asset_path and os.path.isfile(userdefined_file):
            log.info("Loading %s from userdefined path %s", filename, userdefined_file)
            with open(userdefined_file) as f:
                yield f
        else:
            if self.asset_path:
                # Add a print here, because the log only is mostly invisible when developing,
                # and may lead to an invisible error, when developing backtests locally
                print(
                    "================\n"
                    "WARNING!! Asset file %s not found. Falling back to default asset: %s.\n"
                    "================" % (userdefined_file, filename))
                log.warning("Asset file %s not found. Falling back to default asset.", userdefined_file)
            log.debug("Loading default asset file for: %s.", filename)
            with open(os.path.join(DEFAULT_TP_ASSET_PATH, filename)) as f:
                yield f


class DataContainer(object):
    def __init__(self):
        self.data = list()
        self.properties = dict()


class SimulationStep(object):
    """
    A single timestep in the simulation. Instances of this class perform the actual matching.

    Within a single step, we track simulated traded quantities to ensure consistency within the step.

    Note: Exchange simulator does not keep any data between steps. Thus consistency between steps has
    to be maintained by the AutoTrader's order_book.
    """

    def __init__(self, exchange, current_timestamp):
        self.exchange = exchange
        self.timestamp = current_timestamp
        self.remaining_own_quantities = _QuantityLookup()
        self.remaining_public_quantities = _QuantityLookup()
        self.processed_own_order_ids = set()

        if self.exchange.internal_id == COMMON.Exchange.trayport:
            self.company_id = self.exchange.company_id
        else:
            self.company_id = None
        self.executed_own_order_count = collections.Counter()
        # Will be filled with messages.
        self.execution_msg = DataContainer()
        self.own_trade_msg = DataContainer()
        self.error_msg = DataContainer()

    @staticmethod
    def is_matchable(own_order):
        return own_order.quantity > 0.

    def _simulate_single_match(self, own_order, public_object, message_properties):
        """
        Simulate the match between a single own_order and a single public order or public trade.
        For Trayport, we do not match across different broker ids.

        :type own_order: APITR.OwnOrder
        :type public_object: APITR.PublicOrder or APITR.PublicTrade
        :return: True, if a match was possible (even if no trade happened due to too little quantity),
                 False otherwise
        :rtype: bool
        """

        if not self.is_matchable(own_order):
            return False

        # The revision is global for one area.
        # It can be that public order 1 is added at revision 1 and public order 2 is added at revision 2
        # and then the strategy places an order to match order 1.
        # In this case we send an update message for order 1,
        # but we have to give it the latest revision for this area (here 2).
        last_revision = public_object.product.orders._last_area_revision[own_order.delivery_area_id]
        public_object.revision = max([public_object.revision or 0, last_revision or 0])

        # For Trayport, do not match on differing broker ids.
        if self.exchange.internal_id == COMMON.Exchange.trayport:
            if own_order.broker_id != COMMON.Broker.eexs:
                log.warning("Own Order: Broker ID {} is not fully supported!".format(own_order.broker_id))
            # Its an order!
            if hasattr(public_object, "broker_id"):
                if public_object.broker_id != own_order.broker_id:
                    return False
            # Its a trade!
            else:
                if own_order.broker_id not in [public_object.aggressor_broker_id, public_object.initiator_broker_id]:
                    return False

        is_own_sell = own_order.direction == COMMON.Direction.sell
        if _prices_match(own_order.price, public_object.price, is_own_sell):
            traded_quantity = round(min(self.remaining_own_quantities[own_order],
                                        self.remaining_public_quantities[public_object]),
                                    QUANTITY_DIGITS)
            is_public_order = isinstance(public_object, APITR.PublicOrder)
            public_object_id = public_object.order_id if is_public_order else public_object.trade_id
            log.debug("Simulate match: Own Order: %s (%s, qty=%s), with: %s (%s, qty=%s), trade-qty=%s",
                      getattr(own_order, "order_id", None), own_order.internal_id,
                      self.remaining_own_quantities[own_order], type(public_object).__name__, public_object_id,
                      self.remaining_public_quantities[public_object], traded_quantity)
            if traded_quantity > 0.05:
                self.remaining_own_quantities[own_order] = round(self.remaining_own_quantities[own_order]
                                                                 - traded_quantity, QUANTITY_DIGITS)
                self.remaining_public_quantities[public_object] = round(self.remaining_public_quantities[public_object]
                                                                        - traded_quantity, QUANTITY_DIGITS)
                # trade_order (trayport) do not have an own_order.order_id, and should skip the following
                if hasattr(own_order, "order_id"):
                    execution_data = _create_pexe_fexe_data(own_order,
                                                            self.remaining_own_quantities[own_order],
                                                            self.timestamp)
                    self.execution_msg.data.append(execution_data)
                    self.execution_msg.properties.update(message_properties)

                own_trade_data = self._create_own_trade_data(own_order, public_object, traded_quantity)
                self.own_trade_msg.data.append(own_trade_data)
                self.own_trade_msg.properties.update(message_properties)

            else:
                log.warning("Found a potential match, but not creating a trade because qty<0.05 for %s"
                            " (own qty=%s, public qty=%s)", getattr(own_order, "order_id", None),
                            self.remaining_own_quantities[own_order],
                            self.remaining_public_quantities[public_object])
            return True
        return False

    def generate_messages(self, original_message_body, original_message_properties):
        """
        Generate all messages for this simulation step.

        The order is, depending on the intercepted message, as follows:

            * order_book   ==> [order_execution], order_book, [own_trade]
            * public_trade ==> [order_execution], [public_trade], [own_trade]
            * trade_list   ==> [order_execution] [trade_list]
            * trade_order  ==> [order_book], [trade_list]
            * product      ==> product, [order_execution (SDEL)]
            * AT requests  ==> order_execution, [order_book, own_trade]

        :param original_message_body: The original, intercepted message
        :type original_message_body: dict
        :return: A list of message bodies generated
        :rtype: list[dict[str,any]]]
        """

        out_messages = []  # type: list[dict[str,any]]

        # We presume that OMT status message only comes in read-only mode and backtesting feeds don't include it
        if original_message_body and original_message_body["message_type"] == COMMON.EpexResponse.omt_status:
            # replace every OMT value received from the exchange with 0 so that autotrader isn't stopped from outside
            for omt_property_dict in original_message_body["data"].values():
                omt_property_dict["received_omt"] = 0
                omt_property_dict["status"] = COMMON.EpexOMTState.NO_RESTRICTION
            out_messages.append({
                "body": original_message_body,
                "properties": original_message_properties,
            })

        if original_message_body and original_message_body["message_type"] == COMMON.TrayportResponse.venue_connection:
            # In read only simulation mode, no upstream is configured (as it is not needed for R/O).
            # Here we fake that it exists.
            for venue_info in original_message_body["data"]:
                venue_info["upstream_state"] = COMMON.SIMULATION_VENUE_UPSTREAM_STATE
            out_messages.append({
                "body": original_message_body,
                "properties": original_message_properties,
            })

        # An original Product message comes first, potentially followed by SDEL
        if original_message_body and original_message_body["message_type"] == COMMON.Response.product:
            out_messages.append({
                "body": original_message_body,
                "properties": original_message_properties,
            })

        # Then we start with all UADD/UDEL/SDEL/PEXE/FEXE/ messages
        if self.execution_msg.data:
            log.debug("Simulated order executions: %s", ", ".join("{}({})".format(entry["action"], entry["order_id"])
                                                                  for entry in self.execution_msg.data))
            out_messages.append({
                "body": {"data": self.execution_msg.data,
                         "message_type": COMMON.Response.order_execution,
                         "timestamp": self.timestamp,
                         "exchange": self.exchange.internal_id,
                         },
                "properties": self.execution_msg.properties,
            })
        else:
            log.debug("No simulated order executions")
        # Then, an order_book or public_trade/trade_list message

        out_messages.extend(self._generate_orderbook_or_public_trade_messages(original_message_body,
                                                                              original_message_properties))

        # Now packaging the own trades
        if self.own_trade_msg.data:
            if (self.own_trade_msg.data[0]["user"] == COMMON.SimulationUserExchange.trayport_user):
                if out_messages[-1]["body"]["message_type"] == COMMON.TrayportResponse.trade_list:
                    out_messages[-1]["body"]["data"].extend(self.own_trade_msg.data)
                else:
                    out_messages.append({
                        "body": {"data": self.own_trade_msg.data,
                                 "message_type": COMMON.TrayportResponse.trade_list,
                                 "timestamp": self.timestamp,
                                 "exchange": self.exchange.internal_id,
                                 },
                        "properties": self.own_trade_msg.properties,
                    })
            else:
                out_messages.append({
                    "body": {"data": self.own_trade_msg.data,
                             "message_type": COMMON.Response.own_trade,
                             "timestamp": self.timestamp,
                             "exchange": self.exchange.internal_id,
                             },
                    "properties": self.own_trade_msg.properties,
                })

        # And the error data
        if self.error_msg.data:
            out_messages.append({
                "body": {"data": self.error_msg.data,
                         "message_type": COMMON.Response.error_response,
                         "timestamp": self.timestamp,
                         "exchange": self.exchange.internal_id,
                         },
                "properties": self.error_msg.properties,
            })

        return out_messages

    def _generate_orderbook_or_public_trade_messages(self, original_message, original_message_properties):
        """
        Update messages for public orders or trades
        """
        raise NotImplementedError

    def _get_product(self, exchange, line, product_getter, **kwargs):
        """ Returns the product of an exchange from a product_id extracted from the data in line.

        :param exchange: exchange of the product to return
        :type exchange: COMMON.Exchange
        :param line: line in a autotrader message
        :type line: dict
        :param product_getter: function to get the product from its product_id
        :type product_getter: function
        :return: The Product matching the exchange and the product_id extracted from line
        :rtype: APITR.Product or None
        """
        product_id = line.get("product_id", None)
        if exchange == COMMON.Exchange.trayport and not product_id:
            if line["inst_specifier"][0]["sequence_span"] != "Single":
                log.debug("Not returning product for sequence_span %s", line["inst_specifier"][0]["sequence_span"])
                return None
            product_id = u"{}_{}".format(line["inst_specifier"][0]["first_sequence_id"],
                                         line["inst_specifier"][0]["first_item_id"])
        product = product_getter(product_id, **kwargs)
        return product

    def _create_own_trade_data(self, own_order, public_object, traded_quantity):
        """
        Create a simulation data object for own trades.
        """
        raise NotImplementedError


class SimulationStepReceive(SimulationStep):
    """
    A simulation step for receiving a message from the true exchange/ recorded exchange feed.
    """

    @staticmethod
    def is_matchable(own_order):
        """
        Test if we are allowed to match an OwnOrder.

        :type own_order: APITR.OwnOrder
        :rtype: bool
        """
        # Don't match own ComTrader Orders. TODO (bet @lac) should this be in the super-class?
        if isinstance(own_order, APITR.ComTraderOrder):
            return False
        if _is_own_ioc_order(own_order):
            raise AssertionError("There should not be any IOC orders in the orderbook.")
        #  super(X,X) suggested in https://stackoverflow.com/a/26807879
        return super(SimulationStepReceive, SimulationStepReceive).is_matchable(own_order)

    def intercept_incoming_message(self, message_body, message_properties):
        """
        Main entry point. Given an exchange message, create simulation messages.

        :param message_body: A message-body of a message from the exchange.
        :type message_body: dict
        :return: The (modified) incoming messages plus simulation response messages with body and properties.
        :rtype: list[dict[str, any]]
        """

        if message_body["message_type"] == COMMON.Response.public_trade:
            for line in message_body["data"]:
                product = self._get_product(message_body["exchange"], line,
                                            self._get_product_if_unlocked, current_timestamp=self.timestamp)
                if product is not None:
                    if "revision" not in line:
                        line["revision"] = self.timestamp
                    pub_trade = APITR.PublicTrade.from_data_line(line, product, self.exchange.internal_id)
                    matched_sell = self._match_public_trade_with_own_orderbook(pub_trade,
                                                                               product,
                                                                               line["sell_delivery_area"],
                                                                               is_own_sell=True,
                                                                               message_properties=message_properties)
                    if not matched_sell:
                        # No match on sell side. Try matching on the buy side.
                        self._match_public_trade_with_own_orderbook(pub_trade,
                                                                    product,
                                                                    line["buy_delivery_area"],
                                                                    is_own_sell=False,
                                                                    message_properties=message_properties)

        elif message_body["message_type"] == COMMON.TrayportResponse.trade_list:
            for line in message_body["data"]:
                if self.company_id in (message_body.get("initiator_company_id", ""),
                                       message_body.get("aggressor_company_id", "")):
                    # this is an own_trade, we skip those
                    continue

                product = self._get_product(message_body["exchange"], line,
                                            self._get_product_if_unlocked, current_timestamp=self.timestamp)
                if product is not None:
                    if message_body["exchange"] == COMMON.Exchange.trayport:
                        if "revision" not in line:
                            line["revision"] = self.timestamp
                        if "sell_delivery_area_id" not in line:
                            line["sell_delivery_area"] = line["inst_specifier"][0]["instrument_id"]
                        if "buy_delivery_area_id" not in line:
                            line["buy_delivery_area"] = line["inst_specifier"][0]["instrument_id"]

                    pub_trade = APITR.PublicTrade.from_data_line(line, product, self.exchange.internal_id)
                    matched_sell = self._match_public_trade_with_own_orderbook(pub_trade,
                                                                               product,
                                                                               line["sell_delivery_area"],
                                                                               is_own_sell=True,
                                                                               message_properties=message_properties)
                    if not matched_sell:
                        # No match on sell side. Try matching on the buy side.
                        self._match_public_trade_with_own_orderbook(pub_trade,
                                                                    product,
                                                                    line["buy_delivery_area"],
                                                                    is_own_sell=False,
                                                                    message_properties=message_properties)

                    # delete delivery_area_id after public matching, since it was just a helper variable for trayport
                    if message_body["exchange"] == COMMON.Exchange.trayport:
                        del line["sell_delivery_area"]
                        del line["buy_delivery_area"]

        elif message_body["message_type"] == COMMON.Response.order_book:
            sell_order_lines = [line for line in message_body["data"] if line["direction"] == COMMON.Direction.sell]
            sell_order_lines.sort(key=lambda x: x["price"])
            buy_order_lines = [line for line in message_body["data"] if line["direction"] == COMMON.Direction.buy]
            buy_order_lines.sort(key=lambda x: x["price"], reverse=True)

            for line in sell_order_lines + buy_order_lines:
                product = self._get_product(message_body["exchange"], line,
                                            self._get_product_if_unlocked, current_timestamp=self.timestamp)
                if product is not None:
                    if message_body["exchange"] == COMMON.Exchange.trayport:
                        # ignore own_orders for trayport, since order_book contains own and public orders
                        if (not line.get("account")
                                or self.company_id == line["account"]
                                or line["action"].endswith("DEL")):
                            continue

                        # special handling for read only accounts on trayport. Set is_tradable to True so strategies
                        # can use the OrderBookIndicator in exchange_trading.
                        if line.get("state") == "ACTI":
                            line["is_tradable"] = True

                        # for trayport, instead of the delivery_area_id the instrument_id is used.
                        # need to add delivery_area_id to make it compatible public order methods
                        if "delivery_area_id" not in line:
                            line["delivery_area_id"] = line["inst_specifier"][0]["instrument_id"]
                        if "revision" not in line:
                            line["revision"] = self.timestamp

                    pub_order = APITR.PublicOrder.from_data_line(line, product, self.exchange.internal_id)
                    self._match_public_order_with_own_orderbook(pub_order, product,
                                                                line["delivery_area_id"],
                                                                is_own_sell=line["direction"] == COMMON.Direction.buy,
                                                                message_properties=message_properties)

                    # delete delivery_area_id after public matching, since it was just a helper variable for trayport
                    if message_body["exchange"] == COMMON.Exchange.trayport:
                        del line["delivery_area_id"]

        elif message_body["message_type"] == COMMON.Response.product:
            for line in message_body["data"]:
                try:
                    product = self.exchange.products.get_by_id(line["product_id"])
                except COMMON.ProductNotFound:
                    log.info("Did not find product %s", line["product_id"])
                    continue
                for delivery_area_id, info in line["trading_phases"].items():
                    if info.get("state") == COMMON.TradingPhase.closed:
                        own_orders = product.orders.get(delivery_area_id=delivery_area_id,
                                                        order_filter=COMMON.OrderFilter.own)
                        for own_order in own_orders:
                            log.warning("SDEL for Own order because product closed: %s", own_order)
                            sdel_msg_data = SIMDAT.SimulationDataOrder(own_order, own_order.order_id,
                                                                       action=COMMON.OrderAction.system_deleted)
                            sdel_msg_data.update(execution_time=self.timestamp)
                            self.execution_msg.data.append(sdel_msg_data.data)
                            self.execution_msg.properties.update(message_properties)

        responses = self.generate_messages(message_body, message_properties)
        return responses

    def _match_public_order_with_own_orderbook(self, order, product, delivery_area,
                                               is_own_sell, message_properties):
        """
        Simulate a match between a public order and own orders.

        :param order: The public object to match
        :type order: APITR.PublicOrder
        :param product: The Product of the Order
        :type product: APITR.Product
        :param delivery_area: The delivery_area_id.
        :type delivery_area: str
        :param is_own_sell: True if we are selling (public entity is buying)
        :type is_own_sell: bool

        """

        order_filter = COMMON.OrderFilter.own_sell if is_own_sell else COMMON.OrderFilter.own_buy
        own_orders_to_match = product.orders.get(delivery_area, order_filter=order_filter)
        for own_order in sorted(own_orders_to_match, key=lambda o: o.price, reverse=not is_own_sell):
            self._simulate_single_match(own_order, order, message_properties)

    def _match_public_trade_with_own_orderbook(self, public_trade, product, delivery_area,
                                               is_own_sell, message_properties):
        """
        Simulate a match between a public trade and own orders.

        :param public_trade: The public object to match
        :type public_trade: APITR.PublicTrade
        :param product: The Product for which the trade happened
        :type product: APITR.Product
        :param delivery_area: The delivery_area_id.
        :type delivery_area: str
        :param is_own_sell: True if we are selling (public entity is buying)
        :type is_own_sell: bool

        """

        order_filter = COMMON.OrderFilter.own_sell if is_own_sell else COMMON.OrderFilter.own_buy

        # Special treatment of Germany
        #    (only for incoming public trades, not for other messages, because public orders
        #     are already mirrored in the order book).
        if delivery_area in COMMON.Area.de_zone:
            own_orders_to_match = product.orders.get(order_filter=order_filter)
            own_orders_to_match = [o for o in own_orders_to_match if o.delivery_area_id in COMMON.Area.de_zone]
        else:
            own_orders_to_match = product.orders.get(order_filter=order_filter, delivery_area_id=delivery_area)

        has_matches = False
        for own_order in sorted(own_orders_to_match, key=lambda o: o.price, reverse=not is_own_sell):

            has_matches = self._simulate_single_match(own_order, public_trade, message_properties)
        return has_matches

    def _get_product_if_unlocked(self, product_id, current_timestamp):
        """
        Given a product_id, return the Product if it exists and is unlocked and None otherwise.


        :param product_id: The id of the product to get
        :type product_id: str
        :param current_timestamp: Timestamp to use when querying for the product lock
        :type current_timestamp: float
        :return: The Product matching the id.
        :rtype: APITR.Product or None
        """
        try:
            product = self.exchange.products.get_by_id(product_id)
        except COMMON.ProductNotFound:
            return None
        if product.is_product_locked(current_timestamp):
            return None
        return product

    def _generate_orderbook_or_public_trade_messages(self, original_message, original_message_properties):
        """
        Get an updated version of the intercepted orderbook or public_trade/trade_list message.

        :param original_message: A message body
        :type original_message: dict
        :return: A list with 0 or 1 messages
        :rtype: list
        """
        if original_message and original_message["message_type"] == COMMON.Response.public_trade:
            out_lines = []
            for line in original_message["data"]:
                trade_id = line["trade_id"]
                if trade_id in self.remaining_public_quantities.dict:
                    if self.remaining_public_quantities.dict[trade_id] > 0:
                        line["quantity"] = self.remaining_public_quantities.dict[trade_id]
                        out_lines.append(line)
                else:
                    out_lines.append(line)
            if out_lines:
                original_message["data"] = out_lines
                return [{"body": original_message, "properties": original_message_properties}]
            return []

        if original_message and original_message["message_type"] == COMMON.TrayportResponse.trade_list:
            out_lines = []
            for line in original_message["data"]:
                trade_id = line["trade_id"]
                if trade_id in self.remaining_public_quantities.dict:
                    if self.remaining_public_quantities.dict[trade_id] > 0:
                        line["quantity"] = self.remaining_public_quantities.dict[trade_id]
                        out_lines.append(line)
                else:
                    out_lines.append(line)
            if out_lines:
                original_message["data"] = out_lines
                return [{"body": original_message, "properties": original_message_properties}]
            return []

        elif original_message and original_message["message_type"] == COMMON.Response.order_book:
            out_lines = []
            for line in original_message["data"]:
                order_id = line["order_id"]
                if order_id in self.remaining_public_quantities.dict:
                    quantity = self.remaining_public_quantities.dict[order_id]
                    if quantity == 0:
                        pub_state = COMMON.OrderState.iact
                    else:
                        pub_state = COMMON.OrderState.acti
                    line["quantity"] = quantity
                    line["state"] = pub_state
                out_lines.append(line)
            original_message["data"] = out_lines
            return [{"body": original_message, "properties": original_message_properties}]
        return []

    def _create_own_trade_data(self, own_order, public_object, traded_quantity):
        """
        Create a simulation data object for own trades.

        :param own_order: The Own order being traded
        :type own_order: APITR.OwnOrder
        :param public_object: The public order/ trade being matched
        :type public_object: APITR.PublicTrade or APITR.PublicOrder
        :param traded_quantity: The amount being traded
        :type traded_quantity: float
        :return: An entry that can be appended to a message's data field.
        :rtype: dict
        """
        return _create_own_trade_data(own_order, public_object, traded_quantity,
                                      self.timestamp, self.exchange, is_aggressor=False)


class SimulationStepSend(SimulationStep):
    """
    A simulation step for messages sent by AutoTrader.
    """

    def __init__(self, exchange, current_timestamp):
        super(SimulationStepSend, self).__init__(exchange, current_timestamp)
        self.deleted_order_ids = set()
        self.message_type_handler_mapping = {
            COMMON.Request.order_delete: self._acknowledge_deletes,
            COMMON.Request.order_delete_all: self._acknowledge_delete_all,
            COMMON.Request.order_entry: self._handle_entries,
            COMMON.Request.order_modify: self._handle_modifies,
            COMMON.Request.order_deactivate: self._acknowledge_deactivates,
            COMMON.Request.order_activate: self._perform_activates,
            COMMON.TrayportRequest.trade_order: self._handle_trade_order
        }

    def answer_outgoing_messages(self, messages):
        """
        Main entry point. Given messages from AutoTrader, create response messages.

        :param messages: A list of message bodies sent by AutoTrader
        :type messages: list[dict[str,any]]
        :return: A list of response messages, containing the keys "body" and "properties"
        :rtype: list[dict]
        """
        for idx in range(len(messages)):
            if "body" not in messages[idx]:
                if "message_type" not in messages[idx]:
                    raise ValueError("message was in an unknown format.")
                messages[idx] = {"body": messages[idx]}
            if isinstance(messages[idx]["body"].get("data"), dict):
                # On nordpool, we send orders one by one to the exchange and do not use a list for data.
                messages[idx]["body"]["data"] = [messages[idx]["body"]["data"]]

        for msg in messages:
            body = msg["body"]
            properties = msg.get("properties", {})
            # simulate exchange reaction
            message_type = body["message_type"]
            if body.get('data'):
                log.debug("Simulated Exchange answering %s for: %s", message_type,
                          [line.get("order_id", "qty={}_price={}".format(line.get("quantity"), line.get("price")))
                           for line in body["data"]])

            try:
                self.message_type_handler_mapping[message_type](body, properties)
            except KeyError:
                raise NotImplementedError("Messages of type {} are not implemented in simulation mode."
                                          " We only handle delete, modify and entry and (de-)activate "
                                          "requests.".format(body["message_type"]))

        messages = self.generate_messages(None, None)
        return messages

    def _get_own_order_if_allowed(self, line, product):
        """
        Get the own_order object from the order_book, if it exists and it has not been deleted in this simulation step.

        (Note: modifies also result in deletion followed by a new addition)

        :param line: An entry from a message's data field.
        :type line: dict
        :param product: The Product corresponding to the order
        :type product: APITR.Product
        :return: The Order, if it exists in the own Orderbook and we are allowed to use it, or None otherwise.
        :rtype: APITR.OwnOrder or None
        """
        order_id = line["order_id"]
        if order_id in self.deleted_order_ids:
            return None
        own_order = product.orders.get_own_order_by_order_id(order_id, broker_id=line.get("broker_id"))
        return own_order

    def _acknowledge_deletes(self, body, properties):
        """
        Store an UDEL response message for all orders in the message

        :param body: A message (body) of message_type COMMON.Request.order_delete
        :type body: dict
        """
        for line in body["data"]:
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            own_order = self._get_own_order_if_allowed(line, product)
            if not own_order:
                continue  # Old delete request.
            udel_msg_data = SIMDAT.SimulationDataOrder(
                own_order, own_order.order_id, action=COMMON.OrderAction.user_deleted
            )
            udel_msg_data.update(execution_time=self.timestamp)

            self.execution_msg.data.append(udel_msg_data.data)
            self.execution_msg.properties.update(properties)

            self.deleted_order_ids.add(own_order.order_id)

    def _acknowledge_delete_all(self, unused_body, properties):
        """
        Store an UDEL response message for all orders that are currently open for epex on all products.

        :param unused_body: A message (body) of message_type COMMON.Request.order_delete
        :type unused_body: dict
        """
        if self.exchange.internal_id == COMMON.Exchange.epex:
            for product in self.exchange.products.get_all():
                for order in product.orders.get(order_filter=COMMON.OrderFilter.own):
                    if not product.orders.is_com_trader_order(order.order_id):
                        udel_msg_data = SIMDAT.SimulationDataOrder(order, order.order_id,
                                                                   action=COMMON.OrderAction.user_deleted)
                        udel_msg_data.update(execution_time=self.timestamp)

                        self.execution_msg.data.append(udel_msg_data.data)
                        self.execution_msg.properties.update(properties)

                        self.deleted_order_ids.add(order.order_id)

    def _acknowledge_deactivates(self, body, properties):
        """
        Store an UHIB response message for all orders in the message

        :param body: A message (body) of message_type COMMON.Request.order_deactivate
        :type body: dict
        """
        for line in body["data"]:
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            own_order = self._get_own_order_if_allowed(line, product)
            if not own_order:
                continue  # Old delete request.
            uhib_msg_data = SIMDAT.SimulationDataOrder(own_order, own_order.order_id,
                                                       action=COMMON.OrderAction.user_hibernated)
            uhib_msg_data.update(state=COMMON.OrderState.hibe,
                                 execution_time=self.timestamp)

            self.execution_msg.data.append(uhib_msg_data.data)
            self.execution_msg.properties.update(properties)

    def _perform_activates(self, body, properties):
        """
        Store UDEL-UADD response messages for all orders in the message

        :param body: A message (body) of message_type COMMON.Request.order_deactivate
        :type body: dict
        """
        for line in body["data"]:
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            own_order = self._get_own_order_if_allowed(line, product)
            if not own_order:
                continue  # Old delete request.
            udel_msg_data = SIMDAT.SimulationDataOrder(own_order, own_order.order_id,
                                                       action=COMMON.OrderAction.user_deleted)
            udel_msg_data.update(execution_time=self.timestamp)

            self.execution_msg.data.append(udel_msg_data.data)
            self.execution_msg.properties.update(properties)

            self.deleted_order_ids.add(own_order.order_id)
            uadd_msg_data = SIMDAT.SimulationDataOrder(own_order, simulation_order_id.new_id(),
                                                       action=COMMON.OrderAction.user_added)
            uadd_msg_data.update(state=COMMON.OrderState.acti, execution_time=self.timestamp)

            self.executed_own_order_count[(product.delivery_start, product.delivery_end)] += 1
            self.execution_msg.data.append(uadd_msg_data.data)
            self.execution_msg.properties.update(properties)

    def _handle_entries(self, body, properties):
        """
        Acknowledge entry orders and simulate potential matches.

        :param body: A message (body) of message_type COMMON.Request.order_delete
        :type body: dict
        """
        exchange_id = body["exchange"]
        for line in body["data"]:
            if body["exchange"] == COMMON.Exchange.trayport:
                line["engine_id"] = COMMON.EngineID.simulation
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            sim_order_id = simulation_order_id.new_id()
            # TODO(MAD) UADD/UDEL/UMOD message exchange specific (trayport format),  UADD needs engine_id and broker_id

            uadd_msg_data = SIMDAT.SimulationDataOrder.from_order_request(line, sim_order_id,
                                                                          action=COMMON.OrderAction.user_added)
            uadd_msg_data.update(execution_time=self.timestamp)

            self.executed_own_order_count[(product.delivery_start, product.delivery_end)] += 1
            self.execution_msg.data.append(uadd_msg_data.data)
            self.execution_msg.properties.update(properties)

            own_order = APITR.OwnOrder.from_data_line(uadd_msg_data.data, product, exchange_id)

            self._simulate_match_with_public_orderbook(
                own_order,
                product,
                (line.get("side") or line.get("direction")) == COMMON.Direction.sell,
                properties
            )
            if _is_own_ioc_order(own_order) and self.remaining_own_quantities[own_order] > 0.:
                # delete IOC order right after it was added, if the quantity was not exhausted in trades
                msg_data = SIMDAT.SimulationDataOrder(own_order, own_order.order_id,
                                                      action=COMMON.OrderAction.system_deleted)
                msg_data.update(execution_time=self.timestamp)

                self.execution_msg.data.append(msg_data.data)
                self.execution_msg.properties.update(properties)

    def _handle_modifies(self, body, properties):
        """
        Respond to  order modifies by UDEL/UADD(+ optionally PEXE) or by FEXE.

        In case of PEXE, the PEXE message has the same order_id as the UADD message (the new order_id),
        and the UADD message has the new quantity after the Trade.

        :param body: A message (body) of message_type COMMON.Request.order_modify
        :type body: dict
        """
        for line in body["data"]:
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            old_id = line["order_id"]
            original_own_order = self._get_own_order_if_allowed(line, product)
            if not original_own_order:
                continue  # Old modify request.
            if original_own_order.state == COMMON.OrderState.hibe:
                # Deactivated (Comtrader) orders -> do not change order_id.
                # On Nordpool, the delivery area id is not part of the sent message...
                line.setdefault("delivery_area_id", original_own_order.delivery_area_id)
                line.setdefault("side", line.get("direction", original_own_order.direction))

                umod_msg_data = SIMDAT.SimulationDataOrder.from_order_request(line, old_id,
                                                                              action=COMMON.OrderAction.user_modified)
                umod_msg_data.update(state=COMMON.OrderState.hibe,
                                     execution_time=self.timestamp,
                                     user=original_own_order.original_user
                                     )
                self.execution_msg.data.append(umod_msg_data.data)
                self.execution_msg.properties.update(properties)
            else:
                udel_msg_data = SIMDAT.SimulationDataOrder(original_own_order, old_id,
                                                           action=COMMON.OrderAction.user_deleted)
                udel_msg_data.update(execution_time=self.timestamp)

                self.execution_msg.data.append(udel_msg_data.data)
                self.execution_msg.properties.update(properties)

                self.deleted_order_ids.add(old_id)
                # On Nordpool, modification messages are missing some attributes.

                # direction is trayport specific, but we use side to be uniform to other exchanges
                line.setdefault("side", line.get("direction", original_own_order.direction))

                line.setdefault("delivery_area_id", original_own_order.delivery_area_id)
                if "inst_specifier" in line:
                    line["delivery_area_id"] = line["inst_specifier"][0]["instrument_id"]

                uadd_msg_data = SIMDAT.SimulationDataOrder.from_order_request(line,
                                                                              order_id=simulation_order_id.new_id(),
                                                                              action=COMMON.OrderAction.user_added)
                uadd_msg_data.update(execution_time=self.timestamp,
                                     user=original_own_order.original_user
                                     )

                self.executed_own_order_count[(product.delivery_start, product.delivery_end)] += 1
                self.execution_msg.data.append(uadd_msg_data.data)
                self.execution_msg.properties.update(properties)

                own_order = APITR.OwnOrder.from_data_line(uadd_msg_data.data, product, self.exchange.internal_id)
                self._simulate_match_with_public_orderbook(
                    own_order,
                    product,
                    line["side"] == COMMON.Direction.sell,
                    properties
                )

    def _handle_trade_order(self, body, properties):
        """
        Respond to a trade_order messages

        :param body: A message (body) of message_type COMMON.TrayportRequest.trade_order
        :type body: dict
        """

        for line in body["data"]:
            txt_dict = ATUTIL.parse_order_tags(line["txt"])
            line.update(txt_dict)
            product = self._get_product(body["exchange"], line, self.exchange.products.get_by_id)
            public_order_id = line.get("order_id")
            public_order = product.orders.get_public_order_by_order_id(public_order_id, broker_id=line.get("broker_id"))
            # if a public_order exists, we can try to match it with the trade_order
            if public_order:
                # since no data is saved for the _TradeOrder, we create an OwnOrder object with the necessary fields,
                # to generate a trade.
                own_order = APITR.OwnOrder(
                    portfolio_key=line["portfolio_key"],
                    execution_restriction=COMMON.ExecutionRestriction.non,
                    validity_restriction="NON",
                    validity_date=None,
                    initial_order_id=None,
                    direction=(
                        COMMON.Direction.sell
                        if public_order.direction == COMMON.Direction.buy
                        else COMMON.Direction.buy
                    ),
                    product=product,
                    delivery_area_id=public_order.delivery_area_id,
                    quantity=line["quantity"],
                    price=public_order.price,
                    exchange=COMMON.Exchange.trayport,
                    broker_id=line["broker_id"],
                    state=COMMON.OrderState.acti,
                    tags=txt_dict,
                    execmode=line["execmode"],
                )
                own_order._internal_id = line["internal_id"]
                own_order.tags["internal_id"] = line["internal_id"]
                self._simulate_match_with_public_orderbook(
                    own_order,
                    product,
                    own_order.direction == COMMON.Direction.sell,
                    message_properties=properties
                )
            else:
                # if the public order is not found anymore, something went wrong on the exchange side,
                # order has already been traded or was removed. Therefore, an error is returned.
                self._generate_trade_order_error_response(body["timestamp"], properties, line)

    def _simulate_match_with_public_orderbook(self, own_order, product, is_sell, message_properties):
        """
        Own entry or modify orders are immediately matched.

        :param product: The product the own order is for.
        :type product: APITR.Product
        :param own_order: The own order we try to match
        :type own_order: APITR.OwnOrder
        :param is_sell: True if the own_order is a sell-order.
        :type is_sell: bool
        """
        order_filter = COMMON.OrderFilter.public_buy if is_sell else COMMON.OrderFilter.public_sell
        delivery_area = own_order.delivery_area_id
        public_orders_to_match = product.orders.get(delivery_area, order_filter=order_filter)
        for public_order in sorted(public_orders_to_match, key=lambda o: o.price, reverse=is_sell):
            self._simulate_single_match(own_order, public_order, message_properties)

    def _generate_trade_order_error_response(self, timestamp, properties, line):
        self.error_msg.data.append(SIMDAT.simulate_trayport_trade_order_error_response(line))
        self.error_msg.properties.update(properties)

    def _generate_orderbook_or_public_trade_messages(self, original_message, original_message_properties):
        """
        Generate an update message for public orders that have been matched with outgoing own orders.

        :param original_message: unused. (Kept for compatibility with parent class)
        :return: A list with 0 or 1 messages
        :rtype: list[dict[str, str]]
        """
        orderbook_data = []
        for order, quantity in self.remaining_public_quantities.items():
            public_order_data = SIMDAT.SimulationDataPublicOrder(order, order.order_id)
            if quantity == 0:
                pub_state = COMMON.OrderState.iact
            else:
                pub_state = COMMON.OrderState.acti
            public_order_data.update(quantity=quantity, state=pub_state, revision=order.revision)
            orderbook_data.append(public_order_data.data)
        if orderbook_data:
            return [{"body": {"data": orderbook_data,
                              "message_type": COMMON.Response.order_book,
                              "timestamp": self.timestamp,
                              "exchange": self.exchange.internal_id,
                              },
                     "properties": original_message_properties}]
        return []

    def _create_own_trade_data(self, own_order, public_object, traded_quantity):
        """
        Create a simulation data object for own trades.

        :param own_order: The Own order being traded
        :type own_order: APITR.OwnOrder
        :param public_object: The public order/ trade being matched
        :type public_object: APITR.PublicTrade or APITR.PublicOrder
        :param traded_quantity: The amount being traded
        :type traded_quantity: float
        :return: An entry that can be appended to a message's data field.
        :rtype: dict
        """
        return _create_own_trade_data(own_order, public_object, traded_quantity,
                                      self.timestamp, self.exchange, is_aggressor=True)


def _prices_match(price_a, price_b, a_is_selling):
    """
    Return True, if a trade can be created between two orders with prices price_a and price_b
    :param price_a: The first price
    :type price_a: float
    :param price_b: The second price
    :type price_b: float
    :param a_is_selling: True, if price_a corresponds to the selling party, False otherwise.
    :type a_is_selling: bool
    :rtype: bool
    """
    return a_is_selling and price_a <= price_b or not a_is_selling and price_a >= price_b


def _is_own_ioc_order(order):
    """
    Returns True, if the order is an OwnOrder and has execution restriction IOC.

    :type order: APITR.Order
    :rtype: bool
    """
    return isinstance(order, APITR.OwnOrder) and order.execution_restriction == COMMON.ExecutionRestriction.ioc


def _create_pexe_fexe_data(own_order, remaining_qty, execution_time):
    """
    Create an order_execution message data for an own order that has been traded.

    :type own_order: APITR.OwnOrder
    :param remaining_qty: The remaining quantity of the Order.
    :type remaining_qty: float
    :return: An entry that can be appended to a message's data field.
    :rtype: dict
    """
    if remaining_qty == 0:
        action = COMMON.OrderAction.full_execution
    else:
        action = COMMON.OrderAction.partial_execution

    execution_data = SIMDAT.SimulationDataOrder(own_order, own_order.order_id,
                                                quantity=remaining_qty, action=action)
    execution_data.update(execution_time=execution_time)
    return execution_data.data


def _create_own_trade_data(own_order, public_object, traded_quantity, timestamp, exchange, is_aggressor):
    """
    Create an own_trade message data for an own order that has been traded.

    :param own_order: The own order that has been traded
    :type own_order: APITR.OwnOrder
    :param public_object: The other order that trades
    :type public_object: APITR.PublicTrade or APITR.PublicOrder
    :param traded_quantity: The trade quantity in MW
    :type traded_quantity: float
    :param timestamp: The time of the simulated trade
    :type timestamp: float
    :param exchange: the exchange of the own trade
    :type exchange: autotrader_core.exchanges.Exchange
    :param is_aggressor: True if we are the aggressor
    :type is_aggressor: bool
    :return: An entry that can be appended to a message's data field.
    :rtype: dict
    """

    if isinstance(public_object, APITR.PublicTrade):
        price = own_order.price
    else:
        # We take the price of the order that exists on the true market, so our
        # simulated prices are closer to the real market.
        # For this reason we always take the price of the public order, no matter what order
        # came first to the exchange.
        price = public_object.price

    # Own Trade

    # for trade_orders no own order_id exists, therefore we use the public order id
    if exchange.internal_id == COMMON.Exchange.trayport and not hasattr(own_order, "order_id"):
        order_id = public_object.order_id
    else:
        order_id = own_order.order_id
    msg = SIMDAT.SimulationDataTrade(own_order, order_id,
                                     trade_id=simulation_order_id.new_id(),
                                     quantity=traded_quantity,
                                     user="{}_SIMULATION".format(exchange.internal_id),
                                     execution_time=timestamp,
                                     exchange=exchange,
                                     price=price,
                                     is_aggressor=is_aggressor)
    return msg.data
