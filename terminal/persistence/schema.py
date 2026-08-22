"""Initial SQLite schema for Terminal execution recovery state."""

SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE trading_commands (
        command_id TEXT PRIMARY KEY,
        order_link_id TEXT NOT NULL UNIQUE,
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        command_kind TEXT NOT NULL,
        side TEXT NOT NULL,
        requested_notional TEXT NOT NULL,
        normalized_price TEXT,
        normalized_quantity TEXT,
        origin TEXT NOT NULL,
        controller TEXT NOT NULL,
        current_state TEXT NOT NULL,
        version INTEGER NOT NULL,
        exchange_order_id TEXT,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        CHECK (category = 'linear'),
        CHECK (position_idx = 0),
        CHECK (version >= 1)
    )
    """,
    """
    CREATE TABLE command_state_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        command_id TEXT NOT NULL,
        previous_state TEXT,
        next_state TEXT NOT NULL,
        reason TEXT NOT NULL,
        occurred_at_ms INTEGER NOT NULL,
        FOREIGN KEY (command_id) REFERENCES trading_commands(command_id)
    )
    """,
    """
    CREATE TABLE executions (
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        exec_id TEXT NOT NULL,
        order_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        fee TEXT NOT NULL,
        exchange_timestamp_ms INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, category, exec_id),
        CHECK (category = 'linear')
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE position_projections (
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        side TEXT NOT NULL,
        quantity TEXT NOT NULL,
        average_entry TEXT,
        realized_pnl TEXT NOT NULL,
        accumulated_fee TEXT NOT NULL,
        engaged_notional TEXT NOT NULL,
        sync_state TEXT NOT NULL,
        version INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, category, symbol, position_idx),
        CHECK (category = 'linear'),
        CHECK (position_idx = 0),
        CHECK (version >= 1)
    ) WITHOUT ROWID
    """,
)
