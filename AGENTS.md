# AGENTS.md

## Purpose
This repository contains a small Python library that exposes a high-level REST client for Binance USD-M Futures. The client wraps public, signed trading, account, position, user-stream, and Algo Service endpoints, with request signing and conditional-order routing handled internally.

This file is the operating guide for future maintainers and coding agents. It records the repository's current architecture and sets default rules so new endpoint coverage and behavior changes follow the strongest existing patterns.

## Repository snapshot
- **Main technologies:** Python package using `requests`/`urllib3` for HTTP transport.
- **Runtime:** Python `>=3.9`.
- **Frameworks:** No web framework, job framework, ORM, database layer, UI framework, or application server.
- **Key dependencies:** `requests>=2.31.0` is the only runtime dependency. `urllib3` is used transitively through `requests` for retry configuration.
- **Package entrypoint:** `binance_futures_python/__init__.py` re-exports `BinanceFuturesClient`, `BinanceFuturesAPIError`, and `ConditionalOrderMigratedError`.
- **Build command:** `python3 -m build` once the `build` package is installed.
- **Test command:** `python3 -m unittest discover -s tests`.
- **Targeted test command:** `python3 -m unittest tests.test_algo_orders`.
- **Syntax check:** `PYTHONPYCACHEPREFIX=/tmp python3 -m compileall -q binance_futures_python`.
- **Lint/type-check commands:** None configured in the repository.
- **Deployment target:** Python package distribution. There are no runtime deployment manifests or CI/CD files in the repo.

## Current project structure
- `binance_futures_python/` — importable Python package.
- `binance_futures_python/__init__.py` — public package surface and version constant. Keep exported symbols intentional and stable.
- `binance_futures_python/client.py` — the library implementation. Contains error types, `BinanceFuturesClient`, endpoint helper methods, request signing, retry setup, request dispatch, parameter cleanup, and API error mapping.
- `tests/` — unittest-based test suite. Tests mock `_request` or a `Session`; they do not call Binance live endpoints.
- `tests/test_algo_orders.py` — coverage for conditional-order migration, Algo Service payloads, guardrails, query/cancel fallback, and batch splitting.
- `README.md` — user-facing install, usage, endpoint coverage, packaging, and Binance Algo migration documentation.
- `CHANGELOG.md` — release notes. Currently documents the `0.2.0` Algo Service migration.
- `pyproject.toml` — primary package metadata and setuptools build backend configuration.
- `setup.cfg` and `setup.py` — legacy setuptools compatibility files. Treat these as compatibility mirrors of `pyproject.toml`, not the source of truth.
- `requirements.txt` — convenience runtime dependency list, currently mirroring the single package dependency.
- `.gitignore` — broad Python ignores for caches, build artifacts, virtual environments, tooling caches, and editor-generated metadata.
- `LICENSE` — MIT license.

## Architecture overview
This is a single-package, single-client REST SDK. The architecture is intentionally flat: `BinanceFuturesClient` is both the public facade and the internal orchestrator for endpoint-specific helpers.

Request flow:
1. A user imports `BinanceFuturesClient` from `binance_futures_python`.
2. Public methods such as `new_order`, `get_account_balance`, or `create_listen_key` validate required inputs and normalize endpoint-specific parameters.
3. Signed methods delegate credential checks and HMAC SHA256 signing to `_request` through `_sign_params`.
4. `_request` cleans `None` values, chooses query parameters for `GET` and form data for non-`GET`, applies API-key headers when needed, and calls the configured `requests.Session`.
5. Non-2xx responses are converted into `BinanceFuturesAPIError` or `ConditionalOrderMigratedError` by `_raise_api_error`.

The main domain boundary is Binance USD-M Futures HTTP behavior. There is no persistent data model, database access layer, background worker, routing layer, state-management layer, or UI layer. The only stateful object is the client instance, which stores credentials, base URL selection, timeout/retry settings, the `Session`, and routing feature flags.

Business rules currently live inside `BinanceFuturesClient` methods and private helpers. The most important rules are conditional-order routing to `/fapi/v1/algoOrder`, mandatory `algoType="CONDITIONAL"`, close-position guardrails, order-not-found fallback behavior, and Binance error-code hints.

## Architectural decisions
- **Decision:** Keep the SDK as a flat, single-client package until there is a strong reason to split it.
  - **Evidence:** All endpoint families and private transport helpers live in `binance_futures_python/client.py`; `__init__.py` only re-exports the public API.
  - **Implication:** New endpoint helpers should be added to `BinanceFuturesClient` in the matching section before introducing new modules.

- **Decision:** Use one shared `_request` path for HTTP dispatch, signing, headers, retries, timeout, and error conversion.
  - **Evidence:** Public, signed, and listen-key methods all call `_request` with `signed=True` or `send_api_key=True` rather than constructing HTTP calls inline.
  - **Implication:** Do not call `session.request` from endpoint helpers. Extend `_request` or a private helper when transport behavior changes globally.

