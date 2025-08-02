# Forwards and Futures Arbitrage Strategy - Part 9 - Multiple Product

In this example we are going to write a strategy that does arbitrage against different product: Gas vs. Electricity.

## Final Notes at the end of the workshop on various topics

- slot packing
  - strategies on 1 child run in sequence.
  - only when all strategies finished the place_slots, will the slots be sent out
  - autotrader assigns strategies to children randomly
  - autotrader calls strategies in random but deterministic order
  - assign exchange per child to avoid memory duplication
- Rest Calls
  - can have a return value
  - 504 Rest API timeout happens if response takes longer than 30sec
  - Rest writes request to MongoDB where autotrader picks it up. Rest then waits for response appearing in MongoDB up until timeout time
- Rest calls by strategy?
  - do not call external sources from the strategy!
  - in future autotrader will be sandboxed, and cannot interact with the outside world from inside
- PushAPI
  - work in progress, currently done as internal tool for Joule
  - made for F&F, synthetic order updates
- Persistent Parameters
  - Configurations added via e.g. template are persisted in MongoDB and reloaded after restart
  - This is true for strategy configs and also synthetic order configs
  - random values, if needed to be reproducible, use seeds based e.g. on hashes of product_id and configurations
- Simulation vs Backtest
  - Simulation (forward test / paper trading): Prod environment, with read only access
    - limited interaction, you cannot trade the same public order twice
    - exchange simulator keep memory about orderbooks, and changes them according to interaction
  - Backtest: Feed generated / from recording
    - Test PnL, financial performance
    - Test compliance with Code, should not crash!
    - Check all setup steps, rest and config calls
