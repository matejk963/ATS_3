import pickle
import pandas as pd
import numpy as np
from Strategies.Sparse_momentum.ob_attributes import TR_attributes
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import roc_auc_score, classification_report
from Math.tickclass import tick_class
from sklearn.preprocessing import StandardScaler


class DataClass:
    def __init__(self, scale_bool):
        self.scale_bool = scale_bool
        self.__scale_params_dict = {}

    @staticmethod
    def split_data(df_data, date_range_dict, n_tests, y_col, x_cols):
        date_s = {k: (v[-n_tests], v[-1]) for k, v in date_range_dict.items()}
        out_dict = {'train': {}, 'tests': {}, 'keys': []}
        y_ser = df_data[y_col]
        X_df = df_data[x_cols]
        for d, date_tuple in date_s.items():
            date_test, date_end = date_tuple
            date_end += pd.Timedelta(hours=24)
            date = date_test
            y_train, y_tests = y_ser.loc[d:date_test], y_ser.loc[date_test:date_end]
            X_train, X_tests = X_df.loc[d:date_test, :], X_df.loc[date_test:date_end, :]
            out_dict['train'][date] = {'y': y_train.values, 'X': X_train.values, 'ts': X_train.index}
            out_dict['tests'][date] = {'y': y_tests.values, 'X': X_tests.values, 'ts': X_tests.index}
            out_dict['keys'].append(date)
        return out_dict

    def scale_data(self, data_dict):
        if not self.scale_bool:
            return data_dict
        scaled_dict = {'keys': [], 'train': {}, 'tests': {}}
        for d in data_dict['keys']:
            X_train = data_dict['train'][d]['X']
            X_tests = data_dict['tests'][d]['X']
            y_train = data_dict['train'][d]['y']
            y_tests = data_dict['tests'][d]['y']
            ts_train = data_dict['train'][d]['ts']
            ts_tests = data_dict['tests'][d]['ts']

            X_train_s, X_tests_s = self.scale_data_reg(X_train, X_tests, d)

            scaled_dict['train'][d] = {'y': y_train, 'X': X_train_s, 'ts': ts_train}
            scaled_dict['tests'][d] = {'y': y_tests, 'X': X_tests_s, 'ts': ts_tests}
            scaled_dict['keys'].append(d)
        return scaled_dict

    def scale_data_reg(self, X_train, X_tests, d):
        scaler_x = StandardScaler()
        X_train_s = scaler_x.fit_transform(X_train)
        X_tests_s = scaler_x.transform(X_tests)
        self.__scale_params_dict[d] = scaler_x
        return X_train_s, X_tests_s


