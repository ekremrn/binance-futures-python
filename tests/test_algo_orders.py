"""
Unit tests for Algo Order API integration.

Tests verify:
- Conditional orders route to /fapi/v1/algoOrder
- Non-conditional orders route to /fapi/v1/order
- Proper handling of algoId vs orderId
- Error handling and logging
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json

from binance_futures_python.client import BinanceFuturesClient, BinanceFuturesAPIError


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
        
        with self.assertRaises(BinanceFuturesAPIError) as context:
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


if __name__ == "__main__":
    unittest.main()
