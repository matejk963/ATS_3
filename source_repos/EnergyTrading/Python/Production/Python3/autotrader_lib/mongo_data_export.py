import datetime
import collections
import csv
import logging

import six

import autotrader_lib.common as COMMON
import autotrader_lib.util as UTIL
from six.moves import zip

logger = logging.getLogger("mongo_data_export")

# Possible delimiters. The first element is the default one
DELIMITERS = ",;\t |"

# Possible decimal delimiters. The first element is the default one
DECIMAL_DELIMITERS = ".,"

DB_QUERY_LIMIT = 200000


class StrategyNotFoundException(ValueError):
    """
    Raised when a strategy with specified internal number not found in mongo
    """
    pass


class MongoQueryLimitException(RuntimeError):
    """
    Raised when MongoDB query limit is breached
    """
    pass


def export_market_data(database, exchange_id, trade_type,
                       group_by_product_id=False,
                       delivery_start=None,
                       delivery_end=None,
                       filename=None,
                       delimiter=DELIMITERS[0],
                       decimal_delimiter=DECIMAL_DELIMITERS[0]):
    """
    Function to export back-testing market data to a csv file.

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :param group_by_product_id: flag telling whether results should be grouped by product_id.
                                This is mostly used to separate local and XBID products on EPEX.
                                When False grouping by time period will be used.
                                Exclusive to time period: delivery_start and delivery_end
    :type group_by_product_id: bool
    :param delivery_start: start of delivery. Exclusive to group_by_product_id
    :type delivery_start: date string
    :param delivery_end: end of delivery. Exclusive to group_by_product_id
    :type delivery_end: date string
    :param filename: name of the file to export to
    :type filename: str
    :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
    :type delimiter: str
    :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                              Possible values are in DECIMAL_DELIMITERS
    :type decimal_delimiter: str
    :return: Number of exported records (lines)
    :rtype: int
    """

    _validate_csv_parameters(decimal_delimiter, delimiter, filename)

    data = get_market_info(database=database, exchange_id=exchange_id, trade_type=trade_type,
                           group_by_product_id=group_by_product_id,
                           delivery_start=delivery_start, delivery_end=delivery_end)

    csv_columns = _get_csv_headers(data,
                                   sort_function=lambda field: "{}_{}".format(field.split("_")[-1], field))
    data = write_to_csv_file(data, decimal_delimiter, delimiter, filename,
                             csv_columns)

    logger.info("Exported {} records to {}".format(len(data), filename))
    return len(data)


def write_to_csv_file(data, decimal_delimiter, delimiter, filename, csv_columns):
    """
    Write the data to a file in csv format.

    :param data: A list of dicts, each dict corresponding to one row
    :type data: list[dict]
    :param decimal_delimiter: The decimal delimiter for numbers
    :type decimal_delimiter: str
    :param delimiter: The field delimiter
    :type delimiter: str
    :param filename: The absolute path of the file to write to
    :type filename: string
    :param csv_columns: A list of columns, which are used as header and as dictionary keys for the dicts in data
    :type csv_columns: list[string] if python 2, list[bytes] if python3
    """
    writemode = "wb" if six.PY2 else "w"
    with open(filename, writemode) as fn:
        if len(data) > 0:
            writer = csv.DictWriter(fn, fieldnames=csv_columns, delimiter=delimiter, extrasaction="ignore")
            writer.writeheader()
            if decimal_delimiter != DECIMAL_DELIMITERS[0]:
                data = [_replace_decimal_delimiter(entry, decimal_delimiter) for entry in data]
            writer.writerows(data)
        else:
            if not csv_columns:
                csv_columns = ["exchange", "delivery_start", "delivery_end"]
            writer = csv.DictWriter(fn, fieldnames=csv_columns, delimiter=delimiter)
            writer.writeheader()
    return data


