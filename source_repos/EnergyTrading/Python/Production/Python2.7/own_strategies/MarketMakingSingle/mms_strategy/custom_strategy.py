import logging
import time

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
from own_tools.instrument_key import InstrumentKey
import autotrader_core.common as COMMON
from strategy_stats import StrategyStats
from model_stats import ModelStats
from mm_bid_so import MarketMakingOrderBid
from mm_ask_so import MarketMakingOrderAsk

log = logging.getLogger("autotrader.market_making_single_strategy")


class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    broker_list = []
    fix_margin = None
    preferred_clips = None
    max_clips = None
    take_profit = None
    stop_loss = None
    bo_max = None
    idle_thres = None
    hard_stop_loss = None
    mtm_bool = None
    delivery_areas_additional = []
    ref_areas = []
    trade_id_list = []
    initialized = False
    timestamp = None

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log
        # Strategy stats
        self.stats = StrategyStats(None, self.strategy_id)
        self.model = ModelStats(None, None, self.strategy_id)
        self.timestamp = (int(time.time()) // 86400) * 86400

    @property
    def leg_instrument_key(self):
        return InstrumentKey.from_instrument_key(self.delivery_areas_additional[0])

    @property
    def inst_id_list(self):
        return [InstrumentKey().from_instrument_key(inst_key).instrument_id
                for inst_key in self.delivery_areas_additional]

    @property
    def all_delivery_areas(self):
        areas_list = [i for i in self.delivery_areas_additional]
        if not self.ref_areas:
            return areas_list
        else:
            areas_list.extend([i for i in self.ref_areas])
            return areas_list

    def on_strategy_update(self, strategy_json):
        try:
            if "steering_call" in strategy_json:
                self.handle_steering_call(strategy_json["steering_call"])
            else:
                super(CustomStrategy, self).on_strategy_update(strategy_json)
        except Exception as err:
            self.delete_standing_orders()
            log.error("Exception in on_strategy_update: %s", err)

    def handle_steering_call(self, payload):
        self.debug_log(text="{}".format(payload))
        # TASK: debug and check what payload is sent after you fix the backtesting setup
        self.debug_log(
            "[{}] Steering call activated [timestamp]: Position Spread // Position Legs [{}]: {}".format(
                self.strategy_id, int(self.stats.timestamp), self.stats.net_spread_position)
        )
        if "stats" in payload:
            self.api_export_timeseries({
                "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: self.stats.to_dict()})}
            )
        elif "model" in payload:
            output_dict = self.model.to_dict()
            output_dict['price_model_adj'] = self.stats.adjusted_model_price
            output_dict['last_price'] = self.model.last_value
            self.api_export_timeseries({
                "model": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: output_dict})}
            )
        elif "model_init" in payload:
            self.model.reset()
            self.stats.init_strategy_prices(self.exchange.products, None, self.model)
        else:
            self.debug_log("[{}] Unknown steering call code: {}".format(self.strategy_id, payload))

    def export_position_call(self):
        export_dict = self.stats.position_to_dict()
        self.debug_log(
            "[{}] Export position call activated [timestamp]: [{}]".format(
                self.strategy_id, int(self.stats.timestamp))
        )
        self.api_export_timeseries({
            "position": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: export_dict})}
        )

    def on_strategy_configuration_update(self, strategy_json):
        self.debug_log(
            "[{}] Strategy configuration update.".format(self.strategy_id)
        )
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # Create InstrumentKey Lists
        product_id_list = strategy_json["product_ids"]

        # parameters of strategy
        self.broker_list = strategy_json["broker_ids"]
        self.fix_margin = strategy_json["fix_margin"]
        self.preferred_clips = strategy_json["preferred_clips"]
        self.max_clips = strategy_json["max_clips"]
        self.take_profit = strategy_json["take_profit"]
        self.stop_loss = strategy_json["stop_loss"]
        self.bo_max = strategy_json["bo_max"]
        self.idle_thres = strategy_json["idle_thres"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]
        self.mtm_bool = strategy_json["mtm_bool"]
        # Strategy stats initiate
        leg_clip = strategy_json["leg_clip"]
        w = strategy_json["eql_weight"]
        w1 = strategy_json["mrg_weight"]
        w_std = strategy_json["std_weight"]
        eql_price = strategy_json["eql_price"]
        # Model class initiate
        model_type = strategy_json["model_type"]
        model_params = strategy_json["model_params"]
        if not self.initialized:
            self.delivery_areas_additional = [InstrumentKey(self.delivery_areas[0], product_id_list[0]).key]
            instr_key_list = [i for i in self.delivery_areas_additional]
            # Reference market
            try:
                self.ref_areas = [InstrumentKey(inst_id, prod_id).key for (inst_id, prod_id) in
                                  zip(self.delivery_areas[1:3], product_id_list[1:3])]
                instr_key_list.extend([i for i in self.ref_areas])
            except IndexError:
                self.ref_areas = []
            self.model.update_models(model_type, model_params)
            self.stats.update_instruments(instr_key_list, leg_clip, w, eql_price, w1, w_std)
            self.stats.init_strategy_prices(self.exchange.products, None, self.model)
            self.initialized = True
        self.stats.eql_value = eql_price
        self.stats.w = w
        self.stats.w1 = w1
        self.stats.w_std = w_std
        if strategy_json.get(COMMON.StrategyJsonKey.active) == True:
            self.model.reset()
            self.stats.init_strategy_prices(self.exchange.products, None, self.model)

    def on_synthetic_order(self, payload):
        print("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        # Update prices
        tuple_kd_list = []
        for o in orders:
            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            direction = o.direction
            tuple_kd_list.append((instrument_key, direction))
        tuple_list = set(tuple_kd_list)
        for instrument_key, direction in tuple_list:
            if instrument_key.key in self.all_delivery_areas:
                self.stats.update_strategy_prices(instrument_key, direction, self.exchange.products, None)
        # Update model & mtm
        self.stats.update_model_prices(self.model)
        # Create Synthetic orders for quoting
        self.quote()
        # Check balancing
        self.stats.check_balancing()
        # just call act, to trigger all product synthetic orders
        try:
            res = super(CustomStrategy, self).custom_on_order_book_update(orders, timestamp)
        except Exception as err:
            self.delete_standing_orders()
            log.error("Exception in custom_on_order_book_update: %s", err)
            res = {}
        return res

    def is_traded(self, trade):
        is_traded = False
        if trade.tags.get("portfolio_key") == self.strategy_id and trade.trade_id not in self.trade_id_list:
            if trade.direction == 'sell':
                instrument_id = trade.sell_delivery_area
            else:
                instrument_id = trade.buy_delivery_area
            product_id = trade.product.product_id
            instrument_key = InstrumentKey(instrument_id, product_id).key
            if instrument_key == self.leg_instrument_key:
                is_traded = True
        return is_traded

    def custom_on_trade_update(self, trades, timestamp):
        # self.delete_standing_orders()
        for trade in trades:
            if self.is_traded(trade):
                self.trade_id_list.append(trade.trade_id)
                self._process_single_trade(trade, timestamp)
            else:
                self.debug_log("Trade NOT recorded. Tag: {}, id: {}".format(trade.tags.get("portfolio_key"),
                                                                            trade.trade_id))
        # Create Synthetic orders for quoting
        self.quote()
        # Check balancing
        self.stats.check_balancing()
        # just call act, to trigger all product synthetic orders
        try:
            res = super(CustomStrategy, self).custom_on_trade_update(trades, timestamp)
        except Exception as err:
            self.delete_standing_orders()
            log.error("Exception in custom_on_trade_update: %s", err)
            res = {}
        return res

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "MMBidOrder": MarketMakingOrderBid,
            "MMAskOrder": MarketMakingOrderAsk,
        }

    def quote(self):
        margin_list = self.margin
        self._strategy_market_order_buy(margin_list[0])
        self._strategy_market_order_sell(margin_list[1])

    @property
    def margin(self):
        if self.model.is_std_model:
            if self.stats.is_model_std:
                margin = self.stats.w1 * self.fix_margin + (1 - self.stats.w1) * self.stats.model_std * self.stats.w_std
            else:
                return [None, None]
        else:
            margin = self.fix_margin
        if self.mtm_bool:
            if self.stats.net_spread_position == 0:
                ratio_list = [0., 0.]
            else:
                tp = self.take_profit
                sl = self.stop_loss
                mtm = self.stats.mtm
                ratio = min(max(mtm + sl, 0) / sl - 1, max(tp - mtm, 0) / (2 * tp) - .5)
                if mtm <= -sl * .5:
                    other_ratio = None
                else:
                    other_ratio = 0.
                if self.stats.net_spread_position > 0:
                    ratio_list = [other_ratio, ratio]
                else:
                    ratio_list = [ratio, other_ratio]
        else:
            ratio_list = [0., 0.]
        return [None if r is None else margin * (1 + 2 * r) for r in ratio_list]

    def _strategy_market_order_buy(self, margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            num_clips = min(self.preferred_clips, max(self.max_clips - self.stats.net_spread_position, 0))
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    (isinstance(so, MarketMakingOrderBid) and so.instrument_key == instrument_key)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingBid SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = {"identifier": so.identifier, "configuration": {"margin": margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingBid SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = {"identifier": so.identifier, "configuration": {"margin": margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing MarketMakingBid SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MMBidOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating MarketMakingBid SO {}[{}], MARGIN: {}, CLIPS: {}".format(
                    instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = self.create_bid_synthetic_order_payload_register(instrument_key, margin, num_clips)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _strategy_market_order_sell(self, margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            num_clips = min(self.preferred_clips, max(self.max_clips + self.stats.net_spread_position, 0))
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    (isinstance(so, MarketMakingOrderAsk) and so.instrument_key == instrument_key)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingOrderAsk SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = {"identifier": so.identifier, "configuration": {"margin": margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingOrderAsk SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = {"identifier": so.identifier, "configuration": {"margin": margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing MarketMakingOrderAsk SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MMAskOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create sell order
                self.debug_log("Creating MarketMakingOrderAsk SO {}[{}], MARGIN: {}, CLIPS: {}".format(
                    instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                payload = self.create_ask_synthetic_order_payload_register(instrument_key, margin, num_clips)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _process_single_trade(self, trade, timestamp):
        if trade.direction == 'sell':
            direction = COMMON.Direction.sell
            instrument_id = trade.sell_delivery_area
        else:
            direction = COMMON.Direction.buy
            instrument_id = trade.buy_delivery_area
        product_id = trade.product.product_id
        instrument_key = InstrumentKey(instrument_id, product_id).key
        self.debug_log(
            "Trade on {}[{}]: [{}]: {}@{}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price)
        )
        # Distribute trade into buckets
        try:
            self.stats.manage_trade_position(instrument_key, trade.price, trade.quantity, direction, timestamp)
            self.export_position_call()
            if -self.stats.pnl >= self.hard_stop_loss:
                self.stats.hard_sl = True
                self.debug_log(
                    "[{}] Strategy hard stop loss breached {}, PNL: {}".format(
                        self.strategy_id, self.hard_stop_loss, self.stats.pnl)
                )
        except Exception as err:
            log.error("Exception in managing position: %s", err)

    def delete_standing_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, (MarketMakingOrderBid, MarketMakingOrderAsk)):
                    self.debug_log("Removing MarketMaking SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MarketMakingOrder"}
                    self.on_synthetic_order_delete(prod, payload)
        return 0

    def create_bid_synthetic_order_payload_register(self, instrument_key, margin, num_clips):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "MMBidOrder",
            "identifier": "MM_Order_BID_" + instrument_key.key,
            "configuration": {
                "slot_name": "MM_Order_BID_" + instrument_key.key,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_list[0],
                "broker_list": self.broker_list,
                "product_id": instrument_key.product_id,
                "num_clips": num_clips,
                "margin": margin,
                "stop_loss": self.stop_loss,
                "idle_thres": self.idle_thres,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }

    def create_ask_synthetic_order_payload_register(self, instrument_key, margin, num_clips):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "MMAskOrder",
            "identifier": "MM_Order_ASK_" + instrument_key.key,
            "configuration": {
                "slot_name": "MM_Order_ASK_" + instrument_key.key,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_list[0],
                "broker_list": self.broker_list,
                "product_id": instrument_key.product_id,
                "num_clips": num_clips,
                "margin": margin,
                "stop_loss": self.stop_loss,
                "idle_thres": self.idle_thres,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }
