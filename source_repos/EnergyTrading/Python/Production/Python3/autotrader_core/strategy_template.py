from __future__ import absolute_import
import base64
import datetime
import imp
import io
import os.path
import re
import shutil
import six
import tempfile
import zipfile
from collections import OrderedDict

import autotrader_lib.common as COMMON
import autotrader_lib._strategy_managing as SM
import autotrader_lib.package_config_fields as PKG_CONF
# For backwards compatibility we need to import the types and errors here
from autotrader_lib.package_config_fields import (  # noqa: F401
    AdditionalTypeABC, AdditionalViewType, IntAsString, JsonString, Datetime, Enum, ListOf, FieldValidationError
)
from six.moves import zip


class TemplateValidationError(Exception):
    """ To use when the all template cannot be validated."""

    def __init__(self, args, message=None, template_name=""):
        if message is None:
            message = "The template {!r} could not be validated because of the following reasons:\n".format(
                template_name)
        self.message = message + "\n".join(args)
        self.validation_errors = args
        super(TemplateValidationError, self).__init__()

    def __str__(self):
        return self.message


class PackageNotFound(ValueError):
    """
    Raised if we try to load a package but cannot find it in MongoDB.
    """
    pass


class MalformedTemplateError(ImportError):
    """
    Raised when the template class is badly defined.
    """
    pass


# ----------------------------------------------
# Loading of templates
# ----------------------------------------------

def get_raw_strategy_zip(file_list, encoded=False):
    """ Create a zip object in memory with the content of file_list and return the raw content of the zip file.

    :param file_list: a tuple containing the name of the file and its content like
                      [("__init__.py", "import custom_strategy"), ("custom_strategy.py", "")]
    :type file_list: list[tuple]
    :return: the raw content of the zip object.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for filename, content in file_list:
            zip_file.writestr(filename, content)
    raw = zip_buffer.getvalue()

    return base64.b64encode(raw) if encoded else raw


def load_package_from_zip(package_name, package_zip, directory=None):
    """
    Load a strategy template.

    :param package_name: The name of the package from which to load the template
    :type package_name: str
    :param package_zip: The encoded and zipped file.
    :type package_zip: str
    :param directory: The folder where the code should be extracted to. The folder must exist, otherwise an error will
                      be raised. This function does not delete it afterwards, so the caller is responsible for clean-up
                      If it is None, a temporary directory is created and cleaned-up after extracting
                      the template.
    :type directory: str
    :return: The loaded template: a BaseTemplate class or a subclass of it
    """
    if directory is None:
        strategy_dir = tempfile.mkdtemp()
    else:
        strategy_dir = directory
    try:
        os.mkdir(os.path.join(strategy_dir, package_name))
        SM.unzip_custom_package(package_zip, os.path.join(strategy_dir, package_name))
        return package_loader(strategy_dir, package_name)
    finally:
        if directory is None:
            shutil.rmtree(strategy_dir, ignore_errors=True)


def package_loader(directory, package_name):
    """
    Return the correct template class.

    :param directory: The path to the directory where the custom strategy was unzipped to.
    :type directory: str
    :param package_name: Name of the package from which to take the template
    :type package_name: str
    :return: The correct BaseTemplate subclass
    """
    mod_file = None
    try:
        mod_file, mod_path, mod_descr = imp.find_module(package_name, [directory])
        package_object = imp.load_module(package_name, mod_file, mod_path, mod_descr)
    finally:
        if mod_file:
            mod_file.close()
    return package_object


def get_template_from_package(package_object):
    return getattr(package_object, "template_class", BaseTemplate)

# ----------------------------------------------
# StrategyConfigField descriptor
# ----------------------------------------------


class StrategyConfigField(PKG_CONF.ConfigField):
    """
    A descriptor to define which fields of the strategy settings can be set via the REST-API.
    """

    def __init__(self, caption, description, expected_type,
                 mandatory="never", read_only="never", hidden=False, default=None):
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
        :type expected_type: type or autotrader_lib.package_config_fields.AdditionalTypeABC
        :param mandatory: Setting to specify under which conditions this parameter is mandatory.
                          Allowed values: "always", "active" or "never".
                          "always" means that the parameter is always mandatory and must never be None.
                          "active" means that the parameter can remain unset as long as the strategy is not active,
                          but before or when the strategy is activated, the parameter has to be set to a not None value.
                          Setting the mandatory flag to "active" allows for creation of the strategy without deciding
                          about the value for this parameter and deferring this decision to the time when the
                          strategy is activated.
                          "never" means that the parameter is always optional.
                          Setting a parameter to None is equivalent to unsetting the parameter, and the strategy code
                          will always receive the value None if the parameter is not set.
        :type mandatory: str
        :param read_only: Under what conditions this parameter cannot be changed.
                          Allowed values "always", "active" and "never".
                          Sometimes considering every edge case of parameter changing in the strategy implementation
                          would cause too much overhead or increase the risk of bugs. In this case making a parameter
                          read-only while the strategy is active is a good solution. Such parameters can only be
                          changed when the strategy is inactive and has removed all its orders.
                          If read_only is always, then the default value of the parameter is always used.
                          Note that the internal number is a special case, which is formally defined as always
                          read_only, but it must be set on strategy creation.
        :type read_only: str
        :param hidden: Set this to true, if the parameter should not be included when querying the template meta-data.
        :type hidden: bool
        :param default: Initial value for this parameter, as it would be received by the REST-API.
                        This value will be subject to the same type validation and conversion rules as normal
                        parameters are.
                        Note that this is not a fall-back. I.e. it will only be used when the strategy is created
                        or when we switch to a new template, but the value can still be set to None later on updates
                        (unless the parameter is mandatory)
        """
        if mandatory not in ["always", "active", "never"]:
            raise MalformedTemplateError("'mandatory' must be one of 'always', 'active', 'never',"
                                         " not {!r}".format(mandatory))
        if read_only not in ["always", "active", "never"]:
            raise MalformedTemplateError("'read_only' must be one of 'always', 'active', 'never',"
                                         " not {!r}".format(read_only))
        super(StrategyConfigField, self).__init__(caption, description, expected_type,
                                                  mandatory, read_only, hidden, default)

    def _general_validation(self, instance, value):
        if self._name == "internal_number":
            if hasattr(instance, "_internal_number"):
                raise PKG_CONF.FieldValidationError("The 'internal_number' cannot be changed after"
                                                    " the initial creation.")
        elif self.read_only == "always" and value != self.default:
            raise PKG_CONF.FieldValidationError("Field {!r} is read-only!".format(self._name))
        setattr(instance, "_{}".format(self._name), value)


