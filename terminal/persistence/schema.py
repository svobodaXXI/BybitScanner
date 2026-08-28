"""Versioned SQLite schema for Terminal execution recovery state."""

SCHEMA_VERSION = 9

SCHEMA_V1_STATEMENTS = (
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

SCHEMA_V2_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE reconciliation_checkpoints (
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        generation INTEGER NOT NULL,
        outcome TEXT NOT NULL,
        exchange_snapshot_at_ms INTEGER NOT NULL,
        exchange_sequence INTEGER,
        started_at_ms INTEGER NOT NULL,
        completed_at_ms INTEGER,
        version INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, category, symbol, position_idx),
        CHECK (category = 'linear'),
        CHECK (position_idx = 0),
        CHECK (generation >= 1),
        CHECK (version >= 1),
        CHECK (length(trim(outcome)) > 0),
        CHECK (exchange_snapshot_at_ms >= 0),
        CHECK (exchange_sequence IS NULL OR exchange_sequence >= 0),
        CHECK (started_at_ms >= 0),
        CHECK (completed_at_ms IS NULL OR completed_at_ms >= started_at_ms),
        CHECK (completed_at_ms IS NULL OR updated_at_ms >= completed_at_ms),
        CHECK (updated_at_ms >= started_at_ms)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V3_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE cleanup_runs (
        cleanup_id TEXT PRIMARY KEY,
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        cause TEXT NOT NULL,
        reconciliation_generation INTEGER NOT NULL,
        confirmed_at_ms INTEGER NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        UNIQUE (trading_account_id, category, symbol, position_idx,
                reconciliation_generation, confirmed_at_ms),
        CHECK (category = 'linear'),
        CHECK (position_idx = 0),
        CHECK (version >= 1)
    )
    """,
    """
    CREATE TABLE cleanup_items (
        cleanup_id TEXT NOT NULL,
        order_id TEXT NOT NULL,
        order_link_id TEXT,
        cancel_command_id TEXT NOT NULL UNIQUE,
        cancel_order_link_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        version INTEGER NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (cleanup_id, order_id),
        FOREIGN KEY (cleanup_id) REFERENCES cleanup_runs(cleanup_id),
        CHECK (version >= 1)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE protection_intents (
        command_id TEXT PRIMARY KEY,
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        take_profit TEXT,
        stop_loss TEXT,
        tp_trigger_by TEXT NOT NULL,
        sl_trigger_by TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        FOREIGN KEY (command_id) REFERENCES trading_commands(command_id),
        CHECK (category = 'linear'),
        CHECK (position_idx = 0)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE protection_projections (
        trading_account_id TEXT NOT NULL,
        category TEXT NOT NULL,
        symbol TEXT NOT NULL,
        position_idx INTEGER NOT NULL,
        status TEXT NOT NULL,
        take_profit TEXT,
        stop_loss TEXT,
        trailing_stop TEXT,
        pending_command_id TEXT,
        version INTEGER NOT NULL,
        evidence_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, category, symbol, position_idx),
        CHECK (category = 'linear'),
        CHECK (position_idx = 0),
        CHECK (version >= 1)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V4_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_accounts (
        trading_account_id TEXT PRIMARY KEY,
        initial_deposit_usdt TEXT NOT NULL,
        equity_usdt TEXT NOT NULL,
        version INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        CHECK (version >= 1)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V5_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_limit_orders (
        order_id TEXT PRIMARY KEY,
        order_link_id TEXT NOT NULL UNIQUE,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        time_in_force TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        CHECK (side IN ('Buy', 'Sell')),
        CHECK (time_in_force = 'GTC'),
        CHECK (status IN ('open', 'cancelled'))
    )
    """,
    """
    CREATE TABLE paper_limit_actions (
        client_action_id TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        order_id TEXT,
        created_at_ms INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES paper_limit_orders(order_id),
        CHECK (operation IN ('create', 'cancel'))
    ) WITHOUT ROWID
    """,
)

SCHEMA_V6_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_limit_actions_v6 (
        client_action_id TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        order_id TEXT,
        created_at_ms INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES paper_limit_orders(order_id),
        CHECK (operation IN ('create', 'amend', 'cancel'))
    ) WITHOUT ROWID
    """,
    """
    INSERT INTO paper_limit_actions_v6
    SELECT client_action_id, operation, request_fingerprint, order_id, created_at_ms
    FROM paper_limit_actions
    """,
    "DROP TABLE paper_limit_actions",
    "ALTER TABLE paper_limit_actions_v6 RENAME TO paper_limit_actions",
)

SCHEMA_V7_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_limit_orders_v7 (
        order_id TEXT PRIMARY KEY,
        order_link_id TEXT NOT NULL UNIQUE,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        filled_quantity TEXT NOT NULL DEFAULT '0',
        time_in_force TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        CHECK (side IN ('Buy', 'Sell')),
        CHECK (time_in_force = 'GTC'),
        CHECK (status IN ('open', 'partially_filled', 'filled', 'cancelled'))
    )
    """,
    """
    INSERT INTO paper_limit_orders_v7 (
        order_id, order_link_id, trading_account_id, symbol, side, price,
        quantity, filled_quantity, time_in_force, status, created_at_ms, updated_at_ms
    )
    SELECT
        order_id, order_link_id, trading_account_id, symbol, side, price,
        quantity, '0', time_in_force, status, created_at_ms, updated_at_ms
    FROM paper_limit_orders
    """,
    """
    CREATE TABLE paper_limit_actions_v7 (
        client_action_id TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        order_id TEXT,
        created_at_ms INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES paper_limit_orders_v7(order_id),
        CHECK (operation IN ('create', 'amend', 'cancel'))
    ) WITHOUT ROWID
    """,
    """
    INSERT INTO paper_limit_actions_v7
    SELECT client_action_id, operation, request_fingerprint, order_id, created_at_ms
    FROM paper_limit_actions
    """,
    "DROP TABLE paper_limit_actions",
    "DROP TABLE paper_limit_orders",
    "ALTER TABLE paper_limit_orders_v7 RENAME TO paper_limit_orders",
    "ALTER TABLE paper_limit_actions_v7 RENAME TO paper_limit_actions",
)

SCHEMA_V8_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_state_revisions (
        symbol TEXT PRIMARY KEY,
        revision INTEGER NOT NULL,
        CHECK (revision >= 0)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V9_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_state_revisions_v9 (
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        revision INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, symbol),
        CHECK (revision >= 0)
    ) WITHOUT ROWID
    """,
    """
    INSERT INTO paper_state_revisions_v9 (trading_account_id, symbol, revision)
    SELECT 'paper', symbol, revision FROM paper_state_revisions
    """,
    "DROP TABLE paper_state_revisions",
    "ALTER TABLE paper_state_revisions_v9 RENAME TO paper_state_revisions",
)

SCHEMA_STATEMENTS = (
    SCHEMA_V1_STATEMENTS
    + SCHEMA_V2_MIGRATION_STATEMENTS
    + SCHEMA_V3_MIGRATION_STATEMENTS
    + SCHEMA_V4_MIGRATION_STATEMENTS
    + SCHEMA_V5_MIGRATION_STATEMENTS
    + SCHEMA_V6_MIGRATION_STATEMENTS
    + SCHEMA_V7_MIGRATION_STATEMENTS
    + SCHEMA_V8_MIGRATION_STATEMENTS
    + SCHEMA_V9_MIGRATION_STATEMENTS
)
