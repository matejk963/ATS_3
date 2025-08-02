# Forwards and Futures Arbitrage Strategy - Part 7 - Backtesting Arbitrage - Same product different instrument

In this example we add multiple parts to simulate a synthetic order registration on our strategy

The backtest simulates the entire process, from transferring the strategy to autotrader, to setting limits and registering synthetic orders and interacting with public orderbooks.

Thus it is very configurable, depending on the strategy or market conditions we would like to use.

## New Files/Folders

- **synth_ord_strategy/constants.py**
  - Constants to keep all sequence and item IDs used in this example
- **./backtesting_example_futures.py**
  - key backtesting start file
- **init_files_2022_08_23.zip**
  - initialisation files with relevant info on the sequences and items.
  - This is in general returned by the exchange after logging in.

## Backtest

### Strategy Definition 
We start with the file: **./backtesting_example_futures.py**

No comments are made here about imports

Start with creating a strategy definition
```python
    def setUp(self):
        self.strategy_id = "synth_ord_strategy"
        self.first_transfer = CETUTIL.utc_dt2ts(datetime.datetime(2022, 06, 27, 10, 0, 0))
        self.config = StrategyConfiguration(
            strategy_id=self.strategy_id,
            instrument_ids=[TTF_ICE, THE_ICE],  # can only place 2 instrument ids here
            strategies_folder=EXAMPLE_FOLDER,
            caption="Synth Strategy",
            package_name="synth_ord_strategy",
        )
```

All the instrument ids are imported as constants.

The package name is the directory name in which the custom_strategy.py is placed

We also remember a first transfer time.

### Setting up a simulator

The core of the backtest is the simulator.

It can be fed with messages which simulate manual interaction, such as:
- uploading strategies
- activating strategies
- registering synthetic
- setting limits

It will combine these messages, all of which have timestamps, with a given feed, and sort the messages correctly

The simulator we build will look like this.
```python
        sim = Simulator(
            [rest_msg_create, limits_setup_message, rest_msg_activate, rest_msg_so],
            json_feed=feed,
            use_persistence=False,
            trayport_init_directory="init_files_2022_08_23.zip",
            trayport_config={"venues": "EEX, ICE, EEXWD, EEX A, EEX F, IENX, IENX F",
                             "commodities": "Gas, Euro, Emissions",
                             "product_subscription_max_years": 5,
                             "product_subscription_shortterm_days": 0,
                             "product_subscription_midterm_count": 200,
                             "product_subscription_longterm_count": 100},
            simulated_exchanges=(COMMON.Exchange.trayport,),
            strategies_folder=EXAMPLE_FOLDER,
            timer_fast_timestep=3600,
            timer_timestep=3600,
        )
```
#### [rest_msg_create, limits_setup_message, rest_msg_activate, rest_msg_so]
We define here the messages we will send, we create a strategy, then set its limits regarding the sequences.
In the next steps we activate the strategy, and register a synthetic order

#### json_feed
In this example, we will just add a json feed.
Here a list of paths to time-sorted simulation feed files can also be given,
if instead of `json_feed` you use: `feed_paths=[feed_path]`

#### trayport_init_directory
Directory pointing to the initialization files

#### trayport_config
Configs which define what trayport products are allowed to be used by autotrader

#### simulated_exchanges
In our case we set only Trayport here

#### strategies_folder
To tell the simulator in which path relative the directory of the strategy can be found. 

#### timer_fast_timestep
Regular autotrader fast timer callbacks which activate the strategy will be called in this simulated time frequency.
Autotrader standard is 0.5s. This just checks whether other products need to be called.

#### timer_timestep
Regular autotrader timer callbacks will be called in this simulated time frequency.
Autotrader standard is 10s.

### Creating the strategy and limit messages

With these messages we simulate the calls to create strategy and set limits
- PUT `{{BaseURL}}/strategies/limits/{{algo_id}}`
- POST `{{BaseURL}}/strategies/{{algo_id}}`
- PUT `{{BaseURL}}/strategies/{{algo_id}}`

With the curresponding payloads.

