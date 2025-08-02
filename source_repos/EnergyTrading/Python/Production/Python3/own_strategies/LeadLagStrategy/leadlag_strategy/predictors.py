import numpy as np
from datetime import datetime, time
import pytz
import logging
import math
import time as tm

log = logging.getLogger("leadlag_strategy.predictors")


######################################################################################
### helper functions
class EMA:
    def __init__(self, span):
        self.span = span
        self.value = 0
        self.alpha = 2 / (span + 1)

    def push(self, value):
        self.value = self.alpha * value + (1 - self.alpha) * self.value



class TR_class:
    def __init__(self, tau, tau_ema, burn=10):
        self.tau = tau
        self.tau_ema = tau_ema
        self.reset()
        self.__burn = burn

    @property
    def param_keys(self):
        return ['tau', 'tau_ema']

    def update_params(self, params_dict):
        if 'tau' in params_dict.keys():
            self.tau = params_dict['tau']
        if 'tau_ema' in params_dict.keys():
            self.tau_ema = params_dict['tau_ema']

    @property
    def ewma_val(self):
        return self.ewma.value

    @property
    def is_burn(self):
        return self.tot_n < self.burn

    @property
    def min_tau(self):
        return self.tau // 3

    @property
    def old_value(self):
        return self.__old_value

    @property
    def bt(self):
        return self.__bt

    @property
    def burn(self):
        return self.__burn

    @property
    def tot_n(self):
        return self.__tot_n

    def reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index = 0
        self.__bt = 1
        self.__old_value = np.nan
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def soft_reset(self):
        self.phiT = 0
        self.ewma = EMA(self.tau_ema)
        self.ewma_T = EMA(self.tau_ema)
        self.thres = 0
        self.index += 1
        self.__bt = 1
        self.__n = 0
        self.__tot_n = 0
        self.init = False

    def initialize(self):
        self.ewma.value = .5
        self.ewma_T.value = self.tau
        self.init = False

    def push(self, value, volume=None):
        if self.tot_n < 1:
            self.init = True
        else:
            diff_value = value - self.old_value
            self.__bt = self.signed_tick_vals(diff_value)
            bt = max(self.__bt, 0)
            if self.init:
                self.initialize()
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
            if self.is_burn:
                self.phiT += bt
                self.__n += 1
            elif max(self.phiT, self.__n - self.phiT) < self.thres:
                self.phiT += bt
                self.__n += 1
            else:
                self.ewma.push(self.phiT / self.__n)
                self.ewma_T.push(self.__n)
                self.phiT = 0
                self.thres = max(abs(self.ewma.value) * self.ewma_T.value, self.min_tau)
                self.index += 1
                self.__n = 0
        self.__tot_n += 1
        self.__old_value = value
        return None if self.is_burn else self.index

    def signed_tick_vals(self, diff_value):
        if diff_value > 0:
            return 1
        elif diff_value < 0:
            return -1
        else:
            return 0

    def tick_imbalance_single(self, trades):
        self.soft_reset()
        index_series = []
        for trade in trades:
            value = trade[0]
            index_series.append((trade[0], trade[1], trade[2], self.push(value)))
        return index_series

    def tick_imbalance_indices(self, trades):
        self.reset()
        index_series = []
        current_date = None
        daily_trades = []

        for trade in trades:
            trade_date = trade[2].date()
            if current_date is None:
                current_date = trade_date

            if trade_date != current_date:
                # Process the previous day's trades
                index_series.extend(self.tick_imbalance_single(daily_trades))
                daily_trades = []
                current_date = trade_date

            daily_trades.append(trade)

        # Process the last day's trades
        if daily_trades:
            index_series.extend(self.tick_imbalance_single(daily_trades))

        return index_series



def get_nine_am_unix_today_cet():
    # Define the CET timezone
    cet = pytz.timezone('CET')

    # Get today's date in the CET timezone
    today = datetime.now(cet).date()

    # Combine today's date with the time 09:00 AM in CET
    nine_am_today = cet.localize(datetime.combine(today, time(9, 0)))

    # Convert to Unix timestamp (seconds since epoch)
    unix_timestamp = int(nine_am_today.timestamp())

    return unix_timestamp


def calculate_ema(current_price, previous_ema, span):
    alpha = 2 / (span + 1)
    return alpha * current_price + (1 - alpha) * previous_ema

######################################################################################
### predictor calculation


