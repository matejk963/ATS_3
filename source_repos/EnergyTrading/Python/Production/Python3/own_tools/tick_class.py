import numpy as np
from datetime import datetime, time
import pytz
import logging
import math
from .math_features import EMA

log = logging.getLogger("own_tools.tick_class")


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
            index_series.append((trade[2], self.push(value)))
        return index_series

    def tick_imbalance_single_new(self, trades):
        self.soft_reset()
        last_index = self.index + 0
        index_series = []
        index_list = []
        for trade in trades:
            value = trade[0]
            new_index = self.push(value)
            if new_index is None or last_index == new_index:
                index_list.append((trade[2], new_index))
            else:
                index_series.append(index_list)
                index_list = [(trade[2], new_index)]
                last_index = self.index + 0
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


class DataClass:
    last_tick_start_time = None
    prev_tick_start_time = None
    last_index = None

    def __init__(self, tau, tau_ema, scale_params_list, diff_bool=True, scale_bool=True):
        self.tau = tau
        self.tau_ema = tau_ema
        self.init_bool = True
        self.diff_bool = diff_bool
        self.scale_bool = scale_bool
        self.scale_params_dict = scale_params_list

    @property
    def scale_params_dict(self):
        return self.__scale_params_dict

    @scale_params_dict.setter
    def scale_params_dict(self, params_list):
        self.__scale_params_dict = {k: {'mean': np.nan, 'std': np.nan} for k in ['x', 'y']}
        if self.scale_bool:
            self.__scale_params_dict['x']['mean'] = params_list[0]
            self.__scale_params_dict['x']['std'] = params_list[1]
            self.__scale_params_dict['y']['mean'] = params_list[2]
            self.__scale_params_dict['y']['std'] = params_list[3]

    def scale_data_reg(self, x_raw, y_raw):
        if self.scale_bool:
            x_trans = (x_raw - self.scale_params_dict['x']['mean']) / self.scale_params_dict['x']['std']
            y_trans = (y_raw - self.scale_params_dict['y']['mean']) / self.scale_params_dict['y']['std']
        else:
            x_trans, y_trans = x_raw, y_raw
        return x_trans, y_trans

    def rescale_data_reg(self, x_trans, y_trans):
        if self.scale_bool:
            x_raw = x_trans * self.scale_params_dict['x']['std'] + self.scale_params_dict['x']['mean']
            y_raw = y_trans * self.scale_params_dict['y']['std'] + self.scale_params_dict['y']['mean']
        else:
            x_raw, y_raw = x_trans, y_trans
        return x_raw, y_raw

    def model_recalc(self, lead_trades, lag_trades, first_occurrence, model_class):
        if self.init_bool:
            self.init_bool = False
            tick_start_times_aux = [t for t, i in first_occurrence]
            lead_aux, lag_aux = index_trades(lead_trades, tick_start_times_aux), index_trades(lag_trades, tick_start_times_aux)
            x_list, y_list = process_prices_vw(lead_aux), process_prices_vw(lag_aux)
            [model_class.push(x, y) for x, y in zip(x_list, y_list)]
            self.last_index = first_occurrence[-2][1]
        else:
            if self.last_index == first_occurrence[-2][1]:
                pass
            else:
                tick_start_times_aux = [t for t, i in first_occurrence[-3:]]
                lead_aux, lag_aux = index_trades(lead_trades, tick_start_times_aux), index_trades(lag_trades, tick_start_times_aux)
                x, y = process_prices_vw(lead_aux)[0], process_prices_vw(lag_aux)[0]
                model_class.push(x, y)
                self.last_index = first_occurrence[-2][1]
        pass

    def calculate_regression_model_price(self, lead_market_view, lag_market_view, model_class):
        lead_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')
        lag_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')

        try:
            lead_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lead_market_view.public_trades]
            lag_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lag_market_view.public_trades]

            lag_trades = group_trades(lag_trades)

            log.debug(
                "lag_trades {}".format(
                    lag_trades))

            # Initialize the TR_class with specific tau and tau_ema values.
            tr_class = TR_class(tau=self.tau, tau_ema=self.tau_ema)
            # Process the trade data to calculate tick imbalance indices.
            indices = tr_class.tick_imbalance_single(lag_trades)

            # Initialize a dictionary to store the first occurrence of each index
            first_occurrence = {}

            # Iterate through the list to capture the first occurrence
            for timestamp, index in indices:
                if index not in first_occurrence:
                    first_occurrence[index] = timestamp

            # Convert the dictionary back to a list of tuples (timestamp, value)
            first_occurrence = [(first_occurrence[index], index) for index in first_occurrence]
            first_occurrence = sorted(first_occurrence, key=lambda x: (x[1] is not None, x[1]))
            tick_start_times = [timestamp for timestamp, index in first_occurrence]

            # Push model if new tick
            self.model_recalc(lead_trades, lag_trades, first_occurrence, model_class)

            self.last_tick_start_time = tick_start_times[-1]
            self.prev_tick_start_time = tick_start_times[-2]

            trades_lead_prev_tick = [pt for pt in lead_trades if
                                     (pt[2] >= self.prev_tick_start_time and pt[2] < self.last_tick_start_time)]
            trades_lag_prev_tick = [pt for pt in lag_trades if
                                    (pt[2] >= self.prev_tick_start_time and pt[2] < self.last_tick_start_time)]

            price_lead_t_0 = lead_trades[-1][0]
            price_lead_t_1 = np.sum([pt[0] * pt[1] for pt in trades_lead_prev_tick]) / np.sum(
                [pt[1] for pt in trades_lead_prev_tick])

            price_lag_t_1 = np.sum([pt[0] * pt[1] for pt in trades_lag_prev_tick]) / np.sum(
                [pt[1] for pt in trades_lag_prev_tick])

            price_lead_t_1 = None if math.isnan(price_lead_t_1) else price_lead_t_1
            price_lead_t_0 = None if math.isnan(price_lead_t_0) else price_lead_t_0
            price_lag_t_1 = None if math.isnan(price_lag_t_1) else price_lag_t_1

            return self.predict_lag_price(price_lead_t_1, price_lead_t_0, price_lag_t_1, model_class)
        except Exception as err:
            log.error("Exception in calculate_regression_model_price: %s", err)
            return None, None, None, None, None, None, None

    def predict_lag_price(self, lead_price_tick, lead_price, lag_price_tick, model_class):
        if not any(x is None for x in [lead_price_tick, lead_price]):
            x_vec = np.asarray([np.log(lead_price / lead_price_tick)])
            ret_prediction = model_class.predict(x_vec)
        else:
            ret_prediction = None
        log.debug(
            "last_tick_start_time {}, prev_tick_start_time{}, lead_price_tick {}, lead_price {}, lag_price_tick {}, ret_hat {}".format(
                self.last_tick_start_time, self.prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick,
                ret_prediction))
        if not any(x is None for x in [lead_price_tick, lead_price, lag_price_tick, ret_prediction]):
            return lag_price_tick * np.exp(
                ret_prediction), lag_price_tick, self.last_tick_start_time, self.prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick
        else:
            return None, None, self.last_tick_start_time, self.prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick



