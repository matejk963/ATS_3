import logging
import time
import copy
import autotrader_synthetic.factory_view as FV
import autotrader_lib.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC
from .own_tools.price_class import PriceVol
from .own_tools.instrument_key import InstrumentKey
from .own_tools.misc import push_to_list,unix_timestamp_to_cet_string
from .predictors import calculate_MACD, calculate_rolling_macd_fast, calc_vol_intensity_index

import numpy as np

tol = 1e-5

log = logging.getLogger("leadlag_strategy.strategy_statistics")


class StrategyStats(AdditionalTypeABC):
    strategy_id = ""
    caption = ""
    instrument_list = []
    trade_leg_dict={}
    trade_leg_dict_for_mtm={}
    trade_spread_dict = {}
    price_leg_dict = {}
    bool_dict = {'manage_pos': False,'take_profit': False, 'stop_loss': False,'hard_stop_loss': False, 'trail_stop_flag': False}
    balancing_dict={}
    pnl_dict = {}
    slot_dict={}
    bid_ask_list = [(None, None, None)] * 50
    aux_dict={'action': None, 'locked_until': 0.0, 'ql': None, 'timestamp': None, 'max_mtm': None, 'op_tip': None, 'last_action': None, 'last_bid':None, 'last_ask': None}
    paper_trading_list=[(None, None, None, None)]*50
    predictor_dict = {'MACD': None,
                      'bid_macd': None, 'ask_macd': None,
                      'bid_volatility': None, 'ask_volatility': None,
                      'ba_spread': None,
                      'VII_5':None, 'intensity':None}
    # public_lead_trade_list = [(None, None, None, None)]*1000
    # public_lag_trade_list = [(None, None, None, None)]*1000


    def __init__(self, instrument_list=None, strategy_id='', caption=''):
        if instrument_list is None:
            instrument_list = []
        self.strategy_id = strategy_id
        self.caption = caption


    def get_attr(self, name):
        return getattr(self, name)

    def set_attr(self, name, value):
        setattr(self, name, value)

    @property
    def attributes_list(self):
        return ['strategy_id', 'caption', 'instrument_list','trade_leg_dict', 'trade_leg_dict_for_mtm', 'trade_spread_dict', 'bool_dict','balancing_dict', 'pnl_dict', 'slot_dict', 'bid_ask_list','aux_dict', 'paper_trading_list', 'predictor_dict']#,, 'public_lead_trade_list', 'public_lag_trade_list'

    @property
    def pnl(self):
        return self.pnl_dict['pnl']

    @pnl.setter
    def pnl(self, value):
        if isinstance(value, float):
            self.pnl_dict['pnl'] = value
        else:
            raise ValueError("StrategyStats pnl must be float, instead was: %s." % value)

    @property
    def mtm(self):
        return self.pnl_dict['mtm']

    @mtm.setter
    def mtm(self, value):
        if isinstance(value, float):
            self.pnl_dict['mtm'] = value
        else:
            raise ValueError("StrategyStats mtm must be float, instead was: %s." % value)


    @property
    def stop_loss(self):
        return self.bool_dict['stop_loss']

    @stop_loss.setter
    def stop_loss(self, value):
        if isinstance(value, bool):
            self.bool_dict['stop_loss'] = value
        else:
            raise ValueError("StrategyStats stop_loss must be boolean, instead was: %s." % value)

    @property
    def hard_sl(self):
        return self.bool_dict['hard_stop_loss']

    @hard_sl.setter
    def hard_sl(self, value):
        if isinstance(value, bool):
            self.bool_dict['hard_stop_loss'] = value
        else:
            raise ValueError("StrategyStats hard_sl must be boolean, instead was: %s." % value)


    @property
    def price_vol_trade_leg_dict(self):
        return {k: {s: PriceVol.from_dict(v) for s, v in list(d.items())} for k, d in list(self.trade_leg_dict.items())}

    @property
    def price_vol_trade_leg_dict_for_mtm(self):
        return {k: {s: PriceVol.from_dict(v) for s, v in list(d.items())} for k, d in list(self.trade_leg_dict_for_mtm.items())}

    @property
    def price_vol_trade_spread_dict(self):
        return {s: PriceVol.from_dict(v) for s, v in list(self.trade_spread_dict.items())}
    @property
    def net_position(self):
        trade_leg_dict = self.price_vol_trade_leg_dict
        return {k: v['buy'].quantity - v['sell'].quantity for k, v in list(trade_leg_dict.items())}

    @property
    def pnl_dict_per_instrument(self):
        trade_leg_dict = self.price_vol_trade_leg_dict
        return {k: - v['buy'].quantity*v['buy'].price + v['sell'].quantity*v['sell'].price for k, v in list(trade_leg_dict.items())}

    @property
    def mtm_dict_per_instrument(self):
        trade_leg_dict_for_mtm = self.price_vol_trade_leg_dict_for_mtm
        return {k: v['buy'].quantity*((self.price_leg_dict[k]['buy']/2.0+self.price_leg_dict[k]['sell']/2.0)-v['buy'].price) + v['sell'].quantity*(v['sell'].price - (self.price_leg_dict[k]['buy']/2.0+self.price_leg_dict[k]['sell']/2.0)) for k, v in list(trade_leg_dict_for_mtm.items())}

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        return value.to_dict()

    @classmethod
    def from_dict(cls, value_dict):
        new_cls = StrategyStats()
        for key in new_cls.attributes_list:
            new_cls.set_attr(key, value_dict[key])
        return new_cls


    def to_dict(self):
        return {k: self.get_attr(k) for k in self.attributes_list}

    def in_position(self):
        if sum(self.net_position.values()):
            return not sum(self.net_position.values()) == 0.0
        else:
            return False


    def update_instruments(self, instrument_list, time_of_init):
        # Position dictionary
        self.instrument_list = instrument_list
        self.pnl_dict = {'pnl': 0., 'mtm': 0.}
        self.timestamp = time.time()
        self.bool_dict = {'manage_pos': False, 'take_profit': False,
                     'stop_loss': False, 'hard_stop_loss': False}

        self.balancing_dict={inst_key: False for inst_key in instrument_list}
        self.initiate_slot_dict(instrument_list, time_of_init)
        self.bid_ask_list = [(None, None, None)]*50
        self.paper_trading_list= [(None, None, None, None)]*50
        self.aux_dict = {'action': None, 'locked_until': 0.0, 'ql': None, 'timestamp': None, 'max_mtm': None, 'op_tip': None, 'last_action': None, 'last_bid':None, 'last_ask': None}

        self.predictor_dict = {'MACD': None,
                      'bid_macd': None, 'ask_macd': None,
                      'bid_volatility': None, 'ask_volatility': None,
                      'ba_spread': None,
                      'VII_5':None, 'intensity':None}

        self.trade_leg_dict = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_leg_dict_for_mtm = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_spread_dict = {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}

        self.price_leg_dict = {k: {s: 0. for s in ['buy', 'sell']} for k in instrument_list}



        # self.public_lead_trade_list = [(None, None, None, None)]*1000
        # self.public_lag_trade_list = [(None, None, None, None)]*1000

    def manage_trade_position(self, instrument_key, price, quantity, side, timestamp):
        trade_pv = PriceVol(price, quantity)
        log.debug(
            "[{}] StrategyStats Management of position started".format(
                self.strategy_id)
        )
        self.manage_pos = True
        trade_leg_dict = self.price_vol_trade_leg_dict
        trade_leg_dict_for_mtm = self.price_vol_trade_leg_dict_for_mtm
        trade_spread_dict = self.price_vol_trade_spread_dict

        if side == COMMON.Direction.sell:
            trade_leg_dict[instrument_key]["sell"] += trade_pv
            trade_leg_dict_for_mtm[instrument_key]["sell"] += trade_pv
            trade_spread_dict["sell"] += trade_pv

        else:
            trade_leg_dict[instrument_key]["buy"] += trade_pv
            trade_leg_dict_for_mtm[instrument_key]["buy"] += trade_pv
            trade_spread_dict["buy"] += trade_pv


        # Write it back to dictionaries
        self.trade_leg_dict.update({k: {s: v.to_dict() for s, v in list(d.items())} for k, d in list(trade_leg_dict.items())})
        self.trade_leg_dict_for_mtm.update({k: {s: v.to_dict() for s, v in list(d.items())} for k, d in list(trade_leg_dict_for_mtm.items())})
        self.trade_spread_dict.update({s: v.to_dict() for s, v in list(trade_spread_dict.items())})

        if sum(self.net_position.values())==0.0:
            self.pnl_calc_and_push()
            #reset the trade_leg_dict_for_mtm calculator
            self.trade_leg_dict_for_mtm = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                                            for k in self.instrument_list}

        # Balance
        self.manage_pos = False
        self.timestamp = timestamp
        return 0

    def pnl_calc_and_push(self):
        """ Calculates and pushes the PNL"""
        pnl_dict_per_instrument = self.pnl_dict_per_instrument
        self.pnl=sum(pnl_dict_per_instrument.values())

    def mtm_calc_and_push(self):
        """ Calculates and pushes the MTM"""
        mtm_dict_per_instrument = self.mtm_dict_per_instrument
        self.mtm=sum(x if x is not None else 0 for x in mtm_dict_per_instrument.values())

    def initiate_slot_dict(self, instrument_list, time_of_init):
        self.slot_dict={}
        slot_name_list = ["Init_Order_", "CLOSING_Init_Order_"]
        for inst_key in instrument_list:
            for slots in slot_name_list:
                slot_name = slots + inst_key + "_" + time_of_init
                self.slot_dict[slot_name]={'net_volume':0, 'last_direction':None,
                                        'last_price': None, 'last_execution_time':None,
                                        'last_order_price': None}
    def increment_slot_dict_trade(self, trade):
        slot_name=trade.tags.get('strategy_slot')

        if slot_name not in self.slot_dict:
            return

        if trade.direction == 'sell':
            self.slot_dict[slot_name]['net_volume'] += -1*trade.quantity

        else:
            self.slot_dict[slot_name]['net_volume'] += +1*trade.quantity

        self.slot_dict[slot_name]['last_direction'] = trade.direction
        self.slot_dict[slot_name]['last_price'] = trade.price
        self.slot_dict[slot_name]['last_execution_time'] = trade.execution_time

    def increment_slot_dict_order(self, order):
        slot_name=order.tags.get('strategy_slot')

        if slot_name not in self.slot_dict:
            return

        else:
            self.slot_dict[slot_name]['last_order_price'] = order.price


    def increment_bid_ask_list(self, instrument_key, products):
        additional_views = FV.ViewFactory(products=products, strategy_id=self.strategy_id)
        market_view = additional_views.get_view_for_instrument(
            instrument_key.instrument_id,
            instrument_key.product_id
        )
        bid_price=market_view.current_front_price(COMMON.Direction.buy)
        ask_price=market_view.current_front_price(COMMON.Direction.sell)

        if bid_price and ask_price and (bid_price!=self.aux_dict['last_bid'] or ask_price!=self.aux_dict['last_ask']) and ask_price-bid_price>-0.15:
            self.aux_dict['last_bid']=bid_price
            self.aux_dict['last_ask']=ask_price

            record=(bid_price, ask_price, time.time())
            log.debug("Pushing to bid_ask_list: [{}]: bid_price: {},ask_price: {}, time: {}".format(self.strategy_id,record[0], record[1], record[2]))
            push_to_list(self.bid_ask_list, record)


    def increment_paper_trading_list(self, direction, price, quantity, timestamp):
        record=(direction, price, quantity, timestamp)
        push_to_list(self.paper_trading_list, record)


    def update_locked_until(self, value):
        self.aux_dict['locked_until'] = value

    def update_strategy_prices(self, instrument_key, direction, products, broker_id):
        additional_views = FV.ViewFactory(products=products, strategy_id=self.strategy_id)
        market_view = additional_views.get_view_for_instrument(
            instrument_key.instrument_id,
            instrument_key.product_id
        )
        price = get_avg_market_price_depth(direction, market_view, 0, broker_id)
        # log.debug(
        #     "[{}] StrategyStats Price Update, BROKER:{}, {}[{}] {}@{}".format(
        #         self.strategy_id, broker_id, instrument_key.instrument_id, instrument_key.product_id,
        #         direction, price)
        # )
        if price:
            self.price_leg_dict[instrument_key.key][direction] = price
        else:
            self.price_leg_dict[instrument_key.key][direction] = 0.0
        self.timestamp = time.time()



    def calculate_action(self, market_view, bid_price, ask_price, parameter_dict):

        MACD = calculate_MACD(market_view)
        VII_5=calc_vol_intensity_index(market_view, 5, time.time())
        bid_macd, bid_volatility=calculate_rolling_macd_fast(self.bid_ask_list, side='bid')
        ask_macd, ask_volatility=calculate_rolling_macd_fast(self.bid_ask_list, side='ask')
        ba_spread=round(ask_price-bid_price,4)

        self.predictor_dict['MACD'], self.predictor_dict['bid_macd'], self.predictor_dict['bid_volatility'], self.predictor_dict['ask_macd'], self.predictor_dict['ask_volatility'], self.predictor_dict['ba_spread'], self.predictor_dict['VII_5']  = MACD,bid_macd,bid_volatility,ask_macd,ask_volatility,ba_spread, VII_5

        if any(value is None for value in [MACD, bid_macd, bid_volatility, ask_macd, ask_volatility, ba_spread, VII_5]):
            log.debug(
                "[{}] BAC-CALCULATE-ACTION: Action could not be calculated: MACD {}, bid_macd {},bid_volatility {},ask_macd {},ask_volatility {},ba_spread {},VII_5 {},".format(
                    self.strategy_id, MACD, bid_macd, bid_volatility, ask_macd, ask_volatility, ba_spread, VII_5)
            )
            return 0

        self.predictor_dict['intensity']=abs(VII_5)

        #calculate the action/direction to take based on the values calculated
        action=0

        if (bid_macd > parameter_dict['ba_conv_large_threshold']
                and abs(ask_macd) < parameter_dict['ba_conv_small_threshold']
                and ask_volatility < parameter_dict['ba_conv_volatility_threshold']
                and ba_spread < parameter_dict['ba_conv_ba_threshold']

                and (MACD > parameter_dict['MACD_long_threshold'] and abs(VII_5) > parameter_dict[
                    'minimum_intensity'])):
            action = 1

        elif (ask_macd < -1*parameter_dict['ba_conv_large_threshold']
                and abs(bid_macd) < parameter_dict['ba_conv_small_threshold']
                and bid_volatility < parameter_dict['ba_conv_volatility_threshold']
                and ba_spread < parameter_dict['ba_conv_ba_threshold']

                and (MACD < parameter_dict['MACD_short_threshold'] and abs(VII_5) > parameter_dict[
                    'minimum_intensity'])):
            action = -1


        log.debug("[{}] BAC-CALCULATE-ACTION: Action calculated: action {}, : MACD {}, bid_macd {},bid_volatility {},ask_macd {},ask_volatility {},ba_spread {},intensity {},".format(
                    self.strategy_id, action, MACD, bid_macd, bid_volatility, ask_macd, ask_volatility, ba_spread, abs(VII_5))
            )
        return action