class TradeProbabilityEstimator:
    """
    Estimate the probability of a trade hitting your quote
    based on how close the fair price is to the actual quote.
    """
    def __init__(self, fair_price_series: pd.DataFrame,
                 quotes: pd.DataFrame,
                 trades: pd.DataFrame,
                 features: pd.DataFrame = pd.DataFrame([]),
                 window_secs: float = 1.0,
                 time_bool: bool = True):
        """
        Parameters:
        - fair_price_series: pd.Series indexed by timestamp
        - quotes: pd.DataFrame with columns [timestamp, b_price, a_price]
        - trades: pd.DataFrame with columns [timestamp, price]
        - window_secs: float, time window after each quote to check for a trade
        """
        self.fair_price = fair_price_series.copy()
        self.quotes = quotes.copy()
        self.trades = trades.copy()
        self.features = features.copy()
        self.data = None
        self.time_bool = time_bool
        self.window = pd.Timedelta(seconds=window_secs)
        self.window_num = window_secs
        self.model_dict = {'bid': {}, 'ask': {}}

    def calc_tick_index_pd(self, mid_price, tick=0.01):
        # Group by date to handle each day separately
        grouped = mid_price.groupby(mid_price.index.date)
        df_out = pd.DataFrame()
        idx_start, csum_start = 0, 0
        for day, mid_price_day in grouped:
            # Calculate tick index for each group
            idx_list, csum_list, index = self.calc_tick_index_single(mid_price_day, self.window_num, tick,
                                                                     idx_start, csum_start)
            df_aux = pd.DataFrame({'idx': idx_list, 'csum': csum_list}, index=index)
            idx_start = idx_list[-1] + 1 if idx_list else idx_start
            csum_start = csum_list[-1] + self.window_num * 2 if csum_list else csum_start
            # Concatenate results
            if df_out.empty:
                df_out = df_aux
            else:
                df_out = pd.concat([df_out, df_aux], axis=0)
        return df_out['idx'].values, df_out['csum'].values, mid_price.index

    @staticmethod
    def calc_tick_index_single(mid_price, tick_val, tick, idx_start, csum_start):
        # Calculate tick index for a single series
        t_class = tick_class(tick, tick_val)
        mid_list = mid_price.values
        [t_class(x) for x in mid_list]
        idx_list = [i + idx_start for i in t_class.idx_list]
        csum_list = [i + csum_start for i in t_class.csum_list]
        return idx_list, csum_list, mid_price.index

    def prepare_features(self, train_size, test_size) -> dict:
        # Calculate side of trades
        mid_price = 0.5 * (self.quotes['b_price'] + self.quotes['a_price'])
        self.trades['side'] = np.where(self.trades['price'] >= mid_price, 1, -1)
        # Align fair price to quotes
        self.data = self.quotes.copy()
        if self.time_bool:
            self.data['timestamp'] = self.data.index
            self.trades['timestamp'] = self.data.index
        else:
            _, csum, _ = self.calc_tick_index_pd(mid_price, 0.01)
            self.data['timestamp'] = csum
            self.trades['timestamp'] = csum
        self.data['fair_price'] = self.fair_price
        # Compute distance between fair price and quoted price
        ba_spread = (self.data['a_price'] - self.data['b_price']).replace(0, 0.01)
        self.data['distance_bid'] = -(self.data['b_price'] - self.data['fair_price'])
        self.data['distance_ask'] = (self.data['a_price'] - self.data['fair_price'])
        # Label whether a trade occurred at the same price and side within window
        labels_bid, labels_ask = [], []
        for idx, row in self.data.iterrows():
            t0 = row['timestamp']
            if self.time_bool:
                t1 = t0 + self.window
                t0_ = t0
            else:
                t1 = t0 + self.window_num
                t0_ = row.name
            mask = (self.trades['timestamp'] >= t0) & (self.trades['timestamp'] <= t1)
            # Mark bid & ask price
            bid, ask = self.data.loc[t0_, ['b_price', 'a_price']].values
            # if any trade price equals the quote
            occured_bid = (self.trades.loc[mask, 'price'] >= ask).any()
            occured_ask = (self.trades.loc[mask, 'price'] <= bid).any()
            labels_bid.append(int(occured_bid))
            labels_ask.append(int(occured_ask))
        self.data['label_bid'] = labels_bid
        self.data['label_ask'] = labels_ask
        # Features: distance, side encoded
        df = self.data[['distance_bid', 'distance_ask', 'label_bid', 'label_ask']].copy()
        if self.features.empty:
            pass
        else:
            df = pd.concat([df, self.features], axis=1)

        # Gini
        x_cols = [x for x in df.columns if 'label_' not in x]
        self.gini_dict = {k: [] for k in ['label_bid', 'label_ask']}
        for y_col in ['label_bid', 'label_ask']:
            df_y = df.loc[:, [y_col]]
            df_X = df.loc[:, x_cols]
            ginis = {}
            for col in df_X.columns:
                xj = df_X.loc[:, col].values.reshape(-1, 1)  # single feature
                yj = df_y.values
            
                # If X is constant, AUC is undefined → skip or set Gini=0
                if np.unique(xj).size < 2:
                    ginis[col] = 0.0
                    continue
            
                # Compute AUC of a 'model' that uses only X_j as predictor
                # (this is equivalent to ranking by X_j itself)
                auc = roc_auc_score(yj, xj)
                gini = 2 * auc - 1
                ginis[col] = gini

            # Convert to a sorted Series for easy viewing
            self.gini_dict[y_col] = pd.Series(ginis).sort_values(ascending=False)

        # Prepare train and test sets
        total_size = train_size + test_size
         # Split data into training and testing sets
        sample_dates = [x for x in sorted(set(df.index.date))]
        date_range_dict = {sample_dates[i]: list(sample_dates[i:i + total_size])
                           for i in range(len(sample_dates) - total_size + 1)}
        ### Data Class
        scale_bool = False
        data_class = DataClass(scale_bool=scale_bool)
        split_dict = {k: data_class.split_data(df, date_range_dict, test_size, y_col='label_' + k, x_cols=x_cols)
                      for k in ['bid', 'ask']}
        scaled_dict = {k: data_class.scale_data(v) for k, v in split_dict.items()}
        return scaled_dict

    def train(self, train_size: int = 10, test_size: int = 1) -> dict:
        # Prepare data
        data_dict = self.prepare_features(train_size, test_size)
        # Train models for bid and ask sides
        out_dict = {k: {'auc': None, 'report': None} for k in ['bid', 'ask']}
        for side in ['bid', 'ask']:
            y_tests_all, proba_list_all, pred_list_all = [], [], []
            for date in data_dict[side]['keys']:
                X_train, y_train = data_dict[side]['train'][date]['X'], data_dict[side]['train'][date]['y']
                X_tests, y_tests = data_dict[side]['tests'][date]['X'], data_dict[side]['tests'][date]['y']
                # Train model with cross-validated regularization
            model = LogisticRegressionCV(
                Cs=10,            # Number of regularization strengths to try
                cv=5,             # 5-fold cross-validation
                penalty='l2',     # L2 regularization
                solver='lbfgs',   # Suitable for L2
                scoring='roc_auc',
                max_iter=1000,
                n_jobs=-1,
                refit=True
            )
            model.fit(X_train, y_train)
            preds = model.predict_proba(X_tests)[:, 1]
            proba_list_all.extend(preds)
            pred_list_all.extend(model.predict(X_tests))
            y_tests_all.extend(y_tests)
            self.model_dict[side][date] = model
            out_dict[side]['auc'] = roc_auc_score(y_tests_all, proba_list_all)
            out_dict[side]['report'] = classification_report(y_tests_all, pred_list_all)
        return out_dict

    def predict(self, distances: np.ndarray, sides: np.ndarray) -> np.ndarray:
        """
        Predict trade probability for new quotes.
        distances: array of distance values
        sides: array of side strings ('bid' or 'ask')
        Returns: array of probabilities
        """
        df_new = pd.DataFrame({'distance': distances, 'side': sides})
        df_new = pd.get_dummies(df_new, columns=['side'], drop_first=True)
        # Ensure both columns exist
        for col in ['side_bid']:
            if col not in df_new:
                df_new[col] = 0
        return self.model.predict_proba(df_new)[:, 1]


