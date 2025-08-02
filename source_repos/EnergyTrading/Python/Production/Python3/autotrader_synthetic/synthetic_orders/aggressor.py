from __future__ import absolute_import
import numbers
import six
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

import autotrader_lib.common as COMMON
import autotrader_lib.py2_funcs as PY2LIB
import autotrader_synthetic.config_util as CONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

LOGGER_NAME = "synthetic_orders.aggressor"
log = FLOG.getLogger(LOGGER_NAME)


class Aggressor(SYB.SyntheticOrderBase):

    position = CONF.ConfigOptionDescriptor("position", numbers.Number, "Total position to buy or sell", required=True)
    slot_size = CONF.ConfigOptionDescriptor("slot_size", numbers.Number, "Size of the slot", required=True)

    def __init__(self, *args, **kwargs):
        super(Aggressor, self).__init__(*args, **kwargs)

    def act(self, localview, additional_views, timestamp):
        remaining_volume = self.position - self.traded_volume(localview)
        if remaining_volume == 0:
            self.remove(status_text="Remaining volume is 0")
        direction = COMMON.Direction.buy if remaining_volume > 0 else COMMON.Direction.sell
        other_direction = COMMON.Direction.sell if remaining_volume > 0 else COMMON.Direction.buy
        log.debug("Remaining volume: %s", remaining_volume)

        target_front_volume = localview.current_front_volume(other_direction)
        target_front_price = localview.current_front_price(other_direction)

        volume = PY2LIB.py2min([remaining_volume, target_front_volume, self.slot_size])
        log.debug("Price %s, volume %s", target_front_price, volume)

        return self.create_slot(direction, quantity=volume, price=target_front_price)


if __name__ == "__main__":
    raise RuntimeError("This module should not be directly executed")  # pragma: no cover
