# Functions in this module are for internal autotrader usage
# and should not be used in the customer's code directly
import base64
import datetime
import logging
import pprint
import shutil
import tempfile
import time
import uuid
import zipfile

import six
from six.moves import range

import autotrader_lib.common as COMMON
from autotrader_lib import util as ALU

log = logging.getLogger("autotrader_lib.strategy_managing")

# We use Deciseconds as timeout, while REST_API_TIMEOUT is in seconds.
# We add 0.1 seconds to the timeout, to make sure we only report the
# timeout after the Autotrader has really timed out.
DEFAULT_TIMEOUT = COMMON.REST_API_TIMEOUT * 10 + 1


class StrategyManagingTimeout(Exception):
    """ Class for timeouts on messages sent to autoTRADER and expected to be acted upon by strategies """
    pass


class StrategyManagingException(Exception):
    """ Class for exception on messages sent to autoTRADER's strategies """
    pass


class StrategyMissingException(Exception):
    """ Class for exception on messages sent to non-existent strategies """
    pass


class BadInput(TypeError):
    """Raised if the request content does not follow the requested format (e.g. has wrong types)"""
    pass


class EmptyInput(ValueError):
    """Raised if a Post-request expects some content, but no understandable content was sent"""
    pass


def _raise_if_strategy_does_not_exist(database, strategy_id):
    """
    Check if a strategy with id strategy_id exist in the database and raise a StrategyMissingException otherwise

    :type database: pymongo.database.Database
    :type strategy_id: str
    :raises: StrategyMissingException
    """
    strategy_object = database.strategies.find_one({
        "object_type": {"$in": [COMMON.MongoDBObjects.strategy, COMMON.MongoDBObjects.strategy_configuration]},
        "internal_number": strategy_id})
    if not strategy_object:
        raise StrategyMissingException(u"The strategy '{}' does not exist.".format(strategy_id))


def strategy_steering(database, strategy_id, payload, halt_or_resume=False):
    """
    Steering a custom strategy by sending payload.
    The strategy will receive payload in the on_strategy_update function, and react accordingly

    :param database: mongo client object
    :type database: pymongo.database.Database
    :param strategy_id: ID of a strategy to steer
    :type strategy_id: str
    :param payload: strategy payload
    :type payload: dict[atr, any]
    :param halt_or_resume: denotes if steering call comes as a strategy halt or strategy resume request
    :type halt_or_resume: bool
    :return: The found mongo entry's result field
    :rtype: dict[str, str]
    """

    if not strategy_id:
        raise BadInput("stategy_id can't be empty in the steering call")
    if not payload:
        raise BadInput("payload can't be empty in the steering call")
    # check if the strategy object exists - if not, an error is raised
    _raise_if_strategy_does_not_exist(database, strategy_id)
    # initiate the send-receive cycle for the steering call
    query = send_document_to_mongo(database,
                                   COMMON.MongoDBObjects.strategy_steering,
                                   internal_number=strategy_id,
                                   payload=payload,
                                   halt_or_resume=halt_or_resume)
    result, _ = recv_response_from_db(query, database)
    return result


def synthetic_order(database, strategy_id, payload):
    # check if the strategy object exists - if not, an error is raised
    _raise_if_strategy_does_not_exist(database, strategy_id)

    query = send_document_to_mongo(database,
                                   object_type=COMMON.MongoDBObjects.synthetic_order,
                                   internal_number=strategy_id,
                                   payload=payload)
    result, _ = recv_response_from_db(query, database)
    return result


