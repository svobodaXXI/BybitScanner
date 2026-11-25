"""Append-only observational wedge revisions; no Robot state or order authority."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

APP_ID = 0x42574752
VERSION = 1
_LINE_FIELDS = ("anchor_index", "anchor_price", "second_index", "second_price",
                "slope", "intercept")


def _line(line):
    return {k: line[k] for k in _LINE_FIELDS}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _key(seed):
    candidate = seed["candidate_id"]
    digest = seed["source_geometry_sha256"]
    if not isinstance(candidate, str) or not candidate or len(digest) != 64:
        raise ValueError("invalid source identity")
    int(digest, 16)
    return hashlib.sha256(_json([candidate, digest]).encode()).hexdigest()


def _path(database_path):
    return Path(database_path).with_suffix(".wedge_geometry_revisions.sqlite3")


def _check(db):
    if (db.execute("PRAGMA application_id").fetchone()[0] != APP_ID
            or db.execute("PRAGMA user_version").fetchone()[0] != VERSION):
        raise ValueError("foreign or unsupported revision journal")


def load_revisions(database_path, seed):
    """Read immutable ordered history; never create a journal on read."""
    path = _path(database_path)
    if not path.exists():
        return []
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as db:
        _check(db)
        return [json.loads(row[0]) for row in db.execute(
            "SELECT payload FROM revisions WHERE source_key=? ORDER BY revision",
            (_key(seed),))]


def append_revision(database_path, seed, proposal, geometry, *,
                    previous_control_anchor, previous_strict_line):
    """Persist one selected, fully validated revision, atomically and once.

    Called only off ingress by an observation owner with proven coverage.
    Selection and coverage are caller responsibilities. A rejected proposal
    or unchanged ray never creates a success event. Retries are idempotent;
    a divergent previous line or reused trade ID is a conflict.
    """
    if geometry not in proposal.get("validated_pairs", []):
        raise ValueError("pair is not a validated proposal")
    family = seed["family"]
    if family not in ("falling", "rising"):
        raise ValueError("invalid wedge family")
    strict, opposite = ("upper_line", "lower_line") if family == "falling" else ("lower_line", "upper_line")
    old, new = _line(previous_strict_line), _line(geometry[strict])
    if (geometry["start_index"] != seed["episode_start"]
            or _line(geometry[opposite]) != _line(seed["original_opposite_line"])
            or old["anchor_index"] != new["anchor_index"]
            or old["anchor_price"] != new["anchor_price"]
            or new not in [_line(line) for line in proposal["lines"]]
            or not geometry["validation"]["valid"]
            or not geometry["pair_metrics"]["true_converging"]
            or proposal["status"] not in ("CONTROL_CONTACT", "OUTER_ENVELOPE")):
        raise ValueError("revision violates frozen geometry")
    if old == new:
        return None, False
    price, prior = Decimal(proposal["trigger_price"]), Decimal(proposal["previous_extreme"])
    if not (price.is_finite() and prior.is_finite() and price > 0 and prior > 0
            and (price < prior if family == "falling" else price > prior)):
        raise ValueError("trigger is not a new extreme")
    trade_id = proposal["source_trade_id"]
    event_ms, receipt_ms = proposal["event_time_ms"], proposal["received_at_ms"]
    if (not isinstance(trade_id, str) or not trade_id
            or type(event_ms) is not int or type(receipt_ms) is not int
            or event_ms <= 0 or receipt_ms <= 0
            or proposal.get("candidate_id") != seed["candidate_id"]):
        raise ValueError("invalid event provenance")
    source_key = _key(seed)
    facts = {
        "event": "Паттерн перестроен", "candidate_id": seed["candidate_id"],
        "source_geometry_sha256": seed["source_geometry_sha256"],
        "symbol": seed["symbol"], "timeframe_ms": seed["timeframe_ms"],
        "family": family, "episode_start": seed["episode_start"],
        "episode_start_ms": int(seed["candles"]["open_time_ms"].iloc[seed["episode_start"]]),
        "source_trade_id": trade_id, "event_time_ms": event_ms, "received_at_ms": receipt_ms,
        "previous_extreme": str(prior), "trigger_price": str(price),
        "previous_control_anchor": dict(previous_control_anchor),
        "control_anchor": dict(proposal["control_anchor"]),
        "previous_strict_line": old, "strict_line": new,
        "opposite_line": _line(geometry[opposite]), "reason": proposal["status"],
    }
    db = sqlite3.connect(_path(database_path), isolation_level=None, timeout=5)
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0:
            db.execute("""CREATE TABLE revisions (
                source_key TEXT NOT NULL, revision INTEGER NOT NULL,
                trade_id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(source_key, revision), UNIQUE(source_key, trade_id)
            ) WITHOUT ROWID""")
            db.execute("""CREATE TRIGGER no_revision_update BEFORE UPDATE ON revisions
                BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""")
            db.execute("""CREATE TRIGGER no_revision_delete BEFORE DELETE ON revisions
                BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""")
            db.execute(f"PRAGMA application_id={APP_ID}")
            db.execute(f"PRAGMA user_version={VERSION}")
        _check(db)
        existing = db.execute("SELECT payload FROM revisions WHERE source_key=? AND trade_id=?",
                              (source_key, trade_id)).fetchone()
        if existing:
            stored = json.loads(existing[0])
            if _json(stored) != _json(dict(facts, revision=stored["revision"])):
                raise ValueError("conflicting duplicate trade")
            db.execute("COMMIT")
            return stored, False
        last = db.execute("SELECT payload FROM revisions WHERE source_key=? ORDER BY revision DESC LIMIT 1",
                          (source_key,)).fetchone()
        if last:
            previous = json.loads(last[0])
            if (old != previous["strict_line"]
                    or facts["previous_control_anchor"] != previous["control_anchor"]
                    or event_ms < previous["event_time_ms"]):
                raise ValueError("revision chain conflict")
            revision = previous["revision"]+1
        else:
            if old != _line(seed["original_strict_line"]):
                raise ValueError("missing original revision predecessor")
            revision = 1
        record = dict(facts, revision=revision)
        db.execute("INSERT INTO revisions VALUES (?,?,?,?)",
                   (source_key, revision, trade_id, _json(record)))
        db.execute("COMMIT")
        return record, True
    finally:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
