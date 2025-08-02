import logging
import time
import datetime as dt

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
from .own_tools.instrument_key import InstrumentKey
import autotrader_lib.common as COMMON
from .strategy_stats import StrategyStats
from .model_stats import ModelStats
from .mm_bid_so import MarketMakingOrderBid
from .mm_ask_so import MarketMakingOrderAsk
from .mm_lift_so_new import MarketMakingOrderLift

log = logging.getLogger("autotrader.market_making_strategy")


class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    broker_list = []
    fix_margin = None
    max_margin = None
    preferred_clips = None
    max_clips = None
    take_profit = None
    stop_loss = None
    bo_max = None
    idle_thres = None
    market_depth=None
    hard_stop_loss = None
    mtm_bool = None
    delivery_areas_additional = []
    opposite_areas_dict = {}
    ref_area = None
    trade_id_list = []
    initialized = False
    reset_bool = False
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
    def leg1_instrument_key(self):
        return InstrumentKey.from_instrument_key(self.delivery_areas_additional[0])

    @property
    def leg2_instrument_key(self):
        return InstrumentKey.from_instrument_key(self.delivery_areas_additional[1])

    @property
    def inst_id_list(self):
        return [InstrumentKey().from_instrument_key(inst_key).instrument_id
                for inst_key in self.delivery_areas_additional]

    @property
    def all_delivery_areas(self):
        areas_list = [i for i in self.delivery_areas_additional]
        if self.ref_area is None:
            return areas_list
        else:
            areas_list.append(self.ref_area)
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
            "[{}] Steering call activated [timestamp]: Position Spread // Position Legs [{}]: {}//{}".format(
                self.strategy_id, int(self.stats.timestamp), self.stats.net_spread_position,
                self.stats.total_net_position)
        )
        if "stats" in payload:
            self.api_export_timeseries({
                "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: self.stats.to_dict_ex()})}
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
        # Reference market
        # ref_instr_ids = strategy_json["ref_inst_ids"]
        # ref_product_ids = strategy_json["ref_product_ids"]

        # parameters of strategy
        self.broker_list = strategy_json["broker_ids"]
        self.fix_margin = strategy_json["fix_margin"]
        self.max_margin = strategy_json["max_margin"]
        self.preferred_clips = strategy_json["preferred_clips"]
        self.max_clips = strategy_json["max_clips"]
        self.take_profit = strategy_json["take_profit"]
        self.stop_loss = strategy_json["stop_loss"]
        self.bo_max = strategy_json["bo_max"]
        self.idle_thres = strategy_json["idle_thres"]
        self.market_depth = strategy_json["market_depth"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]
        self.mtm_bool = strategy_json["mtm_bool"]
        # Strategy stats initiate
        quote_list = [strategy_json["quote_leg1"], strategy_json["quote_leg2"],
                      strategy_json["quote_buy"], strategy_json["quote_sell"]]
        ql_max = strategy_json["ql_max"]
        leg1_clip = strategy_json["leg1_clip"]
        leg2_clip = strategy_json["leg2_clip"]
        price_coeff = strategy_json["price_coeff"]
        w = strategy_json["eql_weight"]
        w1 = strategy_json["mrg_weight"]
        w_std = strategy_json["std_weight"]
        eql_price = strategy_json["eql_price"]
        # Model class initiate
        model_type = strategy_json["model_type"]
        model_params = strategy_json["model_params"]
        if not self.initialized:
            self.delivery_areas_additional = [InstrumentKey(inst_id, prod_id).key
                                              for (inst_id, prod_id) in zip(self.delivery_areas[:2], product_id_list[:2])]
            self.opposite_areas_dict = {self.delivery_areas_additional[0]: self.delivery_areas_additional[1],
                                        self.delivery_areas_additional[1]: self.delivery_areas_additional[0]}
            instr_key_list = [i for i in self.delivery_areas_additional]
            # Reference market
            try:
                self.ref_area = InstrumentKey(self.delivery_areas[2], product_id_list[2]).key
                instr_key_list.append(self.ref_area)
            except IndexError:
                self.ref_area = None
            self.model.update_models(model_type, model_params)
            self.stats.update_instruments(instr_key_list, leg1_clip, leg2_clip, w, eql_price, w1, w_std, quote_list,
                                          price_coeff)
            self.stats.init_strategy_prices(self.exchange.products, None, self.model)
            self.initialized = True
        self.stats.eql_value = eql_price
        self.stats.w = w
        self.stats.w1 = w1
        self.stats.w_std = w_std
        self.stats.ql_max = ql_max
        self.stats.quote_bool_dict = {k: b for k, b in zip(self.stats.instrument_list + ['buy', 'sell'], quote_list)}
        if strategy_json.get(COMMON.StrategyJsonKey.active):
            self.model.reset()
            self.stats.init_strategy_prices(self.exchange.products, None, self.model)
        self.__check_params()

    def on_synthetic_order(self, payload):
        print(("DEBUG on_synthetic_order: ", payload))
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_lift_orders()
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        timestamp2 = dt.datetime.fromtimestamp(timestamp)

        # Update prices
        tuple_kd_list = []
        for o in orders:
            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            if instrument_key.key in self.all_delivery_areas:
                direction = o.direction
                tuple_kd_list.append((instrument_key, direction))
        tuple_list = set(tuple_kd_list)
        if not tuple_list:
            res = {}
        else:
            for instrument_key, direction in tuple_list:
                if instrument_key.key in self.all_delivery_areas:
                    self.stats.update_strategy_prices(instrument_key, direction, self.exchange.products, None)
            self.stats.timestamp = timestamp
            self.stats.ql = self.autotrader.queue_lag[self.exchange.caption]
            # Update model & mtm
            self.stats.update_model_prices(self.model)
            # Create Synthetic orders for quoting
            self.quote()
            try:
                if (self.margin[0] + self.model.spread_value) < self.stats.bid_spread:
                    pass
                elif (self.margin[0] - self.model.spread_value) > self.stats.ask_spread:
                    pass
            except:
                pass
            # Check balancing
            self.stats.check_balancing()
            # just call act, to trigger all product synthetic orders
            try:
                res = self._call_act_orders(timestamp)
            except Exception as err:
                self.delete_standing_orders()
                log.error("Exception in custom_on_order_book_update: %s", err)
                res = {}
            self._update_lift_orders()
        return res

    def custom_on_trade_update(self, trades, timestamp):
        # self.delete_standing_orders()
        for trade in trades:
            if trade.tags.get("portfolio_key") == self.strategy_id and trade.trade_id not in self.trade_id_list:
                self.stats.balancing = True
                self.trade_id_list.append(trade.trade_id)
                self._process_single_trade(trade, timestamp)
            else:
                self.debug_log("Trade NOT recorded. Tag: {}, id: {}".format(trade.tags.get("portfolio_key"),
                                                                            trade.trade_id))
        # res = super(CustomStrategy, self).custom_on_trade_update(trades, timestamp)
        # just call act, to trigger all product synthetic orders
        # Create Synthetic orders for quoting
        self.quote()
        # Check balancing
        self.stats.check_balancing()
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            self.delete_standing_orders()
            log.error("Exception in custom_on_trade_update: %s", err)
            res = {}
        self._update_lift_orders()
        return res

    def _update_lift_orders(self):
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, MarketMakingOrderLift):
                    if any([(lead_so.slot_name.startswith("MM_Order_")
                             and lead_so.market_area == so.other_instrument_id)
                            for lead_so in list(self.product_synthetic_order_mapping[so.other_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log(
                                "Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        else:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, (MarketMakingOrderBid, MarketMakingOrderAsk)):
                    if any([(lift_so.slot_name == "LIFT_" + so.other_instrument_id
                             and lift_so.market_area == so.other_instrument_id)
                            for lift_so in list(self.product_synthetic_order_mapping[so.other_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(so.product_id, payload)
                            self.debug_log(
                                "Found LIFT for LEAD SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.other_product_id, payload)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "MMBidOrder": MarketMakingOrderBid,
            "MMAskOrder": MarketMakingOrderAsk,
            "MMLiftOrder": MarketMakingOrderLift
        }

    def __check_params(self):
        pass

    def __update_status_lift(self):
        instrument_key_list = [InstrumentKey().from_instrument_key(key) for key in self.delivery_areas_additional]
        lift_orders_dict = {ik.key: so.status for ik in instrument_key_list
                            for so in list(self.product_synthetic_order_mapping[ik.product_id].values())
                            if isinstance(so, MarketMakingOrderLift)}
        for inst_key, status in list(lift_orders_dict.items()):
            self.stats.update_lift_instkey(inst_key, status)

    def _call_act_orders(self, timestamp):
        products = []
        for inst_id in set(self.inst_id_list):
            products.extend(self.exchange.products.get_active_products(inst_id))
        res = self.act(timestamp, products)
        self.__update_status_lift()
        return res

    def quote(self):
        margin_list = self.margin
        if self.check_stats_dict_all:
            self._strategy_market_order_buy(margin_list[0], margin_list[2])
            self._strategy_market_order_sell(margin_list[1], margin_list[3])
        else:
            self.reset_bool = True
            self._strategy_market_order_buy(margin_list[0], margin_list[2])
            self._strategy_market_order_sell(margin_list[1], margin_list[3])
            self.__update_status_lift()
            self.debug_log("MarketMaking reset, all SO must stop posting orders")

    @property
    def margin(self):
        size_margin = [0,0]
        # size_margin = .3 * self.fix_margin * (self.stats.net_spread_position // self.preferred_clips) / self.max_clips
        if self.model.is_std_model:
            if self.stats.is_model_std:
                if self.stats.net_spread_position <1:
                margin = self.stats.w1 * self.fix_margin + (1 - self.stats.w1) * self.stats.model_std * self.stats.w_std
            else:
                return [None, None, None, None]
        else:
            margin = self.fix_margin

        if self.max_clips <= 1:
            size_margin = [0, 0]
        else:
            size_increment = self.stats.net_spread_position//self.preferred_clips

        else:
            pos = abs(self.stats.net_spread_position)
            c1 = (max(pos - self.preferred_clips, 0) // self.preferred_clips) / (self.max_clips - 1)
            c2 = (pos // self.preferred_clips) / (self.max_clips - 1)
            if self.stats.net_spread_position >= 0:
                size_margin = [c2 * (self.max_margin - self.fix_margin), -c1 * margin]
            else:
                size_margin = [-c1 * margin, c2 * (self.max_margin - self.fix_margin)]
        if self.mtm_bool:
            if self.stats.net_spread_position == 0:
                ratio_list = [0., 0.]
            else:
                tp = self.take_profit
                sl = self.stop_loss
                mtm = self.stats.mtm
                if abs(mtm)>0:
                    pass
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
        return [None if r is None else margin * (1 + 2 * r) for r in ratio_list] + size_margin


    @property
    def margin(self):
        # Set default ba_spread in case current price is already out of the bands
        def_ba = 0.05

        # size_margin = .3 * self.fix_margin * (self.stats.net_spread_position // self.preferred_clips) / self.max_clips
        if self.model.is_std_model:
            if self.stats.is_model_std:
                size_increment = abs(self.stats.net_spread_position)//self.preferred_clips + 1
                std = self.stats.model_std * self.stats.w_std * size_increment
                base_bands = [self.stats.model_price - std, self.stats.model_price + std]
                if base_bands[1]<self.stats.bid_spread:
                    ask_margin = self.stats_bid_spread - self.stats.model_price + def_ba
                else:
                    ask_margin = base_bands[1]
                if base_bands[0]>self.stats.ask_spread:
                    bid_margin = self.stats.model_price - self.stats_ask_spread + def_ba
                else:
                    bid_margin = base_bands[0]
                margin = self.stats.w1 * self.fix_margin + (1 - self.stats.w1) * self.stats.model_std * self.stats.w_std
            else:
                return [None, None, None, None]
        else:
            margin = self.fix_margin
        if self.max_clips <= 1:
            size_margin = [0, 0]
        else:
            pos = abs(self.stats.net_spread_position)
            c1 = (max(pos - self.preferred_clips, 0) // self.preferred_clips) / (self.max_clips - 1)
            c2 = (pos // self.preferred_clips) / (self.max_clips - 1)
            if self.stats.net_spread_position >= 0:
                size_margin = [c2 * (self.max_margin - self.fix_margin), -c1 * margin]
            else:
                size_margin = [-c1 * margin, c2 * (self.max_margin - self.fix_margin)]
        if self.mtm_bool:
            if self.stats.net_spread_position == 0:
                ratio_list = [0., 0.]
            else:
                tp = self.take_profit
                sl = self.stop_loss
                mtm = self.stats.mtm
                if abs(mtm)>0:
                    pass
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
        return [None if r is None else margin * (1 + 2 * r) for r in ratio_list] + size_margin

    def _strategy_market_order_buy(self, margin, size_margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            other_instrument_key = InstrumentKey().from_instrument_key(self.opposite_areas_dict[key])
            num_clips = min(self.preferred_clips, max(self.max_clips - self.stats.net_spread_position, 0))
            market_making_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    (isinstance(so, MarketMakingOrderBid) and so.instrument_key == instrument_key)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingBid SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, num_clips)
                )
                if self.reset_bool:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips,
                                                 "reset_bool": self.reset_bool}}
                else:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingBid SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, size_margin,
                    num_clips)
                )
                if self.reset_bool:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips,
                                                 "reset_bool": self.reset_bool}}
                else:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips}}
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
                    instrument_key.instrument_id, instrument_key.product_id, margin, size_margin, num_clips)
                )
                payload = self.create_bid_synthetic_order_payload_register(instrument_key, other_instrument_key,
                                                                           margin, size_margin, num_clips)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _strategy_market_order_sell(self, margin, size_margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            other_instrument_key = InstrumentKey().from_instrument_key(self.opposite_areas_dict[key])
            num_clips = min(self.preferred_clips, max(self.max_clips + self.stats.net_spread_position, 0))
            market_making_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    (isinstance(so, MarketMakingOrderAsk) and so.instrument_key == instrument_key)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingOrderAsk SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, size_margin,
                    num_clips)
                )
                if self.reset_bool:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips,
                                                 "reset_bool": self.reset_bool}}
                else:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingOrderAsk SO {} {}[{}], MARGIN: {}, CLIPS: {}".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id, margin, size_margin,
                    num_clips)
                )
                if self.reset_bool:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips,
                                                 "reset_bool": self.reset_bool}}
                else:
                    payload = {"identifier": so.identifier,
                               "configuration": {"margin": margin, "size_margin": size_margin, "num_clips": num_clips}}
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
                    instrument_key.instrument_id, instrument_key.product_id, margin, size_margin, num_clips)
                )
                payload = self.create_ask_synthetic_order_payload_register(instrument_key, other_instrument_key,
                                                                           margin, size_margin, num_clips)
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
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, MarketMakingOrderBid):
                    self.debug_log("Removing MarketMaking BID SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MMBidOrder"}
                    self.on_synthetic_order_delete(prod, payload)
                elif isinstance(so, MarketMakingOrderAsk):
                    self.debug_log("Removing MarketMaking ASK SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MMAskOrder"}
                    self.on_synthetic_order_delete(prod, payload)
                elif isinstance(so, MarketMakingOrderLift):
                    self.debug_log("Removing Lift SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MMLiftOrder"}
                    self.on_synthetic_order_delete(prod, payload)
        return 0

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.other_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "MMLiftOrder",
            "identifier": "LIFT_" + so.other_instrument_id,
            "configuration": {
                "slot_name": "LIFT_" + so.other_instrument_id,
                "market_area": so.other_instrument_id,
                "broker_id": self.broker_list[0],
                "broker_list": self.broker_list,
                "product_id": so.other_product_id,
                "other_instrument_id": so.market_area,
                "other_product_id": so.product_id,
                "num_clips": self.preferred_clips,
                "margin": self.fix_margin,
                "stop_loss": self.stop_loss,
                "bo_max": self.bo_max,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }

    def create_bid_synthetic_order_payload_register(self, instrument_key, other_instrument_key, margin, size_margin,
                                                    num_clips):
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
                "mkt1_instrument_key": self.leg1_instrument_key.key,
                "product_id": instrument_key.product_id,
                "other_instrument_id": other_instrument_key.instrument_id,
                "other_product_id": other_instrument_key.product_id,
                "num_clips": num_clips,
                "margin": margin,
                "size_margin": size_margin,
                "stop_loss": self.stop_loss,
                "idle_thres": self.idle_thres,
                "market_depth": self.market_depth,
                "strategy_stats_dict": self.stats,
                "reset_bool": self.reset_bool,
                "strategy_id": self.strategy_id
            }
        }

    def create_ask_synthetic_order_payload_register(self, instrument_key, other_instrument_key, margin, size_margin,
                                                    num_clips):
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
                "mkt1_instrument_key": self.leg1_instrument_key.key,
                "product_id": instrument_key.product_id,
                "other_instrument_id": other_instrument_key.instrument_id,
                "other_product_id": other_instrument_key.product_id,
                "num_clips": num_clips,
                "margin": margin,
                "size_margin": size_margin,
                "stop_loss": self.stop_loss,
                "idle_thres": self.idle_thres,
                "market_depth": self.market_depth,
                "strategy_stats_dict": self.stats,
                "reset_bool": self.reset_bool,
                "strategy_id": self.strategy_id
            }
        }

    @property
    def check_stats_dict_all(self):
        stat_id = id(self.stats.trade_leg_dict)
        so_stat_id_list = [id(x.strategy_stats_dict['trade_leg_dict']) for tr in
                           self.product_synthetic_order_mapping.values() for x in tr.values()]
        return all([x == stat_id for x in so_stat_id_list])
