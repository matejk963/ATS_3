import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_core.common as COMMON
from own_tools.instrument_key import InstrumentKey
# from own_tools.misc import api_export_trade
from strategy_stats import StrategyStats
import time

import so_arbitrage_lead
import so_arbitrage_lift

# from constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID


log = logging.getLogger("autotrader.arbitrage_strategy")

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
        # Create InstrumentKey Lists
        instrument_id_list=self.delivery_areas
        product_id_list = strategy_json["product_ids"]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                          for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        # parameters of strategy
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list
        self.broker_ids = strategy_json["broker_ids"]
        self.fix_margin = strategy_json["fix_margin"]
        self.preferred_quantity = strategy_json["preferred_quantity"]
        self.max_quantity = strategy_json["max_quantity"]
        self.stop_loss = strategy_json["stop_loss"]
        self.idle_thres = strategy_json["idle_thres"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]
        self.market_volume_check_flag=strategy_json["market_volume_check_flag"]
        self.ql_max=strategy_json["ql_max"]

        assert self.market_volume_check_flag in [0.0, 1.0], 'Parameter market_volume_check_flag must be 1 or 0!'

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
        self._update_lift_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        for o in orders:
            #print("DEBUG ORDER UPDATE: ",o.original_user, o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction, o.broker_id)
            self.debug_log("DEBUG ORDER UPDATE: " + o.product.product_id + " " + o.delivery_area_id + " " + str(
                o.price) + " " + str(o.quantity) + " " + o.direction + " " + str(o.broker_id))

            if o.tags.get('portfolio_key') == self.strategy_id:
                self._process_single_order(o, timestamp)

        self.stats.ql = self.autotrader.queue_lag[self.exchange.caption]
        self.quote()

        # just call act, to trigger all product synthetic orders
        try:
            res = self._call_act_orders(timestamp)
        except Exception as err:
            #self.delete_standing_orders()
            log.error("Exception in custom_on_order_book_update: %s", err)
            res = {}
        self._update_lift_orders()
        return res

    def custom_on_trade_update(self, trades, timestamp):
        for trade in trades:
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
        self._update_lift_orders()
        return res

    ##################################################################################################

    def create_bid_synthetic_order_payload_register(self, instrument_key, margin):

        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "ArbitrageOrder",
            "identifier": "Arb_Order_BID_"+instrument_key.key+"_"+self.time_of_init,
            "configuration": {
                "slot_name": "Arb_Order_BID_"+instrument_key.key+"_"+self.time_of_init,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_ids[0],
                # "product_id": PRODUCT_ID,
                "margin": margin,
                "strategy_id": self.strategy_id,

                "own_product_id": instrument_key.product_id,
                "lift_slot_name": "LIFT_" + "Arb_Order_BID_"+instrument_key.key+"_"+self.time_of_init,
                "lift_product_id": instrument_key.product_id,
                "lift_instrument_id": instrument_key.instrument_id,
                "lift_broker_ids": self.broker_ids[1:],

                "strategy_stats_dict": self.stats.to_dict(),

                "max_quantity": self.max_quantity,
                "market_volume_check_flag": self.market_volume_check_flag,
                "ql_max": self.ql_max

            }
        }

    def create_ask_synthetic_order_payload_register(self, instrument_key, margin):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "ArbitrageOrder",
            "identifier": "Arb_Order_ASK_"+instrument_key.key+"_"+self.time_of_init,
            "configuration": {
                "slot_name": "Arb_Order_ASK_"+instrument_key.key+"_"+self.time_of_init,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_ids[0],
                # "product_id": PRODUCT_ID,
                "margin": margin,
                "strategy_id": self.strategy_id,

                "own_product_id": instrument_key.product_id,
                "lift_slot_name": "LIFT_"+"Arb_Order_ASK_"+instrument_key.key+"_"+self.time_of_init,
                "lift_product_id": instrument_key.product_id,
                "lift_instrument_id": instrument_key.instrument_id,
                "lift_broker_ids": self.broker_ids[1:],

                "strategy_stats_dict": self.stats.to_dict(),

                "max_quantity": self.max_quantity,
                "market_volume_check_flag": self.market_volume_check_flag,
                "ql_max": self.ql_max

            }
        }

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.lift_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LiftOrder",
            "identifier": "LIFT_" + so.slot_name,
            "configuration": {
                "slot_name": "LIFT_" + so.slot_name,
                "market_area": so.lift_instrument_id,
                # "product_id": so.lift_product_id,
                "broker_id": self.broker_ids[0],
                "lead_instrument_id": so.market_area,
                "lead_slot_name": so.slot_name,
                "lead_product_id": so.own_product_id,
                "lead_broker_id": self.broker_ids[0],
                "lift_broker_ids": self.broker_ids[1:],
                "strategy_id": self.strategy_id,
                "strategy_stats_dict": self.stats.to_dict(),
                "margin" : self.fix_margin,

                "max_quantity": self.max_quantity,
                "idle_threshold": self.idle_thres
            }
        }

    def quote(self):
        margin = self.fix_margin
        self._simple_order_buy(margin)
        self._simple_order_sell(margin)

    def _simple_order_buy(self, margin):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    isinstance(so, so_arbitrage_lead.ArbitrageOrder) and 'BID' in so.identifier]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying ArbitrageBid SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying ArbitrageBid SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing ArbitrageBid SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "ArbitrageOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating ArbitrageBid SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print("Creating ArbitrageBid SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id))
                payload = self.create_bid_synthetic_order_payload_register(instrument_key, margin)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _simple_order_sell(self, margin):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    isinstance(so, so_arbitrage_lead.ArbitrageOrder) and 'ASK' in so.identifier]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying ArbitrageAsk SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying ArbitrageAsk SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing ArbitrageAsk SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "ArbitrageOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create sell order
                self.debug_log("Creating ArbitrageAsk SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print("Creating ArbitrageAsk SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id))
                payload = self.create_ask_synthetic_order_payload_register(instrument_key, margin)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_lift_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, so_arbitrage_lift.LiftOrder) and 'BID' in so.slot_name:
                    if any([(lead_so.slot_name.startswith("Arb_Order_BID")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in self.product_synthetic_order_mapping[so.lead_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_arbitrage_lift.LiftOrder) and 'ASK' in so.slot_name:
                    if any([(lead_so.slot_name.startswith("Arb_Order_ASK")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in self.product_synthetic_order_mapping[so.lead_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    if any([(lift_so.slot_name == "LIFT_" + so.slot_name
                             and lift_so.market_area == so.lift_instrument_id)
                            for lift_so in self.product_synthetic_order_mapping[so.lift_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.lift_product_id, payload)

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
            lift_orders_bid_dict = {inst_key.key: so.status
                                for so in self.product_synthetic_order_mapping[inst_key.product_id].values()
                                if isinstance(so, so_arbitrage_lift.LiftOrder) and 'BID' in so.identifier}
            lift_orders_ask_dict = {inst_key.key: so.status
                                for so in self.product_synthetic_order_mapping[inst_key.product_id].values()
                                if isinstance(so, so_arbitrage_lift.LiftOrder) and 'ASK' in so.identifier}

            if any([status!=COMMON.SyntheticOrderStates.passive for status in lift_orders_bid_dict.values()]):
                self.stats.balancing_dict[inst_key.key]['BID']=True
                self.debug_log("self.stats.balancing_bid for "+ str(inst_key.key)+" set to True")
            else:
                self.stats.balancing_dict[inst_key.key]['BID']=False
                self.debug_log("self.stats.balancing_bid for "+ str(inst_key.key)+" set to False")


            if any([status != COMMON.SyntheticOrderStates.passive for status in lift_orders_ask_dict.values()]):
                self.stats.balancing_dict[inst_key.key]['ASK']=True
                self.debug_log("self.stats.balancing_ask for "+ str(inst_key.key)+" set to True")

            else:
                self.stats.balancing_dict[inst_key.key]['ASK']=False
                self.debug_log("self.stats.balancing_ask for "+ str(inst_key.key)+" set to False")

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
            "ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
            "LiftOrder": so_arbitrage_lift.LiftOrder
        }
