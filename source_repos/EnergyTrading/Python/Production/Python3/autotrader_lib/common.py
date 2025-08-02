#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import collections
import logging
import os
import time
import re
import six
from six.moves import range

# ISO UTC datetime formatting string
DATEFORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# Common regular expression pattern for strategy and package names:
NAME_PATTERN_RAW = r"^\w[\w\@\-]{,%s}$"
# Names longer than 255 characters trigger OSError path is too long.
# Package name consists of: strategy name + separator + arbitrary string + separator + datetime
# In maximal character lengths: MAX_STRATEGY_NAME_LENGTH + 1 + (MAX_PACKAGE_NAME_LENGTH + 49) + 1 + 19 = 255
# (Extra 49 characters are reserved for future-proofing.)
MAX_STRATEGY_NAME_LENGTH = 35
MAX_PACKAGE_NAME_LENGTH = 255 - 21 - MAX_STRATEGY_NAME_LENGTH - 49   # with strategy name length 35, it is 150


def _compile_regex(raw):
    if six.PY2:
        return re.compile(raw)
    return re.compile(raw, flags=re.ASCII)


STRATEGY_NAME_PATTERN = _compile_regex(NAME_PATTERN_RAW % (MAX_STRATEGY_NAME_LENGTH - 1))
PACKAGE_NAME_PATTERN = _compile_regex(NAME_PATTERN_RAW % (MAX_PACKAGE_NAME_LENGTH - 1))

# TIMER_SLEEP_FAST/SLOW defines time (in sec), which should be lapsed between two successive timer_fast/timer events
TIMER_SLEEP_FAST = 2.0
TIMER_SLEEP_SLOW = 10.0
# NUM_REPETITIONS defines a number of times pro minute each strategy
# (during timer_fast action) should be called for a product one hour
# before the delivery start
NUM_REPETITIONS = 30

MINUTE = 60
QUARTER = 15 * MINUTE
HALF = 2 * QUARTER
HOUR = 4 * QUARTER
DAY = 24 * HOUR
WEEK = DAY * 7
MINUTES_PER_HOUR = 60
OTR = 100

# time at which the German Zones become decoupled
DE_ZONES_JOINED_UNTIL_SEC_BEFORE_DELIVERY = HOUR / 2

# User for internal order executions and internal trades
INTERNAL_USER = "INTERNAL"

# Default service user for JDA
JDA_SERVICE_USER_PROD = "prod.jda.trayport.com"
JDA_SERVICE_USER_UAT = "uat.jda.trayport.com"

# REST_API_TIMEOUT defines the number of seconds the rest_api waits for responses for
# request communicated with Autotrader via the mongo-db.
# Unanswered requests in the database that are older than this timeout are not
# be handled by Autotrader.
REST_API_TIMEOUT = 5

# Location of static files, such as Swagger, on production-like systems
RESTAPI_STATIC_FILES_FOLDER = "/var/www/html/autotrader_rest"

# rounding digits to avoid machine errors (should not exceed 16, approximately the binary representation of floats)
MACHINE_ERROR_DIGITS = 10

# The key used to store the token in the Cookie for logins via PT-RESTAPI
# This is needed by autotrader_rest
PT_REST_COOKIE_TOKEN_KEY = "periotheus"

# How often we remove the orderbook data for products which are no longer actively trading.
ORDERBOOK_CLEANUP_INTERVAL = HOUR

# Default precision for rounding floats
FLOAT_ROUNDING_PRECISION = 4

# Minimum quantity for orders. Orders with smaller quantity are considered orders with 0 quantity
# (i.e. the wish to remove the order.) This is useful, so strategies can calculate the slot quantity based on
# unprecise floating point arithmetics.
# As spot-markets currently have a tick-size of 0.1 and F&F of 1, this is ok.
# We use the same limit, independent of the unit of the exchange/ instrument
MIN_ORDER_QTY = 0.05

# After how many seconds we release lock and remove the orderbook data for orders that wait for exchange response.
# If we have waited that many seconds for an exchange response, we are sure that the response will never come.
# The value of 50 is based on the fact that EPEX by default discards messages from the queue after 30 seconds.
# Additionally, this value should be bigger than the expected worst case queue_lag (to avoid overtrading),
# but not too big to reduce the impact of hanging locks on autoTRADER.
ORDER_LOCK_TIMEOUT = 50

# Venue connection state used in simulation mode
SIMULATION_VENUE_UPSTREAM_STATE = "autoTRADER Simulation"


log = logging.getLogger('autotrader.common')

TradingPhaseInfo = collections.namedtuple("trading_phase_info", ["start", "end", "state"])


class ProductType:
    class ID:
        """Intraday Power Product Types"""

        # Nordpool types
        NX_Intraday_Power_D_QH = "NX_Intraday_Power_D_QH"
        NX_Intraday_Power_D_HH = "NX_Intraday_Power_D_HH"
        NX_Intraday_Power_D = "NX_Intraday_Power_D"

        # XBID product types
        XBID_Quarter_Hour_Power = "XBID_Quarter_Hour_Power"
        XBID_Half_Hour_Power = "XBID_Half_Hour_Power"
        XBID_Hour_Power = "XBID_Hour_Power"

        # Local product types
        Intraday_Quarter_Hour_Power = "Intraday_Quarter_Hour_Power"
        Half_Hour_Power = "Half_Hour_Power"
        Intraday_Hour_Power = "Intraday_Hour_Power"

        # uk/gb product types
        GB_Half_Hour_Power = "GB_Half_Hour_Power"
        GB_Hour_Power = "GB_Hour_Power"
        GB_2_Hour_Power = "GB_2_Hour_Power"
        GB_4_Hour_Power = "GB_4_Hour_Power"

        ALL_QUARTERS = (Intraday_Quarter_Hour_Power, XBID_Quarter_Hour_Power, NX_Intraday_Power_D_QH)
        ALL_HALF = (NX_Intraday_Power_D_HH, XBID_Half_Hour_Power, Half_Hour_Power, GB_Half_Hour_Power)
        ALL_HOUR = (NX_Intraday_Power_D, XBID_Hour_Power, Intraday_Hour_Power, GB_Hour_Power)
        ALL_2_HOUR = (GB_2_Hour_Power,)
        ALL_4_HOUR = (GB_4_Hour_Power,)

        ALL_XBID = (
            XBID_Quarter_Hour_Power,
            XBID_Half_Hour_Power,
            XBID_Hour_Power,
        )

        ALL = ALL_QUARTERS + ALL_HALF + ALL_HOUR + ALL_2_HOUR + ALL_4_HOUR

    class Gas:
        """Product Types for SPOT Gas"""
        WD = "WD"  # within day
        DA = "DA"  # day ahead
        WE = "W/END"  # weekend

        ALL = (WD, DA, WE)


class ProductDurations:
    """
    product type filters, which allow certain product durations to be traded,
     used for power position closer and flex
    """

    class ID:
        """Intraday Power Product Durations"""
        QUARTER = QUARTER
        HALF = HALF
        HOUR = HOUR
        BLOCK_2_HOUR = 2 * HOUR
        BLOCK_4_HOUR = 4 * HOUR

        ALL = (QUARTER, HALF, HOUR, BLOCK_2_HOUR, BLOCK_4_HOUR)
        ALLOWED_BLOCK_DURATION = (HOUR, BLOCK_2_HOUR, BLOCK_4_HOUR)

        DEFAULT = 0


class ProductNotFound(Exception):
    pass


class OrderNotFound(Exception):
    pass


class StrategyLoadError(Exception):
    pass


class UnknownOrderType(Exception):
    pass


class MissingParameters(Exception):
    pass


class ActionLimitFormatError(Exception):
    pass


class HaltExchangeException(Exception):
    """Throwing this exception indicates that the exchange should be halted immediately."""

    def __init__(self, exchange_id, *args, **kwargs):
        """

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        self.restart = kwargs.pop("restart", False)
        super(HaltExchangeException, self).__init__(*args, **kwargs)
        self.exchange_id = exchange_id


class RestartExchangeException(Exception):
    """This exception can be thrown to fully reinitialize an exchange."""

    def __init__(self, exchange_id, *args, **kwargs):
        """

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        super(RestartExchangeException, self).__init__(*args, **kwargs)
        self.exchange_id = exchange_id

    def __str__(self):
        return "A restart of the exchange {} is needed: {}".format(
            self.exchange_id, super(RestartExchangeException, self).__str__()
        )


class DanglingExchangeException(Exception):
    """This exception is thrown when someone holds a dangling reference to an old, unused exchange object"""
    pass


class OutOfSyncChildException(Exception):
    """This exception is thrown in a multiprocessing context when one of the child has some messages missing"""
    pass


