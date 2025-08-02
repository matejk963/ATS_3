import logging
import time
import autotrader_synthetic.factory_view as FV
import autotrader_core.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC
from own_tools.price_class import PriceVol
from own_tools.instrument_key import InstrumentKey
tol = 1e-5

log = logging.getLogger("arbitrage.strategy_statistics")


class StrategyStats(AdditionalTypeABC):
    strategy_id = ""
    caption = ""
    instrument_list = []
    trade_leg_dict={}
    trade_spread_dict = {}
    bool_dict = {'manage_pos': False,'stop_loss': False,'hard_stop_loss': False}
    balancing_dict={}
    pnl_dict = {}
    slot_dict={}
    ql=None
    timestamp = None

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
        return ['strategy_id', 'caption', 'instrument_list','trade_leg_dict', 'trade_spread_dict', 'bool_dict','balancing_dict', 'pnl_dict', 'slot_dict', 'ql', 'timestamp']

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
        return {k: {s: PriceVol.from_dict(v) for s, v in d.items()} for k, d in self.trade_leg_dict.items()}
    @property
    def price_vol_trade_spread_dict(self):
        return {s: PriceVol.from_dict(v) for s, v in self.trade_spread_dict.items()}
    @property
    def net_position(self):
        trade_leg_dict = self.price_vol_trade_leg_dict
        return {k: v['buy'].quantity - v['sell'].quantity for k, v in trade_leg_dict.items()}

    @property
    def pnl_dict_per_instrument(self):
        trade_leg_dict = self.price_vol_trade_leg_dict
        return {k: - v['buy'].quantity*v['buy'].price + v['sell'].quantity*v['sell'].price for k, v in trade_leg_dict.items()}

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


    def update_instruments(self, instrument_list):
        # Position dictionary
        self.instrument_list = instrument_list
        self.pnl_dict = {'pnl': 0., 'mtm': 0.}
        self.timestamp = time.time()
        self.bool_dict = {'manage_pos': False,
                     'stop_loss': False, 'hard_stop_loss': False}

        self.balancing_dict={inst_key: {'BID': False, 'ASK': False} for inst_key in instrument_list}
        self.slot_dict = {}
        self.trade_leg_dict = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_spread_dict = {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}


    def manage_trade_position(self, instrument_key, price, quantity, side, timestamp):
        trade_pv = PriceVol(price, quantity)
        log.debug(
            "[{}] StrategyStats Management of position started".format(
                self.strategy_id)
        )
        self.manage_pos = True
        trade_leg_dict = self.price_vol_trade_leg_dict
        trade_spread_dict = self.price_vol_trade_spread_dict

        if side == COMMON.Direction.sell:
            trade_leg_dict[instrument_key]["sell"] += trade_pv
            trade_spread_dict["sell"] += trade_pv

        else:
            trade_leg_dict[instrument_key]["buy"] += trade_pv
            trade_spread_dict["buy"] += trade_pv


        # Write it back to dictionaries
        self.trade_leg_dict.update({k: {s: v.to_dict() for s, v in d.items()} for k, d in trade_leg_dict.items()})
        self.trade_spread_dict.update({s: v.to_dict() for s, v in trade_spread_dict.items()})

        if sum(self.net_position.values())==0.0:
            self.pnl_calc_and_push()


        # Balance
        self.manage_pos = False
        self.timestamp = timestamp
        return 0

    def pnl_calc_and_push(self):
        """ Calculates and pushes the PNL"""
        pnl_dict_per_instrument = self.pnl_dict_per_instrument
        self.pnl=sum(pnl_dict_per_instrument.values())

    def increment_slot_dict_trade(self, trade):
        slot_name=trade.tags.get('strategy_slot')

        if slot_name not in self.slot_dict:
            self.slot_dict[slot_name]={'net_volume':0, 'last_direction':None,
                                       'last_price': None, 'last_execution_time':None,
                                       'last_order_price': None}

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
            self.slot_dict[slot_name]={'net_volume':0, 'last_direction':None,
                                       'last_price': None, 'last_execution_time':None,
                                       'last_order_price': None}

            self.slot_dict[slot_name]['last_order_price'] = order.price

        else:
            self.slot_dict[slot_name]['last_order_price'] = order.price


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

def aon_check(strategy_id,direction, market_view, price_in, depth, broker_id, instrument_id):
    try:
        lift_orders=[]
        for order in market_view._product.orders._public_order_book[instrument_id].values():
            if order.broker_id==broker_id and order.direction==direction and order.price==price_in:
                lift_orders.append((order.direction, order.price, order.quantity,order.execution_restriction))

        normal_volumes=[order[2] for order in lift_orders if order[3]<>'AON']
        aon_volumes=[order[2] for order in lift_orders if order[3]=='AON']


        if sum(aon_volumes)<=0:#sum(normal_volumes)>=depth or (depth-sum(normal_volumes) in aon_volumes):
            log.debug(
                "[{}] aon_check({},{},{},{},{}) calculated normal_volumes and aon_volumes: {}, {}; Result True. ".format(
                 strategy_id, direction, price_in, depth, broker_id, instrument_id, sum(normal_volumes),
                    sum(aon_volumes))
            )
            return True

        log.debug(
            "[{}] aon_check({},{},{},{},{}) calculated normal_volumes and aon_volumes: {}, {}; Result False. ".format(
                 strategy_id, direction, price_in, depth, broker_id, instrument_id, sum(normal_volumes),
                sum(aon_volumes))
        )
        return False

    except Exception as e:
        log.debug(
            "[{}] aon_check({},{},{},{},{}) failed! Error: {}, ".format(
             strategy_id, direction, price_in, depth,broker_id, instrument_id,
                str(e))
        )
        return False


