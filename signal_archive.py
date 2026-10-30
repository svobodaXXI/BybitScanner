"""Durable archive of the exact Telegram signal that produced a Robot candidate.

The Scanner posts a chart PNG plus text. The chart file on disk is overwritten
by the next signal for the same symbol, and the Telegram message ids were never
stored, so the original could not be shown again. This module keeps, per Robot
candidate id (an exact key, never a ticker match), an immutable copy of the
image bytes, the text and the original send time. The first record for a key
wins; a later send never replaces it. Writing is best effort and must never
affect signal delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterable, Mapping

ARCHIVE_VERSION = 1
ARCHIVE_ENV = "BYBITSCANNER_SIGNAL_ARCHIVE_DIR"
_DEFAULT_DIR = Path(__file__).resolve().parent / "review_queue" / "signal_archive"


def archive_dir(directory=None) -> Path:
    if directory is not None:
        return Path(directory)
    override = os.environ.get(ARCHIVE_ENV, "").strip()
    return Path(override) if override else _DEFAULT_DIR


def _key(candidate_id: str) -> str:
    return hashlib.sha256(str(candidate_id).encode("utf-8")).hexdigest()[:40]


def _largest_photo_file_id(response) -> str | None:
    """file_id of the biggest photo size in a successful sendPhoto response."""
    if not isinstance(response, Mapping) or response.get("ok") is not True:
        return None
    photos = (response.get("result") or {}).get("photo")
    if not isinstance(photos, list) or not photos:
        return None
    last = photos[-1]
    file_id = last.get("file_id") if isinstance(last, Mapping) else None
    return file_id if isinstance(file_id, str) and file_id else None


def _message_id(response) -> int | None:
    if not isinstance(response, Mapping) or response.get("ok") is not True:
        return None
    value = (response.get("result") or {}).get("message_id")
    return value if isinstance(value, int) else None


def record_original_signal(
    candidate_id, *, symbol, timeframe, pattern, text, image_bytes,
    photo_response=None, text_response=None, sent_at_ms=None, directory=None,
    source_formation_ids=None,
) -> bool:
    """Persist the original signal for ``candidate_id``. Never raises; True if stored."""
    try:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id or not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            return False
        root = archive_dir(directory)
        root.mkdir(parents=True, exist_ok=True)
        key = _key(candidate_id)
        meta_path, image_path = root / f"{key}.json", root / f"{key}.png"
        if meta_path.exists():
            return True  # immutable: the first record is the original
        image = bytes(image_bytes)
        tmp_image = root / f"{key}.png.tmp"
        tmp_image.write_bytes(image)
        os.replace(tmp_image, image_path)
        meta = {
            "version": ARCHIVE_VERSION,
            "candidate_id": candidate_id,
            "symbol": str(symbol),
            "timeframe": str(timeframe),
            "pattern": str(pattern),
            "text": str(text or ""),
            "source_formation_ids": sorted({str(v) for v in (source_formation_ids or ()) if v}),
            "sent_at_ms": int(time.time() * 1000) if sent_at_ms is None else int(sent_at_ms),
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "image_file": image_path.name,
            "photo_file_id": _largest_photo_file_id(photo_response),
            "photo_message_id": _message_id(photo_response),
            "text_message_id": _message_id(text_response),
        }
        tmp_meta = root / f"{key}.json.tmp"
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp_meta, meta_path)  # the json is the commit marker
        return True
    except Exception as exc:  # delivery of the live signal must never depend on this
        print("[SIGNAL ARCHIVE ERROR]", type(exc).__name__, exc)
        return False


def load_original_signal(candidate_ids: Iterable, *, directory=None) -> dict | None:
    """The archived original for the first exact id that has an intact record, else None.

    A record is returned only if its key matches, the image exists and its bytes
    match the stored sha256. Anything else is treated as not archived.
    """
    root = archive_dir(directory)
    for candidate_id in candidate_ids:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            continue
        key = _key(candidate_id)
        try:
            meta = json.loads((root / f"{key}.json").read_text(encoding="utf-8"))
            if (meta.get("version") != ARCHIVE_VERSION
                    or meta.get("candidate_id") != candidate_id
                    or meta.get("image_file") != f"{key}.png"):
                continue
            image_path = root / meta["image_file"]
            if hashlib.sha256(image_path.read_bytes()).hexdigest() != meta.get("image_sha256"):
                continue
            meta["image_path"] = str(image_path)
            return meta
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return None