# ----------------------------------------------
# Base Template
# ----------------------------------------------


class BaseTemplate(PKG_CONF.Configurable):
    """
    Base class for strategy templates. Allows for specifying the allowed fields via descriptors.

    Use a subsclass of this template to add additional configuration parameters using the StrategyConfigField
    descriptor. Additionally, to expose the fields via the GET packages/<package_name> endpoint, you have to
    override get_attribute_groups, which defines the groups and the order at which a front-end (such as the
    Joule Screen) should display these fields.
    """
    _username = ""
    _data = None

    # We use last_update_time instead of alteration_time, as we have an auto-expiry index on the alteration_time!
    _mongo_fields = ["_id", "child_id", "object_type", "last_update_time", "username", "package_name", "created_utc",
                     "deleted", "_json_repr"]

    # These names are forbidden to use as fields for custom templates
    RESERVED_FIELD_NAMES = ["id", "child_id", "object_type", "last_update_time", "username", "package_name",
                            "created_utc", "deleted", "json_repr", "halted", "halt_reason", "market_area_1",
                            "market_area_2", "market_area_3", "market_area_4", "market_area_5", "exchange_1",
                            "algorithm"]

    def __init__(self, _strict=True, **kwargs):
        """
        Initialize a template.

        Strategy templates are implemented in a way that the class defines the allowed fields while the instance
        represents the filled-out template which contains data and is validated either within the call to __init__
        or (if _strict is false) in a subsequent call to update_parameters. Then the filled-out data is translated
        (only exchange_id and instrument_ids) before being written into the mongo database and received by autoTRADER.

        :param _strict : True means we raise ValidationErrors for missing mandatory fields, extra fields or
                         values not matching the type/ validator function.
        :type _strict: bool
        :raise TemplateValidationError if some fields are missing or could not be validated.
        """
        validation_errors = []

        # First start with the defaults, then override them with the provided configuration:
        validation_errors.extend(self._apply_defaults())
        for param_name, value in six.iteritems(kwargs):
            if not hasattr(type(self), param_name):
                if _strict:
                    validation_errors.append("Field {!r} does not exist.".format(param_name))
            elif not isinstance(getattr(type(self), param_name), StrategyConfigField):
                if _strict:
                    validation_errors.append("Field {!r} is not defined as StrategyConfigField in "
                                             "the template.".format(param_name))
            else:
                try:
                    setattr(self, param_name, value)
                except PKG_CONF.FieldValidationError as error:
                    if _strict:
                        validation_errors.append(str(error))

        if _strict:
            validation_errors.extend(self._validate_mandatory("create")[0])
            if self.active:
                validation_errors.append("'active' cannot be set to True on strategy creation")

        if validation_errors:
            raise TemplateValidationError(validation_errors, template_name=type(self).__name__)

    def update_parameters(self, _has_exposed_orders=False, **kwargs):
        """
        This function is the main entry point for updating one or more parameters of the filled-out template.

        In terms of the REST-API, this is where PUT requests are handled.

        In addition to the validation provided by the individual StrategyConfigField descriptors and their validators,
        this function performs additional validation of the changeable and mandatory fields that goes beyond the
        context of an StrategyConfigField. Thus this function should be used instead of assigning to the
        StrategyConfigFields directly.

        Can Raise a TemplateValidationError.
        Note: if you catch such an error, you should discard the template instance,
        as it can be in an inconsistent state.

        :param _has_exposed_orders: The validation for mandatory="active" and read_only="active" considers strategies
                                    with exposed orders as being active. Set to true if the strategy has exposed orders.
        :type _has_exposed_orders: bool
        :param kwargs: The parameters to be set on the template
        :type kwargs: dict
        """
        errors = []
        need_active_hint = False
        original_active = self.active
        # The restrictions for active strategies still apply while setting the strategy to inactive.
        # They no longer apply on the next call, when the strategy already is inactive...
        active_flag = _has_exposed_orders or original_active or kwargs.get("active", False)
        for param_name, new_value in kwargs.items():
            if not hasattr(type(self), param_name):
                errors.append("Field {!r} does not exist.".format(param_name))
            elif not isinstance(getattr(type(self), param_name), StrategyConfigField):
                errors.append("Field {!r} is not defined as StrategyConfigField in the template.".format(param_name))
            else:
                try:
                    setattr(self, param_name, new_value)
                except PKG_CONF.FieldValidationError as err:
                    errors.append(str(err))
        # Check mandatory flag, especially with "update"
        mandatory_errors, need_active_hint = self._validate_mandatory("active" if active_flag else "inactive")
        errors.extend(mandatory_errors)
        if errors:
            error_hint = None
            if need_active_hint and not kwargs.get("active"):
                # If there were errors for active strategies, but the customer wanted to set the strategy to inactive,
                # we have to give some explanation why the error occurred.
                if original_active and not self.active:
                    error_hint = ("Deactivating the strategy and updating fields that require an inactive strategy "
                                  "have to be done in separate calls. Details: ")
                elif _has_exposed_orders:
                    error_hint = ("The strategy has not yet removed all its orders and is thus still considered active "
                                  "for the purpose of changing the configuration. Try to repeat this call "
                                  "after a few seconds. Details: ")
            raise TemplateValidationError(errors, message=error_hint, template_name=type(self).__name__)

    def _validate_mandatory(self, method="create"):
        """
        Helper function to check if all mandatory fields are given

        :param method: One of "create", "active" and "inactive". Describes for what state of the strategy the
                       mandatory fields should be checked
        :type method: str
        :returns: A tuple. The first value is a list of error message (empty list if no error occurred),
                  the second one is a boolean flag indicating whether any errors only occurred because the
                  strategy is active.
        :rtype: Tuple[list, bool]
        """
        errors = []
        need_active_hint = False
        for field in self.fields():
            prop = getattr(type(self), field)
            if not hasattr(self, field) or getattr(self, field) in (None, "", []):
                if prop.mandatory == "always":
                    errors.append("The field {!r} is mandatory.".format(field))
                elif prop.mandatory == method == "active":
                    errors.append("The field {!r} is mandatory for active strategies.".format(field))
                    need_active_hint = True
        return errors, need_active_hint

    @classmethod
    def get_attribute_groups(cls):
        """
        Return an ordered list of all StrategyConfigFields in the parameter groups they belong to.

        :rtype: list
        """
        return [{"caption": "General Settings",
                 "description": "General parameters for this concurrent algorithm",
                 "config_fields": ["internal_number", "caption", "exchange", "instrument_ids", "active"]}]

    def to_mongo_object(self, package_name, username, child_id=0):
        """Return the representation of the strategy as we insert it in mongo.

        :param package_name: Name of the package from which the filled-out template originated.
        :type package_name: str
        :param username: Name of the user who made the last update to the strategy
        :type username: unicode
        :param child_id: child on which the strategy is run
        :type child_id: int
        :return: the mongo object to insert in the mongo database
        :rtype: dict
        """
        data = ["{}.{}".format(COMMON.MongoDBObjects.strategy_configuration, self.internal_number),
                child_id,
                COMMON.MongoDBObjects.strategy_configuration,
                datetime.datetime.utcnow(),
                username,
                package_name]

        # Note that "deleted" and "_json_repr" (self._mongo_fields[6:]) are excluded on purpose!
        ret = dict(list(zip(self._mongo_fields, data)))

        for param_name in self.fields():
            if param_name == "instrument_ids":
                # Special handling for the instrument ids
                inst_ids = getattr(self, param_name)
                for idx, market_area_key in enumerate([COMMON.StrategyJsonKey.market_area_1,
                                                       COMMON.StrategyJsonKey.market_area_2,
                                                       COMMON.StrategyJsonKey.market_area_3,
                                                       COMMON.StrategyJsonKey.market_area_4,
                                                       COMMON.StrategyJsonKey.market_area_5]):
                    if len(inst_ids) > idx:
                        ret[market_area_key] = inst_ids[idx]
                    else:
                        break
            elif param_name == "exchange":
                ret["exchange_1"] = getattr(self, param_name, None)
            else:
                ret[param_name] = getattr(self, param_name, None)

        if "algorithm" in ret:
            ret["algorithm"] = COMMON.SupportedStrategies.get_algorithm_name_mongo(ret["algorithm"])

        # to be able to sent StrategyConfig via PUSH without [re-]loading a template we keep repr in mongo
        ret["_json_repr"] = self.dict_from_mongo_object(ret)

        return ret

    @classmethod
    def from_mongo_object(cls, mongo_object, _strict=False):
        """ Initialize the template from a mongo object

        :param mongo_object: The dictionary received from MongoDB
        :type mongo_object: dict
        :rtype: BaseTemplate
        """
        attributes = cls.dict_from_mongo_object(mongo_object)
        return cls(_strict=_strict, **attributes)

    @classmethod
    def dict_from_mongo_object(cls, mongo_object):
        """ Initialize the template from a mongo object so that we can return in the rest api the template fields

        :param mongo_object: input object retrieved from mongo
        :type mongo_object: dict
        """
        attributes = {}
        for field, value in six.iteritems(mongo_object):
            if field.startswith("market_area"):
                # To preserve the order of the instrument_ids, they are handled afterwards.
                continue
            elif field == "exchange_1":
                attributes["exchange"] = value
            elif field not in cls._mongo_fields:
                try:
                    expected_type = getattr(cls, field).expected_type
                except AttributeError:
                    # Allow loading the mongo data even if the template (changed/ got broken)
                    attributes[field] = value
                else:
                    attributes[field] = PKG_CONF._inverse_cast(value, expected_type)

        attributes["instrument_ids"] = [mongo_object[COMMON.StrategyJsonKey.market_area_1]]
        for market_area_field in [COMMON.StrategyJsonKey.market_area_2, COMMON.StrategyJsonKey.market_area_3,
                                  COMMON.StrategyJsonKey.market_area_4, COMMON.StrategyJsonKey.market_area_5]:
            if mongo_object.get(market_area_field):
                attributes["instrument_ids"].append(mongo_object[market_area_field])
            else:
                break
        return attributes

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return all(getattr(self, key, None) == getattr(other, key, None) for key in self.fields())

    # --------------------------------------------------------------
    #  ------------------------ PROPERTIES ------------------------
    # --------------------------------------------------------------
    internal_number = StrategyConfigField(caption="Internal Number",
                                          description="Unique identifier of this concurrent algorithm",
                                          expected_type=str, mandatory="always", read_only="always")

    @internal_number.validator
    def internal_number(self, value):
        if value is not None and re.match(COMMON.STRATEGY_NAME_PATTERN, value) is None:
            error_description = (
                "'internal_number' [%s] can only contain alphanumeric characters and '-' "
                "(and '@', which has a special meaning inside autoTRADER) and "
                "must be 1 to %s characters long." % (value, COMMON.MAX_STRATEGY_NAME_LENGTH)
            )
            raise PKG_CONF.FieldValidationError(error_description)

    caption = StrategyConfigField(caption="Algo Name", description="User-friendly name of this concurrent algorithm",
                                  expected_type=str, mandatory="always", read_only="never")

    @caption.validator
    def caption(self, value):
        if value is not None and not value.strip():
            raise PKG_CONF.FieldValidationError("'caption' must not be empty or consist of only whitespace characters.")

    exchange = StrategyConfigField(caption="Exchange", description="The Connection to trade",
                                   expected_type=PKG_CONF.Enum(COMMON.Exchange.get_external()),
                                   mandatory="always",
                                   read_only="active")

    instrument_ids = StrategyConfigField(caption="Instrument Ids",
                                         description="A list of instrument ids or market areas where the strategy"
                                                     " should trade.",
                                         expected_type=PKG_CONF.ListOf(str), mandatory="always", read_only="active")

    @instrument_ids.validator
    def instrument_ids(self, value):
        if len(value) > 5:
            raise PKG_CONF.FieldValidationError("Currently at most 5 instrument_ids are supported")
        # We do not check at this point if the instrument is valid for autoTRADER.
        # That last check is done when loading the strategy.
        for i, inst_id in enumerate(value):
            if not isinstance(inst_id, str):
                raise PKG_CONF.FieldValidationError("Instrument ids have to be strings,"
                                                    " but {!r} at position {} is not.".format(inst_id, i))
            if not inst_id:
                raise PKG_CONF.FieldValidationError("Empty instrument_id given at position {}.".format(i))

    active = StrategyConfigField(caption="Active", description="Sets this concurrent algorithm active or inactive",
                                 expected_type=bool, read_only="never", mandatory="always", default=False)


