from six.moves import range
# -*- coding: utf-8 -*-

# the DENY_SILENCE is used in fast_logging to check if a compliance log message should not be silenced
# in general, the silence period blocks recurring messages with the same name for a defined amount of time (def: 60 sec)
# add the log_code for which the silence period MUST NOT be used (e.g: strategy changes)
DENY_SILENCE = set(list(range(1, 9)) + list(range(3001, 3009)) + [2002, 2003, 2006, 4004])


def get_own_order_keys(own_order):
    """
    Use this when logging an own order in the compliance log.

    This function extracts all needed fields of an order to unambiguously identify it.
    It should be logged using nesting, e.g.::

        compliance_log((1,"DEBUG", "Example order 1 {order_1[internal_id]}"),
                       order_1=get_own_order_keys(own_order))

    :param own_order: The OwnOrder to log.
    :type own_order: autotrader_core.exchange_trading.OwnOrder
    :return: A dictionary representing the order in a concise but mostly complete way
    :rtype: dict
    """
    return {"id": getattr(own_order, "order_id", None),
            "internal_id": own_order.internal_id,
            "price": own_order.price,
            "quantity": own_order.quantity,
            "broker_id": own_order.broker_id,
            "strategy_id": own_order.portfolio_key,
            "product_id": own_order.product.product_id,
            "product_name": own_order.product.name,
            "delivery_area": own_order.delivery_area_id,
            "slot_type": own_order.tags.get("strategy_slot", "")}


def get_trade_order_keys(trade_order):
    """
    Use this when logging a converted trade order in the compliance log.

    This function extracts all needed fields of an trade order to unambiguously identify it.
    It should be logged using nesting, e.g.::

        compliance_log((1,"DEBUG", "Example order 1 {order_1[internal_id]}"),
                       order_1=get_trade_order_keys(trade_order))

    :param trade_order: The TradeOrder to log.
    :type trade_order: autotrader_core.exchanges.Trayport._TradeOrder
    :return: A dictionary representing the trade order
    :rtype: dict
    """
    return {"id": getattr(trade_order, "order_id", None),
            "internal_id": trade_order.tags.get("internal_id", ""),
            "quantity": trade_order.quantity,
            "strategy_id": trade_order.tags.get("portfolio_key", ""),
            "product_id": trade_order.product_id,
            "slot_type": trade_order.tags.get("strategy_slot", ""),
            "broker_id": trade_order.broker_id,
            "trading_account": trade_order.trading_account}


class AutoTraderBasic(object):
    """
    Any compliance logs are available here, with an error code, a predefined log level and text::

            log_entry_name = (log code, log level, pure text or formattable text)
    """
    autotrader_service_start = (1, "INFO", "Service autoTRADER starting")
    autotrader_service_stop = (2, "INFO", "Service autoTRADER stopping")
    exchange_halted = (3, "INFO", "Exchange '{exchange_name}' was halted by user '{username}' due to"
                                  " reason: '{reason}' and orders were removed: '{remove_orders}'")
    exchange_started = (4, "INFO", "Exchange '{exchange_name}' has been unhalted by user '{username}'")
    autotrader_halted = (5, "INFO", "autoTRADER has halted by user '{username}' due to reason: '{reason}' "
                                    "and orders were removed: '{remove_orders}'")
    initialization_state_change = (6, "INFO", "Initialization state of '{object_name}', "
                                              "has changed from '{old_state}' to '{new_state}'")
    autotrader_started = (7, "INFO", "autoTRADER has been unhalted by user '{username}'")
    exchange_connection_state_change = (8, "INFO", "Connection state of '{exchange_name}' "
                                                   "has changed from '{old_state}' to '{new_state}'")