def _get_csv_headers(data, sort_function):
    """
    Extract the union of keys from the data, and performs filtering and sorting

    Private keys (starting with "_" and keys mapping to collections are removed from the result.
    The result is sorted as follows: The first 4 keys are always (if present) "exchange",
    "product_id", "delivery_start", "delivery_end". The remaining keys are sorted using the sort_function.

    :param data: A list of records (dicts)
    :type data: list(dict)
    :param sort_function: A function for sorting the keys.
    :type sort_function: callable
    :return: A list of keys, in a well defined sort order.
    :rtype: list(string)
    """
    csv_columns = []
    # As different records may have different keys, we have to iterate over all records to get the union of keys.
    # Additionally, we filter out private keys and keys that map to collections
    data_fields = []
    for record in data:
        for key in record.keys():
            if key not in data_fields and not key.startswith("_") \
                    and not isinstance(record[key], (list, dict)):
                data_fields.append(key)
    # Always start with the exchange and product information
    leading_fields = ["exchange", "product_id", "delivery_start", "delivery_end"]
    for field_name in leading_fields:
        if field_name in data_fields:
            csv_columns.append(field_name)
            data_fields.remove(field_name)
    # After the product information, add the remaining fields in a sorted way
    csv_columns.extend(sorted(data_fields, key=sort_function))
    return csv_columns


def _validate_csv_parameters(decimal_delimiter, delimiter, filename):
    """
    Check that the parameters "decimal_delimiter", "delimiter" and "filename" are given and valid.

    Raises a ValueError, if validation fails.
    :param decimal_delimiter: A single character used as decimal delimiter
    :type decimal_delimiter: char
    :param delimiter:  A single character used as delimiter between the fields in the csv
    :type delimiter: char
    :param filename: The absolute path of the output file
    :type filename: string
    """
    if delimiter not in DELIMITERS:
        raise ValueError("Delimiter must be one of {}."
                         " '{}' is specified".format(repr(DELIMITERS), delimiter))
    if decimal_delimiter not in DECIMAL_DELIMITERS:
        raise ValueError("Decimal delimiter must be one of {}."
                         " '{}' is specified".format(repr(DECIMAL_DELIMITERS), decimal_delimiter))
    if delimiter == decimal_delimiter:
        raise ValueError("Parameters delimiter = '{}' and decimal_delimiter = '{}'"
                         "cannot be the same".format(delimiter, decimal_delimiter))
    if not filename:
        raise ValueError("Filename is not specified")


def get_market_info(database, exchange_id, trade_type,
                    group_by_product_id=False,
                    delivery_start=None,
                    delivery_end=None):
    """
    Function to calculate and retrieve market data.

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :param group_by_product_id: flag telling whether results should be grouped by product_id.
                                This is mostly used to separate local and XBID products on EPEX.
                                When False grouping by time period will be used.
                                Exclusive to time period: delivery_start and delivery_end
    :type group_by_product_id: bool
    :param delivery_start: start of delivery. Exclusive to group_by_product_id
    :type delivery_start: date string
    :param delivery_end: end of delivery. Exclusive to group_by_product_id
    :type delivery_end: date string
    :return: list of entries to a csv file, or None if mutually exclusive parameters are specified
    :rtype: list[dict]
    """

    if group_by_product_id and (delivery_start or delivery_end):
        logger.error("Time period restriction (delivery_start and/or delivery_end) "
                     "and group_by_product_id are mutually exclusive")
        return None

    if delivery_start:
        delivery_start = UTIL.convert_datestring(delivery_start)

    if delivery_end:
        delivery_end = UTIL.convert_datestring(delivery_end)

    return _group_by_product_id(database, exchange_id, trade_type) if group_by_product_id else \
        _group_by_delivery_period(database, exchange_id, trade_type, delivery_start, delivery_end)


def _replace_decimal_delimiter(entry, decimal_delimiter):
    """
    Helper function for replacing decimal delimiter in float numbers

    :param entry: csv line where float numbers should be changed
    :type entry: dict
    :param decimal_delimiter: new decimal delimiter to be replaced with
    :type decimal_delimiter: str
    :return: dictionary identical to entry with replaced decimal delimiters
    :rtype: dict
    """

    result = {}
    for key in entry:
        if type(entry[key]) == float:
            result[key] = str(entry[key]).replace(".", decimal_delimiter)
        else:
            result[key] = entry[key]

    return result


