
import abc
import copy
import json
import numbers

import bson
import six
from six.moves import map

import autotrader_lib.mongo_data_export as MDE
import autotrader_lib.util as ALU


class FieldValidationError(Exception):
    """ To use when a single field cannot be validated"""
    pass


cast_functions = {bool: MDE.to_boolean, int: MDE.to_int, float: MDE.to_float}


def _cast_value(value, expected_type):
    """
    Cast a value to the given type
    :param value: The value to cast
    :param expected_type: Either a type or a subclass or instance of AdditionalTypeABC
    :return: The converted value
    """
    if value is None:
        # None stays None to unset a value (independent of the type)
        cast_function = lambda x: None
    elif hasattr(expected_type, "validate_and_cast_to_mongo"):
        # Custom types defined in this module (AdditionalTypeABC)
        cast_function = expected_type.validate_and_cast_to_mongo
    elif expected_type == numbers.Number:
        cast_function = MDE.to_number
    else:
        if expected_type == str and not isinstance(value, (str, six.text_type)):
            raise FieldValidationError(
                "expected type: {} not {}.".format(_get_type_description(expected_type), type(value).__name__))
        # simple types
        cast_function = cast_functions.get(expected_type, expected_type)

    # Now use the cast function to cast the value to the correct type (and thereby validate the type)
    try:
        value = cast_function(value)
    except UnicodeError:
        raise FieldValidationError("{!r} should not contain non-ascii characters!".format(value))
    except (ValueError, AttributeError, TypeError):
        raise FieldValidationError(
            "expected type: {} not {}.".format(_get_type_description(expected_type), type(value).__name__))
    try:
        # Make sure the value can be written to mongoDB. Otherwise we would get not recoverable errors later.
        bson.BSON.encode({"key": value})
    except Exception as err:
        raise FieldValidationError("{} is not BSON serializable. Reason: {}".format(value, str(err)))
    return value


def _inverse_cast(value, expected_type):
    """
    Cast from mongo value to json serializable value
    :param value: The value to cast
    :param expected_type: Either a type or a subclass or instance of AdditionalTypeABC
    :return: Json serializable value
    """
    if value is None:
        return None
    if hasattr(expected_type, "to_json_serializable"):
        # Custom types defined in this module (AdditionalTypeABC)
        return expected_type.to_json_serializable(value)
    return value


def _get_type_description(expected_type):
    """
    Get the string representation of a type, as we like to send it via REST-API
    :param expected_type: Either a type or a subclass or instance of AdditionalTypeABC
    :rtype: str
    """
    try:
        return getattr(expected_type, "get_typename")()
    except AttributeError:
        return expected_type.__name__


class AdditionalTypeABC(six.with_metaclass(abc.ABCMeta, object)):
    """
    Class for defining additional types with a conversion rules from a json serialization to the type.

    WARNING: custom subclasses in strategy packages are not supported!
    """

    @classmethod
    def get_typename(cls):
        return cls.__name__

    @abc.abstractmethod
    def validate_and_cast_to_mongo(self_or_cls, value):
        """
        Implement this for custom conversion functions between the json serializable type received in the json and
        the type you like to use inside your code.

        IMPORTANT: The value returned by this has to be a/ correspond to a valid MongoDB data type.
        """
        raise NotImplementedError

    def to_json_serializable(self_or_cls, value):
        """
        The inverse conversion of validate_and_cast_to_mongo. Take a value that is valid inside mongoDB and return
        a value that is valid inside the JSON.

        This function is only called for strategy templates. For synthetic orders the mongoDB value must be JSON
        serializable without further conversion!
        """
        return value


