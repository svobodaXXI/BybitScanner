"""Compact deterministic runner for RVL-G2 Geometry Gold.

This module references existing frozen OHLC fixtures. It does not fetch market
data, mutate production configuration, or implement a second geometry engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

import geometry.engine as engine
from pivots import find_pivots
from wedge import analyze_wedge
from wedge.analyzer import _freshness_predicate
from wedge.detector import detect_structure


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "geometry_gold" / "manifest_v1.json"
STANDARD_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def geometry_identity(geometry) -> list[int] | None:
    if geometry is None:
        return None
    return [
        int(geometry.upper_line["anchor_index"]),
        int(geometry.upper_line["second_index"]),
        int(geometry.lower_line["anchor_index"]),
        int(geometry.lower_line["second_index"]),
        int(geometry.start_index),
        int(geometry.end_index),
    ]


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported Geometry Gold manifest schema")
    return payload


def _load_frame(case: dict[str, Any]) -> pd.DataFrame:
    fixture_path = ROOT / case["fixture_ref"]
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if "fixture_case" in case:
        source = payload["cases"][case["fixture_case"]]
        frame = pd.DataFrame(source["candles"], columns=STANDARD_COLUMNS)
    else:
        candles = payload["candles"]
        frame = (
            pd.DataFrame(candles, columns=payload["columns"])
            if payload.get("columns")
            else pd.DataFrame(candles)
        )
    cutoff = int(case["as_of_index"])
    if cutoff < 0 or cutoff >= len(frame):
        raise ValueError(f"{case['case_id']}: as_of_index outside fixture")
    return frame.iloc[: cutoff + 1].reset_index(drop=True)


def _analyze(frame: pd.DataFrame):
    highs, lows = find_pivots(frame.copy())
    geometry = engine.analyze_geometry(
        highs,
        lows,
        current_index=len(frame) - 1,
        candles=frame,
        freshness_predicate=_freshness_predicate,
    )
    return highs, lows, geometry


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    frame = _load_frame(case)
    highs, lows, geometry = _analyze(frame)
    expectation = case["expectation"]
    kind = expectation["kind"]
    errors: list[str] = []
    observed: dict[str, Any] = {
        "geometry_identity": geometry_identity(geometry),
    }

    if kind == "POSITIVE_ANCHOR":
        expected_identity = expectation["geometry_identity"]
        if observed["geometry_identity"] != expected_identity:
            errors.append(
                f"geometry identity {observed['geometry_identity']} != {expected_identity}"
            )
        detected = bool(
            geometry is not None
            and detect_structure(geometry, candles=frame).get("detected")
        )
        observed["detected"] = detected
        if detected != bool(expectation["detected"]):
            errors.append(f"detected {detected} != {expectation['detected']}")

    elif kind == "FORBIDDEN_ANCHOR_PAIR":
        pair = None
        if geometry is not None:
            pair = [
                int(geometry.upper_line["anchor_index"]),
                int(geometry.lower_line["anchor_index"]),
            ]
        observed["anchor_pair"] = pair
        if pair == expectation["forbidden_anchor_pair"]:
            errors.append(f"forbidden anchor pair selected: {pair}")

        wedge_result = analyze_wedge(
            highs,
            lows,
            current_index=len(frame) - 1,
            candles=frame,
        )
        pattern = wedge_result.get("pattern") if wedge_result else None
        observed["pattern"] = pattern
        if pattern == expectation["forbidden_pattern"]:
            errors.append(f"forbidden pattern emitted: {pattern}")

    elif kind == "LOCALITY_INVARIANT":
        if geometry is None:
            errors.append("expected an admitted local geometry")
        else:
            interval = [int(geometry.start_index), int(geometry.end_index)]
            span = interval[1] - interval[0]
            fresh = bool(
                _freshness_predicate(
                    geometry.start_index,
                    geometry.end_index,
                    (geometry.apex or {}).get("index"),
                    geometry.current_index,
                )
            )
            observed.update({"interval": interval, "span": span, "fresh": fresh})
            if span > int(expectation["max_span"]):
                errors.append(f"span {span} exceeds {expectation['max_span']}")
            if interval == expectation["forbidden_interval"]:
                errors.append(f"forbidden interval selected: {interval}")
            if fresh != bool(expectation["fresh"]):
                errors.append(f"fresh {fresh} != {expectation['fresh']}")

    elif kind == "NO_GEOMETRY":
        if geometry is not None:
            errors.append(f"expected no geometry, got {observed['geometry_identity']}")

    else:
        raise ValueError(f"{case['case_id']}: unsupported expectation kind {kind}")

    return {
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "expectation_kind": kind,
        "passed": not errors,
        "errors": errors,
        "observed": observed,
    }


def run_geometry_gold(path: Path = MANIFEST) -> list[dict[str, Any]]:
    manifest = load_manifest(path)
    return [run_case(case) for case in manifest["cases"]]
