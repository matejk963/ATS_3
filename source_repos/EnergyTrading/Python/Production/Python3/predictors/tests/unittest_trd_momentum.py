import pandas as pd
import numpy as np

from Production.Python3.predictors.trd_momentum import FeatureTrdMomentum

from Math.accumfeatures import DifferentialEMA as diffEMA_class_im
from Math.accumfeatures import DerivativeEMA as derEMA_class_im



@staticmethod
def feature_trd_momentum(data_pro, pma_list):
    """
    Calculates momentum features for trade prices using diff and differential for each period in pma_list.
    Returns a dictionary with the results, keys formatted as in other feature methods.
    """
    variable_dict = {}
    variable_dict['timestamp'] = list(data_pro.index)
    # Calculate momentum features
    for period in pma_list:
        nS = '{:02}'.format(period)
        feature = 'trd_momentum'
        variable_dict[feature + '_' + nS] = list(diff(data_pro['price'], period, log_bool=True).values)
        feature = 'trd_momentum_acc'
        variable_dict[feature + '_' + nS] = list(differential(data_pro['price'], period, 2, log_bool=True).values)
    return variable_dict

def diff(data_series, period, log_bool, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    vals = []
    if log_bool:
        value0 = np.log(value0)
    diffEMA_class = diffEMA_class_im(period, value0=value0)
    if log_bool:
        [vals.append(diffEMA_class.push(np.log(x))) for x in data_series.values]
    else:
        [vals.append(diffEMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


def differential(data_series, period, n, log_bool, value0=None):
    if value0 is None:
        value0 = data_series.bfill().iloc[0]
    gamma = .5
    vals = []
    if log_bool:
        value0 = np.log(value0)
    diffEMA_class = derEMA_class_im(period, n, gamma, value0=value0)
    if log_bool:
        [vals.append(diffEMA_class.push(np.log(x))) for x in data_series.values]
    else:
        [vals.append(diffEMA_class.push(x)) for x in data_series.values]
    return pd.Series(vals, data_series.index)


# Generate dummy test trade prices, dataframe (timestamp index, trade_price column)

# Create a time series index
time_index = pd.date_range(start='2023-01-01', periods=100, freq='T')
# Create a DataFrame with trade prices
trade_prices = pd.DataFrame({
    'timestamp': time_index,
    'price': np.random.rand(len(time_index)) * 100
})
trade_prices.set_index('timestamp', inplace=True)
# Initialize the FeatureTrdMomentum object
period = 10  # Example period
feature = FeatureTrdMomentum(period=period, value0=trade_prices['price'].iloc[0])

period_list = [10]

# Original code run
original_result = feature_trd_momentum(trade_prices, period_list)

# Run the feature_trd_momentum function with the dummy data
trd_momentum_list = []
trd_momentum_acc_list = []
trd_timestamps = []
for i, row in trade_prices.iterrows():
    value, value_acc = feature.push(row['price'])
    trd_momentum_list.append(value)
    trd_momentum_acc_list.append(value_acc)
    trd_timestamps.append(i)

original_df = pd.DataFrame(original_result)
test_df = pd.DataFrame({
    'timestamp': trd_timestamps,
    'trd_momentum_10': trd_momentum_list,
    'trd_momentum_acc_10': trd_momentum_acc_list
})

# Compare the results
assert original_df.equals(test_df), "The results from the original and test implementations do not match"