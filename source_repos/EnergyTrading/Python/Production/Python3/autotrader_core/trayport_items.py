#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import collections
import datetime
from dateutil import rrule, relativedelta

import autotrader_lib.common as COMMON
import autotrader_core.trayport_trading_calendar as TRCAL
import autotrader_core.utils
import autotrader_lib.cet_util as CETUTIL
from six.moves import range

_AREA_IDS = COMMON.Area.get_all(exchange=COMMON.Exchange.trayport)

TRADING_END_DELTA = 15  # remove 15 sec before trading ends
START_GAS_DAY = 6 * COMMON.HOUR
START_TRADING_DAY = 3 * COMMON.HOUR


class _ItemInterval(object):
    def __init__(self, delivery_start, delivery_end, trading_start, trading_end, name):
        """

        :type delivery_start: float
        :type delivery_end: float
        :type trading_start: float
        :type trading_end: float
        :type name: str
        """
        self.trading_start = trading_start
        self.trading_end = trading_end
        self.delivery_start = delivery_start
        self.delivery_end = delivery_end
        self.name = name

    def __repr__(self):
        return "delivery start: {}; delivery end: {}; trading start: {}; trading end: {}; name: {}".format(
            self.delivery_start, self.delivery_end, self.trading_start,
            self.trading_end, self.name)

    def __str__(self):
        return (
            "delivery start: {:%a %Y-%m-%d %H:%M:%S} CE(S)T; "
            "delivery end: {:%a %Y-%m-%d %H:%M:%S} CE(S)T; "
            "trading start: {:%a %Y-%m-%d %H:%M:%S} CE(S)T; "
            "trading end: {:%a %Y-%m-%d %H:%M:%S} CE(S)T; "
            "name: {}".format(
                CETUTIL.utc_ts2cet_dt(self.delivery_start),
                CETUTIL.utc_ts2cet_dt(self.delivery_end),
                CETUTIL.utc_ts2cet_dt(self.trading_start),
                CETUTIL.utc_ts2cet_dt(self.trading_end),
                self.name))


class BaseItem(object):
    def __init__(self, record):
        """ Interface

        :param record: record object holding the item data
        :type record: `autotrader_core.trayport_records.Record`
        """

        def _set_trading_day(timestamp, nb_hours):
            """ Sets the gas day according to nb_hours"""
            try:
                unused_prod_day, prod_start_day_start, unused_prod_start_day_end = \
                    autotrader_core.utils.cet_date_of_timestamp(timestamp)
                ret = prod_start_day_start + nb_hours
            except AssertionError:  # means the timestamp is in the past
                ret = timestamp
            return ret

        self.item_id = record.item_id
        self.name = record.item_name
        delivery_day_start = START_GAS_DAY if record.gas else 0
        trading_day_start = START_TRADING_DAY if record.gas else 0

        # products which are equal or longer to a day need to account for the trade day start differences in commodities
        if record.delivery_end - record.delivery_start >= COMMON.HOUR * 24:
            self.trading_start = _set_trading_day(record.trading_start, trading_day_start)
            self.trading_end = _set_trading_day(record.trading_end, trading_day_start) - TRADING_END_DELTA
            self.delivery_start = _set_trading_day(record.delivery_start, delivery_day_start)
            self.delivery_end = _set_trading_day(record.delivery_end, delivery_day_start)
        else:
            self.trading_start = record.trading_start
            self.trading_end = record.trading_end - TRADING_END_DELTA
            self.delivery_start = record.delivery_start
            self.delivery_end = record.delivery_end

        self._next_work_day_cache = collections.OrderedDict()
        self._prev_work_day_cache = collections.OrderedDict()

    def get_interval(self, unused_timestamp):
        """Return item trading interval based on the provided timestamp

            :param timestamp: int
            :return: ItemInternal
        """
        # return by default the obj attributes
        return _ItemInterval(self.delivery_start, self.delivery_end, self.trading_start, self.trading_end, self.name)