class Datetime(AdditionalTypeABC):
    """
    Used to specify a type that correspond to a datetime.datetime in MongoDB and an ISO string in json.

    WARNING: This can only be used for strategy templates and not for synthetic orders.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        converted = ALU.convert_datestring(value)
        if converted is None:
            raise FieldValidationError("{!r} does not match the expected iso-format "
                                       "'%Y-%m-%dT%H:%M:%S.%fZ' ('.%f' and 'Z' optional)".format(value))
        if converted.year < 1900:
            # Years before 1900 would break strftime, so we disallow them here.
            raise FieldValidationError("Dates before 1900 are not supported, but {!r} was given.".format(value))
        return converted

    @classmethod
    def to_json_serializable(cls, value):
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @classmethod
    def get_typename(cls):
        return "ISODateUTC"


class Enum(AdditionalTypeABC):
    """
    Used to specify a type that only takes one out of a discrete set of strings.
    """

    def __init__(self, allowed_values):
        """
        :param allowed_values: The values that this field can be set to. Either a list of strings,
                               or an (Ordered-)Dict of strings mapped to human-readable descriptions
        :type allowed_values: list or dict
        """
        if isinstance(allowed_values, list):
            self.allowed_values = list(allowed_values)
            self.allowed_value_descriptions = list(allowed_values)
        elif isinstance(allowed_values, dict):
            if not all(isinstance(descr, six.string_types) for descr in six.itervalues(allowed_values)):
                raise TypeError("The allowed_value_descriptions of type Enum must only contain strings")
            self.allowed_values = list(allowed_values.keys())
            self.allowed_value_descriptions = list(allowed_values.values())
        else:
            raise TypeError("The allowed_values must be list or dict ({!r} provided).".format(type(allowed_values)))

    def validate_and_cast_to_mongo(self, value):
        if value not in self.allowed_values:
            raise FieldValidationError("expected one of {} not {!r}.".format(
                ", ".join(map(repr, self.allowed_values)), value))
        return value


class JsonString(AdditionalTypeABC):
    """A type for strings that have to be valid json

    WARNING: This might be removed in the future in favor of a type that allows the specification of a json schema.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if isinstance(value, (str, six.text_type)):
            try:
                return json.loads(value)
            except ValueError as err:
                raise FieldValidationError("{!r} is not valid JSON ({})".format(value, err))
        else:
            return value

    @classmethod
    def to_json_serializable(cls, value):
        return json.dumps(value)

    @classmethod
    def get_base_type(cls):
        return "str"


class IntAsString(AdditionalTypeABC):
    """
    Store this data as string internally (in Mongo), but tell the front-end that we expect an integer.
    Accepts integers as either int or string.

    NOTE: This is only intended for strategy templates and not for synthetic orders.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        try:
            as_int = int(str(value))
        except ValueError:
            raise FieldValidationError("{!r} is not an integer number".format(value))
        cls._additional_validations(as_int)
        return str(as_int)

    @classmethod
    def _additional_validations(cls, value):
        """
        Allows subclasses to implement additional validations

        Receives the value cast to integer and can raise FieldValidationErrors if desired..
        :type value: int
        """
        pass

    @classmethod
    def to_json_serializable(cls, value):
        return int(value)

    @classmethod
    def get_typename(cls):
        return "int"

    @classmethod
    def get_base_type(cls):
        return "int"


class ListOf(AdditionalTypeABC):
    """
    Type for lists of values, where all values have the same type.
    """

    def __init__(self, inner_type):
        self.inner_type = inner_type

    def validate_and_cast_to_mongo(self, value):
        if not isinstance(value, list):
            raise FieldValidationError("expected type: list not {}.".format(type(value).__name__))
        converted_list = []
        for i, inner_value in enumerate(value):
            try:
                converted_list.append(_cast_value(inner_value, self.inner_type))
            except FieldValidationError as err:
                raise FieldValidationError("List element #{}: {}".format(i, err))
        return converted_list

    def to_json_serializable(self, value):
        converted_list = []
        for inner_value in value:
            converted_list.append(_inverse_cast(inner_value, self.inner_type))
        return converted_list

    def get_typename(self):
        return "ListOf({})".format(_get_type_description(self.inner_type))


class AdditionalViewType(AdditionalTypeABC):
    """
    Type used for additional view fields

    WARNING: This can only be used for strategy templates and not for synthetic orders.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if not isinstance(value, list):
            raise FieldValidationError("expected type: list not {}.".format(type(value).__name__))
        converted_dict = {"_type": "view", "instrument_ids": []}
        for i, inner_value in enumerate(value):
            if inner_value:
                try:
                    converted_dict["instrument_ids"].append(str(inner_value))
                except FieldValidationError as err:
                    raise FieldValidationError("List element #{}: {}".format(i, err))
        if not converted_dict["instrument_ids"]:
            raise FieldValidationError("Additional views cannot be empty and must contain non empty elements.")
        return converted_dict

    @classmethod
    def to_json_serializable(cls, value):
        return list(value["instrument_ids"])

    @classmethod
    def get_typename(cls):
        return "AdditionalViewType"

    @classmethod
    def get_base_type(cls):
        return "ListOf(str)"


