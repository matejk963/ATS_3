import pandas as pd
import pandera as pa
import numpy as np
from typing import Any, Dict, List, Union, Optional
from datetime import datetime
import json


class ValidationError(Exception):
    def __init__(self, message, check_type=None, data=None):
        super().__init__(message)
        self.check_type = check_type
        self.data = data

    def __str__(self):
        return f"[{self.check_type}] {super().__str__()}"

class Check:
    def __str__(self):
        return f"{self.__class__.__name__}"

    def validate(self, data: Any) -> bool:
        raise NotImplementedError

class CheckDataFrame(Check):
    def __init__(self, 
                columns=None, 
                checks=None, 
                parsers=None, 
                index=None, 
                dtype=None, 
                coerce=False, 
                strict=False, 
                name=None, 
                ordered=False, 
                unique=None, 
                report_duplicates='all', 
                unique_column_names=False, 
                add_missing_columns=False, 
                title=None, 
                description=None, 
                metadata=None, 
                drop_invalid_rows=False):
        self.pandera = pa.DataFrameSchema(
            columns=columns,
            checks=checks, 
            parsers=parsers, 
            index=index, 
            dtype=dtype, 
            coerce=coerce, 
            strict=strict, 
            name=name, 
            ordered=ordered, 
            unique=unique, 
            report_duplicates=report_duplicates, 
            unique_column_names=unique_column_names, 
            add_missing_columns=add_missing_columns, 
            title=title, 
            description=description, 
            metadata=metadata, 
            drop_invalid_rows=drop_invalid_rows)

    def validate(self, data: Any) -> bool:
        try:
            self.pandera.validate(data)
            return True
        except pa.errors.SchemaError as e:
            raise ValidationError(
                message=f"DataFrame validation failed: {e}",
                check_type="DataFrame",
                data=data
            )

class CheckNumpy(Check):
    def __init__(self, dim=None, not_empty=False, type=None):
        self.dim = dim
        self.not_empty = not_empty
        self.type = type

    def validate(self, data: Any) -> bool:
        try:
            if self.dim and data.shape != tuple(self.dim):
                raise ValueError(f"Expected dimensions {self.dim}, got {data.shape}")
            if self.not_empty and data.size == 0:
                raise ValueError("Array is empty")
            if self.type and not np.issubdtype(data.dtype, self.type):
                raise ValueError(f"Expected type {self.type}, got {data.dtype}")
            return True
        except ValueError as e:
            raise ValidationError(
                message=f"Numpy array validation failed: {e}",
                check_type="Numpy",
                data=data
            )

def validate_schema(schema: Union[Check, Dict, List], data: Any) -> Dict[str, Any]:
    results = {}

    if isinstance(schema, Check):
        # Validate using the Check object directly
        results[str(schema)] = schema.validate(data)

    elif isinstance(schema, dict):
        # Handle dict schema
        for key, sub_schema in schema.items():
            if key == "_":  # Uniform schema for all keys
                for sub_key, sub_value in data.items():
                    results[f"{key}[{sub_key}]"] = validate_schema(sub_schema, sub_value)
            else:  # Schema for specific keys
                results[key] = validate_schema(sub_schema, data[key])

    elif isinstance(schema, list):
        # Handle list schema
        for idx, item in enumerate(data):
            results[f"item_{idx}"] = validate_schema(schema[0], item)

    else:
        raise ValidationError("Unsupported schema type", check_type="General")

    return results

def check_numeric(value):
    try:
        # Convert to float and check for np.nan
        numeric_value = float(value)
        if np.isnan(numeric_value):
            return None
        return numeric_value
    except (ValueError, TypeError):
        return None

def assert_pair(actual, expected, text=""):
    """Verify if two values match and print comparison results."""
    assert actual == expected, f"{text} mismatch: {actual} != {expected}"

