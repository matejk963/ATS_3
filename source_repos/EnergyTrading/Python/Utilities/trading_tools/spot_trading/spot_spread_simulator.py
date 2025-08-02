from collections import defaultdict
import pandas as pd
import numpy as np
import scipy.stats as stats
from Database.DB_reader import Database

class ForecastSpotSimulator:
    def __init__(self, db_connection, fcst_start_date, fcst_end_date, markets, delivery, periods, correlation=0.7, n_samples=10000):
        """
        db_connection: Your database connection string (or engine) used by pd.read_sql.
        fcst_start_date, fcst_end_date: Forecast date range strings (e.g., '2025-04-04').
        markets: List of market codes (e.g., ['de']).
        delivery: List of delivery types (now referred to as legs, e.g. ['leg1', 'leg2']).
        periods: List of rel_product periods (e.g., ['W_1', 'W_2', 'W_3']).
        correlation: Historical correlation between leg1 and leg2 forecasts.
        n_samples: Number of simulation samples.
        """
        self.db_connection = db_connection
        self.fcst_start_date = pd.to_datetime(fcst_start_date)
        self.fcst_end_date = pd.to_datetime(fcst_end_date)
        self.markets = markets
        self.delivery = delivery  # Expected to be e.g. ['leg1', 'leg2']
        self.periods = periods
        self.correlation = correlation
        self.n_samples = n_samples
        
        # Extract forecast data over the date range into a nested dictionary.
        self.fcst_dict = self.extract_forecast_prices()

    def extract_forecast_prices(self):
        """
        Extract forecast prices for the given date range.
        Returns a nested dictionary keyed as:
          fcst_dict[fcst_date][market][rel_product][leg] = {'perc': [...], 'mean': [...]}
        """
        market_condition = ", ".join(f"'{m}'" for m in self.markets)
        delivery_condition = ", ".join(f"'{d}'" for d in self.delivery)
        periods_condition = ", ".join(f"'{p}'" for p in self.periods)
        
        query = f"""
            SELECT *
            FROM "MODEL_forecast_prices"."xgboost_mean_nominal"
            WHERE fcst_date BETWEEN '{self.fcst_start_date.strftime('%Y-%m-%d')}' 
                                 AND '{self.fcst_end_date.strftime('%Y-%m-%d')}'
              AND rel_product IN ({periods_condition})
              AND del_type IN ({delivery_condition})
              AND market IN ({market_condition})
              AND scenario_type IN ('base_col', 'perc_col')
        """
        fcst_data = pd.read_sql(query, con=self.db_connection)
        # Create nested dictionary: fcst_dict[fcst_date][market][period][leg]
        fcst_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
        for _, row in fcst_data.iterrows():
            fcst_date = pd.to_datetime(row['fcst_date']).strftime('%Y-%m-%d')
            market = row['market']
            period = row['rel_product']
            leg = row['del_type']  # Expected to be 'leg1' or 'leg2'
            
            if leg not in fcst_dict[fcst_date][market][period]:
                fcst_dict[fcst_date][market][period][leg] = {'perc': [], 'mean': []}
            
            if row['value_type'] in ['10th_perc', '25th_perc', '75th_perc', '90th_perc']:
                fcst_dict[fcst_date][market][period][leg]['perc'].append(row['value'])
            elif row['value_type'] == 'base':
                fcst_dict[fcst_date][market][period][leg]['mean'].append(row['value'])
        return fcst_dict

    def _get_marginal_params(self, fcst_date, market, rel_product, leg):
        """
        For a given fcst_date, market, rel_product, and leg (i.e., 'leg1' or 'leg2'),
        extract the forecast mean and estimate sigma using the 10th and 90th percentiles.
        Returns (mean, sigma) or (None, None) if missing.
        """
        try:
            data = self.fcst_dict[fcst_date][market][rel_product][leg]
        except KeyError:
            return None, None
        
        if not data['mean'] or not data['perc']:
            return None, None
        
        mean_val = data['mean'][0]  # Assume first value is the desired mean.
        # Assume order [10th, 25th, 75th, 90th] is maintained.
        if len(data['perc']) < 4:
            return mean_val, None
        p10, p25, p75, p90 = data['perc'][:4]
        sigma_val = (p90 - p10) / (2 * 1.28)
        return mean_val, sigma_val

    def simulate_spreads_by_date(self, rel_product, market=None):
        """
        For each forecast date, simulate the spread (leg2 - leg1) for the given rel_product.
        Optionally, restrict to a specific market (if not provided, use the first market).
        Returns a dictionary:
          simulated_spreads[fcst_date] = simulated spread array.
        """
        simulated_spreads = {}
        chosen_market = market if market is not None else self.markets[0]
        
        for fcst_date in self.fcst_dict.keys():
            mean_leg1, sigma_leg1 = self._get_marginal_params(fcst_date, chosen_market, rel_product, self.delivery[0])
            mean_leg2, sigma_leg2 = self._get_marginal_params(fcst_date, chosen_market, rel_product, self.delivery[1])
            if None in (mean_leg1, sigma_leg1, mean_leg2, sigma_leg2):
                # Skip forecast dates with incomplete data.
                continue
            cov_matrix = np.array([[1, self.correlation], [self.correlation, 1]])
            norm_samples = np.random.multivariate_normal(mean=[0, 0],
                                                         cov=cov_matrix,
                                                         size=self.n_samples)
            # Convert standard normals to uniforms.
            u = stats.norm.cdf(norm_samples)
            # Transform uniforms to desired marginals (assumed normal).
            leg1_sim = stats.norm.ppf(u[:, 0], loc=mean_leg1, scale=sigma_leg1)
            leg2_sim = stats.norm.ppf(u[:, 1], loc=mean_leg2, scale=sigma_leg2)
            spreads = leg1_sim - leg2_sim
            simulated_spreads[fcst_date] = spreads
        return simulated_spreads

    def spread_percentile(self, spread_value, simulated_spreads):
        """
        Given a spread value and a simulated spread array, return its percentile rank.
        """
        return stats.percentileofscore(simulated_spreads, spread_value, kind='rank')

if __name__ == '__main__':
    db = Database()
    # ------------------- USAGE EXAMPLE -------------------
    # Replace "your_connection_string" with your actual database connection string.
    db_connection = db.connection_string# e.g., "postgresql://user:pass@host/dbname"

    markets = ['de']
    # Delivery types (legs) are now referred to as leg1 and leg2.
    delivery = ['base', 'peak']
    periods = ['W_1', 'W_2', 'W_3']
    fcst_start_date = '2025-04-01'
    fcst_end_date = '2025-04-04'

    # Instantiate the simulator for the forecast date range.
    simulator = ForecastSpotSimulator(db_connection, fcst_start_date, fcst_end_date, markets, delivery, periods, correlation=0.7, n_samples=10000)

    # Simulate spreads for a given rel_product (e.g., "W_1") for each forecast date.
    simulated_spreads_dict = simulator.simulate_spreads_by_date("W_1")
    for date, spreads in simulated_spreads_dict.items():
        sample_spread = 35.4  # Example spread value.
        percentile = simulator.spread_percentile(sample_spread, spreads)
        spread_percentiles = np.percentile(spreads, [10, 25, 75, 90])
        print(f"Forecast Date: {date}")
        print(f"Spread value {sample_spread} is at the {percentile:.2f}th percentile.")
        print("Simulated Spread Percentiles (10th, 25th, 75th, 90th):", spread_percentiles)
        print("------")
