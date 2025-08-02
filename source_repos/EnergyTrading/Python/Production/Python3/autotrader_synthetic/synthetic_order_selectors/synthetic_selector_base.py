""" This module contains the implementation of the synthetic selector base """
from __future__ import absolute_import
import six
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

import autotrader_synthetic.errors as ERR
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYNORDBASE

log = FLOG.getLogger("autotrader_synthetic.synthetic_order_selector_base")


class SyntheticOrderSelectorBase(SYNORDBASE.SyntheticOrderBase):
    """This is the main switching behavior implementing object but this is only a parent class which should be
    subclassed for different switching behaviors

    .. deprecated:: ever since

        This is not suitable for production use, as persistence of selectors is not implemented.
        Additionally, Selectors are not tested and experimental.

    A selector is essentially a collection of preconfigured synthetic orders, and some logic to switch between them

    The base class pre-implements the following behaviors:
        - self-configuration when receiving a valid configuration payload
            - configuration nesting logic
            - configuration cascading logic
        - reporting of configuration options

    """

    # any config option which will be cascaded down to all the Synthetic orders
    # immutable by childs, this is a static class variable,
    # each instance would refer to the same and could modify it and impact all other instance if this is mutable
    cascaded_configurations = ("broker_id", "market_area", "slot_name")

    # any config that is not used by the selector can be excluded here
    excluded_configurations = ()

    # It has one slot_name, so switching between SyntheticOrders is easy
    def __init__(self, tick_size, identifier, configuration, synthetic_orders_configuration):
        """

        :param tick_size: Tick size is a dynamic property in case of Trayport and is
                            therefore not part of the configuration
        :type tick_size: float
        :param configuration: The configuration payload used to initially configure the SyntheticOrder
                                see .configuration() docstring for more information
        :type configuration: dict
        """
        # these are the available "classes" of synthetic orders
        self._available_synth_ord = self.get_available_synthetic_orders()

        # these are the instances of the synth orders
        self._synthetic_orders = dict()

        # should use the same logic then the SyntheticOrder parent class
        super(SyntheticOrderSelectorBase, self).__init__(tick_size, identifier, configuration)

        self.configure_synthetic_orders(synthetic_orders_configuration)

    @property
    def synthetic_orders(self):
        """Property to make synthetic orders public but making them readonly to add them with proper procedures"""
        return self._synthetic_orders

    def delete(self, status_text=None):
        """
        Deletes the Synthetic Orders for this Selector and the Selector itself, and passes down
        the provided status text for e.g. logging within the Synthetic Order delete function.

        :param status_text: Status text to be passed down to the Synthetic Order deletion function to set the
        status while order is being deleted and to log it.
        :type status_text: str
        :return: None
        """
        # we must cascade deletions as well
        for synth_ord in self.synthetic_orders.values():
            synth_ord.delete(status_text)

        super(SyntheticOrderSelectorBase, self).delete(status_text)

    def act(self, localview, additional_views, timestamp):
        """ This is the main behavioral function which needs to be subclassed and implement the switching behavior"""
        raise NotImplementedError  # pragma: no cover

    def configure(self, incoming_configuration_dict):
        """ The function that takes care of configuring a SyntheticOrder Selector,
        with all the nesting and cascading logic

        .. note::
            Besides the identifiers all the configuration is considered in an incremental manner,
            so it can only specify the changed value and does not need to repeat the others

        .. note::
            Configuration and synthetic orders are optional depending which one is desired to change

        Example configuration dict (see get_config_options below for more details):

            {"configuration": {"market_area": COMMON.Area.ttf,
                               "slot_name": "shared_slot_name",
                               "broker_id": "20",
                               "from_ts": 1000.,
                               "to_ts": 5000.},
             "synthetic_orders": [{"synthetic_order_type": "ExampleSynthOrder",
                                   "identifier": "first_order",
                                   "configuration": {"example_value": 1}}]}

        :param incoming_configuration_dict: The configuration payload (see above example)
        :type incoming_configuration_dict: dict
        :return: None
        """

        # we know at this point the configuration will exist so no error checking needed
        filtered_incoming_own_config = {key: value for key, value in incoming_configuration_dict.items()
                                        if key not in self.excluded_configurations}
        super(SyntheticOrderSelectorBase, self).configure(filtered_incoming_own_config)

        # cascade the reconfig into the synthetic orders
        if incoming_configuration_dict and any(key in self.cascaded_configurations
                                               for key in incoming_configuration_dict.keys()):
            for current_synth_order in self._synthetic_orders.values():

                # this will ensure to just cascade what is needed
                synth_order_config = self.get_cascaded_config(dict())
                current_synth_order.configure(synth_order_config)

    def configure_synthetic_orders(self, synth_orders_config):
        for idx, synth_order_payload in enumerate(synth_orders_config):

            if "identifier" not in synth_order_payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name="identifier",
                    section_name="synthetic_orders[{}]".format(idx)
                ))

            current_synth_order_identifier = synth_order_payload["identifier"]

            if "configuration" not in synth_order_payload:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                    field_name="configuration",
                    section_name="synthetic_orders[{}]".format(idx)
                ))

            configuration = synth_order_payload["configuration"]
            configuration = self.get_cascaded_config(configuration)

            # try to get it
            synthetic_order = self._synthetic_orders.get(current_synth_order_identifier)

            # initial configuration
            if not synthetic_order:

                if "synthetic_order_type" not in synth_order_payload:
                    raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.missing_configuration_field.format(
                        field_name="synthetic_order_type",
                        section_name="synthetic_orders[{}]".format(idx)
                    ))

                synthetic_order_type = synth_order_payload["synthetic_order_type"]

                if synthetic_order_type not in self._available_synth_ord:
                    raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.order_type_not_available.format(
                        given_order_type=synthetic_order_type,
                        selector_class=self.__class__.__name__,
                        allowed_only=", ".join(list(self._available_synth_ord.keys()))
                    ))

                log.debug("Creating a new synthetic order of type: {ord_type}; with identifier: {ord_id}"
                          "on selector of type: {sel_type} "
                          "with selector identifier: {sel_id}".format(ord_type=synthetic_order_type,
                                                                      ord_id=current_synth_order_identifier,
                                                                      sel_type=self.__class__.__name__,
                                                                      sel_id=self.identifier))

                # get the class
                order_class = self._available_synth_ord[synthetic_order_type]

                # create the instance
                synthetic_order = order_class(tick_size=self.tick_size,
                                              identifier=current_synth_order_identifier,
                                              configuration=configuration)

                self._synthetic_orders[current_synth_order_identifier] = synthetic_order

            # subsequent configurations
            else:
                log.debug("Reconfiguring an existing synthetic order of type: {ord_type}; "
                          "with identifier: {ord_id} on selector of type: {sel_type} "
                          "with selector identifier: {sel_id}".format(ord_type=synthetic_order.__class__.__name__,
                                                                      ord_id=current_synth_order_identifier,
                                                                      sel_type=self.__class__.__name__,
                                                                      sel_id=self.identifier))
                synthetic_order.configure(configuration)

    def get_cascaded_config(self, incoming_order_configuration):
        """ Helper function to cascade the configurations,
        which are shared from the selector to all its synthetic orders

        :param incoming_order_configuration: The configuration for the specific SyntheticOrder,
                                     will be overwritten (or filled) with cascaded configuration values
        :type incoming_order_configuration: dict
        :return: Returns the final configuration for the order, with the configurations correctly cascaded
        :rtype: dict
        """

        # Removes any previous configurations, and uses the ones from the selector
        for key in incoming_order_configuration:
            if key in self.cascaded_configurations:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.config_will_cascade.format(
                    config_key=key, cascaded_list=self.cascaded_configurations
                ))

        cascaded_configurations = {key: getattr(self, key)  # this will get the configurations of the selector
                                   for key in self.cascaded_configurations}
        cascaded_config = incoming_order_configuration.copy()
        cascaded_config.update(cascaded_configurations)
        return cascaded_config

    # region: CONFIG REPORTING

    @classmethod
    def get_available_synthetic_orders(cls):
        """ This function needs to be subclassed whenever making a custom selector as it will
        define which synthetic orders it accepts"""
        raise NotImplementedError  # pragma: no cover

    @classmethod
    def get_own_config_options(cls):
        """ Some options are only allowed in the deeper synth orders """
        conf_info_dict = super(SyntheticOrderSelectorBase, cls).get_own_config_options()
        return {conf_name: conf_info
                for conf_name, conf_info in conf_info_dict.items()
                if conf_name not in cls.excluded_configurations}

    @classmethod
    def get_config_options(cls):
        """ This function returns the config options available on the selector class

        Schema:
           SyntheticOrderSelector
                  |
                  |--- "configuration" -> Own Configuration at selector level
                  |          |--- conf_attr1:
                  |          |      |--- the config description of each config descriptor attribute
                  |          |--- conf_attr2:
                  |            ....
                  |--- "synthetic_orders" -> A list of Synthetic Orders available for this selector
                            |--- SyntheticOrderX -> A synthetic order type (class)
                            |         |--- conf_attr1:
                            |         |        |--- the config description of each config descriptor attribute
                            |         |--- conf_attr2:
                            |            ....
                            |--- SyntheticOrderY
                                    .....

        Example return for a SyntheticOrderSelector:
            {'configuration': {'broker_id': {'config_type': 'basestring',
                                     'default': 'None',
                                     'description': 'Broker ID for the Synthetic Order',
                                     'name': 'broker_id',
                                     'required': 'False'},
                               'from_ts': {'config_type': 'float',
                                           'default': '0.0',
                                           'description': 'Slot validity timestamp from',
                                           'name': 'from_ts',
                                           'required': 'False'},

                               'market_area': {'config_type': 'basestring',
                                               'default': 'None',
                                               'description': 'The market area id for this particular synthetic order,
                                                                this will be set by the strategy automatically',
                                               'name': 'market_area',
                                               'required': 'False'},
                               'slot_name': {'config_type': 'basestring',
                                             'default': 'None',
                                             'description': 'Used for identifying the slot placed
                                                              by this synthetic order',
                                             'name': 'slot_name',
                                             'required': 'True'},
                               'to_ts': {'config_type': 'float',
                                         'default': 'inf',
                                         'description': 'Slot validity timestamp to',
                                         'name': 'to_ts',
                                         'required': 'False'}},

             'synthetic_orders': {'ExampleSynthOrder':
                                 {'example_value': {'config_type': 'int',
                                                                    'default': 'None',
                                                                    'description': 'example value can be anything',
                                                                    'name': 'example_value',
                                                                    'required': 'False'}},
                                  'ExampleSynthOrderTwo':
                                  {'test_value_two': {'config_type': 'int',
                                                      'default': 'None',
                                                      'description': 'This will be used for testing',
                                                      'name': 'test_value_two',
                                                      'required': 'False'}}}}

        :return: Returns a dict of explained configuration options and available synthetic orders
        :rtype: dict
        """
        config_options_dict = dict()
        config_options_dict["configuration"] = cls.get_own_config_options()
        config_options_dict["synthetic_orders"] = dict()
        for available_synth_identifier, available_synth_order_class in cls.get_available_synthetic_orders().items():
            conf_info_dict = available_synth_order_class.get_config_options()

            # any configuration that will be shared across the selector
            filtered_conf_info = {conf_name: conf_info
                                  for conf_name, conf_info in conf_info_dict.items()
                                  if conf_name not in cls.cascaded_configurations}
            config_options_dict["synthetic_orders"][available_synth_identifier] = filtered_conf_info

        return config_options_dict

    # endregion


if __name__ == "__main__":
    raise RuntimeError("This module should not be directly executed")  # pragma: no cover