def _group_by_product_id(database, exchange_id, trade_type):
    """
    Helper function to retrieve trades grouped by delivery_area and product_id

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :return: list of trades
    :rtype: list[dict]
    """

    aggr_trades = _aggregate_trades_per_product_id(database=database,
                                                   exchange_id=exchange_id,
                                                   trade_type=trade_type)

    info_per_delivery_period = collections.defaultdict(lambda: collections.defaultdict(list))

    for aggr_group in aggr_trades:
        aggr_group_regions = UTIL.get_regions(sell_delivery_area=aggr_group["sell_delivery_area"],
                                              buy_delivery_area=aggr_group["buy_delivery_area"],
                                              exchange_id=exchange_id)
        for curr_region in aggr_group_regions:
            curr_group_by = (aggr_group["product_id"], curr_region)
            info_per_delivery_period[curr_group_by]["quantities"].extend(aggr_group["quantities"])
            info_per_delivery_period[curr_group_by]["prices"].extend(aggr_group["prices"])
            info_per_delivery_period[curr_group_by]["execution_times"].extend(aggr_group["execution_times"])

    full_stats_per_delivery_period = collections.defaultdict(dict)
    for (curr_product_id, curr_region), bucket_info in info_per_delivery_period.items():
        region_stats = _compute_stats_per_region(bucket_info=bucket_info, region=curr_region, trade_type=trade_type)
        full_stats_per_delivery_period[curr_product_id].update(region_stats)

    result = list()
    for product_id, stats in full_stats_per_delivery_period.items():
        current_result = dict(exchange=exchange_id, product_id=product_id, **stats)
        result.append(current_result)

    return result


def _group_by_delivery_period(database, exchange_id, trade_type, delivery_start, delivery_end):
    """
    Helper function to retrieve trades grouped by delivery_area and delivery intervals.

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :param delivery_start: start of delivery
    :type delivery_start: datetime.datetime
    :param delivery_end: end of delivery
    :type delivery_end: datetime.datetime
    :return: list of trades
    :rtype: list[dict]
    """

    aggr_trades = _aggregate_trades_per_time_period(database=database,
                                                    exchange_id=exchange_id,
                                                    trade_type=trade_type,
                                                    delivery_start=delivery_start,
                                                    delivery_end=delivery_end)

    info_per_delivery_period = collections.defaultdict(lambda: collections.defaultdict(list))

    # each group will produce a unique combination of delivery_{start,end}, {buy,sell}_delivery_area
    # such a group in turn produces a unique set of regions from 2 to 4 regions.
    # however, the same region can appear in a different set of regions while in the same delivery period
    # therefore we need to reaggregate them in regions within time periods
    for aggr_group in aggr_trades:
        aggr_group_regions = UTIL.get_regions(sell_delivery_area=aggr_group["sell_delivery_area"],
                                              buy_delivery_area=aggr_group["buy_delivery_area"],
                                              exchange_id=exchange_id)
        for curr_region in aggr_group_regions:
            curr_group_by = (aggr_group["delivery_start"], aggr_group["delivery_end"], curr_region)
            info_per_delivery_period[curr_group_by]["quantities"].extend(aggr_group["quantities"])
            info_per_delivery_period[curr_group_by]["prices"].extend(aggr_group["prices"])
            info_per_delivery_period[curr_group_by]["execution_times"].extend(aggr_group["execution_times"])

    # once we have buckets with unique time period and region we can compute the stats for each such bucket
    # and then aggregate them into time periods with all the regions in each time period
    full_stats_per_delivery_period = collections.defaultdict(dict)
    for (curr_delivery_start, curr_delivery_end, curr_region), bucket_info in info_per_delivery_period.items():
        region_stats = _compute_stats_per_region(bucket_info=bucket_info, region=curr_region, trade_type=trade_type)
        full_stats_per_delivery_period[(curr_delivery_start, curr_delivery_end)].update(region_stats)

    result = list()
    for (delivery_start, delivery_end), stats in full_stats_per_delivery_period.items():
        current_result = dict(exchange=exchange_id, delivery_start=delivery_start, delivery_end=delivery_end, **stats)
        result.append(current_result)

    return result


