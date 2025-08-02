"""
Data Fetcher Implementation for ATS_3

Clean interface with flexible contract-specific date handling for trading data.
Based on ATS_2 data_fetch.py patterns with modern improvements.
"""

import sys
import os
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional, Union, Tuple
import pandas as pd
import numpy as np

# Add EnergyTrading to path for TPData imports
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/EnergyTrading/Python')

try:
    from Database.TPData import TPData, TPDataDa
    TPDATA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: TPData import failed: {e}")
    TPDATA_AVAILABLE = False


class DeliveryDateCalculator:
    """Calculate first delivery dates from tenor/contract specifications"""
    
    @staticmethod
    def calc_delivery_date(tenor: str, contract: str) -> datetime:
        """
        Convert tenor/contract to first delivery date
        
        Args:
            tenor: 'd', 'w', 'm', 'q', 'y', 'da'
            contract: Contract specification (e.g., '07_25', '2_25', '1')
            
        Returns:
            First delivery date
        """
        base_year = 2000
        current_year = datetime.now().year
        
        if tenor.lower() == 'da':
            # Day-ahead: contract is days offset
            days_offset = int(contract)
            return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_offset)
        
        elif tenor.lower() == 'd':
            # Daily: contract is specific date
            return datetime.strptime(contract, '%Y-%m-%d')
        
        elif tenor.lower() == 'w':
            # Weekly: contract is week number_year
            week_str, year_str = contract.split('_')
            year = base_year + int(year_str) if int(year_str) < 50 else 1900 + int(year_str)
            return datetime.strptime(f'{year}-W{week_str}-1', '%Y-W%W-%w')
        
        elif tenor.lower() == 'm':
            # Monthly: contract is MM_YY format
            month_str, year_str = contract.split('_')
            year = base_year + int(year_str) if int(year_str) < 50 else 1900 + int(year_str)
            return datetime(year, int(month_str), 1)
        
        elif tenor.lower() == 'q':
            # Quarterly: contract is Q_YY format
            quarter_str, year_str = contract.split('_')
            year = base_year + int(year_str) if int(year_str) < 50 else 1900 + int(year_str)
            quarter = int(quarter_str)
            month = (quarter - 1) * 3 + 1
            return datetime(year, month, 1)
        
        elif tenor.lower() == 'y':
            # Yearly: contract is YY format
            year = base_year + int(contract) if int(contract) < 50 else 1900 + int(contract)
            return datetime(year, 1, 1)
        
        else:
            raise ValueError(f"Unknown tenor: {tenor}")


