import autotrader_synthetic.factory_view as FV
import autotrader_core.common as COMMON
from autotrader_lib.package_config_fields import AdditionalTypeABC


class StrategyStats(AdditionalTypeABC):
    strategy_id = ""
    trade_leg_dict = {}
    price_leg_dict = {}
    balancing = False

    def __init__(self, instrument_list=None, strategy_id=''):
        if instrument_list is None:
            instrument_list = []
        self.strategy_id = strategy_id
        self.update_instruments(instrument_list)

    @property
    def attributes_list(self):
        return ['strategy_id', 'trade_leg_dict', 'price_leg_dict', 'balancing']

    @property
    def net_position(self):
        return {k: v['buy'] - v['sell'] for k, v in self.trade_leg_dict.items()}

    @property
    def total_net_position(self):
        return sum([v for v in self.net_position.values()])

    @classmethod
    def validate_and_cast_to_mongo(cls, value):
        return value.to_dict()

    @classmethod
    def from_dict(cls, value_dict):
        new_cls = StrategyStats()
        for key in new_cls.attributes_list:
            setattr(new_cls, key, value_dict[key])
        return new_cls

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}

    def update_instruments(self, instrument_list):
        # Position dictionary
        self.trade_leg_dict = {k: {s: 0 for s in ['buy', 'sell']} for k in instrument_list}
        # PriceVol dictionary
        self.price_leg_dict = {k: {s: None for s in ['buy', 'sell']} for k in instrument_list}

    def update_strategy_position(self, instrument_key, quantity, side):
        if side == COMMON.Direction.sell:
            self.trade_leg_dict[instrument_key]['sell'] += quantity
        else:
            self.trade_leg_dict[instrument_key]['buy'] += quantity
        self.check_balancing()

    def update_strategy_prices(self, instrument_key, direction, products, broker_id):
        additional_views = FV.ViewFactory(products=products, strategy_id=self.strategy_id)
        market_view = additional_views.get_view_for_instrument(
            instrument_key.instrument_id,
            instrument_key.product_id
        )
        self.price_leg_dict[instrument_key.key][direction] = get_avg_market_price_depth(direction, market_view,
                                                                                        0, broker_id)

    def check_balancing(self):
        if abs(self.total_net_position) == 0:
            self.balancing = False


def get_avg_market_price_depth(direction, market_view, depth, broker_id):
    if depth == 0:
        return market_view.current_front_price(direction, broker_id)
    else:
        price = 0
        vol = 0
        price_levels_list = market_view._summarize_price_level(direction, broker_id)
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
            return price