class TrayportBaseTemplate(BaseTemplate):
    broker_id = StrategyConfigField("Venue",
                                    "The Venue to place orders on",
                                    PKG_CONF.IntAsString, mandatory="always", read_only="active")
    trading_account = StrategyConfigField("Account Name (Trading Account)",
                                          "The default trading account to use by this strategy for the field "
                                          "'AccountName'", str, mandatory="never", read_only="active")

    @classmethod
    def get_attribute_groups(cls):
        groups = super(TrayportBaseTemplate, cls).get_attribute_groups()
        # Add broker_id to general settings at position 3 (after exchange but before instrument_ids)
        groups[-1]["config_fields"].insert(3, "broker_id")
        groups[-1]["config_fields"].append("trading_account")

        return groups


class MifidTemplate(TrayportBaseTemplate):
    allowed_values = OrderedDict(
        list(
            zip(
                COMMON.TradingCapacityType.__slots_container_py2__,
                ["Dealing on own account", "Matched principal", "Any other capacity"])
        )
    )
    mifid_trading_capacity = StrategyConfigField("Trading Capacity",
                                                 "Trading Capacity is an indication of whether the transaction results "
                                                 "from the executing firm carrying out matched principal trading."
                                                 " 'DEAL': Dealing on own account;"
                                                 " 'MTCH': Matched principal;"
                                                 " 'AOTC': Any other capacity",
                                                 PKG_CONF.Enum(allowed_values),
                                                 mandatory="never", default="DEAL")

    mifid_decision_maker = StrategyConfigField("Decision Maker", "The code for the user that is responsible for the "
                                                                 "investment decisions carried out by this concurrent "
                                                                 "algorithm", str, mandatory="active")

    mifid_execution_maker = StrategyConfigField("Execution Maker",
                                                "Code used to identify the algorithm within the investment firm that"
                                                " is responsible for the execution under the MiFID II regulation."
                                                " The Execution Maker is unique for each package used by a concurrent"
                                                " algo.",
                                                str, mandatory="active")

    mifid_liquidity_provision = StrategyConfigField("Liquidity Provision",
                                                    "Liquidity Provision according to the MiFID II regulations. Set to"
                                                    " 'True' if the purpose of this algorithm is market making",
                                                    bool, mandatory="always", default=False)

    mifid_dea = StrategyConfigField("DEA",
                                    "Direct Electronic Access. Se to 'True' when submitting the order to the trading "
                                    "venue using DEA, 'False' otherwise.",
                                    bool, mandatory="always", default=False)

    mifid_dea_client_id = StrategyConfigField("DEA Client ID",
                                              "The code of the DEA user, if DEA is used.",
                                              str, mandatory="never")

    mifid_derivative_indicator = StrategyConfigField("Derivative Indicator",
                                                     "Commodity derivative indicator according to MiFID II regulations."
                                                     " Set to 'True' if the transaction reduces risk in an objectively"
                                                     " measurable way in accordance with the MiFID II regulation. "
                                                     "Otherwise 'False'.",
                                                     bool, mandatory="always", default=False)

    @classmethod
    def get_attribute_groups(cls):
        groups = super(MifidTemplate, cls).get_attribute_groups()
        groups.append({"caption": "MIFID settings",
                       "description": "Defaults for the MiFID II fields for all orders placed by this algorithm "
                                      "(Can be overridden by individual synthetic orders)",
                       "config_fields": ["mifid_decision_maker", "mifid_execution_maker",
                                         "mifid_liquidity_provision", "mifid_dea",
                                         "mifid_dea_client_id", "mifid_trading_capacity",
                                         "mifid_derivative_indicator"]})
        return groups