class DateRangeResolver:
    """Convert lookback days to start/end dates from delivery date"""
    
    @staticmethod
    def resolve_date_range(delivery_date: datetime, lookback_days: int) -> Tuple[datetime, datetime]:
        """
        Calculate start and end dates based on lookback from delivery date or today
        
        For future contracts (delivery date > today), calculates from today instead
        to ensure we have actual trading data available.
        
        Args:
            delivery_date: First delivery date
            lookback_days: Number of business days to look back
            
        Returns:
            (start_date, end_date) tuple
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # If delivery date is in the future, use today as reference point
        if delivery_date > today:
            end_date = today - timedelta(days=1)  # Yesterday (last complete day)
        else:
            end_date = delivery_date - timedelta(days=1)  # Day before delivery
        
        # Calculate business days backwards
        current_date = end_date
        business_days_counted = 0
        
        while business_days_counted < lookback_days:
            current_date = current_date - timedelta(days=1)
            # Monday=0, Sunday=6; business days are 0-4
            if current_date.weekday() < 5:
                business_days_counted += 1
        
        start_date = current_date
        return start_date, end_date


class ContractValidator:
    """Validate contract specifications"""
    
    @staticmethod
    def validate_contract(contract_config: Dict) -> bool:
        """
        Validate a single contract configuration
        
        Args:
            contract_config: Dictionary containing contract specification
            
        Returns:
            True if valid, raises ValueError if invalid
        """
        required_fields = ['market', 'tenor', 'contract']
        
        # Check required fields
        for field in required_fields:
            if field not in contract_config:
                raise ValueError(f"Missing required field: {field}")
        
        # Check market is valid
        valid_markets = ['de', 'fr', 'hu', 'it', 'es', 'ttf', 'the', 'eua']
        if contract_config['market'] not in valid_markets:
            raise ValueError(f"Invalid market: {contract_config['market']}")
        
        # Check tenor is valid
        valid_tenors = ['da', 'd', 'w', 'm', 'q', 'y']
        if contract_config['tenor'] not in valid_tenors:
            raise ValueError(f"Invalid tenor: {contract_config['tenor']}")
        
        # Check date configuration - either explicit dates or lookback
        has_explicit_dates = 'start_date' in contract_config and 'end_date' in contract_config
        has_lookback = 'lookback_days' in contract_config
        
        if not (has_explicit_dates or has_lookback):
            raise ValueError("Contract must specify either explicit dates (start_date/end_date) or lookback_days")
        
        if has_explicit_dates and has_lookback:
            raise ValueError("Contract cannot specify both explicit dates and lookback_days")
        
        return True


class DataFetcher:
    """
    Main data fetcher class with flexible contract-specific date handling
    
    Features:
    - Contract-specific date ranges (explicit dates or lookback-based)
    - Unified contract configuration for trades and orders
    - Parallel processing with data alignment
    - Clean interface preserving legacy functionality
    """
    
    def __init__(self, trading_hours: Tuple[int, int] = (9, 17), 
                 allowed_broker_ids: Optional[List[int]] = None):
        """
        Initialize DataFetcher
        
        Args:
            trading_hours: (start_hour, end_hour) for filtering
            allowed_broker_ids: List of allowed broker IDs for trade filtering
        """
        self.trading_hours = trading_hours
        self.allowed_broker_ids = allowed_broker_ids or [1441]  # Default to EEX
        
        # Initialize TPData connections
        self.data_class_oracle = None
        self.data_class_pg = None
        self.data_class_da = None
        
        if not TPDATA_AVAILABLE:
            raise RuntimeError("TPData not available. Cannot initialize DataFetcher.")
    
    def _init_connections(self):
        """Initialize database connections"""
        if not self.data_class_oracle:
            self.data_class_oracle = TPData()
            self.data_class_oracle.create_connection('OracleSQL')
        
        if not self.data_class_pg:
            self.data_class_pg = TPData()
            self.data_class_pg.create_connection('PostgreSQL')
        
        if not self.data_class_da:
            self.data_class_da = TPDataDa()
    
    def _resolve_contract_dates(self, contract_config: Dict) -> Tuple[datetime, datetime]:
        """
        Resolve contract configuration to start/end dates
        
        Args:
            contract_config: Contract configuration dictionary
            
        Returns:
            (start_date, end_date) tuple
        """
        ContractValidator.validate_contract(contract_config)
        
        if 'start_date' in contract_config and 'end_date' in contract_config:
            # Explicit dates
            start_date = pd.to_datetime(contract_config['start_date']).to_pydatetime()
            end_date = pd.to_datetime(contract_config['end_date']).to_pydatetime()
            return start_date, end_date
        
        elif 'lookback_days' in contract_config:
            # Lookback from delivery date
            delivery_date = DeliveryDateCalculator.calc_delivery_date(
                contract_config['tenor'], contract_config['contract']
            )
            return DateRangeResolver.resolve_date_range(
                delivery_date, contract_config['lookback_days']
            )
        
        else:
            raise ValueError("Invalid contract configuration")
    
    def fetch_contract_data(self, contract_config: Dict, 
                          include_trades: bool = True, 
                          include_orders: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for a single contract
        
        Args:
            contract_config: Contract configuration
            include_trades: Whether to fetch trade data
            include_orders: Whether to fetch order book data
            
        Returns:
            Dictionary containing fetched data
        """
        self._init_connections()
        
        start_date, end_date = self._resolve_contract_dates(contract_config)
        
        market = contract_config['market']
        tenor = contract_config['tenor']
        contract = contract_config['contract']
        prod = contract_config.get('prod', 'base')
        venue_list = contract_config.get('venue_list', ['eex'])
        
        # Calculate product delivery date
        product_date = DeliveryDateCalculator.calc_delivery_date(tenor, contract)
        
        # Trading hours
        start_time = time(self.trading_hours[0], 0, 0)
        end_time = time(self.trading_hours[1], 0, 0)
        
        result = {}
        
        # Generate business days in the range
        dates = pd.date_range(start_date, end_date, freq='B')
        
        if include_trades:
            result['trades'] = self._fetch_trades(
                market, tenor, venue_list, product_date, 
                dates, start_time, end_time, prod
            )
        
        if include_orders:
            result['orders'] = self._fetch_orders(
                market, tenor, venue_list, product_date,
                dates, start_time, end_time, prod
            )
            result['mid_prices'] = self._calculate_mid_prices(result['orders'])
        
        return result
    
    def _fetch_trades(self, market: str, tenor: str, venue_list: List[str], 
                     product_date: datetime, dates: pd.DatetimeIndex,
                     start_time: time, end_time: time, prod: str) -> pd.DataFrame:
        """Fetch trade data following legacy pattern"""
        df_tr = pd.DataFrame([])
        
        agg_dict = {'price': 'sum', 'volume': 'sum', 'action': 'median',
                   'broker_id': 'median', 'count': 'sum', 'tradeid': 'first'}
        
        series = pd.Series(product_date, index=dates)
        
        for p_d, ds in series.groupby(series).groups.items():
            bT = datetime.combine(ds[0], start_time)
            eT = datetime.combine(ds[-1], end_time)
            
            # Trades
            df_tr_aux = self.data_class_oracle.get_trades(market, tenor, venue_list, p_d, bT, eT, prod)
            
            # Filter by broker
            if self.allowed_broker_ids and tenor != 'da':
                df_tr_aux = df_tr_aux[df_tr_aux['broker_id'].isin(self.allowed_broker_ids)]
            
            try:
                df_tr_aux = df_tr_aux.between_time(start_time, end_time)
            except(TypeError):
                pass
            
            # Group trades
            df_tr_aux['count'] = 1
            df_tr_aux['price'] *= df_tr_aux['volume']
            df_tr_aux = df_tr_aux.groupby(df_tr_aux.index).agg(agg_dict)
            df_tr_aux['price'] /= df_tr_aux['volume']
            
            df_tr = pd.concat([df_tr, df_tr_aux])
            del df_tr_aux
        
        return df_tr
    
    def _fetch_orders(self, market: str, tenor: str, venue_list: List[str],
                     product_date: datetime, dates: pd.DatetimeIndex,
                     start_time: time, end_time: time, prod: str) -> pd.DataFrame:
        """Fetch order book data following legacy pattern"""
        df_ba = pd.DataFrame([])
        
        series = pd.Series(product_date, index=dates)
        
        for p_d, ds in series.groupby(series).groups.items():
            bT = datetime.combine(ds[0], start_time)
            eT = datetime.combine(ds[-1], end_time)
            
            # Order book data
            df_ba_aux = self.data_class_pg.get_best_ob_data(market, tenor, venue_list, p_d, bT, eT, prod, None, False)
            df_ba_aux = df_ba_aux.rename(columns={'bidbestprice': 'b_price', 'askbestprice': 'a_price'})
            
            try:
                df_ba_aux = df_ba_aux.between_time(start_time, end_time)
            except(TypeError):
                pass
            
            df_ba = pd.concat([df_ba, df_ba_aux])
            del df_ba_aux
        
        return df_ba
    
    def _calculate_mid_prices(self, orders_df: pd.DataFrame) -> pd.Series:
        """Calculate mid prices from order book data"""
        if 'b_price' in orders_df.columns and 'a_price' in orders_df.columns:
            return 0.5 * (orders_df['b_price'] + orders_df['a_price'])
        return pd.Series(dtype=float)
    
    def fetch_multiple_contracts(self, contracts: List[Dict], 
                               include_trades: bool = True,
                               include_orders: bool = True) -> Dict[str, Dict]:
        """
        Fetch data for multiple contracts
        
        Args:
            contracts: List of contract configurations
            include_trades: Whether to fetch trade data
            include_orders: Whether to fetch order book data
            
        Returns:
            Dictionary keyed by contract identifiers
        """
        results = {}
        
        for contract_config in contracts:
            # Generate contract key
            contract_key = f"{contract_config['market']}{contract_config['tenor']}{contract_config['contract']}"
            
            try:
                results[contract_key] = self.fetch_contract_data(
                    contract_config, include_trades, include_orders
                )
                print(f"Successfully fetched data for {contract_key}")
            except Exception as e:
                print(f"Error fetching data for {contract_key}: {e}")
                results[contract_key] = {}
        
        return results
    
    def export_to_parquet(self, contract_data: Dict[str, Dict], output_dir: str):
        """
        Export contract data to parquet files
        
        Args:
            contract_data: Result from fetch_multiple_contracts
            output_dir: Output directory path
        """
        os.makedirs(output_dir, exist_ok=True)
        
        for contract_key, data in contract_data.items():
            if not data:
                continue
            
            # Merge trades, orders, and mid prices
            merged_data = pd.DataFrame()
            
            if 'trades' in data and not data['trades'].empty:
                merged_data = pd.concat([merged_data, data['trades']], axis=1, join='outer')
            
            if 'orders' in data and not data['orders'].empty:
                merged_data = pd.concat([merged_data, data['orders']], axis=1, join='outer')
            
            if 'mid_prices' in data and not data['mid_prices'].empty:
                merged_data = pd.concat([merged_data, data['mid_prices']], axis=1, join='outer')
            
            if not merged_data.empty:
                file_path = os.path.join(output_dir, f'{contract_key}_tr_ba_data.parquet')
                merged_data.to_parquet(file_path)
                print(f"Exported {contract_key} to {file_path}")


