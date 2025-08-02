import autotrader_core.common as COMMON
import autotrader_core.exchange_simulator as ATSIM

DEFAULT_LIMIT_VALUES = {COMMON.StrategyJsonKey.TS.limit_buy_price: 1000.,
                        COMMON.StrategyJsonKey.TS.limit_buy_vol: 1000.,
                        COMMON.StrategyJsonKey.TS.limit_sell_vol: 1000.,
                        COMMON.StrategyJsonKey.TS.limit_sell_price: -1000}


def _get_strategies(simulation_definition, timestamp=None, strategy_name=None):
    """
    Get a list of strategies in the simulation definition feed.
    Strategies can be further queried based on the timestamp when the strategy definition is loaded in the test
    and its name.
    """
    strategies = []
    for current_timestamp, current_definitions in simulation_definition["definition"]["timeline"]:
        if any([timestamp and current_timestamp == timestamp,
                not timestamp]):
            for current_name, current_definition in current_definitions["data"]["strategy_objects"].items():
                if any([strategy_name and strategy_name == current_name,
                        not strategy_name]):
                    strategies.append(current_definition)
    return strategies


def set_default_limits(simulation_definition):
    """This callback sets limits to some very high numbers if not
       set manually in the strategy definition file.
       It can be used when limits do not play any role in the test."""

    # limits for all strategies and their definitions will be changed
    for strategy in _get_strategies(simulation_definition):
        for timeseries_name, default_value in DEFAULT_LIMIT_VALUES.items():
            for timeslot in strategy[timeseries_name]:
                if timeslot["value"] is None:
                    timeslot["value"] = default_value


class IterativeSimulator(ATSIM.ExchangeSimulator):
    """
    Intercept an exchange message and simulate all AT's responses and responses to responses etc.
    """

    def __init__(self, autotrader, exchange_id, nasty_orders_generators, trayport_init_directory=None,
                 intercept_msgs_to_autotrader=None, omt_simulator=None):
        """
        :param autotrader: A reference to the autoTRADER parent object
        :type autotrader: autotrader_core.api.AutoTrader
        :param exchange_id: The exchange to simulate.
        :type exchange_id: str
        :param nasty_orders_generators: A list of objects which implement generate_messages to react on autoTRADER
                                        messages. Used to test botrace protections and botrace scenarios.
        :type nasty_orders_generators: list or None
        :param trayport_init_directory: Path to the directory where the init files related to the used exchange feed
                                        for TRAYPORT are stored. Not needed for other exchanges and when simulating
                                        GasPrompt products.
        :type trayport_init_directory: str or None
        :param intercept_msgs_to_autotrader: A function that receives all messages from the exchange simulator before
                                             they are sent to autoTRADER. This can be used to make assertions on these
                                             messages. Additionally, by modifying the list of messages in-place, this
                                             function can control what messages are sent to autoTRADER and thus test
                                             specific scenarios with different exchange behavior.
        :type intercept_msgs_to_autotrader: function or None
        :param omt_simulator: omt limit parameters for the simulation
        :type omt_simulator: autotrader_core.exchange_simulator.OMTSimulator
        """
        super(IterativeSimulator, self).__init__(autotrader, exchange_id, trayport_init_directory, omt_simulator)
        self.nasty_orders_generators = nasty_orders_generators
        if intercept_msgs_to_autotrader is None:
            self.intercept_msgs_to_autotrader = lambda responses: None
        else:
            self.intercept_msgs_to_autotrader = intercept_msgs_to_autotrader

    def run_once(self, action_type, timestamp, auto_trader_child, send_func):
        """
        Run housekeeping tasks once.

        This includes freeing the vault on every timer event and an update from json

        :param action_type: "timer" or "timer_fast"
        :type action_type: str
        :type timestamp: float
        :type auto_trader_child: autotrader_core.api.AutoTrader
        """
        self.autotrader.run_once(action_type=action_type, timestamp=timestamp)
        auto_trader_child.run_once(action_type=action_type, timestamp=timestamp)
        response_messages = send_func.cache().get("res", [])
        send_func.clear_cache()

        # Outgoing answers by autotrader
        self.send(response_messages)

    def receive(self, data_dict):
        """
        Run simulation with one message from the exchange/ the timer.

        This first runs the incoming message through the simulator, then updates AutoTrader, handles all responses
        from AutoTrader through simulator and the responses to the simulations etc...
        """
        incoming_msgs = super(IterativeSimulator, self).receive(data_dict)
        if self.intercept_msgs_to_autotrader:
            self.intercept_msgs_to_autotrader(incoming_msgs)
        changed_orders = []  # Used only for nasty_orders
        for message in incoming_msgs:
            if message["body"]["message_type"] == "order_execution":
                changed_orders.extend([entry["order_id"] for entry in message["body"].get("data", [])])
            self.autotrader.update_from_json(message["body"], message.get("properties", {}))
            self.autotrader.send_to_children(message["body"])
        self._process_nasty_orders(changed_orders)
        response_messages = self.exchange.send_func.cache().get("res", [])
        self.exchange.send_func.clear_cache()
        # Outgoing answers by autotrader
        self.send(response_messages)

    def send(self, data_dicts):
        """
        Handle all responses in self.autotrader.epex.send_func.cache until it remains empty.
        """
        i = 0
        while data_dicts:
            i += 1
            if i > 100:
                # This should not happen, because the orderbook becomes more empty as we continue to trade.
                print("PROBLEM DETECTED infinit loop?")
                raise RuntimeError("Infinite loop?")

            responses = super(IterativeSimulator, self).send(data_dicts)
            self.intercept_msgs_to_autotrader(responses)

            changed_orders = []  # Used only for nasty_orders
            for message in responses:
                if message["body"]["message_type"] == "order_execution":
                    changed_orders.extend([entry["order_id"] for entry in message["body"].get("data", [])])
                # This might refill send_func.cache()
                self.autotrader.update_from_json(message["body"], message.get("properties", {}))
                self.autotrader.send_to_children(message["body"])
            self._process_nasty_orders(changed_orders)

            data_dicts = self.exchange.send_func.cache().get("res", [])
            self.exchange.send_func.clear_cache()

    def _process_nasty_orders(self, changed_orders):
        if not self.nasty_orders_generators:
            return
        exchange = self.autotrader.get_exchange(self.exchange_id)
        if not exchange.allowed:
            return
        for product in exchange.products.get_active_products():
            orders = [o for o in product.orders.get(order_filter=COMMON.OrderFilter.own) if hasattr(o, "order_id")
                      and o.order_id in changed_orders]
            areas = set(order.delivery_area_id for order in orders)
            for area in areas:
                for nasty_order_generator in self.nasty_orders_generators:
                    for msg in nasty_order_generator.generate_messages(self.autotrader, product, area,
                                                                       exchange.internal_id,
                                                                       self.autotrader.current_timestamp):
                        self.autotrader.update_from_json(msg, {})
                        self.autotrader.send_to_children(msg)


def _convert_to_list(to_convert):
    """Make the input into a list if it is not one already.

    :type to_convert: list or object or None
    :rtype: list
    """
    if to_convert is None:
        return []
    elif isinstance(to_convert, list):
        return to_convert
    else:
        return [to_convert]