- **Decision:** Preserve Binance parameter names in public methods.
  - **Evidence:** Methods accept and forward names such as `stopPrice`, `recvWindow`, `positionSide`, `closePosition`, `batchOrders`, and `algoId`.
  - **Implication:** Prefer Binance API field names over Pythonic renames for endpoint parameters. This keeps the SDK close to upstream documentation and avoids mapping drift.

- **Decision:** Endpoint helpers return decoded Binance response dictionaries without DTO/model wrapping.
  - **Evidence:** Methods are annotated as `Dict[str, Any]` and tests assert raw response keys such as `orderId`, `algoId`, `success`, and `_via_algo_api`.
  - **Implication:** Do not introduce response classes or schema objects for one endpoint. If typed models are ever added, they must be a repository-wide design change.

- **Decision:** Conditional order behavior is a first-class domain rule.
  - **Evidence:** `CONDITIONAL_ORDER_TYPES`, `ConditionalOrderMigratedError`, `ERROR_HINTS[-4120]`, `new_algo_order`, stop/take-profit/trailing helpers, and batch splitting are all implemented in the client and covered by tests.
  - **Implication:** Any change to order placement must preserve Algo Service routing, `algoType="CONDITIONAL"`, `_via_algo_api`, and the ability to distinguish `algoId` from `orderId`.

- **Decision:** Tests should isolate SDK behavior from external Binance availability.
  - **Evidence:** The test suite uses `unittest.mock.patch` around `_request` and mocked `Session` objects.
  - **Implication:** New tests should mock transport boundaries and assert method, path, signed flag, and payload shape. Do not add tests that require live credentials or network access.

- **Decision:** `pyproject.toml` is the primary packaging configuration.
  - **Evidence:** README says the project ships as a proper Python library via `pyproject.toml`; `setup.cfg`/`setup.py` exist for old pip compatibility.
  - **Implication:** Change package metadata in `pyproject.toml` first, then mirror necessary compatibility fields in `setup.cfg`, `__init__.__version__`, `requirements.txt`, README, and CHANGELOG.

## Default rules for future changes
- Prefer adding new Binance REST endpoint methods to `BinanceFuturesClient` under the existing section that matches the endpoint family: public market data, trading, Algo Service, account/position, user stream, or internals.
- Do not create a new module for one or two endpoint helpers. Split `client.py` only when a full endpoint family has grown large enough to justify an explicit module boundary and tests can migrate cleanly.
- New public methods should be thin: validate required parameters with `_ensure_required`, normalize only values the SDK already owns, then delegate to `_request`.
- Use `**params: Any` for endpoints with many Binance-defined optional parameters. Use explicit positional or keyword parameters only for simple, stable requirements such as `symbol`, `leverage`, `listen_key`, or boolean mode toggles.
- Preserve upstream Binance field casing in request payloads. Do not convert `stopPrice` to `stop_price`, `positionSide` to `position_side`, or similar inside the public API.
- Remove `None` values through `_clean_params`; endpoint helpers should not duplicate that filtering unless they are building nested structures such as `batchOrders`.
- Keep signed endpoint behavior centralized. Use `signed=True` for endpoints requiring timestamp/signature and `send_api_key=True` for listen-key endpoints that require only `X-MBX-APIKEY`.
- Keep all direct network behavior inside `_request`. Endpoint helpers must never construct URLs, headers, signatures, or retry adapters themselves.
- For new order-placement behavior, explicitly check whether the order type is conditional. Conditional STOP, TAKE_PROFIT, and TRAILING_STOP variants must route through `new_algo_order` unless a test-covered compatibility escape hatch requires otherwise.
- Always include `algoType="CONDITIONAL"` for `/fapi/v1/algoOrder` requests.
- Preserve `_via_algo_api` on Algo responses when the response is a dictionary. Downstream callers may use it to distinguish `algoId` from `orderId`.
- Keep guardrails close to the behavior they protect. Algo-specific parameter mutation belongs in `_prepare_algo_order_params` or a similarly private helper, not scattered across public methods.
- Add actionable error hints in `ERROR_HINTS` when Binance error codes need SDK-level explanation. Map specialized exceptions only when callers can make a useful decision from the distinction.
- Use module-level logging for operationally useful information, but never log API keys, secrets, signatures, or full signed payloads.
- Keep test coverage next to behavior changes. New endpoint helpers need at least mocked-path tests for method, endpoint path, `signed`/API-key behavior, and important payload fields.
- For signing or request-dispatch changes, add mocked `Session` tests that inspect actual `params` or `data` sent to `session.request`.
- Update README and CHANGELOG when public methods, package metadata, endpoint coverage, or Binance migration behavior changes.
- Keep dependency growth conservative. Adding a runtime dependency should be justified by a clear SDK need; prefer the standard library for small helpers.
- Do not add UI code, database code, background workers, CLI entrypoints, or service runtimes unless the repository is intentionally changing scope from a library to an application.

