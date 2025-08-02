""" This module defines custom error classes and predefined fail reasons
to make the error messages clearer and better organized
"""

# region: EXCEPTION CLASSES


class AutotraderSyntheticException(Exception):
    """ The base class for all exceptions within autotrader_synthetic, should be used to emit any known errors,
     so that they can be generally caught and handled appropriately """


class ConfigurationError(AutotraderSyntheticException):
    """ Raised when there is a known configuration error within the synthetic order configuration,
    providing valuable feedback on what went wrong. These arise when the PAYLOAD is incorrect """


class DescriptorError(AutotraderSyntheticException):
    """ These errors are raised when a descriptor within the synthetic orders is defined incorrectly """


class ChangeStatusError(Exception):
    """
    Error raised when checking status of a synthetic order
    """
    pass

# endregion

# region: ERROR REASON COLLECTIONS


class DescriptorErrorReason(object):
    """ This class contains all the common errors that can happen when defining a descriptor on a synthetic order """

    wrong_default_config_type = "The default value of the descriptor must be of type: {default_type}; " \
                                "currently given: {current_type}"

    allowed_values_list = "The parameter allowed_values must be of type list"

    missing_allowed_values = "Config option: {config_name}; needs at least one allowed value"

    wrong_enum_config_type = "Allowed enum value: {allowed_value}; of the descriptor must be of type: " \
                             "{default_type}; currently given: {current_type}"


class ConfigurationErrorReason(object):
    """ This class contains all the common errors that can happen during the configuration of synthetic orders
    used in conjunction with raising a ConfigurationError """

    missing_configuration_field = "The field: {field_name}; missing from the payload section: {section_name}"

    invalid_operation_specified = "Invalid configuration operation specified in payload. " \
                                  "Got operation: {given}; only allowed: {allowed_list}"

    operation_forbidden = "The configuration operation: {given}; is not allowed for this strategy. Only allowed: " \
                          "{allowed_list}"

    synth_order_type_not_available = ("This synthetic order type: {given_order_type}; is not available for this "
                                      "strategy type: {strategy_class}; allowed only: {allowed_only}")

    synthetic_order_already_exists = "Cannot register synthetic order with identifier: {identifier}; " \
                                     "as it already exists"

    deleting_a_non_existing_selector = "Attempted to delete a non existing synthetic order with identifier: " \
                                       "{identifier}"

    modify_a_non_existing_selector = "A Synthetic Order with the identifier '{identifier}' " \
                                     "cannot be found on product {product_id}."
    order_type_not_available = "This synthetic order type: {given_order_type}; is not available for this " \
                               "selector type: {selector_class}; allowed only: {allowed_only}"

    cannot_reset_deletion = "Resetting a synthetic order deletion state is not allowed"

    allows_only_one_synth_order = "The default selector only allows a single synthetic order to be set"

    wrong_config_type = "The ConfigOption named: {config_name}; only accepts type: {accepted_type}; " \
                        "but was given: {actual_value}; of type: {actual_type}"

    zero_not_allowed = "The ConfigOption named: {config_name} must not be empty/ zero. Found {actual_value!r}"

    slot_name_reconfig_forbidden = "It is not allowed to change the slot_name of an existing synthetic order." \
                                   "Initial slot_name: {initial}; currently provided slot_name: {provided}"

    default_selector_must_have_synth_ord = "The default selector must have a synthetic order defined on registration"

    not_in_enum = "The value: {actual_value}; is not allowed for option: {config_name}; Choose from: {allowed_values}"

    config_will_cascade = "Invalid config key: {config_key}; for order because of config cascading. " \
                          "These configs will be cascaded: [{cascaded_list}]"

    config_is_required = "The configuration field: {config_name}; is required and was not provided on initial config"

    unrecognized_message_type = "This message type is not recognized. Given: {original}, recognized: {recognized}"

    message_type_field_not_matching = "The field: {field_name} is required for the message_type: {msg_type}"

    message_type_needs_selector = "For the message_type 'synthetic_selector' a selector subclass must be provided"

    slot_name_is_different_to_identifier = ("Invalid slot_name: {slot_name} is not equal to identifier: {identifier} "
                                            "(should be the same).")

    not_valid_identifier = (u"The identifier: '{identifier}' is not valid, as it should only contain ASCII letters, "
                            u"digits and underscores.")

    identifier_too_long = "The identifier is not allowed to be longer than 64 characters."

    invalid_broker_area_product_combination = ("The combination of broker {broker_id!r}, instrument {instrument_id!r} "
                                               "and sequence item {product_id!r} is invalid")
    inactive_strategy = "Cannot place synthetic orders for inactive strategies."
    unsupported_fields = "This Synthetic Order does not have the following parameter(s): {}"
# endregion


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly!")  # pragma: no cover
