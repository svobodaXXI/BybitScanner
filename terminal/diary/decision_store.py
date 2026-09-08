"""Append-only SQLite persistence for Trading Diary D2 linkage.

This store is intentionally separate from the Terminal execution SQLite writer.
It persists observational strategy/research linkage only and cannot mutate orders,
executions, reconciliation state or position projections.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal.domain.models import Controller, Origin, PositionSide, Symbol, TradingAccountId

from .decision_models import (
    DecisionEventId,
    DecisionEventKind,
    DecisionEventRecord,
    OrderPlanId,
    OrderPlanRecord,
    SetupInstanceId,
    SetupInstanceRecord,
    SetupTerminalOutcome,
    TradeEpisodeSetupLink,
)
from .models import TradeEpisodeId


class DiaryPersistenceError(RuntimeError):
    pass


class DiaryImmutableConflict(DiaryPersistenceError):
    pass


class DiaryLinkageError(DiaryPersistenceError):
    pass


SCHEMA_VERSION = 1

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS setup_instances (
        setup_instance_id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        pattern TEXT NOT NULL,
        direction TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        setup_id TEXT NOT NULL,
        hypothesis_id TEXT,
        entry_mode TEXT NOT NULL,
        origin TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        CHECK (direction IN ('Long','Short')),
        CHECK (created_at_ms >= 0)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_events (
        decision_event_id TEXT PRIMARY KEY,
        setup_instance_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        previous_state TEXT,
        next_state TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        origin TEXT NOT NULL,
        controller TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        hypothesis_id TEXT,
        setup_id TEXT NOT NULL,
        entry_mode TEXT NOT NULL,
        feature_snapshot_ref TEXT,
        risk_snapshot_ref TEXT,
        order_plan_id TEXT,
        occurred_at_ms INTEGER NOT NULL,
        schema_version INTEGER NOT NULL,
        FOREIGN KEY (setup_instance_id) REFERENCES setup_instances(setup_instance_id),
        CHECK (kind IN ('STRATEGY','RISK','SETUP_OUTCOME')),
        CHECK (occurred_at_ms >= 0),
        CHECK (schema_version >= 1)
    ) WITHOUT ROWID
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_decision_events_setup_time
    ON decision_events(setup_instance_id, occurred_at_ms, decision_event_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS order_plans (
        order_plan_id TEXT PRIMARY KEY,
        setup_instance_id TEXT NOT NULL,
        strategy_decision_event_id TEXT NOT NULL,
        risk_decision_event_id TEXT NOT NULL,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        FOREIGN KEY (setup_instance_id) REFERENCES setup_instances(setup_instance_id),
        FOREIGN KEY (strategy_decision_event_id) REFERENCES decision_events(decision_event_id),
        FOREIGN KEY (risk_decision_event_id) REFERENCES decision_events(decision_event_id),
        CHECK (side IN ('Long','Short')),
        CHECK (created_at_ms >= 0)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_episode_setup_links (
        trade_episode_id TEXT PRIMARY KEY,
        setup_instance_id TEXT NOT NULL,
        order_plan_id TEXT NOT NULL,
        linked_at_ms INTEGER NOT NULL,
        FOREIGN KEY (setup_instance_id) REFERENCES setup_instances(setup_instance_id),
        FOREIGN KEY (order_plan_id) REFERENCES order_plans(order_plan_id),
        CHECK (linked_at_ms >= 0)
    ) WITHOUT ROWID
    """,
    "CREATE INDEX IF NOT EXISTS idx_episode_links_setup ON trade_episode_setup_links(setup_instance_id)",
)


