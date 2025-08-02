#!/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

import autotrader_lib.common as COMMON
import autotrader_core.power_position_closer_base as PCB
from six.moves import range

log = logging.getLogger('autotrader.position_closing_strategy')


class CustomStrategy(PCB.PositionClosingBase):
    """Implements the behaviour of the standard position closer. The current volume to be closed is determined
    by a fixed curve over time that can be manipulated through the market price prediction timeseries."""
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # use log handler for all logs related to this strategy instance
        self.log = log

    def get_omt_step_settings(self):
        return PCB.OMT_TOLERANCE_STEPS

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # note that here the position_slot_generator is instanced with use_grace_mode=True,
        # in contrast to the spontaneous position closer
        self.position_slot_generator = PCB.PositionSlotGenerator(
            self.strategy_settings, True, omt_steps_settings=self.get_omt_step_settings()
        )

    def calculate_exposures(self, ts_from, ts_until, traded, trading_start_before_delivery_sec,
                            trading_end_before_delivery_sec, timestamp, omt_percent=0.):
        """Calculate_exposures calculates the current factor of volume to trade up to now and from that derives
        the current placement volumes in the orderbook.

        :param ts_from: unix timestamp marking the start of the first quarter hour to look at
        :type ts_from: float or int
        :param ts_until: unix timestamp marking the end of the last quarter hour to look at
        :type ts_until: float or int
        :param traded: dict mapping from timestamp to power already traded in that quarter
        :type traded: Dict[float, float]
        :param trading_start_before_delivery_sec: algo setting that defines how many seconds before delivery (sic!)
                                                  trading starts.
        :type trading_start_before_delivery_sec: float
        :param trading_end_before_delivery_sec: algo setting that defines how many seconds before delivery (sic!)
                                                trading has to end.
        :type trading_end_before_delivery_sec: float
        :param timestamp: current time in unix timestamp
        :type timestamp: float
        :param omt_percent: 0..100 omt percentage
        :type omt_percent: float
        :return: exposures as dictionary from quarter timestamp to
        (maximum_order_exposure, traded, slot_size, use_maximum_order_book, factor) and seconds left to trade
        :rtype: (Dict[float, tuple[float, float, float, float, float]], float)
        """

        # initialize the return values
        exposures = defaultdict(lambda: [0, 0, 0, 0, 0])
        seconds_left = defaultdict(int)

        # iterate through all quarters
        for ts in range(int(ts_from), int(ts_until), COMMON.QUARTER):
            # calculate the target balance of trading (diff of long and short)
            pos_balance = self.position.positions_long[ts] - self.position.positions_short[ts]
            # calculate the delta between target position balance and what has already been traded
            open_position = pos_balance - traded[ts]

            # if the target position balance has changed, remember that in last changed timestamps.
            # a change in last_change_timestamps triggers grace mode (less aggressive behaviour).
            # if there weren't grace mode, a sudden change in position can cause rapid order aggressing.
            if self.last_change_timestamps[ts] is None or self.last_change_timestamps[ts][1] != pos_balance:
                self.last_change_timestamps[ts] = (timestamp, pos_balance)

            # calculate when trading ends
            end_trading_activity_at = ts - trading_end_before_delivery_sec
            start_trading_activity_at = ts - trading_start_before_delivery_sec

            # shift this end timestamp if we know that the exchange will be halted in that interval.
            # in that case the end timestamp will move to the beginning of the planned exchange outage.
            timestamp_check_halt = self.check_epex_timestamp_halt(end_trading_activity_at)
            if timestamp_check_halt:
                end_trading_activity_at = timestamp_check_halt[0]
            # if quarter already behind trading end, then ignore it
            if timestamp >= end_trading_activity_at:
                self.debug_log("trading ended for {}".format(PCB.timestamp_log(ts)))
                continue

            # how many seconds are there still to trade
            seconds_left[ts] = end_trading_activity_at - timestamp

            if ts - timestamp > start_trading_activity_at:
                # if it is before the set trading start, then set the factor to 0
                factor = 0
            # calculate factor for quarter position (from 0. to 1.)
            elif open_position < 0.:
                factor = self.product_volume_factor_buy.get_factor(ts, timestamp, end_trading_activity_at)
            else:
                factor = self.product_volume_factor_sell.get_factor(ts, timestamp, end_trading_activity_at)

            # get standard deviation for position for this quarter
            stddev = self.position_deviation_handler.get_stddev(ts)

            # get exposure data for this quarter (containing information about the overall missing quantity,
            # how big the order should be and what the order packet size should be
            exposures[ts] = self.order_volume_calculator.calculate_exposures(
                pos_balance, traded[ts], stddev, factor, omt_percent=omt_percent
            )

            self.debug_log(
                "assessing quarter %s : pos:%.2f trd:%.2f op:%.2f f:%.2f s:%.2f mw:%.2f ss:%.2f lc:%.2f omt:%.2f" % (
                    PCB.timestamp_log(ts), pos_balance, traded[ts], open_position, factor, stddev,
                    exposures[ts][0], exposures[ts][2], self.last_change_timestamps[ts][0], omt_percent
                )
            )

        return exposures, seconds_left