class IdType(IntAsString):
    """
    Base class for types that represent an id as a non-negative integer that is sent to autotrader as string.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        try:
            as_int = int(str(value))
        except ValueError:
            raise FieldValidationError("{} is not an integer number".format(value))
        if as_int < 0:
            raise FieldValidationError("Value must be greater than or equal to 0")
        return str(as_int)

    @classmethod
    def get_typename(cls):
        return "AnyId"

    @classmethod
    def get_base_type(cls):
        return "str"


class BrokerIdType(IdType):
    """
    This type is used for config fields that allow configuration of a broker (sometimes also called venue)
    """

    @classmethod
    def get_typename(cls):
        return "BrokerId"


class InstrumentIdType(AdditionalTypeABC):
    """
    This type is used for configuation of market areas or instruments
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if not isinstance(value, (str, six.text_type, int)) or isinstance(value, bool):
            raise FieldValidationError("instrument ids/ market area ids must be of type integer or string")
        return str(value)

    @classmethod
    def get_base_type(cls):
        # We use str and not int as basetype, to allow for EPEX style market areas
        # in addition to Joule instrument ids.
        return "str"

    @classmethod
    def get_typename(cls):
        return "InstrumentId"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class SequenceIdType(IdType):
    """
    Used to configure sequences.
    """

    @classmethod
    def get_typename(cls):
        return "SequenceId"


class SequenceItemIdType(IdType):
    """
    Used to configure sequence items.
    """

    @classmethod
    def get_typename(cls):
        return "SequenceItemId"


class CombinedSequenceItemIdType(AdditionalTypeABC):
    """
    A sequence id and a sequence item id, combined by an underscore.

    In autoTRADER this translates to a product_id.
    But note that EPEX and Nordpool product ids are not supported via this type.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        try:
            sequence_id, sequence_item_id = value.split("_")
            SequenceIdType._additional_validations(int(sequence_id))
            SequenceItemIdType._additional_validations(int(sequence_item_id))
        except (TypeError, ValueError, AttributeError, FieldValidationError):
            raise FieldValidationError("A CombinedSequenceItemsId should consist of a sequence_id and a "
                                       "sequence_item_id, joined by a single underscore")
        return value

    @classmethod
    def get_base_type(cls):
        return "str"

    @classmethod
    def get_typename(cls):
        return "CombinedSequenceItemId"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class TimestampType(AdditionalTypeABC):
    """
    A type for unix utc timestamps.

    A client implementation may choose to display a datetime selector and convert the value to a unix timestamp
    before sending it over the wire.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        return float(value)

    @classmethod
    def get_base_type(cls):
        return "float"

    @classmethod
    def get_typename(cls):
        return "Timestamp"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class ExpiryTsType(TimestampType):
    """
    A timestamp that has the purpose of the expiry of something.
    """

    @classmethod
    def get_typename(cls):
        return "ExpiryTs"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class PriceType(AdditionalTypeABC):
    """
    Type for Price fields
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if isinstance(value, bool):
            # we don't want boolean values to be cast to 0/1.
            raise FieldValidationError("Prices cannot be of type {type}".format(type=type(value).__name__))
        return float(value)

    @classmethod
    def get_base_type(cls):
        return "float"

    @classmethod
    def get_typename(cls):
        return "Price"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class QuantityType(AdditionalTypeABC):
    """
    Field for quantity types.

    Quantities cannot be negative. Use NetQuantityType for balanced quantities that can be negative.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if isinstance(value, bool):
            # we don't want boolean values to be cast to 0/1.
            raise FieldValidationError("Quantities cannot be of type {type}".format(type=type(value).__name__))
        if not isinstance(value, int):
            # Most instruments use integer quantities, so we keep any
            # integer input as integer, to avoid loss of precision.
            value = float(value)
        if value < 0:
            raise FieldValidationError("Quantities cannot be negative numbers")  # The NetQuantityType allows them
        return value

    @classmethod
    def get_base_type(cls):
        return "float"

    @classmethod
    def get_typename(cls):
        return "Quantity"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class NetQuantityType(AdditionalTypeABC):
    """
    For balanced/ net quantities.
    """

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        if isinstance(value, bool):
            # we don't want boolean values to be cast to 0/1.
            raise FieldValidationError("Quantities cannot be of type {type}".format(type=type(value).__name__))
        if isinstance(value, int):
            # Most instruments use integer quantities, so we keep any
            # integer input as integer, to avoid loss of precision.
            return value
        return float(value)

    @classmethod
    def get_base_type(cls):
        return "float"

    @classmethod
    def get_typename(cls):
        return "NetQuantity"

    @classmethod
    def to_json_serializable(cls, value):
        return value