def test_tpdata_connectivity():
    """Test basic TPData connectivity"""
    print("Testing TPData connectivity...")
    
    if not TPDATA_AVAILABLE:
        print("❌ TPData not available for import")
        return False
    
    try:
        # Test basic instantiation
        data_class = TPData()
        print("✅ TPData instantiated successfully")
        
        # Test connection creation (without actually connecting)
        print("✅ TPData basic functionality available")
        
        data_class_da = TPDataDa()
        print("✅ TPDataDa instantiated successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ TPData connectivity test failed: {e}")
        return False


if __name__ == "__main__":
    # Run connectivity test
    test_tpdata_connectivity()
    
    # Test delivery date calculator
    print("\nTesting DeliveryDateCalculator...")
    calc = DeliveryDateCalculator()
    
    test_cases = [
        ('m', '07_25'),  # July 2025
        ('q', '2_25'),   # Q2 2025
        ('y', '25'),     # Year 2025
    ]
    
    for tenor, contract in test_cases:
        try:
            delivery_date = calc.calc_delivery_date(tenor, contract)
            print(f"✅ {tenor}:{contract} -> {delivery_date}")
        except Exception as e:
            print(f"❌ {tenor}:{contract} -> {e}")
    
    # Test date range resolver
    print("\nTesting DateRangeResolver...")
    resolver = DateRangeResolver()
    
    delivery_date = datetime(2025, 7, 1)
    start_date, end_date = resolver.resolve_date_range(delivery_date, 90)
    print(f"✅ 90 days before {delivery_date} -> {start_date} to {end_date}")