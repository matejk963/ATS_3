# Forwards and Futures Arbitrage Strategy - Part 5 - Additional views

## What are additional views?
Additional views are used by synthetic orders in order to gather information on different market areas (like price, spread etc...).

In order to use additional view functionality one or more custom AdditionalViewType field should be defined in the strategy template like the following:
```python
custom_named_additional_view = TEMPLATE.StrategyConfigField("Additional view",
                                                            "An additional view defined as an example",
                                                            TEMPLATE.AdditionalViewType, mandatory="never")
```

In the synthetic order before the `act()` function, the other instrument name for the view should be defined as a parameter when creating the SO 
(in our case if we would use this strategy the name of this should be "custom_named_additional_view")
```python
    other_instrument_name = SYNCONF.SyntheticOrderConfigField(
        caption="other_instrument_name",
        description="Name of the other additional view, as used in the strategy template",
        expected_type=PKG_CONF.InstrumentIdType,
        mandatory=True
    )
```

With this defined, when receiving the `additional_view` parameter in the `act()` function of synthetic order, it will 
already contain the view (or views) which can be used the same way as local views.
```python
    def act(self, localview, additional_views, timestamp):

        other_view = additional_views.get_configured_view(self.other_instrument_name, localview.product_id)

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)
```
Based on this information we can implement our own logic for the synthetic order to be useful for an arbitrage
```python
        if other_sell is not None and local_buy is not None:
            # local buy: 20
            # other sell: 60
            # spread buy: 40
            # if we sell in local, and buy in other, we lose 40
            spread_buy = other_sell - local_buy
        if other_buy is not None and local_sell is not None:
            # local sell: 20
            # other buy: 60
            # spread sell: 40
            # if we buy in local, and sell in other, we profit 40
            spread_sell = other_buy - local_sell

        if spread_buy < 0:
            return self.create_slot(COMMON.Direction.sell, QUANTITY_TICK_SIZE, local_buy)
        elif spread_sell > 0:
            return self.create_slot(COMMON.Direction.buy, QUANTITY_TICK_SIZE, local_sell)
        else:
            return self.remove()
```