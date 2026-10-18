"""Owner-attested administrative closure of four stale historical LIVE Limit commands.

Between 2026-09-04 and 2026-09-07 four controlled LIVE MAINNET acceptance BUY Limits
for ONGUSDT (about 5.2 USDT each) were created through the Terminal. Their parent
``create_limit`` commands stayed ``open`` forever: two orders were cancelled through
separate CANCEL commands (which resolved those commands, not the parent), one was
cancelled manually outside the Terminal and one was never recorded. The OWNER has
stated (2026-10-18) that all four were cancelled long ago. This module records that
statement, and nothing more:

* the commands move ``open -> owner_attested_closed`` through the existing
  transition primitive and gain exactly one history row whose reason says it is an
  owner statement, NOT exchange evidence;
* no exchange is queried, no ``cancelled``/``filled`` event, execution or order is
  invented, no exchange confirmation and no LIVE/PAPER record is changed or removed;
* scope is the exact four-command allowlist below (command, link, exchange order,
  price/quantity, acceptance session, request fingerprint, account); anything else
  is refused before any write, the whole group is one transaction;
* it is idempotent: already attested commands are verified and left untouched.

Never called on runtime start-up. Applied only by tools.attest_legacy_live_limit_commands
against a stopped runtime and a verified backup.
"""

from __future__ import annotations

from dataclasses import dataclass

from terminal.domain.models import CommandId
from terminal.domain.states import CommandState

LIVE_ACCOUNT_ID = "bybit-9e55e9b1839a41b4b492a54a25b26295"
SYMBOL = "ONGUSDT"
OWNER_STATEMENT_DATE = "2026-10-18"

# command_id -> exact identity of the original LIVE acceptance Limit.
ALLOWED_LEGACY_LIVE_COMMANDS: dict[str, dict[str, object]] = {
    "cmd_8a6297e87d7f4d2bb4cfecb048cce5e8": dict(
        order_link_id="tw_8a6297e87d7f4d2bb4cfecb048cce5e8f",
        exchange_order_id="9b79a481-315f-4aab-8fde-23a1a2b59e08",
        price="0.09513", quantity="54", created_at_ms=1788559783787,
        session="live-limit-ong-accept-002", client_action_id="live-limit-1788559781310",
        fingerprint="455b5c58f1aa3651f34d8afe09d6bfa07ada4d94754869367814870f1e8eff8d",
    ),
    "cmd_c6b41c3a86aa413cb070ffc3b4ad8508": dict(
        order_link_id="tw_c6b41c3a86aa413cb070ffc3b4ad8508d",
        exchange_order_id="1aaf9a68-f17c-4699-b561-99ece221e08c",
        price="0.09489", quantity="54", created_at_ms=1788587603679,
        session="live-limit-ong-ux-accept-003", client_action_id="live-limit-1788587595878",
        fingerprint="8099ac2717ac2539d2cd675ddfbafd26fbad08323017f577685ee532fd6fd509",
    ),
    "cmd_5aa2bc7b2c114b92857ce9dbb9d21b01": dict(
        order_link_id="tw_5aa2bc7b2c114b92857ce9dbb9d21b019",
        exchange_order_id="53570b3f-f0c5-47b5-8665-1f9f29462b11",
        price="0.09247", quantity="56", created_at_ms=1788683319484,
        session="live-limit-ong-shared-core-accept-007", client_action_id="live-limit-1788683318726",
        fingerprint="91ea8f58af3b3acaa3c88375fdcd5311a9afc4347631e7bd55b7e2e45a26b18a",
    ),
    "cmd_cb7e8a57fe05494eacbaaa2151067a94": dict(
        order_link_id="tw_cb7e8a57fe05494eacbaaa2151067a94a",
        exchange_order_id="75609e45-c4f1-4ad2-828b-18185c8d5853",
        price="0.09225", quantity="56", created_at_ms=1788763337841,
        session="live-limit-ong-cancel-accept-011", client_action_id="live-limit-1788763337270",
        fingerprint="2d3483e2fa7f142ace956c8d5379b462f0f743e9ca82c4d3f4ee54837af13578",
    ),
}

ATTESTATION_REASON = (
    "OWNER_ATTESTED_CLOSED: administrative closure on the owner's statement of "
    f"{OWNER_STATEMENT_DATE} that this 2026-09 LIVE MAINNET acceptance Limit was cancelled "
    "long ago; NOT exchange evidence; no exchange query was made; no cancel, fill or "
    "execution is implied or recorded"
)

_ORIGINAL_HISTORY = (
    (None, CommandState.ADMITTED, "durable LIVE Limit acceptance ownership"),
    (CommandState.ADMITTED, CommandState.SUBMITTING, "LIVE Limit adapter dispatch durably started"),
    (CommandState.SUBMITTING, CommandState.ACKNOWLEDGED, "exchange accepted mutation request"),
    (CommandState.ACKNOWLEDGED, CommandState.OPEN, "normalized exchange evidence resolved command"),
)
_ATTESTED_HISTORY = _ORIGINAL_HISTORY + (
    (CommandState.OPEN, CommandState.OWNER_ATTESTED_CLOSED, ATTESTATION_REASON),
)


class LegacyLiveAttestationError(ValueError):
    """The command is not exactly the attested historical record; nothing was written."""


