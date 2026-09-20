"""Uncalled, research-only proposals from as-of-confirmed source-time swings.

This module neither detects pivots nor selects a wedge, START, pair or winner.
An alternating four-turn proposal is only a chronological hypothesis: same-side
rival pivots, coincident HIGH/LOW, and left-edge uncertainty are never resolved
by silently choosing an extreme. Trading admission MUST NOT use its statuses.
"""

from __future__ import annotations

import math


STEP_MS = 300_000  # S3 shadow is researched only for source timeframe 5m.
RIGHT_BARS = 3
FOUR_TURNS = 4


def propose_local_episodes(frame, confirmed_points, *, as_of_index, timeframe="5",
                           seed_indices=None):
    """Return bounded four-turn hypotheses, including both HIGH_FIRST and LOW_FIRST.

    Input is a closed 5m source-index OHLC prefix and confirmed raw pivots.
    Each pivot has side/index/price, event_time_ms, confirm_index,
    confirm_time_ms and confirmation_contiguous. Source index is a POSITION in
    this complete prefix (not an index renumbered after dropping bad rows).
    A caller must establish real decision-time cutoff *before* creating frame.
    """
    result = {"status": "UNKNOWN", "reasons": [], "as_of_index": as_of_index,
              "proposals": [], "scope": "UNCHOSEN_CHRONOLOGICAL_SHADOW"}
    reasons = result["reasons"]
    if str(timeframe) != "5" or frame is None or as_of_index is None:
        reasons.append("UNSUPPORTED_TIMEFRAME_OR_MISSING_CLOSED_PREFIX")
        return result
    try:
        end = int(as_of_index)
        if end < 0 or len(frame) != end + 1:
            raise ValueError("prefix")
        times = [int(v) for v in frame["time"]]
        if (any(t < 1_000_000_000_000 or t >= 10_000_000_000_000 for t in times)
                or any(y - x != STEP_MS for x, y in zip(times, times[1:]))):
            raise ValueError("timestamps")
        for column in ("open", "high", "low", "close"):
            if any(not math.isfinite(float(v)) for v in frame[column]):
                raise ValueError("OHLC")
        for candle in frame.itertuples(index=False):
            if not (float(candle.low) <= min(float(candle.open), float(candle.close))
                    <= max(float(candle.open), float(candle.close)) <= float(candle.high)):
                raise ValueError("OHLC envelope")
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        reasons.append("SOURCE_PREFIX_UNPROVEN")
        return result

    entries, seen = [], set()
    try:
        for point in confirmed_points:
            i, j = int(point["index"]), int(point["confirm_index"])
            side = point["side"]
            price = float(point["price"])
            if side not in ("HIGH", "LOW") or (i, side) in seen:
                raise ValueError("duplicate/side")
            if not (0 <= i < j <= end and j == i + RIGHT_BARS
                    and bool(point["confirmation_contiguous"])
                    and int(point["event_time_ms"]) == times[i]
                    and int(point["confirm_time_ms"]) == times[j] + STEP_MS
                    and math.isfinite(price)):
                raise ValueError("confirmation provenance")
            actual = float(frame.iloc[i]["high" if side == "HIGH" else "low"])
            if abs(price - actual) > 1e-12 * max(1.0, abs(actual)):
                raise ValueError("source price")
            seen.add((i, side))
            entries.append({"index": i, "side": side, "price": price,
                            "event_time_ms": times[i], "confirm_index": j,
                            "confirm_time_ms": times[j] + STEP_MS})
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        reasons.append("CONFIRMED_LEDGER_UNPROVEN")
        return result

    entries.sort(key=lambda p: (p["index"], p["side"]))
    both = {p["index"] for p in entries if (p["index"], "HIGH") in seen
            and (p["index"], "LOW") in seen}
    both.update(p["index"] for p in confirmed_points
                if p.get("ambiguous_same_candle", False))
    if seed_indices is not None:
        try:
            seeds = {int(x) for x in seed_indices}
        except (TypeError, ValueError, OverflowError):
            reasons.append("INVALID_SEED_COORDINATES")
            return result
    else:
        seeds = None

    for position, seed in enumerate(entries):
        if seeds is not None and seed["index"] not in seeds:
            continue
        turns = [seed]
        same_side = []
        flags = []
        if seed["index"] in both:
            flags.append("COINCIDENT_SEED_ORDER_UNPROVEN")
        if not any(p["side"] != seed["side"] for p in entries[:position]):
            flags.append("LEFT_HISTORY_NOT_PROVEN")
        cursor = position + 1
        while len(turns) < FOUR_TURNS and cursor < len(entries):
            candidate = entries[cursor]
            cursor += 1
            if candidate["index"] in both:
                flags.append("COINCIDENT_NEXT_TURN_ORDER_UNPROVEN")
                break
            if candidate["side"] == turns[-1]["side"]:
                same_side.append(candidate)
                continue
            turns.append(candidate)
        if same_side:
            flags.append("COMPETING_SAME_SIDE_TURNS")
        status = ("AMBIGUOUS" if any(f.startswith("COINCIDENT") for f in flags)
                  else "UNKNOWN" if flags
                  else "INSUFFICIENT" if len(turns) < FOUR_TURNS
                  else "PROPOSAL_ONLY")
        # Do not conflate an interrupted/ambiguous proposal with a completed wedge.
        result["proposals"].append({
            "seed_index": seed["index"], "seed_side": seed["side"],
            "order": "LOW_FIRST" if seed["side"] == "LOW" else "HIGH_FIRST",
            "status": status, "reasons": flags,
            "turns": [dict(t) for t in turns],
            "competing_same_side": [dict(p) for p in same_side],
            "first_complete_as_of": turns[-1]["confirm_index"]
            if len(turns) == FOUR_TURNS and status == "PROPOSAL_ONLY" else None,
        })
    result["status"] = "OK"
    return result


