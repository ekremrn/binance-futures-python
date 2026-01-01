"""
Unit tests for Algo Order API integration.

Tests verify:
- Conditional orders route to /fapi/v1/algoOrder
- Non-conditional orders route to /fapi/v1/order
- Proper handling of algoId vs orderId
- Mandatory algoType="CONDITIONAL" is included in all algo order calls
- Guardrails for closePosition and Hedge Mode
- Error handling and logging
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json

from binance_futures_python.client import (
    BinanceFuturesAPIError,
    BinanceFuturesClient,
    ConditionalOrderMigratedError,
)


class TestAlgoOrderAPI(unittest.TestCase):
    """Test Algo Order API functionality."""
    
    def setUp(self):
        """Set up test client."""
        self.client = BinanceFuturesClient(
            api_key="test_key",
            api_secret="test_secret",
            use_testnet=True
        )
    
    def test_error_code_extraction(self):
        """Test that error codes are properly extracted from API responses."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.ok = False
        mock_response.json.return_value = {
            "code": -4120,
            "msg": "Order type not supported for this endpoint"
        }
        
        with self.assertRaises(ConditionalOrderMigratedError) as context:
            self.client._raise_api_error(mock_response)
        
        self.assertEqual(context.exception.error_code, -4120)
        self.assertEqual(context.exception.status_code, 400)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_stop_loss_uses_algo_api(self, mock_request):
        """Test that stop-loss orders use the Algo Order API."""
        # Mock algo order response
        mock_request.return_value = {
            "algoId": 12345,
            "success": True,
            "code": 0,
            "msg": "OK"
        }
        
        result = self.client.new_stop_loss_order(
            symbol="BTCUSDT",
            side="SELL",
            stopPrice=50000.0,
            closePosition="true"
        )
        
        # Verify algo endpoint was called
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOrder")
        self.assertTrue(call_args[1]["signed"])
        
        # CRITICAL: Verify algoType="CONDITIONAL" is included (mandatory param)
        params = call_args[1]["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL",
            "algoType='CONDITIONAL' is MANDATORY for /fapi/v1/algoOrder")
        
        # Verify params include type=STOP_MARKET
        params = call_args[1]["params"]
        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["side"], "SELL")
        
        # Verify response indicates algo API usage
        self.assertTrue(result.get("_via_algo_api"))
        self.assertEqual(result.get("algoId"), 12345)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_take_profit_uses_algo_api(self, mock_request):
        """Test that take-profit orders use the Algo Order API."""
        # Mock algo order response
        mock_request.return_value = {
            "algoId": 67890,
            "success": True,
            "code": 0,
            "msg": "OK"
        }
        
        result = self.client.new_take_profit_order(
            symbol="ETHUSDT",
            side="BUY",
            stopPrice=3000.0,
            quantity=1.5,
            reduceOnly="true"
        )
        
        # Verify algo endpoint was called
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOrder")
        
        # Verify params include type=TAKE_PROFIT_MARKET
        params = call_args[1]["params"]
        self.assertEqual(params["type"], "TAKE_PROFIT_MARKET")
        self.assertEqual(params["symbol"], "ETHUSDT")
        
        # Verify response indicates algo API usage
        self.assertTrue(result.get("_via_algo_api"))
        self.assertEqual(result.get("algoId"), 67890)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_market_order_uses_regular_api(self, mock_request):
        """Test that market orders still use the regular order API."""
        mock_request.return_value = {
            "orderId": 11111,
            "symbol": "BTCUSDT",
            "status": "FILLED"
        }
        
        result = self.client.new_order(
            symbol="BTCUSDT",
            side="BUY",
            type="MARKET",
            quantity=0.1
        )
        
        # Verify regular order endpoint was called
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertEqual(call_args[0][1], "/fapi/v1/order")
        
        # Verify response has orderId (not algoId)
        self.assertEqual(result.get("orderId"), 11111)
        self.assertIsNone(result.get("_via_algo_api"))

    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_new_order_routes_conditional_to_algo(self, mock_request):
        """Conditional types are routed to algo endpoint automatically."""
        mock_request.return_value = {
            "algoId": 555,
            "success": True
        }

        result = self.client.new_order(
            symbol="BTCUSDT",
            side="SELL",
            type="STOP_MARKET",
            stopPrice=25000.0
        )

        call_args = mock_request.call_args
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOrder")
        self.assertTrue(result.get("_via_algo_api"))
        self.assertEqual(result.get("algoId"), 555)

    @patch('binance_futures_python.client.BinanceFuturesClient.new_algo_order')
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_new_order_retries_on_stop_switch_error(self, mock_request, mock_new_algo):
        """STOP_ORDER_SWITCH_ALGO triggers fallback to algo endpoint."""
        mock_response = Mock()
        mock_response.status_code = 400
        stop_error = ConditionalOrderMigratedError(
            "STOP_ORDER_SWITCH_ALGO",
            400,
            mock_response,
            {"code": -4120, "msg": "STOP_ORDER_SWITCH_ALGO"},
        )
        mock_request.side_effect = stop_error

        mock_new_algo.return_value = {"algoId": 777, "success": True, "_via_algo_api": True}

        result = self.client.new_order(
            symbol="BTCUSDT",
            side="SELL",
            type="STOP_MARKET",
            stopPrice=23000.0,
            _force_rest_route=True
        )

        mock_new_algo.assert_called_once()
        self.assertEqual(mock_request.call_args[0][1], "/fapi/v1/order")
        self.assertEqual(result.get("algoId"), 777)
        self.assertTrue(result.get("_via_algo_api"))

    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_cancel_algo_order(self, mock_request):
        """Test canceling an algo order."""
        mock_request.return_value = {
            "algoId": 12345,
            "success": True,
            "code": 0,
            "msg": "OK"
        }
        
        result = self.client.cancel_algo_order(
            symbol="BTCUSDT",
            algoId=12345
        )
        
        # Verify DELETE was called on algo endpoint
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "DELETE")
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOrder")
        self.assertTrue(result.get("success"))
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_query_algo_order(self, mock_request):
        """Test querying an algo order."""
        mock_request.return_value = {
            "algoId": 12345,
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "status": "WORKING"
        }
        
        result = self.client.query_algo_order(algoId=12345)
        
        # Verify GET was called on algo endpoint
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "GET")
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOrder")
        self.assertEqual(result["algoId"], 12345)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_get_open_algo_orders(self, mock_request):
        """Test getting all open algo orders."""
        mock_request.return_value = {
            "total": 2,
            "data": [
                {"algoId": 12345, "symbol": "BTCUSDT", "status": "WORKING"},
                {"algoId": 67890, "symbol": "ETHUSDT", "status": "WORKING"}
            ]
        }
        
        result = self.client.get_open_algo_orders()
        
        # Verify GET was called on openAlgoOrders endpoint
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "GET")
        self.assertEqual(call_args[0][1], "/fapi/v1/openAlgoOrders")
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["data"]), 2)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_get_open_algo_orders_for_symbol(self, mock_request):
        """Test getting open algo orders for specific symbol."""
        mock_request.return_value = {
            "total": 1,
            "data": [
                {"algoId": 12345, "symbol": "BTCUSDT", "status": "WORKING"}
            ]
        }
        
        result = self.client.get_open_algo_orders(symbol="BTCUSDT")
        
        # Verify symbol was passed in params
        call_args = mock_request.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(result["total"], 1)
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_algo_order_with_all_params(self, mock_request):
        """Test algo order with all optional parameters."""
        mock_request.return_value = {
            "algoId": 99999,
            "success": True
        }
        
        result = self.client.new_algo_order(
            symbol="BTCUSDT",
            side="SELL",
            type="STOP_MARKET",
            stopPrice=50000.0,
            quantity=0.5,
            reduceOnly="true",
            priceProtect="true",
            workingType="MARK_PRICE"
        )
        
        # Verify all params were passed
        call_args = mock_request.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["side"], "SELL")
        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["stopPrice"], 50000.0)
        self.assertEqual(params["quantity"], 0.5)
        self.assertEqual(params["reduceOnly"], "true")
        self.assertEqual(params["priceProtect"], "true")
        self.assertEqual(params["workingType"], "MARK_PRICE")