class PromptItem(BaseItem):
    """ Default interface for the products"""

    def get_interval(self, timestamp):
        """
        Get the interval that is valid at the given timestamp.

        Usually this is the interval that corresponds to trades with an exectution time equal to timestamp.
        However, Saturday, Sunday and Weekend product are not always tradeable. In case the product is not tradeable at
        timestamp, the interval returned should be that of the next (upcoming) product. I.e. on Monday,
        return the weekend product that is tradeable in this week, starting e.g. Thursday.

        :type timestamp: float
        :rtype: _ItemInterval
        """
        use_timestamp = timestamp
        for i in range(2):
            # Usually, the _get_interval function should return an item interval where trading_end is
            # after the current timestamp. However, we have extra logic here so the subclass's _get_item does
            # not have to take care of the TRADING_END_DELTA. E.g. on Monday 2:59:55, the _get_item of the DA product
            # would still return the item delivering on Tuesday. But the loop here would change the use_timestamp
            # to 3:00:10 so we would return the item interval with delivery Wednesday, but trading starting at 3:00:00
            # (i.e. after timestamp).

            item_interval = self._get_interval(use_timestamp)
            if item_interval.trading_end > timestamp:
                return item_interval
            else:
                use_timestamp += TRADING_END_DELTA
        raise RuntimeError("No valid item interval returned for {} and timestamp {}".format(type(self).__name__,
                                                                                            timestamp))

    def _get_interval(self, timestamp):
        # make 3 hours shift to correctly account for trading start date (not applicable for WD product)
        ts_start = timestamp - 3 * COMMON.HOUR
        item_params = self._get_item(ts_start)
        return _ItemInterval(*item_params)

    @staticmethod
    def set_gas_day(trading_start, trading_end, delivery_start, delivery_end):
        return trading_start + START_TRADING_DAY, trading_end + START_TRADING_DAY - TRADING_END_DELTA,\
            delivery_start + START_GAS_DAY, delivery_end + START_GAS_DAY


