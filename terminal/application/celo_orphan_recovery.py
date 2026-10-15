"""Exact CELOUSDT manual PAPER orphan recovery; never called on runtime startup."""
from decimal import Decimal

from terminal.application.paper_orphan_market_commands import (
    OrphanEvidenceError, OrphanProof, _require_identity,
)
from terminal.domain.models import CommandId
from terminal.domain.states import CommandState

# Exact identities and original normalized request evidence from the incident.
ALLOWED_ORPHAN_COMMANDS = {
    "cmd_d2d1c17dd4ed41e5a2fd5859a3648a28": ("CELOUSDT", "tw_d2d1c17dd4ed41e5a2fd5859a3648a281"),
    "cmd_529244bf01e34cd0872bbaf0b33831ec": ("CELOUSDT", "tw_529244bf01e34cd0872bbaf0b33831ecb"),
    "cmd_be1186183dfe4fd083fa6e96e830cb4c": ("CELOUSDT", "tw_be1186183dfe4fd083fa6e96e830cb4c7"),
}
REQUESTS = dict(zip(ALLOWED_ORPHAN_COMMANDS, (
    ("3320.7", 1788112610580), ("3320.7", 1788112616678), ("3340.7", 1788127901385),
)))
FAILED_REASON = (
    "CELO-RECOVERY-1: exact PAPER Market identity has no order/execution; "
    "unrelated completed ledger nets to zero, projection Flat/synced, no active obligations"
)
HISTORY = ((None, CommandState.ADMITTED, "admitted before exchange submission"),
           (CommandState.ADMITTED, CommandState.SUBMITTING, "single mutation attempt durably started"))


def _require(condition, reason):
    if not condition:
        raise OrphanEvidenceError(reason)


def _prove_flat(store):
    c = store._connection
    scope = ("paper", "CELOUSDT")
    positions = c.execute("SELECT * FROM position_projections WHERE trading_account_id=? AND symbol=?", scope).fetchall()
    _require(len(positions) == 1, "missing/ambiguous position projection")
    p = positions[0]
    _require(p['category'] == 'linear' and p['position_idx'] == 0 and p['side'] == 'Flat'
             and Decimal(p['quantity']) == 0 and Decimal(p['engaged_notional']) == 0
             and p['sync_state'] == 'synced', "position is not Flat/synced")
    net = Decimal(0)
    for e in c.execute("SELECT * FROM executions WHERE trading_account_id=? AND symbol=?", scope):
        _require(e['category'] == 'linear' and e['side'] in ('Buy', 'Sell'), "ambiguous ledger")
        q = Decimal(e['quantity'])
        _require(q.is_finite() and q > 0, "invalid execution quantity")
        owners = c.execute("SELECT * FROM trading_commands WHERE trading_account_id=? AND symbol=? AND exchange_order_id=?",
                           (*scope, e['order_id'])).fetchall()
        _require(len(owners) == 1 and owners[0]['current_state'] == 'filled', "foreign history is not completed/owned")
        owner = owners[0]
        _require(owner['command_id'] not in ALLOWED_ORPHAN_COMMANDS
                 and e['order_id'] == 'paper-order-' + owner['order_link_id']
                 and e['exec_id'] == 'paper-exec-' + owner['order_link_id'], "foreign execution identity mismatch")
        net += q if e['side'] == 'Buy' else -q
    _require(net == 0, "execution ledger is not flat")
    terminal = ('filled', 'cancelled', 'amended', 'rejected', 'failed')
    for row in c.execute("SELECT command_id,current_state FROM trading_commands WHERE trading_account_id=? AND symbol=?", scope):
        _require(row['command_id'] in ALLOWED_ORPHAN_COMMANDS or row['current_state'] in terminal,
                 "another unfinished command")
    guards = (
        ("paper_limit_orders", "status NOT IN ('filled','cancelled')"),
        ("robot_trades", "exit_time_ms IS NULL"),
        ("paper_protection_obligations", "status <> 'RESOLVED'"),
        ("robot_candidates", "status NOT IN ('CLOSED','EXPIRED','INVALIDATED')"),
        ("protection_intents", "status <> 'no_protection_configured'"),
        ("protection_projections", "status <> 'no_protection_configured'"),
        ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
    )
    for table, predicate in guards:
        _require(c.execute(f"SELECT 1 FROM {table} WHERE trading_account_id=? AND symbol=? AND ({predicate}) LIMIT 1", scope).fetchone() is None,
                 'active/uncertain obligation: ' + table)
    for table, column, stopped in (("robot_runtime_state", "mode", "ROBOT_STOPPED"),
                                   ("scanner_runtime_state", "mode", "SCANNER_STOPPED")):
        rows = c.execute(f"SELECT {column} FROM {table} WHERE trading_account_id='paper'").fetchall()
        _require(len(rows) == 1 and rows[0][0] == stopped, 'runtime not durably stopped: ' + table)
    row = c.execute("SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'").fetchone()
    _require(row is not None and row[0] in ('OFF', 'SHADOW'), 'PAPER_AUTO/unknown mode')