## Allowed patterns
- Public facade methods on `BinanceFuturesClient` grouped by comment sections.
- Private helpers prefixed with `_` for transport, signing, validation, normalization, and error classification.
- Raw `Dict[str, Any]` responses matching Binance payloads.
- `ValueError` for local caller misuse before any HTTP request is made.
- `BinanceFuturesAPIError` subclasses for non-2xx Binance responses.
- Optional injected `requests.Session` for testing and caller-controlled transport.
- Mocked `unittest` tests using `patch`, `Mock`, and explicit payload assertions.
- README examples that use `use_testnet=True` for safety.

## Discouraged or legacy patterns
- **Legacy:** `setup.cfg`/`setup.py` packaging metadata. Keep it compatible, but do not treat it as the canonical configuration.
- **Transitional:** Duplicated version/dependency metadata across `pyproject.toml`, `setup.cfg`, `requirements.txt`, and `__init__.py`. Keep these synchronized until the project removes legacy packaging files.
- **Exception-only:** `_force_rest_route` in `new_order`. Use it only for tested compatibility/fallback paths, not as a normal integration path for conditional orders.
- **Discouraged:** Live Binance tests in the default suite. They would make tests credential-dependent, network-dependent, and unsafe for trading accounts.
- **Discouraged:** Parallel endpoint clients, alternate request dispatchers, or per-method signing logic.
- **Discouraged:** Pythonic parameter aliases that sit beside Binance field names. They increase ambiguity without adding current value.
- **Discouraged:** Broad architectural directories such as `services/`, `models/`, `repositories/`, or `shared/` while the package remains a focused REST SDK with no persistence layer.

## Feature addition playbook
1. Identify the Binance endpoint family and add the public method to the matching section of `BinanceFuturesClient`.
2. Match the method shape to nearby methods: explicit arguments for simple stable fields, `**params` for broad Binance parameter surfaces.
3. Validate required parameters with `_ensure_required` before calling `_request`.
4. Preserve Binance parameter names and pass dictionaries directly to `_request`.
5. Choose the correct transport flags: `signed=True` for signed endpoints, `send_api_key=True` for API-key-only listen-key endpoints, neither for public endpoints.
6. For order-related endpoints, verify conditional-order handling, `algoId` versus `orderId`, `algoType`, and `_via_algo_api` behavior.
7. Add or update tests in `tests/test_algo_orders.py` if the change touches orders or Algo Service behavior. Create a new `tests/test_<endpoint_family>.py` only when a separate endpoint family needs focused coverage.
8. Mock `_request` for high-level routing tests. Mock `Session` when verifying signing, HTTP method, query/body placement, headers, or cleaned parameters.
9. Run `python3 -m unittest discover -s tests` and `PYTHONPYCACHEPREFIX=/tmp python3 -m compileall -q binance_futures_python`.
10. Update README endpoint coverage and examples for public API additions. Update CHANGELOG for behavior changes or release-worthy fixes.
11. If package metadata changes, update `pyproject.toml` first and then synchronize `setup.cfg`, `requirements.txt`, and `__init__.__version__` as applicable.

## Decision policy for ambiguous cases
- When there are multiple places to put endpoint code, choose the existing `BinanceFuturesClient` section over a new abstraction.
- When adding a helper used by one behavior, keep it private and local to `client.py`.
- When a helper becomes reused by multiple endpoint families, promote it to a private method on `BinanceFuturesClient` before creating a new module.
- When introducing a new abstraction, prefer the smallest change that preserves the single-client facade.
- When upstream Binance names conflict with Python style, keep the upstream request/response name in the public API.
- When test style is unclear, use `unittest` and mocks to assert SDK decisions, not external service behavior.
- When documentation and code disagree, treat code plus tests as current behavior and update documentation to match.

## Open questions / uncertainty
- README's syntax-check command currently references `binance-futures-python`, but the actual package directory is `binance_futures_python`; use the package directory form shown in this file unless the README is corrected.
- `pyproject.toml` and `setup.cfg` contain different author email values. The canonical metadata appears to be `pyproject.toml`, but this should be reconciled before publishing.
- There is no CI configuration, formatter, linter, or type-checker configuration. Future additions should be explicit rather than assumed.
- There are no integration tests against Binance testnet. That appears intentional for the default suite, but release validation expectations are not documented beyond mocked tests and compile checks.
- `client.py` is already large for a single file. The current preferred direction is still to keep the single-client facade, but a future endpoint-family split may become worthwhile if it reduces real maintenance cost without changing the public API.

## Maintenance note
Update `AGENTS.md` whenever repository structure, packaging, public API shape, test strategy, or architecture meaningfully changes. This guide should remain evidence-based: if the code moves, the operating rules must move with it.
