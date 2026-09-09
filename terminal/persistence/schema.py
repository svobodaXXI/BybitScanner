"""Versioned SQLite schema for Terminal execution recovery state."""

SCHEMA_VERSION = 15

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

SCHEMA_V10_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_protection_actions (
        client_action_id TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        CHECK (operation IN ('create', 'amend', 'delete'))
    ) WITHOUT ROWID
    """,
)

SCHEMA_V11_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE live_market_actions (
        trading_account_id TEXT NOT NULL,
        session_generation INTEGER NOT NULL,
        client_action_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        command_id TEXT NOT NULL UNIQUE,
        order_link_id TEXT NOT NULL UNIQUE,
        dispatch_started INTEGER NOT NULL DEFAULT 0,
        created_at_ms INTEGER NOT NULL,
        PRIMARY KEY (trading_account_id, session_generation, client_action_id),
        FOREIGN KEY (command_id) REFERENCES trading_commands(command_id),
        CHECK (session_generation >= 1),
        CHECK (dispatch_started IN (0, 1))
    ) WITHOUT ROWID
    """,
)

SCHEMA_V12_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE live_limit_acceptance_sessions (
        acceptance_session_id TEXT NOT NULL,
        trading_account_id TEXT NOT NULL,
        environment TEXT NOT NULL,
        symbol TEXT NOT NULL,
        capability TEXT NOT NULL,
        state TEXT NOT NULL,
        max_create_count INTEGER NOT NULL,
        aggregate_notional_ceiling TEXT NOT NULL,
        per_order_ceiling TEXT NOT NULL,
        reserved_count INTEGER NOT NULL DEFAULT 0,
        reserved_notional TEXT NOT NULL DEFAULT '0',
        opened_at_ms INTEGER NOT NULL,
        expires_at_ms INTEGER NOT NULL,
        authorized_build_sha TEXT NOT NULL,
        database_identity TEXT NOT NULL,
        operator_authorization_reference TEXT NOT NULL,
        authorized_session_generation INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (
            acceptance_session_id, trading_account_id, environment, symbol, capability
        ),
        CHECK (state IN ('ARMED', 'EXHAUSTED', 'EXPIRED', 'REVOKED')),
        CHECK (max_create_count > 0),
        CHECK (reserved_count >= 0 AND reserved_count <= max_create_count),
        CHECK (opened_at_ms >= 0 AND expires_at_ms > opened_at_ms),
        CHECK (authorized_session_generation >= 1),
        CHECK (capability = 'LIVE_LIMIT_CREATE')
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE live_limit_actions (
        acceptance_session_id TEXT NOT NULL,
        trading_account_id TEXT NOT NULL,
        environment TEXT NOT NULL,
        capability TEXT NOT NULL,
        session_generation INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        operation TEXT NOT NULL,
        client_action_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        command_id TEXT NOT NULL UNIQUE,
        order_link_id TEXT NOT NULL UNIQUE,
        exchange_order_id TEXT UNIQUE,
        dispatch_state TEXT NOT NULL,
        reconciliation_state TEXT NOT NULL,
        reserved_count INTEGER NOT NULL,
        reserved_notional TEXT NOT NULL,
        build_sha TEXT NOT NULL,
        process_instance_id TEXT NOT NULL,
        process_started_at_ms INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        database_path TEXT NOT NULL,
        database_identity TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        host_identity TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (
            acceptance_session_id, trading_account_id, session_generation, client_action_id
        ),
        FOREIGN KEY (command_id) REFERENCES trading_commands(command_id),
        FOREIGN KEY (
            acceptance_session_id, trading_account_id, environment, symbol, capability
        ) REFERENCES live_limit_acceptance_sessions (
            acceptance_session_id, trading_account_id, environment, symbol, capability
        ),
        CHECK (session_generation >= 1),
        CHECK (operation IN ('CREATE', 'AMEND', 'CANCEL')),
        CHECK (dispatch_state IN ('OWNED', 'DISPATCHING', 'PRE_DISPATCH_FAILED', 'ACKNOWLEDGED', 'UNKNOWN')),
        CHECK (reconciliation_state IN ('NOT_REQUIRED', 'REQUIRED', 'RESOLVED')),
        CHECK (reserved_count >= 0),
        CHECK (schema_version > 0),
        CHECK (process_id > 0),
        CHECK (created_at_ms >= 0 AND updated_at_ms >= created_at_ms)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V13_MIGRATION_STATEMENTS = (
    "ALTER TABLE live_limit_actions ADD COLUMN outcome_disposition TEXT",
    "ALTER TABLE live_limit_actions ADD COLUMN outcome_reason TEXT",
    "ALTER TABLE live_limit_actions ADD COLUMN outcome_at_ms INTEGER",
    "ALTER TABLE live_limit_actions ADD COLUMN outcome_code INTEGER",
)

SCHEMA_V14_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE live_limit_operations (
        acceptance_session_id TEXT NOT NULL,
        trading_account_id TEXT NOT NULL,
        session_generation INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        client_action_id TEXT NOT NULL,
        command_id TEXT NOT NULL UNIQUE,
        operation TEXT NOT NULL,
        parent_client_action_id TEXT NOT NULL,
        parent_order_link_id TEXT NOT NULL,
        parent_exchange_order_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        requested_price TEXT,
        requested_quantity TEXT,
        conservative_notional TEXT,
        dispatch_state TEXT NOT NULL,
        reconciliation_state TEXT NOT NULL,
        outcome_disposition TEXT,
        outcome_reason TEXT,
        outcome_code INTEGER,
        outcome_at_ms INTEGER,
        build_sha TEXT NOT NULL,
        process_instance_id TEXT NOT NULL,
        process_started_at_ms INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        database_path TEXT NOT NULL,
        database_identity TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        host_identity TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (
            acceptance_session_id, trading_account_id,
            session_generation, client_action_id
        ),
        FOREIGN KEY (command_id) REFERENCES trading_commands(command_id),
        FOREIGN KEY (
            acceptance_session_id, trading_account_id,
            session_generation, parent_client_action_id
        ) REFERENCES live_limit_actions (
            acceptance_session_id, trading_account_id,
            session_generation, client_action_id
        ),
        CHECK (operation IN ('AMEND', 'CANCEL')),
        CHECK (dispatch_state IN ('OWNED', 'DISPATCHING', 'ACKNOWLEDGED', 'UNKNOWN')),
        CHECK (reconciliation_state IN ('NOT_REQUIRED', 'REQUIRED', 'RESOLVED')),
        CHECK (session_generation >= 1),
        CHECK (process_id > 0),
        CHECK (schema_version > 0),
        CHECK (created_at_ms >= 0 AND updated_at_ms >= created_at_ms)
    ) WITHOUT ROWID
    """,
)

SCHEMA_V15_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE robot_runtime_state (
        trading_account_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        recovery_status TEXT NOT NULL,
        reason TEXT,
        version INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        CHECK (mode IN ('ROBOT_STOPPED', 'ROBOT_RUNNING')),
        CHECK (recovery_status IN (
            'ROBOT_STOPPED', 'RECONCILING', 'READY',
            'RECONCILIATION_REQUIRED'
        )),
        CHECK (
            (mode = 'ROBOT_STOPPED' AND recovery_status IN (
                'ROBOT_STOPPED', 'RECONCILIATION_REQUIRED'
            )) OR
            (mode = 'ROBOT_RUNNING' AND recovery_status IN (
                'RECONCILING', 'READY', 'RECONCILIATION_REQUIRED'
            ))
        ),
        CHECK (version >= 1),
        CHECK (updated_at_ms >= 0)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE robot_candidates (
        candidate_id TEXT PRIMARY KEY,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        status TEXT NOT NULL,
        signal_snapshot_json TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,
        robot_state_json TEXT,
        state_revision INTEGER NOT NULL,
        approved_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        UNIQUE (trading_account_id, snapshot_sha256),
        CHECK (length(trim(candidate_id)) > 0),
        CHECK (length(trim(symbol)) > 0),
        CHECK (status IN ('APPROVED', 'OPEN', 'CLOSED', 'EXPIRED', 'INVALIDATED')),
        CHECK (length(snapshot_sha256) = 64),
        CHECK (state_revision >= 0),
        CHECK ((state_revision = 0 AND robot_state_json IS NULL)
            OR (state_revision >= 1 AND robot_state_json IS NOT NULL)),
        CHECK (approved_at_ms >= 0),
        CHECK (updated_at_ms >= approved_at_ms)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE robot_trades (
        trade_id TEXT PRIMARY KEY,
        trading_account_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL UNIQUE,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        pattern TEXT NOT NULL,
        source_timeframe TEXT NOT NULL,
        signal_time_ms INTEGER NOT NULL,
        entry_time_ms INTEGER NOT NULL,
        entry_path TEXT NOT NULL,
        actual_wv TEXT NOT NULL,
        average_entry TEXT NOT NULL,
        stop_price TEXT NOT NULL,
        take_price TEXT NOT NULL,
        exit_time_ms INTEGER,
        exit_price TEXT,
        exit_reason TEXT,
        realized_pnl_usdt TEXT,
        realized_pnl_pct TEXT,
        fees_costs_usdt TEXT,
        version INTEGER NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES robot_candidates(candidate_id),
        CHECK (direction IN ('LONG', 'SHORT')),
        CHECK (entry_path IN ('LIMIT', 'MARKET', 'MIXED')),
        CHECK (length(trim(pattern)) > 0),
        CHECK (length(trim(source_timeframe)) > 0),
        CHECK (signal_time_ms >= 0),
        CHECK (entry_time_ms >= signal_time_ms),
        CHECK (version >= 1),
        CHECK (created_at_ms >= entry_time_ms AND updated_at_ms >= created_at_ms),
        CHECK (exit_reason IS NULL OR exit_reason IN (
            'STOP', 'TAKE', 'MANUAL', 'TAKEOVER',
            'EMERGENCY_CLOSE', 'EMERGENCY_PROTECTION_FAILURE'
        )),
        CHECK (
            (exit_time_ms IS NULL AND exit_price IS NULL AND exit_reason IS NULL
                AND realized_pnl_usdt IS NULL AND realized_pnl_pct IS NULL)
            OR
            (exit_time_ms IS NOT NULL AND exit_price IS NOT NULL AND exit_reason IS NOT NULL
                AND realized_pnl_usdt IS NOT NULL AND realized_pnl_pct IS NOT NULL
                AND exit_time_ms >= entry_time_ms)
        )
    ) WITHOUT ROWID
    """,
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
    + SCHEMA_V10_MIGRATION_STATEMENTS
    + SCHEMA_V11_MIGRATION_STATEMENTS
    + SCHEMA_V12_MIGRATION_STATEMENTS
    + SCHEMA_V13_MIGRATION_STATEMENTS
    + SCHEMA_V14_MIGRATION_STATEMENTS
    + SCHEMA_V15_MIGRATION_STATEMENTS
)