def limit_management(database, strategy_id, payload, login_name, overwrite_limits=False):
    """
    Send a (partial) update to the per-product limits to a strategy.

    :param database: The MongoDB instance
    :type database: pymongo.database.Database
    :param strategy_id: The id of the strategy for which to set limits.
    :type strategy_id: str
    :param payload: A dictionary describing the limit changes to be applied
    :type payload: dict
    :param login_name: The name of the user issuing the limit chnage. Used for compliance logging
    :type login_name: six.string_types
    :param overwrite_limits: flag telling if limits need to be overwritten
    :type overwrite_limits: bool
    :return: A dictionary describing the limits after the change has been applied by the strategy.
             This is returned from the strategy through MongoDB.
             It is returned here to get immediate feedback without the delay the Mongo WriterThread would introduce
             for the actual LimitObject.
    :rtype: dict
    """

    if not strategy_id:
        raise BadInput("stategy_id can't be empty in limits call")
    if not payload:
        raise BadInput("payload can't be empty in limits call")
    # check if the strategy object exists - if not, an error is raised
    _raise_if_strategy_does_not_exist(database, strategy_id)

    sanitized_payload = {"limits_per_sequence": {},
                         "limits_per_sequence_item": {},
                         "user_login": login_name}
    # Validate payload:
    for limit_type in ["limits_per_sequence", "limits_per_sequence_item"]:
        for limit_name, limits_per_type in payload.get(limit_type, {}).items():
            if limit_name not in COMMON.PerProductLimits.supported_limits:
                raise BadInput(
                    "Limit_name must be one of {}, found {!r}.".format(
                        ", ".join(COMMON.PerProductLimits.supported_limits), limit_name))
            if not isinstance(limits_per_type, dict):
                raise BadInput(
                    "Value of limit {} for limit type {} must be a dictionary, found: {!r} of type: {})".format(
                        limit_name, limit_type, limits_per_type, type(limits_per_type).__name__))
            for product_identifier, value in limits_per_type.items():
                if limit_type == "limits_per_sequence":
                    if not isinstance(product_identifier, (six.string_types, int)):
                        raise BadInput(
                            "sequence_ids must be string or int, found: {!r} of type: {}".format(
                                product_identifier, type(product_identifier).__name__))
                elif limit_type == "limits_per_sequence_item" and not isinstance(product_identifier, six.string_types):
                    raise BadInput(
                        "sequence_item_ids must be string, found: {!r} of type: {}".format(
                            product_identifier, type(product_identifier).__name__))
                if not isinstance(value, (float, int)):
                    raise BadInput(
                        "limits must be float or int, found {!r} of type {} for {}[{!r}][{!r}]".format(
                            value, type(limit_name).__name__, limit_type, limit_name, product_identifier))
                if limit_name not in sanitized_payload[limit_type]:
                    sanitized_payload[limit_type][limit_name] = {}
                sanitized_payload[limit_type][limit_name][product_identifier] = value
    if not overwrite_limits and not any(sanitized_payload["limits_per_sequence"].values()) and not any(
            sanitized_payload["limits_per_sequence_item"].values()):
        raise EmptyInput
    query = send_document_to_mongo(database, COMMON.MongoDBObjects.per_product_limits, strategy_id, sanitized_payload,
                                   overwrite_limits=overwrite_limits)
    # Wait until the request has been processed by the strategy or a timeout occurs.
    recv_response_from_db(query, database)
    # Return the updated limits.
    return database.strategies.find_one({"_id": "ProductLimits.{}".format(strategy_id)})