def current_front_price_brk(market_view, direction, brk_list, only_tradable):
    price_tuple = [(market_view.current_front_price(direction, b, only_tradable=only_tradable), b, i)
                   for i, b in enumerate(brk_list)]
    price_tuple = [p_t for p_t in price_tuple if p_t[0] is not None]
    if not price_tuple:
        return None, brk_list[0]
    if direction == COMMON.Direction.buy:
        return max(price_tuple, key=lambda x: (x[0], -x[2]))[:2]
    else:
        return min(price_tuple, key=lambda x: (x[0], x[2]))[:2]

def get_avg_market_price_depth(direction, market_view, depth, broker_list):
    if not broker_list:
        broker_list = [None]
        only_tradable = False
    else:
        only_tradable = True
    if depth == 0:
        return current_front_price_brk(market_view, direction, broker_list, only_tradable)[0]
    else:
        if direction == COMMON.Direction.buy:
            reverse = True
        else:
            reverse = False
        price = 0
        vol = 0
        price_levels_list = []
        [price_levels_list.extend(market_view._summarize_price_level(direction, b, only_tradable=only_tradable))
         for b in broker_list]
        if len(broker_list) > 1:
            price_levels_list.sort(key=lambda e: e[0], reverse=reverse)
        for p, v in price_levels_list:
            if vol + v > depth:
                v = depth - vol
                price += p * v
                vol += v
                break
            else:
                price += p * v
                vol += v
        if vol < depth:
            return None
        else:
            if vol > 0:
                return price / vol
            else:
                return None

