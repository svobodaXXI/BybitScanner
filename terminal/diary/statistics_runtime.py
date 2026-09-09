"""Runtime-safe read boundary for Trading Diary D6.4 statistics.

This module composes existing TradeEpisode/D3 analytics and optional D4/D5 factor
observations. Factor evidence is opened strictly read-only: requesting statistics
must never create or migrate a Diary database.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .analytics import TradeAnalyticsRecord, pnl_from_episode
from .factors import (
    FactorObservation,
    FactorProvenance,
    FactorSubjectKind,
)
from .models import TradeEpisode
from .statistics_presentation import POST_TRADE_FACTOR_KEYS, project_trade_statistics


def load_post_trade_factors_read_only(
    database_path: str | Path,
    *,
    trade_episode_ids: Iterable[str],
) -> tuple[FactorObservation, ...]:
    """Load existing D5 observations without creating a missing factor store."""
    path = Path(database_path)
    subject_ids = tuple(sorted({item for item in trade_episode_ids if item}))
    if not subject_ids or not path.exists():
        return ()

    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='factor_observations'"
        ).fetchone()
        if table is None:
            return ()

        placeholders = ",".join("?" for _ in subject_ids)
        factor_placeholders = ",".join("?" for _ in POST_TRADE_FACTOR_KEYS)
        rows = connection.execute(
            f"""SELECT observation_id, factor_key, factor_version, subject_kind,
                       subject_id, observed_at_ms, provenance, source_version, value_json
                FROM factor_observations
                WHERE subject_kind=?
                  AND subject_id IN ({placeholders})
                  AND factor_key IN ({factor_placeholders})
                ORDER BY observed_at_ms, observation_id""",
            (
                FactorSubjectKind.TRADE_EPISODE.value,
                *subject_ids,
                *POST_TRADE_FACTOR_KEYS,
            ),
        ).fetchall()
        return tuple(
            FactorObservation(
                observation_id=row["observation_id"],
                factor_key=row["factor_key"],
                factor_version=int(row["factor_version"]),
                subject_kind=FactorSubjectKind(row["subject_kind"]),
                subject_id=row["subject_id"],
                observed_at_ms=int(row["observed_at_ms"]),
                provenance=FactorProvenance(row["provenance"]),
                source_version=row["source_version"],
                value=json.loads(row["value_json"]),
            )
            for row in rows
        )
    finally:
        connection.close()


def project_runtime_statistics(
    episodes: Iterable[TradeEpisode],
    *,
    factor_store_path: str | Path,
) -> dict[str, object]:
    """Project current runtime evidence without inventing unavailable PnL costs."""
    materialized = tuple(episodes)
    records = tuple(
        TradeAnalyticsRecord(
            episode=episode,
            pnl=pnl_from_episode(
                episode,
                funding=None,
                other_exchange_costs=None,
                manual_external_costs=None,
            ),
        )
        for episode in materialized
    )
    factor_observations = load_post_trade_factors_read_only(
        factor_store_path,
        trade_episode_ids=(
            episode.trade_episode_id.value
            for episode in materialized
            if episode.is_closed
        ),
    )
    return project_trade_statistics(
        records,
        factor_observations=factor_observations,
    )
