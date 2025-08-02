#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

import autotrader_core.common as COMMON
import autotrader_core.power_position_closer_base as PCB

log = logging.getLogger('autotrader.spontaneous_position_closing_strategy')


class CustomStrategy(PCB.PositionClosingBase):
    """Implements the behaviour of the spontaneous position closer. The current volume to be closed is determined
    by a linear ascent from the point in time a position is transferred. The ascent cannot be manipulated otherwise."""
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # use log handler for all logs related to this strategy instance
        self.log = log

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # note that position_slot_generator is instanced with use_grace_mode=False here, in contrast
        # to the standard position closer. No grace mode in this algo.
        self.position_slot_generator = PCB.PositionSlotGenerator(
            self.strategy_settings, False, omt_steps_settings=self.get_omt_step_settings()
        )

    def calculate_exposures(self, ts_from, ts_until, traded, trading_start_before_delivery_sec,
                            trading_end_before_delivery_sec, timestamp):
        """
        calculate_exposures calculates the current factor of volume to trade up to now and from that derives
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
        :return: exposures as dictionary from quarter timestamp to
        (maximum_order_exposure, traded, slot_size, use_maximum_order_book, factor) and seconds left to trade
        :rtype: (Dict[float, (float, float, float, float, float)], float)
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
            # a change in last_change_timestamps changes the linear ascent in the factor calculation, basically
            # starting a new line from the current traded volume to the target volume.
            if self.last_change_timestamps[ts] is None or self.last_change_timestamps[ts][1] != pos_balance:
                self.last_change_timestamps[ts] = (timestamp, pos_balance, traded[ts])

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

            # make sure, factor of 1 is reached 1 minute before end
            end_trading_activity_at -= 60

            # how many seconds are there still to trade
            seconds_left[ts] = end_trading_activity_at - timestamp

            # get timestamp, last balance and last traded from the last time the position changed.
            # might be now, if the reset has happened above in the code
            last_change_ts, last_change_position_balance, last_change_traded = self.last_change_timestamps[ts]

            if ts - timestamp > start_trading_activity_at:
                factor = 0
            else:
                # distance in time between when the last change to the position was made and when trading ends
                duration_from_change_to_trading_end = end_trading_activity_at - last_change_ts

                # the factor calculation is simple here. We just calculate the point on a linear function that
                # goes from 0 when the last changes was made to 1 at trading end.
                factor = min(
                    1.,
                    (1. - float(end_trading_activity_at - timestamp) / duration_from_change_to_trading_end) + 0.08
                )

            # get standard deviation for position for this quarter
            stddev = self.position_deviation_handler.get_stddev(ts)

            # calculate the position and what has been traded only since the last position change
            # the linear function starts at the last change, so we must remove quantities from before that
            local_position = pos_balance - last_change_traded
            local_traded = traded[ts] - last_change_traded

            # get exposure data for this quarter (containing information about the overall missing quantity,
            # how big the order should be and what the order packet size should be
            exposures[ts] = self.order_volume_calculator.calculate_exposures(
                local_position, local_traded, stddev, factor, pos_balance, traded[ts])

            self.debug_log(
                "assessing quarter {} : pos:{} trd:{} loc_pos: {}, loc_td:{}, op:{} f:{:.2f} s:{:.2f} mw:{} ss:{} lc:{}"
                .format(
                    PCB.timestamp_log(ts), pos_balance, traded[ts], local_position, local_traded, open_position, factor,
                    stddev, exposures[ts][0], exposures[ts][2], self.last_change_timestamps[ts][0]
                )
            )

        return exposures, seconds_left
