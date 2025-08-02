import logging
import numpy as np
from .test_wrap import log_behavior

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, current_front_price_brk, aon_check
from .predictors import constrained_coefficient_model_with_lastprice_features
from .OB_attributes import OB_attributes
from .own_tools.math_features import ffill, diff

log = logging.getLogger("sparsity_bmark.lead_order")
tol = 1e-3

#QUANTITY_TICK_SIZE = 10


class SpBMarkOrder(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", str,
        "Own Product ID, which is passed to the 2nd arbitrage leg synthetic order as 'other'",
        required=True
    )

    lift_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lift_slot_name", str,
        "Name of the lifting slot",
        required=True
    )

    lift_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lift_instrument_id", str,
        "Name of the lift instrument additional view, as used in the strategy template",
        required=True
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )

    max_position = SYNCONF.SyntheticOrderConfigField(
        caption="max position",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    ql_max = SYNCONF.SyntheticOrderConfigField(
        caption="maximal_allowed_queue_lag",
        expected_type=float,
        description="Maximal allowed queue lag for strategy",
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="autoTrader_reset",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    lead_closing = SYNCONF.SyntheticOrderConfigField(
        caption="lead closing",
        expected_type=bool,
        description="lead closing bool",
    )

    instrument_map = SYNCONF.SyntheticOrderConfigField(
        caption="instrument map",
        expected_type=dict,
        description="instrument map"
    )

    fair_price_buffer_size = SYNCONF.SyntheticOrderConfigField(
        caption="buffer size",
        expected_type=int,
        description="buffer size")

    fair_price_t_zero = SYNCONF.SyntheticOrderConfigField(
        caption="fair price t zero",
        expected_type=float,
        description="fair price t zero"
    )

    def get_open_position(self):
        try:
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            buy = strategy_stats.trade_spread_dict['buy']['quantity']
            sell = strategy_stats.trade_spread_dict['sell']['quantity']

            return round(buy - sell)

        except Exception as e:
            log.error(f"{e}, line number: {e.__traceback__.tb_lineno}")
            return 0


    def condition_data_check(self, data):
        self.data_columns = ['trd_price', 'b_price', 'a_price', 'ba_spread', 'a_price_sparsity', 'b_price_sparsity']
        return all([x in self.data_columns for x in data.keys()])

    def condition_long(self, data):
        x = {}
        # x['trd_gap'] = data['trd_price'] > round(data['a_price'] + self.trd_gap, 2)
        # x['ba_spread'] = data['ba_spread'] < self.bid_ask
        # x['misstrade_limit'] = data['trd_price'] < round(data['a_price'] + 0.5, 2)
        # x['sparsity'] = data['a_price_sparsity'] > self.thold_sparse and data['b_price_sparsity'] < self.thold_dense
        log.info(f"[CONDITION LONG]: {x}")
        return all(x.values())

    def condition_short(self, data):
        x = {}
        # x['trd_gap'] = data['trd_price'] < round(data['b_price'] - self.trd_gap, 2)
        # x['ba_spread'] = data['ba_spread'] < self.bid_ask
        # x['misstrade_limit'] = data['trd_price'] > round(data['b_price'] - 0.5, 2)
        # x['sparsity'] = data['b_price_sparsity'] > self.thold_sparse and data['a_price_sparsity'] < self.thold_dense
        log.info(f"[CONDITION SHORT]: {x}")
        return all(x.values())

    def push_bo_buffer(self, local_buy, local_sell, strategy_stats):
        index = strategy_stats.fairprice_dict['index']
        row = np.array(local_buy, local_sell)
        if index < (self.fair_price_buffer_size-1):
            strategy_stats.fairprice_dict['bo_buffer'][index] = row
        else:
            arr = np.roll(strategy_stats.fairprice_dict['bo_buffer'], -1, axis=0)
            arr[-1] = row
            strategy_stats['bo_buffer'] = arr

    def consecutive_true_counter(self, bool_array):
        # Create output array with same shape as input
        result = np.zeros_like(bool_array, dtype=int)

        # Process each column independently
        for col in range(bool_array.shape[1]):
            counter = 0
            for row in range(bool_array.shape[0]):
                if bool_array[row, col]:
                    counter += 1
                    result[row, col] = counter
                else:
                    counter = 0
                    result[row, col] = 0

        return result


    def prepare_data_dict(self, localview, strategy_stats):
        try:
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            self.push_bo_buffer(local_buy, local_sell, strategy_stats)
            # fairprice_dict buffer
            if strategy_stats.fairprice_dict['index'] < self.fair_price_buffer_size - 1:
                fair_price = np.nan
            else:
                w_scaler = lambda row: 1 - (np.minimum(100, row) / np.minimum(100, row).max())
                trade_prices = ffill(strategy_stats.fairprice_dict['tr_buffer'][:, 0])

                # Calculate the function for each timestamp where we have both order and trade data
                mask = ~trade_prices.isna()
                bid_diff = strategy_stats.fairprice_dict['bo_buffer'][mask, 0] - trade_prices[mask] #TODO: check logic
                ask_diff = strategy_stats.fairprice_dict['bo_buffer'][mask, 1] - trade_prices[mask]

                D = np.maximum(bid_diff, 0) + np.minimum(ask_diff, 0)
                D = D.fillna(0.0).values.reshape(-1, 1)
                mask = strategy_stats.fairprice_dict['tr_buffer'][:, 0] > 0
                W_m = self.consecutive_true_counter(~mask)
                W_m = np.apply_along_axis(w_scaler, 0, W_m)

                X = strategy_stats.fairprice_dict['tr_buffer']
                X.iloc[0] = self.fair_price_t_zero
                X_fill = ffill(X)
                change_mask = np.abs(ffill(diff(X_fill))) > 0.001
                X[change_mask] = ffill(diff(X_fill))[change_mask]
                X[X > 10.0] = 0.0
                X = ffill(X)

                fair_price = constrained_coefficient_model_with_lastprice_features(X, W_m, D, X[0],mask_thold=5,
                                                                                    lambda_value=1.0)

            ####

            obAttr = OB_attributes(localview, self.market_area)
            spread = round(local_sell - local_buy, 2)
            trade_price = strategy_stats.aux_dict['last_traded_price']

            #TODO: memory dict
            data_dict = {
                'b_price': local_buy,
                'a_price': local_sell,
                'ba_spread': spread,
                'trd_price': trade_price,
                'fair_price': fair_price
            }
            data_dict = {**data_dict}
            return data_dict
        except Exception as e:
            log.error(f"[PREPARE data_dict] - exception: {e}, lineno{e.__traceback__.tb_lineno}")
            return None

    def act(self, localview, additional_views, timestamp):
        try:
            # Set broker_id to primary (EEX)
            self.broker_id = self.broker_list[0]
            # Strategy stats object
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            # No lead action logic
            if strategy_stats.hard_sl:
                return self.remove_slot_info('[HARD STOPLOSS check] - pnl has reached stoploss, lead order is not placing slots')
            if not self.lead_closing and round(self.get_open_position()) != 0:
                return self.remove_slot_info(f'[LEAD CLOSING check] - self.lead_closing{self.lead_closing},'
                                             f' round(get_open_position){self.get_open_position()}')
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)



            if not local_buy or not local_sell:
                return self.remove_slot_info('None orders')
            # RESET BOOL
            if self.reset_bool:
                return self.remove_slot_info('RESET BOOL is TRUE')
            # ====================================================================
            log.info(f"Strategy stats: strategy stats last_trade_{strategy_stats.aux_dict['last_traded_price']}, ")

            # check last trade age
            if isinstance(strategy_stats.aux_dict['timestamp'], int) and strategy_stats.aux_dict['timestamp'] + 1 < timestamp:
                log.error('OLD TRADE')
                return self.remove_slot_info('OLD TRADE')

            log.info(f"[LAST TRADE CHECK]: self.processed_trade_id{self.processed_trade_id if hasattr(self, 'processed_trade_id') else 'not defined yet'},"
                     f"self.processed_trade_ts{self.processed_trade_ts if hasattr(self, 'processed_trade_ts') else 'not defined yet'}"
                     f"strategy_stats.aux_dict['trade_id']{strategy_stats.aux_dict['trade_id']}"
                     f"strategy_stats.aux_dict['timestamp']{strategy_stats.aux_dict['timestamp']}")

            # SKIP already processed trade ===================================
            if not strategy_stats.aux_dict['trade_id']:
                # Do nothing
                return self.remove_slot_info('[LEAD] - not trade for this product')
            if not hasattr(self, 'processed_trade_id'):
                self.processed_trade_id = strategy_stats.aux_dict['trade_id']
                self.processed_trade_ts = strategy_stats.aux_dict['timestamp']
            else:
                if self.processed_trade_id == strategy_stats.aux_dict['trade_id'] or self.processed_trade_ts > strategy_stats.aux_dict['timestamp']:
                    # Do nothing
                    return self.remove_slot_info('[LEAD] - already processed trade')
                else:
                    self.processed_trade_id = strategy_stats.aux_dict['trade_id']
                    self.processed_trade_ts = strategy_stats.aux_dict['timestamp']
            # ==================================================================

            open_position = self.get_open_position()

            # data to condition check
            data_dict = self.prepare_data_dict(localview, strategy_stats)
            if not data_dict:
                return self.remove_slot_info('prepare data error')
            if not self.condition_data_check(data_dict):
                log.error(f"[CONDITION CHECK]: data column missing - data: {data_dict}, required columns: {self.data_columns}")
                self.remove_slot_info("Condition check failed")
            log.info(f"[data_dict]: {data_dict}")
            self.strategy_stats_dict['param_dict']['b_price_sparsity'] = data_dict['b_price_sparsity']
            self.strategy_stats_dict['param_dict']['a_price_sparsity'] = data_dict['a_price_sparsity']
            # ======================================================
            long_bool = self.condition_long(data_dict)
            short_bool = self.condition_short(data_dict)

            # returns volume <-max_position;+max_position> and best order price for aggress
            price, volume = self.calculate_action(data_dict, long_bool, short_bool, open_position)

            if round(volume) != 0:
                return self.create_slot_info(
                    volume, price, localview)
            else:
                # No action
                return self.remove_slot_info("LEAD condition was not met")

        except Exception as e:
            log.error(f'[LEAD] {e}, line number: {e.__traceback__.tb_lineno}')
            # print("EXCEPTION catched", e, e.__traceback__.tb_lineno)
            return self.remove_slot_info(e)

    def calculate_action(self, data_dict, long, short, open_position):
        a_price, b_price = data_dict['a_price'], data_dict['b_price']
        volume = 0
        if long and short:
            if open_position >= 0:
                volume = round(self.max_position - open_position)
            else:
                volume = -round(self.max_position + open_position)
        elif long:
            if open_position < 0:
                volume = abs(open_position)
            else:
                volume = round(self.max_position - open_position)
        elif short:
            if open_position > 0:
                volume = -open_position
            else:
                volume = -round(self.max_position + open_position)

        price = a_price if volume > 0 else b_price
        return price, volume

    def create_slot_info(self, volume, price, localview):
        price = round(price, 2)
        direction = COMMON.Direction.buy if volume > 0 else COMMON.Direction.sell
        inverted_direction = COMMON.Direction().invert(COMMON.Direction.get(direction))
        log.info(
            f"[{self.strategy_id}] LEAD-SO-ACT-CREATE-SLOT, direction-{direction}, price-{price}, volume-{abs(volume)}, broker-{self.broker_id}"
        )
        # match broker to aggress
        _, self.broker_id = current_front_price_brk(localview,
                                                    inverted_direction,
                                                    self.broker_list, True)
        if self.broker_id == self.broker_list[0]:
            return self.remove_slot_info("Best order is EEX, no action")
        aon = aon_check(localview, inverted_direction, price, abs(volume), self.broker_id, self.market_area)
        if not aon:
            return self.remove_slot_info("AON check False")
        else:
            return self.create_slot(direction, quantity=abs(volume), price=price, info="lead_"+direction.capitalize())

    def remove_slot_info(self, reason):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        log.info(
            "[{}] {} LEAD-SO-ACT-REMOVE-SLOT: , ql: {}, reason: {}]".format(
                self.strategy_id, self.identifier, strategy_stats.aux_dict['ql'], reason)
        )
        return self.remove(reason)


