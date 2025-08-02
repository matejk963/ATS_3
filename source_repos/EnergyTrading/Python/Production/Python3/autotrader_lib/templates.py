#!/usr/bin/python3
# -*- coding: utf-8 -*-
import xml.sax.saxutils


def epex_order_entry(orders):
    return """\
<OrdrEntry xmlns="http://www.deutsche-boerse.com/m7/v6">
    <StandardHeader marketId="EPEX"/>
    <OrdrList>
       {orders}
    </OrdrList>
</OrdrEntry>""".format(orders=orders)


def epex_order_modify(orders, mod_type="MODI"):
    return """\
<OrdrModify xmlns="http://www.deutsche-boerse.com/m7/v6" ordrModType="{mod_type}">
    <StandardHeader marketId="EPEX"/>
    <OrdrList>
       {orders}
    </OrdrList>
</OrdrModify>""".format(orders=orders, mod_type=mod_type)


def epex_trade_recall_request(trade_id, revision):
    return """\
<TradeRecallReq xmlns="http://www.deutsche-boerse.com/m7/v6"
                tradeId="{trade_id}"
                revisionNo="{revision}">
    <StandardHeader marketId="EPEX"/>
</TradeRecallReq>""".format(trade_id=trade_id, revision=revision)


def epex_trade_capture_request(start_date, end_date, acct_id):
    return """\
<TradeCaptureReq
    startDate="{start_date}"
    endDate="{end_date}"
    xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"></StandardHeader>
  {acct_id}
</TradeCaptureReq>""".format(start_date=start_date,
                             end_date=end_date,
                             acct_id="".join(["<acctId>{}</acctId>".format(a) for a in acct_id.split(",")]))


def epex_public_trade_confirmation_request(start_date, end_date):
    return """\
<PblcTradeConfReq
    startDate="{start_date}"
    endDate="{end_date}"
    xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"></StandardHeader>
</PblcTradeConfReq>""".format(start_date=start_date,
                              end_date=end_date)


def epex_request_product_infos(start, end):
    return """\
<ContractInfoReq startDate="{start}" endDate="{end}" xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX">
  </StandardHeader>
</ContractInfoReq>""".format(start=start, end=end)


def epex_request_public_order_book(allowed_products, use_local=True, use_xbid=True, use_uk=True,
                                   use_half_hour_products=True, use_quarter_hour_products=True):
    products = []
    if allowed_products:
        products = allowed_products
    else:
        if use_local:
            products.extend(["Intraday_Hour_Power", "Continuous_Power_Base"])
            if use_quarter_hour_products:
                products.append("Intraday_Quarter_Hour_Power")
            if use_half_hour_products:
                products.append("Intraday_Half_Hour_Power")
        if use_xbid:
            products.append("XBID_Hour_Power")
            if use_quarter_hour_products:
                products.append("XBID_Quarter_Hour_Power")
            if use_half_hour_products:
                products.append("XBID_Half_Hour_Power")
        if use_uk:
            products.extend(["GB_4_Hour_Power", "GB_2_Hour_Power", "GB_Hour_Power", "GB_Half_Hour_Power"])
    products_string = "\n".join("  <prodName>{}</prodName>".format(product) for product in products)
    return """\
<PblcOrdrBooksReq xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"></StandardHeader>
{}
</PblcOrdrBooksReq>""".format(products_string)


def epex_request_private_order_book():
    return """\
<OrdrReq xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"/>
</OrdrReq>"""


def epex_system_info_request():
    return """<SystemInfoReq xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"/>
</SystemInfoReq>"""


def epex_modify_all_orders(mod_type, user_id):
    return """\
<ModifyAllOrdrs
        ordrModType="{mod_type}"
        usrId="{user_id}"
        inclPreArranged="true"
        xmlns="http://www.deutsche-boerse.com/m7/v6">
    <StandardHeader marketId="EPEX"></StandardHeader>
</ModifyAllOrdrs>""".format(mod_type=mod_type,
                            user_id=user_id)


def epex_request_market_state_info():
    return """<MktStateReq xmlns="http://www.deutsche-boerse.com/m7/v6">
  <StandardHeader marketId="EPEX"/>
</MktStateReq>"""


def epex_request_change_password(current_password, new_password):
    return """<ChgPwdReq xmlns="http://www.deutsche-boerse.com/m7/v6" currentPwd={} newPwd={}>
  <StandardHeader marketId="EPEX"/>
</ChgPwdReq>""".format(xml.sax.saxutils.quoteattr(current_password), xml.sax.saxutils.quoteattr(new_password))
