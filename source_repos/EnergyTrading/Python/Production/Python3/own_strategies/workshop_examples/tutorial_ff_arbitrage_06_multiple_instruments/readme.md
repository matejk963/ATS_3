# Forwards and Futures Arbitrage Strategy - Part 5 - Additional views - Multiple instruments

## Add additional parameters in strategy template, to define api for configuration via REST
In the template we add the possibility to define additional views
```python
    view_italy = StrategyConfigField("Additional View", "View on italy", AdditionalViewType)
    view_ncg = StrategyConfigField("Additional View", "View on ncg", AdditionalViewType)
    view_ttf = StrategyConfigField("Additional View", "View on ttf", AdditionalViewType)
```

These views have to be defined by a list of instrument ids (string), 
which define which instruments should be taken into account when calculating order_book information. 
