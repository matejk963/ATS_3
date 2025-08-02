import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_lib.common as COMMON
from .own_tools.instrument_key import InstrumentKey
# from own_tools.misc import api_export_trade
from .strategy_stats import StrategyStats

import time

from . import so_sparsity_bm_lead
from . import so_sparsity_bm_lift

# from constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID


log = logging.getLogger("autotrader.sparsity_bmark")

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
        # Create boolean for shutdown
        self.reset_bool = False
        # Create InstrumentKey Lists
        instrument_id_list=self.delivery_areas
        product_id_list = strategy_json["product_ids"]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                          for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        # parameters of strategy
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list
        self.broker_list = strategy_json["broker_list"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]
        self.ql_max=strategy_json["ql_max"]

        # position logic attributes
        self.trd_gap = strategy_json["trd_gap"]
        self.make_profit_margin = strategy_json["make_profit_margin"]
        self.loss_making_thold = strategy_json["loss_making_thold"]
        self.stop_loss_margin = strategy_json["stop_loss_margin"]
        self.makeagg_ratio_thold = strategy_json["makeagg_ratio_thold"]
        self.burnout_period = strategy_json["burnout_period"]
        self.bid_ask = strategy_json["bid_ask"]
        self.max_position = strategy_json["max_position"]
        self.lead_closing = strategy_json["lead_closing"]
        self.thold_dense = strategy_json["thold_dense"]
        self.thold_sparse = strategy_json["thold_sparse"]
        # self.trading_direction = strategy_json["trading_direction"]


        self.stats = StrategyStats(None, self.strategy_id, self.caption)
        self.time_of_init=str(int(round(time.time())))
        self.trade_counter=0

        self.initialized=False

        self.duplicity_trade_list = []

        if not self.initialized:
            self.stats.update_instruments(self.instrument_keys, self.time_of_init, {'make_profit_margin': self.make_profit_margin})
            try:
                self.ref_area = InstrumentKey(self.delivery_areas[0], self.product_ids[0]).key
            except IndexError:
                self.ref_area = None
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

    def handle_steering_call(self, payload):        # TASK: debug and check what payload is sent after you fix the backtesting setup
        payload_dict =  {k: v for d in payload if isinstance(d, dict) for k, v in d.items()}

        self.debug_log(
            "[{}] Steering call for [{}] made.".format(
                self.strategy_id, payload)
        )
        try:
            if "stats" in payload:
                self.api_export_timeseries({
                    "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: {**self.stats.to_dict(), **{'reset_bool': self.reset_bool}}})}
                )
            elif "close_behavior" in payload_dict.keys():
                self.stats.aux_dict['steering_closing'] = payload_dict['close_behavior']
            elif "open_price" in payload_dict.keys():
                self.stats.aux_dict['open_price'] = payload_dict['open_price']
            elif "make_profit_margin" in payload_dict.keys():
                self.stats.aux_dict['make_profit_margin'] = payload_dict['make_profit_margin']
            elif "set_position_dict" in payload_dict.keys():
                self.stats.set_spread_dict_quantity(payload_dict["set_position_dict"])
            else:
                self.debug_log("[{}] Unknown steering call code: {}".format(self.strategy_id, payload))
        except Exception as e:
            self.debug_log(f'ERROR steering, exception: {e}, line number: {e.__traceback__.tb_lineno}')

    def on_synthetic_order(self, payload):
        self.debug_log("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        self._update_lift_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        print('Orderbook update entry')
        strategy_stats = self.stats.to_dict()
        if not strategy_stats['position_dict']['open_price']:
            return {}
        for o in orders:
            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            if instrument_key.key == self.ref_area:
                self.debug_log("[" + self.strategy_id + "] DEBUG ORDER UPDATE: " + o.product.product_id + " " + o.delivery_area_id + " " + str(
                    o.price) + " " + str(o.quantity) + " " + o.direction + " " + str(o.broker_id))
                self.stats.update_locked_until(o.product.locked_until)

                self.stats.aux_dict['ql'] = self.autotrader.queue_lag[self.exchange.caption]
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
        return {}

    def custom_on_public_trade_update(self, trades, timestamp):
        for trade in trades:
                if trade.match_delivery_areas(self.delivery_areas) and trade.product.product_id in self.ref_area:
                    self.info_log("[{}] On Public Trade Update class {}, {}[{}]: {}@{}  execution_time: {}".format(self.strategy_id, (trade), trade.buy_delivery_area, trade.product.product_id,
                                                                        trade.quantity, trade.price, trade.execution_time))
                    if trade.portfolio_key is not None and 'arb' in trade.portfolio_key:
                        self.info_log(f"PASS - Arbitrage trade {trade.trade_id}")
                        return {}

                    if trade.trade_id in self.duplicity_trade_list:
                        self.info_log(f"PASS - Duplicate trade {trade.trade_id}, duplicity list len {len(self.duplicity_trade_list)}\n duplicity list:\n{self.duplicity_trade_list}")
                        return {}
                    else:
                        self.duplicity_trade_list.append(trade.trade_id)
                    if not (trade.initiator_broker_id == self.broker_list[0] or trade.aggressor_broker_id == self.broker_list[0]):
                        self.info_log(f"PASS - not an EEX trade")
                        return {}
                    # Not our trade, call act
                    self.stats.update_trade_info(trade, trade.execution_time)
                    try:
                        self.quote()
                        res = self._call_act_orders(timestamp)
                    except Exception as err:
                        # self.delete_standing_orders()
                        log.error("Exception in custom_on_trade_update: %s", err)
                        res = {}
                    self._update_lift_orders()
        return {}


    def custom_on_trade_update(self, trades, timestamp):
        res = {}
        for trade in trades:
            self.info_log("On Trade Update {}[{}]: {}@{}  execution_time: {}".format(trade.buy_delivery_area, trade.product.product_id,
                                                                    trade.quantity, trade.price, trade.execution_time))
            if trade.tags.get("portfolio_key") == self.strategy_id:
                if trade.trade_id not in self.trade_id_list:
                    self._process_single_trade(trade, timestamp)
                    self.trade_id_list.append(trade.trade_id)
        return res



    ##################################################################################################

    def create_lead_synthetic_order_payload_register(self, instrument_key):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LeadOrder",
            "identifier": "SpBMark_Order_"+instrument_key.key+"_"+self.time_of_init,
            "configuration": {
                "slot_name": "SpBMark_Order_"+instrument_key.key+"_"+self.time_of_init,
                "market_area": instrument_key.instrument_id,
                "strategy_id": self.strategy_id,
                "broker_id": self.broker_list[0],
                "broker_list": self.broker_list,
                "own_product_id": instrument_key.product_id,
                "lift_slot_name": "LIFT_" + "SpBMark_Order_"+instrument_key.key+"_"+self.time_of_init,
                "lift_instrument_id": instrument_key.instrument_id,

                "strategy_stats_dict": self.stats.to_dict(),

                # params
                "max_position": self.max_position,
                "ql_max": self.ql_max,
                "bid_ask": self.bid_ask,
                "reset_bool": self.reset_bool,
                "trd_gap": self.trd_gap,
                "lead_closing": self.lead_closing,
                "thold_dense": self.thold_dense,
                "thold_sparse": self.thold_sparse
            }
        }

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.own_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LiftOrder",
            "identifier": "LIFT_" + so.slot_name,
            "configuration": {
                "slot_name": "LIFT_" + so.slot_name,
                "market_area": so.lift_instrument_id,
                # "product_id": so.lift_product_id,
                "broker_id": self.broker_list[0],
                "broker_list": self.broker_list,
                "lead_instrument_id": so.market_area,
                "lead_slot_name": so.slot_name,
                "lead_product_id": so.own_product_id,
                "strategy_id": self.strategy_id,

                "strategy_stats_dict": self.stats.to_dict(),

                # params
                "reset_bool": self.reset_bool,
                #"trd_gap": self.trd_gap,
                "make_profit_margin": self.make_profit_margin,
                "loss_making_thold": self.loss_making_thold,
                "stop_loss_margin": self.stop_loss_margin,
                "makeagg_ratio_thold": self.makeagg_ratio_thold,
                "burnout_period": self.burnout_period,
                "max_position": self.max_position
            }
        }

    def quote(self):
        # TODO check for mutability of dictionaries
        if self.check_stats_dict_all:
            self._simple_lead_order()
        else:
            self.reset_bool = True
            self._simple_lead_order()
            self._update_lift_orders()
            self.debug_log("[RESET FLAG] - strategy reset, all SO must stop posting orders")

    def _simple_lead_order(self):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            init_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    isinstance(so, so_sparsity_bm_lead.SpBMarkOrder)]
            if len(init_orders) == 1:
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Lead SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier} if not self.reset_bool else {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(init_orders) > 1:
                # Should not happen
                # Modify order
                so = init_orders[0]
                self.debug_log("Modifying Lead SO {} {}[{}]".format(
                    so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                )
                payload = {"identifier": so.identifier} if not self.reset_bool else {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in init_orders[1:]:
                    self.debug_log("Removing Lead SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "InitialOrder"} if not self.reset_bool else {"identifier": so.identifier, "synthetic_order_type": "InitialOrder", "configuration": {"reset_bool": self.reset_bool}}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create buy order
                self.debug_log("Creating Lead SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print(("Creating Lead SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)))
                payload = self.create_lead_synthetic_order_payload_register(instrument_key)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_lift_orders(self):
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, so_sparsity_bm_lift.LiftOrder):
                    if any([(lead_so.slot_name.startswith("Sp")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in list(self.product_synthetic_order_mapping[so.lead_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            # so.reset_bool = self.reset_bool
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log("Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        else:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_sparsity_bm_lift.LiftOrder):
                    if any([(lead_so.slot_name.startswith("Sp")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in list(self.product_synthetic_order_mapping[so.lead_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            # so.reset_bool = self.reset_bool
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log("Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        else:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_sparsity_bm_lead.SpBMarkOrder):
                    if any([(lift_so.slot_name == "LIFT_" + so.slot_name
                             and lift_so.market_area == so.lift_instrument_id)
                            for lift_so in list(self.product_synthetic_order_mapping[so.own_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            # so.reset_bool = self.reset_bool
                            self.on_synthetic_order_modify(so.own_product_id, payload)
                            self.debug_log("Found LIFT for LEAD SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        print("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.own_product_id, payload)

    def _call_act_orders(self, timestamp):
        products = []
        for inst_id in set(self.instrument_ids):
            products.extend(self.exchange.products.get_active_products(inst_id))
        res = self.act(timestamp, products)
        return res

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
            "Trade on {}[{}]: [{}]: {}@{} ".format(instrument_id, product_id, direction,
                                                  trade.quantity, trade.price)
        )

        # Distribute trade into buckets
        try:
            self.stats.manage_trade_position(instrument_key, trade.price, trade.quantity, direction, timestamp)
            self._append_trade_paper_trading_list(timestamp, direction, trade.price, trade.quantity)
            #api_export_trade(self, trade)
            if -self.stats.pnl >= self.hard_stop_loss:
                self.stats.hard_sl = True
                self.debug_log(
                    "[{}] Strategy hard stop loss breached {}, PNL: {}".format(
                        self.strategy_id, self.hard_stop_loss, self.stats.pnl)
                )
        except Exception as err:
            log.error("Exception in managing position: %s", err)

    def _append_trade_paper_trading_list(self, timestamp, direction, price, volume):
        index = -1
        for i, x in enumerate(self.stats.param_dict['position_list']):
            if x['timestamp'] == None:
                index = i
                break
        if index >= 0:
            self.stats.param_dict['position_list'][index] = {'timestamp': timestamp, 'direction': direction, 'price': price, 'volume': volume}
        else:
            for i in range(len(self.stats.param_dict['position_list'])-1):
                self.stats.param_dict['position_list'][i] = self.stats.param_dict['position_list'][i+1]
            self.stats.param_dict['position_list'][-1] = {'timestamp': timestamp, 'direction': direction, 'price': price, 'volume': volume}

    @property
    def check_stats_dict_all(self):
        stat_id = id(self.stats.position_dict)
        so_stat_id_list = [id(x.strategy_stats_dict['position_dict']) for tr in self.product_synthetic_order_mapping.values() for x in tr.values()]
        return all([x == stat_id for x in so_stat_id_list])

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "LeadOrder": so_sparsity_bm_lead.SpBMarkOrder,
            "LiftOrder": so_sparsity_bm_lift.LiftOrder
        }
