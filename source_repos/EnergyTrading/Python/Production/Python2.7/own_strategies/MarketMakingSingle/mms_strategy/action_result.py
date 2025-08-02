import autotrader_core.common as COMMON
from strategy_stats import get_avg_market_price_depth
tol = 1e-8


class ActionResult(object):
    value = None
    side = None

    def __init__(self, value, side, quantity):
        self.value = value
        self.quantity = quantity
        if side in [COMMON.Direction.buy, COMMON.Direction.sell]:
            self.side = side
        else:
            raise ValueError("Action order side parameter must be in COMMON.DIRECTION class, instead was: %s." % side)

    @property
    def is_none(self):
        if self.value is None:
            return True
        else:
            return False

    def invert(self):
        self.side = COMMON.Direction().invert(self.side)

    def __eq__(self, other):
        if isinstance(other, ActionResult):
            return self.value == other.value
        elif isinstance(other, (int, float)):
            return self.value == other
        else:
            raise ValueError("Action order equality parameter must be Action order class, instead was: %s." % other)

    def __ne__(self, other):
        if isinstance(other, ActionResult):
            return self.value != other.value
        elif isinstance(other, (int, float)):
            return self.value != other
        else:
            raise ValueError("Action order not equality parameter must be Action order class, instead was: %s." % other)

    def __lt__(self, other):
        if isinstance(other, ActionResult):
            return self.value < other.value
        elif isinstance(other, (int, float)):
            return self.value < other
        else:
            raise ValueError("Action order inequality parameter must be Action order class, instead was: %s." % other)

    def __le__(self, other):
        if isinstance(other, ActionResult):
            return self.value <= other.value
        elif isinstance(other, (int, float)):
            return self.value <= other
        else:
            raise ValueError("Action order inequality parameter must be Action order class, instead was: %s." % other)

    def __gt__(self, other):
        if isinstance(other, ActionResult):
            return self.value > other.value
        elif isinstance(other, (int, float)):
            return self.value > other
        else:
            raise ValueError("Action order inequality parameter must be Action order class, instead was: %s." % other)

    def __ge__(self, other):
        if isinstance(other, ActionResult):
            return self.value >= other.value
        elif isinstance(other, (int, float)):
            return self.value >= other
        else:
            raise ValueError("Action order inequality parameter must be Action order class, instead was: %s." % other)

    def __add__(self, other):
        if isinstance(other, ActionResult):
            return self.value + other.value
        elif isinstance(other, (int, float)):
            return self.value + other
        else:
            raise ValueError("Action order parameter must be Action order class or int/float, instead was: %s." % other)

    def __sub__(self, other):
        if isinstance(other, ActionResult):
            return self.value - other.value
        elif isinstance(other, (int, float)):
            return self.value - other
        else:
            raise ValueError("Action order parameter must be Action order class or int/float, instead was: %s." % other)

    def to_string(self):
        return "Value: %s, Direction %s, Quantity %s: " % (self.value, self.side, self.quantity)