class ChangeStreamException(Exception):
    """This exception is thrown in a multiprocessing context if a ChangeStream dies"""
    pass


class WriterThreadException(Exception):
    """This exception is thrown when the writer thread has been detected to be dead and aT should stop"""
    pass


class GapDetectedException(RestartExchangeException):
    def __init__(self, exchange_id, *args, **kwargs):
        """
        To be used when a gap in message sequence is detected. It schedules EPEX connection manager restart.

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        super(GapDetectedException, self).__init__(exchange_id, *args, **kwargs)


class SkippedHeartbeatException(RestartExchangeException):
    def __init__(self, exchange_id, *args, **kwargs):
        """
        To be used when 3 consecutive heartbeats are skipped. EPEX recommends connection manager restart in this case.

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        super(SkippedHeartbeatException, self).__init__(exchange_id, *args, **kwargs)


class UnexpectedAreaRevisionException(RestartExchangeException):
    def __init__(self, exchange_id, delivery_area, expected_revision_number, actual_revision_number, *args, **kwargs):
        """
        To be used when there is inconsistent revision number.

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        self.exchange_id = exchange_id
        self.area = delivery_area
        self.expected_rev_num = expected_revision_number
        self.actual_rev_num = actual_revision_number
        super(UnexpectedAreaRevisionException, self).__init__(exchange_id, *args, **kwargs)

    def __str__(self):
        return ("Exchange {} received a public order with an unexpected revision on area {}. Previous revision: {}, "
                "received {}.").format(self.exchange_id, self.area, self.expected_rev_num, self.actual_rev_num)


class UnresponsiveExchangeException(RestartExchangeException):
    def __init__(self, exchange_id, *args, **kwargs):
        """
        To be used when an order times out, and in the same period there were no other messages received from the
        exchange.

        :param exchange_id: Internal ID of the exchange to restart. See COMMON.Exchange
        :type exchange_id:  str
        """
        super(UnresponsiveExchangeException, self).__init__(exchange_id, *args, **kwargs)

    def __str__(self):
        return "Exchange {} did not respond to a message and did not receive any new message for too long".format(
            self.exchange_id
        )


class Direction(object):
    bid = "buy"
    buy = "buy"
    ask = "sell"
    sell = "sell"
    none = None
    other = {buy: sell, sell: buy}

    def invert(self, order_type):
        try:
            return self.other[order_type]
        except KeyError:
            raise UnknownOrderType()

    @classmethod
    def get(cls, direction):
        if direction.lower() in ["bid", "buy"]:
            return cls.buy
        else:
            return cls.sell


class TrayportReplyATErrorType(object):
    trade = "trade"
    tradeorder = "tradeorder"
    order = "order"
    general = "general"


class Exchange(object):

    # all added exchanges should have at least 4 bytes and the first 4 bytes must identify them uniquely
    UNIQUE_EXCH_BYTES = 4

    nordpool = "NORD"
    epex = "EPEX"
    periotheus = "PERIOTHEUS"
    autotrader = "AUTOTRADER"
    trayport = "TRAYPORT"
    parent = "PARENT"
    children = "CHILDREN"
    persistence = "PERSISTENCE"

    @staticmethod
    def name_map(exchange_name):
        """
        Use this instead of asking yourself who thought it would be a good idea to use inconsistent exchange ids.
        :type exchange_name: str
        :rtype: str
        """
        return 'nordpool' if exchange_name == Exchange.nordpool else exchange_name.lower()

    @classmethod
    def get_external(cls):
        """
        Get external exchanges.
        :returns: Identifiers for the exchanges autotrader can connect to.
        :rtype: [str]
        """
        return [cls.epex, cls.nordpool, cls.trayport]

    @classmethod
    def get_configured(cls, at_cfg):
        """
        Get currently configured external exchanges.
        :type at_cfg: `ATCONF.ATConfig`
        :rtype: [str]
        """
        return [e for e in Exchange.get_external() if getattr(at_cfg, Exchange.name_map(e))]


class Units(object):
    __slots_container_py2__ = ["MW", "MWH", "PEG_MWH_DAY"]
    MW = "Megawatts"  # e.g. on UK
    MWH = "MWh"  # e.g. on TTF
    PEG_MWH_DAY = "Megawatt Hours per Day"  # only on PEG!


class Broker(object):
    """
    For some brokers which are used commonly in our strategies and tests, we provide the broker_id as constant.
    Other brokers are supported as well.
    """
    ice = "30"
    ice_endex = "148"
    eexs = "20"  # Formerly PEGAS
    # Until spring 2022, the broker_id of EEX is 27.
    # However, in spring 2022 the connection between EEX and the TRAYPORT Joule Direct server is switched
    # to a T7 connection. This new T7 connection towards EEX has different broker ids, which are additionally different
    # between UAT and production.
    eex = "27"
    eex_t7_prod = "1441"
    eex_t7_uat = "1262"


class TemplateFieldRequired(object):
    create = "create"
    active = "active"
    never = "never"
    inactive = "inactive"


class SequenceId(object):
    """
    Sequence Ids of most commonly used sequences for Trayport.

    This can be used in strategy and test code.
    """
    gas_prompt = "10000302"
    bom = "10000301"
    weekends = "10000322"


class GasPromptItemId(object):
    """
    Most commonly used item ids (first_item_id) for the sequence 10000302 (gas prompt)

    This can be used in strategy and test code.
    """
    within_day = "1"
    day_ahead = "2"
    bow = "3"
    weekend = "4"
    # The working days next week contract (item_id 5) is not supported by autoTRADER
    saturday = "6"
    sunday = "7"
    monday = "19"
    tuesday = "20"
    wednesday = "21"
    thursday = "22"
    friday = "23"
    bom = "35"


class _GasPromptProductMeta(type):
    def __getattr__(cls, item):
        return "{}_{}".format(SequenceId.gas_prompt, getattr(GasPromptItemId, item))


class GasPromptProductId(six.with_metaclass(_GasPromptProductMeta, object)):
    """
    Full product id for the most commonly used gas prompt products

    This can be used in strategy and test code.
    """


class AreaType(type):
    def __getattr__(cls, name):
        """We have to overwrite the getattr for the type of the Area class
           because we use it on class variables"""
        try:
            return cls._areas[name].code
        except KeyError:
            raise AttributeError("No area with this name")


class Area(six.with_metaclass(AreaType, object)):
    """Possible areas"""

    AreaDef = collections.namedtuple("AreaDef", ["code", "exchange", "zone", "caption"])

    _areas = dict(
        rwe=AreaDef("10YDE-RWENET---I", Exchange.epex, "germany", "Amprion"),
        rte=AreaDef("10YFR-RTE------C", Exchange.epex, "france", "RTE"),
        apg=AreaDef("10YAT-APG------L", Exchange.epex, "austria", "APG"),
        eon=AreaDef("10YDE-EON------1", Exchange.epex, "germany", "TenneT"),
        ve=AreaDef("10YDE-VE-------2", Exchange.epex, "germany", "50Hz"),
        enbw=AreaDef("10YDE-ENBW-----N", Exchange.epex, "germany", "TransnetBW"),
        ch=AreaDef("10YCH-SWISSGRIDZ", Exchange.epex, "switzerland", "Swissgrid"),
        nl=AreaDef("10YNL----------L", Exchange.epex, "netherlands", "NL"),
        be=AreaDef("10YBE----------2", Exchange.epex, "belgium", "BE"),
        uk=AreaDef("10YGB----------A", Exchange.epex, "uk", "UK"),
        dk1_epex=AreaDef("10YDK-1--------W", Exchange.epex, "denmark", "DK1"),
        dk2_epex=AreaDef("10YDK-2--------M", Exchange.epex, "denmark", "DK2"),
        fi_epex=AreaDef("10YFI-1--------U", Exchange.epex, "finland", "FI"),
        no1_epex=AreaDef("10YNO-1--------2", Exchange.epex, "norway", "NO1"),
        no2_epex=AreaDef("10YNO-2--------T", Exchange.epex, "norway", "NO2"),
        no3_epex=AreaDef("10YNO-3--------J", Exchange.epex, "norway", "NO3"),
        no4_epex=AreaDef("10YNO-4--------9", Exchange.epex, "norway", "NO4"),
        no5_epex=AreaDef("10Y1001A1001A48H", Exchange.epex, "norway", "NO5"),
        se1_epex=AreaDef("10Y1001A1001A44P", Exchange.epex, "sweden", "SE1"),
        se2_epex=AreaDef("10Y1001A1001A45N", Exchange.epex, "sweden", "SE2"),
        se3_epex=AreaDef("10Y1001A1001A46L", Exchange.epex, "sweden", "SE3"),
        se4_epex=AreaDef("10Y1001A1001A47J", Exchange.epex, "sweden", "SE4"),
        elia_epex=AreaDef("10YBE----------2", Exchange.epex, "belgium", "ELIA"),
        pl_epex=AreaDef("10YPL-AREA-----S", Exchange.epex, "poland", "PSE"),
        amp=AreaDef("10YDE-RWENET---I", Exchange.nordpool, "germany", "AMP"),
        dk_1a=AreaDef("10YDK-1-------AA", Exchange.nordpool, "denmark", "DK1A"),
        dk_1=AreaDef("10YDK-1--------W", Exchange.nordpool, "denmark", "DK1"),
        dk_2=AreaDef("10YDK-2--------M", Exchange.nordpool, "denmark", "DK2"),
        ee=AreaDef("10Y1001A1001A39I", Exchange.nordpool, "estonia", "EE"),
        fi=AreaDef("10YFI-1--------U", Exchange.nordpool, "finland", "FI"),
        fre=AreaDef("10YDOM-1001A084H", Exchange.nordpool, "fre", "FRE"),
        hr=AreaDef("10YHR-HEP------M", Exchange.nordpool, "hr", "HR"),
        hz=AreaDef("10YDE-VE-------2", Exchange.nordpool, "germany", "50HZ"),
        lt=AreaDef("10YLT-1001A0008Q", Exchange.nordpool, "lithuania", "LT"),
        lv=AreaDef("10YLV-1001A00074", Exchange.nordpool, "latvia", "LV"),
        nl_np=AreaDef("10YNL----------L", Exchange.nordpool, "nl", "NL"),
        be_np=AreaDef("10YBE----------2", Exchange.nordpool, "belgium", "BE"),
        no_1=AreaDef("10YNO-1--------2", Exchange.nordpool, "norway", "NO1"),
        no_1a=AreaDef("10Y1001A1001A64J", Exchange.nordpool, "norway", "NO1A"),
        no_2=AreaDef("10YNO-2--------T", Exchange.nordpool, "norway", "NO2"),
        no_3=AreaDef("10YNO-3--------J", Exchange.nordpool, "norway", "NO3"),
        no_4=AreaDef("10YNO-4--------9", Exchange.nordpool, "norway", "NO4"),
        no_5=AreaDef("10Y1001A1001A48H", Exchange.nordpool, "norway", "NO5"),
        se_1=AreaDef("10Y1001A1001A44P", Exchange.nordpool, "sweden", "SE1"),
        se_2=AreaDef("10Y1001A1001A45N", Exchange.nordpool, "sweden", "SE2"),
        se_3=AreaDef("10Y1001A1001A46L", Exchange.nordpool, "sweden", "SE3"),
        se_4=AreaDef("10Y1001A1001A47J", Exchange.nordpool, "sweden", "SE4"),
        tbw=AreaDef("10YDE-ENBW-----N", Exchange.nordpool, "germany", "TBW"),
        ttg=AreaDef("10YDE-EON------1", Exchange.nordpool, "germany", "TTG"),
        uj=AreaDef("10Y1001A1001A57G", Exchange.nordpool, "uk", "UK"),
        rte_np=AreaDef("10YFR-RTE------C", Exchange.nordpool, "france", "RTE"),
        brnn_np=AreaDef("IT-BRNN--------D", Exchange.nordpool, "IT", "BRNN"),
        cnor_np=AreaDef("IT-CNOR--------Y", Exchange.nordpool, "IT", "CNOR"),
        coac_np=AreaDef("IT-COAC--------U", Exchange.nordpool, "IT", "COAC"),
        cors_np=AreaDef("IT-CORS--------G", Exchange.nordpool, "IT", "CORS"),
        csud_np=AreaDef("IT-CSUD--------B", Exchange.nordpool, "IT", "CSUD"),
        fogn_np=AreaDef("IT-FOGN--------0", Exchange.nordpool, "IT", "FOGN"),
        malta_np=AreaDef("IT-MALT0-------R", Exchange.nordpool, "IT", "MALTA"),
        nord_np=AreaDef("IT-NORD--------N", Exchange.nordpool, "IT", "NORD"),
        prgp_np=AreaDef("IT-PRGP0-------R", Exchange.nordpool, "IT", "PRGP"),
        rosn_np=AreaDef("IT-ROSN--------8", Exchange.nordpool, "IT", "ROSN"),
        sard_np=AreaDef("IT-SARD--------F", Exchange.nordpool, "IT", "SARD"),
        sici_np=AreaDef("IT-SICI--------Y", Exchange.nordpool, "IT", "SICI"),
        sud_np=AreaDef("IT-SUD---------W", Exchange.nordpool, "IT", "SUD"),
        pt_np=AreaDef("10YPT-REN------W", Exchange.nordpool, "PT", "PT"),
        es_np=AreaDef("10YES-REE------0", Exchange.nordpool, "ES", "ES"),
        mo_np=AreaDef("10YMA-ONE------O", Exchange.nordpool, "MA", "MO"),
        ch_np=AreaDef("10YCH-SWISSGRIDZ", Exchange.nordpool, "CH", "CH"),
        apg_np=AreaDef("10YAT-APG------L", Exchange.nordpool, "AT", "APG"),
        bg_np=AreaDef("10YCA-BULGARIA-R", Exchange.nordpool, "BG", "BG"),
        ie_np=AreaDef("10Y1001A1001A59C", Exchange.nordpool, "IE", "IE"),
        pl_np=AreaDef("10YPL-AREA-----S", Exchange.nordpool, "PL", "PL"),
        gb2_np=AreaDef("10Y1001A1001A58E", Exchange.nordpool, "UK", "GB2"),
        cegh=AreaDef("10641392", Exchange.trayport, "austria", "EEXS: CEGH VTP"),
        ncg_h=AreaDef("10002785", Exchange.trayport, "germany", "EEXS: THE Hi Cal"),
        ncg_l=AreaDef("10641458", Exchange.trayport, "germany", "EEXS: THE Low Cal"),
        ncg=AreaDef("10002148", Exchange.trayport, "germany", "EEXS: THE"),
        ttf=AreaDef("10002806", Exchange.trayport, "netherlands", "EEXS: TTF Hi Cal 51.6"),
        nbp=AreaDef("10002317", Exchange.trayport, "uk", "EEXS: NBP"),
        peg=AreaDef("10642951", Exchange.trayport, "france", "EEXS: PEG"),
        pvb=AreaDef("10642965", Exchange.trayport, "spain", "PVB"),
        ztp=AreaDef("10002940", Exchange.trayport, "belgium", "EEXS: ZTP"),
        ztp_l=AreaDef("10641476", Exchange.trayport, "belgium", "EEXS: ZTP Low Cal"),
        zeebrugge=AreaDef("10002948", Exchange.trayport, "belgium", "EEXS: Zeebrugge"),
        czech_vtp=AreaDef("10002808", Exchange.trayport, "czech_republic", "EEXS: Czech VTP"),
        etf=AreaDef("10641346", Exchange.trayport, "denmark", "EEXS: ETF Denmark"),
        it_bl=AreaDef("10100480", Exchange.trayport, "italy", "Italy Baseload EEX Anon"),
        de_bl=AreaDef("10641710", Exchange.trayport, "germany", "Germany Baseload EEX"),
        hu_bl=AreaDef("10011036", Exchange.trayport, "hungary", "Hungary Baseload EEX"),
        be_bl=AreaDef("10012566", Exchange.trayport, "belgium", "Belgium Baseload EEX Anon"),
        nl_bl=AreaDef("10012534", Exchange.trayport, "netherlands", "Holland Baseload EEX Anon"),
        at_bl=AreaDef("10641714", Exchange.trayport, "austria", "Austria Baseload EEX"),
        ch_bl=AreaDef("10100484", Exchange.trayport, "netherlands", "Swiss Baseload EEX Anon"),
        ro_bl=AreaDef("10012526", Exchange.trayport, "romania", "Romania Baseload EEX"),
        fr_bl=AreaDef("10001075", Exchange.trayport, "france", "EEX France Baseload Anon"),
        es_bl=AreaDef("10012528", Exchange.trayport, "spain", "Spain Baseload EEX Anon"),
        nordic_bl=AreaDef("10012572", Exchange.trayport, "nordic", "Nordic Baseload EEX Anon"),
    )

    epex_short_delivery_names = {"50Hz": _areas["ve"].code,
                                 "Amprion": _areas["rwe"].code,
                                 "Tennet": _areas["eon"].code,
                                 "TransnetBW": _areas["enbw"].code}

    de_zone = list(epex_short_delivery_names.values())

    @classmethod
    def get_all(cls, exchange=None):
        if exchange is None:
            return [x.code for x in cls._areas.values()]
        else:
            return [x.code for x in cls._areas.values() if x.exchange == exchange]

    @classmethod
    def is_short_delivery_area(cls, area):
        return area in cls.epex_short_delivery_names

    @classmethod
    def get_area_by_short_delivery_name(cls, name):
        return cls.epex_short_delivery_names[name]

    @classmethod
    def get_zone(cls, area, exchange=Exchange.epex):
        """Get the zone for a specified area.

        The zones unite areas of the same country.

        :param area: Area for the zone to be found
        :type area: str
        :param exchange: Filter the area by this exchange
        :type exchange: Exchange
        :return: str
        """

        try:
            return [x.zone for x in cls._areas.values() if x.code == area and x.exchange == exchange][0]
        except IndexError:
            return None

    @classmethod
    def get_caption(cls, area, exchange=Exchange.epex):
        # type: (str, str) -> str or None
        """Get the caption for a specified area.

        The caption is a human readable title of the area.

        :param area: Area for the zone to be found
        :type area: str
        :param exchange: Filter the area by this exchange
        :type exchange: str
        :return: str or None
        """

        try:
            return [x.caption for x in cls._areas.values() if x.code == area and x.exchange == exchange][0]
        except IndexError:
            return None

    @classmethod
    def get_exchanges(cls, code):
        """Get the exchanges for a specified area code.

        :param code: Area code for the exchanges to be found
        :type code: str
        :return: list[Exchange]
        """

        try:
            return [x.exchange for x in cls._areas.values() if x.code == code]
        except IndexError:
            return None


class OrderType(object):
    order = "O"  # Regular limit order
    block = "B"  # User defined block order
    iceberg = "I"  # Iceberg order


class MarketState(object):
    active = "active"
    hibernated = "hibernated"


class TradingPhase(object):
    closed = "closed"  # The trading in the contract is closed for the current trading day.
    # The members will not be able to submit any new orders
    continuous = "continuous"  # The trading in the contract is in continuous mode.
    auction = "auction"  # The contract is in Auction phase.
    balancing = "balancing"  # The contract is in balancing phase.
    same_area = "same_area"  # The contract is in Same Delivery Area Trading phase

    EX2AT_CONVERTER = {
        Exchange.epex: {
            "CLSD": closed,
            "CONT": continuous,
            "AUCT": closed,
            "BALA": closed,
            "SDAT": continuous,
            "STBY": closed,
        },
        Exchange.nordpool: {
            continuous: continuous,  # Nord Pool does not have trading Phases, will be set to continuous by default
            closed: closed,
        }
    }

    @classmethod
    def convert(cls, exchange, state):
        return cls.EX2AT_CONVERTER[exchange][state]


class DeliveryAreaState(object):
    """Current state of the contract in a delivery area, and trading phase"""

    # contract states
    active = "active"  # Contract is active and available for trading in this delivery area.
    inactive = "inactive"  # The contract is inactive and not available for trading for this delivery area
    hibernated = "hibernated"  # the contract was manually deactivated for this delivery area by market operations.
    standby = "standby"  # Contract is waiting on external event to become available for trading.
    none = "none"
    balancing = "balancing"  # The contract is in balancing phase.
    deleted = "deleted"  # Delivery area was deleted. Trading not possible

    EX2AT_CONVERTER = {
        Exchange.epex: {
            "ACTI": active,
            "CONT": active,
            "CLSD": inactive,
            "IACT": inactive,
            "HIBE": inactive,
            "STBY": inactive,
            "DELE": inactive,
            "BALA": inactive,
            "SDAT": active
        },

        Exchange.nordpool: {
            "ACTI": active,
            "IACT": inactive,
            "HIBE": inactive,
            "FRZN": inactive,
        }
    }

    @classmethod
    def convert(cls, exchange, state):
        return cls.EX2AT_CONVERTER[exchange][state]


class GlobalInternalMarketMode(object):
    """Represents the option to active/deactivate the internal market according to the zones of the orders

    """
    active = 2  # activate the internal_market
    skip_de = 1  # skip conflicting orders from two different german zones
    skip = 0  # deactivate the internal market

    default = active


class ActorType(object):
    true = "Y"
    false = "N"
    unknown = "U"


class InternalExecutionMode(object):
    skip = -1  # this mode does not resolve a conflict if present
    no = 0  # this mode resolves an order conflict, without creating an internal trade
    exchange_base_price = 1  # resolves an order conflict, may lead to int.trades with price evaluated on the pub.orders
    average_price = 2  # resolves an order conflict, may lead to int.trades with avg price between the conflicted orders
    internal_only = 3  # this is for orders, which must not reach the exchange and can only be used for internal market
    default = exchange_base_price

    available_execmodes = (skip, no, exchange_base_price, average_price, internal_only)


class InternalOrderStatus(object):
    entered = "E"
    modified = "M"
    unchanged = "U"
    hibernated = "H"
    active = "A"
    old = "O"  # Order on the exchange, for which there is already a modification request

    com_trader_status = [hibernated, active]
    hidden_order_status = [hibernated, entered]


class StatusTopic(object):
    """Sent to status port"""
    heartbeat = "heartbeat"  # tells that component is alive
    change = "change"  # informs about a status change, like disconnect or connect


class ExecutionRestriction(object):
    default = "NON"
    non = "NON"  # No execution restriction
    fok = "FOK"  # Fill Or Kill  (full execution, or cancel all)
    ioc = "IOC"  # Immediate Or Cancel (at least partial execution, cancel remainder)
    aon = "AON"  # All or None

    trayport_trade_orders = fok, ioc
    available_execution_restrictions = non, fok, ioc, aon


class ValidityRestriction(object):
    non = "NON"  # No validity restriction
    gfs = "GFS"  # Good for trading session
    gtd = "GTD"  # Good till date
    gfd = "GFD"  # Good for day


class OrderState(object):
    hibe = "HIBE"
    acti = "ACTI"
    iact = "IACT"
    unknown = "UKNW"  # order state is unknown, this can happen e.g. during a M7 XBID disconnect (SIDC maintenence)
    pending = "PENDING"  # order reached back-end (acknowledged) and is about to be processed.
    # in some cases actual order processing, such as in XBID, may take some time.
    rejected = "REJECTED"


class TrayportOrderState(object):
    hibe = "Withheld"
    acti = "Firm"


class OrderAction(object):
    added = "ADD"
    hibernated = "HIB"
    modified = "MOD"
    deleted = "DEL"
    queried = "QRADD"
    user_added = "UADD"  # Order added by user.
    user_hibernated = "UHIB"  # Order deactivated by user.
    user_modified = "UMOD"  # Order modified by user.
    user_deleted = "UDEL"  # Order deleted by user.
    user_rejected = "UREJ"  # Pre-arranged order rejected by user.
    market_added = "AADD"  # Order added by market operations on behalf.
    market_hibernated = "AHIB"  # Order deactivated by market operations on behalf.
    market_modified = "AMOD"  # Order modified by market operations on behalf.
    market_deleted = "ADEL"  # Order deleted by market operations on behalf.
    market_rejected = "AREJ"  # Pre-arranged order rejected by market operations on behalf.
    system_added = "SADD"  # Order added by the system.
    system_hibernated = "SHIB"  # Order deactivated by the system.
    system_modified = "SMOD"  # Order modified by the system.
    system_deleted = "SDEL"  # Order deleted by the system.
    system_rejected = "SREJ"  # Pre-arranged order rejected by system.
    full_execution = "FEXE"  # Order is fully executed.
    partial_execution = "PEXE"  # Partial execution of order.
    iceberg_slice_added = "IADD"  # A new slice of an Iceberg order was added to the service
    quote_added = "QADD"  # Quote was added
    quote_full_execution = "QFEX"  # Quote was fully executed
    quote_partial_execution = "QPEX"  # Quote was partially executed
    state_unknown = "SNAV"  # Order state is unknown due to SOB unavailability
    order_validation_failed = "SERR"  # Order validation failed on SOB side or the request was timed out


class TradeState(object):
    cancelled = "CNCL"  # Trade was cancelled by market operations.
    recall_request_rejected = "RREJ"  # Requested Recall was rejected by market operations.
    recall_granted = "RGRA"  # Requested Recall was granted by market operations.
    recall_requested = "RREQ"  # Recall of this trade was requested. #
    active = "ACTI"  # Trade is active (this is the default value).
    cancel_requested = "CREQ"  # cancel was requested from local market operations.
    cancel_rejected = "CREJ"  # cancel was rejected by global market operations.
    request_approval = "RSFA"  # Request sent for approval to SOB (XBID)


class Response(object):
    init_response = "initial_refresh_response"
    market_state = "market_state"
    public_trade = "public_trade"
    own_trade = "own_trade"
    own_order = "own_order"
    internal_trade = "internal_trade"
    order_execution = "order_execution"
    order_book = "order_book"
    error_response = "error_response"
    product = "product"
    logout_response = "logout_response"
    capacities = "capacities"
    heartbeatping = "heartbeatping"
    configuration = "configuration"
    public_statistics = "public_statistics"
    delivery_areas_info = "delivery_areas_info"
    strategy = "strategy"
    ack_response = "ack_response"
    internal_order_execution = order_execution
    internal_order_reject = "order_reject"
    internal_trade_lock = "trade_lock"
    password_changed = "password_changed"
    exchange_halt = "exchange_halted"
    internal_messages = [internal_trade, internal_order_execution, internal_order_reject, internal_trade_lock]


class TrayportResponse(Response):
    user_info = "user_info"
    inst_definitions = "inst_definitions"
    inst_properties = "inst_properties"
    sequences = "sequences"
    sequence_items = "sequence_items"
    term_format = "term_format"
    companies = "companies"
    trade_list = "trade_list"
    init_finished = "init_finished"
    routes = "routes_to_market"
    venue_connection = "venue_connection_info"
    delete_all_succeeded = "delete_all_succeeded"


class TrayportInitFileNames(object):
    inst_definitions = "inst_definitions.jsonl"
    sequence_items = "sequence_items.jsonl"
    term_format = "term_format.jsonl"
    inst_properties = "inst_properties.jsonl"


class EpexResponse(Response):
    omt_status = "omt_status_response"
    system_info = "system_info"
    message_report = "message_report_response"


class Request(object):
    init = "initial_refresh_request"
    order_entry = "order_entry_request"
    order_activate = "order_activate_request"
    order_modify = "order_modify_request"
    order_delete = "order_delete_request"
    order_deactivate = "order_deactivate_request"
    order_reactivate = "order_reactivate_request"
    order_delete_all = "order_delete_all_request"
    order_deactivate_all = "order_deactivate_all_request"
    order_activate_all = "order_activate_all_request"
    own_trade = "own_trade_request"
    internal_trade = "internal_trade_request"
    public_trade = "public_trade_request"
    market_state = "market_state_request"
    order_book = "order_book_request"
    trade_list = "trade_list_request"
    my_order_book = "my_order_book_request"
    my_trade_list = "my_trade_list_request"
    own_orders = "own_orders_request"
    product = "product_request"
    trade_recall = "trade_recall_request"
    logout_request = "logout_request"
    strategy = "strategy_request"
    set_api_opts = "set_api_options"
    change_password = "change_password_request"
    set_password = "set_password_request"


class TrayportRequest(Request):
    user_info = "own_user_info_request"
    order_book_sub = "order_book_subscribe"
    trade_list_sub = "trade_list_subsctibe"
    my_order_book_sub = "my_order_book_subscribe"
    my_trade_list_sub = "my_trade_list_subscribe"
    inst_definition = "inst_definition_request"
    sequences = "sequences_request"
    companies = "companies_request"
    sequence_items = "sequence_items_request"
    inst_properties = "inst_properties_request"
    term_format = "term_format_request"
    trade_order = "trade_order_request"
    init_request = "init_trayport_request"
    relogin = "relogin_request"


class EpexRequest(Request):
    omt_status = "omt_status_request"
    system_info = "system_info_request"


# Whitelist for safe messages in readonly mode.
READONLY_MESSAGES = (Request.init,
                     Request.public_trade,
                     Request.market_state,
                     Request.order_book,
                     Request.trade_list,
                     Request.product,
                     Request.logout_request,
                     EpexRequest.system_info,
                     Request.set_api_opts,
                     Request.change_password,
                     TrayportRequest.user_info,
                     TrayportRequest.order_book_sub,
                     TrayportRequest.trade_list_sub,
                     TrayportRequest.inst_definition,
                     TrayportRequest.sequences,
                     TrayportRequest.companies,
                     TrayportRequest.sequence_items,
                     TrayportRequest.inst_properties,
                     TrayportRequest.term_format,
                     TrayportRequest.init_request,
                     TrayportRequest.relogin,
                     EpexRequest.omt_status)


class InitCorrelationIds(object):
    """
    :meta: private
    """
    trayport_init = "trayport-init"
    nordpool_init = "nordpool-init"
    epex_init = "init"

    class Topic(object):
        delete_all = "DA"
        inst_properties = "IP"
        inst_definitions = "ID"
        sequence_items = "SI"
        term_formats = "TF"
        trading_data = "TD"


class TimerEvent(object):
    timer_fast = "timer_fast"
    timer = "timer"


class M7RoutingKey(object):
    management = "m7.request.management"
    throttling = "m7.request.inquiry.throttling"
    inquiry = "m7.request.inquiry"


class RateLimitType(object):
    class Epex(object):
        short = "short"
        long = "long"


class ThrottlingState(object):
    NON_BLOCKING = "NON_BLOCKING"
    BLOCKING = "BLOCKING"


class EpexOMTState(object):
    RESTRICTED = "RESTRICTED"
    NO_RESTRICTION = "NO_RESTRICTION"
    WARNING = "WARNING"


class OrderTagKeys(object):
    # For trade-orders, we store the order-id as a tag as well, because the trade might have a different id.
    product_id = "product_id"
    internal_orders_broker_id = "original_broker"


class RejectReason(object):
    """
    Reasons why the autoTRADER parent might reject a modification request sent by the child.

    Not every reject message must have a reason (we reject every modification request that we do not send
    to the exchange), but if it has a reason, the reason should start with one of the constants defined here.

    .. note::

        The strings defined here can be directly visible in the synthetic order status and are exposed to customers via
        the REST- and push-API and can thus be visible on the Joule Screen. So they should be human readable.
    """
    price_moved_by_internal_market = "Price shifted by the internal market/ cross-trade protection"


class ErrorMsgs(object):
    request_timeout = "Request timed out"
    request_expired = "Request has expired"
    pwd_changed = "CONNECTION_FORCED - PWD_CHANGE"


class EpexErrorCodes(object):
    """
    Error codes used in EPEX error responses
    """
    concurrent_update = "12580"  # If we specify an old revision on an order modification/ delete request.
    order_not_found = "2014"  # If we try to modify/ delete an order that (no longer) exists (based on order_id)

    order_id_variable = {
        concurrent_update: "0",
        order_not_found: "0"
    }


class EpexVars(object):
    user_code = "0"
    member = "20"
    omt_status_general = "26"
    omt_status_changed_date = "27"
    omt_short_info = "28"
    omt_long_info = "29"
    account = "30"
    correlation_id = "31"
    client_order_id_max_len = 40


class EpexMessageCodes(object):
    no_throttling = "166"
    throttling = "168"


class ResolverState(object):
    entry_orders = "entry_orders"
    modify_orders = "modify_orders"
    delete_orders = "delete_orders"
    delete_all_orders = "delete_all_orders"
    deactivate_orders = "deactivate_orders"
    activate_orders = "activate_orders"
    trade_orders = "trade_orders"
    internal_trades = "internal_trades"
    internal_order_executions = "order_executions"
    internal_order_reject = "order_reject"
    internal_trade_lock = "trade_lock"
    # when sending a delete request to an exchange for a product which is locked it is fairly likely
    # that the venue will reject the whole bunch of delete requests [if it does not support partial reject]
    # therefore, we send delete messages for locked products separately to be extra-safe in such case
    delete_orders_for_locked_product = "delete_orders_for_locked_product"

    internal_messages = [internal_trades, internal_order_executions, internal_order_reject, internal_trade_lock]


class OrderEntry(collections.namedtuple("OrderEntry", "status order")):
    """Class extending parameters and representation of :class:`API.OwnOrder`

    The class inherits from :class:`collections.namedtuple` and assigns to each order
    of the type :class:`API.OwnOrder` or :class:`API.ComTraderOrder` a status
    reflecting the order state relative to the exchange/market.

    :param status: status of the order relative the market
    :param order: order to be extended
    :type status: :class:`COMMON.InternalOrderStatus`
    :type order: :class:`API.OwnOrder` or :class:`API.ComTraderOrder`

    .. seealso:: available status in :class:`COMMON.InternalOrderStatus`
    """

    def __repr__(self):
        order_class_type = self.order.__class__.__name__
        order_type = self.order.order_type
        price = getattr(self.order, "price", None)
        internal_market_price = self.order.internal_market_price
        quantity = getattr(self.order, "quantity", None)
        direction = getattr(self.order, "direction", None)
        order_id = getattr(self.order, "order_id", None)
        delivery_area = getattr(self.order, "delivery_area_id", None)
        execmode = getattr(self.order, "execmode", None)
        execution_restriction = getattr(self.order, "execution_restriction", None)

        return ("\n<OrderEntry {}: {} {} {} price {}; int-price {}; qty {}; {}; "
                "order_id {}; restr {}; execmode: {}>"
                ).format(self.status, order_class_type, order_type,
                         direction, price, internal_market_price, quantity, delivery_area, order_id,
                         execution_restriction, execmode)


class TradeFilter(object):
    """Supplies the filter expressions for the Trade.get(...) method.

    Usage:
        *TradeFilter.own returns* all own trades

        *TradeFilter.own_exchange* returns all own trades from the exchange (excluding internal executions)

        *TradeFilter.internal* returns all internally executed trades

        *TradeFilter.public* returns all public trades (not own trades)

        *TradeFilter.own_buy* returns only own buy trades

        *TradeFilter.own_sell* returns only own sell trades

        *TradeFilter.own_exchange_buy* returns only own buy trades made on an exchange

        *TradeFilter.own_exchange_sell* returns only own sell trades made on an exchange

        *TradeFilter.internal_buy* returns only internal own buy trades

        *TradeFilter.internal_sell* returns only internal own sell trades

        *TradeFilter.no_filter* applies no filter at all
    """
    own = "own_internal_buy_sell"
    own_exchange = "own_buy_sell"
    internal = "internal_buy_sell"
    public = "public_buy_sell"
    own_buy = "own_internal_buy"
    own_sell = "own_internal_sell"
    own_exchange_buy = "own_buy"
    own_exchange_sell = "own_sell"
    internal_buy = "internal_buy"
    internal_sell = "internal_sell"
    no_filter = None

    @classmethod
    def properties(cls, trade_filter):
        properties = {"own": True,
                      "internal": True,
                      "public": True,
                      "buy": True,
                      "sell": True}
        if trade_filter is None:
            return properties
        for prop in properties:
            if prop not in trade_filter:
                properties[prop] = False
        return properties


class OrderFilter(object):
    """Supplies the filter expressions for the OrderBook.get(...) method.

    Usage:
        *OrderBook.own returns* all own orders

        *OrderBook.public* returns all public orders

        *OrderBook.own_buy* returns all own buy orders (bid)

        *OrderBook.public_buy* returns all public buy orders (bid)

        *OrderBook.own_sell* returns all own sell orders (ask)

        *OrderBook.public_sell* returns all public sell orders (ask)

        *OrderBook.buy* returns all buy orders (own and public)

        *OrderBook.sell* returns all sell orders (own and public)

        *OrderBook.no_filter* applies no filter at all
    """
    own = "own_com_buy_sell"
    com_trader = "com_buy_sell"
    public = "public_buy_sell"
    own_buy = "own_com_buy"
    public_buy = "public_buy"
    own_sell = "own_com_sell"
    public_sell = "public_sell"
    com_sell = "com_sell"
    com_buy = "com_buy"
    buy = "own_com_public_buy"
    sell = "own_com_public_sell"
    com_public_buy = "com_public_buy"
    com_public_sell = "com_public_sell"
    only_buy = "buy"
    only_sell = "sell"
    no_filter = None

    @classmethod
    def properties(cls, order_filter):
        properties = {"own": True,
                      "com": True,
                      "public": True,
                      "buy": True,
                      "sell": True}
        if order_filter is None:
            return properties
        for prop in properties:
            if prop not in order_filter:
                properties[prop] = False
        return properties


class InstanceLockState(object):
    confirm_one = "CONF_ONE"
    confirm_all = "CONF_ALL"
    added = "ADD"
    added_negative = "ADDNEG"


class UniqueIDGenerator(object):
    usechars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self):
        self.counter = 0

    @staticmethod
    def get_process_designation():
        return os.getpid()

    def _make_hash(self, to_hash, char_len):
        uclen = len(self.usechars)
        result = []
        for _ in range(char_len):
            temp_char = int(to_hash % uclen)
            result.append(self.usechars[temp_char])
            to_hash -= temp_char
            to_hash /= uclen
        return "".join(result)

    def get_uid(self):
        # theoretically, for timestamp_hash with char len 5 we will
        # get a collision after 916 million hundredths of a second (62^5)
        # so we're using mod 900000000
        timestamp = time.time()
        timestamp_hash = int(timestamp * 100)
        timestamp_hash = timestamp_hash % 900000000

        # theoretically, for counter_hash with char len 3 we will
        # get a collision after 238328 orders (62^3)
        # so we're using mod 200000
        self.counter += 1
        counter_hash = self.counter % 200000

        # TODO: with worker numbers, reduce pid hash to length 2
        return (
            self._make_hash(self.get_process_designation(), 3)
            + self._make_hash(timestamp_hash, 5)
            + self._make_hash(counter_hash, 3)
        )


class ParentChildMessages(object):
    """Defines message types being sent between parent and child processes"""
    child_initialized = "child_initialized"
    begin_exchange_restart = "begin_exchange_restart"
    exchange_restarted = "exchange_restarted"
    exchange_initialized = "exchange_initialized"
    forward_to_pt = "forward_to_pt"
    strategy_request = "strategy_order_request"
    exchange_halt = "exchange_halt"
    exchange_resume = "exchange_resume"
    trading_halt = "trading_halt"
    trading_resume = "trading_resume"
    strategy_stop = "strategy_stop_request"
    child_request_exchange_restart = "child_request_exchange_restart"
    backtesting_start = "backtesting_start"  # Used to send the timestamp for backtesting


class MongoDBObjects(object):
    """Defines the object_type values for MongoDB"""
    strategy_steering = "StrategySteeringObject"
    strategy = "StrategyObject"
    strategy_configuration = "StrategyConfigurationObject"
    market_state_timeseries = "MarketStateTimeseries"
    dump_strategy_request = "DumpStrategyRequest"
    per_product_limits = "PerProductLimitMessage"
    synthetic_order = "SyntheticOrder"  # A SO REQUEST from the REST-API to AutoTRADER
    synthetic_order_state = "SyntheticOrderState"
    synthetic_order_type = "SyntheticOrderType"
    package = "Package"
    action_limits = "ActionLimits"
    solver = "solver"
    strategy_persistence = "StrategyPersistence"
    product = "Product"


class RoutingKey(object):
    """ZMQ Routing keys for adapter communication"""
    rest_api = b"REST-API"


class HistorySpreadMethod(object):
    """Allowed values for history spread calculations for synethtic orders"""
    get_max = "max"
    get_min = "min"
    get_avg = "avg"
    __slots_container_py2__ = [get_max, get_min, get_avg]


class TradingCapacityType(object):
    """Allowed values for mifid field TradingCapacity, used for place slots when trading on Trayport"""
    __slots_container_py2__ = ["DEAL", "MTCH", "AOTC"]

    DEAL = "DEAL"
    MTCH = "MTCH"
    AOTC = "AOTC"


class SimulationUserExchange(object):
    trayport_user = "TRAYPORT_SIMULATION"
    epex_user = "EPEX_SIMULATION"
    nordpool_user = "NORDPOOL_SIMULATION"


class PerProductLimits(object):
    maximum_purchase_volume = "maximum_purchase_volume"
    maximum_sales_volume = "maximum_sales_volume"
    maximum_purchase_price = "maximum_purchase_price"
    minimum_sales_price = "minimum_sales_price"

    supported_limits = (maximum_purchase_price, maximum_purchase_volume, maximum_sales_volume, minimum_sales_price)


class SlotResponseAction(object):
    """
    Used as action in SlotResponse objects.

    ignore means that nothing is sent to autoTRADER, create, modify and delete mean that entry/ modify/delete
    order request is sent to autoTRADER.

    Note that this does not guarantee that the orders are also sent to the exchange, as asynchronous processes inside
    autoTRADER may prevent sending of the order (e.g. internal market or order_guard)
    """
    ignore = "ignored"
    create = "created"
    modify = "modified"
    delete = "deleted"
    no_order = "no_order"  # Special case, if the strategy placed 0 quantity and no corresponding order exists.


class SlotResponseReason(object):
    """
    Used in SlotResponse objects as reasons why a slot resulted in an order or did not result in an order.

    As synthetic orders have handling based on the SlotResponseReason, make sure to also adjust
     :py:meth:`~SyntheticOrderStrategyBase._update_so_state_based_on_slotresponse` if you adjust this list
    """
    duplicate_name = "duplicate name"  # The strategy is trying to place 2 slots with the same slot type
    duplicate_orders = "duplicate orders on the exchange"  # There are 2 orders for this slot type on the exchange.
    unconfirmed_order = "unconfirmed order entry"  # For this slot name
    missing_direction = "missing direction"  # The direction is None
    nonfinite_quantity = "nonfinite quantity"  # The quantity is not a finite number (nan, inf or None)
    nonfinite_price = "nonfinite price"  # The price is not a finite number (nan, inf or None)
    limit_sale_price = "sale price limit violated"
    invalid_limit_sale_price = "invalid sale price limit"
    limit_buy_price = "purchase price limit violated"
    invalid_limit_buy_price = "invalid purchase price limit"
    iceberg_large_clip = "clip quantity larger than quantity"
    iceberg_invalid_clip_qty = "clip quantity is invalid"
    invalid_block_exec_restriction = "execution restriction invalid for block order"
    tp_broker_unset = "missing broker"
    tp_broker_must_be_string = "broker_id should be a string"
    tp_broker_unchangeable = "broker changed"
    tp_invalid_broker_area_combination = "broker not allowed for this area"
    tp_price_tick_size_violation = "price violates tick size"
    tp_quantity_tick_size_violation = "quantity violates tick size"
    tp_min_quantity_violation = "minimum quantity not reached"  # The broker's minimum quantity for this area / product
    direction_changed = "direction changed"  # Changing an order from buy to sell leads to a delete request
    unchanged = "unchanged"  # The order is not modified, as it is already in the correct state
    ok = ""  # Used if everything worked as expected and there is no other reason.
    derivative_indicator_not_bool = "derivative_indicator must be boolean type or None"
    liquidity_provision_not_bool = "liquidity_provision must be boolean type or None"
    dea_not_bool = "dea must be boolean type or None"
    decision_maker_not_string = "decision_maker must be a string or None"
    execution_maker_not_string = "execution_maker must be a string or None"
    dea_client_id_not_string = "dea_client_id must be a string or None"
    wrong_trading_capacity = "trading_capacity must be one of {} or None".format(
        "/".join(TradingCapacityType.__slots_container_py2__))
    mifid_fields_changed = "mifid fields cannot be changed for existing orders"
    exec_restriction_changed = "execution restriction changed"
    wrong_exec_restriction = "execution_restriction must be one of {}".format(
        "/".join(ExecutionRestriction.available_execution_restrictions))
    no_matching_order = "{} order didn't match any public order"
    terms_not_list_type = "terms must be of type 'list' or None"
    omt_too_high = "order-management-transaction count is too high for placement"
    inactive_area = "inactive area"
    hibernated = "won't modify hibernated order"  # A manual trader should delete the hibernated order to solve this.
    market_halt = "market halt"
    outside_strategy_validity = "outside strategy's validity"
    placement_too_deep_on_own_side = "placement too deep on own side"
    exchange_not_initialized = "exchange is not initialized"


class HaltReasonAutotrader(object):
    RESTART_AT = "autoTRADER is being restarted"
    HALTED_BY_USER_ORDERS_REMOVED = "halted by user; orders are removed"
    HALTED_BY_USER_ORDERS_NOT_REMOVED = "halted by user; orders are not removed"
    USER_DISCONNECTED = "User disconnected"


class ActionLimits(object):
    version = "VERSION"
    filename = "action_limits.json"
    limit = "action_rate_limit"
    interval = "action_rate_interval"
    broker = "avg_action_limit_month"
    product = "avg_pdt_action_limit_month"

    action_limit_keys = (limit, interval)
    HFT_limit_keys = (broker, product)


class BrokerSpecs(object):
    version = "VERSION"
    # File which defines the special handling for combined orders for brokers,
    # which sum up orders on the same price levels
    filename = "jd_manager_config.json"
    does_combine_public_orders = "combined_orders"
    does_not_support_tradeorders = "disable_tradeorders"
    does_match_quantity_for_execution_lock_release = "multimatching_trade_lock_release"
    cannot_hibernate_orders = "cannot_hibernate_orders"
    valid_keys = (does_not_support_tradeorders, does_combine_public_orders,
                  does_match_quantity_for_execution_lock_release, cannot_hibernate_orders)


class NordpoolMessageSequenceType(object):
    """
    Used in NordpoolManager to make distinction of the results of message sequence check.
    """
    snapshot = "sequence number of a snapshot message"  # The sequence number is accepted as a starting value
    heartbeat = "heartbeat message came"  # Don't care about the sequence number of heartbeat messages
    error = "sequence number is too small"  # This sequence number was already processed, so we have a fatal error
    wrong = "sequence number is too big"  # The message is stored in failing message buffer, might be restored later
    bad_sub_error = "subscription ID does not belong to a registered destination and tolerance limit exceeded"
    bad_sub_wrong = "subscription ID does not belong to a registered destination but still within tolerance limit"
    correct = "sequence number is OK"  # The incoming sequence number equals with the expected value


class PeriotheusSystemUsers(object):
    """
    Class to keep system users for compliance logging
    """
    users = ("aggregator", "scheduler", "root")
    system = "SYSTEM"
    unset = "UNSET"
    periotheus = Exchange.periotheus
    autotrader = Exchange.autotrader

    @staticmethod
    def get_username_from_obj(obj, key):
        """
        Returns username from obj, and changes it if needed.
        :param obj: object instance to get username from
        :type obj: dict
        :param key: key name for username in obj
        :type key: str
        :returns: username from obj, or Exchange.periotheus if name is a system user, or "UNSET" otherwise
        :rtype: str
        """
        username = obj.get(key, PeriotheusSystemUsers.unset)
        return PeriotheusSystemUsers.periotheus if username in PeriotheusSystemUsers.users else username


class StrategyType(object):
    """
    Class to keep strategy type for compliance logging
    """
    own = "OWN"
    custom = "CUSTOM"


class SupportedStrategies(object):
    """Keep track of the officially supported strategies.
    (name: mongo_name) key-value pairs where 'mongo_name' represents the value which is stored in mongo
    """
    algorithms = {"spontaneous_position_closing_strategy": "LINEAR_CLOSE",
                  "position_closing_strategy": "VOLUME_CLOSE",
                  "manual_trading_strategy": "MANUAL_TRADING",
                  "gas_arbitrage": "GAS_ARBITRAGE",
                  "gas_position_closer": "GAS_POSITION_CLOSER",
                  "gas_strategy_storage": "GAS_STORAGE",
                  "custom_strategy": "USERDEF",
                  "flex_strategy_v2": "PWR_FLEX_V2",
                  }

    # this list should be completed everytime a new template for a own_strategy is created
    supported = ["custom_strategy"]

    @classmethod
    def get_all(cls):
        return list(cls.algorithms.keys())

    @classmethod
    def get_by_commodity(cls, commodity):
        """ Get the strategy according to the commodity passed in parameter.
        :type commodity: str element of ["power", "gas"]
        :rtype list
        """
        names = list(cls.algorithms.keys())
        if commodity == "gas":
            names = [name for name in cls.algorithms.keys() if name.startswith("gas")] + ["custom_strategy"]
        elif commodity == "power":
            names = [name for name in cls.algorithms.keys() if not name.startswith("gas")]
        return names

    @classmethod
    def get_algorithm_name_mongo(cls, name):
        """ Get the name of the algorithm used in mongo from the strategy name.
        :param name: strategy name
        :type name: element of cls._supported.keys()
        :return the code of the strategy passed in parameters or USERDEF
        :rtype str (element of cls._supported.values())
        """
        return cls.algorithms.get(name, "USERDEF")

    @classmethod
    def get_algorithm_from_mongo_name(cls, code):
        """ Get the strategy name from the name used in mongo
        :param code: strategy name as it is written in mongo
        :type code: element of cls._supported.values()
        :return the code of the strategy passed in parameters or custom_strategy
        :rtype str (element of cls._supported.keys())
        """
        reverted = {value: key for key, value in six.iteritems(cls.algorithms)}
        return reverted.get(code, "custom_strategy")


class SyntheticOrderOperations(object):
    """ Used to identify the received operation type for synthetic orders """
    register = "register"
    modify = "modify"
    delete = "delete"


class SyntheticOrderStates(object):
    """ Used to identify the current state of synthetic orders """
    inserting = "inserting"  # The SO has placed a non-zero slot, but is still waiting for exchange confirmation.
    active = "active"  # placing orders
    deleting = "is deleting"  # being deleted but the order might still be on the market for some time
    passive = "passive"  # not placing orders (not withheld)
    withheld = "withheld"  # withheld by user and not placing orders
    warning = "warning"  # warning about not being able to place orders because of e.g. limit violations
    faulted = "faulted"  # error coming from either guard or market


class SyntheticMessageType(object):
    """ Used to identify different types of synthetic order payloads """
    order = "synthetic_order"
    selector = "synthetic_selector"


class TradeStatisticsMetric(object):
    """ Comprises the usable trade statistics metric names in local views """
    __slots_container_py2__ = [
        "vwap", "first_price", "low_price", "high_price", "last_price", "last_change", "volume_buy", "volume_sell"
    ]
    vwap = "vwap"
    low_price = "low_price"
    high_price = "high_price"
    first_price = "first_price"
    last_price = "last_price"
    last_change = "last_change"
    volume_buy = "volume_buy"
    volume_sell = "volume_sell"


class AggregatorRule(object):
    max = "max"
    min = "min"
    avg = "avg"
    max_nonone = "max_nonone"
    min_nonone = "min_nonone"
    avg_nonone = "avg_nonone"

    max_set = frozenset([max, max_nonone])
    min_set = frozenset([min, min_nonone])
    avg_set = frozenset([avg, avg_nonone])
    none_set = frozenset([max_nonone, min_nonone, avg_nonone])


class StrategyJsonKey(object):
    """Standard fields transferred from Periotheus to Autotrader on transfer strategy"""

    # this field contains all the userdefined timeseries set for strategies
    user_defined_timeseries = "user_defined_timeseries"
    # The fallback for the delivery area is market area. For some strategies like arbitrage,
    # up to 5 market areas can be defined via rest API, that is why we need market_area_2-5
    market_area = "market_area"
    market_area_1 = "market_area_1"
    market_area_2 = "market_area_2"
    market_area_3 = "market_area_3"
    market_area_4 = "market_area_4"
    market_area_5 = "market_area_5"
    # for all set market areas, Periotheus maps the corresponding exchange and send the info as well
    exchange = "exchange"
    exchange_1 = "exchange_1"
    exchange_2 = "exchange_2"
    # maximum bid and ask, which limit the order size which can be placed by an algo.
    # This is checked by the order guard
    maximum_bid = "maximum_bid"
    maximum_ask = "maximum_ask"
    # if this field is set to True, then the autotrader will halt the strategy on limit violation
    stop_on_limit_violation = "stop_on_limit_violation"

    # parameters by which the order guard stops flapping behaviour
    maximum_neg_buyback = "maximum_neg_buyback"
    neg_buyback_period = "neg_buyback_period"

    valid_from = "valid_from"
    valid_to = "valid_to"
    active = "active"
    username = "username"

    # values used by position closer, to detect low liquidity market and change behaviour
    llq_spread1_indicator = "llq_spread1_indicator"
    llq_spread1_limit = "llq_spread1_limit"
    llq_spread2_indicator = "llq_spread2_indicator"
    llq_spread2_limit = "llq_spread2_limit"
    # trading start. Position Closer is only standard strategy to use this.
    # Time before delivery start to start trading a product
    trading_start = "trading_start"

    # describes if passive of risky behaviour
    behavior = "behavior"

    # package with data about the strategy transferred
    package = "package"
    # internal number used to identify the strategy
    internal_number = "internal_number"
    # free text description
    caption = "caption"

    # additional parameters part of strategy definition
    maximum_order_book = "maximum_order_book"

    risk_affinity = "risk_affinity"

    standard_deviation_begin = "standard_deviation_begin"
    standard_deviation_end = "standard_deviation_end"

    minimum_sales_price = "minimum_sales_price"
    maximum_purchase_price = "maximum_purchase_price"

    maximum_sales_volume_per_product = "maximum_sales_volume_per_product"
    maximum_purchase_volume_per_product = "maximum_purchase_volume_per_product"

    minimum_spread_for_buyback = "minimum_spread_for_buyback"

    immediate_purchase_price = "immediate_purchase_price"
    immediate_sales_price = "immediate_sales_price"

    last_prognosis_before_market_closure = "last_prognosis_before_market_closure"
    trading_end_before_market_closure = "trading_end_before_market_closure"

    short_name = "short_name"
    packagename = "packagename"

    approved_privs = "approved_privs"

    global_privs = "global_privs"

    comment = "comment"
    approved_group = "approved_group"

    lifecycle = "lifecycle"
    owner_group = "owner_group"
    maximum_imbalance_on_market_closure = "maximum_imbalance_on_market_closure"
    algorithm = "algorithm"
    hour = "hour"

    grace_period_mode = "grace_period_mode"  # Power position closer additional parameters

    class TS(object):
        """Standard Timeseries names"""

        # necessary limit timeseries
        limit_sell_vol = "strategy_limit_maximum_sales_volume"
        limit_buy_vol = "strategy_limit_maximum_purchase_volume"
        limit_buy_price = "strategy_limit_maximum_purchase_price"
        limit_sell_price = "strategy_limit_minimum_sales_price"

        # standard timeseries sent by the autotrader
        pos_sell = "strategy_position_tradable_position_long"
        pos_buy = "strategy_position_tradable_position_short"
        price_buy = "strategy_price_purchase"
        price_sell = "strategy_price_sales"

        # additional behavioural timeseries used by some standard strategies such as position closer and flex
        price_min_spread_buyback = "strategy_price_minimum_spread_buyback"
        price_imm_buy = "strategy_price_purchase_immediate_vesting"
        price_imm_sell = "strategy_price_sales_immediate_vesting"
        pos_dev = "strategy_position_deviation"
        price_forecast_trend = "strategy_price_forecast_trend"
        risk_affinity = "risk_affinity"

    class UDFTS(object):
        """Userdefined timeseries names"""

        # Timeseries names used in standard flexibility algo
        pos_closed = "strategy_closed_positions_before_intraday"
        prod_filter = "strategy_products_filter"
        ramp_buy = "strategy_ramp_buy"
        ramp_sell = "strategy_ramp_sell"
        ramp = "strategy_ramp"
        omt = "strategy_omt"
        pos_sell_scale = "strategy_position_long_scale_{}"
        pos_buy_scale = "strategy_position_short_scale_{}"
        price_buy_scale = "strategy_tradeable_price_purchase_scale_{}"
        price_sell_scale = "strategy_tradeable_price_sales_scale_{}"

        # allow setting the orderbook depth limit for order updates for the position closing strategy
        # this is used to reduce OMT counts, by avoiding updates deep on the own side of the orderbook
        order_update_absolute_depth_limit = "strategy_order_update_absolute_depth_limit"
        order_update_relative_depth_limit = "strategy_order_update_relative_depth_limit"

    limits_per_sequence = "limits_per_sequence"

    class LimitKeys:
        max_buy_vol = "maximum_purchase_volume"
        min_sell_price = "minimum_sales_price"
        max_sell_vol = "maximum_sales_volume"
        max_buy_price = "maximum_purchase_price"


class EngineID(object):
    # Fixed Engine ID 99 used in simulation response
    simulation = "99"


class Roles(object):
    autotrader_get = "AUTOTRADER_GET"
    autotrader_status_get_object = "AUTOTRADER_STATUS_GET_OBJECT"
    autotrader_halt_action = "AUTOTRADER_HALT_ACTION"
    autotrader_resume_action = "AUTOTRADER_RESUME_ACTION"

    own_orders_get_all = "OWN_ORDERS_GET_ALL"
    own_trades_get_list = "OWN_TRADES_GET_LIST"

    roles_get_all = "ROLES_GET_ALL"
    role_get = "ROLES_GET_OBJECT"

    users_post = "USERS_POST"
    users_get_all = "USERS_GET_ALL"
    users_get = "USERS_GET_OBJECT"
    users_put = "USERS_PUT"
    users_delete = "USERS_DELETE"

    packages_get_list = "PACKAGES_GET_LIST"
    packages_post = "PACKAGES_POST"
    packages_get_object = "PACKAGES_GET_OBJECT"
    packages_delete = "PACKAGES_DELETE"

    algorithms_halt = "ALGORITHMS_HALT_ACTION"
    algorithms_resume = "ALGORITHMS_RESUME_ACTION"
    algorithms_activate = "ALGORITHMS_ACTIVATE_ACTION"
    algorithms_deactivate = "ALGORITHMS_DEACTIVATE_ACTION"
    algorithms_sequences = "ALGORITHMS_SEQUENCES_GET_ALL"

    algorithms_post = "ALGORITHMS_POST"
    algorithms_patch = "ALGORITHMS_PATCH"
    algorithms_get_list = "ALGORITHMS_GET_LIST"
    algorithms_get_object = "ALGORITHMS_GET_OBJECT"
    algorithms_get_limits = "ALGORITHMS_LIMITS_GET_ALL"
    algorithms_put_limits = "ALGORITHMS_LIMITS_PUT"
    algorithms_delete = "ALGORITHMS_DELETE"
    algorithms_steering_patch = "ALGORITHMS_STEERING_PATCH"

    algorithms_synthetic_get = "ALGORITHMS_SYNTHETIC_GET_ALL"
    algorithms_synthetic_post = "ALGORITHMS_SYNTHETIC_POST"
    algorithms_synthetic_patch = "ALGORITHMS_SYNTHETIC_PUT"
    algorithms_synthetic_delete = "ALGORITHMS_SYNTHETIC_DELETE"

    market_changes_since_get = "MARKET_CHANGES_SINCE_GET_ALL"


class MongoCollections(object):
    state = "state"
    users = "users"
    own_trades = "own_trades"
    strat_history = "strategy_history"
