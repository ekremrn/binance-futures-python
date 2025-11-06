## Binance Futures Python Client

High-level REST client for Binance USDⓈ-M (USDT-margined) Futures that covers the major public, trading, account, and user-stream endpoints with automatic HMAC SHA256 signing.

### Features
- Works on both mainnet (`https://fapi.binance.com`) and testnet (`https://demo-fapi.binance.com`) via the `use_testnet` flag.
- Handles `X-MBX-APIKEY` headers, timestamps, recvWindow, and signatures automatically for signed endpoints.
- Retries on common transient failures (HTTP 429/5xx) with a configurable timeout.
- Simple pythonic helpers for order placement, account queries, leverage/margin configuration, and listen-key lifecycle management.

### Installation
The project ships as a proper Python library (see `pyproject.toml`). Install it into your environment with pip:

```bash
pip install .
```

or install straight from a git checkout:

```bash
pip install git+https://github.com/your-org/binance-futures-python.git
```

The single runtime dependency is `requests>=2.31.0` (declared in `pyproject.toml` and `requirements.txt` for convenience).
Older `pip` releases (<22) sometimes mis-handle pure `pyproject.toml` metadata, so the repository also ships legacy `setup.cfg`/`setup.py` files for compatibility—nevertheless, upgrading `pip`/`setuptools` is recommended.

### Quick Start
```python
from binance_futures_python import BinanceFuturesClient

client = BinanceFuturesClient(
    api_key="YOUR_KEY",
    api_secret="YOUR_SECRET",
    use_testnet=True,  # False for mainnet
)

# Public data
server_time = client.get_server_time()

# Account & trading
client.set_leverage("BTCUSDT", 15)
order = client.new_order(
    symbol="BTCUSDT",
    side="BUY",
    type="MARKET",
    quantity=0.001,
)

print(order)
```

### Endpoint Coverage
- **Public**: ping, time, exchange info, depth, trades, historical trades, agg trades, klines, premium index, funding rate, 24h ticker, price ticker, book ticker, open interest.
- **Trading**: new/test order, query/cancel order(s), cancel batch, user trades, open/all orders.
- **Account/Position**: account info, balance, position risk, set leverage, set margin type, adjust position margin, dual-side mode, multi-asset margin, income history, commission rate, leverage brackets.
- **User Stream**: create/keep-alive/close listen keys (API key only).

### Error Handling
All non-2xx responses raise `BinanceFuturesAPIError`, exposing the HTTP status code and payload so you can react programmatically.

### Development & Packaging
- Build distribution artifacts (wheel + sdist) locally:

  ```bash
  python3 -m build
  ```

- Run a quick syntax check to ensure everything compiles before publishing:

  ```bash
  PYTHONPYCACHEPREFIX=/tmp python3 -m compileall -q binance-futures-python
  ```

- Publish with Twine once you have an index to push to:

  ```bash
  twine upload dist/*
  ```

> **Note:** This library was generated with Codex automation to speed up development. While the critical flows are covered, please review the code and test thoroughly before trading with live capital—bugs or breaking API changes may still exist.