def trace_episode_checkpoints(frame, confirmed_points, *, as_of_index,
                              seed_index, seed_side, checkpoints, timeframe="5"):
    """Replay bounded source-time checkpoints without joining or selecting episodes.

    This function records which *confirmed* swings were observable at each prefix.
    It does NOT infer that later same-side/alternating pivots belong to a seed's
    wedge, and it never mutates or upgrades an earlier checkpoint.
    """
    out = {"status": "UNKNOWN", "reasons": [], "seed_index": seed_index,
           "seed_side": seed_side, "history": [], "membership": "UNPROVEN"}
    if seed_side not in ("HIGH", "LOW"):
        out["reasons"].append("INVALID_SEED_SIDE")
        return out
    try:
        final = int(as_of_index)
        seed = int(seed_index)
        steps = [int(c) for c in checkpoints]
        if (frame is None or len(frame) != final + 1 or not steps
                or any(c < 0 or c > final for c in steps)
                or steps != sorted(set(steps))):
            raise ValueError("invalid checkpoint range/order")
    except (TypeError, ValueError, OverflowError):
        out["reasons"].append("INVALID_CHECKPOINTS_OR_AS_OF")
        return out

    # Full-prefix provenance is checked once by the existing proposal builder;
    # each selected prefix is independently revalidated on truncated OHLC.
    full = propose_local_episodes(
        frame, confirmed_points, as_of_index=final, timeframe=timeframe,
        seed_indices={seed}
    )
    if full["status"] != "OK":
        out["reasons"].extend(full["reasons"])
        return out
    if not any(p["seed_index"] == seed and p["seed_side"] == seed_side
               for p in full["proposals"]):
        out["reasons"].append("SEED_NOT_CONFIRMED_AT_FULL_AS_OF")
        return out

    previous = -1
    for cutoff in steps:
        prefix = frame.iloc[:cutoff + 1].copy()
        available = [
            dict(p) for p in confirmed_points if int(p["confirm_index"]) <= cutoff
        ]
        checked = propose_local_episodes(
            prefix, available, as_of_index=cutoff, timeframe=timeframe,
            seed_indices={seed}
        )
        if checked["status"] != "OK":
            out["reasons"].extend(checked["reasons"])
            return out
        proposed = next(
            (p for p in checked["proposals"]
             if p["seed_index"] == seed and p["seed_side"] == seed_side),
            None
        )
        new_events = sorted(
            ({"index": p["index"], "side": p["side"],
              "confirm_index": p["confirm_index"],
              "confirm_time_ms": p["confirm_time_ms"]}
             for p in available
             if previous < p["confirm_index"] <= cutoff and p["index"] >= seed),
            key=lambda p: (p["confirm_index"], p["index"], p["side"])
        )
        out["history"].append({
            "as_of_index": cutoff,
            "seed_status": proposed["status"] if proposed else "NOT_YET_CONFIRMED",
            "turn_indices": [t["index"] for t in proposed["turns"]] if proposed else [],
            "competing_same_side_indices": [
                t["index"] for t in proposed["competing_same_side"]
            ] if proposed else [],
            "reasons": list(proposed["reasons"]) if proposed else [],
            "newly_confirmed": new_events,
            "membership": "UNPROVEN",
        })
        previous = cutoff
    out["status"] = "OK"
    return out