class TradingAccountType(AdditionalTypeABC):
    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        return str(value)

    @classmethod
    def get_base_type(cls):
        return "str"

    @classmethod
    def get_typename(cls):
        return "TradingAccount"

    @classmethod
    def to_json_serializable(cls, value):
        return value


DirectionType = Enum(["buy", "sell"])
DirectionType.get_typename = lambda: "Direction"
DirectionType.get_base_type = lambda: "Enum"


class ConfigField(object):
    """
    A descriptor to define which fields of the strategy settings can be set via the REST-API.
    """

    def __init__(self, caption, description, expected_type,
                 mandatory, read_only, hidden=False, default=None):
        """
        Use this descriptor to define config fields (=parameters) which can be configured for this strategy
        via the REST-API.

        :param caption: A human readable name of this config field. Will be displayed by the Joule front-end.
        :type caption: str
        :param description: A human readable description of this config field. Might be shown as tooltip/ help-text by
                            a front-end
        :type description: str
        :param expected_type: Define the type for values that this field can be set to. It can be one of str, int,
                              float, bool and a subclass of the AdditionalTypeABC defined in this module.
                              Note that setting the value to None is always allowed unless the parameter is mandatory
                              (see below).
        :type expected_type: type or AdditionalTypeABC
        :param mandatory: Setting to specify if / under which conditions this parameter is mandatory.
                          Bool if the subclass uses binary logic, str otherwise
        :type mandatory: str or bool
        :param read_only: If / Under what conditions this parameter cannot be changed.
                          Bool if the subclass uses binary logic, str otherwise
        :type read_only: str or bool
        :param hidden: Set this to true, if the parameter should not be included when querying the template meta-data.
        :type hidden: bool
        :param default: Initial value for this parameter, as it would be received by the REST-API.
                        This value will be subject to the same type validation and conversion rules as normal
                        parameters are.
                        Note that this is not a fall-back. I.e. it will only be used when the strategy is created
                        or when we switch to a new template, but the value can still be set to None later on updates
                        (unless the parameter is mandatory)
        """
        self.fvalidate = None
        self.caption = caption
        self.description = description
        self.hidden = hidden
        self.default = default
        self.expected_type = expected_type
        self.mandatory = mandatory
        self.read_only = read_only
        self._name = None  # Will be set by __set_name__
        self._is_overridden = False

    @property
    def name(self):
        return self._name

    def overridden_with(self, **kwargs):
        """
        Get a copy of this descriptor, with some arguments overridden.

        This can be used to set defaults on a subclass without modifying the base class.

        :param kwargs: Any of the keywords arguments supported by the __init__ of the ConfigField
        :type kwargs: dict
        :return: A deep copy of self, with the given attributes changed.
        :rtype: ConfigField
        """
        parent_kwargs = {"caption": self.caption, "description": self.description,
                         "expected_type": copy.deepcopy(self.expected_type),
                         "mandatory": self.mandatory, "read_only": self.read_only, "hidden": self.hidden,
                         "default": self.default}
        unsupported_kwargs = set(kwargs) - set(parent_kwargs)
        if unsupported_kwargs:
            raise ValueError("Function overridden_with does not support keyword "
                             "argument(s) {}".format(", ".join(unsupported_kwargs)))
        parent_kwargs.update(kwargs)
        new_instance = type(self)(**parent_kwargs)
        new_instance.fvalidate = self.fvalidate
        new_instance._is_overridden = True
        return new_instance

    def validator(self, fvalidate):
        """
        Decorator to attach custom validation functions to this descriptor.

        Custom validator functions should raise a FieldValidationError on validation failures and return nothing.

        :param fvalidate: The decorated function to be used as validator.
        :type fvalidate: function
        :return: The descriptor instance
        :rtype: ConfigField
        """
        self.fvalidate = fvalidate
        return self

    def __get__(self, instance, owner):
        if instance is None:
            # When get is called on the class, return the descriptor object
            return self

        # WARNING: the following line raises AttributeError if _<<attr_name>> doesn't exist
        return getattr(instance, "_" + self._name)

    def __set__(self, instance, value):
        try:
            value = _cast_value(value, self.expected_type)
        except FieldValidationError as err:
            message = "Field {!r}: {}".format(self.caption, err)
            raise FieldValidationError(message)
        self._general_validation(instance, value)
        # after converting the type, we call some specific rule validation from the validator
        if self.fvalidate is not None and value is not None:
            try:
                self.fvalidate(self, value)
            except FieldValidationError as err:
                message = "Custom validation error for field {!r}: {}".format(self._name, err)
                raise FieldValidationError(message)
            except Exception as err:
                raise FieldValidationError("The custom validator for field {!r} failed with an unexpected error: "
                                           "{} {!r}".format(self._name, type(err).__name__, err))
        # and if everything went well we set the _attribute
        setattr(instance, "_{}".format(self._name), value)

    def _set_name_backport(self, unused_owner, name):
        # In python3, use __set_name__
        self._name = name

    def _general_validation(self, instance, value):
        pass

    def get_description_dict(self):
        if self.hidden:
            return None
        field_description = {
            "internal_field_name": self._name,
            "caption": self.caption,
            "description": self.description,
            "mandatory": self.mandatory,
            "read-only": self.read_only,
        }
        expected_type = self.expected_type
        if isinstance(expected_type, Enum):
            field_description["allowed_values"] = self.expected_type.allowed_values
            field_description["allowed_value_descriptions"] = self.expected_type.allowed_value_descriptions
        field_description["type"] = _get_type_description(expected_type)
        try:
            field_description["base_type"] = expected_type.get_base_type()
        except AttributeError:
            field_description["base_type"] = field_description["type"]
        if self.default is not None:
            field_description["default"] = self.default
        return field_description