```python
        # simulate POST to create strategy, referring to package, as defined in config
        rest_strat_msg_create = create_strategy_config_message(
            timestamp=self.first_transfer,
            strategy_id=self.strategy_id,
            strategy_configuration=self.config
        )

        self.config.update({"active": True})
        rest_strat_msg_activate = create_strategy_config_message(
            timestamp=self.first_transfer + 1,
            strategy_id=self.strategy_id,
            strategy_configuration=self.config
        )

        limits_payload = self._get_setup_limits()

        limits_setup_message = create_per_products_limit_message(timestamp=self.first_transfer + 2,
                                                                 strategy_id=self.strategy_id,
                                                                 limits_dict=limits_payload)
```

The limit payloads has this shape:
```python
    def _get_setup_limits(self):
        return {
            "limits_per_sequence": {"maximum_purchase_volume": {GAS_YEARS: 1000, POWER_YEARS: 1000, EUA_YEARS: 1000},
                                    "minimum_sales_price": {GAS_YEARS: 0, POWER_YEARS: 0, EUA_YEARS: 0},
                                    "maximum_sales_volume": {GAS_YEARS: 1000, POWER_YEARS: 1000, EUA_YEARS: 1000},
                                    "maximum_purchase_price": {GAS_YEARS: 1000, POWER_YEARS: 1000, EUA_YEARS: 1000}},
        }
```

### Simulate a synthetic order register message

Here we simulate a POST call to the endpoint `/synthetic/<strategy_id>/<product_id>/<synth_identifier>`

```python
        synthetic_orders_payload = get_synth_order_payload()
        so_register_msg = create_synthetic_order_message(
            timestamp=self.first_transfer,
            strategy_id=self.strategy_id,
            synthetic_orders_payload=synthetic_orders_payload
        )
```

The synthetic order payload is built based on the needed configuration for the custom synthetic order
```python
def get_synth_order_payload():
    return {
        # register stands for the POST
        "operation": COMMON.SyntheticOrderOperations.register,
        # product_id would usually be filled based on the url
        "product_id": GAS_PRODUCT_ID,

        "message_type": "synthetic_order",
        "synthetic_order_type": "ArbitrageOrder",
        "identifier": SLOT_NAME_LEAD,
        "configuration": {
            # slot_name must be equal to identifier.
            # try to run this with different slotname and identifier to see the difference
            "slot_name": SLOT_NAME_LEAD,

            # market area and slot_name are required parameters
            # synthetic order will only be able to place slots for this instrument
            # the localview in the synthetic order will be based on this instrument
            "market_area": TTF_ICE,

            # broker id, as defined in the base synthetic order class
            "broker_id": TTF_BROKER_ID,

            # now we add the additional synthetic order parameters
            # as defined in our custom ArbitrageOrder class
            "direction": COMMON.Direction.buy,
            "quantity": 10,
            "other_instrument_name": "view_the_ice",
        }
    }
```

The entry of ICE instrument:
```python
"other_instrument_name": "10002220",
```
is because in our synthetic order we will use
```python
other_view = additional_views.get_configured_view(self.other_instrument_name, localview.product_id)
```
This also allows commingled views.

If we want to use the instrument ID directly, rather then a configuration, then in the synthetic order we have to use:
```python
other_view = additional_views.get_view_for_instrument(self.other_instrument_name, localview.product_id)
```

Beware of the difference here!


### create artificial feed just to add public orders
```python
        feed = create_feed(self.first_transfer + 5)
```

### Final output after simulation

The public prices and synthetic order are setup in a way, that the synthetic order finds an arbitrage opportunity.

Run the code and investigate the printouts.
e.g.
```text
LEAD-SO-ACT [Public BUY/SELL]: A: 10002196: 10.0//200.0 --- B: 10002220: 400.0//None
```
For the sake of this workshop, we also added additional printouts in the core code,
to make internal activity more visible without fully running with logging
```text
('WORKSHOP-DEBUG: [SlotResponse] : placing slot on 10002196: B_10.0@200.00 [t=LEAD] [i=soi_LEAD/name_LEAD/class_ArbitrageOrder] [r=created (0i9twCJ3400)]', '10000308_21', '10002196')
```

Finally we can check that the lead synthetic order create a trade, and automate this check in the backtest:

```python
        traded_by_strategy = sim.get_net_traded_amounts_by_strategy(printout=False, only_traded=True)

        # check traded amount for a specific product
        traded = traded_by_strategy[self.strategy_id]
        self.assertEqual(traded[GAS_PRODUCT_ID]['net_volume'], 10)
        self.assertEqual(traded[GAS_PRODUCT_ID]['areas']['10002220']['net_volume'], 10)
```
