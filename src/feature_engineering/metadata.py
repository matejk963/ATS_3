"""DataFrameMetadata class for preserving DataFrame structure during array processing"""

from dataclasses import dataclass
from typing import Dict, List
import pandas as pd
import numpy as np


@dataclass
class DataFrameMetadata:
    """Stores DataFrame information for reconstruction"""
    index: pd.Index
    columns: List[str]
    dtypes: Dict[str, np.dtype]
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> 'DataFrameMetadata':
        """Extract metadata from DataFrame"""
        return cls(
            index=df.index.copy(),
            columns=df.columns.tolist(),
            dtypes=df.dtypes.to_dict()
        )
        
    def reconstruct(self, data: Dict[str, np.ndarray]) -> pd.DataFrame:
        """Rebuild DataFrame from arrays using stored metadata"""
        df = pd.DataFrame(data, index=self.index)
        for col, dtype in self.dtypes.items():
            if col in df.columns:
                df[col] = df[col].astype(dtype)
        return df