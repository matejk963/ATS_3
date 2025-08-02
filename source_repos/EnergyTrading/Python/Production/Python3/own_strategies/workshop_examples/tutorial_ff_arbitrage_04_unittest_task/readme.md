# Forwards and Futures Arbitrage Strategy - Part 4 - Create Unittests

Create unittest for the cases that:
1) position Buy 100, already traded Buy 100
   1) Check that no more quantity is placed
   2) Call testmethod: `test_fully_traded`
2) position Buy 100, already traded Buy 50
   1) Check that synthetic order still places 50
   2) Call testmethod: `test_partially_traded`
3) position Sell 100, nothing traded yet, empty orderbooks
   1) Create your own test!

For solutions check the unittest file: **strategy_unit_test.py**
