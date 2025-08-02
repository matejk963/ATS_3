import numpy as np
import math
import json
from .OB_attributes import OB_attributes

class MEMORY_KEYS:
    LVL_DIST = 'lvl_dist'
    P_MOVEMENT = 'p_movement'

def initiate_memory():
    #TODO: load memory from create strategy
    # steering to get current memory
    # \
    lvl_dist = {
        'buff_len': 30,
        'buffer': [],
        'max_value': 0,
        'min_value': 9999
    }
    p_movement = {
        'pm_value': {
            '0.3': 0.0,
            '0.5': 0.0,
            '1.0': 0.0
        },
        'last_mid': None
    }
    return {
        'lvl_dist': lvl_dist,
        'p_movement': p_movement
    }
def _sparsity_func(order_book):
    _MIN_N_ORDERS = 4
    order_book = np.array(order_book)

    # Calculate differences
    diff = np.diff(order_book)

    # Shift the differences to align with the required positions
    if len(diff) < 1:
        return 2.0

    # diff = diff[:-1]  # Remove last element to align with shifted values

    length = len(diff)
    if length < _MIN_N_ORDERS:
        return 2.0

    # Define the manual kernel and normalize
    manual_kernel = np.array([2, 1.5, 1.25, 1, 1])
    kernel_list = manual_kernel / 2

    # Calculate weighted differences
    sum_w_diff = 0
    for i in range(min(4, length)):  # To handle cases where length is less than 5
        sum_w_diff += kernel_list[i] * abs(diff[i])

    return min(round(sum_w_diff, 2), 1)

# def predictor_sparsity(localview, market_area):
#     bids = [x.price for x in localview._product.orders.get(market_area) if x.is_tradable and x.direction == 'buy']
#     asks = [x.price for x in localview._product.orders.get(market_area) if x.is_tradable and x.direction == 'sell']
#     asks = sorted(asks, reverse=False)
#     bids = sorted(bids, reverse=True)
#     return {
#         'b_price_sparsity': _sparsity_func(bids),
#         'a_price_sparsity': _sparsity_func(asks)
#     }
def predictor_sparsity(obAttr: OB_attributes):
    bids = [x.price for x in obAttr.bids]
    asks = [x.price for x in obAttr.asks]
    return {
        'b_price_sparsity': obAttr._sparsity_func(bids),
        'a_price_sparsity': obAttr._sparsity_func(asks)
    }

def predictor_scaled_sparsity(b_price_sparsity, a_price_sparsity):
    FILENAME_SP_DISTRIBUTION_ = "todo.json"

    with open(FILENAME_SP_DISTRIBUTION_, 'r') as file:
        sp_distribution = json.load(file)

    if not sp_distribution or len(sp_distribution) < 1:
        raise ValueError(f"sp_distribution loading failed, name of file: {FILENAME_SP_DISTRIBUTION_}")
        
    length = len(sp_distribution)
        
    def approx_ppf(sparsity):
        p = np.where(sp_distribution == sparsity)[0][0] / length

        tol = 1e-5
        if p <= 0 or p >= 1:
            # Handle the boundary cases for p = 0 and p = 1
            if round(p, 2) <= 0:
                return -np.inf  # Approximate negative infinity for p = 0
            elif round(p, 2) >= 1:
                return np.inf  # Approximate positive infinity for p = 1
            else:
                raise ValueError("p must be in the range (0, 1)")

        # Constants for central approximation
        a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
        b = [-8.4735109309, 23.08336743743, -21.06224101826, 3.13082909833]

        # Polynomial approximation for the central region (0.08 < p < 0.92)
        if 0.08 < p < 0.92:
            q = p - 0.5
            r = q * q
            return q * (((a[3] * r + a[2]) * r + a[1]) * r + a[0]) / \
                ((((b[3] * r + b[2]) * r + b[1]) * r + b[0]) * r + 1.0)

        # Tail approximation for values near 0 and 1
        else:
            if p < 0.5:
                r = np.sqrt(-2.0 * np.log(p))
                return -(r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) /
                         (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3))
            else:
                r = np.sqrt(-2.0 * np.log(1.0 - p))
                return r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) / \
                    (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3)

    return math.erf((approx_ppf(a_price_sparsity) - approx_ppf(b_price_sparsity)) / 2)