def _compute_stats_per_region(bucket_info, region, trade_type):
    """
    Helper function for computing stats for a group within a region

    :param bucket_info: bucket info
    :type bucket_info: collections.defaultdict
    :param region: region (delivery_area)
    :type region: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :return: statistics for the region. If quantities_sum is 0, an empty dict will be returned
    :rtype: dict
    """

    region_stats = dict()
    quantities_sum = sum(bucket_info["quantities"])
    if quantities_sum > 0:
        max_price = max(bucket_info["prices"])
        min_price = min(bucket_info["prices"])
        last_trade_index = bucket_info["execution_times"].index(max(bucket_info["execution_times"]))
        last_price = bucket_info["prices"][last_trade_index]
        last_quantity = bucket_info["quantities"][last_trade_index]
        last_trade_time = bucket_info["execution_times"][last_trade_index]

        weighted_quantities = sum([price * quantity for price, quantity in zip(bucket_info["prices"],
                                                                               bucket_info["quantities"])])
        trade_type_str = "own" if trade_type == "OwnTrade" else "pub"
        region_stats["high_price_{}".format(region)] = max_price
        region_stats["low_price_{}".format(region)] = min_price
        region_stats["traded_volume_{}_{}".format(trade_type_str, region)] = quantities_sum
        region_stats["vwap_{}_{}".format(trade_type_str, region)] = round(weighted_quantities / quantities_sum, 2)
        region_stats["last_price_{}".format(region)] = last_price
        region_stats["last_quantity_{}".format(region)] = last_quantity
        region_stats["last_trade_time_{}".format(region)] = last_trade_time

    return region_stats


def _aggregate_trades_per_time_period(database, exchange_id, trade_type, delivery_start=None, delivery_end=None):
    """
    Helper function for aggregating trades based on delivery areas and delivery intervals

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :param delivery_start: start of delivery.
                           Trades with start >= delivery_start will be included to results
    :type delivery_start: datetime.datetime
    :param delivery_end: end of delivery.
                         Trades with end <= delivery_start will be included to results
    :type delivery_end: datetime.datetime
    :return: cursor object for mongo db
    :rtype: pymongo.command_cursor.CommandCursor
    """
    match_query = dict(object_type=trade_type,
                       exchange=exchange_id)
    if delivery_start:
        match_query["delivery_start"] = {"$gte": delivery_start}
    if delivery_end:
        match_query["delivery_end"] = {"$lte": delivery_end}

    group_query = {"_id": {"delivery_start": "$delivery_start",
                           "delivery_end": "$delivery_end",
                           "buy_delivery_area": "$buy_delivery_area",
                           "sell_delivery_area": "$sell_delivery_area"},
                   "execution_times": {"$push": "$execution_time"},
                   "prices": {"$push": "$price"},
                   "quantities": {"$push": "$quantity"}}

    project_query = {"delivery_start": "$_id.delivery_start",
                     "delivery_end": "$_id.delivery_end",
                     "buy_delivery_area": "$_id.buy_delivery_area",
                     "sell_delivery_area": "$_id.sell_delivery_area",
                     "quantities": "$quantities",
                     "prices": "$prices",
                     "execution_times": "$execution_times",
                     "_id": 0}

    return database.state.aggregate([{"$match": match_query}, {"$group": group_query}, {"$project": project_query}])


