import numpy as np


def cost_function(value_list, methods):

    ret = np.asarray(value_list)

    # Function to calculate maximum drawdown
    def calculate_max_drawdown(values):
        peak = values[0]
        max_drawdown = 0
        for value in values:
            if peak != 0:  # Ensure peak is not zero to avoid division by zero
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            if value > peak:
                peak = value
        return max_drawdown

    def calculate_max_absolute_drawdown(values):
        peak = values[0]
        max_drawdown = 0
        for value in values:
            drawdown = (peak - value)
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            if value > peak:
                peak = value
        return max_drawdown

    def calculate_cost(method):
        if method == 'sharp':
            return np.mean(ret) / np.std(ret)
        elif method == 'mean':
            return np.mean(ret)
        elif method == 'cumpnl':
            return ret[-1]
        elif method == 'max_drawdown':
            return calculate_max_drawdown(ret)
        elif method == 'max_absolute_drawdown':
            return calculate_max_absolute_drawdown(ret)
        else:
            raise ValueError(f'Unknown method of optimisation {method}')



    # Check if methods is a list and apply the function accordingly
    if isinstance(methods, list):
        results = [calculate_cost(method) for method in methods]
        return results
    else:
        return calculate_cost(methods)