def calculate_MACD(market_view):
    market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')
    lag_trades=[(pt.price, pt.quantity, pt.execution_time) for pt in market_view.public_trades]

    if len(lag_trades)<=0:
        return None

    try:

        # Initialize the first EMA values with the first trade price
        short_ema = lag_trades[0][0]
        long_ema = lag_trades[0][0]

        # Calculate EMAs iteratively
        for price, quantity, timestamp in lag_trades[1:]:
            short_ema = calculate_ema(price, short_ema, span=12)
            long_ema = calculate_ema(price, long_ema, span=26)

        # Calculate MACD as the difference between the last short and long EMAs
        last_macd = short_ema - long_ema

        return last_macd

    except Exception as err:
            log.error("Exception in calculate_MACD: %s", err)
            return None

def calculate_regression_model_price(lead_market_view, lag_market_view, coef1, coef2):

    lead_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')
    lag_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')

    try:
        lead_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lead_market_view.public_trades]
        lag_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lag_market_view.public_trades]

        lag_trades = sorted(
            lag_trades,
            key=lambda x: (
                x[2],  # execution_time
               -x[1],  # volume
                x[0]  # lag_price
            ))

        log.debug(
            "lag_trades {}".format(
                lag_trades))

        # Initialize the TR_class with specific tau and tau_ema values.
        tr_class = TR_class(tau=10, tau_ema=10)

        # Process the trade data to calculate tick imbalance indices.
        indices = tr_class.tick_imbalance_single(lag_trades)

        # Initialize a dictionary to store the first occurrence of each index
        first_occurrence = {}

        # Iterate through the list to capture the first occurrence
        for _,_,timestamp, index in indices:
            if index not in first_occurrence:
                first_occurrence[index] = timestamp

        # Convert the dictionary back to a list of tuples (timestamp, value)
        first_occurrence = [(first_occurrence[index], index) for index in first_occurrence]
        first_occurrence = sorted(first_occurrence, key=lambda x: (x[1] is not None, x[1]))
        tick_start_times = [timestamp for timestamp, index in first_occurrence]

        # log.debug(
        #     "LL-calculate_regression_model_price: tick_stat_times are:  {}".format(tick_start_times)
        # )

        last_tick_start_time = tick_start_times[-1]
        prev_tick_start_time = tick_start_times[-2]

        prev_tick_id=max([index if index else 0 for _,_,_,index in indices])-1

        trades_lead_prev_tick = [pt for pt in lead_trades if (pt[2]>=prev_tick_start_time and pt[2]<last_tick_start_time)]
        trades_lag_prev_tick = [pt for pt in indices if pt[-1] == prev_tick_id]


        price_lead_t_0 = lead_trades[-1][0]
        price_lead_t_1 = np.sum([pt[0]*pt[1] for pt in trades_lead_prev_tick])/np.sum([pt[1] for pt in trades_lead_prev_tick])

        price_lag_t_1 = np.sum([pt[0]*pt[1] for pt in trades_lag_prev_tick])/np.sum([pt[1] for pt in trades_lag_prev_tick])

        price_lead_t_1=None if math.isnan(price_lead_t_1) else price_lead_t_1
        price_lead_t_0=None if math.isnan(price_lead_t_0) else price_lead_t_0
        price_lag_t_1=None if math.isnan(price_lag_t_1) else price_lag_t_1

        def predict_lag_price(lead_price_tick, lead_price, lag_price_tick, coef1, coef2):
            log.debug(
                "last_tick_start_time {}, prev_tick_start_time{}, lead_price_tick {}, lead_price {}, lag_price_tick {}, coef1 {}, coef2 {}".format(
                    last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick, coef1,
                    coef2))

            if not any(x is None for x in [lead_price_tick, lead_price, lag_price_tick, coef1, coef2]):
                return lag_price_tick*np.exp((coef1+coef2*np.log(lead_price/lead_price_tick))), lag_price_tick, last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick, coef1, coef2
            else:
                return None, None, last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick, coef1, coef2

        return predict_lag_price(price_lead_t_1, price_lead_t_0, price_lag_t_1, coef1, coef2)

    except Exception as err:
            log.error("Exception in calculate_regression_model_price: %s", err)
            return None, None, None, None, None, None, None, None, None



def calc_vol_intensity_index(market_view, n, timestamp):

    market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')
    lag_trades=[(pt.price, pt.quantity, pt.execution_time) for pt in market_view.public_trades]

    if len(lag_trades) < n or not timestamp:
        return None

    try:

        lag_trades = sorted(
            lag_trades,
            key=lambda x: (
                x[2],  # execution_time
               -x[1],  # volume
                x[0]  # lag_price
            ))

        n_trades=len(lag_trades)
        time_since_first=max(timestamp,lag_trades[-1][2])-lag_trades[0][2]
        time_since_last_n=max(timestamp,lag_trades[-1][2]) -lag_trades[-n][2]

        VII_n = (time_since_first*n)/(time_since_last_n*n_trades)

        return VII_n



    except Exception as err:
            log.error("Exception in calculate_VII: %s", err)
            return None