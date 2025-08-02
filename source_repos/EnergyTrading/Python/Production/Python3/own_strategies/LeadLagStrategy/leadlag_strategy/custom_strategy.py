import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_lib.common as COMMON
from .own_tools.instrument_key import InstrumentKey
# from own_tools.misc import api_export_trade
from .strategy_stats import StrategyStats
import time

from . import so_ll_initial
from . import so_ll_closing

# from constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID


log = logging.getLogger("autotrader.leadlag_strategy")

class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)

        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log
        self.trade_id_list=[]
        self.timestamp = (int(time.time()) // 86400) * 86400
        self.trade_counter=0
        self.initialized=False

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        self.lead_product_id = strategy_json["lead_product_id"]
        self.lag_product_id = strategy_json["lag_product_id"]
        self.broker_id = strategy_json["broker_id"]
        self.lead_brokers_list=strategy_json["lead_brokers_list"]
        self.reset_bool = False
        # Create InstrumentKey Lists
        instrument_id_list = self.delivery_areas
        product_id_list = [strategy_json["lead_product_id"],strategy_json["lag_product_id"]]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                          for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list

        # main strategy parameters

        # self.max_secs_between_trades = strategy_json["max_secs_between_trades"]
        # self.cluster_trade_num_threshold = strategy_json["cluster_trade_num_threshold"]
        # self.min_price_movement = strategy_json["min_price_movement"]

        self.MACD_long_threshold = strategy_json["MACD_long_threshold"]
        self.MACD_short_threshold = strategy_json["MACD_short_threshold"]
        self.price_diff_long_threshold = strategy_json["price_diff_long_threshold"]
        self.price_diff_short_threshold = strategy_json["price_diff_short_threshold"]
        self.combined_long_threshold = strategy_json["combined_long_threshold"]
        self.combined_short_threshold = strategy_json["combined_short_threshold"]

        self.reg_model_coef1 = strategy_json["reg_model_coef1"]
        self.reg_model_coef2 = strategy_json["reg_model_coef2"]

        self.combined_mode = strategy_json["combined_mode"]

        self.minimum_intensity = strategy_json["minimum_intensity"]

        # auxilliary strategy parameters
        self.take_profit = strategy_json["take_profit"]
        self.stop_loss = strategy_json["stop_loss"]
        self.ba_max=strategy_json["ba_max"]
        self.aggloss_thres=strategy_json["aggloss_thres"]

        self.burnout_period = strategy_json["burnout_period"]
        self.stop_profit = strategy_json["stop_profit"]
        self.makeagg_ratio = strategy_json["makeagg_ratio"]
        self.trail_stop = strategy_json["trail_stop"]

        # other parameters
        self.preferred_quantity = strategy_json["preferred_quantity"]
        self.max_quantity = strategy_json["max_quantity"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]

        self.ql_max=strategy_json["ql_max"]

        self.time_of_init=str(int(round(time.time())))
        self.trade_counter=0

        self.initialized=False

        if not self.initialized:
            self.stats = StrategyStats(None, self.strategy_id, self.caption)
            self.stats.update_instruments(self.instrument_keys, self.time_of_init)
            self.initialized = True


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
            "[{}] Steering call for strategy stats made.".format(
                self.strategy_id)
        )
        if "stats" in payload:
            self.api_export_timeseries({
                "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: {**self.stats.to_dict(), **{'reset_bool': self.reset_bool}}})}
            )
        else:
            self.debug_log("[{}] Unknown steering call code: {}".format(self.strategy_id, payload))

    def on_synthetic_order(self, payload):
        print(("DEBUG on_synthetic_order: ", payload))
        self.debug_log("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_closing_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        self.quote()

        # Update prices
        tuple_kd_list = []
        for o in orders:
            #print(("DEBUG ORDER UPDATE: ",o.original_user, o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction, o.broker_id))
            #self.debug_log("DEBUG ORDER UPDATE: " + o.product.product_id + " " + o.delivery_area_id + " " + str(
            #    o.price) + " " + str(o.quantity) + " " + o.direction + " " + str(o.broker_id))

            self.stats.update_locked_until(o.product.locked_until)
            if o.tags.get('portfolio_key') == self.strategy_id:
                self._process_single_order(o, timestamp)

            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            direction = o.direction
            tuple_kd_list.append((instrument_key, direction))

        tuple_list = set(tuple_kd_list)
        for instrument_key, direction in tuple_list:
            if instrument_key.key in self.instrument_keys:
                self.stats.update_strategy_prices(instrument_key, direction, self.exchange.products, None)


        if ((self.stats.in_position() and any([instrument_key.key==self.instrument_keys[1] for instrument_key, direction in tuple_list]))
                or (not self.stats.in_position() and (self.stats.check_for_new_lead_trade() or self.stats.check_one_second_within_last_lead_trade()))):

            #update mark_to_market value
            try:
                self.stats.mtm_calc_and_push()
            except Exception as err:
                log.error("Exception in updating mark_to_market value: %s", err)

            self.stats.aux_dict['ql'] = self.autotrader.queue_lag[self.exchange.caption]

            # just call act, to trigger all product synthetic orders
            try:
                res = self._call_act_orders(timestamp)
            except Exception as err:
                #self.delete_standing_orders()
                log.error("Exception in custom_on_order_book_update: %s", err)
                res = {}
            self._update_closing_orders()
            return res

    def custom_on_public_trade_update(self, trades, timestamp):
        for trade in trades:
            #print("On Public Trade Update {}[{}]: {}@{} trade_id: {}, execution_time: {}, aggresor_broker: {}, initiator_broker: {}".format(trade.buy_delivery_area, trade.product.product_id,
            #                                                        trade.quantity, trade.price, trade.trade_id, trade.execution_time, trade.aggressor_broker_id, trade.initiator_broker_id))
            log.debug("On Public Trade Update {}[{}]: {}@{} trade_id: {}, execution_time: {}, aggresor_broker: {}, initiator_broker: {}".format(trade.buy_delivery_area, trade.product.product_id,
                                                                    trade.quantity, trade.price, trade.trade_id, trade.execution_time, trade.aggressor_broker_id, trade.initiator_broker_id))

            if ((trade.buy_delivery_area + '_' + trade.product.product_id == self.instrument_keys[0]) or (trade.sell_delivery_area + '_' + trade.product.product_id == self.instrument_keys[0])) \
                and ('OwnTrade' not in str(type(trade)))\
                and trade.aggressor_broker_id in self.lead_brokers_list\
                and trade.initiator_broker_id in self.lead_brokers_list: #check if the trade is from lead product, if yes then write it into strategy_stats
                self.stats.increment_lead_trade_list(trade)

        #res = super(CustomStrategy, self).on_trade_update(trades, timestamp)
        # just call act, to trigger all product synthetic orders
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            #self.delete_standing_orders()
            log.error("Exception in custom_on_trade_update: %s", err)
            res = {}
        self.stats.aux_dict['lead_last_trade_id'] = self.stats.calc_lead_last_trade_id()
        self.stats.aux_dict['ql'] = self.autotrader.queue_lag[self.exchange.caption]
        self._update_closing_orders()
        return res

    def custom_on_trade_update(self, trades, timestamp):
        for trade in trades:
            #print("On Trade Update {}[{}]: {}@{} trade_id: {},  execution_time: {}, aggresor_broker: {}, initiator_broker: {}".format(trade.buy_delivery_area, trade.product.product_id,
            #                                                        trade.quantity, trade.price, trade.trade_id, trade.execution_time, trade.aggressor_broker_id, trade.initiator_broker_id))
            log.debug("On Trade Update {}[{}]: {}@{} trade_id: {},  execution_time: {}, aggresor_broker: {}, initiator_broker: {}".format(trade.buy_delivery_area, trade.product.product_id,
                                                                    trade.quantity, trade.price, trade.trade_id, trade.execution_time, trade.aggressor_broker_id, trade.initiator_broker_id))

            if ((trade.buy_delivery_area + '_' + trade.product.product_id == self.instrument_keys[0]) or (trade.sell_delivery_area + '_' + trade.product.product_id == self.instrument_keys[0]))\
                and ('OwnTrade' not in str(type(trade)))\
                and trade.aggressor_broker_id in self.lead_brokers_list\
                and trade.initiator_broker_id in self.lead_brokers_list: #check if the trade is from lead product, if yes then write it into strategy_stats
                self.stats.increment_lead_trade_list(trade)


            if trade.tags.get("portfolio_key") == self.strategy_id:
                if trade.trade_id not in self.trade_id_list:
                    self._process_single_trade(trade, timestamp)
                    self.trade_id_list.append(trade.trade_id)
                    self.trade_counter+=1

        #res = super(CustomStrategy, self).on_trade_update(trades, timestamp)
        # just call act, to trigger all product synthetic orders
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            #self.delete_standing_orders()
            log.error("Exception in custom_on_trade_update: %s", err)
            res = {}
        self.stats.aux_dict['lead_last_trade_id'] = self.stats.calc_lead_last_trade_id()
        self._update_closing_orders()
        return res

    ##################################################################################################

    def create_ll_initial_synthetic_order_payload_register(self, instrument_key):

        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "InitialOrder",
            "identifier": "Init_Order_"+instrument_key.key+"_"+self.time_of_init,
            "configuration": {
                "slot_name": "Init_Order_"+instrument_key.key+"_"+self.time_of_init,
                "market_area": instrument_key.instrument_id,

                # "product_id": PRODUCT_ID,
                "strategy_id": self.strategy_id,
                "lead_instrument_id": self.instrument_ids[0],
                "lead_product_id": self.lead_product_id,
                "lag_product_id": instrument_key.product_id,
                "broker_id": self.broker_id,

                "MACD_long_threshold": self.MACD_long_threshold,
                "MACD_short_threshold": self.MACD_short_threshold,
                "price_diff_long_threshold": self.price_diff_long_threshold,
                "price_diff_short_threshold": self.price_diff_short_threshold,

                "combined_long_threshold": self.combined_long_threshold,
                "combined_short_threshold": self.combined_short_threshold,

                "reg_model_coef1": self.reg_model_coef1,
                "reg_model_coef2": self.reg_model_coef2,

                "combined_mode": self.combined_mode,

                "minimum_intensity": self.minimum_intensity,

                "ba_max": self.ba_max,

                "closing_slot_name": "CLOSING_" + "Init_Order_" + instrument_key.key + "_" + self.time_of_init,
                "closing_product_id": instrument_key.product_id,
                "closing_instrument_id": instrument_key.instrument_id,

                "strategy_stats_dict": self.stats.to_dict(),

                "reset_bool": self.reset_bool,
                "max_quantity": self.max_quantity,
                "ql_max": self.ql_max

            }
        }

    def create_ll_closing_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.closing_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "ClosingOrder",
            "identifier": "CLOSING_" + so.slot_name,
            "configuration": {
                "slot_name": "CLOSING_" + so.slot_name,
                "market_area": so.closing_instrument_id,
                # "product_id": so.lift_product_id,
                "init_instrument_id": so.market_area,
                "init_slot_name": so.slot_name,
                "init_product_id": so.lag_product_id,

                "broker_id": self.broker_id,

                "strategy_id": self.strategy_id,
                "strategy_stats_dict": self.stats.to_dict(),

                "take_profit": self.take_profit,
                "stop_loss": self.stop_loss,
                "aggloss_thres": self.aggloss_thres,

                "burnout_period": self.burnout_period,
                "stop_profit": self.stop_profit,
                "makeagg_ratio": self.makeagg_ratio,
                "trail_stop": self.trail_stop,

                "reset_bool": self.reset_bool,
                "max_quantity": self.max_quantity,
                "ba_max": self.ba_max,

                #"idle_threshold": self.idle_thres
            }
        }

    def quote(self):
        # TODO check for mutability of dictionaries
        if self.check_stats_dict_all:
            self._simple_init_order()
        else:
            self.reset_bool = True
            self._simple_init_order()
            self._update_closing_orders()
            self.debug_log("Arbitrage reset, all SO must stop posting orders")

    def _simple_init_order(self):
        for key in self.instrument_keys[1:2]:
            instrument_key = InstrumentKey().from_instrument_key(key)
            init_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    isinstance(so, so_ll_initial.InitialOrder)]
            if len(init_orders) == 1:
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Initial SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier} if not self.reset_bool else {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(init_orders) > 1:
                # Should not happen
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Initial SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier} if not self.reset_bool else {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in init_orders[1:]:
                    self.debug_log("Removing Initial SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "InitialOrder"} if not self.reset_bool else {"identifier": so.identifier, "synthetic_order_type": "InitialOrder", "configuration": {"reset_bool": self.reset_bool}}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating Initial SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print(("Creating Initial SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)))
                payload = self.create_ll_initial_synthetic_order_payload_register(instrument_key)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_closing_orders(self):
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, so_ll_closing.ClosingOrder):
                    if any([(init_so.slot_name.startswith("Init_Order_")
                             and init_so.market_area == so.init_instrument_id)
                            for init_so in list(self.product_synthetic_order_mapping[so.init_product_id].values())]):
                        # if we already have a CLOSING for this, then do nothing
                        self.debug_log("Found INIT for CLOSING SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing CLOSING SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "ClosingOrder"} if not self.reset_bool else {"identifier": so.identifier, "synthetic_order_type": "ClosingOrder", "configuration": {"reset_bool": self.reset_bool}}
                        self.on_synthetic_order_delete(prod, payload)


                elif isinstance(so, so_ll_initial.InitialOrder):
                    if any([(closing_so.slot_name == "CLOSING_" + so.slot_name
                             and closing_so.market_area == so.closing_instrument_id)
                            for closing_so in list(self.product_synthetic_order_mapping[so.closing_product_id].values())]):
                        # if we already have a CLOSING for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating CLOSING SO {} [{}]".format(so.identifier, prod))
                        print("Creating CLOSING SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_ll_closing_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.closing_product_id, payload)

    def _call_act_orders(self, timestamp):
        products = []
        for inst_id in set(self.instrument_ids):
            products.extend(self.exchange.products.get_active_products(inst_id))
        res = self.act(timestamp, products)
        self.__update_status_balancing()
        return res

    def __update_status_balancing(self):
        instrument_key_list = [InstrumentKey().from_instrument_key(key) for key in self.instrument_keys]

        for inst_key in instrument_key_list:
            closing_orders_dict = {inst_key.key: so.status
                                for so in list(self.product_synthetic_order_mapping[inst_key.product_id].values())
                                if isinstance(so, so_ll_closing.ClosingOrder)}

            if any([status!=COMMON.SyntheticOrderStates.passive for status in list(closing_orders_dict.values())]):
                self.stats.balancing_dict[inst_key.key]=True
                self.debug_log("self.stats.balancing for "+ str(inst_key.key)+" set to True")
            else:
                self.stats.balancing_dict[inst_key.key]=False
                self.debug_log("self.stats.balancing for "+ str(inst_key.key)+" set to False")



    def _process_single_trade(self, trade, timestamp):
        if trade.direction == 'sell':
            direction = COMMON.Direction.sell
            instrument_id = trade.sell_delivery_area
        else:
            direction = COMMON.Direction.buy
            instrument_id = trade.buy_delivery_area
        product_id = trade.product.product_id
        instrument_key = InstrumentKey(instrument_id, product_id).key
        slot_name=trade.tags.get('strategy_slot')

        if slot_name not in self.stats.slot_dict.keys():
            return

        self.debug_log(
            "Trade on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price, slot_name)
        )
        print(("Trade on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price, slot_name)))

        # Distribute trade into buckets
        try:
            self.stats.increment_slot_dict_trade(trade)
            self.stats.manage_trade_position(instrument_key, trade.price, trade.quantity, direction, timestamp)
            if -self.stats.pnl >= self.hard_stop_loss:
                self.stats.bool_dict['hard_stop_loss'] = True
                self.debug_log(
                    "[{}] Strategy hard stop loss breached {}, PNL: {}".format(
                        self.strategy_id, self.hard_stop_loss, self.stats.pnl)
                )
        except Exception as err:
            log.error("Exception in managing position: %s", err)

    def _process_single_order(self, order, timestamp):
        product_id = order.product.product_id
        instrument_id = order.delivery_area_id
        slot_name=order.tags.get('strategy_slot')

        self.debug_log(
            "Order on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, order.direction,
                                                              order.quantity, order.price, slot_name)
        )

        self.stats.increment_slot_dict_order(order)

    @property
    def check_stats_dict_all(self):
        slot_dict_id = id(self.stats.slot_dict)
        so_slot_dict_id_list = [id(x.strategy_stats_dict['slot_dict']) for tr in
                           self.product_synthetic_order_mapping.values() for x in tr.values()]

        lead_trade_list_id = id(self.stats.lead_trade_list)
        so_lead_trade_list_id_list = [id(x.strategy_stats_dict['lead_trade_list']) for tr in
                           self.product_synthetic_order_mapping.values() for x in tr.values()]
        return all([x == slot_dict_id for x in so_slot_dict_id_list]) and all([x == lead_trade_list_id for x in so_lead_trade_list_id_list])

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "InitialOrder": so_ll_initial.InitialOrder,
            "ClosingOrder": so_ll_closing.ClosingOrder
        }