def get_price_diff_depth(strategy_id,direction, market_view, price_in, depth, broker_id):
    # Initialize variables for volume and output price
    vol = 0
    price_out = 0

    # Summarize the price levels based on the given direction and broker_id
    price_levels_list = market_view._summarize_price_level(direction, broker_id, only_tradable=True)

    # Determine the sign based on the direction (buy or sell)
    if direction == COMMON.Direction.buy:
        sign = 1
    else:
        sign = -1

    # Iterate through the summarized price levels
    for p, v in price_levels_list:
        # Check if the price level matches the desired direction
        if sign * p <= sign * price_in:
            # Check if adding the volume would exceed the specified depth
            if vol + v > depth:
                v = depth - vol
                price_out += p * v
                vol += v
                continue
            else:
                price_out += p * v
                vol += v
        else:
            # Skip price levels that do not match the desired direction
            pass

    log.debug(
        "[{}] get_price_diff_depth({},{},{},{}) calculated vol: {}. ".format(
            strategy_id, direction, price_in, depth, broker_id, vol)
    )

    # If the accumulated volume is less than the desired depth, return None
    if vol < depth:
        return None
    else:
        # If there is a non-zero volume, return the weighted average price
        if vol > 0:
            return price_out / vol
        else:
            # If volume is zero, return None
            return None


