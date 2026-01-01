# Changelog

## 0.2.0 - 2026-01-01
- Added automatic routing/fallback for conditional STOP/TAKE_PROFIT/TRAILING_STOP orders to the Algo Service with `auto_switch_conditional_to_algo`.
- Added algo order lifecycle helpers (query/cancel/cancel-open/open/all) plus batch-order splitting to keep conditional orders off `/fapi/v1/batchOrders`.
- Added smart query/cancel fallback hooks and actionable error hints for Binance codes `-4120`, `-4116`, and `-4117`.
- Updated README and tests to document the Algo migration, behavior notes (no margin check pre-trigger, no modification of untriggered conditional orders), and new usage examples.