def _aggregate_trades_per_product_id(database, exchange_id, trade_type):
    """
    Helper function for aggregating trades based on delivery areas and product_id

    :param database: a mongo client object used to retrieve info from the connected db
    :type database: pymongo.database.Database
    :exchange_id: exchange ID
    :type exchange_id: str
    :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    :type trade_type: str
    :return: cursor object for mongo db
    :rtype: pymongo.command_cursor.CommandCursor
    """

    match_query = dict(object_type=trade_type,
                       exchange=exchange_id)

    group_query = {"_id": {"product_id": "$product_id",
                           "buy_delivery_area": "$buy_delivery_area",
                           "sell_delivery_area": "$sell_delivery_area"},
                   "execution_times": {"$push": "$execution_time"},
                   "prices": {"$push": "$price"},
                   "quantities": {"$push": "$quantity"}}

    project_query = {"product_id": "$_id.product_id",
                     "buy_delivery_area": "$_id.buy_delivery_area",
                     "sell_delivery_area": "$_id.sell_delivery_area",
                     "quantities": "$quantities",
                     "prices": "$prices",
                     "execution_times": "$execution_times",
                     "_id": 0}

    return database.state.aggregate([{"$match": match_query}, {"$group": group_query}, {"$project": project_query}])


def to_boolean(text):
    """
    Helper function to convert str to bool

    :param text: Text to convert
    :type text: str
    :returns: boolean value of text
    :rtype: bool
    """
    if isinstance(text, bool):
        return text
    elif text.lower() in ["true", "false"]:
        return text.lower() == "true"
    raise ValueError("The parameter text was: '{}' and should be true or false.".format(text))


def to_int(value):
    """ Convert the value into an integer if the value has type str or int
    :param value: the data to cast into an integer
    :type value: any
    :return the value as an integer
    :rtype int
    :raise ValueError if the value is not castable to integer
    """
    # here we do not use isinstance because bool is a subclass of int!
    if type(value) in (int, six.text_type, str):
        return int(value)
    raise ValueError("Unsupported type {!r} with value {!r}!".format(type(value), value))


def to_float(value):
    """
    Convert the value into a float if the value does not have type boolean
    :param value: the data to cast into a float
    :type value: any
    :return the value as a float
    :rtype int
    :raise ValueError if the value is not castable to float
    """
    if not isinstance(value, bool):
        return float(value)
    raise ValueError("Unsupported type {!r} with value {!r}!".format(type(value), value))


def to_number(value):
    """
    Convert the value into an integer or float if the value has type str.
    Return it as is, if it has type int or float

    :param value: the data to cast into an int or float
    :type value: any
    :return the value as an int or float, depending on the format of the string
    :rtype int/float
    :raise ValueError if the value is not castable to integer or float
    """
    if type(value) in (int, float):
        return value
    if type(value) not in (six.text_type, str):
        # we only support conversion from str/unicode,
        # otherwise we can't do anything (int and float are already handled above)
        raise ValueError("Unsupported type {!r} with value {!r}!".format(type(value), value))

    # probably trying to pass a float
    if "." in value:
        try:
            return float(value)
        except ValueError:
            # wasn't castable to float, therefore isn't castable to int, can't handle it
            raise ValueError("Unsupported type {!r} with value {!r}!".format(type(value), value))

    # no '.', therefore probably trying to pass an int
    try:
        return int(value)
    except ValueError:
        # not a float, but also not castable to int, therefore isn't castable to int, can't handle it
        raise ValueError("Unsupported type {!r} with value {!r}!".format(type(value), value))


def _get_trades_query(trade_type, exchange_id=None, internal=None, portfolios=None, root=False):
    """
    Helper function to get query to mongo db for trades

    :param trade_type: trade type. Can be either "OwnTrade" or "PublicTrade"
    :type trade_type: str
    :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param internal: internal flag
    :type internal: bool
    :param portfolios: list of Portfolios
    :type portfolios: list[str]
    :param root: flag telling is a user the root
    :type root: bool
    :returns: query to mongo db
    :rtype: dict[str->any]
    """
    query = {"object_type": trade_type}
    if not root and portfolios is not None:
        query["trading_portfolio"] = {"$in": portfolios}

    if exchange_id is not None:
        query["exchange"] = exchange_id

    if internal is not None:
        query["internal"] = to_boolean(internal)
    return query


