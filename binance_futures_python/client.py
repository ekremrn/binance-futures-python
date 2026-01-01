"""
High-level REST client for the Binance USDⓈ-M (USDT-margined) Futures API.

The client wraps both public and private endpoints, manages request signing,
and exposes helpers for common trading, account, and user-stream workflows.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class BinanceFuturesAPIError(RuntimeError):
    """Raised when Binance returns an error payload."""

    def __init__(self, message: str, status_code: int, response: Response, payload: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.payload = payload


class BinanceFuturesClient:
    """REST client for Binance USDⓈ-M Futures (USDT margined)."""

    MAINNET_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://demo-fapi.binance.com"

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
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
        self.timeout = timeout
        self.base_url = self.TESTNET_URL if use_testnet else self.MAINNET_URL
        self.session = session or requests.Session()

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
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def new_test_order(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol", "side", "type"))
        return self._request("POST", "/fapi/v1/order/test", params=params, signed=True)

    # ---------------------------------------------------------------------
    # Algo Orders (SIGNED) - For STOP_MARKET and TAKE_PROFIT_MARKET
    # ---------------------------------------------------------------------

    def new_stop_loss_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create a STOP_MARKET order using the Algo Order API.
        
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
        """
        self._ensure_required(params, ("symbol", "side", "stopPrice"))
        return self._request("POST", "/fapi/v1/order/stopLoss", params=params, signed=True)

    def new_take_profit_order(self, **params: Any) -> Dict[str, Any]:
        """
        Create a TAKE_PROFIT_MARKET order using the Algo Order API.
        
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
        """
        self._ensure_required(params, ("symbol", "side", "stopPrice"))
        return self._request("POST", "/fapi/v1/order/takeProfit", params=params, signed=True)

    def query_order(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol",))
        return self._request("GET", "/fapi/v1/order", params=params, signed=True)

    def cancel_order(self, **params: Any) -> Dict[str, Any]:
        self._ensure_required(params, ("symbol",))
        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

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
        else:
            message = str(payload)
            
        raise BinanceFuturesAPIError(
            message or "Binance API error", 
            response.status_code, 
            response, 
            payload
        )