class TrayportConMgrLogs(object):
    """
    Logs for Trayport do not support keyword arguments for string formatting.
    So, do not use such arguments for text, e.g. "User {user_id} logged in"

    For whatever reason, adding ``**kwargs`` to the .compliance_log() method makes it "dead" (no logs, no reaction)
    Therefore, we have to use ugly constructs with a template to allow string formatting, e.g.::

        log.compliance_log(log_mapping=(LOGTEMP.TrayportConMgrLogs.routes_received[0],
                                        LOGTEMP.TrayportConMgrLogs.routes_received[1],
                                        LOGTEMP.TrayportConMgrLogs.routes_received[2].format(
                                            routes_num=len(self._routes),
                                            routes=self._routes)))
    """
    trayport_service_starting = (1001, "INFO", "Starting Service: Trayport Connection Manager")
    trayport_service_stopping = (1002, "INFO", "Stopping Service: Trayport Connection Manager")
    routes_received = (1003, "INFO", "Received {routes_num} route(s) to market: {routes}")
    no_route_specified = (1004, "ERROR", "Routes to market not configured. Possible routes: {routes}")
    incorrect_route = (1005, "ERROR", "Configured Route with ID: {route_id} is not allowed. Possible routes: {routes}")
    multiple_routes = (1006, "ERROR",
                       "Multiple routes to market are specified in system.cfg. Currently, only one route is allowed")
    route_set_up = (1007, "INFO", "Active Route to market is {source} and set up to: {route_id}")
    jd_service_starting = (1008, "INFO", "Starting Service: Joule Direct Connection Manager")
    jd_service_stopping = (1009, "INFO", "Stopping Service: Joule Direct Connection Manager")


class StrategyBasicLogs(object):
    """
    Logs for Strategies

    due to the silence period, the text is used as a key to identify the message. Therefore, avoid using continually
    changing information (e.g. order.internal_id) in the log text. The order object can still be added to the log
    itself, but references to continually changing fields should be avoided.
    """
    strategy_activated = (3001, "INFO", "Strategy '{strategy_id}' has been activated by user '{username}'")
    strategy_deactivated = (3002, "INFO", "Strategy '{strategy_id}' has been deactivated by user '{username}'")
    strategy_halted = (3003, "INFO", "Strategy '{strategy_id}' has been halted by user '{username}' "
                                     "due to reason: '{reason}' and orders were removed: '{orders_removed}'")
    strategy_started = (3004, "INFO", "Strategy '{strategy_id}' has been unhalted by user '{username}'")
    strategy_version_changed = (3005, "INFO", "Strategy '{strategy_id}' has changed the version"
                                              " to '{strategy_zip_version}' by user '{username}'")
    strategy_config_changed = (3006, "INFO", "User '{username}' changed config for strategy '{strategy_id}'")
    strategy_deleted = (3007, "INFO", "User '{username}' deleted strategy '{strategy_id}'")


class AutoTraderLimiter(object):
    """
    All compliance logs relevant for limit management and limit violations are defined here.

    due to the silence period, the text is used as a key to identify the message. Therefore, avoid using continually
    changing information (e.g. order.internal_id) in the log text. The order object can still be added to the log
    itself, but references to continually changing fields should be avoided.
    """
    found_limit_violations = (2001, "WARNING", u"The order request from strategy {strategy_id} was not processed "
                                               u"due to limit violations.")
    # order as returned by get_own_order_keys,
    # Additional key: limit_violations as a list of dicts, as defined in order_guard.py
    per_sequence_id_limit_updated = (2002, "INFO",
                                     u"User {login_name} is setting the per_sequence_id limit: {limit_name} "
                                     u"for strategy: {strategy_id} and sequence: {sequence_id} to {limit_value}"
                                     # Additional key: update_timestamp old_limit_value
                                     )
    per_sequence_item_id_limit_updated = (2003, "INFO",
                                          u"User {login_name} is setting the per_sequence_id limit: {limit_name} "
                                          u"for strategy: {strategy_id} and sequence: {sequence_item_id} "
                                          u"to {limit_value}"
                                          # Additional key: update_timestamp old_limit_value
                                          )
    no_per_product_limits_in_db = (2004, "DEBUG", u"No per_sequence_id or per_sequence_item_id limits found "
                                                  u"in the database for strategy {strategy_id} during strategy "
                                                  u"initialization")
    limits_restored_from_db = (2005, "DEBUG", u"Limits for strategy {strategy_id} restored from database"
                               # Additional keys: limits_per_sequence_id limits_per_sequence_item_id
                               )
    limits_received = (2006, "DEBUG", u"Received a limit update from user {login_name} for strategy {strategy_id}"
                       # Additional keys: limits_per_sequence_id limits_per_sequence_item_id alteration_time
                       # This is useful in addition to the log entries for individual limits,
                       # as it also appears, if nothing changes.
                       )
    limit_expired = (
        2007, "DEBUG", u"Clean-up: Deleting limit {limit_name} for sequence_item {sequence_item_id} because "
                       u"the product's delivery period is long in the past")  # additional key: old_limit_value

    broker_limit_info = (2009, "INFO", u"For the broker {broker_id}, "
                                       u"{percent}% of the current available action limit is used.")
    product_limit_info = (2010, "INFO", u"For the broker {broker_id}, on the product {product_id}, "
                                        u"{percent}% of the current available action limit is used.")
    broker_limit_error = (2011, "WARNING", u"All action limits for the broker {broker_id} "
                                           u"are used up. No orders can be placed or modified for broker {broker_id}. "
                                           u" Order deletions are still working. "
                                           u"New actions become available tomorrow.")
    product_limit_error = (2012, "WARNING", u"All action limits for the broker {broker_id} on the product {product_id} "
                                            u"are used up. No orders can be placed or modified for broker {broker_id} "
                                            u"on product {product_id}. "
                                            u"Order deletions are still working. "
                                            u"New actions become available tomorrow.")
    max_exposed_entry_denied = (2013, "DEBUG", u"Order for {strategy_id} not placed due to Max Order Limit at product:"
                                               u" {product_id}, area/instrument {instrument_id}, side {side}."
                                               u" The limit currently is {max_exposed_order_limit}.")
    max_exposed_order_deleted = (2014, "DEBUG",
                                 u"Max order limit: The order {deleted_order[id]} (price {deleted_order[price]} from"
                                 u" strategy {deleted_order[strategy_id]} will be deleted from the exchange to make"
                                 u" space for a better order from strategy {better_order[strategy_id]} with price"
                                 u" {better_order[price]}. Product: {product_id}, area/instrument {instrument_id},"
                                 u" side {side}. The limit currently is {max_exposed_order_limit}.")
    omt_state_warning = (2015, "WARNING",
                         u"Strategy {strategy} tried to submit an OMT relevant request although the"
                         u" OMT lower threshold has been exceeded. (Short status: {short_state},"
                         u" long status: {long_state})")


