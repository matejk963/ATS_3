from scipy import stats
import numpy as np

def kde_interval(data, bounds: tuple):
    """
    Calculate the probability of the interval for the given bounds (Gaussian approximation)
    :param bounds: tuple of bounds
    :return: probability of the interval
    """
    # Check for np array if not convert
    if not isinstance(data, np.ndarray):
        data = np.array(data)
    # Check for 1d data
    if data.ndim > 1:
        raise ValueError("Data must be 1-dimensional")
    
    kde = stats.gaussian_kde(data)
    grid = np.linspace(data.min(), data.max(), 1024)
    pdf = kde(grid)
    cdf = np.cumsum(pdf)
    cdf = (cdf - cdf.min()) / (cdf.max() - cdf.min())  # Normalize to [0,1]
    # Find quantile boundaries
    lower_bound = np.interp(bounds[0], cdf, grid)
    upper_bound = np.interp(bounds[1], cdf, grid)
    return lower_bound, upper_bound