### LOAD DATA ###
dump_path = 's:\Algo\Database\Model Data\martin_model\lle_data_dq1_ens_20250301_20250623.pkl'
with open(dump_path, 'rb') as f:
    loaded_data = pickle.load(f)

mkt = 'deq1'

# Fair price
df_fair_price = loaded_data['db_data'].loc[:, ['price_hat_ens']]
df_fair_price = df_fair_price.reset_index(level='tradeid', drop=True).dropna()
df_fair_price.columns = ['price']
df_fair_price.index.name = 'timestamp'
timestamp = df_fair_price.index

# Traded price
df_price = loaded_data['data_p_'].loc[:, [mkt]].loc[timestamp]
df_price.columns = ['price']
df_price.index.name = 'timestamp'

# Bid ask
df_ba = loaded_data['ba_data_dict'][mkt].loc[timestamp]
df_ba.index.name = 'timestamp'

# Aux features
tr_att_list = ['lamb_tr', 'trd_gap']
trAtt = TR_attributes(tr_att_list)

df_tr = loaded_data['data_p_'].loc[:, [mkt]].dropna()
df_tr.columns = ['trd_price']
df_tr.index.name = 'timestamp'

# DTI
lookback_list = ['180s', '300s', '420s']
df_dti = pd.DataFrame([])
for lookback in lookback_list:
    df_dti_aux = trAtt.calculate_dti_time(df_tr, '300s').reindex(timestamp).ffill()
    if df_dti.empty:
        df_dti = df_dti_aux
    else:
        df_dti = pd.concat([df_dti, df_dti_aux], axis=1)

# VPIN
df_data_vpin = pd.concat([loaded_data['data_p_'][mkt], loaded_data['data_v_'][mkt]], axis=1).dropna()
df_data_vpin.columns = ['price', 'volume']
df_data_vpin.index.name = 'timestamp'
 
### VPIN ###
vol_bucket_dict = {'dem1': 20, 'dem2': 13, 'deq1': 12, 'dey1': 13}
bucket_n_list = [80, 100, 150]
df_vpin = pd.DataFrame()
for n_buckets in bucket_n_list:
    df_aux = trAtt.vpin(df_data_vpin, vol_bucket_dict[mkt], n_buckets, n_days=3)
    df_aux.columns = ['vpin_' + str(n_buckets)]
    if df_vpin.empty:
        df_vpin = df_aux
    else:
        df_vpin = pd.concat([df_vpin, df_aux], axis=1)

df_vpin = df_vpin.reindex(timestamp.union(df_vpin.index)).ffill().loc[timestamp]

# Bid Ask spread
df_ba_spread = df_ba.loc[:, 'a_price'] - df_ba.loc[:, 'b_price']
df_ba_spread.name = 'ba_spread'

df_features = pd.concat([df_dti, df_vpin, df_ba_spread], axis=1).ffill().fillna(0)

# Merge
window = 300
time_bool = True
estimator = TradeProbabilityEstimator(df_fair_price, df_ba, df_price, df_features, window, time_bool)
metrics = estimator.train(10, 1)
print(metrics)

# Example usage:
# fair = pd.Series(..., index=...)
# quotes_df = pd.DataFrame(...)
# trades_df = pd.DataFrame(...)
# estimator = TradeProbabilityEstimator(fair, quotes_df, trades_df)
# metrics = estimator.train()
# print(metrics)
# prob = estimator.predict(np.array([0.01, 0.02]), np.array(['bid', 'ask']))