class WithinDayItem(PromptItem):
    """WD (Within Day)  is  tradable  each  trading  day  for  delivery  on  the  remaining  hours  of  the  same
    day  taking  into consideration a specific lead time (three hours)"""

    def __init__(self, record):
        super(WithinDayItem, self).__init__(record=record)

    def _get_interval(self, timestamp):
        # shifted rounded timestamps
        ts_start = int(timestamp // COMMON.HOUR * COMMON.HOUR + 4 * COMMON.HOUR)
        # examine 6-6 day for that timestamp
        # end of day minus 18 hours -> 6:00
        # round up to get starting timestamp
        item_params = self._get_item(ts_start)
        return _ItemInterval(*item_params)

    @staticmethod
    def _get_item(timestamp):
        prod_day, prod_start_day_start, prod_start_day_end = autotrader_core.utils.cet_date_of_timestamp(timestamp)
        prod_name = prod_day
        initial_day_start = prod_start_day_start
        if prod_start_day_end - timestamp <= COMMON.HOUR * 18:
            # day before
            prod_day += datetime.timedelta(1)
            prod_start_day_start, prod_start_day_end = autotrader_core.utils.boundaries_for_cet_day(prod_day)

        delivery_start = timestamp
        delivery_end = prod_start_day_end - COMMON.HOUR * 18
        trading_start = timestamp - COMMON.HOUR * 4
        trading_end = timestamp - COMMON.HOUR * 3 - TRADING_END_DELTA
        hour = int((delivery_start - initial_day_start) // COMMON.HOUR)
        interval_name = "{}-{:02}".format(prod_name.strftime("%Y%m%d"), hour)

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class DayAheadItem(PromptItem):
    """DA (Day Ahead) Product is tradable each day for delivery on the following trading day"""

    def __init__(self, record):
        super(DayAheadItem, self).__init__(record=record)

    @classmethod
    def _get_item(cls, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        next_work_day = TRCAL.find_next_work_day(trading_date)
        # If the trading day is a work day, then "previous_work_day" is the same as the trading day.
        # Otherwise it is the last work day before the trade day.
        previous_work_day = TRCAL.find_previous_work_day(next_work_day)
        delta = next_work_day + datetime.timedelta(1)

        prev_day_start, unused_prev_day_end = autotrader_core.utils.boundaries_for_cet_day(previous_work_day)
        prod_day_start, prod_day_end = autotrader_core.utils.boundaries_for_cet_day(next_work_day)
        unused_prod_end_day_start, prod_end_day_end = autotrader_core.utils.boundaries_for_cet_day(delta)
        # examine 6-6 day
        # end of day minus 18 hours -> 6:00

        delivery_start = prod_day_end - COMMON.HOUR * 18
        delivery_end = prod_end_day_end - COMMON.HOUR * 18
        # Trading starts at 3am on the day before the day of delivery and ends at 3am on the delivery day
        trading_start = prev_day_start + 3. * COMMON.HOUR
        trading_end = prod_day_start + 3. * COMMON.HOUR - TRADING_END_DELTA
        interval_name = next_work_day.strftime("%Y%m%d")
        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class WeekEndItem(PromptItem):
    """WE (Week End) Product is tradable the two trading days preceding a weekend for delivery on
    Saturday and Sunday"""

    def __init__(self, record):
        super(WeekEndItem, self).__init__(record=record)

    def _get_item(self, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        # If today is not a work day, take the next workday
        if not list(TRCAL.work_days_rules(trading_date, trading_date + datetime.timedelta(days=1))):
            trading_date = TRCAL.find_next_work_day(trading_date)
        next_saturday = TRCAL.saturdays_rules(trading_date)[0].date()
        next_work_day = TRCAL.find_next_work_day(next_saturday)
        prev_work_day = TRCAL.find_previous_work_day(next_saturday)
        prod_day = prev_work_day + datetime.timedelta(days=1)

        prod_start_day_start, prod_start_day_end = autotrader_core.utils.boundaries_for_cet_day(prod_day)
        unused_prod_end_day_start, prod_end_day_end = autotrader_core.utils.boundaries_for_cet_day(next_work_day)
        # examine 6-6 day
        # end of day minus 18 hours -> 6:00
        delivery_start = prod_start_day_end - COMMON.HOUR * 18
        delivery_end = prod_end_day_end - COMMON.HOUR * 18
        # Trading starts 2 days and 3 hours before the delivery starts and ends at 3am on the delivery day
        trading_start = prod_start_day_start + 3 * COMMON.HOUR - 2 * 24 * COMMON.HOUR
        trading_end = prod_start_day_start + 3 * COMMON.HOUR - TRADING_END_DELTA
        interval_name = prod_day.strftime("%Y%m%d")

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class SaturdayItem(PromptItem):
    """A SAT (Saturday) Product is tradable on Thursdays and Fridays preceding a Saturday"""

    def __init__(self, record):
        super(SaturdayItem, self).__init__(record=record)

    def _get_item(self, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        next_saturday = TRCAL.saturdays_rules(trading_date)[0].date()
        delta = next_saturday + datetime.timedelta(1)

        prod_day_start, prod_day_end = autotrader_core.utils.boundaries_for_cet_day(next_saturday)
        unused_prod_end_day_start, prod_end_day_end = autotrader_core.utils.boundaries_for_cet_day(delta)
        # Convert to gas day.
        # Note: Adding 6 hours to midnight will fail in case of daylight saving time
        # switch, but removing 18 hours from midnight to get 6am of the previous day always works.
        delivery_start = prod_day_end - COMMON.HOUR * 18
        delivery_end = prod_end_day_end - COMMON.HOUR * 18

        # Trading starts 2 days and 3 hours before the delivery starts and ends at 3am on the delivery day
        trading_start = prod_day_start + 3 * COMMON.HOUR - 2 * 24 * COMMON.HOUR
        trading_end = prod_day_start + 3 * COMMON.HOUR - TRADING_END_DELTA
        interval_name = next_saturday.strftime("%Y%m%d")

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class SundayItem(PromptItem):
    """A SUN (Sunday) Product is tradable on Thursdays, Fridays and Saturdays preceding a Sunday"""

    def __init__(self, record):
        super(SundayItem, self).__init__(record=record)

    def _get_item(self, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        next_sunday = TRCAL.sundays_rules(trading_date)[0].date()
        delta = next_sunday + datetime.timedelta(1)

        prod_day_start, prod_day_end = autotrader_core.utils.boundaries_for_cet_day(next_sunday)
        unused_prod_end_day_start, prod_end_day_end = autotrader_core.utils.boundaries_for_cet_day(delta)
        # Convert to gas day.
        # Note: Adding 6 hours to midnight will fail in case of daylight saving time
        # switch, but removing 18 hours from midnight to get 6am of the previous day always works.
        delivery_start = prod_day_end - COMMON.HOUR * 18
        delivery_end = prod_end_day_end - COMMON.HOUR * 18

        # Trading starts 3 days and 3 hours before the delivery starts and ends at 3am on the delivery day
        trading_start = prod_day_start + 3 * COMMON.HOUR - 3 * 24 * COMMON.HOUR
        trading_end = prod_day_start + 3 * COMMON.HOUR - TRADING_END_DELTA
        interval_name = next_sunday.strftime("%Y%m%d")

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class WeekdayItem(PromptItem):
    """
    For week days (Monday/Tuesday/...) on the prompt sequence,
    we calculate an empty trading period, as they are currently not tradeable by autoTRADER,
    and a correct delivery period for trade capturing.
    """
    weekday = None

    def _get_item(self, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        delivery_day = TRCAL.next_weekday_rule(trading_date, self.weekday)[0].date()
        day_after_delivery = delivery_day + datetime.timedelta(1)

        # Get midnight for the day of delivery and the day after delivery.
        prod_day_start, prod_day_end = autotrader_core.utils.boundaries_for_cet_day(delivery_day)
        unused_prod_end_day_start, prod_end_day_end = autotrader_core.utils.boundaries_for_cet_day(day_after_delivery)
        # convert to a 6am-6am gas day.
        delivery_start = prod_day_end - COMMON.HOUR * 18
        delivery_end = prod_end_day_end - COMMON.HOUR * 18

        # Trading ends at 3am on the delivery day. As we currently do not know when trading starts
        # (i.e. we do not know if the product is always tradable or trading starts somewhere in the middle of the week),
        # we set the trading start equal to the trading end, so autoTRADER can never trade it.
        trading_end = delivery_start - 3 * COMMON.HOUR - TRADING_END_DELTA
        trading_start = trading_end
        interval_name = delivery_day.strftime("%Y%m%d")

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class MondayItem(WeekdayItem):
    weekday = rrule.MO


class TuesdayItem(WeekdayItem):
    weekday = rrule.TU


class WednesdayItem(WeekdayItem):
    weekday = rrule.WE


class ThursdayItem(WeekdayItem):
    weekday = rrule.TH


class FridayItem(WeekdayItem):
    weekday = rrule.FR


class BalanceOfWeekItem(PromptItem):
    """ BOW (Balance of Week). From the documentation :

        'The Balance of Week contract (BOW) is a strip that spans four, three or two individual and consecutive gas days
        from Tuesday 5:00 (GMT/BST) through to  Saturday  05:00  (GMT/BST),
        Wednesday 5:00  (GMT/BST) through to Saturday 05:00 (CET) or
        Thursday 5:00 (GMT/BST) through to  Saturday  05:00  (GMT/BST)  respectively.
        UK  Bank  Holidays  on Tuesday and/or Friday are not included in the BOW contract.'

        i.e : Monday (after 3am) returns interval (Monday 3am, Tuesday 3am, Tuesday 6am, Saturday 6am)
              Tuesday(after 3am) returns interval (Tuesday 3am, Wednesday 3am, Wednesday 6am, Saturday 6am)
              Wednesday (after 3am) returns interval (Wednesday 3am, Thursday 3am, Thursday 6am, Saturday 6am)

    """

    def __init__(self, record):
        super(BalanceOfWeekItem, self).__init__(record=record)

    def _get_item(self, timestamp):
        trading_date = CETUTIL.utc_ts2cet_dt(timestamp).date()
        rest_of_the_week = TRCAL.days_of_the_week_rule(trading_date, trading_date.weekday(), work_only=True)

        # If the first day in rest_of_the_week is thursday, BOW of the current week returns nothing.
        # We return then BOW of the next week.
        if len(list(rest_of_the_week)) <= 2:
            rest_of_the_week = TRCAL.days_of_the_week_rule(trading_date, 0, delta=1, work_only=True)

        trading_start, trading_end = autotrader_core.utils.boundaries_for_cet_day(rest_of_the_week[0].date())
        _, prod_day_end = autotrader_core.utils.boundaries_for_cet_day(rest_of_the_week[-1].date())

        trading_start, trading_end, delivery_start, delivery_end = self.set_gas_day(trading_start, trading_end,
                                                                                    trading_end, prod_day_end)
        interval_name = rest_of_the_week[0].strftime("%Y%m%d")

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]


class BalanceOfMonthItem(PromptItem):
    """ BOM (Balance of Month)

        'The Balance of Month contract (BOM) is a strip of two or more gas days from two business days ahead to the end
        of the contract month, where the first day of any period of non-trading days is considered to be a business day.
        N.B. On certain days at the end of a contract month there will not be a BOM listed.'
    """

    def __init__(self, record):
        super(BalanceOfMonthItem, self).__init__(record=record)
        if record.seq_id == "10000301":
            # The sequence 10000301 is the Balance of Month sequence.
            # While 10000302_35 always is for the current month, the sequence 10000301 has one item for each month.
            # Still, the delivery period of this item changes during the course of the corresponding month
            # based on the BOM rules.
            self.month = CETUTIL.utc_ts2cet_dt(record.delivery_start).date().replace(day=1)
        else:
            self.month = None

    def _get_item(self, timestamp):
        if self.month:
            first_start, last_end = self.bom_month(self.month.year, self.month.month)
            if timestamp + COMMON.HOUR * 3 < CETUTIL.utc_dt2ts(first_start):  # Not yet tradable
                return self._get_item_inner(CETUTIL.utc_dt2ts(first_start))
            elif CETUTIL.utc_dt2ts(last_end) < timestamp + COMMON.HOUR * 3:  # Tradable in the past
                # The PromptItem class will always search for an item with delivery_end in the future.
                # So we cannot hard-code a delivery in the past,
                # and instead set the expired product into the far future.
                never = CETUTIL.utc_dt2ts(datetime.datetime(2100, 1, 1))
                return [never, never, never, never, "invalid_bom"]
        return self._get_item_inner(timestamp)

    @classmethod
    def _get_item_inner(cls, timestamp):
        # The timestamp has been corrected by 3h in the baseclass's _get_interval.
        # I.e. if get_interval was called with Tue 2:00 CET, we receive Mon 23:00 CET here,
        # so the returned date is Monday, which is correct for gas days.
        # If get_item was called with Tue 4:00 CET, we receive Tue 1:00 CET here, so the CET date is Tue.
        # WARNING: Don't use the UTC date here, that would still be Mon,
        # creating an interval that has finished trading before the timestamp given to get_interval.
        trading_day = CETUTIL.utc_ts2cet_dt(timestamp).date()

        # rruleset of working days for current month, now empty
        current_work_month = rrule.rruleset()
        # rruleset of all days for current month, now empty
        current_month = rrule.rruleset()

        # add all working days from trading_day until end of the same month
        current_work_month.rrule(TRCAL.days_of_the_month_rule(trading_day, trading_day.day, work_only=True))

        # if there are any working days in this month left,
        # add all days since first such working day to the rruleset of all days
        # This will skip the current month completely if we're after the last working day of it.
        if current_work_month.count():
            first_work_in_month = current_work_month[0]
            current_month.rrule(TRCAL.days_of_the_month_rule(first_work_in_month.date(), first_work_in_month.day))

        # if there are less than 3 working days then we should return BOM of next month
        # delivery period should be two days minimum
        if current_work_month.count() < 3:
            ext_current_work_month = TRCAL.days_of_the_month_rule(trading_day, 1, delta=1, work_only=True)
            current_work_month.rrule(ext_current_work_month)
            current_month.rrule(TRCAL.days_of_the_month_rule(trading_day, 1, delta=1))

        # calculate trading start/end
        # trading start is at the beginning of today
        # trading end is at the end of the day prior to the next working day (starting from today)
        trading_start, _ = autotrader_core.utils.boundaries_for_cet_day(trading_day)
        prev_day = current_month[0].date()
        current_work_month_set = set(current_work_month)
        for day in current_month:
            if day in current_work_month_set:
                _, trading_end = autotrader_core.utils.boundaries_for_cet_day(prev_day)
                break
            prev_day = day.date()

        # calculate delivery start/end
        # delivery start is at the beginning of the +2 working day
        # (where the first non-working day in the row counts as one working day)
        # Mo/Di/Mi/Do -> Mi/Do/Fr/Sa (+2)
        # Fr -> Mo (+3)
        # Sa -> Mi (+4)
        # So -> Mi (+3)
        # delivery end is at the end of the last day of this month (or next month if less than 3 working days left)
        found_days = 0
        day_of_nonworking_block = 0
        delivery_start = 0
        interval_name = ""
        for i, day in enumerate(current_month):
            if day in current_work_month_set:
                if i:
                    found_days += 1
                    day_of_nonworking_block = 0
            else:
                if day_of_nonworking_block == 0:
                    found_days += 1
                day_of_nonworking_block += 1
            if found_days == 2:
                interval_name = day.strftime("%Y%m%d")
                delivery_start, _ = autotrader_core.utils.boundaries_for_cet_day(day.date())
                break
        next_month = TRCAL.days_of_the_month_rule(day.date(), 1, delta=1)
        delivery_end, _ = autotrader_core.utils.boundaries_for_cet_day(next_month[0].date())
        if delivery_end - delivery_start < COMMON.HOUR * 47:  # less than 2 days including possible March DST switch
            next_next_month = TRCAL.days_of_the_month_rule(trading_day, 1, delta=2)
            delivery_start, _ = autotrader_core.utils.boundaries_for_cet_day(next_month[0].date())
            delivery_end, _ = autotrader_core.utils.boundaries_for_cet_day(next_next_month[0].date())

        trading_start, trading_end, delivery_start, delivery_end = cls.set_gas_day(trading_start, trading_end,
                                                                                   delivery_start, delivery_end)

        return [delivery_start, delivery_end, trading_start, trading_end, interval_name]

    @staticmethod
    def bom_month(year, month):
        """For a given integer year/month return trading_start, trading_end"""
        current_month_begin = datetime.date(year, month, 1)
        previous_month = current_month_begin - relativedelta.relativedelta(months=1)
        previous_month_work_days = list(TRCAL.days_of_the_month_rule(previous_month, 2, work_only=True))
        previous_month_days = list(TRCAL.days_of_the_month_rule(previous_month, 1))

        trading_start = min(previous_month_days[-3],
                            next(wd for wd in reversed(previous_month_work_days) if wd != previous_month_days[-1]))
        trading_start = CETUTIL.cet_dt2utc_dt(trading_start.replace(hour=6)) - datetime.timedelta(hours=3)

        current_month_work_days = list(TRCAL.days_of_the_month_rule(current_month_begin, 1, work_only=True))
        current_month_days = list(TRCAL.days_of_the_month_rule(current_month_begin, 1))
        trading_end = min(current_month_days[-3],
                          next(wd for wd in reversed(current_month_work_days) if wd != current_month_days[-1]))
        trading_end = CETUTIL.cet_dt2utc_dt(trading_end.replace(hour=6)) - datetime.timedelta(hours=3)

        return trading_start, trading_end