class TemplateMeta(type):
    """
    Meta class to backport the __set_name__ behavior of python 3
    """

    def __init__(cls, name, bases, attrs):
        super(TemplateMeta, cls).__init__(name, bases, attrs)
        for k, v in six.iteritems(attrs):
            if issubclass(type(v), ConfigField):
                v._set_name_backport(cls, k)


class Configurable(six.with_metaclass(TemplateMeta, object)):
    """
    Base class for objects that can be configured using _ConfigFields
    """

    @classmethod
    def fields(cls):
        """
        Return a dict with the names of all StrategyConfigFields of this template mapped to the descriptor

        :rtype: dict
        """
        fields = {}
        for param_name, value in six.iteritems(vars(cls)):
            if not param_name.startswith("_") and isinstance(value, ConfigField):
                fields[param_name] = value

        for parent_class in cls.__bases__:
            if issubclass(parent_class, Configurable):
                fields.update(parent_class.fields())
        return fields

    @classmethod
    def get_attribute_groups(cls):
        """
        Return an ordered list of all StrategyConfigFields in the parameter groups they belong to.

        :rtype: list
        """
        raise NotImplementedError("Must be implemented in the subclass")

    @classmethod
    def get_meta_data(cls):
        """
        Return a dictionary describing all StrategyConfigFields in their groups and with their meta-data.

        :rtype: dict(list)
        """
        groups = cls.get_attribute_groups()
        out_groups = []
        fields_in_groups = {field_name for group in groups for field_name in group.get("config_fields", [])}
        ungrouped_fields = set(cls.fields()) - fields_in_groups
        groups.append({"caption": "Additional Settings",
                       "description": "Additional settings that are not assigned to any group.",
                       "config_fields": sorted(ungrouped_fields)})
        for group in groups:
            out_properties = []
            for attribute in group.get("config_fields", []):
                field_description = cls._get_config_field_description(attribute)
                if field_description is not None:
                    out_properties.append(field_description)
            if out_properties:
                out_groups.append({"config_fields": out_properties,
                                   "caption": group.get("caption", ""),
                                   "description": group.get("description", "")})
        return {"groups": out_groups}

    @classmethod
    def _get_config_field_description(cls, config_field_name):
        """
        Get the meta-data for a single config field, as used by the get_meta_data function.

        :param config_field_name: Name of the attribute at the python level
        :type config_field_name: str
        :rtype: dict
        """
        return getattr(cls, config_field_name).get_description_dict()

    def _apply_defaults(self):
        validation_errors = []
        for param_name in self.fields():
            prop = getattr(type(self), param_name)
            if prop.default is not None:
                try:
                    setattr(self, param_name, prop.default)
                except FieldValidationError as err:
                    validation_errors.append("Invalid default: {}".format(err))
        return validation_errors