def get_trade_cursor(database, trade_type, exchange_id=None, area_id=None, product_ids=None, trade_ids=None,
                     internal=None, portfolios=None, execution_until=None, execution_after=None, root=False):
    """
    Helper function to get db cursor for fetched data

    :param database: The database to perform the trade query on
    :type database: pymongo.database.Database
    :param trade_type: trade type. Can be either "OwnTrade" or "PublicTrade"
    :type trade_type: str
    :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param area_id: are ID. The return result will contain only records with this ID
    :type area_id: str
    :param product_ids: list of product IDs. The return result will contain only records with these IDs
    :type product_ids: list[str]
    :param trade_ids: list of trade IDs. The return result will contain only records with these IDs
    :type trade_ids: list[str]
    :param internal: internal flag
    :type internal: bool
    :param portfolios: list of Portfolios
    :type portfolios: list[str]
    :param execution_until: filter trades that are executed until the given datetime.
                            Can be used only with execution_after
    :type execution_until: datetime.datetime
    :param execution_after: filter trades that are executed after the given datetime.
    :type execution_after: datetime.datetime
    :param root: flag telling is a user the root
    :type root: bool
    :returns: cursor to mongo db for fetched data
    :rtype: pymongo.cursor.Cursor

    """

    query = _get_trades_query(trade_type=trade_type,
                              internal=internal,
                              exchange_id=exchange_id,
                              portfolios=portfolios,
                              root=root)

    if product_ids is not None:
        if isinstance(product_ids, str):
            query["product_id"] = product_ids
        elif isinstance(product_ids, list) and len(product_ids) > 0:
            query["product_id"] = {"$in": product_ids}

    if trade_ids is not None:
        if isinstance(trade_ids, str):
            query["trade_id"] = trade_ids
        elif isinstance(trade_ids, list) and len(trade_ids) > 0:
            query["trade_id"] = {"$in": trade_ids}

    if area_id is not None:
        query["$or"] = [{"buy_delivery_area": area_id}, {"sell_delivery_area": area_id}]

    if execution_after is None and execution_until is not None:
        raise ValueError("execution_after is not given")
    elif execution_after is None and execution_until is None:
        query["execution_time"] = {"$gt": datetime.datetime.utcnow() - datetime.timedelta(hours=72)}
    elif execution_until is not None and execution_after is not None:
        query["execution_time"] = {"$lte": execution_until, "$gt": execution_after}
    elif execution_after is not None:
        query["execution_time"] = {"$gt": execution_after}

    if trade_type == "OwnTrade":
        return database.own_trades.find(query)
    elif trade_type == "PublicTrade":
        return database.state.find(query)


def get_own_trades(database, exchange_id=None, area_id=None, product_ids=None, trade_ids=None, internal=None,
                   portfolios=None, execution_until=None, execution_after=None):
    """
    Function to get list of Own Trades

    :param database: The database to perform the trade query on
    :type database: pymongo.database.Database
    :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param area_id: are ID. The return result will contain only records with this ID
    :type area_id: str
    :param product_ids: list of product IDs. The return result will contain only records with these IDs
    :type product_ids: list[str]
    :param trade_ids: list of trade IDs. The return result will contain only records with these IDs
    :type trade_ids: list[str]
    :param internal: internal flag
    :type internal: bool
    :param portfolios: list of Portfolios
    :type portfolios: list[str]
    :param execution_until: filter trades that are executed until the given datetime.
                            Can be used only with execution_after
    :type execution_until: datetime.datetime
    :param execution_after: filter trades that are executed after the given datetime.
    :type execution_after: datetime.datetime
    :returns: list of Own Trades
    :rtype: list[dict[str->any]]
    """

    trade_type = "OwnTrade"

    trades = list(get_trade_cursor(database=database, trade_type=trade_type, exchange_id=exchange_id,
                                   area_id=area_id, product_ids=product_ids, trade_ids=trade_ids, internal=internal,
                                   portfolios=portfolios, execution_until=execution_until,
                                   execution_after=execution_after).limit(DB_QUERY_LIMIT))

    if len(trades) >= DB_QUERY_LIMIT:
        raise RuntimeError("Too many records (more than {})".format(DB_QUERY_LIMIT))

    return trades


