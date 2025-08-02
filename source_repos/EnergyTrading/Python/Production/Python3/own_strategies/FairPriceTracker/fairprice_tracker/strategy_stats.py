import logging
import time
import numpy as np
import autotrader_synthetic.factory_view as FV
import autotrader_lib.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC
from .own_tools.price_class import PriceVol
from .own_tools.instrument_key import InstrumentKey
from .predictors import initiate_memory

tol = 1e-5

log = logging.getLogger("fairprice_tracker.strategy_statistics")
BUFFER_SIZE = 200

class StrategyStats(AdditionalTypeABC):
    strategy_id = ""
    caption = ""
    trade_leg_dict = {}
    instrument_list = []
    position_dict = {}
    bool_dict = {'manage_pos': False,'stop_loss': False,'hard_stop_loss': False}
    pnl_dict = {}
    aux_dict = {'ql': None, 'locked_until': 0.0, 'timestamp': None, 'last_traded_price': None,
                'trade_id': None, 'steering_closing': 'auto', 'open_price': None, 'make_profit_margin': None}
    param_dict = {'makeagg_ratio': None, 'bid_price': None, 'ask_price': None, 'open_price': None, 'burnout_period': 0.0, 'branch_flag': 0,
                  'position_list': [{'timestamp': None, 'direction': None, 'price': None, 'volume': None} for _ in range(50)]}

    def __init__(self, instrument_list=None, strategy_id='', caption=''):
        if instrument_list is None:
            instrument_list = []
        self.strategy_id = strategy_id
        self.caption = caption
        self.position_dict = self.init_position_dict


    def get_attr(self, name):
        return getattr(self, name)

    def set_attr(self, name, value):
        setattr(self, name, value)

    @property
    def init_position_dict(self):
        return {
            'open_price': None,
            'trailing_price': None,
            'open_time': None,
            'volume': 0,
            'takeprofit': None
        }

    def update_position(self, price, volume, timestamp):
        # volume is negative for short position
        log.info(f"position_dict id: {id(self.position_dict)}")
        if self.position_dict['open_time'] is None:
            # There was no position -> open
            self.position_dict['open_price'] = price
            self.position_dict['trailing_price'] = price
            self.position_dict['open_time'] = timestamp
            self.position_dict['volume'] = volume
            tp = self.position_dict['open_price'] + self.param_dict['make_profit_margin'] if volume > 0 else round(self.position_dict['open_price'] - self.param_dict['make_profit_margin'], 2)
            self.position_dict['takeprofit'] = tp
        else:
            # update parameters for the existing postion
            # open_price has to be averaged when increasing position
            # reseting position dict when position is balanced
            # when position is decrease just add the volume, current volume should have inversed sign
            pos_direction = 'long' if self.position_dict['volume'] > 0 else 'short'
            curr_direction = 'long' if volume > 0 else 'short'
            old_p, old_v = self.position_dict['open_price'], self.position_dict['volume']
            if pos_direction == curr_direction:
                self.position_dict['open_price'] = round((old_p*old_v + price*volume)/(old_v+volume),2)
                self.position_dict['volume'] += volume
            else:
                if old_v + volume == 0:
                    self.position_dict['open_price'] = None
                    self.position_dict['open_time'] = None
                    self.position_dict['trailing_price'] = None
                    self.position_dict['volume'] = 0
                    self.param_dict['burnout_period'] = 0.0
                else:
                    if pos_direction != curr_direction:
                        self.position_dict['volume'] += volume
                    else:
                        log.error(f"STRATEGY STATS - update position, self.position_dict['volume']{self.position_dict['volume']},"
                                  f"current_volume{volume}")
    def update_open_price(self, data_dict):
        open_position = self.position_dict['volume']
        open_price = self.position_dict['trailing_price']
        if open_position > 0:
            if data_dict['b_price']  > open_price:
                self.position_dict['trailing_price'] = data_dict['b_price']
        elif open_position < 0:
            if data_dict['a_price'] < open_price:
                self.position_dict['trailing_price'] = data_dict['a_price']
        else:
            log.error('ERROR Unexpected position', data_dict)

    def fair_price_bfr_init(self, instruments, buffer_size):
        ins_len = len(instruments)
        self.fairprice_dict = {
            'tr_buffer': np.full((buffer_size, ins_len), np.nan),
            'bo_buffer': np.full((buffer_size, 2), np.nan),
            'index': 0,
            'instruments': instruments
        }
    def tr_buffer_push(self, trade, instrument, inst_map):
        index = self.fairprice_dict['index']
        instrument_index = self.fairprice_dict['instruments'].index(instrument)
        row = np.full(len(self.fairprice_dict['instruments']), np.nan)
        row[instrument_index] = trade.price

        if index < (BUFFER_SIZE-1):
            self.fairprice_dict['tr_buffer'][index] = row
            self.fairprice_dict['index'] += 1
        else:
            arr = np.roll(self.fairprice_dict['tr_buffer'], -1, axis=0)
            arr[-1] = row
            self.fairprice_dict['tr_buffer'] = arr

    @property
    def attributes_list(self):
        return ['strategy_id', 'caption', 'instrument_list','trade_leg_dict', 'trade_spread_dict', 'bool_dict', 'pnl_dict', 'aux_dict', 'param_dict', 'position_dict', 'memory_dict', 'fairprice_dict']

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


    def update_instruments(self, instrument_list, time_of_init, params):
        # Position dictionary
        self.instrument_list = instrument_list
        self.pnl_dict = {'pnl': 0., 'mtm': 0.}
        self.timestamp = time.time()
        self.bool_dict = {'manage_pos': False,
                     'stop_loss': False, 'hard_stop_loss': False}

        self.trade_leg_dict = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_spread_dict = {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
        self.aux_dict = {'ql': None, 'locked_until': 0.0, 'timestamp': None, 'last_traded_price': None,
                    'trade_id': None, 'steering_closing': 'auto', 'open_price': None, 'make_profit_margin': None}
        self.param_dict = {'make_profit_margin': params['make_profit_margin'], 'makeagg_ratio': None, 'bid_price': None, 'ask_price': None,
                           'open_price': None, 'burnout_period': 0.0, 'branch_flag': 0,
                           'a_price_sparsity': 0.0, 'b_price_sparsity': 0.0,
                  'position_list': [{'timestamp': None, 'direction': None, 'price': None, 'volume': None} for _ in range(50)]}
        self.position_dict = self.init_position_dict
        self.memory_dict = initiate_memory()


    def manage_trade_position(self, instrument_key, price, quantity, side, timestamp):
        trade_pv = PriceVol(price, quantity)
        log.debug(
            "[{}] StrategyStats Management of position started".format(
                self.strategy_id)
        )
        # position_dict is used in decision making logic


        self.manage_pos = True
        trade_leg_dict = self.price_vol_trade_leg_dict
        trade_spread_dict = self.price_vol_trade_spread_dict

        if side == COMMON.Direction.sell:
            trade_leg_dict[instrument_key]["sell"] += trade_pv
            trade_spread_dict["sell"] += trade_pv
            self.update_position(price, -quantity, timestamp)

        else:
            trade_leg_dict[instrument_key]["buy"] += trade_pv
            trade_spread_dict["buy"] += trade_pv
            self.update_position(price, quantity, timestamp)


        # Write it back to dictionaries
        self.trade_leg_dict.update({k: {s: v.to_dict() for s, v in d.items()} for k, d in trade_leg_dict.items()})
        self.trade_spread_dict.update({s: v.to_dict() for s, v in trade_spread_dict.items()})

        if sum(self.net_position.values())==0.0:
            self.pnl_calc_and_push()


        # Balance
        self.manage_pos = False
        self.timestamp = timestamp
        return 0

    def set_spread_dict_quantity(self, trade_spread_dict):
        self.trade_spread_dict.update({s: v for s, v in trade_spread_dict.items()})
    def pnl_calc_and_push(self):
        """ Calculates and pushes the PNL"""
        pnl_dict_per_instrument = self.pnl_dict_per_instrument
        self.pnl=sum(pnl_dict_per_instrument.values())

    def update_locked_until(self, value):
        self.aux_dict['locked_until'] = value

    def update_trade_info(self, trade, timestamp):
        self.aux_dict['trade_id'] = trade.trade_id
        self.aux_dict['last_traded_price'] = trade.price
        self.aux_dict['timestamp'] = timestamp

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

def aon_check(market_view, direction, price_in, our_volume, broker_id, instrument_id):
    try:
        lift_orders=[]
        for order in market_view._product.orders._public_order_book[instrument_id].values():
            if order.broker_id==broker_id and order.direction==direction and order.price==price_in:
                lift_orders.append((order.direction, order.price, order.quantity,order.execution_restriction))

        normal_volumes=[order[2] for order in lift_orders if order[3]!='AON']
        aon_volumes=[order[2] for order in lift_orders if order[3]=='AON']

        for x in normal_volumes:
            return True

        for x in aon_volumes:
            if round(x) <= round(our_volume):
                return True

        return False

    except Exception as e:
        log.debug(
            "[{}] aon_check({},{},{},{},{}) failed! Error: {}, ".format(
             direction, price_in,broker_id, instrument_id,
                str(e))
        )
        return False

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


