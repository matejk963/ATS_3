import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_core.common as COMMON
from own_tools.instrument_key import InstrumentKey
# from own_tools.misc import api_export_trade
from strategy_stats import StrategyStats
import time

import so_ll_initial
import so_ll_closing

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


    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        self.lead_product_id = strategy_json["lead_product_id"]
        self.lag_product_id = strategy_json["lag_product_id"]
        self.broker_id = strategy_json["broker_id"]

        # Create InstrumentKey Lists
        instrument_id_list = self.delivery_areas
        product_id_list = [strategy_json["lag_product_id"]]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                          for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list

        # main strategy parameters
        self.max_secs_between_trades = strategy_json["max_secs_between_trades"]
        self.cluster_trade_num_threshold = strategy_json["cluster_trade_num_threshold"]
        self.min_price_movement = strategy_json["min_price_movement"]

        # auxilliary strategy parameters
        self.take_profit = strategy_json["take_profit"]
        self.stop_loss = strategy_json["stop_loss"]
        self.trail_tp_bool = strategy_json["trail_tp_bool"]
        self.trailing_tp_tau = strategy_json["trailing_tp_tau"]
        self.ba_max=strategy_json["ba_max"]

        # other parameters
        self.preferred_quantity = strategy_json["preferred_quantity"]
        self.max_quantity = strategy_json["max_quantity"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]

        self.ql_max=strategy_json["ql_max"]

        self.stats = StrategyStats(None, self.strategy_id, self.caption)
        self.time_of_init=str(int(round(time.time())))
        self.trade_counter=0

        self.initialized=False

        if not self.initialized:
            self.stats.update_instruments(self.instrument_keys)
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
                "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: self.stats.to_dict()})}
            )
        else:
            self.debug_log("[{}] Unknown steering call code: {}".format(self.strategy_id, payload))

    def on_synthetic_order(self, payload):
        print("DEBUG on_synthetic_order: ", payload)
        self.debug_log("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_closing_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        # Update prices
        tuple_kd_list = []
        for o in orders:
            print("DEBUG ORDER UPDATE: ",o.original_user, o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction, o.broker_id)
            self.debug_log("DEBUG ORDER UPDATE: " + o.product.product_id + " " + o.delivery_area_id + " " + str(
                o.price) + " " + str(o.quantity) + " " + o.direction + " " + str(o.broker_id))

            if o.tags.get('portfolio_key') == self.strategy_id:
                self._process_single_order(o, timestamp)

            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            direction = o.direction
            tuple_kd_list.append((instrument_key, direction))

        tuple_list = set(tuple_kd_list)
        for instrument_key, direction in tuple_list:
            if instrument_key.key in self.instrument_keys:
                self.stats.update_strategy_prices(instrument_key, direction, self.exchange.products, None)


        #update mark_to_market value
        try:
            self.stats.mtm_calc_and_push()
        except Exception as err:
            log.error("Exception in updating mark_to_market value: %s", err)

        self.stats.ql = self.autotrader.queue_lag[self.exchange.caption]
        self.quote()

        # just call act, to trigger all product synthetic orders
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            #self.delete_standing_orders()
            log.error("Exception in custom_on_order_book_update: %s", err)
            res = {}
        self._update_closing_orders()
        return res

    def custom_on_trade_update(self, trades, timestamp):
        for trade in trades:
            # print("Trade {}[{}]: [{}]: {}@{}".format(trade.instrument_id, trade.product_id, trade.direction,
            #                                                         trade.quantity, trade.price))
            print('TRADE!!!')
            if trade.tags.get("portfolio_key") == self.strategy_id:
                if trade.trade_id not in self.trade_id_list:
                    self._process_single_trade(trade, timestamp)
                    self.trade_id_list.append(trade.trade_id)
                    self.trade_counter+=1

            if (trade.buy_delivery_area + '_' + trade.product.product_id == self.lead_product_id) or (trade.sell_delivery_area + '_' + trade.product.product_id == self.lead_product_id): #check if the trade is from lead product, if yes then write it into strategy_stats
                self.stats.increment_lead_trade_list(trade)

        #res = super(CustomStrategy, self).on_trade_update(trades, timestamp)
        # just call act, to trigger all product synthetic orders
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            #self.delete_standing_orders()
            log.error("Exception in custom_on_trade_update: %s", err)
            res = {}
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
                "lead_product_id": self.lead_product_id,
                "lag_product_id": instrument_key.product_id,
                "broker_id": self.broker_id,

                "max_secs_between_trades": self.max_secs_between_trades,
                "cluster_trade_num_threshold": self.cluster_trade_num_threshold,
                "min_price_movement": self.min_price_movement,

                "ba_max": self.ba_max,

                "closing_slot_name": "CLOSING_" + "Init_Order_" + instrument_key.key + "_" + self.time_of_init,
                "closing_product_id": instrument_key.product_id,
                "closing_instrument_id": instrument_key.instrument_id,

                "strategy_stats_dict": self.stats.to_dict(),

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
                "trail_tp_bool": self.trail_tp_bool,
                "trailing_tp_tau": self.trailing_tp_tau,

                "max_quantity": self.max_quantity
                #"idle_threshold": self.idle_thres
            }
        }

    def quote(self):
        self._simple_init_order()

    def _simple_init_order(self):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            init_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    isinstance(so, so_ll_initial.InitialOrder)]
            if len(init_orders) == 1:
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Initial SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(init_orders) > 1:
                # Should not happen
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Initial SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in init_orders[1:]:
                    self.debug_log("Removing Initial SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "InitialOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating Initial SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print("Creating Initial SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id))
                payload = self.create_ll_initial_synthetic_order_payload_register(instrument_key)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_closing_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, so_ll_closing.ClosingOrder):
                    if any([(init_so.slot_name.startswith("Init_Order_")
                             and init_so.market_area == so.init_instrument_id)
                            for init_so in self.product_synthetic_order_mapping[so.init_product_id].values()]):
                        # if we already have a CLOSING for this, then do nothing
                        self.debug_log("Found INIT for CLOSING SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing CLOSING SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "ClosingOrder"}
                        self.on_synthetic_order_delete(prod, payload)


                elif isinstance(so, so_ll_initial.InitialOrder):
                    if any([(closing_so.slot_name == "CLOSING_" + so.slot_name
                             and closing_so.market_area == so.closing_instrument_id)
                            for closing_so in self.product_synthetic_order_mapping[so.closing_product_id].values()]):
                        # if we already have a CLOSING for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating CLOSING SO {} [{}]".format(so.identifier, prod))
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
                                for so in self.product_synthetic_order_mapping[inst_key.product_id].values()
                                if isinstance(so, so_ll_closing.ClosingOrder)}

            if any([status!=COMMON.SyntheticOrderStates.passive for status in closing_orders_dict.values()]):
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
        self.debug_log(
            "Trade on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price, slot_name)
        )
        print("Trade on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price, slot_name))

        # Distribute trade into buckets
        try:
            self.stats.increment_slot_dict_trade(trade)
            self.stats.manage_trade_position(instrument_key, trade.price, trade.quantity, direction, timestamp)
            #api_export_trade(self, trade)
            # if -self.stats.pnl >= self.hard_stop_loss:
            #     self.stats.hard_sl = True
            #     self.debug_log(
            #         "[{}] Strategy hard stop loss breached {}, PNL: {}".format(
            #             self.strategy_id, self.hard_stop_loss, self.stats.pnl)
            #     )
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

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "InitialOrder": so_ll_initial.InitialOrder,
            "ClosingOrder": so_ll_closing.ClosingOrder
        }
