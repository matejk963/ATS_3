""" This module contains the configuration descriptor class and helper functions as utilities for config reporting"""
from __future__ import absolute_import
import weakref

import autotrader_lib.package_config_fields as PKG_CONF
import autotrader_synthetic.errors as ERR
import six


class ConfigOptionDescriptor(object):
    """ A descriptor allows for a shared implementation to define a instance attribute on a class level.

    .. deprecated:: V1.114.9

        This is deprecated! Use the :class:`autotrader_synthetic.config_util.SyntheticOrderConfigField` instead!
    """

    def __init__(self, name, config_type, description, default=None, required=False, nonzero=False):
        """ The descriptor will be defined as a class level attribute so init will be called on that

        :param name: The descriptor name should ideally match the attribute at which it is assigned on the class
        :type name: str
        :param config_type: This should be the class of the variable that the descriptor accepts
        :type config_type: type
        :param description: This should provide an explanation of what this particular configuration is used for
        :type description: str
        :param default: This is the default value of the descriptor which will be used if none is defined
        on first config
        :param required: Is the parameter required for the config to be valid
        :type required: bool
        :param nonzero: if set to True, the parameter is not allowed to take empty / zero values. Specifically,
                        bool(value) must be True
        :type nonzero: bool
        """
        self.name = name
        self.config_type = config_type
        self.description = description
        self.required = required
        self.nonzero = nonzero

        if default and not isinstance(default, self.config_type):
            raise ERR.ConfigurationError(ERR.DescriptorErrorReason.wrong_default_config_type.format(
                default_type=str(self.config_type),
                current_type=default.__class__.__name__
            ))

        else:
            self.default = default

        # values is __ so that nobody messes with it or tries to use it in any way
        # the purpose of the WeakKeyDictionary is that if the only thing keeping the reference to the object
        # is this dictionary, then the object will be removed as a key and garbage collected
        # for the main magic of the descriptors see __get__ and __set__
        self.__values = weakref.WeakKeyDictionary()

    def __get__(self, obj, unused_objtype):
        """ The getter function to return the value of the set descriptor

        NOTE: Since the descriptor instance itself is created at the class level it needs to hold reference to the
        actual object instance where it is used

        :param obj: the instance of the referring object for which the descriptor was previously set
        :param unused_objtype: Not used
        :return: Will return the value of the attribute of the object for which the descriptor is set
        """
        if obj is None:
            # When get is called on the class, return the descriptor object
            return self
        return self.__values.get(obj, self.default)

    def __set__(self, obj, new_value):
        """ On the setting of the values we will do some type checking, since this would not happen
        at high volume the performance would likely not be impacted

        :param obj: the referer object which is trying to set this descriptor
        :param new_value: the value that is attempted to be set
        :raises ERR.ConfigurationError: Will raise an Exception if the type being set is incorrect
        :return: None
        """

        # To avoid unicode configuration data from MongoDB
        if self.config_type == str and isinstance(new_value, six.text_type):
            try:
                new_value = str(new_value)
            except UnicodeError:
                raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.wrong_config_type.format(
                    config_name=self.name,
                    accepted_type=self.config_type,
                    actual_value=new_value,
                    actual_type=new_value.__class__.__name__
                ))

        # Nones are allowed to erase a certain configuration
        if new_value is not None and not isinstance(new_value, self.config_type):
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.wrong_config_type.format(
                config_name=self.name,
                accepted_type=self.config_type,
                actual_value=new_value,
                actual_type=new_value.__class__.__name__
            ))

        if self.nonzero and not new_value:
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.zero_not_allowed.format(
                config_name=self.name,
                actual_value=new_value,
            ))

        self.__values[obj] = new_value

    def info(self):
        """ This allows us to gather up information about what settings the descriptor allows and forward them """
        return dict(name=self.name,
                    config_type=self.config_type.__name__,
                    description=self.description,
                    default=str(self.default),
                    required=str(self.required))


class EnumerateConfigOptionDescriptor(ConfigOptionDescriptor):
    """ This descriptor allows us to specify a limited subset of values that are allowed to be set """

    def __init__(self, name, config_type, description, allowed_values, default=None, required=False, nonzero=False):
        """ The descriptor will be defined as a class level attribute so init will be called on that.

        :param name: The descriptor name should ideally match the attribute at which it is assigned on the class
        :type name: str
        :param config_type: This should be the class of the variable that the descriptor accepts
        :type config_type: type
        :param description: This should provide an explanation of what this particular configuration is used for
        :type description: str
        :param allowed_values: This is a list of values which are allowed explicitly for this config option
        :type allowed_values: list
        :param default: This is the default value of the descriptor which will be used if none is defined
        on first config
        :param required: Is the parameter required for the config to be valid
        :type required: bool
        """

        if not isinstance(allowed_values, list):
            raise ERR.DescriptorError(ERR.DescriptorErrorReason.allowed_values_list)

        # there must be an allowed set of values
        if len(allowed_values) < 1:
            raise ERR.DescriptorError(
                ERR.DescriptorErrorReason.missing_allowed_values.format(config_name=name))

        for value in allowed_values:
            if not isinstance(value, config_type):
                raise ERR.ConfigurationError(ERR.DescriptorErrorReason.wrong_enum_config_type.format(
                    allowed_value=value,
                    default_type=str(self.config_type),
                    current_type=value.__class__.__name__))

        self.allowed_values = allowed_values

        super(EnumerateConfigOptionDescriptor, self).__init__(name, config_type, description, default, required,
                                                              nonzero)

    def __set__(self, obj, new_value):
        """ On the setting of the values we will do some type checking.

        Since this would not happen at high volume the performance would likely not be impacted.

        :param obj: the referer object which is trying to set this descriptor
        :param new_value: the value that is attempted to be set
        :raises ERR.ConfigurationError: Will raise an Exception if the type being set is incorrect
        :return: None
        """
        if new_value not in self.allowed_values and (self.required or new_value is not None):
            raise ERR.ConfigurationError(ERR.ConfigurationErrorReason.not_in_enum.format(
                config_name=self.name,
                allowed_values=self.allowed_values,
                actual_value=new_value,
            ))
        super(EnumerateConfigOptionDescriptor, self).__set__(obj, new_value)


