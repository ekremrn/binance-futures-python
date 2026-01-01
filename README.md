## Binance Futures Python Client

High-level REST client for Binance USDⓈ-M (USDT-margined) Futures that covers the major public, trading, account, and user-stream endpoints with automatic HMAC SHA256 signing.

### Features
- Works on both mainnet (`https://fapi.binance.com`) and testnet (`https://demo-fapi.binance.com`) via the `use_testnet` flag.
- Handles `X-MBX-APIKEY` headers, timestamps, recvWindow, and signatures automatically for signed endpoints.
- Retries on common transient failures (HTTP 429/5xx) with a configurable timeout.
- Simple pythonic helpers for order placement, account queries, leverage/margin configuration, and listen-key lifecycle management.
- Automatic routing of STOP/TAKE_PROFIT/TRAILING_STOP orders to the Algo Service with optional fallback for Binance `-4120` STOP_ORDER_SWITCH_ALGO errors.
- Algo order helpers for place/query/cancel (single + cancel-all) and batch order splitting that keeps conditional orders off `/fapi/v1/batchOrders`.

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

### Conditional Orders & Algo Service (effective 2025-12-09)
- STOP/TAKE_PROFIT (limit & market) and TRAILING_STOP_MARKET live on the Algo Service; `/fapi/v1/order` now returns `-4120` (STOP_ORDER_SWITCH_ALGO) for these types.
- `BinanceFuturesClient` auto-routes these orders to `/fapi/v1/algoOrder` when `auto_switch_conditional_to_algo=True` (default) and will retry on `-4120` if you force the legacy route.
- New helpers: `new_algo_order`, `cancel_algo_order`, `cancel_open_algo_orders`, `open_algo_orders`, `all_algo_orders`. `new_test_order` is blocked for conditional types because Binance does not expose a test algo endpoint.
- Query/cancel fallbacks: pass `allow_algo_fallback=True` (or set `attempt_algo_on_not_found=True` on the client) to retry algo lookups when `/order` returns "order not found".
- Batch orders: `new_batch_orders` splits conditional legs to the algo endpoint and sends the rest via `/fapi/v1/batchOrders` so existing batches keep working.
- Behavioral notes from Binance: no margin check before a conditional order triggers, and untriggered conditional orders cannot be modified.

```python
client = BinanceFuturesClient(
    api_key="YOUR_KEY",
    api_secret="YOUR_SECRET",
    auto_switch_conditional_to_algo=True,  # default
)

# Auto-routed stop market (goes to /fapi/v1/algoOrder)
stop = client.new_order(
    symbol="BTCUSDT",
    side="SELL",
    type="STOP_MARKET",
    stopPrice=50000,
    closePosition="true",
)
client.query_algo_order(algoId=stop["algoId"])
client.cancel_algo_order(symbol="BTCUSDT", algoId=stop["algoId"])
client.cancel_open_algo_orders(symbol="BTCUSDT")

# Trailing stop convenience helper
client.new_trailing_stop_order(symbol="BTCUSDT", side="SELL", callbackRate=1.5, quantity=0.01)

# Batch split example: LIMIT stays on /batchOrders, STOP_MARKET is sent individually to algoOrder
client.new_batch_orders(
    [
        {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT", "timeInForce": "GTC", "price": 25000, "quantity": 0.01},
        {"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "stopPrice": 24000, "quantity": 0.01},
    ]
)
```

User-data streams: this client only manages listen keys; ALGO_UPDATE event parsing is not included.

### Endpoint Coverage
- **Public**: ping, time, exchange info, depth, trades, historical trades, agg trades, klines, premium index, funding rate, 24h ticker, price ticker, book ticker, open interest.
- **Trading**: new/test order (conditional types auto-route to Algo), algo order lifecycle (new/query/cancel/cancel-open/open/all), batch orders with conditional split, cancel batch, user trades, open/all orders.
- **Account/Position**: account info, balance, position risk, set leverage, set margin type, adjust position margin, dual-side mode, multi-asset margin, income history, commission rate, leverage brackets.
- **User Stream**: create/keep-alive/close listen keys (API key only).

### Error Handling
- All non-2xx responses raise `BinanceFuturesAPIError` (or `ConditionalOrderMigratedError` for `-4120` STOP_ORDER_SWITCH_ALGO), exposing the HTTP status code and payload.
- Common error hints are surfaced for `-4120` (conditional orders moved to Algo), `-4116` (duplicate `clientOrderId`), and `-4117` (stop order already triggering).
- PriceMatch enum removals and the removal of the `MAX_NUM_ALGO_ORDERS` filter do not require client-side validation; this library does not enforce those fields.

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
