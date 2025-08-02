#!/usr/bin/python3
# -*- coding: utf-8 -*-
__version__ = 1

import json

import lxml.etree
import six

import autotrader_lib.common as COMMON
import autotrader_lib.templates as templates
import autotrader_lib.util as ALU


class M7TranslatorMixIn(object):
    REQUEST_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    REPORT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

    @classmethod
    def from_xml_to_json(cls, body, timestamp=None):
        if isinstance(body, six.text_type):
            body = body.encode("utf-8")
        root = lxml.etree.fromstring(body)
        xml_message_type = lxml.etree.QName(root).localname

        to_json_func = xml_message_type_to_json_map.get(xml_message_type)
        if to_json_func is None:
            # unnecessary message
            raise ALU.MessageTypeNotImplemented(xml_message_type)

        result = to_json_func(root)
        result["timestamp"] = timestamp
        return result

    @classmethod
    def from_xml_to_json_str(cls, body):  # type: (str) -> str
        return json.dumps(cls.from_xml_to_json(body))

    @classmethod
    def from_dict_to_xml(cls, data, account_id, user_id, allowed_products=None):
        message_type = data["message_type"]
        to_xml_func = message_type_to_xml_map.get(message_type)

        if not to_xml_func:
            raise ValueError("Unsupported message type: {}".format(message_type))

        return to_xml_func(data, user_id=user_id, account_id=account_id, allowed_products=allowed_products)

    @classmethod
    def from_dict_to_routing_key(cls, data):
        message_type = data["message_type"]
        if message_type in [COMMON.Request.order_entry,
                            COMMON.Request.order_modify,
                            COMMON.Request.order_deactivate,
                            COMMON.Request.order_activate,
                            COMMON.Request.order_delete,
                            COMMON.Request.trade_recall,
                            COMMON.Request.order_delete_all,
                            COMMON.Request.order_deactivate_all,
                            COMMON.Request.order_activate_all,
                            COMMON.Request.change_password]:
            return COMMON.M7RoutingKey.management
        elif message_type == COMMON.EpexRequest.omt_status:
            return COMMON.M7RoutingKey.throttling
        else:
            return COMMON.M7RoutingKey.inquiry

    @classmethod
    def from_json_to_xml(cls, data, account_id, user_id):
        return cls.from_dict_to_xml(json.loads(data), account_id, user_id)

    @classmethod
    def to_own_trade_request(cls, data, account_id="", **_):
        start_date = ALU.convert_dt_to_string(data["data"]["start"], cls.REQUEST_DATE_FORMAT)
        end_date = ALU.convert_dt_to_string(data["data"]["end"], cls.REQUEST_DATE_FORMAT)
        return templates.epex_trade_capture_request(start_date, end_date, account_id)

    @classmethod
    def to_trade_recall_request(cls, data, **_):
        return templates.epex_trade_recall_request(data["data"]["trade_id"],
                                                   data["data"]["revision"])

    @classmethod
    def to_market_state_request(cls, _, **__):
        return templates.epex_request_market_state_info()

    @classmethod
    def to_public_trade_request(cls, data, **_):
        start_date = ALU.convert_dt_to_string(data["data"]["start"], cls.REQUEST_DATE_FORMAT)
        end_date = ALU.convert_dt_to_string(data["data"]["end"], cls.REQUEST_DATE_FORMAT)
        return templates.epex_public_trade_confirmation_request(start_date, end_date)

    @classmethod
    def to_order_book_request(cls, data, allowed_products=None, **_):
        if allowed_products is None:
            allowed_products = []
        return templates.epex_request_public_order_book(allowed_products=allowed_products,
                                                        use_local=data["data"]["local"],
                                                        use_xbid=data["data"]["xbid"],
                                                        use_uk=data["data"]["uk"],
                                                        use_half_hour_products=data["data"]["half_hour_products"],
                                                        use_quarter_hour_products=data["data"]["quarter_hour_products"])

    @classmethod
    def to_own_orders_request(cls, _, **__):
        return templates.epex_request_private_order_book()

    @classmethod
    def to_system_info_request(cls, _, **__):
        return templates.epex_system_info_request()

    @classmethod
    def to_password_change_request(cls, data, **_):
        return templates.epex_request_change_password(data["body"]["old_password"], data["body"]["new_password"])

    @classmethod
    def to_product_request(cls, data, **_):
        start_date = ALU.convert_dt_to_string(data["data"]["start"], cls.REQUEST_DATE_FORMAT)
        end_date = ALU.convert_dt_to_string(data["data"]["end"], cls.REQUEST_DATE_FORMAT)
        return templates.epex_request_product_infos(start_date, end_date)

    @classmethod
    def to_order_delete_all_request(cls, _, user_id="", **__):
        return templates.epex_modify_all_orders("DELE", user_id)

    @classmethod
    def to_order_deactivate_all_request(cls, _, user_id="", **__):
        return templates.epex_modify_all_orders("DEAC", user_id)

    @classmethod
    def to_order_activate_all_request(cls, _, user_id="", **__):
        return templates.epex_modify_all_orders("ACTI", user_id)

    @classmethod
    def to_entry_order_xml(cls, data, account_id="", **_):
        accounts = account_id.split(",")
        default_account = accounts[0]
        return cls.to_order_xml(data, "entry", default_account)

    @classmethod
    def to_modify_order_xml(cls, data, **_):
        return cls.to_order_xml(data, "modification")

    @classmethod
    def to_delete_order_xml(cls, data, **_):
        return cls.to_order_xml(data, "delete")

    @classmethod
    def to_deactivate_order_xml(cls, data, **_):
        return cls.to_order_xml(data, "deactivate")

    @classmethod
    def to_activate_order_xml(cls, data, **_):
        return cls.to_order_xml(data, "activate")

    @classmethod
    def to_order_xml(cls, data, mod, account=None):
        # If entry is False then an order modify will be generated

        PARAMS = {"revision": "revisionNo",
                  "delivery_area_id": "dlvryAreaId",
                  "side": "side",
                  "quantity": "qty",
                  "price": "px",
                  "client_order_id": "clOrdrId",
                  "validity_restriction": "validityRes",
                  "validity_date": "validityDate",
                  "txt": "txt",
                  "execution_restriction": "ordrExeRestriction",
                  "order_id": "ordrId",
                  "product_id": "contractId",
                  "delivery_start": "dlvryStart",
                  "delivery_end": "dlvryEnd",
                  "product_type": "prod",
                  "type": "type",
                  "clip_quantity": "displayQty"}

        order_elements = []
        for order in data["data"]:
            element = dict()

            # mandatory parameters
            if mod == "entry":
                assert account, ("For order entry an account has to be provided. "
                                 "Either in the configuration file or in the strategy internal number.")
                element["preArranged"] = "false"
                element["acctId"] = order.get("exchange_portfolio_id", account)
                element["clearingAcctType"] = "P"
                element["state"] = "ACTI"
            for param in order:
                if param in PARAMS:
                    if param == "revision":
                        element["revisionNo"] = str(order["revision"])
                    elif param == "side" and mod == "entry":
                        element["side"] = order["side"].upper()
                    elif param == "quantity":
                        element["qty"] = "{:0.0f}".format(round(order["quantity"] * 1000, -2))
                    elif param == "clip_quantity" and order["type"] == COMMON.OrderType.iceberg:
                        element["displayQty"] = "{:0.0f}".format(round(order["clip_quantity"] * 1000, -2))
                    elif param == "price":
                        element["px"] = "{:0.0f}".format(round(order["price"] * 100))
                    elif param in ["validity_date", "delivery_start", "delivery_end"]:
                        param_map = PARAMS[param]
                        element[param_map] = ALU.convert_from_timestamp(
                            order[param], cls.REQUEST_DATE_FORMAT)
                    elif param in ["product_id", "side", "delivery_area_id"] and mod == "entry":
                        element[PARAMS[param]] = order[param]
                    elif param in ["product_id", "side", "delivery_area_id"] and mod in ["modification",
                                                                                         "delete",
                                                                                         "deactivate",
                                                                                         "activate"]:
                        continue
                    elif param == "exchange_portfolio_id":
                        continue
                    else:
                        element[PARAMS[param]] = order[param]
            if "product_id" in order and "txt" in order:
                order_tags = ALU.parse_order_tags(order["txt"])
                internal_id = order_tags.get("internal_id", None)
                product_id = order["product_id"]
                is_client_order_id_built = False
                if internal_id and product_id:
                    client_order_id = internal_id + "|" + product_id
                    # EPEX has a length limit for the clOrdrId field
                    if len(client_order_id) <= COMMON.EpexVars.client_order_id_max_len:
                        element["clOrdrId"] = client_order_id
                        is_client_order_id_built = True
                if not is_client_order_id_built:
                    # either no internal_id/product_id was found or their length exceeded the limit
                    # we can try putting the order_id into the clOrdrId field instead
                    if order.get("order_id") and len(order.get("order_id")) <= COMMON.EpexVars.client_order_id_max_len:
                        element["clOrdrId"] = order.get("order_id")

            order_elements.append(ALU.make_xml_element("Ordr", element))
            if mod == "entry":
                template = templates.epex_order_entry
                kwargs = {}
            elif mod == "modification":
                template = templates.epex_order_modify
                kwargs = {}
            elif mod == "delete":
                template = templates.epex_order_modify
                kwargs = {"mod_type": "DELE"}
            elif mod == "deactivate":
                template = templates.epex_order_modify
                kwargs = {"mod_type": "DEAC"}
            elif mod == "activate":
                template = templates.epex_order_modify
                kwargs = {"mod_type": "ACTI"}

        return template("\n".join(order_elements), **kwargs)

    @classmethod
    def to_throttling_status_request(cls, _, **__):
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <ThrottlingStatusReq xmlns="http://www.deutsche-boerse.com/m7/v6">
                <StandardHeader marketId="EPEX" />
            </ThrottlingStatusReq>"""

    @classmethod
    def from_public_order_book_xml(cls, tree):
        # direction
        # price
        # quantity
        result = dict(exchange="EPEX", message_type="order_book",
                      synchronisation_init=tree.tag.endswith("PblcOrdrBooksResp"), data=[])
        ns = "{{{}}}".format(tree.nsmap[None])
        for ordr in tree.findall("{}OrdrbookList/{}OrdrBook".format(ns, ns)):
            for sellbuy in ordr:
                for new_order_element in sellbuy:
                    element = dict()
                    element["delivery_area_id"] = ordr.attrib["dlvryAreaId"]
                    element["execution_restriction"] = new_order_element.attrib.get("ordrExeRestriction",
                                                                                    COMMON.ExecutionRestriction.non)
                    element["product_id"] = ordr.attrib["contractId"]
                    element["revision"] = int(ordr.attrib["revisionNo"]) or -1
                    element["order_id"] = new_order_element.attrib.get("ordrId")
                    element["direction"] = (
                        COMMON.Direction.buy
                        if sellbuy.tag.endswith("BuyOrdrList")
                        else COMMON.Direction.sell
                    )

                    element["price"] = float(new_order_element.attrib.get("px")) / 100.
                    element["quantity"] = float(new_order_element.attrib.get("qty")) / 1000.
                    result["data"].append(element)
        return result

    @classmethod
    def from_order_execution_report(cls, tree):
        result = dict(exchange="EPEX", message_type="order_execution", data=[])
        # account
        # user
        # execution_restriction
        # validity_restriction
        # validity_date
        ns = "{{{}}}".format(tree.nsmap[None])
        orders = []
        for ordr in tree.findall("{}OrdrList/{}Ordr".format(ns, ns)):
            element = dict()
            element["initial_order_id"] = ordr.attrib["initialOrdrId"]
            element["order_id"] = ordr.attrib["ordrId"]
            element["product_id"] = ordr.attrib["contractId"]
            element["action"] = ordr.attrib["action"]
            element["state"] = ordr.attrib["state"]
            order_type = ordr.attrib["type"]
            element["type"] = order_type
            element["delivery_area_id"] = ordr.attrib["dlvryAreaId"]
            element["txt"] = ordr.attrib["txt"].encode("utf8") if six.PY2 else ordr.attrib["txt"]
            element["revision"] = int(ordr.attrib["revisionNo"])
            element["initial_quantity"] = float(ordr.attrib["initialQty"]) / 1000.
            quantity = float(ordr.attrib["qty"]) / 1000.
            if order_type == COMMON.OrderType.iceberg:
                clip_quantity = float(ordr.attrib["displayQty"]) / 1000.
                visible_quantity = quantity
                hidden_quantity = float(ordr.attrib["hiddenQty"]) / 1000.
                quantity = visible_quantity + hidden_quantity
                element["visible_quantity"] = visible_quantity
                element["clip_quantity"] = clip_quantity
            element["quantity"] = quantity
            element["price"] = float(ordr.attrib["px"]) / 100.
            side = ordr.attrib["side"]
            element["direction"] = COMMON.Direction.buy if side == "BUY" else COMMON.Direction.sell
            element["account"] = ordr.attrib["acctId"]
            element["user"] = ordr.attrib["usrCode"]
            element["last_update_user"] = ordr.attrib["lastUpdateUsrInfo"].replace(ordr.attrib["acctId"], "")
            element["execution_restriction"] = ordr.attrib.get("ordrExeRestriction", "NON")
            element["validity_restriction"] = ordr.attrib.get("validityRes", "GFS")
            element["validity_date"] = ordr.attrib.get("validityDate", None)
            element["timestamp"] = ordr.attrib.get("timestmp", None)
            orders.append(element)
        orders = sorted(orders, key=lambda val: (int(val["order_id"]), int(val["revision"])))
        result["data"] = orders
        return result

    @classmethod
    def from_contract_info_report(cls, tree):
        result = dict(exchange="EPEX", message_type="product", data=[])
        standard_map = tree.nsmap[None]
        for contract in tree.findall("{{{}}}ContractList/"
                                     "{{{}}}Contract".format(standard_map,
                                                             standard_map)):
            element = dict()
            element["name"] = contract.attrib.get("name")
            element["delivery_start"] = ALU.convert_to_timestamp(
                contract.attrib.get("dlvryStart"), cls.REPORT_DATE_FORMAT)
            element["delivery_end"] = ALU.convert_to_timestamp(
                contract.attrib.get("dlvryEnd"), cls.REPORT_DATE_FORMAT)
            element["product_id"] = contract.attrib.get("contractId")
            element["predefined"] = True if contract.attrib.get("predefined") == "true" else False
            element["delivery_area_states"] = {}
            element["trading_phases"] = {}
            element["product_type"] = contract.attrib.get("prod")

            for state in contract.findall("{{{}}}DlvryAreaState".format(standard_map)):
                product_state = COMMON.DeliveryAreaState.convert(COMMON.Exchange.epex, state.attrib.get("state"))
                trading_state = COMMON.TradingPhase.convert(COMMON.Exchange.epex, state.attrib.get("tradingPhase"))
                product_state = (
                    COMMON.DeliveryAreaState.inactive if trading_state == COMMON.TradingPhase.closed else product_state
                )
                element["delivery_area_states"][state.attrib.get("dlvryAreaId")] = dict(state=product_state)
                trading_phase_start = state.attrib.get("tradingPhaseStart")
                trading_phase_end = state.attrib.get("tradingPhaseEnd", trading_phase_start)
                element["trading_phases"][state.attrib.get("dlvryAreaId")] = dict(
                    state=trading_state,
                    start=ALU.convert_to_timestamp(trading_phase_start, cls.REPORT_DATE_FORMAT),
                    end=ALU.convert_to_timestamp(trading_phase_end, cls.REPORT_DATE_FORMAT))
            result["data"].append(element)
        return result

    @classmethod
    def from_trade_capture_report(cls, tree):
        result = dict(exchange="EPEX", message_type="own_trade", data=[])
        standard_map = tree.nsmap[None]
        for trade in tree.findall("{{{}}}TradeList/"
                                  "{{{}}}Trade".format(standard_map, standard_map)):
            for child in trade.getchildren():
                element = dict()
                element["txt"] = child.attrib["txt"].encode("utf8") if six.PY2 else child.attrib["txt"]
                element["delivery_area"] = child.attrib["dlvryAreaId"]
                element["direction"] = COMMON.Direction.buy if child.tag.endswith("Buy") else COMMON.Direction.sell
                element["order_id"] = child.attrib["ordrId"]
                element["aggressor"] = child.attrib.get("aggressorIndicator", COMMON.ActorType.unknown)
                element["user"] = child.attrib["usrCode"]

                element["trade_id"] = trade.attrib["tradeId"]
                element["state"] = trade.attrib["state"]
                element["revision"] = int(trade.attrib["revisionNo"])
                element["execution_time"] = ALU.convert_to_float_timestamp(
                    trade.attrib["execTime"], cls.REPORT_DATE_FORMAT
                )
                element["product_id"] = trade.attrib["contractId"]
                element["price"] = float(trade.attrib["px"]) / 100.
                element["quantity"] = float(trade.attrib["qty"]) / 1000.
                result["data"].append(element)
        return result

    @classmethod
    def from_public_trade_confirmation_report(cls, tree):
        result = dict(exchange="EPEX", message_type="public_trade", data=[])
        standard_map = tree.nsmap[None]
        for trade in tree.findall("{{{}}}TradeList/"
                                  "{{{}}}PblcTradeConf".format(standard_map,
                                                               standard_map)):
            element = dict()
            element["sell_delivery_area"] = trade.attrib["sellDlvryAreaId"]
            element["buy_delivery_area"] = trade.attrib["buyDlvryAreaId"]
            element["trade_id"] = trade.attrib["tradeId"]
            element["state"] = trade.attrib["state"]
            element["revision"] = int(trade.attrib["revisionNo"])
            element["execution_time"] = ALU.convert_to_timestamp(trade.attrib["tradeExecTime"], cls.REPORT_DATE_FORMAT)
            element["product_id"] = trade.attrib["contractId"]
            element["price"] = float(trade.attrib["px"]) / 100.
            element["quantity"] = float(trade.attrib["qty"]) / 1000.
            result["data"].append(element)
        return result

    @classmethod
    def from_err_resp(cls, tree):
        result = dict(exchange="EPEX", message_type="error_response", data=[])

        ns = "{{{}}}".format(tree.nsmap[None])
        for error in tree.findall("{}Error".format(ns)):
            error_message = error.get("err")
            error_code = error.get("errCode")
            client_order_id = error.get("clOrdrId")
            internal_id = None
            product_id = None
            order_id = None
            if client_order_id:
                client_order_id_split = client_order_id.split("|")
                # it only makes sense to add the product_id and internal_id if they are valid
                if len(client_order_id_split) == 2:
                    if len(client_order_id_split[0]) > 0 and len(client_order_id_split[1]) > 0:
                        internal_id = client_order_id_split[0]
                        product_id = client_order_id_split[1]
                else:
                    # fallback case, where order_id was put into the clOrdrId field,
                    # instead of the product_id & internal_id, due to e.g. length
                    order_id = client_order_id

            xml_varlist = error.findall("{}VarList".format(ns))
            varlist = [{
                var.get("id"): var.get("value", "").split(",")
            } for var in xml_varlist[0]] if xml_varlist else []
            result["data"].append(dict(error_message=error_message, error_code=error_code, var_list=varlist,
                                       internal_id=internal_id, product_id=product_id, order_id=order_id))
        return result

    @classmethod
    def from_market_state_report(cls, tree):
        state = tree.attrib["state"]
        if state == "ACTI":
            state = COMMON.MarketState.active
        elif state == "HIBE":
            state = COMMON.MarketState.hibernated
        result = dict(exchange="EPEX", message_type="market_state",
                      data=dict(state=state, revision=tree.attrib["revisionNo"]))
        return result

    @classmethod
    def from_system_info_response(cls, tree):
        max_orders = tree.attrib["maxOrders"]
        return dict(exchange="EPEX", message_type=COMMON.EpexResponse.system_info, data=dict(max_orders=max_orders))

    @classmethod
    def from_ack_response(cls, _):
        return dict(exchange="EPEX", message_type="ack_response")

    @classmethod
    def from_throttling_status_response(cls, tree):
        data = dict()
        ns = "{{{}}}".format(tree.nsmap[None])
        child = tree.find("{}ThrottlingMemberStatus".format(ns))
        for rule in child.getchildren():
            key = COMMON.RateLimitType.Epex.short if "ShortRule" in rule.tag else COMMON.RateLimitType.Epex.long
            status = rule.find("{}Status".format(ns))
            omt_from_exchange = int(status.attrib["currentOmtCount"]) if status is not None else None
            restricted_status = status.attrib["status"] if status is not None else None
            data[key] = ALU.BaseOMTParameters(
                received_omt=omt_from_exchange,
                observation_period=int(rule.attrib["observationPeriodLength"]),
                tolerance_period=int(rule.attrib["tolerancePeriodLength"]),
                cooldown_period=int(rule.attrib["reconnectionCoolDown"]),
                lower_threshold=int(rule.attrib["omtLimitL1"]),
                upper_threshold=int(rule.attrib["omtLimitL2"]),
                limit_type=key,
                status=restricted_status
            ).to_dict(from_exchange=True)
        return dict(message_type=COMMON.EpexResponse.omt_status, exchange=COMMON.Exchange.epex, data=data)

    @classmethod
    def from_message_report(cls, tree):
        data = []
        ns = "{{{}}}".format(tree.nsmap[None])
        msg_list = tree.find("{}MsgList".format(ns))
        for msg in msg_list.getchildren():
            txt = msg.attrib["txt"]
            msg_code = msg.attrib["messageCode"]
            var_list = msg.find("{}VarList".format(ns))
            msg_vars = {var.attrib["id"]: var.attrib["value"] for var in var_list.getchildren()}
            data_dict = dict(
                txt=txt,
                code=msg_code,
                vars=msg_vars,
            )
            data.append(data_dict)
        return dict(message_type=COMMON.EpexResponse.message_report, exchange=COMMON.Exchange.epex, data=data)


xml_message_type_to_json_map = {
    "ContractInfoRprt": M7TranslatorMixIn.from_contract_info_report,
    "PblcOrdrBooksDeltaRprt": M7TranslatorMixIn.from_public_order_book_xml,
    "PblcOrdrBooksResp": M7TranslatorMixIn.from_public_order_book_xml,
    "OrdrExeRprt": M7TranslatorMixIn.from_order_execution_report,
    "TradeCaptureRprt": M7TranslatorMixIn.from_trade_capture_report,
    "PblcTradeConfRprt": M7TranslatorMixIn.from_public_trade_confirmation_report,
    "MktStateRprt": M7TranslatorMixIn.from_market_state_report,
    "SystemInfoResp": M7TranslatorMixIn.from_system_info_response,
    "AckResp": M7TranslatorMixIn.from_ack_response,
    "ErrResp": M7TranslatorMixIn.from_err_resp,
    "ThrottlingStatusResp": M7TranslatorMixIn.from_throttling_status_response,
    "MsgRprt": M7TranslatorMixIn.from_message_report,
}


message_type_to_xml_map = {
    COMMON.Request.order_entry: M7TranslatorMixIn.to_entry_order_xml,
    COMMON.Request.order_modify: M7TranslatorMixIn.to_modify_order_xml,
    COMMON.Request.order_delete: M7TranslatorMixIn.to_delete_order_xml,
    COMMON.Request.order_deactivate: M7TranslatorMixIn.to_deactivate_order_xml,
    COMMON.Request.order_activate: M7TranslatorMixIn.to_activate_order_xml,
    COMMON.Request.order_delete_all: M7TranslatorMixIn.to_order_delete_all_request,
    COMMON.Request.order_deactivate_all: M7TranslatorMixIn.to_order_deactivate_all_request,
    COMMON.Request.order_activate_all: M7TranslatorMixIn.to_order_activate_all_request,
    COMMON.Request.own_trade: M7TranslatorMixIn.to_own_trade_request,
    COMMON.Request.public_trade: M7TranslatorMixIn.to_public_trade_request,
    COMMON.Request.market_state: M7TranslatorMixIn.to_market_state_request,
    COMMON.Request.order_book: M7TranslatorMixIn.to_order_book_request,
    COMMON.Request.own_orders: M7TranslatorMixIn.to_own_orders_request,
    COMMON.Request.product: M7TranslatorMixIn.to_product_request,
    COMMON.Request.trade_recall: M7TranslatorMixIn.to_trade_recall_request,
    COMMON.EpexRequest.system_info: M7TranslatorMixIn.to_system_info_request,
    COMMON.Request.change_password: M7TranslatorMixIn.to_password_change_request,
    COMMON.EpexRequest.omt_status: M7TranslatorMixIn.to_throttling_status_request
}