def trace_explicit_pair_checkpoints(
    frame, confirmed_points, *, as_of_index, checkpoints, pair_specs, timeframe="5"
):
    """Compare independently supplied anchor pairs only when historically knowable.

    This is a research-side replay of EXPLICIT hindsight hypotheses, not pair
    discovery, episode membership or an algorithm for changing frozen candidates.
    Each pair is evaluated on its own truncated source prefix; the previous
    checkpoint's result is never overwritten by a later pair or later OHLC.
    """
    from .local_pair_shadow import evaluate_local_pair

    out = {"status": "UNKNOWN", "reasons": [], "history": [],
           "scope": "EXPLICIT_PAIR_REPLAY_ONLY", "membership": "UNPROVEN"}
    try:
        final = int(as_of_index)
        steps = [int(c) for c in checkpoints]
        specs = list(pair_specs)
        if (frame is None or len(frame) != final + 1 or not steps
                or steps != sorted(set(steps))
                or steps[0] < 0 or steps[-1] > final or not specs):
            raise ValueError("prefix, checkpoint or specs")
        ids = set()
        checked_specs = []
        for spec in specs:
            pair_id = spec["id"]
            if not isinstance(pair_id, str) or not pair_id or pair_id in ids:
                raise ValueError("duplicate or missing pair ID")
            ids.add(pair_id)
            a = {key: int(spec["anchors"][key]) for key in ("h1", "h2", "l1", "l2")}
            start = int(spec["episode_start"])
            if not (0 <= start <= min(a.values()) and a["h1"] < a["h2"]
                    and a["l1"] < a["l2"] and max(a.values()) <= final):
                raise ValueError("invalid explicit anchors")
            first = min((i, side) for side, i in (
                ("HIGH", a["h1"]), ("HIGH", a["h2"]),
                ("LOW", a["l1"]), ("LOW", a["l2"])
            ))
            checked_specs.append((pair_id, start, a, first))
    except (KeyError, TypeError, ValueError, OverflowError):
        out["reasons"].append("INVALID_EXPLICIT_PAIR_REPLAY_INPUT")
        return out

    # trace_episode_checkpoints performs the full and each historical-prefix
    # source/ledger provenance validation; it DOES NOT infer episode membership.
    trace_by_id = {}
    for pair_id, _, _, (seed_index, seed_side) in checked_specs:
        traced = trace_episode_checkpoints(
            frame, confirmed_points, as_of_index=final,
            seed_index=seed_index, seed_side=seed_side,
            checkpoints=steps, timeframe=timeframe,
        )
        if traced["status"] != "OK":
            out["reasons"].extend(traced["reasons"])
            return out
        trace_by_id[pair_id] = traced["history"]

    frozen_first = {}  # One independent baseline per explicit pair ID, never revised.
    for position, cutoff in enumerate(steps):
        prefix = frame.iloc[:cutoff + 1].copy()
        available = [
            dict(p) for p in confirmed_points if int(p["confirm_index"]) <= cutoff
        ]
        keys = {(int(p["index"]), p["side"]) for p in available}
        rows = []
        for pair_id, start, anchors, _ in checked_specs:
            required = [(anchors["h1"], "HIGH"), (anchors["h2"], "HIGH"),
                        (anchors["l1"], "LOW"), (anchors["l2"], "LOW")]
            present = [{"index": i, "side": side} for i, side in required
                       if (i, side) in keys]
            chronological = trace_by_id[pair_id][position]
            row = {"id": pair_id, "as_of_index": cutoff,
                   "anchors": dict(anchors), "episode_start": start,
                   "confirmed_anchors": present,
                   "seed_status": chronological["seed_status"],
                   "seed_reasons": list(chronological["reasons"]),
                   "membership": "UNPROVEN",
                   "pair_status": "NOT_YET_EVALUABLE",
                   "pair_result": None}
            if len(present) == len(required):
                result = evaluate_local_pair(
                    prefix, available, as_of_index=cutoff, timeframe=timeframe,
                    episode_start=start, anchors=dict(anchors),
                )
                row["pair_status"] = result["status"]
                row["pair_result"] = result
                e = result.get("strict", {}).get("E") or {}
                if pair_id not in frozen_first:
                    frozen_first[pair_id] = {
                        "as_of_index": cutoff, "status": result["status"],
                        "e_body": tuple(e.get("body_indices", ())),
                        "e_wick": tuple(e.get("wick_indices", ())),
                    }
                frozen = frozen_first[pair_id]
                # The baseline is the first REQUESTED evaluable checkpoint;
                # it may be later than the first knowable right-confirmation bar.
                row["first_knowable_as_of"] = max(anchors.values()) + RIGHT_BARS
                row["baseline_checked_as_of"] = frozen["as_of_index"]
                row["frozen_first_status"] = frozen["status"]
                row["extension_since_first"] = None
                if cutoff > frozen["as_of_index"]:
                    post_anchor = sorted(
                        ({"index": int(point["index"]), "side": point["side"],
                          "confirm_index": int(point["confirm_index"])}
                         for point in available
                         if max(anchors.values()) < int(point["index"])
                         and frozen["as_of_index"] < int(point["confirm_index"]) <= cutoff),
                        key=lambda point: (point["confirm_index"], point["index"],
                                           point["side"]),
                    )
                    new_bodies = sorted(set(e.get("body_indices", ()))
                                        - set(frozen["e_body"]))
                    new_wicks = sorted(set(e.get("wick_indices", ()))
                                       - set(frozen["e_wick"]))
                    row["extension_since_first"] = {
                        "status": ("EXCURSION_OBSERVED" if new_bodies or new_wicks
                                   else "NEW_POST_ANCHOR_PIVOT" if post_anchor
                                   else "NO_NEW_EVIDENCE"),
                        "membership": "UNPROVEN",
                        "new_E_body_indices": new_bodies,
                        "new_E_wick_indices": new_wicks,
                        "new_confirmed_post_anchor_pivots": post_anchor,
                    }
            rows.append(row)
        out["history"].append({"as_of_index": cutoff, "pairs": rows})
    out["status"] = "OK"
    return out