class BacktestingLogs(object):
    """
    All relevant logs for Backtesting compliance
    """
    testing_started = (4001, "INFO", u"Backtesting started for: {strat_hashes}")
    testing_finished = (4002, "INFO", u"Backtesting finished for: {strat_hashes}")
    info_message = (4003, "INFO", u"Custom INFO message: {message}")
    error_message = (4004, "ERROR", u"Custom ERROR message: {message}")


class RestAPIComplianceLogs(object):
    """
    Relevant log messages for user management compliance logs. Class variable names are important because they are used
    to get the template string in prepare log helper method.
    """
    user_created = (5001, "INFO", u"User {request_maker} created user: {requested_user}")
    user_created_failed = (5002, "WARNING", u"User {request_maker} tried to create user: {requested_user}")
    user_updated = (5003, "INFO", u"User {request_maker} updated the user: {requested_user}")
    user_updated_failed = (5004, "WARNING", u"User {request_maker} tried to update user: {requested_user}")
    user_deleted = (5005, "INFO", u"User {request_maker} deleted user: {requested_user}")
    user_deleted_failed = (5006, "WARNING", u"User {request_maker} tried to delete user: {requested_user}")

    @classmethod
    def prepare_log(cls, template_name, request, error=None):
        """
        Return a dict ready to be passed to logger. This method extracts all relevant data from the request and returns
        it as a dict.

        :param template_name: One of six class variables
        :type template_name: str
        :param request: Request made to REST server.
        :type request: bottle.LocalRequest()
        :param error: In case the action fails, we also want to log the error that causes the failure
        :type error: str | None
        :return: dict to be passed to the structured logging logger
        :rtype: dict
        """
        requested_user = None
        request_maker = request.headers.get("X-JDA-User")

        try:
            body = request.json
        except Exception:
            body = request.body.read()

        if request.method != "POST":
            requested_user = request.url_args.get("login")
        elif isinstance(body, dict):
            requested_user = body.get("login")  # when creating user, it's in body

        try:
            template = getattr(cls, template_name)
            text = template[2].format(request_maker=request_maker, requested_user=requested_user),
            log_code = template[0]
        except AttributeError:
            text = "Unknown template"
            log_code = 5404  # improvised "not found" code

        log_message = {
            "message": text,
            "method": request.method,
            "path": request.url,
            "log_code": log_code,
            "request_maker": request_maker,
            "requested_user": requested_user,
            "body": body
        }
        if error is not None:
            log_message["error"] = error

        return log_message