class TestOrderIDFormatting(unittest.TestCase):
    """Test order ID formatting for algo vs regular orders."""
    
    def test_algo_order_id_format(self):
        """Test that algo orders return algoId in response."""
        response = {
            "algoId": 12345,
            "success": True,
            "_via_algo_api": True
        }
        
        # Simulating trading-agent parsing
        if response.get("_via_algo_api"):
            order_id = f"algo:{response.get('algoId')}"
        else:
            order_id = f"order:{response.get('orderId')}"
        
        self.assertEqual(order_id, "algo:12345")
    
    def test_regular_order_id_format(self):
        """Test that regular orders return orderId in response."""
        response = {
            "orderId": 98765,
            "symbol": "BTCUSDT",
            "status": "FILLED"
        }
        
        # Simulating trading-agent parsing
        if response.get("_via_algo_api"):
            order_id = f"algo:{response.get('algoId')}"
        else:
            order_id = f"order:{response.get('orderId')}"
        
        self.assertEqual(order_id, "order:98765")


class TestAlgoTypeConditional(unittest.TestCase):
    """
    Test suite verifying algoType='CONDITIONAL' is ALWAYS included in algo order payloads.
    
    This is the critical fix for:
    "Mandatory parameter 'algotype' was not sent, was empty/null, or malformed."
    """
    
    def setUp(self):
        """Set up test client."""
        self.client = BinanceFuturesClient(
            api_key="test_key",
            api_secret="test_secret",
            use_testnet=True
        )
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_algo_order_includes_algo_type_conditional(self, mock_request):
        """
        Test that new_algo_order ALWAYS includes algoType='CONDITIONAL'.
        
        This is the root cause fix for the Binance error:
        "Mandatory parameter 'algotype' was not sent, was empty/null, or malformed."
        """
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        self.client.new_algo_order(
            symbol="BTCUSDT",
            side="SELL",
            type="STOP_MARKET",
            stopPrice=50000.0,
            quantity=0.1
        )
        
        call_args = mock_request.call_args
        params = call_args[1]["params"]
        
        # THE KEY ASSERTION: algoType MUST be "CONDITIONAL"
        self.assertIn("algoType", params, 
            "algoType parameter is MISSING from request - this is the root cause!")
        self.assertEqual(params["algoType"], "CONDITIONAL",
            "algoType must be 'CONDITIONAL' - Binance only supports this value")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_stop_loss_order_includes_algo_type_conditional(self, mock_request):
        """Test that stop-loss orders include algoType='CONDITIONAL'."""
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        self.client.new_stop_loss_order(
            symbol="ETHUSDT",
            side="SELL",
            stopPrice=2000.0,
            quantity=1.0
        )
        
        params = mock_request.call_args[1]["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["type"], "STOP_MARKET")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_take_profit_order_includes_algo_type_conditional(self, mock_request):
        """Test that take-profit orders include algoType='CONDITIONAL'."""
        mock_request.return_value = {"algoId": 67890, "success": True}
        
        self.client.new_take_profit_order(
            symbol="ETHUSDT",
            side="SELL",
            stopPrice=3000.0,
            quantity=1.0
        )
        
        params = mock_request.call_args[1]["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["type"], "TAKE_PROFIT_MARKET")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_trailing_stop_order_includes_algo_type_conditional(self, mock_request):
        """Test that trailing stop orders include algoType='CONDITIONAL'."""
        mock_request.return_value = {"algoId": 99999, "success": True}
        
        self.client.new_trailing_stop_order(
            symbol="BTCUSDT",
            side="SELL",
            callbackRate=1.5,
            quantity=0.1
        )
        
        params = mock_request.call_args[1]["params"]
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["type"], "TRAILING_STOP_MARKET")


class TestAlgoOrderGuardrails(unittest.TestCase):
    """
    Test suite for algo order guardrails.
    
    Guardrails prevent common API errors:
    1. closePosition=true + quantity => Error
    2. closePosition=true + reduceOnly => Error  
    3. Hedge Mode requires positionSide
    """
    
    def setUp(self):
        """Set up test client."""
        self.client = BinanceFuturesClient(
            api_key="test_key",
            api_secret="test_secret",
            use_testnet=True
        )
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_close_position_removes_quantity(self, mock_request):
        """Test that closePosition=true removes quantity from params."""
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        # Call with both closePosition=true AND quantity
        self.client.new_stop_loss_order(
            symbol="BTCUSDT",
            side="SELL",
            stopPrice=50000.0,
            closePosition="true",
            quantity=0.1  # Should be REMOVED by guardrail
        )
        
        params = mock_request.call_args[1]["params"]
        
        # Quantity should be removed when closePosition=true
        self.assertNotIn("quantity", params,
            "quantity must be removed when closePosition=true (Binance rejects it)")
        self.assertEqual(params["closePosition"], "true")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_close_position_removes_reduce_only(self, mock_request):
        """Test that closePosition=true removes reduceOnly from params."""
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        # Call with both closePosition=true AND reduceOnly
        self.client.new_stop_loss_order(
            symbol="BTCUSDT",
            side="SELL",
            stopPrice=50000.0,
            closePosition="true",
            reduceOnly="true"  # Should be REMOVED by guardrail
        )
        
        params = mock_request.call_args[1]["params"]
        
        # reduceOnly should be removed when closePosition=true
        self.assertNotIn("reduceOnly", params,
            "reduceOnly must be removed when closePosition=true (Binance rejects it)")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_quantity_preserved_without_close_position(self, mock_request):
        """Test that quantity is preserved when closePosition is not true."""
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        self.client.new_take_profit_order(
            symbol="ETHUSDT",
            side="SELL",
            stopPrice=3000.0,
            quantity=1.5,
            reduceOnly="true"
        )
        
        params = mock_request.call_args[1]["params"]
        
        # Quantity and reduceOnly should be preserved
        self.assertEqual(params["quantity"], 1.5)
        self.assertEqual(params["reduceOnly"], "true")
    
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_position_side_passed_for_hedge_mode(self, mock_request):
        """Test that positionSide is passed through for Hedge Mode."""
        mock_request.return_value = {"algoId": 12345, "success": True}
        
        self.client.new_stop_loss_order(
            symbol="BTCUSDT",
            side="SELL",
            stopPrice=50000.0,
            quantity=0.1,
            positionSide="LONG"  # Required for Hedge Mode
        )
        
        params = mock_request.call_args[1]["params"]
        self.assertEqual(params["positionSide"], "LONG")


class TestMockedHTTPAlgoOrder(unittest.TestCase):
    """
    Mocked HTTP tests to verify the actual request payload sent to Binance.
    
    These tests mock at the HTTP level to verify the exact payload structure.
    """
    
    def setUp(self):
        """Set up test client with mocked session."""
        self.mock_session = Mock()
        self.client = BinanceFuturesClient(
            api_key="test_api_key",
            api_secret="test_secret_key_for_signing",
            use_testnet=True,
            session=self.mock_session
        )
    
    def test_http_payload_includes_algo_type(self):
        """
        Test that the HTTP payload sent to /fapi/v1/algoOrder includes algoType='CONDITIONAL'.
        
        This is the definitive test that the bug is fixed - we verify the actual
        data that would be sent over the wire to Binance.
        """
        # Mock successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "algoId": 14517910,
            "success": True,
            "code": 0,
            "msg": "OK"
        }
        self.mock_session.request.return_value = mock_response
        
        # Make the call
        self.client.new_stop_loss_order(
            symbol="BTCUSDT",
            side="SELL",
            stopPrice=50000.0,
            closePosition="true"
        )
        
        # Verify the HTTP request
        self.mock_session.request.assert_called_once()
        call_kwargs = self.mock_session.request.call_args[1]
        
        # Verify correct endpoint
        self.assertIn("/fapi/v1/algoOrder", call_kwargs["url"])
        
        # Verify payload contains algoType (POST sends data, not params)
        payload = call_kwargs["data"]
        self.assertEqual(payload["algoType"], "CONDITIONAL",
            "HTTP payload must include algoType='CONDITIONAL'")
        self.assertEqual(payload["type"], "STOP_MARKET")
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["side"], "SELL")
        
        # Verify closePosition is passed
        self.assertEqual(payload["closePosition"], "true")
        
        # Verify quantity is NOT in payload (guardrail for closePosition=true)
        self.assertNotIn("quantity", payload)