def send_document_to_mongo(database, object_type, internal_number, payload, overwrite_limits=False,
                           halt_or_resume=False, manual_message_hash=None):
    """
    Create a document in mongo-db.
    Autotrader_core_main_child will then extend this document by a "response" field.

    :param database: The mongo database object
    :type database: pymongo.database.Database
    :param object_type: The object type for the document that will be put into mongo db.
                        One of StrategySteeringObject and DumpStrategyRequest
    :type object_type: str
    :param internal_number: The strategy_id of the strategy this request refers to.
                            Should be in the portfolio.
    :type internal_number: str
    :param payload: A dictionary containing additional payload.
    :param overwrite_limits: flag telling if limits need to be overwritten
    :type overwrite_limits: bool
    :param halt_or_resume: flag telling if steering call should be treated as a strategy halt/resume request
    :type halt_or_resume: bool
    :param manual_message_hash: instead of generating a hash in here, it is given by this parameter (used for testing)
    :type manual_message_hash: str
    :return: A query that can be used to retrieve the created document from mongo db.
    :rtype: dict[str, str]
    """

    message_hash = manual_message_hash if manual_message_hash else str(uuid.uuid4())
    _id = "{obj_type}_{internal_number}_{message_hash}".format(obj_type=object_type,
                                                               internal_number=internal_number,
                                                               message_hash=message_hash)
    message = {
        "_id": _id,
        "alteration_time": datetime.datetime.utcfromtimestamp(time.time()),
        "object_type": object_type,
        "payload": payload,
        "request_hash": message_hash,
        "internal_number": internal_number,
        "overwrite_limits": overwrite_limits,
        "halt_or_resume": halt_or_resume
    }
    log.debug("Sending document %s to database", pprint.pformat(message, depth=1, width=10E10))
    # here "insert_one" can't be used, only "update_one", because $currentDate is an update operator
    try:
        database.strategies.update_one({"_id": _id}, {"$set": message,
                                                      "$currentDate": {"insertion_time": True}}, upsert=True)
    except OverflowError as err:
        if "can only handle up to 8-byte ints" in str(err):
            raise BadInput("Integers longer than 8 bytes are not supported in the payload.")
        else:
            raise BadInput("The payload contains too large values!")

    query = {"_id": _id}
    return query


def recv_response_from_db(query, database, timeout=DEFAULT_TIMEOUT):
    """
    Query the database for an entry and return the entry's "result" field.

    :param query: A query for mongo-db (will be passed to find_one)
    :type query: dict
    :param database: A database opened with _db_connect
    :type database: pymongo.database.Database
    :param timeout: How many deciseconds to wait.
    :type timeout: int
    :raises: RuntimeError on Error or on timeout.
    :return: The found entry's result field
    """

    result = None
    log.debug("Querying database for result of query %s", query)
    if timeout < 1:
        timeout = 1  # At least query once
    for time_used in range(timeout):
        document = database.strategies.find_one(query)
        result = document.get("response", None)
        if result is None:
            time.sleep(.1)
        else:
            log.debug('Received response: """%s"""', pprint.pformat(result, width=10E10, depth=2))
            break
    else:
        log.error("AutoTrader did not provide result field to object queried with %s."
                  "This indicates an error in AutoTrader or a too short "
                  "timeout of %s seconds.", query, 0.1 * timeout)
        msg = "Timeout!"
        if document.get("object_type") in [COMMON.MongoDBObjects.strategy_steering,
                                           COMMON.MongoDBObjects.per_product_limits]:
            msg += " Please check if AutoTrader has processed your request."
        raise StrategyManagingTimeout(msg)

    if isinstance(result, six.string_types) and result.startswith("ERROR"):
        raise StrategyManagingException("Your request caused an exception.")

    return result, time_used


def unzip_custom_package(package, into_dir):
    """
    Unzips a custom strategy from the MongoDB document into the given directory.

    :param package: The base64 encoded content of the zip file
    :type package: str
    :param into_dir: The directory where the unzipped file will be copied to in the end.
    :type into_dir: str
    """
    # extract the zip into a temporary folder
    temporary_strategy_dir = tempfile.mkdtemp()
    package_raw = base64.b64decode(package)
    zip_io = six.BytesIO(package_raw)
    with zipfile.ZipFile(zip_io) as zip_object:
        zip_object.extractall(temporary_strategy_dir)
    zip_io.close()

    # copy the temporary files into the right path and clear the temporary folder
    # it still possible to get collisions at this point when trying to update the file
    # such collisions should be rare and putting another backoff mechanism would be an overkill
    # if the need arises later it would be easy to add it here later
    ALU.copy_full_tree(temporary_strategy_dir, into_dir)
    shutil.rmtree(temporary_strategy_dir)
