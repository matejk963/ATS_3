from __future__ import absolute_import
import collections
import datetime as DT
import dateutil.rrule as RR
import dateutil.relativedelta as RD


def holidays_generator(dtstart=DT.date.today(), until=DT.date.today() + DT.timedelta(days=365)):
    if isinstance(dtstart, DT.datetime):
        dtstart = dtstart.date()
    start_of_year = dtstart.replace(month=1, day=1)
    # Generate bank holidays
    rs = RR.rruleset()

    # 1st of January is the Holiday, however, on EEXS if it falls on the weekend it gets substituted the next days
    jan01_rule = RR.rrule(RR.YEARLY, dtstart=start_of_year, bymonth=1,
                          count=1,  # it will only be one day
                          bymonthday=(1, 2, 3),  # it can substitute the weekend
                          byweekday=(RR.MO, RR.TU, RR.WE, RR.TH, RR.FR))  # only makes sense during the week
    if dtstart <= jan01_rule[0].date():
        rs.rrule(jan01_rule)
    else:
        rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year + DT.timedelta(days=3), bymonth=1,
                          count=1,  # it will only be one day
                          bymonthday=(1, 2, 3),  # it can substitute the weekend
                          byweekday=(RR.MO, RR.TU, RR.WE, RR.TH, RR.FR)))  # only makes sense during the week

    # Easter holidays (Friday and Monday)
    rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year, until=until, byeaster=-2))
    rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year, until=until, byeaster=1))

    # First Monday in May is "Early May Bank Holiday"
    rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year, until=until, bymonth=5, byweekday=RR.MO(1)))
    # in 1995 and 2020 the Early May Bank Holiday has been moved to Friday 8th to mark 50th and 75th VE anniversary
    for year in (1995, 2020):
        if dtstart.year <= year <= until.year:
            rs.exdate(DT.datetime(year, 5, 4))
            rs.rdate(DT.datetime(year, 5, 8))

    # 8th of May is the UK Bank Holiday (Bank holiday for the coronation of King Charles III) in 2023
    if dtstart.year <= 2023 <= until.year:
        rs.rdate(DT.datetime(2023, 5, 8))

    # Last Monday in May is "Spring Bank Holiday"
    rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year, until=until, bymonth=5, byweekday=RR.MO(-1)))

    if dtstart.year <= 2022 <= until.year:
        # spring bank holiday moved from last monday in may to 2nd june 2022 to make a 4 days weekend
        rs.exdate(DT.datetime(2022, 5, 30))
        rs.rdate(DT.datetime(2022, 6, 2))

        rs.rdate(DT.datetime(2022, 6, 3))  # platinum jubilee bank holiday (in 2022 only)

    # Last Monday of August is "August Bank Holiday"
    rs.rrule(RR.rrule(RR.YEARLY, count=1, bymonth=8, byweekday=RR.MO(-1), dtstart=start_of_year))

    # Christmas days are 25 and 26, however on EEXS if they fall on the weekend they get substituted the next days
    rs.rrule(RR.rrule(RR.YEARLY, dtstart=start_of_year, bymonth=12,
                      count=2,  # limit it to only 2 days
                      bymonthday=(25, 26, 27, 28),  # it can substitute the weekend
                      byweekday=(RR.MO, RR.TU, RR.WE, RR.TH, RR.FR)  # it only makes sense during the week
                      ))

    # Exclude potential holidays that fall on weekends
    rs.exrule(RR.rrule(RR.WEEKLY, dtstart=dtstart, until=until, byweekday=(RR.SA, RR.SU)))

    rs.exrule(RR.rrule(RR.DAILY, dtstart=start_of_year, until=dtstart - DT.timedelta(days=1)))

    return rs


def work_days_rules(dtstart, until=None):
    """Returns rule set for working days.

    If until is not specified, it returns the next working day

    :param dtstart: starting datetime for search
    :type dtstart: datetime.datetime or datetime.date
    :param until: search until datetime, defaults to None
    :type until: datetime.datetime, optional
    :returns: Returns a rrule set for working days
    :rtype: {RR.rruleset}
    """
    rs = RR.rruleset()
    if isinstance(dtstart, DT.datetime):
        dtstart = dtstart.date()
    if until:
        rs.rrule(RR.rrule(RR.DAILY, dtstart=dtstart, until=until,
                          byweekday=(RR.MO, RR.TU, RR.WE, RR.TH, RR.FR)))
        rs.exrule(holidays_generator(dtstart, until))
    else:
        while True:
            rs.rrule(RR.rrule(RR.DAILY, dtstart=dtstart, count=1,
                              byweekday=(RR.MO, RR.TU, RR.WE, RR.TH, RR.FR)))
            rs.exrule(holidays_generator(dtstart, until))
            if len(list(rs)) == 0:
                dtstart += DT.timedelta(days=1)
            else:
                break
    return rs


