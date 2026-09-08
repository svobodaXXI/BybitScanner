# Bybit execution import (Phase 13)

The adapter is read-only and uses the official Bybit V5 `GET /v5/execution/list`
endpoint. It returns normalized `ExecutionFact` values; it does not place orders
or create/update/close Journal Trades.

Required environment values:

```text
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_ACCOUNT_ID=<existing Journal AccountId UUID>
```

Optional values:

```text
BYBIT_TESTNET=false
BYBIT_CATEGORY=linear
```

Use a read-only API key with withdrawals disabled. No key material is stored in
the repository or entered through Telegram. Testnet is opt-in; unit tests inject
a fake client and never contact Bybit.
