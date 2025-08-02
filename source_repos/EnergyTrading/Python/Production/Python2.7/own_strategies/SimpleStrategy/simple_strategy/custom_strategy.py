import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
from constants import TTF_ICE, TTF_PRODUCT_ID, BROKER_ID
from own_tools.instrument_key import InstrumentKey
import autotrader_core.common as COMMON
from strategy_stats import StrategyStats
from sm_bid_so import SimpleOrderBid
from sm_ask_so import SimpleOrderAsk
from sm_lift_so import SimpleOrderLift

log = logging.getLogger("autotrader.tutorial_ff_arbitrage_09_multi_products")


class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    broker_id = ""
    fix_margin = None
    preferred_quantity = None
    max_quantity = None
    delivery_areas_additional = []

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log
        # Strategy stats
        self.stats = StrategyStats(None, self.strategy_id)

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # Create InstrumentKey Lists
        product_id_list = strategy_json["product_ids"]
        self.delivery_areas_additional = [InstrumentKey(inst_id, prod_id).key
                                          for (inst_id, prod_id) in zip(self.delivery_areas, product_id_list)]
        self.stats.update_instruments(self.delivery_areas_additional)
        # parameters of strategy
        self.broker_id = strategy_json["broker_id"]
        self.fix_margin = strategy_json["fix_margin"]
        self.preferred_quantity = strategy_json["preferred_quantity"]
        self.max_quantity = strategy_json["max_quantity"]

    def on_synthetic_order(self, payload):
        print("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_lift_orders()
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        # super(SimpleStrategy, self).custom_on_order_book_update(orders, timestamp)
        # Update prices
        tuple_kd_list = []
        for o in orders:
            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            direction = o.direction
            tuple_kd_list.append((instrument_key, direction))
        tuple_list = set(tuple_kd_list)
        for instrument_key, direction in tuple_list:
            self.stats.update_strategy_prices(instrument_key, direction, self.exchange.products, self.broker_id)
        # just call act, to trigger all product synthetic orders
        products = self.exchange.products.get_active_products()
        self.quote()
        res = self.act(timestamp, products)
        self._update_lift_orders()
        return res

    def custom_on_trade_update(self, trades, timestamp):
        #
        # self._delete_standing_orders()
        for trade in trades:
            self._process_single_trade(trade)
        res = super(CustomStrategy, self).custom_on_trade_update(trades, timestamp)
        self._update_lift_orders()
        return res

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "SimpleBidOrder": SimpleOrderBid,
            "SimpleAskOrder": SimpleOrderAsk,
            "SimpleLiftOrder": SimpleOrderLift
        }

    def _delete_standing_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, (SimpleOrderBid, SimpleOrderAsk)):
                    self.debug_log("Removing MarketMaking SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "MarketMakingOrder"}
                    self.on_synthetic_order_delete(prod, payload)
                # elif isinstance(so, SimpleOrderLift):
                #     self.debug_log("Removing Lift SO {} [{}]".format(so.identifier, prod))
                #     payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                #     self.on_synthetic_order_delete(prod, payload)

    def _process_single_trade(self, trade):
        if trade.direction == 'sell':
            direction = COMMON.Direction.sell
            instrument_id = trade.sell_delivery_area
        else:
            direction = COMMON.Direction.buy
            instrument_id = trade.buy_delivery_area
        product_id = trade.product.product_id
        instrument_key = InstrumentKey(instrument_id, product_id)
        self.debug_log(
            "Trade on {}[{}]: [{}]: {}@{}".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price)
        )
        # Distribute trade into buckets
        self.stats.update_strategy_position(instrument_key.key, trade.quantity, direction)

    def quote(self):
        margin = self.fix_margin
        self._simple_order_buy(margin)
        self._simple_order_sell(margin)

    def _simple_order_buy(self, margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            quantity = min(self.preferred_quantity, max(self.max_quantity - self.stats.net_position[key], 0))
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    isinstance(so, SimpleOrderBid)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying MarketMakingBid SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin, "slot_size": quantity}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying SimpleBid SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin, "slot_size": quantity}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing SimpleBid SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "SimpleBidOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating SimpleBid SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = self.create_bid_synthetic_order_payload_register(instrument_key, margin, quantity)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _simple_order_sell(self, margin):
        for key in self.delivery_areas_additional:
            instrument_key = InstrumentKey().from_instrument_key(key)
            quantity = min(self.preferred_quantity, max(self.max_quantity + self.stats.net_position[key], 0))
            market_making_orders = [so for so in
                                    self.product_synthetic_order_mapping[instrument_key.product_id].values() if
                                    isinstance(so, SimpleOrderAsk)]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying SimpleAsk SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin, "slot_size": quantity}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                self.debug_log("Modifying SimpleAsk SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier, "margin": margin, "slot_size": quantity}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing SimpleAsk SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "SimpleAsk"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating SimpleAsk SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = self.create_ask_synthetic_order_payload_register(instrument_key, margin, quantity)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_lift_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, SimpleOrderLift):
                    if any([(simple_so.slot_name.startswith("Simple_Order_")
                             and simple_so.market_area == so.market_area)
                            for simple_so in self.product_synthetic_order_mapping[so.lead_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        self.debug_log("Found Simple Order for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, (SimpleOrderBid, SimpleOrderAsk)):
                    if any([(lift_so.slot_name == "LIFT_" + so.market_area
                             and lift_so.market_area == so.market_area)
                            for lift_so in self.product_synthetic_order_mapping[so.product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.product_id, payload)

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "SimpleLiftOrder",
            "identifier": "LIFT_" + so.market_area,
            "configuration": {
                "slot_name": "LIFT_" + so.market_area,
                "market_area": so.market_area,
                "broker_id": so.broker_id,
                "product_id": so.product_id,
                "lead_slot_name": so.slot_name,
                "lead_instrument_id": so.market_area,
                "lead_product_id": so.product_id,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }

    def create_bid_synthetic_order_payload_register(self, instrument_key, margin, quantity):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "SimpleBidOrder",
            "identifier": "Simple_Order_BID_" + instrument_key.key,
            "configuration": {
                "slot_name": "Simple_Order_BID_" + instrument_key.key,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_id,
                "product_id": instrument_key.product_id,
                "margin": margin,
                "slot_size": quantity,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }

    def create_ask_synthetic_order_payload_register(self, instrument_key, margin, quantity):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "SimpleAskOrder",
            "identifier": "Simple_Order_ASK_" + instrument_key.key,
            "configuration": {
                "slot_name": "Simple_Order_ASK_" + instrument_key.key,
                "market_area": instrument_key.instrument_id,
                "broker_id": self.broker_id,
                "product_id": instrument_key.product_id,
                "margin": margin,
                "slot_size": quantity,
                "strategy_stats_dict": self.stats,
                "strategy_id": self.strategy_id
            }
        }