def saturdays_rules(dtstart):
    """Returns next Saturday
    If current dtstart is already a Saturday, we shift it to Sunday

    :param dtstart: starting datetime for search
    :type dtstart: datetime.date
    :returns: Returns a next Saturday
    :rtype: {RR.rrule}
    """
    return next_weekday_rule(dtstart, RR.SA)


def sundays_rules(dtstart):
    """Returns next Sunday
    If current dtstart is already a Sunday, we shift it to Moday

    :param dtstart: starting datetime for search
    :type dtstart: datetime.date
    :returns: Returns a next Sunday
    :rtype: {RR.rrule}
    """
    return next_weekday_rule(dtstart, RR.SU)


def next_weekday_rule(dtstart, weekday):
    """
    Returns a rule for the next day (after dtstart) that is of the given weekday,
    independent of it being a working day or non-working day.
    :param dtstart: Find the first matching weekday AFTER this day
    :type dtstart: datetime.date
    :param weekday: The day of the week
    :type weekday: RR.weekday
    :return:
    :rtype:
    """
    if dtstart.weekday() == weekday.weekday:
        dtstart += DT.timedelta(days=1)
    return RR.rrule(RR.DAILY, dtstart=dtstart, count=1, byweekday=weekday)


def day_of_the_week(dtstart, weekday):
    """ Returns the week day of the dtstart week.

    :param dtstart: starting datetime for search
    :type dtstart: datetime.datetime
    :param weekday: the index of a week day
    :type weekday: int
    :returns: Returns the weekday of the dtstart week
    :rtype: {datetime.datetime}
    """
    if dtstart.weekday() > weekday:
        the_day = dtstart - RD.relativedelta(weekday=RD.weekday(weekday)(-1))
    else:
        the_day = dtstart + RD.relativedelta(weekday=RD.weekday(weekday)(1))

    return the_day


def days_of_the_week_rule(dtstart, weekday, delta=0, work_only=False):
    """ Returns the days of the dtstart week in delta week.

    :param dtstart: starting datetime for search
    :type dtstart: datetime.datetime
    :param weekday: the week day to start the search.
                    If we want to start the search from dtstart, weekday should be dtstart.weekday()
    :type weekday: int
    :param delta: search in {delta} weeks. default is 0 i.e the week of dtstart.
    :type delta: int
    :param work_only: if True returns only the working days, return the all week otherwise
    :type work_only: bool
    :return: The week from dtstart in {delta} week
    """
    rs = RR.rruleset()

    start_of_the_week = day_of_the_week(dtstart + RD.relativedelta(weeks=delta), weekday)
    end_of_the_week = start_of_the_week + RD.relativedelta(weekday=RR.SU)

    if work_only:
        rs.rrule(work_days_rules(start_of_the_week, end_of_the_week))
    else:
        rs.rrule(RR.rrule(RR.DAILY, dtstart=start_of_the_week, until=end_of_the_week))

    return rs


def days_of_the_month_rule(dtstart, monthday, delta=0, work_only=False):
    """ Returns the days of the month from dtstart.

    :param dtstart: starting datetime for search
    :type dtstart: datetime.datetime
    :param monthday: the month day to start the search.
                     If we want to start the search from dtstart, monthday should be dtstart.day
    :type monthday: int
    :param delta: search in {delta} months. default is 0 i.e the month of dtstart.
    :type delta: int
    :param work_only: if True returns only the working days, return the all week otherwise
    :type work_only: bool
    :return: The month from dtstart in {delta} month
    """
    rs = RR.rruleset()
    # set the start of the month to monthday and in delta month
    start_of_the_month = dtstart + RD.relativedelta(day=monthday, months=delta)
    # set the end of the month in delta month
    end_of_the_month = dtstart + RD.relativedelta(day=31, months=delta)

    if work_only:
        rs.rrule(work_days_rules(start_of_the_month, end_of_the_month))
    else:
        rs.rrule(RR.rrule(RR.DAILY, dtstart=start_of_the_month, until=end_of_the_month))

    return rs


CACHE_LENGTH = 50
_prev_work_day_cache = collections.OrderedDict()
_next_work_day_cache = collections.OrderedDict()


def find_previous_work_day(date):
    if date not in _prev_work_day_cache:
        result = work_days_rules(date - DT.timedelta(7),
                                 date - DT.timedelta(1))[-1].date()
        _prev_work_day_cache[date] = result
        if len(_prev_work_day_cache) > CACHE_LENGTH:
            _prev_work_day_cache.popitem(last=False)  # remove the oldest entry
    return _prev_work_day_cache[date]


def find_next_work_day(date):
    if date not in _next_work_day_cache:
        result = work_days_rules(date + DT.timedelta(1),
                                 date + DT.timedelta(7))[0].date()

        _next_work_day_cache[date] = result
        if len(_next_work_day_cache) > CACHE_LENGTH:
            _next_work_day_cache.popitem(last=False)  # remove the oldest entry
    return _next_work_day_cache[date]