def calculate_regression_model_price(lead_market_view, lag_market_view, model_class, tau, tau_ema):
    lead_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')
    lag_market_view._set_public_trade_filters(from_ts=get_nine_am_unix_today_cet(), to_ts=None, broker_id='1441')

    try:
        lead_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lead_market_view.public_trades]
        lag_trades = [(pt.price, pt.quantity, pt.execution_time) for pt in lag_market_view.public_trades]

        lag_trades = group_trades(lag_trades)

        log.debug(
            "lag_trades {}".format(
                lag_trades))

        # Initialize the TR_class with specific tau and tau_ema values.
        tr_class = TR_class(tau=tau, tau_ema=tau_ema)
        # Process the trade data to calculate tick imbalance indices.
        indices = tr_class.tick_imbalance_single(lag_trades)

        # Initialize a dictionary to store the first occurrence of each index
        first_occurrence = {}

        # Iterate through the list to capture the first occurrence
        for timestamp, index in indices:
            if index not in first_occurrence:
                first_occurrence[index] = timestamp

        # Convert the dictionary back to a list of tuples (timestamp, value)
        first_occurrence = [(first_occurrence[index], index) for index in first_occurrence]
        first_occurrence = sorted(first_occurrence, key=lambda x: (x[1] is not None, x[1]))
        tick_start_times = [timestamp for timestamp, index in first_occurrence]

        last_tick_start_time = tick_start_times[-1]
        prev_tick_start_time = tick_start_times[-2]

        trades_lead_prev_tick = [pt for pt in lead_trades if
                                 (pt[2] >= prev_tick_start_time and pt[2] < last_tick_start_time)]
        trades_lag_prev_tick = [pt for pt in lag_trades if
                                (pt[2] >= prev_tick_start_time and pt[2] < last_tick_start_time)]

        price_lead_t_0 = lead_trades[-1][0]
        price_lead_t_1 = np.sum([pt[0]*pt[1] for pt in trades_lead_prev_tick])/np.sum([pt[1] for pt in trades_lead_prev_tick])

        price_lag_t_1 = np.sum([pt[0]*pt[1] for pt in trades_lag_prev_tick])/np.sum([pt[1] for pt in trades_lag_prev_tick])

        price_lead_t_1 = None if math.isnan(price_lead_t_1) else price_lead_t_1
        price_lead_t_0 = None if math.isnan(price_lead_t_0) else price_lead_t_0
        price_lag_t_1 = None if math.isnan(price_lag_t_1) else price_lag_t_1

        def predict_lag_price(lead_price_tick, lead_price, lag_price_tick, model_class):
            if not any(x is None for x in [lead_price_tick, lead_price]):
                x_vec = np.asarray([np.log(lead_price / lead_price_tick)])
                ret_prediction = model_class.predict(x_vec)
            else:
                ret_prediction = None
            log.debug(
                "last_tick_start_time {}, prev_tick_start_time{}, lead_price_tick {}, lead_price {}, lag_price_tick {}, ret_hat {}".format(
                    last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick, ret_prediction))
            if not any(x is None for x in [lead_price_tick, lead_price, lag_price_tick, ret_prediction]):
                return lag_price_tick*np.exp(ret_prediction), lag_price_tick, last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick
            else:
                return None, None, last_tick_start_time, prev_tick_start_time, lead_price_tick, lead_price, lag_price_tick

        return predict_lag_price(price_lead_t_1, price_lead_t_0, price_lag_t_1, model_class)
    except Exception as err:
            log.error("Exception in calculate_regression_model_price: %s", err)
            return None, None, None, None, None, None, None


