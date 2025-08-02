import logging
import time
import autotrader_synthetic.factory_view as FV
import autotrader_core.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC
from own_tools.price_class import PriceVol
from own_tools.instrument_key import InstrumentKey
tol = 1e-5

log = logging.getLogger("market_making_single.strategy_statistics")


class StrategyStats(AdditionalTypeABC):
    strategy_id = ""
    instrument_list = []
    trade_spread_dict = {}
    price_leg_dict = {}
    price_ref_dict = {}
    model_dict = {}
    leg_clip = None
    param_dict = {}
    bool_dict = {'manage_pos': False, 'stop_loss': False, 'hard_stop_loss': False}
    lift_bool_dict = {}
    hold_dict = {}
    pnl_dict = {}
    timestamp = None

    def __init__(self, instrument_list=None, strategy_id='', leg_clip=1, eql_w=0, eql_price=None,
                 w1=1., w_std=0):
        if instrument_list is None:
            instrument_list = []
        self.strategy_id = strategy_id
        # Position dictionaries
        self.update_instruments(instrument_list, leg_clip, eql_w, eql_price, w1, w_std)

    def get_attr(self, name):
        return getattr(self, name)

    def set_attr(self, name, value):
        setattr(self, name, value)

    @property
    def attributes_list(self):
        return ['strategy_id', 'instrument_list', 'trade_spread_dict', 'price_leg_dict', 'price_ref_dict', 'model_dict',
                'param_dict', 'bool_dict', 'lift_bool_dict', 'pnl_dict', 'timestamp']

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
    def w(self):
        return self.param_dict['eql_weight']

    @w.setter
    def w(self, value):
        if isinstance(value, float):
            if value < 0 or value > 1:
                value = 0.
            self.param_dict['eql_weight'] = value
        else:
            raise ValueError("StrategyStats weight for equilibrium model must be float, instead was: %s." % value)

    @property
    def w1(self):
        return self.param_dict['mrg_weight']

    @w1.setter
    def w1(self, value):
        if isinstance(value, float):
            if value < 0 or value > 1:
                value = 0.
            self.param_dict['mrg_weight'] = value
        else:
            raise ValueError("StrategyStats weight for margin vs std must be float, instead was: %s." % value)

    @property
    def w_std(self):
        return self.param_dict['std_weight']

    @w_std.setter
    def w_std(self, value):
        if isinstance(value, float):
            # It can be bigger than 1
            if value < 0:
                value = 0.
            self.param_dict['std_weight'] = value
        else:
            raise ValueError("StrategyStats weight for std must be float, instead was: %s." % value)

    @property
    def eql_value(self):
        return self.param_dict['eql_value']

    @eql_value.setter
    def eql_value(self, value):
        if isinstance(value, float):
            self.param_dict['eql_value'] = value
        else:
            raise ValueError("StrategyStats value for equilibrium model must be float, instead was: %s." % value)

    @property
    def manage_pos(self):
        return self.bool_dict['manage_pos']

    @manage_pos.setter
    def manage_pos(self, value):
        if isinstance(value, bool):
            self.bool_dict['manage_pos'] = value
        else:
            raise ValueError("StrategyStats manage_pos must be boolean, instead was: %s." % value)

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
    def quote_bool(self):
        return not self.hard_sl

    @property
    def price_vol_trade_spread_dict(self):
        return {s: PriceVol.from_dict(v) for s, v in self.trade_spread_dict.items()}

    @property
    def net_spread_position(self):
        trade_spread_dict = self.price_vol_trade_spread_dict
        return trade_spread_dict['buy'].quantity - trade_spread_dict['sell'].quantity

    @property
    def is_spread_price(self):
        if self.ref_instkey is None:
            return self.is_leg_price
        else:
            return self.is_leg_price or self.is_ref_price

    @property
    def is_leg_price(self):
        return all(x is not None for x in self.price_leg_dict.values())

    @property
    def is_ref_price(self):
        if self.ref_instkey is None:
            return False
        else:
            return all(x is not None for subdict in self.price_ref_dict.values() for x in subdict.values())

    @property
    def bid_spread(self):
        is_leg_price = self.is_leg_price
        is_ref_price = self.is_ref_price
        if is_ref_price:
            p_ref = min(self.price_ref_dict[self.ref1_instkey]['buy'] - self.price_ref_dict[self.ref2_instkey]['buy'],
                        self.price_ref_dict[self.ref1_instkey]['sell'] - self.price_ref_dict[self.ref2_instkey]['sell'])
        else:
            p_ref = None
        if is_leg_price or is_ref_price:
            if is_leg_price and is_ref_price:
                return max(p_ref, self.price_leg_dict['buy'])
            elif is_ref_price:
                return p_ref
            else:
                return self.price_leg_dict['buy']
        else:
            return None

    @property
    def ask_spread(self):
        is_leg_price = self.is_leg_price
        is_ref_price = self.is_ref_price
        if is_ref_price:
            p_ref = max(self.price_ref_dict[self.ref1_instkey]['buy'] - self.price_ref_dict[self.ref2_instkey]['buy'],
                        self.price_ref_dict[self.ref1_instkey]['sell'] - self.price_ref_dict[self.ref2_instkey]['sell'])
        else:
            p_ref = None
        if is_leg_price or is_ref_price:
            if is_leg_price and is_ref_price:
                return min(p_ref, self.price_leg_dict['sell'])
            elif is_ref_price:
                return p_ref
            else:
                return self.price_leg_dict['sell']
        else:
            return None

    @property
    def mid_spread(self):
        if self.is_spread_price:
            return .5 * (self.bid_spread + self.ask_spread)
        else:
            return None

    @property
    def is_model_price(self):
        return self.model_dict['spread'] is not None

    @property
    def is_adjusted_model_price(self):
        return self.model_price is not None and self.eql_value is not None

    @property
    def model_price(self):
        return self.model_dict['spread']

    @property
    def is_model_std(self):
        return self.model_std is not None

    @property
    def model_std(self):
        return self.model_dict['std']

    @property
    def eqb_price(self):
        if self.eql_value is None:
            return self.model_price
        else:
            return self.eql_value

    @property
    def adjusted_model_price(self):
        if self.w == 0:
            return self.model_price
        else:
            if self.is_adjusted_model_price:
                return self.w * self.eqb_price + (1 - self.w) * self.model_price
            else:
                return None

    def get_instrument_model_price(self, instrument_key):
        if any([x is None for x in self.price_leg_dict[instrument_key].values()]):
            price = None
        else:
            price = .5 * (self.price_leg_dict[instrument_key]['buy'] + self.price_leg_dict[instrument_key]['sell'])
        return price

    @property
    def ref_instkey(self):
        if all([x is None for x in [self.ref1_instkey, self.ref2_instkey]]):
            return None
        else:
            return [self.ref1_instkey, self.ref2_instkey]

    @property
    def ref1_instkey(self):
        try:
            return self.instrument_list[1]
        except IndexError:
            return None

    @property
    def ref2_instkey(self):
        try:
            return self.instrument_list[2]
        except IndexError:
            return None

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

    def position_to_dict(self):
        return {k: self.get_attr(k) for k in ['trade_spread_dict']}

    def update_instruments(self, instrument_list, leg_clip, eql_w, eql_price, w1, w_std):
        # Position dictionary
        self.instrument_list = instrument_list
        self.trade_spread_dict = {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
        # PriceVol dictionary
        self.price_leg_dict = {s: None for s in ['buy', 'sell']}
        self.leg_clip = leg_clip
        if self.ref_instkey is None:
            self.price_ref_dict = {}
        else:
            self.price_ref_dict = {k: {s: None for s in ['buy', 'sell']} for k in instrument_list[1:3]}
        self.model_dict = {'spread': None, 'std': None}
        self.param_dict = {'eql_weight': eql_w, 'eql_value': eql_price, 'mrg_weight': w1, 'std_weight': w_std}
        self.pnl_dict = {'pnl': 0., 'mtm': 0.}
        self.timestamp = time.time()

    def manage_trade_position(self, instrument_key, price, quantity, side, timestamp):
        trade_pv = PriceVol(price, quantity)
        log.debug(
            "[{}] StrategyStats Management of position started".format(
                self.strategy_id)
        )
        self.manage_pos = True
        trade_spread_dict = self.price_vol_trade_spread_dict
        if side == COMMON.Direction.sell:
            trade_spread_dict[instrument_key]["sell"] += trade_pv
        else:
            trade_spread_dict[instrument_key]["buy"] += trade_pv
        net_clip_position_spread = min(trade_spread_dict['buy'].quantity, trade_spread_dict['sell'].quantity)
        log.debug(
            "[{}] StrategyStats Management of position clearing clips: Spread: {}".format(
                self.strategy_id, net_clip_position_spread)
        )
        # Clear closed position on Lead market
        if net_clip_position_spread > 0:
            trade_spread_dict['buy'] -= net_clip_position_spread
            trade_spread_dict['sell'] -= net_clip_position_spread
            self.pnl += self.pnl_push(trade_spread_dict, net_clip_position_spread)
        # Write it back to dictionaries
        self.trade_spread_dict.update({s: v.to_dict() for s, v in trade_spread_dict.items()})
        self.print_spread_positions(trade_spread_dict)
        # Balance
        self.manage_pos = False
        self.check_balancing()
        self.timestamp = timestamp
        return 0

    def update_strategy_prices(self, instrument_key, direction, products, broker_id):
        additional_views = FV.ViewFactory(products=products, strategy_id=self.strategy_id)
        market_view = additional_views.get_view_for_instrument(
            instrument_key.instrument_id,
            instrument_key.product_id
        )
        price = get_avg_market_price_depth(direction, market_view, 0, broker_id)
        log.debug(
            "[{}] StrategyStats Price Update, BROKER:{}, {}[{}] {}@{}".format(
                self.strategy_id, broker_id, instrument_key.instrument_id, instrument_key.product_id,
                direction, price)
        )
        if (self.ref_instkey is not None) and (instrument_key.key in self.ref_instkey):
            self.price_ref_dict[instrument_key.key][direction] = price
        else:
            self.price_leg_dict[direction] = price
        self.timestamp = time.time()

    def update_model_prices(self, model_stats):
        model_price = model_stats.update_strategy_prices(self.bid_spread, self.ask_spread, self.mid_spread)
        self.model_dict['spread'] = model_price
        self.model_dict['std'] = model_stats.spread_std
        if self.net_spread_position == 0:
            self.mtm = 0.
        else:
            trade_spread_dict = self.price_vol_trade_spread_dict
            if self.net_spread_position > 0:
                direction = COMMON.Direction.buy
            else:
                direction = COMMON.Direction.sell
            price = trade_spread_dict[direction].price
            self.mtm = self.mtm_spread(direction, price)

    def init_strategy_prices(self, products, broker_id, model_stats):
        log.debug(
            "[{}] StrategyStats Init Prices, BROKER:{}".format(
                self.strategy_id, broker_id)
        )
        direction_list = [COMMON.Direction.buy, COMMON.Direction.sell]
        for instkey in self.instrument_list:
            instrument_key = InstrumentKey().from_instrument_key(instkey)
            for direction in direction_list:
                self.update_strategy_prices(instrument_key, direction, products, broker_id)
        self.update_model_prices(model_stats)

    def check_balancing(self):
        if self.manage_pos:
            log.debug(
                "[{}] StrategyStats Balancing check postponed due to managing position".format(
                    self.strategy_id)
            )
        else:
            if abs(self.net_spread_position) < tol:
                self.stop_loss = False
            log.debug(
                "[{}] StrategyStats Stop Loss check // Total net position: {} // {}".format(
                    self.strategy_id, self.stop_loss, self.net_spread_position)
            )

    def print_spread_positions(self, trade_spread_dict):
        log.debug(
            "[{}] StrategyStats Positions [BID//ASK] on Spread: {}//{}".format(
                self.strategy_id, trade_spread_dict['buy'].to_string(), trade_spread_dict['sell'].to_string())
        )

    def mtm_spread(self, direction, spread_avg_price):
        # Weight distribution of model against market
        w = self.w
        if direction == COMMON.Direction.buy:
            sign = 1.
        else:
            sign = -1.
        if self.is_adjusted_model_price and spread_avg_price is not None:
            spread_edge = sign * (self.eqb_price - self.model_price)
            mtm_price = sign * (self.model_price - spread_avg_price)
            price = w * spread_edge + (1 - w) * mtm_price
        else:
            price = None
        # Log outputs
        return price

    @staticmethod
    def pnl_push(pv_dict, trade_clip_pos):
        return PriceVol.cash_sub(pv_dict['sell'], pv_dict['buy'], trade_clip_pos)


def get_avg_market_price_depth_old(direction, market_view, depth, broker_id):
    if broker_id is None:
        only_tradable = False
    else:
        only_tradable = True
    if depth == 0:
        return market_view.current_front_price(direction, broker_id, only_tradable=only_tradable)
    else:
        price = 0
        vol = 0
        price_levels_list = market_view._summarize_price_level(direction, broker_id, only_tradable=only_tradable)
        for p, v in price_levels_list:
            if vol + v > depth:
                v = depth - vol
                price += p * v
                vol += v
                continue
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


def calc_bo(buy, sell):
    if buy is None or sell is None:
        return None
    else:
        return sell - buy
