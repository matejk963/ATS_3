import logging
import time
import copy
import autotrader_synthetic.factory_view as FV
import autotrader_core.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC
from own_tools.price_class import PriceVol
from own_tools.instrument_key import InstrumentKey
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
    bool_dict = {'manage_pos': False,'take_profit': False, 'stop_loss': False,'hard_stop_loss': False}
    balancing_dict={}
    pnl_dict = {}
    slot_dict={}
    lead_trade_list=[]
    action=None
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
        return ['strategy_id', 'caption', 'instrument_list','trade_leg_dict', 'trade_leg_dict_for_mtm', 'trade_spread_dict', 'bool_dict','balancing_dict', 'pnl_dict', 'slot_dict', 'lead_trade_list', 'action', 'ql', 'timestamp']

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
    def price_vol_trade_leg_dict_for_mtm(self):
        return {k: {s: PriceVol.from_dict(v) for s, v in d.items()} for k, d in self.trade_leg_dict_for_mtm.items()}

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

    @property
    def mtm_dict_per_instrument(self):
        trade_leg_dict_for_mtm = self.price_vol_trade_leg_dict_for_mtm
        return {k: v['buy'].quantity*((self.price_leg_dict[k]['buy']/2.0+self.price_leg_dict[k]['sell']/2.0)-v['buy'].price) + v['sell'].quantity*(v['sell'].price - (self.price_leg_dict[k]['buy']/2.0+self.price_leg_dict[k]['sell']/2.0)) for k, v in trade_leg_dict_for_mtm.items()}

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
        self.bool_dict = {'manage_pos': False, 'take_profit': False,
                     'stop_loss': False, 'hard_stop_loss': False}

        self.balancing_dict={inst_key: False for inst_key in instrument_list}
        self.slot_dict = {}
        self.lead_trade_list = []

        self.trade_leg_dict = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_leg_dict_for_mtm = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                               for k in instrument_list}
        self.trade_spread_dict = {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}

        self.price_leg_dict = {k: {s: None for s in ['buy', 'sell']} for k in instrument_list}


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
        self.trade_leg_dict.update({k: {s: v.to_dict() for s, v in d.items()} for k, d in trade_leg_dict.items()})
        self.trade_leg_dict_for_mtm.update({k: {s: v.to_dict() for s, v in d.items()} for k, d in trade_leg_dict_for_mtm.items()})
        self.trade_spread_dict.update({s: v.to_dict() for s, v in trade_spread_dict.items()})

        if sum(self.net_position.values())==0.0:
            self.pnl_calc_and_push()
            #reset the trade_leg_dict_for_mtm calculator
            self.trade_leg_dict_for_mtm = {k: {s: PriceVol(0., 0.).to_dict() for s in ['buy', 'sell']}
                                            for k in instrument_list}

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
        self.mtm=sum(mtm_dict_per_instrument.values())

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


    def increment_lead_trade_list(self, trade):
        record={"price": trade.price, "quantity": trade.quantity, "timestamp": trade.execution_time}
        self.lead_trade_list.append(record)


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

        self.price_leg_dict[instrument_key.key][direction] = price
        self.timestamp = time.time()


    def calculate_action(self, max_secs_between_trades, cluster_trade_num_threshold, min_price_movement):
        trades = copy.deepcopy(self.lead_trade_list)
        ordered_trades = sorted(trades, key=lambda x: x['timestamp'])

        # Extract the last trades according to cluster_trade_num_threshold parameter
        last_trades = ordered_trades[-cluster_trade_num_threshold:]

        # Calculate the time differences between consecutive trades
        time_differences = [t2['timestamp'] - t1['timestamp'] for t1, t2 in zip(last_trades, last_trades[1:])]

        # Find the maximum time difference
        max_time_difference = max(time_differences)

        # Find the maximum and minimum prices
        prices=[x['price'] for x in last_trades]
        max_price = max(prices)
        min_price = min(prices)
        median_price = np.median(prices)
        price_movement = max_price - min_price

        #calculate the action/direction to take based on the values calculated
        action=0
        if max_time_difference<max_secs_between_trades and price_movement > min_price_movement and median_price>min_price and median_price<max_price:
            if prices.index(min_price)<prices.index(max_price):
                action=1
            else:
                action=-1

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