class DiaryDecisionStore:
    """Single-process append-only persistence for D2 research linkage."""

    def __init__(self, connection: sqlite3.Connection, path: Path):
        self._connection = connection
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> "DiaryDecisionStore":
        database_path = Path(path)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, SCHEMA_VERSION):
            connection.close()
            raise DiaryPersistenceError(f"unsupported Trading Diary schema version: {version}")
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in _SCHEMA:
                connection.execute(statement)
            if version == 0:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            connection.close()
            raise
        return cls(connection, database_path)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "DiaryDecisionStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def create_setup_instance(self, record: SetupInstanceRecord) -> SetupInstanceRecord:
        existing = self.get_setup_instance(record.setup_instance_id)
        if existing is not None:
            if existing != record:
                raise DiaryImmutableConflict("setup instance identity already has different evidence")
            return existing
        try:
            self._connection.execute(
                """INSERT INTO setup_instances VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.setup_instance_id.value,
                    record.symbol.value,
                    record.timeframe,
                    record.pattern,
                    record.direction.value,
                    record.strategy_version,
                    record.setup_id,
                    record.hypothesis_id,
                    record.entry_mode,
                    record.origin.value,
                    record.created_at_ms,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            self._connection.rollback()
            raise DiaryPersistenceError("failed to persist setup instance") from exc
        return record

    def get_setup_instance(self, setup_instance_id: SetupInstanceId) -> SetupInstanceRecord | None:
        row = self._connection.execute(
            "SELECT * FROM setup_instances WHERE setup_instance_id=?",
            (setup_instance_id.value,),
        ).fetchone()
        if row is None:
            return None
        return SetupInstanceRecord(
            setup_instance_id=SetupInstanceId(row["setup_instance_id"]),
            symbol=Symbol(row["symbol"]),
            timeframe=row["timeframe"],
            pattern=row["pattern"],
            direction=PositionSide(row["direction"]),
            strategy_version=row["strategy_version"],
            setup_id=row["setup_id"],
            hypothesis_id=row["hypothesis_id"],
            entry_mode=row["entry_mode"],
            origin=Origin(row["origin"]),
            created_at_ms=int(row["created_at_ms"]),
        )

    def append_decision_event(self, record: DecisionEventRecord) -> DecisionEventRecord:
        setup = self.get_setup_instance(record.setup_instance_id)
        if setup is None:
            raise DiaryLinkageError("decision event requires an existing setup instance")
        existing = self.get_decision_event(record.decision_event_id)
        if existing is not None:
            if existing != record:
                raise DiaryImmutableConflict("decision event identity already has different evidence")
            return existing
        self._validate_event_against_setup(record, setup)
        try:
            self._connection.execute(
                """INSERT INTO decision_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.decision_event_id.value,
                    record.setup_instance_id.value,
                    record.kind.value,
                    record.previous_state,
                    record.next_state,
                    record.reason_code,
                    record.origin.value,
                    record.controller.value,
                    record.strategy_version,
                    record.hypothesis_id,
                    record.setup_id,
                    record.entry_mode,
                    record.feature_snapshot_ref,
                    record.risk_snapshot_ref,
                    record.order_plan_id.value if record.order_plan_id else None,
                    record.occurred_at_ms,
                    record.schema_version,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            self._connection.rollback()
            raise DiaryPersistenceError("failed to persist decision event") from exc
        return record

    def record_setup_outcome(self, record: DecisionEventRecord) -> DecisionEventRecord:
        if record.kind is not DecisionEventKind.SETUP_OUTCOME:
            raise ValueError("setup outcome requires SETUP_OUTCOME event kind")
        SetupTerminalOutcome(record.next_state)
        return self.append_decision_event(record)

    def get_decision_event(self, event_id: DecisionEventId) -> DecisionEventRecord | None:
        row = self._connection.execute(
            "SELECT * FROM decision_events WHERE decision_event_id=?",
            (event_id.value,),
        ).fetchone()
        return self._event_from_row(row) if row is not None else None

    def load_decision_events(self, setup_instance_id: SetupInstanceId) -> tuple[DecisionEventRecord, ...]:
        rows = self._connection.execute(
            """SELECT * FROM decision_events WHERE setup_instance_id=?
               ORDER BY occurred_at_ms, decision_event_id""",
            (setup_instance_id.value,),
        ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def load_setup_outcomes(self, setup_instance_id: SetupInstanceId | None = None) -> tuple[DecisionEventRecord, ...]:
        if setup_instance_id is None:
            rows = self._connection.execute(
                """SELECT * FROM decision_events WHERE kind='SETUP_OUTCOME'
                   ORDER BY occurred_at_ms, decision_event_id"""
            ).fetchall()
        else:
            rows = self._connection.execute(
                """SELECT * FROM decision_events WHERE kind='SETUP_OUTCOME'
                   AND setup_instance_id=? ORDER BY occurred_at_ms, decision_event_id""",
                (setup_instance_id.value,),
            ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def create_order_plan(self, record: OrderPlanRecord) -> OrderPlanRecord:
        setup = self.get_setup_instance(record.setup_instance_id)
        if setup is None:
            raise DiaryLinkageError("order plan requires an existing setup instance")
        if setup.symbol != record.symbol or setup.direction is not record.side:
            raise DiaryLinkageError("order plan contradicts setup symbol or direction")
        strategy = self.get_decision_event(record.strategy_decision_event_id)
        risk = self.get_decision_event(record.risk_decision_event_id)
        if strategy is None or risk is None:
            raise DiaryLinkageError("order plan requires persisted strategy and risk decisions")
        if strategy.setup_instance_id != record.setup_instance_id or risk.setup_instance_id != record.setup_instance_id:
            raise DiaryLinkageError("order-plan decisions belong to another setup")
        if strategy.kind is not DecisionEventKind.STRATEGY or risk.kind is not DecisionEventKind.RISK:
            raise DiaryLinkageError("order plan requires STRATEGY then RISK decision identities")
        existing = self.get_order_plan(record.order_plan_id)
        if existing is not None:
            if existing != record:
                raise DiaryImmutableConflict("order-plan identity already has different evidence")
            return existing
        try:
            self._connection.execute(
                """INSERT INTO order_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.order_plan_id.value,
                    record.setup_instance_id.value,
                    record.strategy_decision_event_id.value,
                    record.risk_decision_event_id.value,
                    record.trading_account_id.value,
                    record.symbol.value,
                    record.side.value,
                    record.created_at_ms,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            self._connection.rollback()
            raise DiaryPersistenceError("failed to persist order plan") from exc
        return record

    def get_order_plan(self, order_plan_id: OrderPlanId) -> OrderPlanRecord | None:
        row = self._connection.execute(
            "SELECT * FROM order_plans WHERE order_plan_id=?",
            (order_plan_id.value,),
        ).fetchone()
        if row is None:
            return None
        return OrderPlanRecord(
            order_plan_id=OrderPlanId(row["order_plan_id"]),
            setup_instance_id=SetupInstanceId(row["setup_instance_id"]),
            strategy_decision_event_id=DecisionEventId(row["strategy_decision_event_id"]),
            risk_decision_event_id=DecisionEventId(row["risk_decision_event_id"]),
            trading_account_id=TradingAccountId(row["trading_account_id"]),
            symbol=Symbol(row["symbol"]),
            side=PositionSide(row["side"]),
            created_at_ms=int(row["created_at_ms"]),
        )

    def link_trade_episode(self, link: TradeEpisodeSetupLink) -> TradeEpisodeSetupLink:
        setup = self.get_setup_instance(link.setup_instance_id)
        plan = self.get_order_plan(link.order_plan_id)
        if setup is None or plan is None:
            raise DiaryLinkageError("episode link requires existing setup and order plan")
        if plan.setup_instance_id != link.setup_instance_id:
            raise DiaryLinkageError("episode link order plan belongs to another setup")
        existing = self.get_trade_episode_link(link.trade_episode_id)
        if existing is not None:
            if existing != link:
                raise DiaryImmutableConflict("trade episode already has a different primary setup link")
            return existing
        try:
            self._connection.execute(
                "INSERT INTO trade_episode_setup_links VALUES (?, ?, ?, ?)",
                (
                    link.trade_episode_id.value,
                    link.setup_instance_id.value,
                    link.order_plan_id.value,
                    link.linked_at_ms,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            self._connection.rollback()
            raise DiaryPersistenceError("failed to persist trade-episode setup link") from exc
        return link

    def get_trade_episode_link(self, trade_episode_id: TradeEpisodeId) -> TradeEpisodeSetupLink | None:
        row = self._connection.execute(
            "SELECT * FROM trade_episode_setup_links WHERE trade_episode_id=?",
            (trade_episode_id.value,),
        ).fetchone()
        if row is None:
            return None
        return TradeEpisodeSetupLink(
            trade_episode_id=TradeEpisodeId(row["trade_episode_id"]),
            setup_instance_id=SetupInstanceId(row["setup_instance_id"]),
            order_plan_id=OrderPlanId(row["order_plan_id"]),
            linked_at_ms=int(row["linked_at_ms"]),
        )

    def load_trade_episode_links(self, setup_instance_id: SetupInstanceId) -> tuple[TradeEpisodeSetupLink, ...]:
        rows = self._connection.execute(
            """SELECT * FROM trade_episode_setup_links WHERE setup_instance_id=?
               ORDER BY linked_at_ms, trade_episode_id""",
            (setup_instance_id.value,),
        ).fetchall()
        return tuple(
            TradeEpisodeSetupLink(
                trade_episode_id=TradeEpisodeId(row["trade_episode_id"]),
                setup_instance_id=SetupInstanceId(row["setup_instance_id"]),
                order_plan_id=OrderPlanId(row["order_plan_id"]),
                linked_at_ms=int(row["linked_at_ms"]),
            )
            for row in rows
        )

    @staticmethod
    def _validate_event_against_setup(record: DecisionEventRecord, setup: SetupInstanceRecord) -> None:
        if record.strategy_version != setup.strategy_version:
            raise DiaryLinkageError("decision strategy version differs from setup")
        if record.setup_id != setup.setup_id or record.entry_mode != setup.entry_mode:
            raise DiaryLinkageError("decision setup identity differs from setup instance")
        if record.hypothesis_id != setup.hypothesis_id:
            raise DiaryLinkageError("decision hypothesis differs from setup instance")
        if record.origin is not setup.origin:
            raise DiaryLinkageError("decision origin differs from setup instance")

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> DecisionEventRecord:
        return DecisionEventRecord(
            decision_event_id=DecisionEventId(row["decision_event_id"]),
            setup_instance_id=SetupInstanceId(row["setup_instance_id"]),
            kind=DecisionEventKind(row["kind"]),
            previous_state=row["previous_state"],
            next_state=row["next_state"],
            reason_code=row["reason_code"],
            origin=Origin(row["origin"]),
            controller=Controller(row["controller"]),
            strategy_version=row["strategy_version"],
            hypothesis_id=row["hypothesis_id"],
            setup_id=row["setup_id"],
            entry_mode=row["entry_mode"],
            feature_snapshot_ref=row["feature_snapshot_ref"],
            risk_snapshot_ref=row["risk_snapshot_ref"],
            order_plan_id=OrderPlanId(row["order_plan_id"]) if row["order_plan_id"] else None,
            occurred_at_ms=int(row["occurred_at_ms"]),
            schema_version=int(row["schema_version"]),
        )
