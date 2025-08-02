""" This module implements the base class of the Synthetic Orders, from which both
SyntheticOrders and Selectors are subclassed"""
from __future__ import absolute_import
import collections
import time
import six
import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRATEGY
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
import autotrader_lib.package_config_fields as PKG_CONF
import autotrader_synthetic.config_util as CONF
import autotrader_synthetic.errors as ERR

log = FLOG.getLogger("autotrader_synthetic.synthetic_order_base")

SO_STATUS_NO_FLICKER_WINDOW = 10
SO_STATUS_NO_FLICKER_MAX_COUNT = 50
SO_TOO_MANY_STATUS_CHANGES_REASON = "Too many state changes in the last {} seconds".format(SO_STATUS_NO_FLICKER_WINDOW)


class SyntheticOrderBase(PKG_CONF.Configurable):
    """ This is the main behavior implementing object but this is only a parent class which should be subclassed
    for different behaviors

    The base class pre-implements the following behaviors:
        - self-configuration when receiving a valid configuration payload
        - reporting of configuration options
        - deletion logic
        - helper functions:
            - traded volume calculation
            - exposed order volume calculation

    """
    slot_name = CONF.SyntheticOrderConfigField(caption="slot_name",
                                               description="Used for identifying the slot placed by this "
                                                           "synthetic order",
                                               expected_type=str,
                                               mandatory=False,
                                               read_only=False,
                                               hidden=True)

    from_ts = CONF.SyntheticOrderConfigField("from_ts", "Synthetic Order validity timestamp from",
                                             PKG_CONF.TimestampType, default=0, hidden=True, mandatory=True)

    to_ts = CONF.SyntheticOrderConfigField("to_ts", "Synthetic Order validity timestamp to",
                                           PKG_CONF.ExpiryTsType, mandatory=True, default=float("inf"))

    market_area = CONF.SyntheticOrderConfigField("market_area",
                                                 description="The market area id for this particular synthetic order,"
                                                             " this will be set by the strategy automatically",
                                                 expected_type=PKG_CONF.InstrumentIdType,
                                                 mandatory=True)

    # the default is None since broker_id is only needed for Trayport
    broker_id = CONF.SyntheticOrderConfigField("broker_id", "Broker ID for the Synthetic Order",
                                               expected_type=PKG_CONF.BrokerIdType)

    # MIFID fields
    liquidity_provision = CONF.SyntheticOrderConfigField("liquidity_provision",
                                                         description="The liquidity provision MIFID field",
                                                         expected_type=bool)

    trading_capacity = CONF.SyntheticOrderConfigField(
        "trading_capacity",
        "The trading_capacity MIFID field",
        expected_type=PKG_CONF.Enum(COMMON.TradingCapacityType.__slots_container_py2__))

    execution_maker = CONF.SyntheticOrderConfigField("execution_maker",
                                                     "The execution_maker MIFID field",
                                                     expected_type=str)

    decision_maker = CONF.SyntheticOrderConfigField("decision_maker",
                                                    "The decision_maker MIFID field",
                                                    expected_type=str)

    derivative_indicator = CONF.SyntheticOrderConfigField("derivative_indicator",
                                                          description="The derivative_indicator MIFID field",
                                                          expected_type=bool,
                                                          )

    dea = CONF.SyntheticOrderConfigField("dea", "The dea MIFID field",
                                         expected_type=bool)

    dea_client_id = CONF.SyntheticOrderConfigField("dea_client_id", "The dea_client_id MIFID field",
                                                   expected_type=str)

    trading_account = CONF.SyntheticOrderConfigField("trading_account",
                                                     "If set, orders are placed with this trading account on"
                                                     " the exchange/ broker",
                                                     expected_type=PKG_CONF.TradingAccountType,
                                                     )

    def __init__(self, tick_size, identifier, configuration):
        """

        :param tick_size: Price tick size is a dynamic property in case of Trayport and is
                            therefore not part of the configuration
        :type tick_size: float
        :param identifier: identifier of the synthetic order
        :type identifier: str
        :param configuration: The configuration payload used to initially configure the SyntheticOrder
                                see .configuration() docstring for more information
        :type configuration: dict
        """
        self.__deleted = False
        self.tick_size = tick_size
        self.identifier = identifier

        errors = self._apply_defaults()
        if errors:
            raise ERR.ConfigurationError("; ".join(errors))

        # run this function only once since this will not change dynamically
        self._all_configurators = self._config_options()

        # this will raise if we miss the initial configuration that are required
        self._verify_required(configuration)

        # this is the initial configuration step
        self.configure(configuration)
        self._status = None
        self.status = COMMON.SyntheticOrderStates.passive
        self._status_text = None
        self._silenced_status = None
        self.status_text = "passive"

        self._needs_database_update = True
        self._status_change_times = collections.deque(maxlen=SO_STATUS_NO_FLICKER_MAX_COUNT + 1)

    def __repr__(self):
        return (
            "SyntheticOrder>>{class_name}(tick_size={tick_size}, identifier={identifier}, configuration=...) "
            "<slot_name={slot_name}, market_area={market_area}, broker_id={broker_id}, "
            "status={status}, status_text={status_text}>".format(
                class_name=self.__class__.__name__,
                tick_size=self.tick_size,
                identifier=self.identifier,
                slot_name=self.slot_name,
                market_area=self.market_area,
                broker_id=self.broker_id,
                status=self.status,
                status_text=self.status_text)
        )

    def mark_for_database_update(self):
        """
        Sets the _needs_database_update flag to True, such that the strategy will soon update this SO in the database
        """
        self._needs_database_update = True

    def needs_database_update(self):
        """
        Called by the synthetic order strategy, to check if any change to the configuration or state of this synthetic
        has happened since the last time this function was called that needs to be written to the database.

        .. warning::
            As only changes since the last call to this function are taken into account, this function should only be
            called by the SyntheticOrderStrategyBase, before writing an update to the database.

        :meta private:
        :rtype: bool
        """
        return_value = self._needs_database_update
        self._needs_database_update = False
        return return_value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if self._status != value:
            self.mark_for_database_update()
        self._status = value

    @property
    def status_text(self):
        return self._status_text

    @status_text.setter
    def status_text(self, value):
        if self._status_text != value:
            self.mark_for_database_update()
        self._status_text = value

    @property
    def deleted(self):
        """ A read-only property to check if a SyntheticOrder has been set to deleted """
        return self.__deleted

    @deleted.setter
    def deleted(self, value):
        """ You are not allowed to set a deleted order back to not deleted """
        if self.__deleted is True and value is False:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.cannot_reset_deletion)
        else:
            self.__deleted = value

    def delete(self, status_text=None):
        """ The method to set the SyntheticOrder as deleted

        NOTE: You are not allowed to set a deleted order back to not deleted so this function just wraps the deletion
        """
        log.debug("Synthetic order with identifier = %s is being deleted with status_text = %s",
                  self.identifier, status_text)
        self.deleted = True
        # Note: We set the status directly and bypass the set_status function, as changing away from "is deleting"
        # is anyway impossible, so there won't be any more flickering.
        self.status = COMMON.SyntheticOrderStates.deleting
        self.status_text = status_text if status_text is not None else ""

    def set_status(self, new_status, status_text=None):
        """
        Set the status of the synthetic order.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :param new_status: The new status of the synthetic order. One of COMMON.SyntheticOrderStates
        :type new_status: str
        :param status_text: A reason explaining why the synthetic order is in this status. Usually
                            used for warnings, errors and passive synthetic orders
        :type status_text: str
        """
        if status_text is None:
            status_text = ""
        if self.deleted and new_status != COMMON.SyntheticOrderStates.deleting:
            # "is deleting" is the strongest status and changing away from it is disallowed.
            return

        current_time = time.time()
        while self._status_change_times and self._status_change_times[0] < current_time - SO_STATUS_NO_FLICKER_WINDOW:
            self._status_change_times.popleft()

        if self.status_text == SO_TOO_MANY_STATUS_CHANGES_REASON and len(self._status_change_times) > 0:
            if (new_status, status_text) != self._silenced_status:
                self._silenced_status = new_status, status_text
                self._status_change_times.append(current_time)
            log.debug("Status %r %r ignored, because we are still in warning state until %s",
                      new_status, status_text, self._status_change_times[-1] + SO_STATUS_NO_FLICKER_WINDOW)
            return

        if self.status != new_status or self.status_text != status_text:
            self._status_change_times.append(current_time)
            if len(self._status_change_times) > SO_STATUS_NO_FLICKER_MAX_COUNT:
                log.info("Going into warning status (instead of changing status to  %r %r), because there were "
                         "too many recent status changes.", new_status, status_text)
                self.status = COMMON.SyntheticOrderStates.warning
                self.status_text = SO_TOO_MANY_STATUS_CHANGES_REASON
                self._silenced_status = new_status, status_text
            else:
                self.status = new_status
                self.status_text = status_text

    def deactivate(self, status_text=None):
        """
        Set the synthetic order status to passive.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :param status_text: text to set status_text
        :type status_text: str
        :return: None
        """
        self.set_status(COMMON.SyntheticOrderStates.passive, status_text)

    def activate(self):
        """
        Set the synthetic order status to active.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :return: None
        """
        self.set_status(COMMON.SyntheticOrderStates.active)

    def withhold(self):
        """
        Set the synthetic order status to withheld.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :return: None
        """
        self.set_status(COMMON.SyntheticOrderStates.withheld)

    def warn(self, status_text):
        """
        Set the synthetic order status to warning.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :param status_text: text to set status_text
        :type status_text: str
        :return: None
        """
        self.set_status(COMMON.SyntheticOrderStates.warning, status_text)

    def fault(self, status_text):
        """
        Set the synthetic order status to faulted.

        Note: This is called by the SyntheticOrderStrategyBase. Calling this from custom strategy or synthetic order
        code is usually not necessary and is not advised.

        :param status_text: text to set status_text
        :type status_text: str
        :return:
        """
        self.set_status(COMMON.SyntheticOrderStates.faulted, status_text)

    def configure(self, incoming_configuration_dict):
        """ This is the function which handles the configuration of the synthetic orders

        Example configuration payload -> incoming_configuration_dict:
                {slot_name: "buy_slot",
                 market_area: COMMON.Area.ttf,
                 broker_id: "20"}

        Example configuration options returned:

            {'broker_id': {'config_type': 'basestring',
                           'default': 'None',
                           'description': 'Broker ID for the Synthetic Order',
                           'name': 'broker_id',
                           'required': 'False'},

             'market_area': {'config_type': 'basestring',
                             'default': 'None',
                             'description': 'The market area id for this particular synthetic order,this will be
                             set by the strategy automatically',
                             'name': 'market_area',
                             'required': 'False'},

             'slot_name': {'config_type': 'basestring',
                           'default': 'None',
                           'description': 'Used for identifying the slot placed by this synthetic order',
                           'name': 'slot_name',
                           'required': 'True'}}


        :param incoming_configuration_dict: The configuration payload (see above example)
        :type incoming_configuration_dict: dict
        :return: None
        """
        # Store the old config, so in case re-configuration fails, we can restore it
        old_config = self.get_configuration()
        is_update = old_config["slot_name"] is not None
        unsupported_keys = set(incoming_configuration_dict) - set(descr_name
                                                                  for descr_name, descr_obj in self._all_configurators)
        if unsupported_keys:
            raise ERR.ConfigurationError(
                ERR.ConfigurationErrorReason.unsupported_fields.format(", ".join(sorted(unsupported_keys))))
        try:
            for config_entry_name, config_descriptor_obj in self._all_configurators:
                config_descriptor_name = config_descriptor_obj.name
                if config_descriptor_name in incoming_configuration_dict:
                    if (getattr(config_descriptor_obj, "read_only", False)
                            and incoming_configuration_dict[config_descriptor_name] != getattr(self,
                                                                                               config_descriptor_name)):
                        raise PKG_CONF.FieldValidationError("The field {!r} is read-only".format(config_entry_name))
                    setattr(self, config_entry_name, incoming_configuration_dict[config_descriptor_name])
            self.validate_new_configuration(incoming_configuration_dict)
        except Exception:
            if is_update:
                log.info("Could not reconfigure synthetic order. Restoring old configuration")
                self.configure(old_config)
            raise

    def _verify_required(self, initial_configuration):
        """ This function helps verify that the required descriptors will be provided on initial configuration

        :param initial_configuration: The configuration dict initially passed on init
        :type initial_configuration: dict()
        :return: None
        """
        for descr_name, descriptor in self._all_configurators:
            if isinstance(descriptor, CONF.ConfigOptionDescriptor):
                descr_set = descriptor.required
            else:
                descr_set = descriptor.mandatory and descriptor.default is None
            if descr_set and descr_name not in initial_configuration:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.config_is_required.format(
                    config_name=descr_name
                ))

    def act(self, localview, additional_views, timestamp):
        """ This function is the core behavioral implementation of any SyntheticOrder which can return a single slot

        IMPORTANT: A Synthetic Order should always return a single slot!

        :param localview: a LocalView object created in the current loop for the product-area-strategy combination
        :type localview: autotrader_synthetic.local_view.LocalView
        :param additional_views: The created ViewFactory object containing the additional views
        :type additional_views: autotrader_synthetic.factory_view.ViewFactory
        :param timestamp: The timestamp of the callback loop
        :type timestamp: float
        :return: returns a single slot, anything that returns more slots would be a selector
        :rtype: STRATEGY.PositionSlot
        """
        raise NotImplementedError  # pragma: no cover

    # region: WRAPPERS

    def exposed_order_volume(self, localview):
        """ Helper function to get the total volume of orders on the exchange

        :param localview: a LocalView object created in the current loop for the product-area-strategy combination
        :type localview: autotrader_synthetic.local_view.LocalView
        :return: Returns the total volume of the orders on the exchange relating to this slot name
        :rtype: float
        """
        return localview.exposed_order_volume(self.slot_name)

    def traded_volume(self, localview, direction="balanced"):
        """ Helper function to get the volume of the trades on the exchange relating to this synthetic order

        :param localview: a LocalView object created in the current loop for the product-area-strategy combination
        :type localview: autotrader_synthetic.local_view.LocalView
        :param direction: One of "balanced", "buy" and "sell"
        :type direction: str
        :return: Returns the total traded volume for the specified side
        :rtype: float
        """
        if direction == "balanced":
            return localview.traded_volume_buy(self.slot_name) - localview.traded_volume_sell(self.slot_name)
        elif direction == "buy":
            return localview.traded_volume_buy(self.slot_name)
        elif direction == "sell":
            return localview.traded_volume_sell(self.slot_name)

    def remove(self, status_text=None):
        """ Helper method used to remove outstanding orders for this product and slot name

        :return: Returns the slot instance
        :rtype: STRATEGY.PositionSlot
        """
        log.debug("Synthetic Order with identifier: %s, is removing orders with slot name: %s. Reason: %s",
                  self.identifier, self.slot_name, status_text)
        self.deactivate(status_text)
        return self.create_slot(COMMON.Direction.buy, quantity=0)

    def create_slot(self, direction, quantity=None, price=None, info=None, **kwargs):
        """ A helper wrapper function to create a slot but manage the bookkeeping

        :param direction: Buy (bid) or sell (ask) order, member of :class:`COMMON.Direction`
        :param quantity: quantity of order wish in MW
        :param price: price of order wish in Euro per MWh
        :type direction: str, :class:`COMMON.Direction`
        :type quantity: float
        :type price: float
        :param info: additional information to be saved with the slot.
                     This info will be seen in the comment or text field of the order and the trade, if executed
        :type info: str
        :param kwargs: Keyword arguments will be passed on to the PositionSlot constructor
        :return: Returns the slot instance
        :rtype: STRATEGY.PositionSlot
        """
        log.debug("The SyntheticOrder of class: {class_name}; with identifier: {identifier}; is creating a slot with "
                  "slot_name: {slot_name} ({direction}) {quantity}@{price}".format(class_name=self.__class__.__name__,
                                                                                   identifier=self.identifier,
                                                                                   slot_name=self.slot_name,
                                                                                   direction=direction,
                                                                                   quantity=quantity,
                                                                                   price=price))
        if info is None:
            info = self.get_default_info()

        return STRATEGY.PositionSlot(slot_type=self.slot_name,
                                     direction=direction,
                                     quantity=quantity,
                                     price=price,
                                     broker_id=self.broker_id,
                                     tick_size=self.tick_size,
                                     liquidity_provision=self.liquidity_provision,
                                     trading_capacity=self.trading_capacity,
                                     execution_maker=self.execution_maker,
                                     decision_maker=self.decision_maker,
                                     derivative_indicator=self.derivative_indicator,
                                     dea=self.dea,
                                     dea_client_id=self.dea_client_id,
                                     trading_account=self.trading_account,
                                     info=info,
                                     **kwargs)
        # TODO: Mifid fields + trading account TEST !!!!

    # endregion

    # region: CONFIG REPORTING

    @classmethod
    def get_attribute_groups(cls):
        """
        Return an ordered list of all StrategyConfigFields in the parameter groups they belong to.

        :rtype: list
        """
        return [{"caption": "General Settings",
                 "description": "General parameters for this synthetic order",
                 "config_fields": ["slot_name", "from_ts", "to_ts", "market_area", "broker_id", "trading_account"]},
                {"caption": "Mifid Settings",
                 "description": "These mifid-related settings can be used to override the"
                                " default set on the strategy level.",
                 "config_fields": ["liquidity_provision", "trading_capacity", "execution_maker", "decision_maker",
                                   "derivative_indicator", "dea", "dea_client_id"]}]

    @classmethod
    def _config_options(cls):
        """ This function takes care of being able to get a list of all config descriptors in the inheritance tree """
        all_config_descriptors = list()

        # it will collect all the base classes and recursively ask them to return their config options
        for base_class in cls.__bases__:
            if hasattr(base_class, "_config_options"):
                all_config_descriptors.extend(base_class._config_options())

        # it then returns its own descriptors
        own_configs = [(attr, val) for attr, val in cls.__dict__.items()
                       if isinstance(val, (CONF.ConfigOptionDescriptor, CONF.SyntheticOrderConfigField))]

        # and it then completes the recursion loop with extend
        all_config_descriptors.extend(own_configs)

        return all_config_descriptors

    # endregion

    def get_default_info(self):
        """default info added to the comment/text field of the order or trade

        This can explicitly be overwritten by the child class if necessary to represent relevant information,
        such as execution mode or exposures at the moment of order creation.

        :rtype: str
        :return: default stats
        """
        return "soi_{}/name_{}/class_{}".format(self.identifier, self.slot_name, self.__class__.__name__)

    def get_configuration(self):
        return {attr[0]: getattr(self, attr[0]) for attr in self._config_options()}

    def validate_new_configuration(self, incoming_configuration):
        """
        This function is to be overwritten by the Synthetic Order. Its purpose is to do some additional field validation
         or comparison after the individual field validations are already done.

        :param incoming_configuration: The new SO config received when creating or modifying a Synthetic Order
        """
        pass


if __name__ == "__main__":
    raise RuntimeError("This module should not be directly executed")  # pragma: no cover