class SyntheticOrderConfigField(PKG_CONF.ConfigField):
    def __init__(self, caption, description, expected_type, mandatory=False, read_only=False,
                 hidden=False, default=None, include_in_tooltip=False):
        """

        :param caption: A human-readable name of this config field. Will be displayed by the Joule front-end.
        :type caption: str
        :param description: A human-readable description of this config field. Might be shown as tooltip/ help-text by
                            a front-end
        :type description: str
        :param expected_type: Define the type for values that this field can be set to. It can be one of str, int,
                              float, bool and a subclass of the AdditionalTypeABC.
                              Note that setting the value to None is always allowed unless the parameter is mandatory
                              (see below).
        :type expected_type: type or AdditionalTypeABC
        :param mandatory: Setting to specify if this parameter is mandatory.
        :type mandatory: bool
        :param read_only: Set to True, if this parameter cannot be changed via the front-end/ REST-API.
                          It can still be changed from code.
        :type read_only: bool
        :param hidden: Set this to True, if the parameter should not be included when querying the template meta-data.
        :type hidden: bool
        :param default: Initial value for this parameter, as it would be received by the REST-API.
                        This value will be subject to the same type validation and conversion rules as normal
                        parameters are.
                        Note that this is not a fall-back. I.e. it will only be used when the synthetic order instance
                        is created, but the value can still be set to None later on updates (unless the parameter
                        is mandatory)
        :param include_in_tooltip: If this is set to True, the caption and value of this config field will be shown
                                   in a tool-tip on the Joule screen.
        :type include_in_tooltip: bool
        """
        if expected_type == PKG_CONF.AdditionalViewType:
            raise ValueError("Additional views should be configured on the strategy level, and the SyntheticOrder "
                             "should refer to them by name.")
        if not isinstance(mandatory, bool):
            raise ERR.ConfigurationError("'mandatory' must be a bool, not {} ({!r})".format(type(mandatory), mandatory))
        if not isinstance(read_only, bool):
            raise ERR.ConfigurationError("'read_only' must be a bool, not {} ({!r})".format(type(read_only), read_only))
        super(SyntheticOrderConfigField, self).__init__(caption, description, expected_type,
                                                        mandatory, read_only, hidden, default)
        if not isinstance(include_in_tooltip, bool):
            raise ERR.ConfigurationError("'include_in_tooltip' must be bool,"
                                         " found {!r}".format(type(include_in_tooltip).__name__))
        self.include_in_tooltip = include_in_tooltip

    def __get__(self, instance, owner):
        try:
            return super(SyntheticOrderConfigField, self).__get__(instance, owner)
        except AttributeError:
            return None

    def __set__(self, instance, value):
        if self.mandatory and value in [None, "", []]:
            raise PKG_CONF.FieldValidationError("Field {!r} is mandatory".format(self.name))

        changed = getattr(instance, "_{}".format(self._name), None) != value
        super(SyntheticOrderConfigField, self).__set__(instance, value)
        # Only set _config_changed, if the super call did not fail
        if changed:
            instance.mark_for_database_update()

    def overridden_with(self, **kwargs):
        """
        Get a copy of this descriptor, with some arguments overridden.

        This can be used to set defaults on a subclass without modifying the base class.

        :param kwargs: Any of the keywords arguments supported by the __init__ of the SyntheticOrderConfigField
        :type kwargs: dict
        :return: A deep copy of self, with the given attributes changed.
        :rtype: SyntheticOrderConfigField
        """
        include_in_tooltip = kwargs.pop("include_in_tooltip", self.include_in_tooltip)
        new_instance = super(SyntheticOrderConfigField, self).overridden_with(**kwargs)
        new_instance.include_in_tooltip = include_in_tooltip
        return new_instance

    def get_description_dict(self):
        descr = super(SyntheticOrderConfigField, self).get_description_dict()
        if descr:
            descr["include_in_tooltip"] = self.include_in_tooltip
        return descr


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly!")  # pragma: no cover