class TestBatchOrderRouting(unittest.TestCase):
    """Test batch order handling for conditional vs regular orders."""

    def setUp(self):
        self.client = BinanceFuturesClient(
            api_key="test_key",
            api_secret="test_secret",
            use_testnet=True
        )

    @patch('binance_futures_python.client.BinanceFuturesClient.new_algo_order')
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_batch_orders_split_conditional(self, mock_request, mock_new_algo):
        mock_request.return_value = {"batchId": 1}
        mock_new_algo.return_value = {"algoId": 2, "_via_algo_api": True}

        result = self.client.new_batch_orders(
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "LIMIT",
                    "timeInForce": "GTC",
                    "price": 25000,
                    "quantity": 0.1,
                },
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "stopPrice": 24000,
                    "quantity": 0.1,
                },
            ]
        )

        self.assertEqual(mock_request.call_args[0][1], "/fapi/v1/batchOrders")
        mock_new_algo.assert_called_once()
        self.assertEqual(result["regular"]["batchId"], 1)
        self.assertEqual(result["conditional"][0]["algoId"], 2)

    def test_batch_orders_rejects_conditional_when_disabled(self):
        orders = [
            {"symbol": "BTCUSDT", "side": "BUY", "type": "STOP_MARKET", "stopPrice": 25000}
        ]
        with self.assertRaises(ValueError):
            self.client.new_batch_orders(orders, auto_split_conditional=False)


