import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
from .own_tools.instrument_key import InstrumentKey
# from own_tools.misc import api_export_trade
from .strategy_stats import StrategyStats
import numpy as np
import time

from . import so_arbitrage_lead
from . import so_arbitrage_lift
from . import so_cross_lead
from . import so_cross_lift

# from constants import BROKER_ID_1, BROKER_ID_2, INST_ID_1, INST_ID_2, PRODUCT_ID


log = logging.getLogger("autotrader.arbitrage_strategy")
tol = 1e-3

class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    shuffle_broker_list = []
    opp_slot_dict = {}
    prod_slot_dict = {'buy': {}, 'sell': {}, 'cross': {}}
    default_payload = {}
    log_stats_dict = {}
    reset_bool = None
    advanced_making = None
    broker_making = None
    cross_arb = None
    cross_arb_margin_min = None
    cross_arb_margin_max = None
    min_time_cross = None
    min_margin = None
    max_margin = None
    opt_margin = None
    flex_margining = None
    initialized = False
    init_orders = False
    fexe_bool = False
    public_update = False
    cons_making = False
    cons_margin = None
    verbose = False

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)

        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log
        self.trade_id_list = []
        self.timestamp = (int(time.time()) // 86400) * 86400
        self.trade_counter = 0

    @property
    def fix_margin(self):
        return self.opt_margin

    def params_cons_making_validation(self, strategy_json):
        # name_list = ["cons_making", "cons_making_aux", "cons_margin", "cons_min_level"]
        cons_making_dict = {k: strategy_json["cons_making"] for k in self.broker_ids_main}
        cons_making_dict.update({k: strategy_json["cons_making_aux"] for k in self.broker_ids if k not in self.broker_ids_main})
        self.cons_making_dict = cons_making_dict
        self.cons_margin = strategy_json["cons_margin"]
        self.cons_min_level = strategy_json["cons_min_level"]

    def params_cross_arb_validation(self, strategy_json):
        name_list = ["cross_arb_margin_min", "cross_arb_margin_max"]
        cross_arb_mrg_min, cross_arb_mrg_max = [strategy_json[name] for name in name_list]
        cross_arb_bool = strategy_json["cross_arb"]
        min_time_cross = strategy_json["min_time_cross"]
        if (cross_arb_mrg_min > 0) and (cross_arb_mrg_min <= cross_arb_mrg_max):
            self.cross_arb = cross_arb_bool
            self.cross_arb_margin_min = cross_arb_mrg_min
            self.cross_arb_margin_max = cross_arb_mrg_max
            self.min_time_cross = min_time_cross
        else:
            self.cross_arb = False

    def params_flex_margin_validation(self, strategy_json):
        name_list = ["min_margin", "max_margin", "opt_margin", "min_margin_aux"]
        min_margin, max_margin, opt_margin, min_margin_aux = [abs(strategy_json[name]) for name in name_list]
        # Check margin for closing limit
        margin_for_closing = strategy_json["margin_for_closing"]
        opt_margin = min(opt_margin, 0.9 * margin_for_closing)
        min_margin = min(min_margin, 0.9 * margin_for_closing)
        max_margin = min(max_margin, 0.9 * margin_for_closing)
        min_margin_aux = min(min_margin_aux, 0.9 * margin_for_closing)
        # Margin must be min <= opt <= max
        if max_margin < opt_margin:
            max_margin = opt_margin
        if opt_margin < min_margin:
            min_margin = opt_margin
        if min_margin_aux < min_margin:
            min_margin_aux = min_margin
        self.opt_margin = opt_margin
        self.min_margin = min_margin
        self.max_margin = max_margin

        self.min_margin_dict = {k: min_margin for k in self.broker_ids_main}
        self.min_margin_dict.update({k: min_margin_aux for k in self.broker_ids if k not in self.broker_ids_main})

        if self.max_margin - self.min_margin < tol:
            self.flex_margining = False
        else:
            self.flex_margining = True

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # Create boolean for shutdown
        self.reset_bool = False
        # Create InstrumentKey Lists
        instrument_id_list = self.delivery_areas
        product_id_list = strategy_json["product_ids"]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        # parameters of strategy
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list
        self.broker_ids_main = strategy_json["broker_ids_main"]
        self.broker_ids = strategy_json["broker_ids"]
        self.margin_for_closing = strategy_json["margin_for_closing"]
        self.closing_in_profit_flag = strategy_json["closing_in_profit_flag"]
        self.preferred_quantity = strategy_json["preferred_quantity"]
        self.max_quantity = strategy_json["max_quantity"]
        self.stop_loss = strategy_json["stop_loss"]
        self.idle_thres = strategy_json["idle_thres"]
        self.hard_stop_loss = strategy_json["hard_stop_loss"]
        self.market_volume_check_flag = strategy_json["market_volume_check_flag"]
        self.ql_max = strategy_json["ql_max"]
        self.public_update = strategy_json["public_update"]
        self.advanced_making = strategy_json["advanced_making"]
        self.broker_making = strategy_json["broker_making"]
        self.maximum_neg_buyback = strategy_json.get(COMMON.StrategyJsonKey.maximum_neg_buyback, None) or 4
        self.verbose = strategy_json["verbose"]
        self.params_cons_making_validation(strategy_json)
        self.params_cross_arb_validation(strategy_json)
        self.params_flex_margin_validation(strategy_json)

        assert self.market_volume_check_flag in [0.0, 1.0], 'Parameter market_volume_check_flag must be 1 or 0!'
        assert self.closing_in_profit_flag in [0.0, 1.0], 'Parameter closing_in_profit_flag must be 1 or 0!'

        self.stats = StrategyStats(None, self.strategy_id, self.caption, self.verbose)
        self.time_of_init = str(int(round(time.time())))
        self.trade_counter = 0

        self.initialized = False
        self.init_orders = False

        if not self.initialized:
            self.opp_slot_dict = {}
            self.prod_slot_dict = {'buy': {}, 'sell': {}, 'cross': {}}
            self.delete_standing_orders()
            self.stats.update_instruments(self.instrument_keys, self.time_of_init)
            self.log_stats_dict = {k: [] for k in self.instrument_keys}
            self.initialized = True
            self.init_orders = True
            self.fexe_bool = False
        # Make permutation of lift brokers
        if strategy_json.get(COMMON.StrategyJsonKey.active):
            if self.broker_making:
                self.shuffle_broker_list = [x for x in np.random.permutation(self.broker_ids[1:])]
            self.init_orders = True
            self.fexe_bool = False
            self.log_stats_dict = {k: [] for k in self.instrument_keys}

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
                "stats": ("Statistics of strategy", "MW", "MW", COMMON.HOUR,
                          {self.timestamp: {**self.stats.to_dict(), **{'reset_bool': self.reset_bool}}})}
            )
        elif "time_slippage" in payload:
            output_dict = self.log_stats_dict
            # Extra debug log
            self.api_export_timeseries({"time_slippage": (
                "Statistics of strategy", "MW", "MW", COMMON.HOUR, {self.timestamp: output_dict})})
        else:
            self.debug_log("[{}] Unknown steering call code: {}".format(self.strategy_id, payload))

    def on_synthetic_order(self, payload):
        print(("DEBUG on_synthetic_order: ", payload))
        self.debug_log("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_lift_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        ord_id_list = []
        # run_bool = False
        # trade_bool = True
        fexe_dict = {instkey: {s: False for s in ['buy', 'sell']} for instkey in self.instrument_keys}
        if self.init_orders:
            self.debug_log("DEBUG ORDER INIT")
            run_bool = True
            trade_bool = False
            self.init_orders = False
        else:
            run_bool = False
            trade_bool = True
        cross_bool = True
        for o in orders:
            instrument_key = InstrumentKey(o.delivery_area_id, o.product.product_id)
            if instrument_key.key in self.instrument_keys:
                #print("DEBUG ORDER UPDATE: ",o.original_user, o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction, o.broker_id)
                self.debug_log("DEBUG ORDER UPDATE: " + o.product.product_id + " " + o.delivery_area_id + " " + str(
                    o.price) + " " + str(o.quantity) + " " + o.direction + " " + str(o.broker_id) + " " + str(o._fexe))

                if o.tags.get('portfolio_key') == self.strategy_id:
                    self._process_single_order(o, timestamp)

                self.stats.aux_dict['locked_until'] = (o.product.locked_until)
                self.stats.aux_dict['ql'] = self.autotrader.queue_lag[self.exchange.caption]
                # FEXE
                if isinstance(o, APITR.OwnOrder) and o._fexe:
                    cross_bool = False
                    self.fexe_bool = True
                    fexe_dict[instrument_key.key][o.direction] = True
                    self.debug_log("DEBUG ORDER BOOK UPDATE: skipping call act due to FULL EXECUTION of order")
                    continue
                if fexe_dict[instrument_key.key][o.direction]:
                    # If we already have fexe for side and instkey do not run synth order
                    continue
                # List orders that need to be called
                try:
                    # ARB SIDE
                    synth_name_lead = self.prod_slot_dict[o.direction][instrument_key.product_id]
                    synth_name_lift = self.opp_slot_dict[synth_name_lead][1]
                    # CROSS SIDE
                    if self.cross_arb:
                        synth_cross_lead = self.prod_slot_dict['cross'][instrument_key.product_id]
                        synth_cross_lift = self.opp_slot_dict[synth_cross_lead][1]
                        net_cross_vol = self.stats.slot_dict_net_position(synth_cross_lead, synth_cross_lift)
                    else:
                        synth_cross_lead = None
                        synth_cross_lift = None
                        net_cross_vol = 0
                    # ARB OPP SIDE
                    synth_name_lead_opp = self.prod_slot_dict[COMMON.Direction().invert(o.direction)][instrument_key.product_id]
                    synth_name_lift_opp = self.opp_slot_dict[synth_name_lead_opp][1]
                    # Determine open positions
                    net_arb_vol = self.stats.slot_dict_net_position(synth_name_lead, synth_name_lift)
                    net_arb_opp_vol = self.stats.slot_dict_net_position(synth_name_lead_opp, synth_name_lift_opp)
                    # Make synthetic order list to activate
                    if abs(net_arb_vol) > tol:
                        # Position is OPEN, activate only lift
                        synth_name = [synth_name_lift]
                    else:
                        # synth_name = [synth_name_lead, synth_name_lead_opp]
                        synth_name = [synth_name_lead]
                        if abs(net_arb_opp_vol) > tol:
                            # Add OPPOSITE LIFT
                            synth_name.append(synth_name_lift_opp)
                        else:
                            # Activate also CROSS ARB synthetic orders
                            if self.cross_arb:
                                if abs(net_cross_vol) < tol:
                                    if cross_bool:
                                        synth_name.append(synth_cross_lead)
                                else:
                                    synth_name.append(synth_cross_lift)
                    # synth_name = [self.prod_slot_dict[o.direction][instrument_key.product_id]]
                    # synth_name.append(self.prod_slot_dict['cross'][instrument_key.product_id])
                    ord_id_list.extend([(instrument_key.product_id, sn) for sn in synth_name])
                except KeyError as e:
                    # Run All synthetic orders
                    trade_bool = False
                    self.debug_log("DEBUG ORDER BOOK UPDATE KEY ERROR: %s" % e)
                run_bool = True
        if run_bool:
            self.quote()
            # just call act, to trigger all product synthetic orders
            try:
                res = self._call_act_orders(timestamp, ord_id_list, trade_bool, True)
            except Exception as err:
                #self.delete_standing_orders()
                log.error("Exception in custom_on_order_book_update: %s", err)
                res = {}
            self._update_lift_orders()
        else:
            res = {}
        return res

    def custom_on_trade_update(self, trades, timestamp):
        trd_id_list = []
        ord_id_list = []
        run_bool = True
        for trade in trades:
            if trade.tags.get("portfolio_key") == self.strategy_id:
                if trade.trade_id not in self.trade_id_list:
                    if trade.tags.get("stats") in ['leadSell', 'leadBuy', 'crossSell', 'crossBuy']:
                        try:
                            trd_id_list.append(self.opp_slot_dict[trade.tags.get("strategy_slot")])
                        except KeyError:
                            pass
                    elif trade.tags.get("stats") in ['lift']:
                        try:
                            synth_tuple = (trade.product.product_id,
                                           self.prod_slot_dict[COMMON.Direction().invert(trade.direction)][
                                               trade.product.product_id])
                            ord_id_list.append(synth_tuple)
                        except KeyError:
                            pass
                    self._process_single_trade(trade, timestamp)
                    self.trade_id_list.append(trade.trade_id)
                    self.trade_counter += 1
        # If trades are not within strategy then check if we are in position somewhere else do nothing
        if not trd_id_list:
            # If we are not in position then skip
            position_dict = {v: self.stats.slot_dict_net_position(k, v[1]) for k, v in self.opp_slot_dict.items()}
            trd_id_list = [k for k, v in position_dict.items() if abs(v) > tol]
            if not trd_id_list:
                if not ord_id_list:
                    run_bool = False
                else:
                    trd_id_list = ord_id_list
        # just call act, to trigger all product synthetic orders
        if run_bool:
            try:
                res = self._call_act_orders(timestamp, trd_id_list, True, False)
                self.fexe_bool = False
            except Exception as err:
                # self.delete_standing_orders()
                log.error("Exception in custom_on_trade_update: %s", err)
                res = {}
        else:
            self.debug_log("custom_on_trade_update: Skipping...")
            self.__update_status_balancing()
            res = {}
        # self._update_lift_orders()
        return res

    def custom_on_public_trade_update(self, trades, timestamp):
        update_bool = False
        synth_ord_list = []
        instrument_tuple_list = []
        # for trade in trades:
        #     if not isinstance(trade, APITR.PublicTrade):
        #         continue
        #     if trade.buy_delivery_area == '':
        #         instrument_id = trade.sell_delivery_area
        #     else:
        #         instrument_id = trade.buy_delivery_area
        #     product_id = trade.product.product_id
        #     instrument_key = InstrumentKey(instrument_id, product_id)
        #     if instrument_key.key in self.instrument_keys:
        #         instrument_tuple_list.extend(
        #             [(COMMON.Direction.buy, instrument_key), (COMMON.Direction.sell, instrument_key)])
        instrument_tuple_list = [
            (direction, instrument_key)
            for trade in trades
            if isinstance(trade, APITR.PublicTrade)
               and (instrument_key := InstrumentKey(
                trade.buy_delivery_area if trade.buy_delivery_area != '' else trade.sell_delivery_area,
                trade.product.product_id
            )).key in self.instrument_keys
            for direction in (COMMON.Direction.buy, COMMON.Direction.sell)
        ]
        if not instrument_tuple_list:
            return {}
        elif self.fexe_bool:
            self.debug_log("DEBUG on_public_trade_update: skipping call act due to FEXE")
            self.fexe_bool = False
        elif self.public_update:
            update_bool = False
            synth_ord_list.extend([(inst_tup[1].product_id, self.prod_slot_dict[inst_tup[0]][inst_tup[1].product_id])
                                   for inst_tup in instrument_tuple_list])
        else:
            update_bool = False
        # Check if we are balanced
        # If we are not in position then skip
        position_dict = {v: self.stats.slot_dict_net_position(k, v[1]) for k, v in self.opp_slot_dict.items()}
        trd_id_list = [k for k, v in position_dict.items() if abs(v) > tol]
        if not trd_id_list:
            pass
        else:
            synth_ord_list = trd_id_list
        if not synth_ord_list:
            res = {}
            if update_bool:
                self.__update_status_balancing()
        else:
            try:
                res = self._call_act_orders(timestamp, synth_ord_list, True, False)
            except Exception as err:
                # self.delete_standing_orders()
                log.error("Exception in custom_on_public_trade_update: %s", err)
                res = {}
        return res

    def create_bid_synthetic_order_payload_register(self, instrument_key, margin):
        slot_name = "Arb_Order_BID_"+instrument_key.key+"_"+self.time_of_init
        ctrs_name = "LIFT_" + slot_name
        self.opp_slot_dict[slot_name] = (instrument_key.product_id, ctrs_name)
        self.prod_slot_dict['buy'][instrument_key.product_id] = slot_name
        if not self.shuffle_broker_list:
            shuffle_broker_list = self.broker_ids[1:]
        else:
            shuffle_broker_list = self.shuffle_broker_list
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
                "margin": margin,
                "min_margin_dict": self.min_margin_dict,
                "max_margin": self.max_margin,
                "strategy_id": self.strategy_id,

                "own_product_id": instrument_key.product_id,
                "lead_broker_id": self.broker_ids[0],
                "lift_slot_name": "LIFT_" + "Arb_Order_BID_"+instrument_key.key+"_"+self.time_of_init,
                "lift_product_id": instrument_key.product_id,
                "lift_instrument_id": instrument_key.instrument_id,
                "lift_broker_ids": shuffle_broker_list,

                "strategy_stats_dict": self.stats.to_dict(),

                "max_quantity": self.max_quantity,
                "market_volume_check_flag": self.market_volume_check_flag,
                "ql_max": self.ql_max,
                "cross_arb_margin_min": self.cross_arb_margin_min,
                "cross_arb_margin_max": self.cross_arb_margin_max,
                "cross_arb_bool": self.cross_arb,
                "reset_bool": self.reset_bool,
                "advanced_making": self.advanced_making,
                "flex_margin": self.flex_margining,
                "broker_making": self.broker_making,
                "cons_margin": self.cons_margin,
                "cons_making_dict": self.cons_making_dict,
                "verbose": self.verbose
            }
        }

    def create_ask_synthetic_order_payload_register(self, instrument_key, margin):
        slot_name = "Arb_Order_ASK_"+instrument_key.key+"_"+self.time_of_init
        ctrs_name = "LIFT_" + slot_name
        self.opp_slot_dict[slot_name] = (instrument_key.product_id, ctrs_name)
        self.prod_slot_dict['sell'][instrument_key.product_id] = slot_name
        if not self.shuffle_broker_list:
            shuffle_broker_list = self.broker_ids[1:]
        else:
            shuffle_broker_list = self.shuffle_broker_list
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
                "margin": margin,
                "min_margin_dict": self.min_margin_dict,
                "max_margin": self.max_margin,
                "strategy_id": self.strategy_id,

                "own_product_id": instrument_key.product_id,
                "lead_broker_id": self.broker_ids[0],
                "lift_slot_name": "LIFT_"+"Arb_Order_ASK_"+instrument_key.key+"_"+self.time_of_init,
                "lift_product_id": instrument_key.product_id,
                "lift_instrument_id": instrument_key.instrument_id,
                "lift_broker_ids": shuffle_broker_list,

                "strategy_stats_dict": self.stats.to_dict(),

                "max_quantity": self.max_quantity,
                "market_volume_check_flag": self.market_volume_check_flag,
                "ql_max": self.ql_max,
                "cross_arb_margin_min": self.cross_arb_margin_min,
                "cross_arb_margin_max": self.cross_arb_margin_max,
                "cross_arb_bool": self.cross_arb,
                "reset_bool": self.reset_bool,
                "advanced_making": self.advanced_making,
                "flex_margin": self.flex_margining,
                "broker_making": self.broker_making,
                "cons_margin": self.cons_margin,
                "cons_making_dict": self.cons_making_dict,
                "verbose": self.verbose
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
                "product_id": so.lift_product_id,
                "broker_id": self.broker_ids[0],
                "lead_instrument_id": so.market_area,
                "lead_slot_name": so.slot_name,
                "lead_product_id": so.own_product_id,
                "lead_broker_id": self.broker_ids[0],
                "lift_broker_ids": self.broker_ids[1:],
                "strategy_id": self.strategy_id,
                "strategy_stats_dict": self.stats.to_dict(),
                "margin": self.fix_margin,
                "margin_for_closing": self.margin_for_closing,
                "closing_in_profit_flag": self.closing_in_profit_flag,

                "max_quantity": self.max_quantity,
                "idle_threshold": self.idle_thres,
                "reset_bool": self.reset_bool,
                "verbose": self.verbose
            }
        }

    def create_cross_synthetic_order_payload_register(self, instrument_key):
        slot_name = "Arb_Order_CROSS_"+instrument_key.key+"_"+self.time_of_init
        ctrs_name = "LIFT_" + slot_name
        self.opp_slot_dict[slot_name] = (instrument_key.product_id, ctrs_name)
        self.prod_slot_dict['cross'][instrument_key.product_id] = slot_name
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": instrument_key.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "CrossOrderArb",
            "identifier": "Arb_Order_CROSS_"+instrument_key.key+"_"+self.time_of_init,
            "configuration": {
                "slot_name": "Arb_Order_CROSS_"+instrument_key.key+"_"+self.time_of_init,
                "market_area": instrument_key.instrument_id,
                "product_id": instrument_key.product_id,
                "broker_id": self.broker_ids[0],
                "lift_broker_id": self.broker_ids[0],
                "broker_list": self.broker_ids,
                "strategy_id": self.strategy_id,

                "lift_slot_name": "LIFT_"+"Arb_Order_CROSS_"+instrument_key.key+"_"+self.time_of_init,
                "cross_arb_margin_min": self.cross_arb_margin_min,
                "cross_arb_margin_max": self.cross_arb_margin_max,
                "min_time_cross": self.min_time_cross,
                "strategy_stats_dict": self.stats.to_dict(),

                "max_quantity": self.max_quantity,
                "market_volume_check_flag": self.market_volume_check_flag,
                "ql_max": self.ql_max,
                "reset_bool": self.reset_bool,
                "verbose": self.verbose
            }
        }

    def create_cross_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "CrossOrderLift",
            "identifier": "LIFT_" + so.slot_name,
            "configuration": {
                "slot_name": "LIFT_" + so.slot_name,
                "market_area": so.market_area,
                "broker_id": self.broker_ids[0],
                "lead_slot_name": so.slot_name,
                "product_id": so.product_id,
                "broker_list": self.broker_ids,
                "strategy_id": self.strategy_id,
                "strategy_stats_dict": self.stats.to_dict(),
                "min_margin": self.cross_arb_margin_min,
                "closing_in_profit_flag": self.closing_in_profit_flag,
                "max_quantity": self.max_quantity,
                "idle_threshold": self.idle_thres,
                "reset_bool": self.reset_bool,
                "verbose": self.verbose
            }
        }

    def quote(self):
        margin = self.fix_margin
        # TODO check for mutability of dictionaries
        if self.check_stats_dict_all:
            self._simple_order_buy(margin)
            self._simple_order_sell(margin)
            if self.cross_arb:
                self._simple_order_cross()
        else:
            self.reset_bool = True
            self._simple_order_buy(margin)
            self._simple_order_sell(margin)
            if self.cross_arb:
                self._simple_order_cross()
            self._update_lift_orders()
            self.debug_log("Arbitrage reset, all SO must stop posting orders")

    def _simple_order_buy(self, margin):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            market_making_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    isinstance(so, so_arbitrage_lead.ArbitrageOrder) and 'BID' in so.identifier]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageBid SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"margin": margin, "reset_bool": self.reset_bool}}
                    self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageBid SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"margin": margin, "reset_bool": self.reset_bool}}
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
                print(("Creating ArbitrageBid SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)))
                payload = self.create_bid_synthetic_order_payload_register(instrument_key, margin)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _simple_order_sell(self, margin):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            market_making_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    isinstance(so, so_arbitrage_lead.ArbitrageOrder) and 'ASK' in so.identifier]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageAsk SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"margin": margin, "reset_bool": self.reset_bool}}
                    self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageAsk SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"margin": margin, "reset_bool": self.reset_bool}}
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
                print(("Creating ArbitrageAsk SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)))
                payload = self.create_ask_synthetic_order_payload_register(instrument_key, margin)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _simple_order_cross(self):
        for key in self.instrument_keys:
            instrument_key = InstrumentKey().from_instrument_key(key)
            market_making_orders = [so for so in
                                    list(self.product_synthetic_order_mapping[instrument_key.product_id].values()) if
                                    isinstance(so, so_cross_lead.ArbitrageOrder) and 'CROSS' in so.identifier]
            if len(market_making_orders) == 1:
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageCROSS SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                    self.on_synthetic_order_modify(instrument_key.product_id, payload)
            elif len(market_making_orders) > 1:
                # Should not happen
                # Modify order
                so = market_making_orders[0]
                if self.verbose:
                    self.debug_log("Modifying ArbitrageCROSS SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                if self.reset_bool:
                    payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                    self.on_synthetic_order_modify(instrument_key.product_id, payload)
                # Delete rest
                for so in market_making_orders[1:]:
                    self.debug_log("Removing ArbitrageCROSS SO {} {}[{}]".format(
                        so.identifier, instrument_key.instrument_id, instrument_key.product_id)
                    )
                    payload = {"identifier": so.identifier, "synthetic_order_type": "ArbitrageOrder"}
                    self.on_synthetic_order_delete(instrument_key.product_id, payload)
            else:
                # Create sell order
                self.debug_log("Creating ArbitrageCROSS SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)
                )
                print(("Creating ArbitrageCROSS SO {}[{}]".format(
                    instrument_key.instrument_id, instrument_key.product_id)))
                payload = self.create_cross_synthetic_order_payload_register(instrument_key)
                self.on_synthetic_order_register(instrument_key.product_id, payload)

    def _update_lift_orders(self):
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, so_arbitrage_lift.LiftOrder) and 'BID' in so.slot_name:
                    if any([(lead_so.slot_name.startswith("Arb_Order_BID")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in list(self.product_synthetic_order_mapping[so.lead_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log("Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        elif self.verbose:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_arbitrage_lift.LiftOrder) and 'ASK' in so.slot_name:
                    if any([(lead_so.slot_name.startswith("Arb_Order_ASK")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in list(self.product_synthetic_order_mapping[so.lead_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log("Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        elif self.verbose:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    if any([(lift_so.slot_name == "LIFT_" + so.slot_name
                             and lift_so.market_area == so.lift_instrument_id)
                            for lift_so in list(self.product_synthetic_order_mapping[so.lift_product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(so.lift_product_id, payload)
                            self.debug_log("Found LIFT for LEAD SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.lift_product_id, payload)

                elif isinstance(so, so_cross_lift.LiftOrder):
                    if any([(lead_so.slot_name.startswith("Arb_Order_CROSS")
                             and lead_so.market_area == so.market_area)
                            for lead_so in list(self.product_synthetic_order_mapping[so.product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(prod, payload)
                            self.debug_log("Found LEAD for LIFT SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                        elif self.verbose:
                            self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_cross_lead.ArbitrageOrder):
                    if any([(lift_so.slot_name == "LIFT_" + so.slot_name
                             and lift_so.market_area == so.market_area)
                            for lift_so in list(self.product_synthetic_order_mapping[so.product_id].values())]):
                        # if we already have a LIFT for this, then do nothing
                        if self.reset_bool:
                            payload = {"identifier": so.identifier, "configuration": {"reset_bool": self.reset_bool}}
                            self.on_synthetic_order_modify(so.product_id, payload)
                            self.debug_log("Found LIFT for LEAD SO RESET BOOL modify {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_cross_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.product_id, payload)

    def delete_standing_orders(self):
        for prod, sos in list(self.product_synthetic_order_mapping.items()):
            for identifier, so in list(sos.items()):
                if isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    self.debug_log("Removing ArbitrageOrder SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "ArbitrageOrder"}
                    self.on_synthetic_order_delete(prod, payload)
                elif isinstance(so, so_cross_lead.ArbitrageOrder):
                    self.debug_log("Removing CrossOrderArb SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "CrossOrderArb"}
                    self.on_synthetic_order_delete(prod, payload)
                elif isinstance(so, so_arbitrage_lift.LiftOrder):
                    self.debug_log("Removing Lift SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                    self.on_synthetic_order_delete(prod, payload)
                elif isinstance(so, so_cross_lift.LiftOrder):
                    self.debug_log("Removing CrossOrderLift SO {} [{}]".format(so.identifier, prod))
                    payload = {"identifier": so.identifier, "synthetic_order_type": "CrossOrderLift"}
                    self.on_synthetic_order_delete(prod, payload)
        return 0

    def _call_act_orders(self, timestamp, trd_id_list=[], trade_bool=False, ordup_bool=True):
        # If order update then update balancing status first
        if ordup_bool:
            self.__update_status_balancing()
        products = []
        for inst_id in set(self.instrument_ids):
            products.extend(self.exchange.products.get_active_products(inst_id))
        products_ord, original_mapping_dict = self._order_synth_list(products, trd_id_list, trade_bool)
        res = self.act(timestamp, products_ord)
        if bool(original_mapping_dict):
            # Reorder back to original mapping
            print_dict = {p: list(v.keys()) for p, v in self.product_synthetic_order_mapping.items()}
            self.debug_log("Reordered activation {}".format(print_dict))
            self._reorder_mapping_dict(original_mapping_dict, False)
        else:
            self.debug_log("All synthetic orders activation")
        if not ordup_bool:
            self.__update_status_balancing()
        return res

    def _order_synth_list(self, products, trd_id_list, trade_bool):
        if trd_id_list:
            product_list = [p.product_id for p in products]
            products_ord = []
            prod_mapping_dict = {k: {} for k in self.product_synthetic_order_mapping.keys()}
            # Reorder products
            for t_id in trd_id_list:
                if not prod_mapping_dict[t_id[0]]:
                    i_d = product_list.index(t_id[0])
                    products_ord.append(products[i_d])
                prod_mapping_dict[t_id[0]][t_id[1]] = self.product_synthetic_order_mapping[t_id[0]][t_id[1]]
            # Reorder synthetic orders
            original_mapping_dict = self._reorder_mapping_dict(prod_mapping_dict, trade_bool)
        else:
            products_ord = products
            original_mapping_dict = {}
        return products_ord, original_mapping_dict

    def _reorder_mapping_dict(self, new_mapping_dict, trade_bool):
        original_mapping_dict = {}
        for p, s in new_mapping_dict.items():
            original_mapping_dict[p] = {k: v for k, v in self.product_synthetic_order_mapping[p].items()}
            if trade_bool:
                # When trade_bool is True then we only want to call relevant synthetic orders
                ordered_dict = s
            else:
                # Otherwise call all synthetic orders
                ordered_dict = {**s, **{k: v for k, v in self.product_synthetic_order_mapping[p].items() if
                                        k not in s.keys()}}
            self._product_synthetic_order_mapping[p] = {k: v for k, v in ordered_dict.items()}
        return original_mapping_dict

    def __update_status_balancing(self):
        instrument_key_list = [InstrumentKey().from_instrument_key(key) for key in self.instrument_keys]

        for inst_key in instrument_key_list:
            lift_orders_bid_dict = {inst_key.key: so.status
                                    for so in list(self.product_synthetic_order_mapping[inst_key.product_id].values())
                                    if isinstance(so, so_arbitrage_lift.LiftOrder) and 'BID' in so.identifier}
            lift_orders_ask_dict = {inst_key.key: so.status
                                    for so in list(self.product_synthetic_order_mapping[inst_key.product_id].values())
                                    if isinstance(so, so_arbitrage_lift.LiftOrder) and 'ASK' in so.identifier}
            lift_orders_cross_dict = {inst_key.key: so.status
                                      for so in list(self.product_synthetic_order_mapping[inst_key.product_id].values())
                                      if isinstance(so, so_cross_lift.LiftOrder) and 'CROSS' in so.identifier}

            if any([status!=COMMON.SyntheticOrderStates.passive for status in list(lift_orders_bid_dict.values())]):
                self.stats.balancing_dict[inst_key.key]['BID']=True
                self.debug_log("self.stats.balancing_bid for "+ str(inst_key.key)+" set to True")
            else:
                self.stats.balancing_dict[inst_key.key]['BID']=False
                self.debug_log("self.stats.balancing_bid for "+ str(inst_key.key)+" set to False")

            if any([status != COMMON.SyntheticOrderStates.passive for status in list(lift_orders_ask_dict.values())]):
                self.stats.balancing_dict[inst_key.key]['ASK']=True
                self.debug_log("self.stats.balancing_ask for "+ str(inst_key.key)+" set to True")
            else:
                self.stats.balancing_dict[inst_key.key]['ASK']=False
                self.debug_log("self.stats.balancing_ask for "+ str(inst_key.key)+" set to False")

            if any([status != COMMON.SyntheticOrderStates.passive for status in list(lift_orders_cross_dict.values())]):
                self.stats.balancing_dict[inst_key.key]['CROSS']=True
                self.debug_log("self.stats.balancing_cross for "+ str(inst_key.key)+" set to True")
            else:
                self.stats.balancing_dict[inst_key.key]['CROSS']=False
                self.debug_log("self.stats.balancing_cross for "+ str(inst_key.key)+" set to False")

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
        # Log into lag time dict
        slippage_time = timestamp - trade.execution_time
        self.log_stats_dict[instrument_key].append((timestamp, slippage_time))

        if slot_name not in self.stats.slot_dict.keys():
            return

        self.debug_log(
            "Trade on {}[{}]: [{}]: {}@{}  by slot {} // slippage {}".format(instrument_id, product_id, direction,
                                                                             trade.quantity, trade.price, slot_name,
                                                                             slippage_time)
        )
        # print(("Trade on {}[{}]: [{}]: {}@{}  by slot {}".format(instrument_id, product_id, direction,
        #                                           trade.quantity, trade.price, slot_name)))

        # Distribute trade into buckets
        try:
            self.stats.increment_slot_dict_trade(trade)
            self.stats.manage_trade_position(instrument_key, trade.price, trade.quantity, direction, timestamp)
            #api_export_trade(self, trade)
            if -self.stats.loss_pnl >= self.hard_stop_loss:
                self.stats.hard_sl = True
                self.debug_log(
                    "[{}] Strategy hard stop loss breached {}, PNL: {}, LOSS PNL: {}".format(
                        self.strategy_id, self.hard_stop_loss, self.stats.pnl, self.stats.loss_pnl)
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
        stat_id = id(self.stats.slot_dict)
        so_stat_id_list = [id(x.strategy_stats_dict['slot_dict']) for tr in self.product_synthetic_order_mapping.values() for x in tr.values()]
        return all([x == stat_id for x in so_stat_id_list])

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
            "LiftOrder": so_arbitrage_lift.LiftOrder,
            "CrossOrderArb": so_cross_lead.ArbitrageOrder,
            "CrossOrderLift": so_cross_lift.LiftOrder
        }