def get_public_trades(database, exchange_id=None, area_id=None, product_ids=None, trade_ids=None,
                      execution_until=None, execution_after=None):
    """
    Function to get list of Public Trades

    :param database: The database to perform the trade query on
    :type database: pymongo.database.Database
    :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param area_id: are ID. The return result will contain only records with this ID
    :type area_id: str
    :param product_ids: list of product IDs. The return result will contain only records with these IDs
    :type product_ids: list[str]
    :param trade_ids: list of trade IDs. The return result will contain only records with these IDs
    :type trade_ids: list[str]
    :param execution_until: filter trades that are executed until the given datetime.
                            Can be used only with execution_after
    :type execution_until: datetime.datetime
    :param execution_after: filter trades that are executed after the given datetime.
    :type execution_after: datetime.datetime
    :returns: list of Public Trades
    :rtype: list[dict[str->any]]
    """

    trade_type = "PublicTrade"

    trades = list(get_trade_cursor(database=database, trade_type=trade_type, exchange_id=exchange_id,
                                   area_id=area_id, product_ids=product_ids, trade_ids=trade_ids,
                                   execution_until=execution_until,
                                   execution_after=execution_after).limit(DB_QUERY_LIMIT))

    if len(trades) >= DB_QUERY_LIMIT:
        raise RuntimeError("Too many records (more than {})".format(DB_QUERY_LIMIT))

    return trades


def export_trades(database, exchange_id=None, trade_type="OwnTrade", area_id=None, product_ids=None,
                  trade_ids=None, execution_until=None, execution_after=None, internal=None,
                  filename=None, delimiter=DELIMITERS[0], decimal_delimiter=DECIMAL_DELIMITERS[0],
                  columns=None):
    """
    Query trades and export them to a csv file.

    :param database: The database to perform the trade query on
    :type database: pymongo.database.Database
    :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
    :type exchange_id: str
    :param trade_type: One of "OwnTrade" and "PublicTrade"
    :type trade_type: str
    :param area_id: are ID. The return result will contain only records with this ID
    :type area_id: str
    :param product_ids: list of product IDs. The return result will contain only records with these IDs
    :type product_ids: list[str]
    :param trade_ids: list of trade IDs. The return result will contain only records with these IDs
    :type trade_ids: list[str]
    :param execution_until: filter trades that are executed until the given datetime.
                            Can be used only with execution_after
    :type execution_until: datetime.datetime
    :param execution_after: filter trades that are executed after the given datetime.
    :type execution_after: datetime.datetime
    :param internal: Only applies when trade_type is OwnTrade.
                     When given, limit trades to internal trades (if True) or exchange trades (if False).
    :type internal: bool or None
    :param filename: Absolute path of the file to export to
    :type filename: str
    :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
    :type delimiter: str
    :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                              Possible values are in DECIMAL_DELIMITERS
    :type decimal_delimiter: str
    :return: Number of exported records (lines)
    :rtype: int
    """

    _validate_csv_parameters(decimal_delimiter, delimiter, filename)

    if trade_type == "OwnTrade":
        trades = get_own_trades(database, exchange_id, area_id, product_ids, trade_ids, internal,
                                execution_until=execution_until,
                                execution_after=execution_after)
    elif trade_type == "PublicTrade":
        trades = get_public_trades(database, exchange_id, area_id, product_ids, trade_ids,
                                   execution_until=execution_until,
                                   execution_after=execution_after)
    else:
        raise ValueError("Wrong trade_type. Choose from 'OwnTrade' and 'PublicTrade', found {}".format(trade_type))

    if columns is None:
        columns = _get_csv_headers(trades,
                                   # Sort price and quantity first (False sorts before True)
                                   sort_function=lambda field: (field != "quantity", field != "price", field))

    data = write_to_csv_file(trades, decimal_delimiter, delimiter, filename,
                             csv_columns=columns)

    logger.info("Exported {} records to {}".format(len(data), filename))
    return len(data)


