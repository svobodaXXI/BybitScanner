"""Read-only export of owner-reviewed immutable Scanner geometry for offline evaluation.

This is NOT an online-learning path. It never edits archived signals, detector
parameters, Trading Diary, PAPER DB, running Scanner/Robot, or acceptance gates.
Output has no train/validation/test assignment to prevent accidental leakage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from geometry_feedback_store import (
    GeometryFeedbackError, _normalize, bars_digest, latest_review, source_revision,
)
from signal_archive import load_frozen_signal_geometry, load_original_signal
from signal_geometry_snapshot import canonical_bytes

EXPORT_SCHEMA = "owner_geometry_feedback_example_v1"


class GeometryExportError(ValueError):
    pass


def reviewed_example(signal_id: str, *, archive_directory=None, feedback_directory=None) -> dict:
    """Return independently validated, reproduction-ready evidence for one signal.

    The caller must supply the exact immutable signal ID; never search by symbol.
    Uncertain or absent reviews are not silently treated as training labels.
    """
    snapshot = load_frozen_signal_geometry(signal_id, directory=archive_directory)
    source = load_original_signal([signal_id], directory=archive_directory)
    if snapshot is None or source is None:
        raise GeometryExportError("frozen_signal_unavailable")
    try:
        review = latest_review(signal_id, snapshot=snapshot, directory=feedback_directory)
        if review is None or review["submission"]["label"] == "UNCERTAIN":
            raise GeometryExportError("review_not_training_eligible")
        submitted = review["submission"]
        validated = _normalize(submitted, snapshot)
        if validated != submitted or review.get("source_boundaries") != snapshot["boundaries"]:
            raise GeometryExportError("review_source_mismatch")
        token = submitted["idempotency_key"]
        expected_review_id = hashlib.sha256((signal_id + "\0" + token).encode("utf-8")).hexdigest()
        if review.get("review_id") != expected_review_id:
            raise GeometryExportError("review_identity_mismatch")
        return {
            "schema": EXPORT_SCHEMA,
            "split": "UNASSIGNED_REQUIRES_GROUPED_HOLDOUT",
            "review_id": expected_review_id,
            "reviewed_at_ms": review["received_at_ms"],
            "signal_id": signal_id,
            "symbol": snapshot["symbol"],
            "timeframe": snapshot["timeframe"],
            "pattern": source.get("pattern"),
            "source_revision_sha256": source_revision(snapshot),
            "bars_sha256": bars_digest(snapshot),
            "frozen_bars": snapshot["bars"],
            "original_boundaries": snapshot["boundaries"],
            "corrected_boundaries": validated["corrected_boundaries"],
            "label": validated["label"],
            "note": validated["note"],
        }
    except GeometryExportError:
        raise
    except (GeometryFeedbackError, KeyError, TypeError, ValueError, OSError) as exc:
        raise GeometryExportError("unverified_feedback_evidence") from exc


def export_reviewed_examples(
    signal_ids: list[str], output: str | Path, *, archive_directory=None, feedback_directory=None,
) -> int:
    """Create JSONL for explicitly selected reviewed signals, refusing overwrite.

    Validate every sample before creating any file, so partial exports are
    never mistaken for complete evidence. No implicit split or detector update.
    """
    if not signal_ids or len(set(signal_ids)) != len(signal_ids):
        raise GeometryExportError("empty_or_duplicate_signal_ids")
    examples = [
        reviewed_example(signal_id, archive_directory=archive_directory, feedback_directory=feedback_directory)
        for signal_id in sorted(signal_ids)
    ]
    path = Path(output)
    content = b"".join(canonical_bytes(record) + b"\n" for record in examples)
    # Fail closed if output exists; neither import nor export rewrites history.
    with path.open("xb") as handle:
        handle.write(content)
    return len(examples)
