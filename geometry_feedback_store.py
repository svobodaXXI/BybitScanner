"""Append-only owner Geometry Feedback attached to an immutable Scanner signal.

This sidecar is independent of the trading database and never changes detector,
PAPER admission, orders, protection, or existing Scanner signal artifacts.
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

from signal_geometry_snapshot import canonical_bytes, validate_snapshot

FEEDBACK_DIR_ENV = "BYBITSCANNER_GEOMETRY_FEEDBACK_DIR"
DEFAULT_FEEDBACK_DIR = Path(__file__).resolve().parent / "review_queue" / "geometry_feedback"
MAX_REQUEST_BYTES = 32_768
MAX_NOTE_LENGTH = 1024
LABELS = frozenset({"CONFIRMED", "GEOMETRY_CORRECTED", "FALSE_POSITIVE", "UNCERTAIN"})
SIGNAL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")


class GeometryFeedbackError(ValueError):
    """Invalid, stale, conflicting, or incomplete review evidence."""


class GeometryFeedbackConflict(GeometryFeedbackError):
    """A submit token has already been used with different facts."""


def feedback_directory(directory=None) -> Path:
    return Path(directory) if directory is not None else Path(
        os.environ.get(FEEDBACK_DIR_ENV) or DEFAULT_FEEDBACK_DIR
    )


def source_revision(snapshot: dict) -> str:
    return hashlib.sha256(canonical_bytes(snapshot)).hexdigest()


def bars_digest(snapshot: dict) -> str:
    return hashlib.sha256(canonical_bytes(snapshot["bars"])).hexdigest()


def _signal_path(signal_id: str, directory=None) -> Path:
    digest = hashlib.sha256(signal_id.encode("utf-8")).hexdigest()[:40]
    return feedback_directory(directory) / digest


def _valid_price(raw) -> float:
    if type(raw) not in (int, float, Decimal):
        raise GeometryFeedbackError("invalid_anchor_price")
    try:
        price = float(raw)
    except (ValueError, OverflowError):
        raise GeometryFeedbackError("invalid_anchor_price") from None
    if not math.isfinite(price) or price <= 0:
        raise GeometryFeedbackError("invalid_anchor_price")
    return price


def _normalize(payload: dict, snapshot: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or set(payload) - {"note"} != {
        "schema_version", "signal_id", "snapshot_revision", "bars_sha256",
        "label", "corrected_boundaries", "idempotency_key",
    }:
        raise GeometryFeedbackError("invalid_review_fields")
    signal_id = payload.get("signal_id")
    if not isinstance(signal_id, str) or not SIGNAL_RE.fullmatch(signal_id):
        raise GeometryFeedbackError("invalid_signal_id")
    if snapshot.get("signal_id") != signal_id:
        raise GeometryFeedbackError("signal_identity_mismatch")
    if payload["snapshot_revision"] != source_revision(snapshot) or payload["bars_sha256"] != bars_digest(snapshot):
        raise GeometryFeedbackConflict("source_snapshot_revision_conflict")
    token = payload.get("idempotency_key")
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise GeometryFeedbackError("invalid_idempotency_key")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
        raise GeometryFeedbackError("invalid_note")
    label = payload.get("label")
    if label not in LABELS:
        raise GeometryFeedbackError("invalid_review_label")
    corrected = payload.get("corrected_boundaries")
    if not isinstance(corrected, list):
        raise GeometryFeedbackError("missing_corrected_boundaries")
    if label != "GEOMETRY_CORRECTED" and corrected:
        raise GeometryFeedbackError("unexpected_corrected_geometry")

    ids = {boundary["boundary_id"] for boundary in snapshot["boundaries"]}
    supplied = {}
    timestamps = {bar["open_time_ms"] for bar in snapshot["bars"]}
    if label == "GEOMETRY_CORRECTED":
        if len(corrected) != len(ids):
            raise GeometryFeedbackError("incomplete_corrected_geometry")
        for boundary in corrected:
            if not isinstance(boundary, dict) or set(boundary) != {"id", "type", "anchors"}:
                raise GeometryFeedbackError("invalid_boundary_fields")
            boundary_id = boundary["id"]
            if not isinstance(boundary_id, str) or boundary_id not in ids or boundary_id in supplied:
                raise GeometryFeedbackError("unexpected_boundary_identity")
            supplied[boundary_id] = boundary
        normalized = []
        for original in snapshot["boundaries"]:
            item = supplied[original["boundary_id"]]
            anchors = item["anchors"]
            if item["type"] != original["kind"] or not isinstance(anchors, list) or len(anchors) != len(original["anchors"]):
                raise GeometryFeedbackError("boundary_topology_changed")
            previous = -1
            converted = []
            for anchor in anchors:
                if not isinstance(anchor, dict) or set(anchor) != {"bar_open_time_ms", "price"}:
                    raise GeometryFeedbackError("invalid_anchor_fields")
                at = anchor["bar_open_time_ms"]
                if type(at) is not int or at not in timestamps or at <= previous:
                    raise GeometryFeedbackError("anchor_not_in_frozen_window")
                previous = at
                converted.append({"bar_open_time_ms": at, "price": _valid_price(anchor["price"])})
            normalized.append({"boundary_id": original["boundary_id"], "kind": original["kind"], "anchors": converted})
    else:
        normalized = []
    return {
        "schema_version": 1,
        "signal_id": signal_id,
        "snapshot_revision": payload["snapshot_revision"],
        "bars_sha256": payload["bars_sha256"],
        "label": label,
        "note": note,
        "idempotency_key": token,
        "corrected_boundaries": normalized,
    }


def record_review(payload: dict, snapshot: dict, *, directory=None) -> dict:
    """Publish one immutable review; same submit token + same facts is replay-safe."""
    try:
        validate_snapshot(snapshot, candidate_id=snapshot["signal_id"], symbol=snapshot["symbol"], timeframe=snapshot["timeframe"])
        normalized = _normalize(payload, snapshot)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, GeometryFeedbackError):
            raise
        raise GeometryFeedbackError("invalid_source_snapshot") from exc

    signal_id = normalized["signal_id"]
    directory_path = _signal_path(signal_id, directory)
    review_id = hashlib.sha256((signal_id + "\0" + normalized["idempotency_key"]).encode("utf-8")).hexdigest()
    target = directory_path / (review_id + ".json")
    record = {
        "review_id": review_id,
        "received_at_ms": int(time.time() * 1000),
        "reviewer_source": "workspace_owner_ingress",
        "source_boundaries": snapshot["boundaries"],
        "submission": normalized,
    }
    directory_path.mkdir(parents=True, exist_ok=True)
    encoded = canonical_bytes(record)
    temp = directory_path / (review_id + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temp.open("xb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temp, target)
            return record
        except FileExistsError:
            try:
                existing = json.loads(target.read_bytes())
            except (OSError, ValueError) as exc:
                raise GeometryFeedbackConflict("existing_review_unreadable") from exc
            if existing.get("submission") != normalized:
                raise GeometryFeedbackConflict("idempotency_key_reused")
            return existing
    finally:
        temp.unlink(missing_ok=True)


def latest_review(signal_id: str, *, snapshot: dict, directory=None) -> dict | None:
    """Return latest matching revision, never mutate source geometry."""
    if not isinstance(signal_id, str) or not SIGNAL_RE.fullmatch(signal_id):
        return None
    path = _signal_path(signal_id, directory)
    if not path.is_dir():
        return None
    revision = source_revision(snapshot)
    reviews = []
    for file in path.glob("*.json"):
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("review_id") != file.stem
                    or not isinstance(value.get("submission"), dict)):
                raise GeometryFeedbackError("invalid_stored_review")
            if value["submission"].get("snapshot_revision") == revision:
                reviews.append(value)
        except (OSError, ValueError, TypeError) as exc:
            raise GeometryFeedbackError("unreadable_stored_review") from exc
    return max(reviews, key=lambda item: (item["received_at_ms"], item["review_id"])) if reviews else None
