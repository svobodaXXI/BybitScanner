"""Local checksum-reported 5m Bybit OI CSV for existing virtual Robot entries.

The input is an explicit local historical research dataset, NOT an assertion
of authoritative API delivery time. Its CSV SHA identifies exact replay inputs.
"""
from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

from robot_entry_flow_evidence import (
    OI_INTERVAL_MS, OpenInterestPoint,
)

MAX_OI_BYTES = 8_000_000
MAX_OI_ROWS = 40_000
EXPECTED_SOURCE = "Bybit V5 public open-interest API"


def load_oi_csv(
    path: Path, *, symbol: str,
) -> tuple[tuple[OpenInterestPoint, ...], str]:
    """Load owner-supplied OI CSV only for the requested instrument.

    Exact filename binds the otherwise symbol-free research CSV to a symbol.
    Require monotonically ordered 5m snapshots, never interpolate gaps.
    """
    if (not isinstance(path, Path) or not isinstance(symbol, str)
            or not symbol.endswith("USDT") or not symbol.isalnum()
            or path.name != symbol + ".csv" or path.is_symlink()
            or not path.is_file()):
        raise ValueError("explicit matching local OI CSV required")
    if not 0 < path.stat().st_size <= MAX_OI_BYTES:
        raise ValueError("OI CSV outside bounded size limit")
    blob = path.read_bytes()
    fingerprint = hashlib.sha256(blob).hexdigest()
    import io
    rows: list[OpenInterestPoint] = []
    try:
        reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""))
        fields = reader.fieldnames
        if (not fields or len(fields) != len(set(fields)) or not
                {"timestamp_ms", "open_interest_base", "source", "native_interval"}
                <= set(fields)):
            raise ValueError("historical OI CSV schema missing")
        for row in reader:
            if len(rows) >= MAX_OI_ROWS:
                raise ValueError("OI CSV exceeds bounded row budget")
            if row["source"] != EXPECTED_SOURCE or row["native_interval"] != "5min":
                raise ValueError("historical OI provenance/period mismatch")
            try:
                if not row["timestamp_ms"].isdigit():
                    raise ValueError("invalid OI timestamp")
                point = OpenInterestPoint(
                    timestamp_ms=int(row["timestamp_ms"]),
                    open_interest_base=Decimal(row["open_interest_base"]),
                )
            except (InvalidOperation, TypeError) as exc:
                raise ValueError("invalid OI record") from exc
            if rows and point.timestamp_ms <= rows[-1].timestamp_ms:
                raise ValueError("historical OI sequence not strictly ordered")
            rows.append(point)
    except UnicodeError as exc:
        raise ValueError("OI CSV must be UTF-8") from exc
    if len(rows) < 2:
        raise ValueError("two historical OI samples required")
    return tuple(rows), fingerprint