def group_trades(trade_list):
    # Trades in from of tuple (price, quantity, timestamp)
    # Step 1: Sort trades by timestamp
    trade_list.sort(key=lambda x: x[2])
    # Step 2: Initialize the list to store VWAP results and variables to track the aggregation
    vwap_results = []
    last_timestamp = None
    weighted_sum = 0
    total_qty = 0
    # Loop over list
    for price, quantity, timestamp in trade_list:
        if timestamp != last_timestamp and last_timestamp is not None:
            # Calculate VWAP for the last group and store the result
            vwap_results.append((weighted_sum / total_qty, total_qty, last_timestamp))
            # Reset the sums for the new timestamp group
            weighted_sum = 0
            total_qty = 0

        # Update the current aggregation for this timestamp
        weighted_sum += price * quantity
        total_qty += quantity
        last_timestamp = timestamp
    # Append the final VWAP result for the last timestamp group
    vwap_results.append((weighted_sum / total_qty, total_qty, last_timestamp))
    return vwap_results


def index_trades(trade_list, tick_start_times):
    grouped_list = []
    for start_time, end_time in zip(tick_start_times[:-1], tick_start_times[1:]):
        aux_list = [t for t in trade_list if (t[2] >= start_time and t[2] < end_time)]
        grouped_list.append(aux_list)
    return grouped_list


def process_prices_vw(trade_grouped_list):
    trade_price_list = [sum([t[0] * t[1] for t in trades]) / sum([t[1] for t in trades]) for trades in trade_grouped_list]
    return [np.log(t_1 / t_0) for t_0, t_1 in zip(trade_price_list[:-1], trade_price_list[1:])]
