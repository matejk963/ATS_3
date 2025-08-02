""" This module contains the implementation of the SyntheticOrderStrategyBase, that is the base class from
which strategies using SyntheticOrders should be subclassed """

from __future__ import absolute_import
import collections
import sys
import traceback
import re
import six
import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.persistence as PERSIST
import autotrader_core.strategy as STRATEGY
import autotrader_lib.package_config_fields as PKG_CONF

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
import autotrader_lib.util as ALU
import autotrader_synthetic.errors as ERR
import autotrader_synthetic.local_view as LV
import autotrader_synthetic.factory_view as FV
import autotrader_synthetic.synthetic_order_selectors.synthetic_selector_base as SELBASE
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB  # noqa: F401

log = FLOG.getLogger("autotrader_synthetic.synthetic_order_strategy_base")

# only log every 10000th deprecation message to avoid too many logs
SILENCE_PERIOD_DEPREC_LOG = 10000


class MiFIDField(object):
    trading_capacity = "trading_capacity"
    decision_maker = "decision_maker"
    execution_maker = "execution_maker"
    derivative_indicator = "derivative_indicator"
    dea = "dea"
    dea_client_id = "dea_client_id"
    liquidity_provision = "liquidity_provision"

    @classmethod
    def get_all(cls):
        return (cls.trading_capacity, cls.decision_maker, cls.execution_maker, cls.derivative_indicator, cls.dea,
                cls.dea_client_id, cls.liquidity_provision)


