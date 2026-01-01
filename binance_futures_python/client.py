"""
High-level REST client for the Binance USDⓈ-M (USDT-margined) Futures API.

The client wraps both public and private endpoints, manages request signing,
and exposes helpers for common trading, account, and user-stream workflows.
"""
from __future__ import annotations

import json
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Module-level logger for algo order operations
_logger = logging.getLogger(__name__)


class BinanceFuturesAPIError(RuntimeError):
    """Raised when Binance returns an error payload."""

    def __init__(self, message: str, status_code: int, response: Response, payload: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.payload = payload
        # Extract error code from payload
        self.error_code = None
        if isinstance(payload, dict):
            self.error_code = payload.get("code")


class ConditionalOrderMigratedError(BinanceFuturesAPIError):
    """Raised when conditional orders hit the legacy endpoint instead of Algo."""


class BinanceFuturesClient:
    """REST client for Binance USDⓈ-M Futures (USDT margined)."""

    MAINNET_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://demo-fapi.binance.com"
    CONDITIONAL_ORDER_TYPES = {
        "STOP_MARKET",
        "TAKE_PROFIT_MARKET",
        "STOP",
        "TAKE_PROFIT",
        "TRAILING_STOP_MARKET",
    }
    ORDER_NOT_FOUND_CODES = {-2013, -2011}
    ERROR_HINTS = {
        -4120: "Conditional orders migrated to Algo Service; use /fapi/v1/algoOrder (effective 2025-12-09).",
        -4116: "Duplicate clientOrderId; supply a unique client order id.",
        -4117: "Stop order already triggering; retry is not allowed during trigger.",
    }

    def __init__(
        self,
        api_key: Optional[str],
        api_secret: Optional[str],
        *,
        use_testnet: bool = False,
        recv_window: int = 5000,
        timeout: int = 10,
        max_retries: int = 3,
        session: Optional[Session] = None,
        auto_switch_conditional_to_algo: bool = True,
        attempt_algo_on_not_found: bool = False,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
        self.timeout = timeout
        self.base_url = self.TESTNET_URL if use_testnet else self.MAINNET_URL
        self.session = session or requests.Session()
        self.auto_switch_conditional_to_algo = auto_switch_conditional_to_algo
        self.attempt_algo_on_not_found = attempt_algo_on_not_found

        retry = Retry(
            total=max_retries,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=False,  # retry on every verb
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # ---------------------------------------------------------------------
    # Public endpoints
    # ---------------------------------------------------------------------

    def ping(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/ping")

    def get_server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/time")

    def get_exchange_info(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/exchangeInfo", params=params)

    def get_order_book(self, symbol: str, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/depth", params={"symbol": symbol, "limit": limit})

    def get_recent_trades(self, symbol: str, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/trades", params={"symbol": symbol, "limit": limit})

    def get_historical_trades(
        self,
        symbol: str,
        limit: Optional[int] = None,
        from_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._request(
            "GET", "/fapi/v1/historicalTrades", params={"symbol": symbol, "limit": limit, "fromId": from_id}
        )

    def get_aggregate_trades(
        self,
        symbol: str,
        from_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {
            "symbol": symbol,
            "fromId": from_id,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request("GET", "/fapi/v1/aggTrades", params=params)

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request("GET", "/fapi/v1/klines", params=params)

    def get_premium_index(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/premiumIndex", params=params)

    def get_funding_rate_history(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/fundingRate", params=params)

    def get_24h_ticker(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/ticker/24hr", params=params)

    def get_symbol_price_ticker(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/ticker/price", params=params)

    def get_book_ticker(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/ticker/bookTicker", params=params)

    def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/openInterest", params={"symbol": symbol})

    def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch open interest history (statistics endpoint)."""
        params = {
            "symbol": symbol,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/futures/data/openInterestHist", params=params)

    def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch long/short account ratio."""
        params = {
            "symbol": symbol,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/futures/data/globalLongShortAccountRatio", params=params)

    def get_top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch top trader long/short account ratio."""
        params = {
            "symbol": symbol,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/futures/data/topLongShortAccountRatio", params=params)

    def get_taker_buy_sell_volume(
        self,
        symbol: str,
        period: str = "5m",
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch taker buy/sell volume ratio."""
        params = {
            "symbol": symbol,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/futures/data/takerlongshortRatio", params=params)

    # ---------------------------------------------------------------------
    # Trading (SIGNED)
    # ---------------------------------------------------------------------

    def new_order(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol", "side", "type"))
        order_type = self._normalize_order_type(params.get("type"))
        params["type"] = order_type
        force_rest_route = bool(params.pop("_force_rest_route", False))

        if self.auto_switch_conditional_to_algo and self._is_conditional_type(order_type) and not force_rest_route:
            return self.new_algo_order(**params)

        try:
            return self._request("POST", "/fapi/v1/order", params=params, signed=True)
        except BinanceFuturesAPIError as exc:
            if exc.error_code == -4120 and self.auto_switch_conditional_to_algo:
                _logger.info("Retrying conditional order via algo endpoint after STOP_ORDER_SWITCH_ALGO")
                return self.new_algo_order(**params)
            raise

    def new_test_order(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol", "side", "type"))
        order_type = self._normalize_order_type(params.get("type"))
        if self._is_conditional_type(order_type):
            raise ValueError(
                "Conditional orders migrated to Algo Service; Binance does not provide /order/test for these types. "
                "Use new_algo_order/new_stop_loss_order/new_take_profit_order instead."
            )

        params["type"] = order_type
        return self._request("POST", "/fapi/v1/order/test", params=params, signed=True)

    def new_batch_orders(self, orders: List[Dict[str, Any]], *, auto_split_conditional: bool = True, **params: Any) -> Dict[str, Any]:
        """
        Create multiple orders in a single request, safely handling conditional order migration.

        If any order in the batch is a conditional type, it will be sent individually to the
        algo endpoint when auto_split_conditional=True. Set auto_split_conditional=False to
        raise when conditional types are found.
        """
        if not orders:
            raise ValueError("orders list is required for batch placement.")

        conditional_orders: List[Dict[str, Any]] = []
        regular_orders: List[Dict[str, Any]] = []
        shared_params = {k: v for k, v in params.items() if v is not None}

        for order in orders:
            if not isinstance(order, dict):
                raise ValueError("Each order must be a dict of order parameters.")

            order_copy = order.copy()
            self._ensure_required(order_copy, ("symbol", "side", "type"))
            order_copy["type"] = self._normalize_order_type(order_copy.get("type"))

            if self._is_conditional_type(order_copy["type"]):
                conditional_orders.append(order_copy)
            else:
                regular_orders.append(order_copy)

        result: Dict[str, Any] = {"regular": None, "conditional": []}

        if conditional_orders and not auto_split_conditional:
            raise ValueError(
                "Batch contains conditional order types. Route them via the Algo endpoint or enable auto_split_conditional."
            )

        if regular_orders:
            payload = {"batchOrders": json.dumps(regular_orders), **shared_params}
            result["regular"] = self._request("POST", "/fapi/v1/batchOrders", params=payload, signed=True)

        if conditional_orders:
            for order in conditional_orders:
                order_payload = {**shared_params, **order}
                result["conditional"].append(self.new_algo_order(**order_payload))

        return result

    # ---------------------------------------------------------------------
    # Stop-loss and Take-profit Orders (SIGNED)
    # These methods use the Algo Order API with automatic fallback
    # ---------------------------------------------------------------------

    def new_stop_loss_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create a STOP_MARKET order using the Algo Order API.
        
        As of 2025-12-09, stop-loss orders must use the algo endpoint.
        This method automatically handles the -4120 error and retries via algo API.
        
        Required params:
        - symbol: str
        - side: "BUY" or "SELL"
        - stopPrice: float or str
        
        Optional params:
        - quantity: float or str (required if closePosition is not "true")
        - closePosition: "true" or "false" (default: "false")
        - reduceOnly: "true" or "false"
        - priceProtect: "true" or "false"
        - workingType: "MARK_PRICE" or "CONTRACT_PRICE"
        - positionSide: "LONG" or "SHORT" (required for Hedge Mode)
        
        Returns:
        - On success via algo API: {"algoId": int, "success": bool, ...}
        - The response includes "_via_algo_api": True to distinguish from regular orders
        """
        self._ensure_required(params, ("symbol", "side", "stopPrice"))
        
        # Apply guardrails and prepare params for algo API
        params_copy = self._prepare_algo_order_params(params.copy())
        params_copy["type"] = "STOP_MARKET"
        
        # Log the algo order request (no secrets)
        _logger.info(
            "Algo order request: endpoint=/fapi/v1/algoOrder, symbol=%s, side=%s, "
            "type=STOP_MARKET, triggerPrice=%s, closePosition=%s",
            params_copy.get("symbol"),
            params_copy.get("side"),
            params_copy.get("stopPrice"),
            params_copy.get("closePosition", "false")
        )
        
        result = self.new_algo_order(**params_copy)
        result["_via_algo_api"] = True
        return result

    def new_take_profit_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create a TAKE_PROFIT_MARKET order using the Algo Order API.
        
        As of 2025-12-09, take-profit orders must use the algo endpoint.
        This method automatically handles the -4120 error and retries via algo API.
        
        Required params:
        - symbol: str
        - side: "BUY" or "SELL"
        - stopPrice: float or str
        
        Optional params:
        - quantity: float or str (required if closePosition is not "true")
        - closePosition: "true" or "false" (default: "false")
        - reduceOnly: "true" or "false"
        - priceProtect: "true" or "false"
        - workingType: "MARK_PRICE" or "CONTRACT_PRICE"
        - positionSide: "LONG" or "SHORT" (required for Hedge Mode)
        
        Returns:
        - On success via algo API: {"algoId": int, "success": bool, ...}
        - The response includes "_via_algo_api": True to distinguish from regular orders
        """
        self._ensure_required(params, ("symbol", "side", "stopPrice"))
        
        # Apply guardrails and prepare params for algo API
        params_copy = self._prepare_algo_order_params(params.copy())
        params_copy["type"] = "TAKE_PROFIT_MARKET"
        
        # Log the algo order request (no secrets)
        _logger.info(
            "Algo order request: endpoint=/fapi/v1/algoOrder, symbol=%s, side=%s, "
            "type=TAKE_PROFIT_MARKET, triggerPrice=%s, closePosition=%s",
            params_copy.get("symbol"),
            params_copy.get("side"),
            params_copy.get("stopPrice"),
            params_copy.get("closePosition", "false")
        )
        
        result = self.new_algo_order(**params_copy)
        result["_via_algo_api"] = True
        return result

    def new_trailing_stop_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create a TRAILING_STOP_MARKET order using the Algo Order API.
        
        As of 2025-12-09, trailing stop orders must use the algo endpoint.
        
        Required params:
        - symbol: str
        - side: "BUY" or "SELL"
        - callbackRate: float or str (callback rate in percentage, e.g., 1.5 for 1.5%)
        
        Optional params:
        - quantity: float or str (required if closePosition is not "true")
        - activationPrice: float or str (price to trigger the trailing stop)
        - closePosition: "true" or "false" (default: "false")
        - reduceOnly: "true" or "false"
        - priceProtect: "true" or "false"
        - workingType: "MARK_PRICE" or "CONTRACT_PRICE"
        - positionSide: "LONG" or "SHORT" (required for Hedge Mode)
        
        Returns:
        - On success via algo API: {"algoId": int, "success": bool, ...}
        - The response includes "_via_algo_api": True to distinguish from regular orders
        """
        self._ensure_required(params, ("symbol", "side", "callbackRate"))
        
        # Apply guardrails and prepare params for algo API
        params_copy = self._prepare_algo_order_params(params.copy())
        params_copy["type"] = "TRAILING_STOP_MARKET"
        
        # Log the algo order request (no secrets)
        _logger.info(
            "Algo order request: endpoint=/fapi/v1/algoOrder, symbol=%s, side=%s, "
            "type=TRAILING_STOP_MARKET, callbackRate=%s, activationPrice=%s, closePosition=%s",
            params_copy.get("symbol"),
            params_copy.get("side"),
            params_copy.get("callbackRate"),
            params_copy.get("activationPrice"),
            params_copy.get("closePosition", "false")
        )
        
        result = self.new_algo_order(**params_copy)
        result["_via_algo_api"] = True
        return result

    # ---------------------------------------------------------------------
    # Algo Order API (SIGNED) - For conditional orders as of 2025-12-09
    # ---------------------------------------------------------------------

    def new_algo_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create an algo order (conditional order) using the Algo Order API.
        
        As of 2025-12-09, Binance migrated STOP_MARKET, TAKE_PROFIT_MARKET, STOP,
        TAKE_PROFIT, and TRAILING_STOP_MARKET to the Algo Service.
        
        IMPORTANT: This method automatically sets algoType="CONDITIONAL" which is
        mandatory for the /fapi/v1/algoOrder endpoint.
        
        Required params:
        - symbol: str
        - side: "BUY" or "SELL"
        - type: "STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT", "TRAILING_STOP_MARKET"
        - stopPrice: float or str (for STOP_MARKET, TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT)
        - activationPrice: float or str (for TRAILING_STOP_MARKET)
        - callbackRate: float or str (for TRAILING_STOP_MARKET)
        
        Optional params:
        - quantity: float or str (required if closePosition is not "true")
        - price: float or str (required for STOP and TAKE_PROFIT limit orders)
        - closePosition: "true" or "false"
        - reduceOnly: "true" or "false"
        - priceProtect: "true" or "false"
        - workingType: "MARK_PRICE" or "CONTRACT_PRICE"
        - positionSide: "LONG" or "SHORT" (required for Hedge Mode)
        
        Returns:
        {
            "algoId": 14517910,
            "success": true,
            "code": 0,
            "msg": "OK"
        }
        """
        self._ensure_required(params, ("symbol", "side", "type"))
        
        # Apply guardrails for closePosition and Hedge Mode
        params = self._prepare_algo_order_params(params.copy())
        params["type"] = self._normalize_order_type(params["type"])
        
        # MANDATORY: algoType must be "CONDITIONAL" for /fapi/v1/algoOrder
        # This is required by Binance and currently only supports "CONDITIONAL"
        params["algoType"] = "CONDITIONAL"
        
        _logger.debug(
            "Sending algo order: symbol=%s, side=%s, type=%s, algoType=%s",
            params.get("symbol"),
            params.get("side"),
            params.get("type"),
            params.get("algoType")
        )
        
        response = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        if isinstance(response, dict):
            response["_via_algo_api"] = True
        return response

    def cancel_algo_order(self, **params: Any) -> Dict[str, Any]:
        """
        Cancel an algo order.
        
        Required params:
        - symbol: str
        - algoId: int
        
        Returns:
        {
            "algoId": 14517910,
            "success": true,
            "code": 0,
            "msg": "OK"
        }
        """
        self._ensure_required(params, ("symbol", "algoId"))
        return self._request("DELETE", "/fapi/v1/algoOrder", params=params, signed=True)

    def cancel_open_algo_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel all open algo orders (optionally scoped to a symbol).
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("DELETE", "/fapi/v1/algoOpenOrders", params=params, signed=True)

    def query_algo_order(self, **params: Any) -> Dict[str, Any]:
        """
        Query a specific algo order.
        
        Required params:
        - symbol: str (optional but recommended)
        - algoId: int
        
        Returns detailed algo order information.
        """
        self._ensure_required(params, ("algoId",))
        return self._request("GET", "/fapi/v1/algoOrder", params=params, signed=True)

    def get_open_algo_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all open algo orders.
        
        Optional params:
        - symbol: str (if not provided, returns for all symbols)
        
        Returns list of open algo orders.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/openAlgoOrders", params=params, signed=True)

    def open_algo_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Alias for get_open_algo_orders."""
        return self.get_open_algo_orders(symbol=symbol)

    def get_algo_order_history(self, **params: Any) -> Dict[str, Any]:
        """
        Get algo order history.
        
        Optional params:
        - symbol: str
        - side: "BUY" or "SELL"
        - startTime: int (timestamp in ms)
        - endTime: int (timestamp in ms)
        - page: int (default 1)
        - pageSize: int (default 100, max 100)
        
        Returns historical algo orders.
        """
        return self._request("GET", "/fapi/v1/allAlgoOrders", params=params, signed=True)

    def all_algo_orders(self, **params: Any) -> Dict[str, Any]:
        """Alias for get_algo_order_history."""
        return self.get_algo_order_history(**params)

    def query_order(self, allow_algo_fallback: Optional[bool] = None, **params: Any) -> Dict[str, Any]:
        algo_id = params.pop("algoOrderId", None) or params.pop("algoId", None)
        prefer_algo_direct = algo_id is not None and not params.get("orderId") and not params.get("origClientOrderId")
        fallback_enabled = self.attempt_algo_on_not_found if allow_algo_fallback is None else allow_algo_fallback

        if prefer_algo_direct:
            return self.query_algo_order(algoId=algo_id, symbol=params.get("symbol"))

        self._ensure_required(params, ("symbol",))
        try:
            return self._request("GET", "/fapi/v1/order", params=params, signed=True)
        except BinanceFuturesAPIError as exc:
            if fallback_enabled and algo_id is not None and self._is_order_not_found(exc):
                return self.query_algo_order(algoId=algo_id, symbol=params.get("symbol"))
            raise

    def cancel_order(self, allow_algo_fallback: Optional[bool] = None, **params: Any) -> Dict[str, Any]:
        algo_id = params.pop("algoOrderId", None) or params.pop("algoId", None)
        prefer_algo_direct = algo_id is not None and not params.get("orderId") and not params.get("origClientOrderId")
        fallback_enabled = self.attempt_algo_on_not_found if allow_algo_fallback is None else allow_algo_fallback

        if prefer_algo_direct:
            return self.cancel_algo_order(symbol=params.get("symbol"), algoId=algo_id)

        self._ensure_required(params, ("symbol",))
        try:
            return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
        except BinanceFuturesAPIError as exc:
            if fallback_enabled and algo_id is not None and self._is_order_not_found(exc):
                return self.cancel_algo_order(symbol=params.get("symbol"), algoId=algo_id)
            raise

    def cancel_all_open_orders(self, symbol: str) -> Dict[str, Any]:
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol}, signed=True)

    def cancel_batch_orders(self, **params: Any) -> Dict[str, Any]:
        return self._request("DELETE", "/fapi/v1/batchOrders", params=params, signed=True)

    def get_open_orders(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def get_all_orders(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol",))
        return self._request("GET", "/fapi/v1/allOrders", params=params, signed=True)

    def get_user_trades(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol",))
        return self._request("GET", "/fapi/v1/userTrades", params=params, signed=True)

    # ---------------------------------------------------------------------
    # Account & position endpoints (SIGNED)
    # ---------------------------------------------------------------------

    def get_account_information(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/account", params=params, signed=True)

    def get_account_balance(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/balance", params=params, signed=True)

    def get_position_risk(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        params = {"symbol": symbol, "leverage": leverage}
        return self._request("POST", "/fapi/v1/leverage", params=params, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        params = {"symbol": symbol, "marginType": margin_type}
        return self._request("POST", "/fapi/v1/marginType", params=params, signed=True)

    def adjust_position_margin(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol", "positionSide", "amount", "type"))
        return self._request("POST", "/fapi/v1/positionMargin", params=params, signed=True)

    def set_position_side_dual(self, dual_side_position: bool) -> Dict[str, Any]:
        params = {"dualSidePosition": "true" if dual_side_position else "false"}
        return self._request("POST", "/fapi/v1/positionSide/dual", params=params, signed=True)

    def get_position_side_dual(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/positionSide/dual", signed=True)

    def set_multi_assets_margin(self, multi_assets_margin: bool) -> Dict[str, Any]:
        params = {"multiAssetsMargin": "true" if multi_assets_margin else "false"}
        return self._request("POST", "/fapi/v1/multiAssetsMargin", params=params, signed=True)

    def get_multi_assets_margin(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/multiAssetsMargin", signed=True)

    def get_income_history(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/income", params=params, signed=True)

    def get_commission_rate(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/commissionRate", params={"symbol": symbol}, signed=True)

    def get_leverage_brackets(self, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/leverageBracket", params=params, signed=True)

    # ---------------------------------------------------------------------
    # User stream (API key only)
    # ---------------------------------------------------------------------

    def create_listen_key(self) -> Dict[str, Any]:
        return self._request("POST", "/fapi/v1/listenKey", send_api_key=True)

    def keepalive_listen_key(self, listen_key: str) -> Dict[str, Any]:
        return self._request("PUT", "/fapi/v1/listenKey", params={"listenKey": listen_key}, send_api_key=True)

    def close_listen_key(self, listen_key: str) -> Dict[str, Any]:
        return self._request("DELETE", "/fapi/v1/listenKey", params={"listenKey": listen_key}, send_api_key=True)

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        send_api_key: bool = False,
    ) -> Dict[str, Any]:
        params = self._clean_params(params)
        headers: Dict[str, str] = {}

        if signed:
            self._require_credentials()
            headers["X-MBX-APIKEY"] = self._require_api_key()
            params = self._sign_params(params)
        elif send_api_key:
            headers["X-MBX-APIKEY"] = self._require_api_key()

        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params if method.upper() == "GET" else None,
                data=params if method.upper() != "GET" else None,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Network error calling Binance Futures API: {exc}") from exc

        if not response.ok:
            self._raise_api_error(response)
        return response.json()

    def _require_credentials(self) -> None:
        if not self.api_key:
            raise ValueError("API key is required for this endpoint.")
        if not self.api_secret:
            raise ValueError("API secret is required for this endpoint.")

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise ValueError("API key is required for this endpoint.")
        return self.api_key

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_secret:
            raise ValueError("API secret is required for signed endpoints.")

        params = params.copy()
        params.setdefault("timestamp", int(time.time() * 1000))
        params.setdefault("recvWindow", self.recv_window)
        query = urlencode(params, doseq=True)
        signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        params["signature"] = signature
        return params

    def _prepare_algo_order_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply guardrails and prepare parameters for algo order API.
        
        Guardrails:
        1. If closePosition=true, remove quantity and reduceOnly (Binance rejects them)
        2. In Hedge Mode, ensure positionSide is sent
        
        Args:
            params: Order parameters (will be modified in place)
            
        Returns:
            Modified params dict ready for algo order API
        """
        # Guardrail 1: If closePosition is "true", do NOT send quantity or reduceOnly
        # Binance rejects algo orders with quantity when closePosition=true
        close_position = str(params.get("closePosition", "")).lower()
        if close_position == "true":
            if "quantity" in params:
                _logger.debug(
                    "Removing 'quantity' from algo order params because closePosition=true"
                )
                del params["quantity"]
            if "reduceOnly" in params:
                _logger.debug(
                    "Removing 'reduceOnly' from algo order params because closePosition=true"
                )
                del params["reduceOnly"]
        
        # Guardrail 2: In Hedge Mode, positionSide is required
        # If user didn't provide it, we try to infer from position mode
        # but caller should explicitly pass positionSide when in Hedge Mode
        if "positionSide" not in params:
            _logger.debug(
                "positionSide not provided - if using Hedge Mode, orders may fail"
            )
        
        return params

    @staticmethod
    def _clean_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not params:
            return {}
        return {k: v for k, v in params.items() if v is not None}

    @staticmethod
    def _ensure_required(params: Dict[str, Any], fields: tuple[str, ...]) -> None:
        missing = [field for field in fields if params.get(field) is None]
        if missing:
            raise ValueError(f"Missing required parameter(s): {', '.join(missing)}")

    def _raise_api_error(self, response: Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text or "<empty>"
        
        # Extract error message from various possible keys
        if isinstance(payload, dict):
            message = (
                payload.get("msg") or 
                payload.get("message") or 
                payload.get("error") or
                str(payload)
            )
            error_code = payload.get("code")
        else:
            message = str(payload)
            error_code = None
        
        hint = self.ERROR_HINTS.get(error_code)
        if hint:
            message = f"{message} | Hint: {hint}"
        
        exc_class = ConditionalOrderMigratedError if error_code == -4120 else BinanceFuturesAPIError
            
        raise exc_class(
            message or "Binance API error", 
            response.status_code, 
            response, 
            payload
        )

    def _is_conditional_type(self, order_type: Optional[str]) -> bool:
        if not order_type:
            return False
        return self._normalize_order_type(order_type) in self.CONDITIONAL_ORDER_TYPES

    @staticmethod
    def _normalize_order_type(order_type: Any) -> str:
        return str(order_type).upper()

    def _is_order_not_found(self, exc: BinanceFuturesAPIError) -> bool:
        return getattr(exc, "error_code", None) in self.ORDER_NOT_FOUND_CODES or exc.status_code == 404
