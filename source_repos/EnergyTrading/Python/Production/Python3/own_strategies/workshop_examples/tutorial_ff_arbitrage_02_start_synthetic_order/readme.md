# Forwards and Futures Arbitrage Strategy - Part 2

## Create a Synthetic Order

Create a file **so_arbitrage_lead.py**.


Add the basic imports we will need:
```python
import logging
import numbers

import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
import autotrader_lib.package_config_fields as PKG_CONF
```

To add custom configuration fields to the synthetic order, we will use `SYNCONF.SyntheticOrderConfigField`,
so we import `import autotrader_synthetic.config_util as SYNCONF`

Our synthetic order comes from the base synthetic order, and we declare it with: 
`class ArbitrageOrder(SYB.SyntheticOrderBase)`,
so we import `import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB`


In the synthetic order, we define the configuration parameters as class variables:
```python
    direction = SYNCONF.SyntheticOrderConfigField(caption="direction",
                                                  description="The side of the order_book: buy or sell",
                                                  expected_type=PKG_CONF.Enum(allowed_values=["buy", "sell"]),
                                                  mandatory=True)

    quantity = SYNCONF.SyntheticOrderConfigField(caption="quantity",
                                                 description="The maximum quantity that is allowed to be traded",
                                                 expected_type=float,
                                                 mandatory=True)
```
- `direction`: can only by `"buy"` or `"sell"`
- `quantity`: must be a `float` or an `int`

Finally, we only need to define the **act** method.
For the quantity and price, we get the currently traded position, and the price, depending on the direction.
In the last step, all infos are combined and then the slot is returned
```python
    def act(self, localview, additional_views, timestamp):

        if self.direction == "buy":
            net_traded = localview.traded_volume_buy(self.slot_name)
        else:
            net_traded = localview.traded_volume_sell(self.slot_name)

        qty = max(0., net_traded)
        price = localview.current_front_price(self.direction, self.broker_id)

        return self.create_slot(self.direction, qty, price)
```
Autotrader will collect the slots of all strategies triggered by the same event, 
and after some limit management guards and internal market checks, autotrader will place the valid orders on the market.

`localview.traded_volume_buy(self.slot_name)` will return the net traded quantity on the specified product and area of
the current strategy, based on the placement slot name.

`localview.current_front_price(self.direction, self.broker_id)`
returns the currently best price based on the best bid or ask, dependent on the direction



The complete file looks like this:
```python
import logging

import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
import autotrader_lib.package_config_fields as PKG_CONF

log = logging.getLogger("arbitrage.arbitrage_order")


class ArbitrageOrder(SYB.SyntheticOrderBase):
    direction = SYNCONF.SyntheticOrderConfigField(caption="direction",
                                                  description="The side of the order_book: buy or sell",
                                                  expected_type=PKG_CONF.Enum(allowed_values=["buy", "sell"]),
                                                  mandatory=True)

    quantity = SYNCONF.SyntheticOrderConfigField(caption="quantity",
                                                 description="The maximum quantity that is allowed to be traded",
                                                 expected_type=float,
                                                 mandatory=True)

    def act(self, localview, additional_views, timestamp):

        if self.direction == "buy":
            net_traded = localview.traded_volume_buy(self.slot_name)
        else:
            net_traded = localview.traded_volume_sell(self.slot_name)

        qty = max(0., net_traded)
        price = localview.current_front_price(self.direction, self.broker_id)

        return self.create_slot(self.direction, qty, price)

```

## Adding the template file for validation

In the **__init__.py** we add a reference to the new template class.

Template classes have a hierarchy, with the default being the `BaseTemplate` class.

By inheriting, we can add more fields to the `BaseTemplate`.

```python
import custom_strategy
import so_strategy_template

template_class = so_strategy_template.StrategyTemplate
```

The basic template can be defined like this:

```python
"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    pass
```

For Trayport Forwards and Futures, we need a broker_id, which is also defined in the
`TrayportBaseTemplate`.
This will add the fields
- broker_id
- trading_account

To also include MifidFields, you can use `MifidTemplate`.
This provides the following fields:
- mifid_trading_capacity
- mifid_decision_maker
- mifid_execution_maker
- mifid_liquidity_provision
- mifid_dea
- mifid_dea_client_id
- mifid_derivative_indicator

## Visibility in Joule

In the autotrader dashboard, when going to the settings of the strategy,
the additional settings will be visible under the tab **"Additional Settings"**.
This is next to the tab **"General Settings "**