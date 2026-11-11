"""Owner-originated candidate proposals from immutable Editor snapshots.

Human-drawn rays are NEVER trusted executable Robot strategy snapshots.
This isolated, append-only evaluation gate reuses Scanner pivot and candidate
geometry diagnostics and Robot pattern support, but cannot create/admit an
order-capable candidate, touch PAPER DB, or update detector state.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from decimal import Decimal

from geometry_feedback_store import bars_digest, source_revision
from signal_archive import archive_dir
from signal_geometry_snapshot import canonical_bytes, validate_snapshot
from retrospective_signal_bars import extension_digest, validate_extension, RetrospectiveBarsError

PROPOSAL_DIR_ENV = "BYBITSCANNER_OWNER_SIGNAL_PROPOSAL_DIR"
MAX_REQUEST_BYTES = 32768
MAX_NOTE_LENGTH = 1024
PATTERNS = frozenset({"Falling Wedge", "Rising Wedge"})
OWNER_CHART_PATTERNS = PATTERNS | {"Ikigai Box"}
REQUIRED = frozenset({
    "schema_version", "signal_id", "snapshot_revision", "bars_sha256",
    "pattern", "proposed_boundaries", "idempotency_key",
})


class OwnerSignalProposalError(ValueError):
    pass


class OwnerSignalProposalConflict(OwnerSignalProposalError):
    pass


def proposal_directory(directory=None) -> Path:
    if directory is not None:
        return Path(directory)
    value = os.getenv(PROPOSAL_DIR_ENV, "").strip()
    return Path(value) if value else archive_dir().parent / "owner_signal_proposals"


def _normalize(payload: dict, snapshot: dict, *, review_bars=None) -> dict:
    context_fields = {"context_as_of_ms", "context_bars_sha256"}
    if not isinstance(payload, dict) or set(payload) - {"note"} - context_fields != REQUIRED:
        raise OwnerSignalProposalError("invalid_proposal_fields")
    if payload["schema_version"] != 1:
        raise OwnerSignalProposalError("invalid_proposal_schema")
    signal_id = payload["signal_id"]
    token = payload["idempotency_key"]
    import re
    if (not isinstance(signal_id, str) or
            not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", signal_id) or
            snapshot["signal_id"] != signal_id):
        raise OwnerSignalProposalError("invalid_source_signal")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", token):
        raise OwnerSignalProposalError("invalid_idempotency_key")
    if (payload["snapshot_revision"] != source_revision(snapshot) or
            payload["bars_sha256"] != bars_digest(snapshot)):
        raise OwnerSignalProposalConflict("source_snapshot_revision_conflict")
    has_context = any(field in payload for field in context_fields)
    if has_context and not context_fields.issubset(payload):
        raise OwnerSignalProposalError("incomplete_retrospective_context")
    extension = []
    if has_context:
        try:
            extension = validate_extension(snapshot, review_bars, payload["context_as_of_ms"])
        except RetrospectiveBarsError as exc:
            raise OwnerSignalProposalError(str(exc)) from exc
        if payload["context_bars_sha256"] != extension_digest(extension):
            raise OwnerSignalProposalConflict("retrospective_context_hash_conflict")
    elif review_bars:
        raise OwnerSignalProposalError("unexpected_retrospective_context")
    pattern = payload["pattern"]
    if pattern not in PATTERNS:
        raise OwnerSignalProposalError("unsupported_proposed_pattern")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
        raise OwnerSignalProposalError("invalid_proposal_note")
    given = payload["proposed_boundaries"]
    if not isinstance(given, list) or len(given) != 2:
        raise OwnerSignalProposalError("two_complete_rays_required")
    timestamps = {bar["open_time_ms"] for bar in [*snapshot["bars"], *extension]}
    rays = {}
    for item in given:
        if not isinstance(item, dict) or set(item) != {"id", "type", "anchors"}:
            raise OwnerSignalProposalError("invalid_ray_fields")
        side = item["id"]
        if side not in ("upper", "lower") or side in rays or item["type"] != "ray":
            raise OwnerSignalProposalError("invalid_ray_identity")
        anchors = item["anchors"]
        if not isinstance(anchors, list) or len(anchors) != 2:
            raise OwnerSignalProposalError("two_ray_anchors_required")
        normalized = []
        for anchor in anchors:
            if not isinstance(anchor, dict) or set(anchor) != {"bar_open_time_ms", "price"}:
                raise OwnerSignalProposalError("invalid_anchor_fields")
            at, price = anchor["bar_open_time_ms"], anchor["price"]
            if (type(at) is not int or at not in timestamps or
                    type(price) not in (int, float, Decimal) or not math.isfinite(float(price))
                    or float(price) <= 0):
                raise OwnerSignalProposalError("invalid_frozen_anchor")
            normalized.append({"bar_open_time_ms": at, "price": float(price)})
        if normalized[0]["bar_open_time_ms"] >= normalized[1]["bar_open_time_ms"]:
            raise OwnerSignalProposalError("nonchronological_ray")
        rays[side] = {"id": side, "type": "ray", "anchors": normalized}
    if set(rays) != {"upper", "lower"}:
        raise OwnerSignalProposalError("missing_upper_or_lower")
    return {
        **({"context_as_of_ms": payload["context_as_of_ms"],
            "context_bars_sha256": payload["context_bars_sha256"]} if has_context else {}),
        "schema_version": 1,
        "signal_id": signal_id,
        "snapshot_revision": payload["snapshot_revision"],
        "bars_sha256": payload["bars_sha256"],
        "pattern": pattern,
        "proposed_boundaries": [rays["upper"], rays["lower"]],
        "note": note,
        "idempotency_key": token,
    }


def _assess_geometry(payload: dict, snapshot: dict, *, review_bars=None) -> dict:
    """Conservative Scanner precheck, NOT an executable Robot admission.

    Validated user geometry must still originate from a trusted Scanner
    strategy adapter with entry, STOP/TAKE, confirmation and freshness proof.
    """
    import pandas as pd
    from pivots import find_pivots
    from geometry.candidate import build_candidate_lines
    from geometry.filter import filter_candidates
    from robot_state_machine import is_supported_pattern

    if not is_supported_pattern(payload["pattern"]):
        return {"decision": "REJECTED", "reason": "robot_pattern_unsupported"}

    bars = [*snapshot["bars"], *(review_bars or [])]
    positions = {bar["open_time_ms"]: index for index, bar in enumerate(bars)}
    upper, lower = find_pivots(pd.DataFrame(bars)[["high", "low"]].copy())
    pivots = {"upper": upper, "lower": lower}
    for side in ("upper", "lower"):
        line = next(line for line in payload["proposed_boundaries"] if line["id"] == side)
        values = pivots[side]
        if len(values) > 40:
            return {"decision": "REJECTED", "reason": "pivot_evaluation_budget_exceeded"}
        pair = []
        for anchor in line["anchors"]:
            index = positions[anchor["bar_open_time_ms"]]
            if not any(p["index"] == index and math.isclose(
                float(p["price"]), anchor["price"], rel_tol=1e-8, abs_tol=1e-12
            ) for p in values):
                return {"decision": "REJECTED", "reason": "ray_anchor_not_confirmed_pivot"}
            pair.append(index)
        generated = build_candidate_lines(values)
        if not any((item["anchor_index"], item["second_index"]) == tuple(pair)
                   for item in generated):
            return {"decision": "REJECTED", "reason": "ray_pair_not_generated"}
        if not any((item["anchor_index"], item["second_index"]) == tuple(pair)
                   for item in filter_candidates(generated)):
            return {"decision": "REJECTED", "reason": "ray_pair_filtered"}
    return {
        "decision": "AWAITING_STRATEGY_PROOF",
        "reason": "trusted_scanner_strategy_snapshot_required",
    }


def record_owner_signal_proposal(payload: dict, snapshot: dict, *, directory=None, review_bars=None,
                                 source_kind: str = "SCANNER",
                                 owner_chart_submission: dict | None = None) -> dict:
    """Durably record a reviewed owner proposal without creating a Robot candidate."""
    try:
        if owner_chart_submission is not None:
            # Only the separately validated, untrusted owner-chart path can
            # carry a Fibonacci boundary. It must never enter Scanner's
            # trusted two-ray snapshot assessment or Robot admission.
            if source_kind != "OWNER_CHART_UNVERIFIED" or review_bars is not None:
                raise OwnerSignalProposalError("invalid_owner_chart_authority")
            submission = owner_chart_submission
        else:
            validate_snapshot(
                snapshot, candidate_id=snapshot["signal_id"],
                symbol=snapshot["symbol"], timeframe=snapshot["timeframe"],
            )
            submission = _normalize(payload, snapshot, review_bars=review_bars)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, OwnerSignalProposalError):
            raise
        raise OwnerSignalProposalError("invalid_source_geometry") from exc

    if source_kind not in {"SCANNER", "OWNER_CHART_UNVERIFIED"}:
        raise OwnerSignalProposalError("unsupported_owner_source_kind")
    assessment = (_assess_geometry(submission, snapshot, review_bars=review_bars)
                  if source_kind == "SCANNER" else {
                      "decision": "AWAITING_OFFLINE_REPLAY",
                      "reason": "owner_supplied_source_not_scanner_evidence",
                  })
    signal_id = submission["signal_id"]
    proposal_id = hashlib.sha256(
        (signal_id + "\0" + submission["idempotency_key"]).encode("utf-8")
    ).hexdigest()
    directory_path = proposal_directory(directory) / hashlib.sha256(
        signal_id.encode("utf-8")
    ).hexdigest()[:40]
    path = directory_path / (proposal_id + ".json")
    record = {
        "proposal_id": proposal_id,
        "submitted_at_ms": int(time.time() * 1000),
        "submission": submission,
        **({"retrospective_bars": validate_extension(snapshot, review_bars, submission["context_as_of_ms"])}
           if "context_as_of_ms" in submission else {}),
        "assessment": assessment,
        **({"source_kind": source_kind, "owner_source_snapshot": snapshot}
           if source_kind != "SCANNER" else {}),
        "robot_candidate_id": None,
        "candidate_created": False,
    }
    directory_path.mkdir(parents=True, exist_ok=True)
    tmp = directory_path / (proposal_id + "." + secrets.token_hex(8) + ".tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(canonical_bytes(record))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(tmp, path)
            if os.name == "posix":
                fd = os.open(directory_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except FileExistsError:
            try:
                previous = json.loads(path.read_bytes())
                if (previous.get("proposal_id") != proposal_id or
                        previous.get("submission") != submission or
                        previous.get("candidate_created") is not False or
                        previous.get("robot_candidate_id") is not None or
                        previous.get("assessment") != assessment or
                        previous.get("source_kind", "SCANNER") != source_kind or
                        (source_kind != "SCANNER" and previous.get("owner_source_snapshot") != snapshot) or
                        previous.get("retrospective_bars", []) != record.get("retrospective_bars", [])):
                    raise ValueError("idempotency_conflict")
            except (OSError, ValueError, AttributeError) as exc:
                raise OwnerSignalProposalConflict("existing_proposal_conflict") from exc
            return previous
    finally:
        tmp.unlink(missing_ok=True)
    return record


def record_owner_chart_proposal(payload: dict, *, directory=None, now_ms: int | None = None) -> dict:
    """Store owner-supplied candle examples with provenance explicitly UNVERIFIED.

    Reuse the append-only owner proposal store, never Scanner's source archive.
    These examples cannot create Robot candidates, edit PAPER DB or teach the
    running detector without a separate chronological offline evaluation.
    """
    required = {
        "schema_version", "source_kind", "symbol", "timeframe", "pattern",
        "direction", "bars", "proposed_boundaries", "idempotency_key",
    }
    if (not isinstance(payload, dict) or set(payload) - {"note"} != required
            or payload.get("schema_version") != 2
            or payload.get("source_kind") != "OWNER_CHART_UNVERIFIED"):
        raise OwnerSignalProposalError("invalid_owner_chart_fields")
    symbol, timeframe = payload["symbol"], payload["timeframe"]
    from retrospective_signal_bars import TF_MS
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{2,25}", symbol):
        raise OwnerSignalProposalError("invalid_owner_chart_symbol")
    if not isinstance(timeframe, str) or timeframe not in TF_MS:
        raise OwnerSignalProposalError("invalid_owner_chart_timeframe")
    period = TF_MS[timeframe]
    if payload["pattern"] not in OWNER_CHART_PATTERNS:
        raise OwnerSignalProposalError("unsupported_proposed_pattern")
    if payload["direction"] not in ("LONG", "SHORT"):
        raise OwnerSignalProposalError("invalid_owner_chart_direction")
    note = payload.get("note", "")
    token = payload["idempotency_key"]
    if (not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH or
            not isinstance(token, str) or
            not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", token)):
        raise OwnerSignalProposalError("invalid_owner_chart_note_or_key")
    raw = payload["bars"]
    if not isinstance(raw, list) or not 20 <= len(raw) <= 120:
        raise OwnerSignalProposalError("invalid_owner_chart_window")
    current = int(time.time() * 1000) if now_ms is None else now_ms
    if type(current) is not int or current < 0:
        raise OwnerSignalProposalError("invalid_owner_chart_time")
    bars = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "open_time_ms", "open", "high", "low", "close",
        }:
            raise OwnerSignalProposalError("invalid_owner_chart_bar")
        at = item["open_time_ms"]
        if (type(at) is not int or at < 0 or at % period or
                at + period > current or
                (bars and at != bars[-1]["open_time_ms"] + period)):
            raise OwnerSignalProposalError("invalid_owner_chart_chronology")
        try:
            values = {key: float(item[key])
                      for key in ("open", "high", "low", "close")}
        except (ValueError, OverflowError, TypeError) as exc:
            raise OwnerSignalProposalError("invalid_owner_chart_ohlc") from exc
        if (not all(math.isfinite(value) and value > 0 for value in values.values())
                or values["low"] > min(values["open"], values["close"])
                or values["high"] < max(values["open"], values["close"])
                or values["high"] < values["low"]):
            raise OwnerSignalProposalError("invalid_owner_chart_ohlc")
        bars.append({"open_time_ms": at, **values})
    lines = payload["proposed_boundaries"]
    is_box = payload["pattern"] == "Ikigai Box"
    if not isinstance(lines, list) or len(lines) != (1 if is_box else 2):
        raise OwnerSignalProposalError("invalid_owner_chart_geometry")
    times = {bar["open_time_ms"] for bar in bars}
    normalized = []
    ids = set()
    for line in lines:
        if not isinstance(line, dict) or set(line) != {"id", "type", "anchors"}:
            raise OwnerSignalProposalError("invalid_owner_chart_geometry")
        boundary_id, kind = line["id"], line["type"]
        if (boundary_id in ids or
                (is_box and (boundary_id != "first_impulse_fibonacci" or kind != "fibonacci")) or
                (not is_box and (boundary_id not in {"upper", "lower"} or kind != "ray"))):
            raise OwnerSignalProposalError("invalid_owner_chart_geometry")
        ids.add(boundary_id)
        anchors = line["anchors"]
        if not isinstance(anchors, list) or len(anchors) != 2:
            raise OwnerSignalProposalError("invalid_owner_chart_anchors")
        pair = []
        for anchor in anchors:
            if not isinstance(anchor, dict) or set(anchor) != {"bar_open_time_ms", "price"}:
                raise OwnerSignalProposalError("invalid_owner_chart_anchor")
            at, price = anchor["bar_open_time_ms"], anchor["price"]
            if (type(at) is not int or at not in times or
                    type(price) not in (int, float, Decimal) or
                    not math.isfinite(float(price)) or float(price) <= 0):
                raise OwnerSignalProposalError("invalid_owner_chart_anchor")
            pair.append({"bar_open_time_ms": at, "price": float(price)})
        if pair[0]["bar_open_time_ms"] >= pair[1]["bar_open_time_ms"]:
            raise OwnerSignalProposalError("invalid_owner_chart_anchor_order")
        normalized.append({"boundary_id": boundary_id, "kind": kind,
                           "anchors": pair})
    if is_box:
        origin, terminal = normalized[0]["anchors"]
        if (payload["direction"] == "SHORT" and
                terminal["price"] <= origin["price"]) or (
                payload["direction"] == "LONG" and
                terminal["price"] >= origin["price"]):
            raise OwnerSignalProposalError("invalid_owner_chart_impulse_direction")
    elif ids != {"upper", "lower"}:
        raise OwnerSignalProposalError("invalid_owner_chart_geometry")

    snapshot = {
        "schema_version": 1,
        "signal_id": "owner-chart:" + hashlib.sha256(canonical_bytes({
            "symbol": symbol, "timeframe": timeframe, "bars": bars,
        })).hexdigest()[:40],
        "symbol": symbol, "timeframe": timeframe,
        "bars": bars, "boundaries": normalized,
    }
    if not is_box:
        try:
            validate_snapshot(snapshot, candidate_id=snapshot["signal_id"],
                              symbol=symbol, timeframe=timeframe)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise OwnerSignalProposalError("invalid_owner_chart_geometry") from exc

    proposal = {
        "schema_version": 2, "signal_id": snapshot["signal_id"],
        "snapshot_revision": source_revision(snapshot),
        "bars_sha256": bars_digest(snapshot),
        "pattern": payload["pattern"], "direction": payload["direction"],
        "proposed_boundaries": [{
            "id": line["boundary_id"], "type": line["kind"],
            "anchors": line["anchors"],
        } for line in normalized],
        "idempotency_key": token, "note": note,
    }
    return record_owner_signal_proposal(
        proposal, snapshot, directory=directory,
        source_kind="OWNER_CHART_UNVERIFIED",
        owner_chart_submission=proposal,
    )


def list_owner_chart_training_examples(pattern: str, *, directory=None) -> list[dict]:
    """Category-filtered, read-only examples for offline Scanner replay."""
    if pattern not in OWNER_CHART_PATTERNS:
        raise OwnerSignalProposalError("unsupported_proposed_pattern")
    root = proposal_directory(directory)
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise OwnerSignalProposalError("untrusted_proposal_archive")
    found = []
    checked = 0
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            checked += 1
            if checked > 5000:
                raise OwnerSignalProposalError("proposal_archive_scan_budget")
            if path.is_symlink() or path.stat().st_size > 65536:
                continue
            try:
                record = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError, UnicodeError):
                continue
            if (isinstance(record, dict)
                    and record.get("source_kind") == "OWNER_CHART_UNVERIFIED"
                    and record.get("candidate_created") is False
                    and record.get("robot_candidate_id") is None
                    and isinstance(record.get("submission"), dict)
                    and record["submission"].get("pattern") == pattern
                    and isinstance(record.get("owner_source_snapshot"), dict)):
                found.append(record)
    found.sort(key=lambda item: (item.get("submitted_at_ms", 0),
                                  item.get("proposal_id", "")), reverse=True)
    return found[:20]
