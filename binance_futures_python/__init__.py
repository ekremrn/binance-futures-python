"""Binance USDT-M Futures REST client package."""

from .client import BinanceFuturesAPIError, BinanceFuturesClient, ConditionalOrderMigratedError

__all__ = [
    "BinanceFuturesClient",
    "BinanceFuturesAPIError",
    "ConditionalOrderMigratedError",
    "__version__",
]

__version__ = "0.2.0"