@dataclass(frozen=True, slots=True)
class LegacyLiveProof:
    command_id: str
    order_link_id: str
    exchange_order_id: str
    session: str
    already_attested: bool
    version: int


def _require(condition, reason):
    if not condition:
        raise LegacyLiveAttestationError(reason)


def prove_legacy_live_limit_command(store, command_id: str) -> LegacyLiveProof:
    """Prove the command is exactly one of the four historical records. Read only."""
    store._assert_owner()
    _require(command_id in ALLOWED_LEGACY_LIVE_COMMANDS, "command not on the legacy LIVE allowlist")
    spec = ALLOWED_LEGACY_LIVE_COMMANDS[command_id]
    connection = store._connection
    row = connection.execute("SELECT * FROM trading_commands WHERE command_id=?", (command_id,)).fetchone()
    _require(row is not None, "command missing")
    _require(
        row["trading_account_id"] == LIVE_ACCOUNT_ID and row["symbol"] == SYMBOL
        and row["category"] == "linear" and row["command_kind"] == "create_limit"
        and row["side"] == "Buy" and row["origin"] == "terminal_manual"
        and row["controller"] == "manual"
        and row["order_link_id"] == spec["order_link_id"]
        and row["exchange_order_id"] == spec["exchange_order_id"]
        and row["normalized_price"] == spec["price"]
        and row["normalized_quantity"] == spec["quantity"]
        and row["created_at_ms"] == spec["created_at_ms"],
        "command identity does not match the attested record",
    )
    attested = row["current_state"] == CommandState.OWNER_ATTESTED_CLOSED.value
    _require(
        row["current_state"] == CommandState.OPEN.value or attested,
        f"command is {row['current_state']}; only an untouched open command can be attested",
    )
    expected_version = 5 if attested else 4
    _require(row["version"] == expected_version, "command version is not the attested one")
    history = tuple(
        (CommandState(h["previous_state"]) if h["previous_state"] else None,
         CommandState(h["next_state"]), h["reason"])
        for h in connection.execute(
            "SELECT * FROM command_state_history WHERE command_id=? ORDER BY history_id", (command_id,))
    )
    _require(history == (_ATTESTED_HISTORY if attested else _ORIGINAL_HISTORY),
             "state history is not the untouched original")

    action = connection.execute(
        "SELECT * FROM live_limit_actions WHERE command_id=?", (command_id,)).fetchone()
    _require(
        action is not None and action["trading_account_id"] == LIVE_ACCOUNT_ID
        and action["environment"] == "MAINNET" and action["operation"] == "CREATE"
        and action["acceptance_session_id"] == spec["session"]
        and action["client_action_id"] == spec["client_action_id"]
        and action["request_fingerprint"] == spec["fingerprint"]
        and action["exchange_order_id"] == spec["exchange_order_id"]
        and action["dispatch_state"] == "ACKNOWLEDGED"
        and action["reconciliation_state"] == "RESOLVED",
        "LIVE Limit action record does not match the attested request",
    )
    # No LIVE work may still be unresolved anywhere in the database.
    for table in ("live_limit_actions", "live_limit_operations"):
        _require(connection.execute(
            f"SELECT 1 FROM {table} WHERE reconciliation_state<>'RESOLVED' LIMIT 1").fetchone() is None,
            f"unresolved LIVE work: {table}")
    # The record must be a pure LIVE record: no PAPER order, execution or command shares it.
    link, order = spec["order_link_id"], spec["exchange_order_id"]
    _require(connection.execute(
        "SELECT 1 FROM paper_limit_orders WHERE order_id=? OR order_link_id=? LIMIT 1", (order, link)
    ).fetchone() is None, "a PAPER order shares this identity")
    _require(connection.execute(
        "SELECT 1 FROM executions WHERE order_id=? LIMIT 1", (order,)).fetchone() is None,
        "an execution exists for this exchange order; closure by attestation would hide it")
    _require(connection.execute(
        "SELECT 1 FROM trading_commands WHERE command_id<>? AND (order_link_id=? OR exchange_order_id=?) LIMIT 1",
        (command_id, link, order)).fetchone() is None, "another command shares this identity")
    return LegacyLiveProof(command_id, link, order, str(spec["session"]), attested, int(row["version"]))


def attest_legacy_live_limit_commands(store, command_ids, *, occurred_at_ms: int):
    """Close exactly the four commands in one transaction. Idempotent; refuses on any doubt."""
    ids = tuple(command_ids)
    _require(len(ids) == len(ALLOWED_LEGACY_LIVE_COMMANDS) and set(ids) == set(ALLOWED_LEGACY_LIVE_COMMANDS),
             "all four exact commands are required")
    with store._transaction():
        proofs = [prove_legacy_live_limit_command(store, command_id) for command_id in ids]
        commands = [store.get_command(CommandId(proof.command_id)) for proof in proofs]
        _require(all(occurred_at_ms >= command.updated_at_ms for command in commands),
                 "attestation timestamp precedes command history")
        return tuple(
            command if proof.already_attested else store._transition_command_in_transaction(
                command, CommandState.OWNER_ATTESTED_CLOSED, ATTESTATION_REASON, occurred_at_ms)
            for proof, command in zip(proofs, commands)
        )