class TestSmartAlgoFallback(unittest.TestCase):
    """Test smart routing for query/cancel with algo ids."""

    def setUp(self):
        self.client = BinanceFuturesClient(
            api_key="test_key",
            api_secret="test_secret",
            use_testnet=True
        )

    @patch('binance_futures_python.client.BinanceFuturesClient.cancel_algo_order')
    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_cancel_order_fallbacks_to_algo(self, mock_request, mock_cancel_algo):
        mock_response = Mock()
        mock_response.status_code = 400
        not_found = BinanceFuturesAPIError(
            "Order does not exist", 400, mock_response, {"code": -2013, "msg": "Order does not exist"}
        )
        mock_request.side_effect = not_found
        mock_cancel_algo.return_value = {"algoId": 321, "success": True}

        result = self.client.cancel_order(
            symbol="BTCUSDT",
            orderId=111,
            algoId=321,
            allow_algo_fallback=True
        )

        mock_cancel_algo.assert_called_once_with(symbol="BTCUSDT", algoId=321)
        self.assertEqual(result["algoId"], 321)

    @patch('binance_futures_python.client.BinanceFuturesClient.query_algo_order')
    def test_query_order_routes_to_algo_when_algo_id_given(self, mock_query_algo):
        mock_query_algo.return_value = {"algoId": 88, "status": "WORKING"}

        result = self.client.query_order(algoId=88, symbol="BTCUSDT")

        mock_query_algo.assert_called_once_with(algoId=88, symbol="BTCUSDT")
        self.assertEqual(result["algoId"], 88)

    @patch('binance_futures_python.client.BinanceFuturesClient._request')
    def test_cancel_open_algo_orders_endpoint(self, mock_request):
        mock_request.return_value = {"success": True}

        self.client.cancel_open_algo_orders(symbol="BTCUSDT")

        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "DELETE")
        self.assertEqual(call_args[0][1], "/fapi/v1/algoOpenOrders")
        params = call_args[1]["params"]
        self.assertEqual(params["symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
