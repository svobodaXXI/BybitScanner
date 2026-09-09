from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

from terminal.diary.models import DiaryEnvironment, TradeEpisodeId
from terminal.diary.statistics_runtime import (
    load_post_trade_factors_read_only,
    project_runtime_statistics,
)


def _episode(episode_id: str, *, closed: bool = True):
    return SimpleNamespace(
        trade_episode_id=TradeEpisodeId(episode_id),
        environment=DiaryEnvironment.PAPER,
        opened_at_ms=1_000,
        closed_at_ms=2_000 if closed else None,
        is_closed=closed,
        realized_price_pnl=Decimal("5"),
        execution_fees=Decimal("1"),
    )


def _create_factor_table(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE factor_observations (
            observation_id TEXT PRIMARY KEY,
            factor_key TEXT NOT NULL,
            factor_version INTEGER NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            observed_at_ms INTEGER NOT NULL,
            provenance TEXT NOT NULL,
            source_version TEXT NOT NULL,
            value_json TEXT NOT NULL
        )"""
    )
    return connection


def test_missing_factor_store_stays_missing_and_does_not_get_created(tmp_path):
    path = tmp_path / "missing.trading_diary.sqlite3"

    result = project_runtime_statistics(
        [_episode("closed"), _episode("open", closed=False)],
        factor_store_path=path,
    )

    assert path.exists() is False
    assert result["sample"] == {
        "total": 2,
        "eligible_closed_ready": 0,
        "excluded_open": 1,
        "excluded_incomplete": 1,
    }
    assert result["pnl"]["net_pnl"] is None
    assert result["coverage"]["post_trade_factors"]["trade.mae_pct"] == {
        "eligible_closed": 1,
        "observed": 0,
        "coverage_ratio": "0",
    }


def test_read_only_factor_loader_returns_only_requested_d5_trade_evidence(tmp_path):
    path = tmp_path / "diary.sqlite3"
    connection = _create_factor_table(path)
    rows = [
        ("mae-one", "trade.mae_pct", 1, "TRADE_EPISODE", "one", 3_000,
         "MARKET_DATA_DERIVED", "d5-v1", json.dumps(1.25)),
        ("mfe-one", "trade.mfe_pct", 1, "TRADE_EPISODE", "one", 3_001,
         "MARKET_DATA_DERIVED", "d5-v1", json.dumps(2.5)),
        ("other-factor", "scanner.final_score", 1, "TRADE_EPISODE", "one", 3_002,
         "MARKET_DATA_DERIVED", "d4-v1", json.dumps(90)),
        ("mae-two", "trade.mae_pct", 1, "TRADE_EPISODE", "two", 3_003,
         "MARKET_DATA_DERIVED", "d5-v1", json.dumps(3.0)),
    ]
    connection.executemany("INSERT INTO factor_observations VALUES (?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()

    observations = load_post_trade_factors_read_only(
        path,
        trade_episode_ids=["one"],
    )

    assert [(item.observation_id, item.factor_key, item.subject_id) for item in observations] == [
        ("mae-one", "trade.mae_pct", "one"),
        ("mfe-one", "trade.mfe_pct", "one"),
    ]


def test_runtime_projection_counts_existing_factor_coverage_without_claiming_net_pnl(tmp_path):
    path = tmp_path / "diary.sqlite3"
    connection = _create_factor_table(path)
    connection.execute(
        "INSERT INTO factor_observations VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "mae-one", "trade.mae_pct", 1, "TRADE_EPISODE", "one", 3_000,
            "MARKET_DATA_DERIVED", "d5-v1", json.dumps(1.25),
        ),
    )
    connection.commit()
    connection.close()

    result = project_runtime_statistics([_episode("one")], factor_store_path=path)

    assert result["sample"]["eligible_closed_ready"] == 0
    assert result["sample"]["excluded_incomplete"] == 1
    assert result["pnl"]["net_pnl"] is None
    assert result["coverage"]["post_trade_factors"]["trade.mae_pct"] == {
        "eligible_closed": 1,
        "observed": 1,
        "coverage_ratio": "1",
    }