def get_sequences(database, strategy_id=None):
    """
    Returns sequences which are still tradable (trading_end field of a sequence item is in the future)

    :param database: mongo database object to be used for sequences retrieval
    :type database: `pymongo.database.Database`
    :param strategy_id: strategy internal number for filtering sequences
    :type strategy_id: str or None
    :return: dict with sequences in the format
             {"sequences": [{"sequence_id": <sequence_id>, "sequence_name": <sequence_name>,
                             "sequence_items": [{"sequence_item_id": <sequence_item_id>,
                                                 "sequence_item_name": <sequence_item_name>},
                                                 ...]},
                             ...]
             }
             In case strategy_id is specified, only sequences relevant for this strategy are returned.
    :rtype: dict[str, list]
    """

    sequence_query = {"object_type": "Sequence"}
    result = {"sequences": []}

    if strategy_id:
        market_areas = database.strategies.find_one(
            {"object_type": {"$in": [COMMON.MongoDBObjects.strategy,
                                     COMMON.MongoDBObjects.strategy_configuration]},
             "internal_number": strategy_id,
             "deleted": {"$ne": True}},
            {COMMON.StrategyJsonKey.market_area_1: 1,
             COMMON.StrategyJsonKey.market_area_2: 1,
             COMMON.StrategyJsonKey.market_area_3: 1,
             COMMON.StrategyJsonKey.market_area_4: 1,
             COMMON.StrategyJsonKey.market_area_5: 1})
        # at least "market_area_1" should be always configured for a strategy
        # if this is not the case, it would mean we could not find the strategy
        if not market_areas:
            raise StrategyNotFoundException("Strategy with internal number '{!r}' is not found.".format(strategy_id))

        areas_query = {"object_type": "Area", "inst_id": {"$in": [market_areas[COMMON.StrategyJsonKey.market_area_1]]}}
        for optional_market_area in [COMMON.StrategyJsonKey.market_area_2,
                                     COMMON.StrategyJsonKey.market_area_3,
                                     COMMON.StrategyJsonKey.market_area_4,
                                     COMMON.StrategyJsonKey.market_area_5]:
            if market_areas.get(optional_market_area):
                areas_query["inst_id"]["$in"].append(market_areas[optional_market_area])
            else:
                break

        sequence_ids = []

        for area in list(database.state.find(areas_query).limit(DB_QUERY_LIMIT)):
            sequence_ids.extend(list(area["sequences"]["collection"].keys()))

        sequence_ids = list(set(sequence_ids))
        sequence_query["seq_id"] = {"$in": sequence_ids}

    sequences = list(database.state.find(sequence_query).limit(DB_QUERY_LIMIT))

    if len(sequences) >= DB_QUERY_LIMIT:
        raise MongoQueryLimitException("Too many Sequence records (more than {!r})".format(DB_QUERY_LIMIT))

    now = datetime.datetime.utcnow()
    for seq in sequences:
        seq_dict = {"sequence_id": seq["seq_id"],
                    "sequence_name": seq["seq_name"],
                    "sequence_items": []}
        for seq_item_id, seq_item in seq["collection"].items():
            # we add only those sequence items that are still tradable (trading_end > now)
            if seq_item["trading_end"] > now:
                seq_dict["sequence_items"].append({"sequence_item_id": seq_item["item_id"],
                                                   "sequence_item_name": seq_item["item_name"]})
        result["sequences"].append(seq_dict)

    return result


def get_concurrent_strategies(database):
    """
    Returns list of internal_ids of concurrent algos added via REST API
    :param database: mongo database object used as persistence for aT
    :type database: `pymongo.database.Database`
    :return: list of strategies IDs
    :rtype: list[str]
    """
    query = {"object_type": COMMON.MongoDBObjects.strategy_configuration,
             "deleted": {"$ne": True},
             }
    fields = {"internal_number": 1, "_id": 0}
    strategies_cursor = database.strategies.find(query, fields).limit(DB_QUERY_LIMIT)
    strategy_ids = [strategy["internal_number"] for strategy in strategies_cursor]
    return strategy_ids
