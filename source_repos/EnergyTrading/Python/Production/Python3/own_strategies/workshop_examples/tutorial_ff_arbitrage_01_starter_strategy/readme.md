# Forwards and Futures Arbitrage Strategy - Part 1

## Plan

1) Basics
   1) Create Empty Strategy
   2) Add Simple placing Synthetic Order
   3) Place according to market - unittest
   4) Task: Add Unittests
   5) Test system, upload and manually test strategy
2) Additional Views
   6) Add Additional Views to simple placing Synthetic Order & Unittests
   7) First backtest
   8) Add Lift Order
   9) Add tests

## SO strategy base class contents

Exchange event callbacks are covered by the base strategy, e.g.:
- on_strategy_configuration_update

Exchange Event Methods:
- custom_on_order_book_update
- custom_on_trade_update
- custom_on_public_trade_update
- custom_on_products_update

Internally triggered updates:
- custom_on_products_queue
- custom_on_timer

Strategy action methods:
- custom_act
- custom_act_for_product

Covered Synthetic Order methods
- on_synthetic_order
  - general function for all synthetic order operations
- on_synthetic_order_register
  - `@app.post("/synthetic/<strategy_id>/<product_id>/<synth_identifier>")`
- on_synthetic_order_modify
  - `@app.put("/synthetic/<strategy_id>/<product_id>/<synth_identifier>")`
- on_synthetic_order_delete
  - `@app.delete("/synthetic/<strategy_id>/<product_id>/<synth_identifier>")`

Example call with payload (with placeholders used in postman):
```json
{
    "message_type": "synthetic_order",
    "synthetic_order_type": "ArbitrageOrder",
    "configuration": {
        "market_area": "{{instrument_id}}",
        "broker_id": "{{broker_id}}",
        "slot_name": "test_so",
        "direction": "buy",
        "quantity": 20.0
    }
}

```

## Creation of an empty Strategy

Import base module for synthetic order strategy:
```python
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
```

Import logging module, to give strategy logs their distinct logger
```python
import logging

log = logging.getLogger("autotrader.tutorial_synthetic_order_01")
```


Setup an empty strategy, with the most important callback.
```python
class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    @classmethod
    def get_available_synthetic_order_types(cls):
        pass
```

### default_payload
A helper object which can be applied to any synthetic order creation/update within this strategy.
Can be omitted in simple cases (here it's only included for presentation purposes).

### on_strategy_configuration_update
This callback is called when we interact with the strategy via REST-Api and send a new configuration.
The endpoint is: `/strategies/<strategy_id>`
What is set there as a put, will be saved in Mongo as `StrategyConfigurationObject`, 
and then loaded to autotrader and forwarded to the strategy via `on_strategy_configuration_update`.

### get_available_synthetic_order_types
This will be a string to Synthetic Order Class mapping,
which allows us to reference synthetic orders also via REST request payload.


### Setup limits

Handled by base strategy:
- update_strategy_limits
  - `@app.put("/strategies/limits/<strategy_id>")

Example Postman: PUT `{{BaseURL}}/strategies/limits/{{algo_id}}`
```json
{
    "limits_per_sequence": 
    {   "maximum_purchase_price": {"10000302": 250, "10000106": 100},
        "minimum_sales_price": {"10000302": 2, "10000106": 2},
        "maximum_purchase_volume": {"10000302": 200, "10000106": 20},
        "maximum_sales_volume": {"10000302": 200, "10000106": 20}
    }
}
```