def aon_check(strategy_id, market_view, direction, price_in, depth, instrument_id):
    try:
        lift_orders=[]
        for order in list(market_view._product.orders._public_order_book[instrument_id].values()):
            if order.direction==direction and order.price==price_in:
                lift_orders.append((order.direction, order.price, order.quantity,order.execution_restriction))

        normal_volumes=[order[2] for order in lift_orders if order[3]!='AON']
        aon_volumes=[order[2] for order in lift_orders if order[3]=='AON']


        if sum(normal_volumes)>=depth or (depth-sum(normal_volumes) in aon_volumes):#
            log.debug(
                "[{}] aon_check({},{},{},{}) calculated normal_volumes and aon_volumes: {}, {}; Result True. ".format(
                 strategy_id, direction, price_in, depth, instrument_id, sum(normal_volumes),
                    sum(aon_volumes))
            )
            return True

        log.debug(
            "[{}] aon_check({},{},{},{}) calculated normal_volumes and aon_volumes: {}, {}; Result False. ".format(
                 strategy_id, direction, price_in, depth, instrument_id, sum(normal_volumes),
                sum(aon_volumes))
        )
        return False

    except Exception as e:
        log.debug(
            "[{}] aon_check({},{},{},{}) failed! Error: {}, ".format(
             strategy_id, direction, price_in, depth, instrument_id,
                str(e))
        )
        return False


