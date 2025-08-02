"""
Simulator package for ObserverStrategy backtesting.

This package contains the simulation infrastructure for running
ObserverStrategy tests with proper exchange order book reconstruction.
"""

from .observer_simulation import ObserverSimulator

__all__ = ['ObserverSimulator']