def predictor_feature_lvl_dist(memory, trade_dict):
    # variables = {
    #     'buff_len': 30,
    #     'buffer': [],
    #     'max_value': 0,
    #     'min_value': 9999
    # }
    variables = memory[MEMORY_KEYS.LVL_DIST]
    def push(x, value):
        if value > x['max_value']: x['max_value'] = value
        if value < x['min_value']: x['min_value'] = value

        value = round(value, 1)
        if len(x['buffer']) < x['buff_len']:
            x['buffer'].append(value)
        else:
            x['buffer'].pop(0)
            x['buffer'].append(value)

    def get_bounds(x, bound: str):
        allowed_bounds = {'close', 'far'}
        if bound not in allowed_bounds:
            # Default to 'far' if the bound is invalid
            bound = 'far'

        if bound == 'far':
            # Use x['min_value'] and x['max_value'] directly or fallback if missing
            min_value = x.get('min_value', np.nan)
            max_value = x.get('max_value', np.nan)
            return min_value, max_value

        # Handle 'close' bound
        arr = np.unique(np.round(x['buffer'], 1))
        low_bound = np.min(arr) if len(arr) > 0 else np.nan
        up_bound = np.max(arr) if len(arr) > 0 else np.nan

        # Check if buffer length is sufficient
        if len(x.get('buffer', [])) < x.get('buff_len', 0):
            return np.nan, np.nan

        return low_bound, up_bound

    def map_to_unit_interval(number, lower_bound, upper_bound):
        return max(min((number - lower_bound) / ((upper_bound - lower_bound) + 0.001), 1.0), 0.0)

    trade = trade_dict['price']
    push(variables, trade)
    close_low, close_up = get_bounds(variables, 'close')
    far_low, far_up = get_bounds(variables, 'far')
    close_level = map_to_unit_interval(trade, close_low, close_up)
    far_level = map_to_unit_interval(trade, far_low, far_up)

    return close_level, far_level

def predictor_ba_volrat(obAttr: OB_attributes, p_depth):
    return obAttr.vol_ratio(p_depth)

def predictor_mid_priceW(obAttr: OB_attributes, p_depth):
    return obAttr.mid_priceW(p_depth)

def predictor_mid_priceW_d(obAttr: OB_attributes, p_depth):
    return obAttr.mid_priceW(p_depth) - obAttr.mid_price()

def predictor_p_movement(memory, obAttr: OB_attributes, ):
    pm_value = memory[MEMORY_KEYS.P_MOVEMENT]['pm_value']
    last_mid = memory[MEMORY_KEYS.P_MOVEMENT]['last_mid']
    def _pm_update(pm_value, price_diff, depth:str):
        """_summary_
        Feature function that keeps memory of price movement for different depth
        Args:
            price_diff (float): should be difference of mid (t0-t1)
            depth (_type_): in eur format 0.3, 0.5, 0.9 recommended
            self.pm_value is dictionary that hold value of the operator for different depths
        """
        if not pm_value.get(depth, None):
            raise ValueError("p_movement memory for depth not defined")
        depth_thold = float(depth)
        if abs(price_diff) > 0.01:
            if pm_value[depth] > depth_thold:
                if price_diff > 0:
                    pm_value[depth] += price_diff / 2
                else:
                    pm_value[depth] += price_diff
            elif pm_value[depth] < -depth_thold:
                if price_diff < 0:
                    pm_value[depth] += price_diff / 2
                else:
                    pm_value[depth] += price_diff
            else:
                pm_value[depth] += price_diff

    def _pm_evaluate(pm_value, depth):
        # https://www.desmos.com/calculator/cc7kcid1jk
        f = lambda x, b: (lambda y: 1 if y > 1 else y)((1 / b ** 2) * x ** 2) if x > 0 else (
            lambda y: -1 if y < -1 else y)(-(1 / b ** 2) * x ** 2)
        # return self.pm_value[depth] / depth
        return f(pm_value[depth], float(depth))

    depth_list = ['0.3', '0.5', '1.0']
    price_diff = round(obAttr.mid_price() - last_mid, 2)

    result_dict = {}
    for depth in depth_list:
        _pm_update(price_diff, depth)
        result_dict["p_movement_" + depth].append(
            _pm_evaluate(depth)
        )

    memory[MEMORY_KEYS.P_MOVEMENT]['last_mid'] = obAttr.mid_price()

    return result_dict


def simple_ridge_regression(X, y, lambda_value=1.0):
    # Adjust target by subtracting the intercept
    # This makes the regression predict the residual (y - A)

    n_features = X.shape[1]
    identity = np.eye(n_features)

    try:
        # No need for an intercept column in X since we're using A directly
        XtX_plus_lambda = X.T @ X + lambda_value * identity
        Xty = X.T @ y
        coefs = np.linalg.solve(XtX_plus_lambda, Xty)
    except np.linalg.LinAlgError:
        # Fallback to pseudo-inverse if matrix is singular
        coefs = np.linalg.pinv(XtX_plus_lambda) @ Xty

    return coefs


def constrained_coefficient_model_with_lastprice_features(X, W_m, D, y, lambda_value=1.0,
                                                          mask_thold=5):
    n_samples, n_features = X.shape
    prediction = np.nan

    target_mask = y > 0
    y_masked = y[target_mask]
    y_window = (y_masked - np.roll(y_masked, 1))[1:]
    # Get window data
    X_window = X[target_mask][1:]
    W_m_window = W_m[target_mask][1:]
    D_window = D[target_mask][1:]

    X_comb = X_window * W_m_window

    if target_mask.sum() < mask_thold:
        prediction = 0.0
    else:
        # Create feature matrix - include all features plus last price
        features = np.hstack([X_comb, D_window])

        # Use Ridge Regression with higher regularization
        coef = simple_ridge_regression(features, y_window, lambda_value=0.05)

        features_next = np.hstack([
            X[-1] * W_m[-1].reshape(1, -1),
            D[-1].reshape(1, -1)])
        intercept = y_masked[-1]
        # Make prediction using our coefficients
        prediction = np.sum(features_next * coef) + intercept

    return prediction