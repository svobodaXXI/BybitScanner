"""Bounded offline preflight for original Bybit orderbook .data.zip.

No market orders, trades, Robot runtime, network or OHLC matching.
A valid archive is not independent proof that a WebSocket capture has no gaps.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED, ZIP_STORED

MAX_ARCHIVE_BYTES = 512_000_000
MAX_MEMBER_BYTES = 8_000_000_000
MAX_LINE_BYTES = 1_000_000
MAX_EVENTS = 8_000_000
DAY_BEGIN_MS = 1794268800000
DAY_END_MS = 1794355200000
SYMBOL = "ICNTUSDT"
DEPTH = 200


def _check_levels(value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("missing L2 side level list")
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("malformed L2 level")
        p, size = row
        if not isinstance(p, str) or not isinstance(size, str):
            raise ValueError("L2 levels must be original decimal strings")
        try:
            price, volume = Decimal(p), Decimal(size)
        except InvalidOperation as exc:
            raise ValueError("invalid L2 decimal value") from exc
        if (not price.is_finite() or not volume.is_finite()
                or price <= 0 or volume < 0 or p in seen):
            raise ValueError("invalid or duplicate L2 level")
        seen.add(p)


def inspect(archive_path: Path, expected_sha256: str, expected_records: int = 569169) -> dict:
    if (not isinstance(archive_path, Path) or archive_path.is_symlink()
            or not archive_path.is_file()
            or not 0 < archive_path.stat().st_size <= MAX_ARCHIVE_BYTES):
        raise ValueError("missing or unsafe pinned L2 archive")
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("explicit lowercase SHA-256 required")
    actual = hashlib.sha256()
    with archive_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1_048_576), b""):
            actual.update(chunk)
    if actual.hexdigest() != expected_sha256:
        raise ValueError("L2 ZIP source SHA-256 mismatch")

    totals: Counter[str] = Counter()
    first = last = None
    prior_at = prior_seq = prior_u = None
    max_gap = 0
    update_gaps = 0
    update_gap_first_samples: list[dict[str, int]] = []
    snapshot_transitions: list[dict[str, int]] = []
    gap_samples: list[dict[str, int]] = []
    anomalies: list[dict[str, int | str]] = []
    covered_minutes: set[int] = set()

    try:
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ValueError("ZIP requires exactly one original .data member")
            member = members[0]
            if (member.is_dir() or member.filename != Path(member.filename).name
                    or not member.filename.endswith(".data")
                    or "\\" in member.filename or member.flag_bits & 1
                    or member.compress_type not in (ZIP_DEFLATED, ZIP_STORED)
                    or not 0 < member.file_size <= MAX_MEMBER_BYTES):
                raise ValueError("unsafe historical L2 ZIP member")
            with archive.open(member) as fh:
                while True:
                    raw = fh.readline(MAX_LINE_BYTES + 1)
                    if not raw:
                        break
                    totals["records"] += 1
                    if totals["records"] > MAX_EVENTS or len(raw) > MAX_LINE_BYTES:
                        raise ValueError("L2 record/line budget exceeded")
                    try:
                        message = json.loads(raw)
                    except (UnicodeDecodeError, ValueError) as exc:
                        raise ValueError(f"invalid JSONL at record {totals['records']}") from exc
                    if (not isinstance(message, dict)
                            or message.get("topic") != f"orderbook.{DEPTH}.{SYMBOL}"
                            or message.get("type") not in ("snapshot", "delta")):
                        raise ValueError(f"foreign or malformed L2 topic/type at {totals['records']}")
                    data = message.get("data")
                    if not isinstance(data, dict) or data.get("s") != SYMBOL:
                        raise ValueError("foreign or malformed L2 payload")
                    ts, cts = message.get("ts"), message.get("cts")
                    u, seq = data.get("u"), data.get("seq")
                    if (type(ts) is not int or type(cts) is not int
                            or type(u) is not int or type(seq) is not int
                            or ts < 0 or cts < 0 or cts > ts or u < 1 or seq < 1):
                        raise ValueError(f"invalid L2 clocks/sequence at {totals['records']}")
                    if not DAY_BEGIN_MS <= ts < DAY_END_MS + 5000:
                        raise ValueError(f"L2 message outside expected day boundary at {totals['records']}")
                    _check_levels(data.get("b"))
                    _check_levels(data.get("a"))
                    kind = message["type"]
                    if first is None:
                        if kind != "snapshot":
                            raise ValueError("first L2 message lacks snapshot")
                        first = {"ts_ms": ts, "cts_ms": cts, "update_id": u, "seq": seq}
                    if prior_at is not None:
                        if ts < prior_at:
                            raise ValueError(f"L2 timestamps reversed at {totals['records']}")
                        gap = ts - prior_at
                        if gap > max_gap:
                            max_gap = gap
                        if gap > 1000:
                            totals["gaps_over_1s"] += 1
                            if len(gap_samples) < 8:
                                gap_samples.append({"before_ts_ms": prior_at, "after_ts_ms": ts, "gap_ms": gap})
                        if kind == "delta":
                            # Within an uninterrupted Bybit depth-200 stream, the
                            # update ID advances by exactly one. Unlike seq,
                            # u is not a cross-channel version number.
                            if u > prior_u + 1:
                                update_gaps += 1
                                if len(update_gap_first_samples) < 8:
                                    update_gap_first_samples.append({
                                        "record": totals["records"],
                                        "before_u": prior_u, "after_u": u,
                                        "missing_update_ids": u - prior_u - 1,
                                    })
                            if u <= prior_u:
                                totals["nonincreasing_delta_u"] += 1
                                if len(anomalies) < 8:
                                    anomalies.append({"record": totals["records"], "issue": "nonincreasing_delta_u", "ts_ms": ts})
                            if seq <= prior_seq:
                                totals["nonincreasing_delta_seq"] += 1
                                if len(anomalies) < 8:
                                    anomalies.append({"record": totals["records"], "issue": "nonincreasing_delta_seq", "ts_ms": ts})
                        else:
                            if len(snapshot_transitions) < 8:
                                snapshot_transitions.append({
                                    "record": totals["records"],
                                    "before_u": prior_u, "snapshot_u": u,
                                    "ts_ms": ts,
                                })
                        if kind == "snapshot" and seq < prior_seq and u != 1:
                            totals["snapshot_seq_rollback_without_reset"] += 1
                            if len(anomalies) < 8:
                                anomalies.append({"record": totals["records"], "issue": "snapshot_seq_rollback_without_reset", "ts_ms": ts})
                    prior_at, prior_seq, prior_u = ts, seq, u
                    totals[kind] += 1
                    if ts < DAY_END_MS:
                        covered_minutes.add((ts - DAY_BEGIN_MS) // 60000)
                    else:
                        totals["after_day_boundary"] += 1
                    last = {"ts_ms": ts, "cts_ms": cts, "update_id": u, "seq": seq}
                # Fully exhausting ZipExtFile establishes CRC validation.
    except BadZipFile as exc:
        raise ValueError("original L2 ZIP member CRC invalid") from exc

    if totals["records"] != expected_records:
        raise ValueError(f"L2 record count mismatch: {totals['records']} != {expected_records}")
    if first is None or totals["snapshot"] == 0:
        raise ValueError("missing initial snapshot")
    if not DAY_BEGIN_MS <= first["ts_ms"] < DAY_BEGIN_MS + 10000:
        raise ValueError("no near-day-start L2 snapshot")
    if last is None or last["ts_ms"] < DAY_END_MS:
        raise ValueError("L2 archive terminates before UTC day end")
    if update_gaps:
        totals["nonconsecutive_delta_u"] = update_gaps
    issues = {
        key: totals[key] for key in (
            "nonincreasing_delta_u", "nonconsecutive_delta_u",
            "nonincreasing_delta_seq",
            "snapshot_seq_rollback_without_reset",
        ) if totals[key]
    }
    return {
        "schema": "BYBIT_L2_ARCHIVE_STRUCTURE_AUDIT_V1",
        "symbol": SYMBOL, "utc_day": "2026-11-10", "depth": DEPTH,
        "source_zip_sha256": actual.hexdigest(),
        "records": totals["records"],
        "snapshots": totals["snapshot"],
        "deltas": totals["delta"],
        "first": first, "last": last,
        "start_coverage_gap_ms": first["ts_ms"] - DAY_BEGIN_MS,
        "minute_buckets_with_messages": len(covered_minutes),
        "largest_gap_ms": max_gap,
        "gaps_over_1s": totals["gaps_over_1s"],
        "gap_samples": gap_samples,
        "messages_after_day_end": totals["after_day_boundary"],
        "sequence_anomaly_counts": issues,
        "sequence_anomaly_samples": anomalies,
        "delta_update_id_gap_samples": update_gap_first_samples,
        "snapshot_update_id_transitions": snapshot_transitions,
        "first_to_last_update_id_difference": last["update_id"] - first["update_id"],
        "delta_update_id_continuity": (
            "NO_GAP_DETECTED_WITHIN_CAPTURE" if not issues
            else "DISCONTINUITY_DETECTED"
        ),
        "structural_result": "PROVISIONAL" if issues else "METADATA_CONSISTENT",
        "capture_completeness": "UNPROVEN_ARCHIVE_ALONE_CANNOT_PROVE_MISSING_MESSAGES",
        "cross_channel_taker_book_order": "UNPROVEN_INDEPENDENT_ARCHIVES",
        "real_l2_simulation_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--records", type=int, default=569169)
    args = parser.parse_args()
    report = inspect(args.archive, args.sha256, args.records)
    if args.out.exists():
        raise SystemExit("BLOCKED: refusing to overwrite previous L2 audit")
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("L2_AUDIT_WRITTEN=" + str(args.out))
    print("STRUCTURAL_RESULT=" + report["structural_result"])
    print("CAPTURE_COMPLETENESS=" + report["capture_completeness"])


if __name__ == "__main__":
    main()
