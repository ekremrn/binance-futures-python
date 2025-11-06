"""Binance USDT-M Futures REST client package."""

from .client import BinanceFuturesAPIError, BinanceFuturesClient

__all__ = ["BinanceFuturesClient", "BinanceFuturesAPIError", "__version__"]

__version__ = "0.1.0"
