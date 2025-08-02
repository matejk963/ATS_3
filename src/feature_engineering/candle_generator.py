"""CandleGenerator for OHLC candle generation from tick data"""

from typing import Dict, Optional
import numpy as np
import pandas as pd
from .array_backend import ArrayBackend
from .array_types import ArrayLike


class CandleGenerator:
    """Generate OHLC candles from price tick data using ArrayBackend"""
    
    def __init__(self, backend: ArrayBackend):
        """Initialize with ArrayBackend for CPU/GPU compatibility"""
        self.backend = backend
        self.xp = backend.xp
    
    def generate_ohlc(self, prices: ArrayLike, timestamps: ArrayLike, 
                      granularity: str) -> Dict[str, ArrayLike]:
        """Generate OHLC candles from price ticks
        
        Args:
            prices: Array of price values
            timestamps: Array of timestamp values (Unix timestamps)
            granularity: Candle granularity ('1min', '5min', '15min', '1H', '4H', '1D')
            
        Returns:
            Dict with 'open', 'high', 'low', 'close' arrays
        """
        prices = self.backend.asarray(prices)
        timestamps = self.backend.asarray(timestamps)
        
        if len(prices) == 0:
            return {
                'open': self.backend.asarray([]),
                'high': self.backend.asarray([]),
                'low': self.backend.asarray([]),
                'close': self.backend.asarray([])
            }
        
        if len(prices) == 1:
            # Single tick - O=H=L=C
            price = prices[0]
            return {
                'open': self.backend.asarray([price]),
                'high': self.backend.asarray([price]),
                'low': self.backend.asarray([price]),
                'close': self.backend.asarray([price])
            }
        
        # Parse granularity to seconds
        interval_seconds = self._parse_granularity(granularity)
        
        # Group ticks into time bins
        candle_bins = self._create_time_bins(timestamps, interval_seconds)
        
        # Generate OHLC for each bin
        return self._compute_ohlc_from_bins(prices, timestamps, candle_bins)
    
    def _parse_granularity(self, granularity: str) -> int:
        """Parse granularity string to seconds"""
        granularity = granularity.lower()
        
        if granularity.endswith('min'):
            minutes = int(granularity[:-3])
            return minutes * 60
        elif granularity.endswith('h'):
            hours = int(granularity[:-1])
            return hours * 3600
        elif granularity.endswith('d'):
            days = int(granularity[:-1])
            return days * 86400
        else:
            raise ValueError(f"Unsupported granularity: {granularity}")
    
    def _create_time_bins(self, timestamps: ArrayLike, interval_seconds: int) -> ArrayLike:
        """Create time bins for grouping ticks"""
        if len(timestamps) == 0:
            return self.backend.asarray([])
        
        # Convert to CPU for time operations if needed
        ts_cpu = self.backend.to_cpu(timestamps)
        
        # Find start and end times
        start_time = ts_cpu[0]
        end_time = ts_cpu[-1]
        
        # Align start to interval boundary
        aligned_start = (int(start_time) // interval_seconds) * interval_seconds
        
        # Create bin edges
        n_bins = int((end_time - aligned_start) / interval_seconds) + 1
        bin_edges = np.arange(aligned_start, aligned_start + (n_bins + 1) * interval_seconds, interval_seconds)
        
        # Assign each timestamp to a bin
        bin_indices = np.digitize(ts_cpu, bin_edges) - 1
        
        return self.backend.asarray(bin_indices)
    
    def _compute_ohlc_from_bins(self, prices: ArrayLike, timestamps: ArrayLike, 
                               bin_indices: ArrayLike) -> Dict[str, ArrayLike]:
        """Compute OHLC values for each time bin"""
        prices_cpu = self.backend.to_cpu(prices)
        bins_cpu = self.backend.to_cpu(bin_indices)
        
        if len(prices_cpu) == 0:
            return {
                'open': self.backend.asarray([]),
                'high': self.backend.asarray([]),
                'low': self.backend.asarray([]),
                'close': self.backend.asarray([])
            }
        
        # Find unique bins
        unique_bins = np.unique(bins_cpu)
        unique_bins = unique_bins[unique_bins >= 0]  # Remove invalid bins
        
        if len(unique_bins) == 0:
            # All ticks in same bin
            return {
                'open': self.backend.asarray([prices_cpu[0]]),
                'high': self.backend.asarray([np.max(prices_cpu)]),
                'low': self.backend.asarray([np.min(prices_cpu)]),
                'close': self.backend.asarray([prices_cpu[-1]])
            }
        
        opens = []
        highs = []
        lows = []
        closes = []
        
        for bin_idx in unique_bins:
            mask = bins_cpu == bin_idx
            bin_prices = prices_cpu[mask]
            
            if len(bin_prices) > 0:
                opens.append(bin_prices[0])    # First price in bin
                highs.append(np.max(bin_prices))  # Highest price
                lows.append(np.min(bin_prices))   # Lowest price  
                closes.append(bin_prices[-1])     # Last price in bin
        
        return {
            'open': self.backend.asarray(opens),
            'high': self.backend.asarray(highs),
            'low': self.backend.asarray(lows),
            'close': self.backend.asarray(closes)
        }


class DualCandleGenerator:
    """
    Generate dual-candle system (historical + evolving) matching ATS_2 implementation.
    
    Supports both historical completed candles and real-time evolving candles
    for the current period, enabling real-time trading compatibility.
    """
    
    def __init__(self, backend: ArrayBackend):
        """Initialize with ArrayBackend for CPU/GPU compatibility"""
        self.backend = backend
        self.candle_generator = CandleGenerator(backend)
        
    def generate_combined_candles(self, 
                                tick_data: pd.DataFrame,
                                granularity: str,
                                historical_candles: Optional[pd.DataFrame] = None,
                                current_time: Optional[pd.Timestamp] = None) -> pd.DataFrame:
        """
        Generate combined historical + evolving candles matching ATS_2 approach.
        
        Args:
            tick_data: DataFrame with 'datetime' and 'price' columns
            granularity: Time granularity (e.g., '15min', '30min')
            historical_candles: Pre-computed completed candles (optional)
            current_time: Current timestamp for evolving candle cutoff
            
        Returns:
            DataFrame with OHLC candles including evolving current period
        """
        if current_time is None:
            current_time = pd.Timestamp.now()
        
        if historical_candles is None:
            # Generate historical candles from tick data (excluding current period)
            period_start = current_time.floor(granularity)
            historical_data = tick_data[tick_data['datetime'] < period_start].copy()
            historical_candles = self._generate_ohlc_dataframe(historical_data, granularity)
        
        # Generate evolving candle from current period trades
        evolving_candle = self._generate_evolving_candle(tick_data, granularity, current_time)
        
        # Combine using ATS_2 pattern
        if evolving_candle is not None and len(evolving_candle) > 0:
            return pd.concat([historical_candles, evolving_candle], ignore_index=False)
        return historical_candles
    
    def _generate_evolving_candle(self, 
                                 tick_data: pd.DataFrame,
                                 granularity: str,
                                 current_time: Optional[pd.Timestamp] = None) -> Optional[pd.DataFrame]:
        """
        Generate real-time evolving candle from current period trades.
        
        Matches ATS_2's combine_candles_with_latest_trades() implementation.
        """
        if current_time is None:
            current_time = pd.Timestamp.now()
            
        # Determine current period start (ATS_2 pattern)
        period_start = current_time.floor(granularity)
        
        # Filter trades in current period
        current_trades = tick_data[tick_data['datetime'] >= period_start].copy()
        
        if current_trades.empty:
            return None
            
        # Create evolving OHLC candle (ATS_2 pattern)
        current_open = current_trades['price'].iloc[0]    # First trade price
        current_high = current_trades['price'].max()      # Highest trade price
        current_low = current_trades['price'].min()       # Lowest trade price
        current_close = current_trades['price'].iloc[-1]  # Latest trade price
        current_volume = len(current_trades)              # Trade count as volume
        
        evolving_candle = pd.DataFrame({
            'open': [current_open],
            'high': [current_high], 
            'low': [current_low],
            'close': [current_close],
            'volume': [current_volume]
        }, index=[period_start])
        
        return evolving_candle
    
    def _generate_ohlc_dataframe(self, tick_data: pd.DataFrame, granularity: str) -> pd.DataFrame:
        """Generate OHLC DataFrame from tick data using existing CandleGenerator"""
        if tick_data.empty:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        
        # Convert to timestamp arrays for CandleGenerator
        timestamps = tick_data['datetime'].astype('int64') // 10**9  # Convert to Unix timestamps
        prices = tick_data['price'].values
        
        # Use existing CandleGenerator
        ohlc_arrays = self.candle_generator.generate_ohlc(prices, timestamps, granularity)
        
        # Convert arrays back to DataFrame
        if len(self.backend.to_cpu(ohlc_arrays['open'])) == 0:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        
        # Create time index for candles
        interval_seconds = self.candle_generator._parse_granularity(granularity)
        first_timestamp = timestamps[0]
        aligned_start = (int(first_timestamp) // interval_seconds) * interval_seconds
        
        n_candles = len(self.backend.to_cpu(ohlc_arrays['open']))
        candle_times = pd.to_datetime([
            aligned_start + i * interval_seconds for i in range(n_candles)
        ], unit='s')
        
        # Create DataFrame with volume (trade count approximation)
        candle_df = pd.DataFrame({
            'open': self.backend.to_cpu(ohlc_arrays['open']),
            'high': self.backend.to_cpu(ohlc_arrays['high']),
            'low': self.backend.to_cpu(ohlc_arrays['low']),
            'close': self.backend.to_cpu(ohlc_arrays['close']),
            'volume': [len(tick_data) // n_candles] * n_candles  # Approximate volume
        }, index=candle_times)
        
        return candle_df