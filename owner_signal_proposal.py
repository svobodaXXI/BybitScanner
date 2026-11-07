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


def record_owner_signal_proposal(payload: dict, snapshot: dict, *, directory=None, review_bars=None) -> dict:
    """Durably record a reviewed owner proposal without creating a Robot candidate."""
    try:
        validate_snapshot(
            snapshot, candidate_id=snapshot["signal_id"],
            symbol=snapshot["symbol"], timeframe=snapshot["timeframe"],
        )
        submission = _normalize(payload, snapshot, review_bars=review_bars)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, OwnerSignalProposalError):
            raise
        raise OwnerSignalProposalError("invalid_source_geometry") from exc

    assessment = _assess_geometry(submission, snapshot, review_bars=review_bars)
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
                        previous.get("retrospective_bars", []) != record.get("retrospective_bars", [])):
                    raise ValueError("idempotency_conflict")
            except (OSError, ValueError, AttributeError) as exc:
                raise OwnerSignalProposalConflict("existing_proposal_conflict") from exc
            return previous
    finally:
        tmp.unlink(missing_ok=True)
    return record
