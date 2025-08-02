# Forwards and Futures Arbitrage Strategy - Part 8 - Backtesting Arbitrgae - Lifting the Traded amounts on the other leg

In this example we add multiple parts to simulate a synthetic order registration on our strategy

The backtest simulates the entire process, from transferring the strategy to autotrader, to setting limits and registering synthetic orders and interacting with public order books.

Thus it is very configurable, depending on the strategy or market conditions we would like to use.

## New Files/Folders
- **so_arbitrage_lift.py**
  - LiftOrder which follows the leading arbitrage order and closes position

```python
    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder, "LiftOrder": so_arbitrage_lift.LiftOrder}
```

## Lift Order

All the lift order needs to do, is to compare its own traded quantity with the leads traded quantity,
and close the gap if there is any.

```python

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_configured_view(self.other_instrument_name, localview.product_id)
        open_position, price = self.get_open_position(localview, other_view)

        if open_position > 0:
            return self.create_slot(self.direction, open_position, price, info="lift")
        else:
            return self.remove()
```

We can check both traded quantities with:

```python
    def get_open_position(self, localview, other_view):

        if self.direction == COMMON.Direction.buy:
            own_traded_quantity = localview.traded_volume_buy(self.slot_name)
            lead_traded_quantity = other_view.traded_volume_sell(self.other_slot_name)
            price = localview.current_front_price(COMMON.Direction.sell)
        else:
            own_traded_quantity = localview.traded_volume_sell(self.slot_name)
            lead_traded_quantity = other_view.traded_volume_buy(self.other_slot_name)
            price = localview.current_front_price(COMMON.Direction.buy)
            
        return min(lead_traded_quantity - own_traded_quantity, 0), price
```

And this is all for a simple version.