class SyntheticOrderStrategyBase(STRATEGY.Strategy):
    """ The base class for all strategies who would use synthetic orders. Should implement as much logic as possible
    as to make the creation of new strategies simple

          Main functions of the synthetic order strategy
            - Runs on all events for all products
            - synthetic order management
                - registration
                - modification
                - deletion
            - implements the config options reporting
            - implements the core bookkeeping and execution of synthetic selectors/orders

    """

    # the callback map which links specific synthetic order operations to callbacks implemented within the strategy
    _on_synthetic_order_callback_map = {
        COMMON.SyntheticOrderOperations.register: "on_synthetic_order_register",
        COMMON.SyntheticOrderOperations.modify: "on_synthetic_order_modify",
        COMMON.SyntheticOrderOperations.delete: "on_synthetic_order_delete"}

    # Override this variable to prohibit certain or all operations from the REST-API.
    allowed_synthetic_order_operations = [COMMON.SyntheticOrderOperations.register,
                                          COMMON.SyntheticOrderOperations.modify,
                                          COMMON.SyntheticOrderOperations.delete]

    required_synthetic_order_fields = ("product_id", "operation")

    def __init__(self, *args, **kwargs):
        super(SyntheticOrderStrategyBase, self).__init__(*args, **kwargs)

        self.log_silencer_act = collections.defaultdict(int)
        self.log_silencer_delivery_area = collections.defaultdict(int)
        self.log_silencer_traceback = collections.defaultdict(int)

        self._mifid_settings = {}
        self._default_trading_account = None
        # this is the list of all classes of selectors available to select from and use
        self._available_synthetic_order_types = self.get_available_synthetic_order_types()

        # this is the dictionary providing the instances linked to products {"product_id" : "selector_instance"}
        self._product_synthetic_order_mapping = collections.defaultdict(dict)
        self.load_existing_synthetic_orders_on_startup()

    def _get_so_reason_from_halt_states(self):
        reason = ""
        if self.autotrader.halted:
            reason = "Autotrader is halted with the reason: {}".format(self.autotrader.halt_reason)
        elif self.exchange.halted:
            reason = "Exchange is halted with the reason: {}".format(self.exchange.halt_reason)
        elif self.halted:
            reason = "Strategy is halted with the reason: {}".format(self.halt_reason)
        elif not self._pt_active:
            reason = "Strategy is deactivated"
        return reason

    def update_active_flag(self, username):
        """
        For Synthetic Order Strategy we need to additionally deactivate orders or call act immediately after
        autoTRADER/exchange/strategy resume
        Therefore, overriding the method.
        :param username: username changing strategy state
        :return: None
        """
        super(SyntheticOrderStrategyBase, self).update_active_flag(username)
        if not self.active:
            reason = self._get_so_reason_from_halt_states()
            if not self._pt_active:
                self._delete_all_synthetic_orders(reason=reason)
            else:
                self._deactivate_synthetic_orders(reason=reason)
        else:
            # calling act immediately after the aT/exchange/strategy resume so that the SO status is changed immediately
            self.act(timestamp=self.autotrader.current_timestamp)

    def iter_synthetic_orders(self):
        """Iterate over all synthetic orders, yielding tuples (product_id, synthetic order)"""
        for product_id in self._product_synthetic_order_mapping:
            for synth_order_id, synthetic_order in list(self._product_synthetic_order_mapping[product_id].items()):
                yield product_id, synthetic_order

    def _delete_all_synthetic_orders(self, reason=""):
        """
        Set all synthetic orders of this strategy to deleted and perform a deletion step.

        :param reason: The reason for the "deleting" state
        :type reason: str
        :rtype: None
        """
        self.debug_log("Deleting all synthetic orders")
        for product_id, synthetic_order in self.iter_synthetic_orders():
            synthetic_order.delete(reason)
            if synthetic_order.needs_database_update():
                PERSIST.MongoDBConnector().update_db_synthetic_order(
                    synthetic_order, product_id, self
                )
            try:
                product = self.exchange.products.get_by_id(product_id)
            except COMMON.ProductNotFound:
                self.debug_log("Product {} not found in '_delete_all_synthetic_orders', hard deleting "
                               "synthetic order {} immediately".format(product_id, synthetic_order.slot_name))
                self._hard_delete_so(synthetic_order, product_id)
            else:
                self._perform_so_deletion_step(product, synthetic_order)

    def _deactivate_synthetic_orders(self, reason=""):
        """
        Sets status of all synthetic orders to "passive"
        :param reason: reason for deactivating
        :type reason: str
        :return: None
        """
        for product_id, synthetic_order in self.iter_synthetic_orders():
            log.debug("Deactivating synthetic order: %s with reason: %s", synthetic_order.slot_name, reason)
            synthetic_order.deactivate(status_text=reason)
            # we need to update mongo here as strategy is inactive and won't do anything
            if synthetic_order.needs_database_update():
                PERSIST.MongoDBConnector().update_db_synthetic_order(synthetic_order, product_id, self)

    def on_strategy_configuration_update(self, strategy_json):
        super(SyntheticOrderStrategyBase, self).on_strategy_configuration_update(strategy_json)
        for mifid_field in MiFIDField.get_all():
            with_mifid_prepend = "mifid_" + mifid_field
            self._mifid_settings[mifid_field] = strategy_json.get(with_mifid_prepend, None)
        self._default_trading_account = strategy_json.get("trading_account")

    @property
    def product_synthetic_order_mapping(self):
        return self._product_synthetic_order_mapping

    # region: SYNTH ORDER HANDLING

    def on_synthetic_order(self, payload):
        """ This callback will be called whenever a new SyntheticOrder object is collected from MongoDB
        (strategies collection). The payload and response works in a similar fashion as the steering calls.
        This function will take care of the cascading and configuration logic. It will catch any foreseeable errors
        to forward them as a response.

        .. warning::

            This function is designed to be called from the REST-API. if you call it from custom strategy code,
            be aware of the following two things. 1) This will call act for all synthetic orders, so running this
            function in a loop is not advised. 2) if an error occurs, this returns the error message as string,
            so you should check the return value.
            For these reasons it is usually better to run on_synthetic_order_register, on_synthetic_order_modify or
            on_synthetic_order_delete directly

        There are 3 options: The synthetic order ...

        * is new -> you REGISTER it for running, on a specific product
        * already exists and should be DELETED -> you only mark it deleted (allowing it to remove its orders)
        * already exists and should be MODIFIED -> you modify the settings of the previously registered one

        .. note::

            In the base class, all synthetic order operations are allowed from the REST-API. If you subclass this,
            you can use cls.allowed_synthetic_order_operations to restrict the allowed actions e.g. to modifications.

        Example payload::

             {"operation": "register",
              "product_id": "10000302_2",
              "message_type": "synthetic_order",
              "synthetic_order_type": "Aggressor",
              "identifier": "selector_A",
              "configuration": {"broker_id": "20",
                                "slot_name": "buy",
                                "market_area": COMMON.Area.ttf,
                                "variableX": 10.}}

        :param payload: See example above:
        :type payload: dict
        :return: Returns the error response or None if successful
        :rtype: str | None
        """
        if not self.exchange.init_files_ready():
            return "The exchange is currently in the process of initialization. Please try again later."

        product_id = payload.get("product_id")
        product = None
        if product_id:
            try:
                product = self.exchange.products.get_by_id(product_id=product_id)
            except COMMON.ProductNotFound:
                self.exception_log("Could not find product with id: {} in exchange: {} for synthetic order payload {}"
                                   .format(product_id, self.exchange.internal_id, payload))
        self.debug_log("Strategy received a synthetic order payload: "
                       "{payload}".format(payload=payload), product=product)

        try:

            # each payload needs the product id and operation to be defined
            for required_field in self.required_synthetic_order_fields:
                if required_field not in payload:
                    raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                        field_name=required_field, section_name="base"
                    ))

            product_id = payload["product_id"]  # Each synthetic order runs on single product & area
            operation = payload["operation"]

            # operation must be a valid one
            if operation not in self._on_synthetic_order_callback_map:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.invalid_operation_specified.format(
                    given=operation, allowed_list=", ".join(list(self._on_synthetic_order_callback_map.keys()))
                ))

            # operation must be allowed within the strategy
            if operation not in self.allowed_synthetic_order_operations:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.operation_forbidden.format(
                    given=operation, allowed_list=", ".join(self.allowed_synthetic_order_operations)
                ))

            callback_function_name = self._on_synthetic_order_callback_map[operation]

            getattr(self, callback_function_name)(product_id=product_id, payload=payload)

        # If it is a known error the message will suffice as we already made it clear
        except (ERR.ConfigurationError, PKG_CONF.FieldValidationError) as err:
            self.exception_log(six.text_type(err), product=product)
            return six.text_type(err)
        except Exception as err:
            message = "Unexpected error occurred in configuration: {}({})".format(err.__class__.__name__, err)
            self.exception_log(message, product=product)
            return message

        else:
            self.debug_log("Successfully completed synthetic order operation: {operation};"
                           .format(operation=operation),
                           product
                           )
            try:
                return self.act(timestamp=self.autotrader.current_timestamp)
            except Exception as err:
                # We do not return the error message to the REST-API here, as the SO has been registered successfully
                # and it is unclear if the newly modified, or an old SO raised the error.
                # Errors during strategy callbacks are ignored and logged by autoTRADER like this as well
                self.exception_log("An exception occurred while running act after 'on_synthetic_order' update. "
                                   "Error: {}. [Happened after operation {} for synthetic order "
                                   "{}]".format(err, payload.get("operation"), payload.get("synthetic_order_type")))

    def on_synthetic_order_register(self, product_id, payload):
        """ This function takes care of synthetic order selector registrations, creating and linking the instance to the
        product.

        NOTE: A registration of an existing selector will not modify it but will rather fail.

        :param product_id: The id of the product to which the selector should be linked
        :type product_id: str
        :param payload: The payload for the registration
        :type payload: dict
        :return: Does not return anything
        """
        if not self._pt_active:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.inactive_strategy)

        for required_field in ["configuration", "identifier", "message_type"]:
            if required_field not in payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name=required_field,
                    section_name="payload"
                ))

        configuration = payload["configuration"]
        identifier = payload["identifier"]
        message_type = payload["message_type"]
        slot_name = configuration.get("slot_name")

        if not slot_name:
            slot_name = identifier
            configuration["slot_name"] = slot_name

        if message_type == COMMON.SyntheticMessageType.selector:

            if "synthetic_selector_type" not in payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name="synthetic_selector_type",
                    section_name="payload"
                ))

            synthetic_object_type = payload["synthetic_selector_type"]

        elif message_type == COMMON.SyntheticMessageType.order:

            if "synthetic_order_type" not in payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name="synthetic_order_type",
                    section_name="payload"
                ))

            synthetic_object_type = payload["synthetic_order_type"]

        else:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.unrecognized_message_type.format(
                original=message_type,
                recognized="; ".join([COMMON.SyntheticMessageType.order,
                                      COMMON.SyntheticMessageType.selector,
                                      ])
            ))

        # first check that its available for this strategy
        if synthetic_object_type not in self._available_synthetic_order_types:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.synth_order_type_not_available.format(
                given_order_type=synthetic_object_type,
                strategy_class=self.__class__.__name__,
                allowed_only=", ".join(list(self._available_synthetic_order_types.keys()))
            ))

        # check valid format of identifier
        if len(identifier) > 64:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.identifier_too_long)
        if not self.validate_identifier(identifier):
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.not_valid_identifier.format(
                identifier=identifier
            ))

        # avoid placing the same ones
        if identifier in self._product_synthetic_order_mapping[product_id]:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.synthetic_order_already_exists.format(
                identifier=identifier
            ))

        if slot_name != identifier:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.slot_name_is_different_to_identifier.format(
                slot_name=slot_name, identifier=identifier
            ))

        # get the class object
        synthetic_order_class = self._available_synthetic_order_types[synthetic_object_type]

        market_area = PKG_CONF.InstrumentIdType.validate_and_cast_to_mongo(configuration["market_area"])

        # in case of Trayport, the broker_id is needed to determine the tick_size from TrayportProperties
        tick_size = self._get_tick_size(broker_id=configuration.get("broker_id"),
                                        delivery_area_id=market_area,
                                        product_id=product_id)

        if message_type == COMMON.SyntheticMessageType.selector:
            if not issubclass(synthetic_order_class, SELBASE.SyntheticOrderSelectorBase):
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.message_type_needs_selector)

            if "synthetic_orders" not in payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name="synthetic_orders",
                    section_name="payload"
                ))

            synthetic_orders_conf_list = payload["synthetic_orders"]

            # make the instance
            synthetic_order_instance = synthetic_order_class(tick_size=tick_size,
                                                             identifier=identifier,
                                                             configuration=configuration,
                                                             synthetic_orders_configuration=synthetic_orders_conf_list)

        elif message_type == COMMON.SyntheticMessageType.order:
            # make the instance
            synthetic_order_instance = synthetic_order_class(tick_size=tick_size,
                                                             identifier=identifier,
                                                             configuration=configuration)
            if not self.active:
                # If autotrader/ exchange/ strategy is halted, then give this info as status_text.
                reason = self._get_so_reason_from_halt_states()
                synthetic_order_instance.deactivate(reason)
            synthetic_order_instance.needs_database_update()  # We will write to mongo anyway, so we reset this flag.
            PERSIST.MongoDBConnector().update_db_synthetic_order(
                synthetic_order_instance, product_id, self, synthetic_object_type=synthetic_object_type
            )

        else:
            raise RuntimeError("This should not happen!")

        self._product_synthetic_order_mapping[product_id][identifier] = synthetic_order_instance

    def on_synthetic_order_modify(self, product_id, payload):
        """ This function takes care of synthetic order selector modifications, putting the new payload to an
        existing selector to reconfigure it

        NOTE 1: A modify will not register a new selector if the one in the payload does not exist

        NOTE 2: Modifies can be incremental and only need to include the identifier and the changed values

        :param product_id: The id of the product from which the selector should be modified/reconfigured
        :type product_id: str
        :param payload: The payload for the registration
        :type payload: dict
        :return: Does not return anything
        """

        if "identifier" not in payload:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                field_name="identifier",
                section_name="payload"
            ))

        identifier = payload["identifier"]

        if identifier not in self._product_synthetic_order_mapping[product_id]:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.modify_a_non_existing_selector.format(
                identifier=identifier, product_id=product_id
            ))

        current_synth_order_instance = self._product_synthetic_order_mapping[product_id][identifier]

        if "configuration" in payload:
            configuration = payload["configuration"]

            if "slot_name" in configuration and current_synth_order_instance.slot_name != configuration["slot_name"]:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.slot_name_reconfig_forbidden.format(
                    initial=current_synth_order_instance.slot_name, provided=configuration["slot_name"]
                ))

            old_broker_id = current_synth_order_instance.broker_id

            # SPECIAL LOGIC: In the case the broker_id for the selector changed, the tick_size needs to be reconfigured
            new_broker_id = configuration.get("broker_id", current_synth_order_instance.broker_id)
            new_market_area = configuration.get("market_area", current_synth_order_instance.market_area)
            new_market_area = PKG_CONF.InstrumentIdType.validate_and_cast_to_mongo(new_market_area)

            localview = LV.LocalView(product=self.exchange.products.get_by_id(product_id),
                                     market_area=current_synth_order_instance.market_area,
                                     strategy_id=self.strategy_id)

            if (new_market_area != current_synth_order_instance.market_area
                    and localview.exposed_order_volume(current_synth_order_instance.slot_name)):
                raise ERR.ConfigurationError("Cannot change the market area of a synthetic order, "
                                             "while it still has exposed volume")
            if new_broker_id != old_broker_id or new_market_area != current_synth_order_instance.market_area:
                new_tick_size = self._get_tick_size(broker_id=new_broker_id, delivery_area_id=new_market_area,
                                                    product_id=product_id)
                self._product_synthetic_order_mapping[product_id][identifier].tick_size = new_tick_size

                # IMPORTANT: Special handling for synthetic selectors
                if isinstance(current_synth_order_instance, SELBASE.SyntheticOrderSelectorBase):
                    # cascade the tick size to all the synthetic orders too:
                    for synth_order in current_synth_order_instance.synthetic_orders.values():
                        synth_order.tick_size = new_tick_size

            current_synth_order_instance.configure(configuration)

        # IMPORTANT: Special handling for synthetic selectors
        if isinstance(current_synth_order_instance, SELBASE.SyntheticOrderSelectorBase) and (
                "synthetic_orders" in payload):
            current_synth_order_instance.configure_synthetic_orders(payload["synthetic_orders"])

        current_synth_order_instance.needs_database_update()  # As we'll write to the database anyway, reset this flag
        PERSIST.MongoDBConnector().update_db_synthetic_order(current_synth_order_instance, product_id, self)

    def on_synthetic_order_delete(self, product_id, payload):
        """ This function takes care of synthetic order selector deletions, marking a selector as deleted on the
        linked product.

        NOTE: Deletions alone will not remove the selector from the product, but will rather set them to deleted to
        first close their exposed order. And the deletion is then performed as part of bookkeeping in the callback
        custom_act_on_product

        :param product_id: The id of the product from which the selector should be marked as deleted
        :type product_id: str
        :param payload: The payload for the registration
        :type payload: dict
        :return: Does not return anything
        """

        for required_field in ["identifier"]:
            if required_field not in payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name=required_field,
                    section_name="payload"
                ))

        identifier = payload["identifier"]

        if identifier not in self._product_synthetic_order_mapping[product_id]:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.deleting_a_non_existing_selector.format(
                identifier=identifier
            ))

        synthetic_order = self._product_synthetic_order_mapping[product_id][identifier]
        synthetic_order.delete()
        synthetic_order.needs_database_update()  # As we will write to the database anyway, we reset this flag.
        PERSIST.MongoDBConnector().update_db_synthetic_order(
            synthetic_order, product_id, self, synthetic_object_type=payload.get("synthetic_order_type")
        )
        product = self.exchange.products.get_by_id(product_id)
        self._perform_so_deletion_step(product, synthetic_order)

    def _perform_so_deletion_step(self, product, synthetic_order, localview=None):
        """
        Perform one step in the deletion of the synthetic order: Remove the exposed order, or the synthetic order

        As long as a synthetic order still has exposed volume at the exchange, we remove only the resting order, but
        the SO stays (in status "deleting"). If there is no exposed volume, we can safely delete the synthetic order.

        :param product: The product where the synthetic order is registered
        :type product: APITR.Product
        :param synthetic_order: The deleted synthetic order. Note that this functipon assumes that the
                                deleted flag is set and does not re-check it.
        :type synthetic_order: autotrader_synthetic.synthetic_orders.synthetic_order_base.SyntheticOrderBase
        :param localview: The localview for this synthetic order's product and area.
        :type localview: LV.LocalView or None
        :return: A list with 1 element of type slot response
        :rtype: list[STRATEGY.SlotResponse]
        """
        if localview is None:
            localview = LV.LocalView(product=product,
                                     market_area=synthetic_order.market_area,
                                     strategy_id=self.strategy_id)
        if synthetic_order.exposed_order_volume(localview):
            self.debug_log("Synthetic Order {} is set to 'deleted', but still has exposed orders. "
                           "Removing orders.".format(synthetic_order.identifier), product)
            slot = synthetic_order.remove()  # place 0 slot
            return self.place_slots({}, product, self.autotrader.current_timestamp, synthetic_order.market_area, [slot])
        else:
            return self._hard_delete_so(synthetic_order, product.product_id)

    def _hard_delete_so(self, current_synthetic_order, product_id):
        self.debug_log(
            "Synthetic Order (Selector) {selector_id} on product {product_id} is set to 'deleted' and has no exposed "
            "volume. Hard deleting it. ".format(selector_id=current_synthetic_order.identifier, product_id=product_id))
        del self._product_synthetic_order_mapping[product_id][current_synthetic_order.identifier]
        PERSIST.MongoDBConnector().delete_db_synthetic_order(
            self.strategy_id, current_synthetic_order.identifier, product_id
        )
        return [STRATEGY.SlotResponse(
            succeeded=True, action=COMMON.SlotResponseAction.no_order, reason=COMMON.SlotResponseReason.ok
        )]

    def _get_tick_size(self, broker_id, delivery_area_id, product_id):
        """ This is a helper function for getting the tick_size. Its only needed because on Trayport the tick_size
        is defined for each broker-delivery_area-product dynamically.

        :param broker_id: The id of the broker used, can be None
        :type broker_id: str
        :param delivery_area_id: The new area (instrument id)
        :type delivery_area_id: str
        :param product_id: The id of the product used
        :type product_id: str
        :return: Returns the tick size to be used for the SyntheticOrder when placing slots
        :rtype: float
        """
        if self.exchange.internal_id == COMMON.Exchange.trayport:
            tick_sizes = STRATEGY.PositionSlot.get_trayport_tick_sizes(broker_id,
                                                                       self.exchange,
                                                                       product_id,
                                                                       delivery_area_id)
            if tick_sizes:
                return tick_sizes[1]  # we only need the price tick
            else:
                raise ERR.ConfigurationError(
                    ERR.ConfigurationErrorReason.invalid_broker_area_product_combination.format(
                        broker_id=broker_id, instrument_id=delivery_area_id, product_id=product_id
                    ))
        else:
            return self.exchange.tick_size

    def _delete_synthetic_orders_from_dead_products(self):
        """
        If a Product no longer exists in our memory AND we are initialized, then we can assume that this product will
        never come back and we should delete the Synthetic orders from it.

        Examples would be products from yesterday or last week on SPOT markets
        """
        if self.exchange.init_files_ready():
            products = self.exchange.products.get_all()
            dead_product_ids = set(self._product_synthetic_order_mapping) - set(p.product_id for p in products)
            for product_id in dead_product_ids:
                for synthetic_order_id, synthetic_order in list(
                        self._product_synthetic_order_mapping[product_id].items()):
                    self.debug_log(
                        "Deleting Synthetic order {}, because product {} no longer exists".format(synthetic_order_id,
                                                                                                  product_id))
                    self._hard_delete_so(synthetic_order, product_id)

    # endregion

    # region: CALLBACKS

    def custom_act(self, log_data, timestamp, products=None):
        additional_views = FV.ViewFactory(products=self.exchange.products, strategy_id=self.strategy_id)
        for view_name, instrument_ids in self.additional_views.items():
            additional_views.configure_view(view_name, instrument_ids)
        results = {}
        if products is None:
            self._delete_synthetic_orders_from_dead_products()
            products = self.exchange.products.get_all()
        try:
            for product in set(products):
                # filter for products for which we have a registered selector
                if self._product_synthetic_order_mapping.get(product.product_id, {}):
                    self.debug_log("Running '_call_synthetic_orders_for_product'", product)
                    results[product.product_id] = self._call_synthetic_orders_for_product(product, timestamp,
                                                                                          additional_views)
        except Exception:
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            raise
        return results

    def custom_on_order_book_update(self, orders, timestamp):
        products = set(o.product for o in orders)
        return self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        products = set(t.product for t in trades)
        return self.act(timestamp, products)

    def custom_on_public_trade_update(self, trades, timestamp):
        products = set(t.product for t in trades)
        return self.act(timestamp, products)

    def custom_on_products_update(self, products, timestamp):
        return self.act(timestamp, products)

    def custom_on_products_queue(self, products, timestamp):
        return self.act(timestamp, products)

    def custom_on_timer(self, timestamp):
        return self.act(timestamp)

    def _call_synthetic_orders_for_product(self, product, timestamp, additional_views):
        """ This function ensures that on every product run, all the synthetic orders (via selectors)
        that are registered for the product are being run.

        :param product: The product on which to run all synthetic orders
        :type product: autotrader_core.exchange_trading.Product
        :param timestamp: The timestamp of the callback
        :type timestamp: float
        :param additional_views: The ViewFactory that will be passed to the synthetic orders
        :param additional_views: FV.ViewFactory
        :return: A dict with synthetic order ID keys and a list of SlotResponse objects as value
        :rtype: dict[str, list[STRATEGY.SlotResponse]]
        """
        synthetic_orders = list(self._product_synthetic_order_mapping.get(product.product_id, {}).values())
        if not synthetic_orders:
            return
        results = {}
        for current_synthetic_order in synthetic_orders:
            if current_synthetic_order.market_area not in self.delivery_areas:
                self.log_silencer_delivery_area[current_synthetic_order.identifier] += 1
                current_synthetic_order.warn("SO's instrument id {} is not in the strategy's "
                                             "instrument ids ({})".format(current_synthetic_order.market_area,
                                                                          ", ".join(self.delivery_areas)))
                if current_synthetic_order.needs_database_update():
                    PERSIST.MongoDBConnector().update_db_synthetic_order(
                        current_synthetic_order, product.product_id, self
                    )
                if self.log_silencer_delivery_area[current_synthetic_order.identifier] % SILENCE_PERIOD_DEPREC_LOG == 1:
                    self.warn_log(
                        "[%s] Skipping SO:The synthetic order's instrument id [%s] "
                        "is not in the strategy's instrument ids [%s]. "
                        "Please adjust the instrument id of the strategy or the synthetic order. "
                        "[n: %d]" %
                        (
                            current_synthetic_order.get_default_info(),
                            current_synthetic_order.market_area,
                            self.delivery_areas,
                            self.log_silencer_delivery_area[current_synthetic_order.identifier]
                        ),
                        product
                    )
                continue
            self.debug_log("Creating LocalView object for market_area: {}".format(
                current_synthetic_order.market_area), product)

            localview = LV.LocalView(product=product,
                                     market_area=current_synthetic_order.market_area,
                                     strategy_id=self.strategy_id)

            self.debug_log(
                "Executing SyntheticOrder with the identifier: {synth_identifier}; of class: {synth_class}; "
                "on market_area: {market_area}".format(synth_identifier=current_synthetic_order.identifier,
                                                       synth_class=current_synthetic_order.__class__.__name__,
                                                       market_area=current_synthetic_order.market_area), product)

            results[current_synthetic_order.identifier] = self._execute_synthetic_order(
                product=product,
                localview=localview,
                additional_views=additional_views,
                timestamp=timestamp,
                current_synthetic_order=current_synthetic_order)

            if current_synthetic_order.needs_database_update():
                PERSIST.MongoDBConnector().update_db_synthetic_order(
                    current_synthetic_order, product.product_id, self
                )
        return results

    def _execute_synthetic_order(
            self,
            product,  # type: APITR.Product
            localview,  # type: LV.LocalView
            additional_views,  # type: FV.ViewFactory
            timestamp,  # type: float
            current_synthetic_order  # type: SYB.SyntheticOrderBase
    ):  # type: (...) -> list[STRATEGY.SlotResponse]
        """ This helper function contains the logic for managing selector validity periods and deletions of selectors

        :param product: The Product object used to place the slots
        :type product: autotrader_core.exchange_trading.Product
        :param localview: The LocalView object used as a wrapper around the product providing indicators
                            for use by synthetic orders
        :type localview: autotrader_synthetic.local_view.LocalView
        :param additional_views: The created ViewFactory object containing the additional views
        :type additional_views: autotrader_synthetic.factory_view.ViewFactory
        :param timestamp: The timestamp of the current run loop
        :type timestamp: float
        :param current_synthetic_order: The synthetic order object currently being executed.
        :type current_synthetic_order: SYB.SyntheticOrderBase
        :return: A list of SlotResponse objects, with the same length as slots
        :rtype: list[STRATEGY.SlotResponse]
        """
        if current_synthetic_order.deleted and not current_synthetic_order.exposed_order_volume(localview):
            # As hard-deleting SOs without exposed volume does not need exchange communication,
            # we can do it before all other checks.
            return self._hard_delete_so(current_synthetic_order, product.product_id)

        if self.exchange.market_state == COMMON.MarketState.hibernated:
            self.debug_log("Exchange {} is hibernated, not executing synthetic"
                           " order {}".format(self.exchange.internal_id, current_synthetic_order.identifier),
                           product=product)
            current_synthetic_order.deactivate(
                "{} is hibernated or autoTRADER is disconnected from it".format(self.exchange.internal_id))
            return [STRATEGY.SlotResponse(succeeded=False,
                                          action=COMMON.SlotResponseAction.ignore,
                                          reason=COMMON.SlotResponseReason.market_halt)]

        if not (self.valid_from <= product.delivery_start < self.valid_to):
            slot = current_synthetic_order.remove("Outside of Strategy's validity period")  # place 0 slot
            return self.place_slots({}, product, timestamp, current_synthetic_order.market_area, [slot])

        # if the from_ts changes it should also make sure to delete
        if timestamp < current_synthetic_order.from_ts:  # this is like a validity from then to when it should be active
            # In case from_ts has changed, we might have exposed volume. => remove the exposed order
            self.debug_log(
                "Selector {selector_id} is invalid for this time period, removing orders. Current timestamp:"
                "{curr_ts} < selector.from_ts: {from_ts}".format(
                    selector_id=current_synthetic_order.identifier,
                    curr_ts=timestamp,
                    from_ts=current_synthetic_order.from_ts),
                product)
            # place 0 slot
            slot = current_synthetic_order.remove(
                status_text="Synthetic Order {!r} is not yet valid".format(current_synthetic_order.identifier))
            return self.place_slots({}, product, timestamp, current_synthetic_order.market_area, [slot])

        # if the current timestamp is past the delivery_start of the product,
        # we want to delete the SO as the product is not tradeable anymore
        if timestamp >= product.delivery_start:
            self.debug_log("Current timestamp: {curr_ts} > product.delivery_start: {delivery_start}."
                           "Setting selector {selector_id} to deleted. ".format(
                               selector_id=current_synthetic_order.identifier,
                               curr_ts=timestamp,
                               delivery_start=product.delivery_start), product)
            current_synthetic_order.delete("Current timestamp is past the delivery start of the product")

        elif timestamp > current_synthetic_order.to_ts:
            self.debug_log("Selector {selector_id} validity has expired, setting to deleted. Current timestamp:"
                           "{curr_ts} < selector.to_ts: {to_ts}".format(selector_id=current_synthetic_order.identifier,
                                                                        curr_ts=timestamp,
                                                                        to_ts=current_synthetic_order.to_ts), product)
            current_synthetic_order.delete("Synthetic Order's validity has expired")

        elif product.state(current_synthetic_order.market_area) != COMMON.DeliveryAreaState.active:
            current_synthetic_order.warn(
                "Product {} is not open for trading on area {}".format(product.product_id,
                                                                       current_synthetic_order.market_area))
            return [STRATEGY.SlotResponse(succeeded=False,
                                          action=COMMON.SlotResponseAction.ignore,
                                          reason=COMMON.SlotResponseReason.inactive_area)]

        if current_synthetic_order.deleted:
            return self._perform_so_deletion_step(product, current_synthetic_order, localview)

        try:
            try:
                slot = current_synthetic_order.act(localview, additional_views, timestamp)
            except TypeError:
                so_class = current_synthetic_order.__class__.__name__
                if six.PY2:
                    if self.log_silencer_act[so_class] % SILENCE_PERIOD_DEPREC_LOG == 0:
                        self.exception_log(
                            "Original TypeError caught before trying to call act with the old signature:")
                        self.warn_log(
                            "The strategy's synthetic order class (%s) is deprecated. Please use the following "
                            "signature for act() function: def act(localview, additional_views, timestamp)" % so_class
                        )
                        self.log_silencer_act[so_class] = 1
                    slot = current_synthetic_order.act(localview, timestamp)
                    self.log_silencer_act[so_class] += 1
                elif six.PY3:
                    # For Python3 we deprecated the old signature of the so.act() function
                    raise ERR.AutotraderSyntheticException(
                        "The strategy's synthetic order class ({}) is deprecated. Please use the following signature "
                        "for act() function: def act(localview, additional_views, timestamp)".format(so_class)
                    )
        except Exception as err:
            if self.log_silencer_traceback[str(err)] % SILENCE_PERIOD_DEPREC_LOG == 0:
                log.exception("Exception in synthetic order 'act' caught. Faulting SO:")
                self.log_silencer_traceback[str(err)] = 1
            else:
                log.error("Exception in synthetic order 'act' caught: %s (traceback of repeated exception silenced)."
                          "Faulting SO.", err)
                self.log_silencer_traceback[str(err)] += 1
            # We do not use .remove here, because we don't want to have unneeded SO status database updates.
            slot = current_synthetic_order.create_slot(COMMON.Direction.buy, quantity=0)
            self._populate_mifid_fields(slot)
            current_synthetic_order.fault("Exception raised in act: {}: {}".format(type(err).__name__, err))
            return self.place_slots({}, product, timestamp, current_synthetic_order.market_area, [slot])
        if slot:
            self._populate_mifid_fields(slot)
            slot_responses = self.place_slots({}, product, timestamp, current_synthetic_order.market_area, [slot])
            if slot.quantity is None or abs(slot.quantity) < COMMON.MIN_ORDER_QTY:
                if (slot_responses[0].action == COMMON.SlotResponseAction.no_order
                        and current_synthetic_order.status != COMMON.SyntheticOrderStates.passive):
                    # If the strategy does not want to place and there is no order on the market,
                    # ensure we are passive (if we are already passive due to .remove, do not overwrite the status).
                    current_synthetic_order.set_status(COMMON.SyntheticOrderStates.passive, "")
                return slot_responses

            used_locked_product_status = False
            if slot_responses[0].action in (COMMON.SlotResponseAction.create, COMMON.SlotResponseAction.modify):
                used_locked_product_status = self._fault_if_product_is_locked(current_synthetic_order,
                                                                              product, timestamp)
            if not used_locked_product_status:
                self._update_so_state_based_on_slotresponse(current_synthetic_order, slot_responses[0])
            return slot_responses

        return [STRATEGY.SlotResponse(succeeded=True,
                                      action=COMMON.SlotResponseAction.no_order,
                                      reason=COMMON.SlotResponseReason.ok)]

    def _populate_mifid_fields(self, slot):
        """
        Populate the MiFID fields and the trading account of the slot (if None) with the strategy's values.

        This allows the Synthetic Order to override the mifid fields of the strategy, but if it does not have mifid
        fields configured, we fall back to the strategy's values.

        :param slot: The slot to populate
        :type slot: STRATEGY.PositionSlot
        """
        for mifid_field in MiFIDField.get_all():
            if getattr(slot, mifid_field) is None:
                setattr(slot, mifid_field, self._mifid_settings.get(mifid_field))
        if slot.trading_account is None:
            slot.trading_account = self._default_trading_account

    def _fault_if_product_is_locked(self, synthetic_order, product, current_timestamp):
        """
        If the product is locked since more than 15 seconds, change the SO status to faulted.

        :type product: APITR.Product
        :type current_timestamp: float or int
        :return: True if the status was updated, False otherwise
        :rtype: bool
        """
        # We use a 15 seconds timeout here, to avoid reporting faults in situations of only slightly higher queue lag.
        CUTOFF = 15
        if product.order_lock.contains_since_longer_time(None, current_timestamp, CUTOFF):
            synthetic_order.fault("autoTRADER is waiting for an order execution on this product "
                                  "since more than {} seconds".format(CUTOFF))
            return True
        elif product.trade_lock.contains_since_longer_time(None, current_timestamp, CUTOFF):
            synthetic_order.fault("autoTRADER is waiting for a trade confirmation on this product "
                                  "since more than {} seconds".format(CUTOFF))
            return True
        elif product.tag_lock.contains_since_longer_time(None, current_timestamp, CUTOFF):
            synthetic_order.fault("autoTRADER is waiting for a trade meta-data update on this product "
                                  "since more than {} seconds".format(CUTOFF))
            return True
        return False

    def _update_so_state_based_on_slotresponse(self, synthetic_order, slot_response):
        """
        Update the state of the synthetic order based on the slot_response

        This function sets the synthetic order's state to active/ creating, if a slot was successfully placed,
        and to warning/ faulted, if slot placement failed. It does not set the synthetic order state to passive,
        as this should have happened before placing the slot when calling SyntheticOrder.remove() to get a zero slot
        (allowing the SyntheticOrder code to set the state_text for passive SOs)

        :param synthetic_order: The SyntheticOrder, which placed the non-zero slot
        :type synthetic_order: autotrader_synthetic.synthetic_orders.synthetic_order_base.SyntheticOrderBase
        :param slot_response: The slot response returned when placing the slot.
        :type slot_response: STRATEGY.SlotResponse
        """
        ignore_reasons = [COMMON.SlotResponseReason.unconfirmed_order,
                          COMMON.SlotResponseReason.duplicate_orders,
                          COMMON.SlotResponseReason.tp_broker_unchangeable,
                          COMMON.SlotResponseReason.direction_changed,
                          COMMON.SlotResponseReason.mifid_fields_changed,
                          COMMON.SlotResponseReason.exec_restriction_changed,
                          ]
        fault_reasons = [COMMON.SlotResponseReason.missing_direction,
                         COMMON.SlotResponseReason.nonfinite_quantity,
                         COMMON.SlotResponseReason.nonfinite_price,
                         COMMON.SlotResponseReason.iceberg_large_clip,
                         COMMON.SlotResponseReason.iceberg_invalid_clip_qty,
                         COMMON.SlotResponseReason.tp_broker_unset,
                         COMMON.SlotResponseReason.tp_broker_must_be_string,
                         COMMON.SlotResponseReason.tp_price_tick_size_violation,
                         COMMON.SlotResponseReason.tp_quantity_tick_size_violation,
                         COMMON.SlotResponseReason.derivative_indicator_not_bool,
                         COMMON.SlotResponseReason.liquidity_provision_not_bool,
                         COMMON.SlotResponseReason.dea_not_bool,
                         COMMON.SlotResponseReason.decision_maker_not_string,
                         COMMON.SlotResponseReason.execution_maker_not_string,
                         COMMON.SlotResponseReason.dea_client_id_not_string,
                         COMMON.SlotResponseReason.wrong_trading_capacity,
                         COMMON.SlotResponseReason.wrong_exec_restriction,
                         COMMON.SlotResponseReason.duplicate_name,
                         ]
        warn_reasons = [COMMON.SlotResponseReason.limit_sale_price,
                        COMMON.SlotResponseReason.limit_buy_price,
                        COMMON.SlotResponseReason.tp_invalid_broker_area_combination,
                        COMMON.SlotResponseReason.tp_min_quantity_violation,
                        COMMON.SlotResponseReason.hibernated
                        ]
        if slot_response.succeeded:
            if (slot_response.action == COMMON.SlotResponseAction.create
                    and synthetic_order.status == COMMON.SyntheticOrderStates.passive):
                synthetic_order.set_status(COMMON.SyntheticOrderStates.inserting, "")
            elif slot_response.action == COMMON.SlotResponseAction.ignore:
                if slot_response.reason == COMMON.SlotResponseReason.unchanged:
                    synthetic_order.set_status(COMMON.SyntheticOrderStates.active, "")
                elif slot_response.reason.startswith(COMMON.SlotResponseReason.placement_too_deep_on_own_side):
                    reason = "not modifying price. %s" % (COMMON.SlotResponseReason.placement_too_deep_on_own_side,)
                    synthetic_order.set_status(COMMON.SyntheticOrderStates.active, reason)
        elif (slot_response.reason in fault_reasons
              or slot_response.reason.endswith(COMMON.SlotResponseReason.no_matching_order[3:])):
            synthetic_order.fault(slot_response.reason)
        elif (slot_response.reason in warn_reasons
              or slot_response.reason.split()[0] in ["maximum_purchase_volume", "maximum_sales_volume",
                                                     "maximum_purchase_price", "minimum_sales_price"]):
            synthetic_order.warn(slot_response.reason)
        elif slot_response.reason not in ignore_reasons:
            log.warning("Slot response reason {!r} is not assigned to a status, "
                        "using 'faulted'".format(slot_response.reason))
            synthetic_order.fault(slot_response.reason)

    # endregion

    # region: CONFIG REPORTING

    @classmethod
    def get_available_synthetic_order_types(cls):
        """
        This method links the selectors to the strategy and can be subclassed to enable other or custom selectors.

        WARNING: This must be a class method, otherwise the SyntheticOrderTypes will not be available
                 via the REST and push API.

        :returns: A dictionary, mapping identifiers to selector instances
        :rtype dict:
        """
        return {}

    # endregion

    def load_existing_synthetic_orders_on_startup(self):
        """On startup this function reloads existing synthetic orders from MongoDB and stores them in the
        _product_synthetic_order_mapping container
        Note: The return value of load_db_synthetic_order() is None in test environment due to function_guard() which is
        non-iterable, so correcting this should be a good dev improvement idea"""
        synthetic_order_list = PERSIST.MongoDBConnector().load_db_synthetic_order(self.strategy_id) or []
        for synthetic_order in synthetic_order_list:
            log.debug("Loading SO from DB: %s", synthetic_order)
            product_id = str(synthetic_order.get("sequence_item_id"))
            identifier = str(synthetic_order.get("synthetic_order_id"))
            configuration = synthetic_order.get("configuration", {})
            slot_name = configuration.get("slot_name")
            try:
                synthetic_order_class = self._available_synthetic_order_types[synthetic_order.get(
                    "synthetic_order_type")]
                # Filter for non-read-only fields only when recreating SO objects
                non_read_only_configuration = {config_field_name: field_value for config_field_name, field_value in
                                               configuration.items()
                                               if not getattr(getattr(synthetic_order_class, config_field_name, None),
                                                              "read_only", False)}
                synthetic_order_instance = synthetic_order_class(tick_size=synthetic_order.get("tick_size"),
                                                                 identifier=identifier,
                                                                 configuration=non_read_only_configuration)
                self._product_synthetic_order_mapping[str(synthetic_order.get("sequence_item_id"))][
                    str(synthetic_order.get("synthetic_order_id"))] = synthetic_order_instance
            except Exception:
                log.exception("Could not load synthetic order from database. "
                              "Synthetic Order Document: {}".format(synthetic_order))
                log.warning("Deleting the synthetic order from MongoDB")
                PERSIST.MongoDBConnector().delete_db_synthetic_order(
                    self.strategy_id, identifier, product_id
                )
            else:
                # Delete synthetic order if it is in the state "in deletion" so later it will be removed from MongoDB
                #  by the _execute_synthetic_order() function
                if synthetic_order.get("status") == COMMON.SyntheticOrderStates.deleting:
                    self._product_synthetic_order_mapping[product_id][identifier].delete()
                # Reset the need database update flag. The SO comes from mongoDB, it does not have to be written again
                synthetic_order_instance.needs_database_update()
                # Delete synthetic order if slot_name is different to identifier of the synthetic order.
                # It will be removed from MongoDB by _execute_synthetic_order() function
                if slot_name != identifier:
                    self.warn_log("Slot name: {}; is different to identifier: {}. The synthetic order will be deleted."
                                  .format(slot_name, identifier))
                    self._product_synthetic_order_mapping[product_id][identifier].delete()

    @staticmethod
    def validate_identifier(identifier):
        return bool(re.match(r"^[a-zA-Z0-9_]+$", identifier)) and not identifier.endswith("\n")

    def custom_on_error(self, errors, timestamp):
        super(SyntheticOrderStrategyBase, self).custom_on_error(errors, timestamp)
        # as it is currently not allowed by Translator
        # we assume that there will be no more than one error in the response
        error = errors[0]
        if "error_msg" in error:
            status_text = "Received error response from the Venue. Message: {msg!r}, Reason {reason!r}".format(
                msg=error.get("error_msg", ""), reason=error.get("error_message", ""))
        else:
            status_text = "Received error response from the exchange. Message: {msg!r}, Error Code: {code!r}".format(
                msg=error.get("error_message", ""), code=error.get("error_code", ""))

        error_info_list = []

        # we have to try to handle the message with the formats for both exchanges (if 2 are present)
        # since we can't know which one sent the error response
        for exchange in self.exchanges:
            error_info_list = self._extract_error_info_for_exchange(exchange.internal_id, error)
            if error_info_list:
                break

        # the error response message does not fit any of the know formats,
        # thus we can't extract sufficient information to handle it
        if not error_info_list:
            self.debug_log("Skipping, as unable to extract product_id, so_instance_name and portfolio_key from the"
                           "following error response: {err}".format(err=error))
            return

        for error_info in error_info_list:
            product_id = error_info[0]
            so_instance_name = error_info[1]
            portfolio_key = error_info[2]
            # we skip errors that do not belong to current strategy
            if portfolio_key != self.strategy_id:
                self.debug_log("Received error response for another strategy, skipping")
                return

            try:
                synthetic_order = self.product_synthetic_order_mapping[product_id][so_instance_name]
            except KeyError:
                self.debug_log("Won't handle error response. Synthetic Order {} not found".format(so_instance_name))
                return
            if synthetic_order.status != COMMON.SyntheticOrderStates.deleting:
                log.debug("Faulting SyntheticOrder: %s with reason: %s", so_instance_name, status_text)
                synthetic_order.fault(status_text)
                # The resting order should be removed in this case (the direction is disregarded when removing orders)
                slot = synthetic_order.create_slot(COMMON.Direction.buy, quantity=0)
                self.place_slots({}, self.exchange.products.get_by_id(product_id), timestamp,
                                 synthetic_order.market_area, [slot])
                if synthetic_order.needs_database_update():
                    PERSIST.MongoDBConnector().update_db_synthetic_order(synthetic_order, product_id, self)

    def _extract_error_info_for_exchange(self, exchange_id, error):
        """
        Call the corresponding error info extraction function, based on the provided exchange_id.

        :param exchange_id: The id if of the exchange, for which we should try to extract
        the relevant error handling info.
        :type exchange_id: str
        :return: tuple_list, containing all the (product_id, so_instance_name, portfolio_key) tuples,
        which are needed to handle the error response. The list is empty
        if no matching function is found for the exchange_id or the matching function could not
        extract sufficient information.
        :rtype: list
        """
        if exchange_id == COMMON.Exchange.trayport:
            return self._extract_trayport_error_info(error)
        elif exchange_id == COMMON.Exchange.nordpool:
            return self._extract_nordpool_error_info(error)
        elif exchange_id == COMMON.Exchange.epex:
            return self._extract_epex_error_info(error)
        return []

    def _extract_trayport_error_info(self, error):
        """
        Extract the product_id, so_instance_name, portfolio_key from the error response message, if the message
        format matches the format, which Trayport uses. This function returns a list of tuples, to be consistent
        with the one for NordPool, where multiple errors might be present.

        :param error: The error message, sent by the exchange.
        :type error: dict
        :return: tuple_list, containing all the (product_id, so_instance_name, portfolio_key) tuples,
        which are needed to handle the error response
        :rtype: list
        """
        order = error["order"] if "order" in error else error.get("tradeorder")
        if not order:
            return []
        # there should not be more than one order
        order = order[0]

        order_tags = ALU.parse_order_tags(order["txt"])
        portfolio_key = order_tags.get("portfolio_key")
        product_id = None
        so_instance_name = order_tags.get("strategy_slot")  # so identifier should be the same as the strategy_slot

        # for orders, we should have `inst_specifier` in the error response
        if "inst_specifier" in order:
            inst_spec = order["inst_specifier"][0]
            if "first_sequence_id" in inst_spec and "first_item_id" in inst_spec:
                product_id = "{}_{}".format(inst_spec["first_sequence_id"], inst_spec["first_item_id"])
        else:
            product_id = order_tags.get("product_id")  # for tradeorders, we have `product_id` in the tags

        if not product_id or not so_instance_name or not portfolio_key:
            return []
        return [(product_id, so_instance_name, portfolio_key)]

    def _extract_epex_error_info(self, error):
        """
        Extract the product_id, so_instance_name, portfolio_key from the error response message, if the message
        format matches the format, which EPEX uses. This function returns a list of tuples, to be consistent
        with the one for NordPool, where multiple errors might be present.

        :param error: The error message, sent by the exchange.
        :type error: dict
        :return: tuple_list, containing all the (product_id, so_instance_name, portfolio_key) tuples,
        which are needed to handle the error response
        :rtype: list
        """
        product_id = error.get("product_id")
        so_instance_name = error.get("strategy_slot")
        portfolio_key = error.get("portfolio_key")
        if not product_id or not so_instance_name or not portfolio_key:
            return []  # invalid message for epex handling
        return [(product_id, so_instance_name, portfolio_key)]

    def _extract_nordpool_error_info(self, error):
        """
        Extract the product_id, so_instance_name, portfolio_key from the error response message, if the message
        format matches the format, which NordPool uses.

        :param error: The error message, sent by the exchange.
        :type error: dict
        :return: tuple_list, containing all the (product_id, so_instance_name, portfolio_key) tuples,
        which are needed to handle the error response
        :rtype: list
        """
        order_list = error.get("var_list")
        if not order_list:
            return []
        if not isinstance(order_list, list):
            order_list = [order_list]

        tuple_list = list()
        for order in order_list:
            if not order:
                continue

            order_tags = ALU.parse_order_tags(order.get("txt"))
            portfolio_key = order_tags.get("portfolio_key")
            so_instance_name = order_tags.get("strategy_slot")  # so identifier should be the same as to strategy_slot
            product_id = order.get("product_id")
            if product_id and portfolio_key and so_instance_name:
                tuple_list.append((product_id, so_instance_name, portfolio_key))
        return tuple_list

    def on_internal_order_reject(self, rejected_order_infos, timestamp):
        """
        Update thje synthetic order status based on the reject reason in internal order reject messages.

        Should not be overridden by custom strategies.
        :param rejected_order_infos: A list of dicts containing the order internal id
                                     and the reason why the modification was rejected
        :type rejected_order_infos: list[dict]
        :param timestamp: The parent processe's timestamp at the time it rejected the modification.
                          Note that this is not time.time, but rather the timestamp of the message
                          which caused the rejection.
        :type timestamp: int or float
        """
        for rejection_info in rejected_order_infos:
            reason = rejection_info["reason"]
            if not reason:
                continue
            so_instance_name = rejection_info["tags"].get("strategy_slot")
            product_id = rejection_info["product_id"]
            synthetic_order = self.product_synthetic_order_mapping[product_id][so_instance_name]

            if reason.startswith(COMMON.RejectReason.price_moved_by_internal_market):
                synthetic_order.set_status(COMMON.SyntheticOrderStates.active, reason)

            if synthetic_order.needs_database_update():
                PERSIST.MongoDBConnector().update_db_synthetic_order(synthetic_order, product_id, self)


if __name__ == "__main__":
    raise RuntimeError("This module should ne be directly executed")  # pragma: no cover