def prove_orphan_paper_market_command(store, command_id):
    store._assert_owner()
    _require(command_id in ALLOWED_ORPHAN_COMMANDS, 'command not on CELO allowlist')
    symbol, link = ALLOWED_ORPHAN_COMMANDS[command_id]
    command = store.get_command(CommandId(command_id))
    _require(command is not None, 'command missing')
    _require_identity(command, symbol, link)
    quantity, created = REQUESTS[command_id]
    _require(command.side.value == 'Buy' and command.requested_notional.value == Decimal('250')
             and command.normalized_quantity.value == Decimal(quantity)
             and command.normalized_price is None and command.created_at_ms == created,
             'original request mismatch')
    failed = command.current_state is CommandState.FAILED
    expected = HISTORY + ((CommandState.SUBMITTING, CommandState.FAILED, FAILED_REASON),) if failed else HISTORY
    history = tuple((h.previous_state, h.next_state, h.reason) for h in store.load_command_history(command.command_id))
    _require(history == expected and command.version == (3 if failed else 2)
             and command.current_state in (CommandState.SUBMITTING, CommandState.FAILED)
             and command.exchange_order_id is None, 'state/history mismatch')
    c = store._connection
    eid, oid = 'paper-exec-' + link, 'paper-order-' + link
    _require(c.execute('SELECT 1 FROM executions WHERE exec_id=? OR order_id=?', (eid, oid)).fetchone() is None,
             'related execution exists')
    _require(c.execute('SELECT 1 FROM paper_limit_orders WHERE order_id=? OR order_link_id=?', (oid, link)).fetchone() is None,
             'related order exists')
    _require(c.execute('SELECT 1 FROM trading_commands WHERE exchange_order_id=? OR (order_link_id=? AND command_id<>?)',
                       (oid, link, command_id)).fetchone() is None, 'related command order exists')
    _prove_flat(store)
    return OrphanProof(command_id, symbol, link, eid, oid, command.version, failed)


def fail_orphan_paper_market_commands(store, command_ids, *, occurred_at_ms):
    ids = tuple(command_ids)
    _require(len(ids) == 3 and set(ids) == set(ALLOWED_ORPHAN_COMMANDS), 'all three exact commands required')
    # Existing store transaction + transition primitive: proof/write share one lock,
    # and any failure rolls back the entire group. No new persistence mechanism.
    with store._transaction():
        proofs = [prove_orphan_paper_market_command(store, cid) for cid in ids]
        commands = [store.get_command(CommandId(p.command_id)) for p in proofs]
        _require(all(occurred_at_ms >= c.updated_at_ms for c in commands), 'recovery timestamp precedes history')
        return tuple(c if p.already_failed else store._transition_command_in_transaction(
            c, CommandState.FAILED, FAILED_REASON, occurred_at_ms)
            for p, c in zip(proofs, commands))
