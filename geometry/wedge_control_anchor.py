"""Source-time strict wedge boundary proposals; not trading decisions."""
from decimal import Decimal, InvalidOperation
from .envelope_metrics import evaluate_strict_wedge_wicks
from .trendline import fit_anchor_trendline


def propose_control_boundary(*, family, episode_start, first_strict_index,
                             previous_extreme, trade_price, event_index,
                             event_time_ms, established_pivots, candles):
    """Preserve episode and first strict contact; propose a clean revision.

    Caller supplies established strict-side pivots (index, price, known_at_ms)
    and the actual as-of candle prefix, including the in-progress event bar.
    No inference of intrabar order from completed OHLC. Whole-geometry
    validation and durable revision publication belong to the integration.
    """
    if family not in ("falling", "rising"):
        raise ValueError("invalid family")
    old, price = Decimal(str(previous_extreme)), Decimal(str(trade_price))
    if not all(v.is_finite() and v > 0 for v in (old, price)):
        raise ValueError("invalid price")
    if not (price < old if family == "falling" else price > old):
        return {"status": "UNCHANGED", "lines": []}
    result = {"status": "REBUILD_UNAVAILABLE", "lines": [],
              "episode_start": episode_start, "event_time_ms": event_time_ms,
              "trigger_price": str(price)}
    if (candles is None or any(type(i) is not int for i in
            (episode_start, first_strict_index, event_index, event_time_ms))
            or not 0 <= episode_start <= first_strict_index < event_index < len(candles)
            or event_time_ms <= 0):
        return result
    side = "upper" if family == "falling" else "lower"
    column, opposite = ("high", "low") if side == "upper" else ("low", "high")
    points = {}
    try:
        if Decimal(str(candles[opposite].iloc[event_index])) != price:
            return result
        for p in established_pivots:
            i, known = p["index"], p["known_at_ms"]
            if type(i) is not int or type(known) is not int:
                return result
            if not first_strict_index <= i < event_index or not 0 < known <= event_time_ms:
                continue
            if Decimal(str(p["price"])) != Decimal(str(candles[column].iloc[i])):
                return result
            if i in points and points[i] != p:
                return result
            points[i] = dict(p)
    except (KeyError, TypeError, ValueError, IndexError, InvalidOperation, AttributeError):
        return result
    if first_strict_index not in points or len(points) < 2:
        return result
    first, control = points[first_strict_index], points[max(points)]
    result["control_anchor"] = dict(control)

    def measure(second):
        line = fit_anchor_trendline([first, second])
        if line is None or not (line["slope"] < 0 if side == "upper" else line["slope"] > 0):
            return None, None
        return line, evaluate_strict_wedge_wicks(line, candles, side, event_index, event_index)

    line, breaches = measure(control)
    if breaches == []:
        return dict(result, status="CONTROL_CONTACT", lines=[line])
    # The fallback is permitted only for a measured earlier structural
    # protrusion, not for a subsequent breakout or a failed trading gate.
    earlier = {i for i in points if first_strict_index < i < control["index"]}
    if not breaches or not earlier.intersection(breaches):
        return result
    fallback = []
    for i in sorted(earlier):
        alternative, outside = measure(points[i])
        if outside == []:
            fallback.append(alternative)
    if fallback:
        return dict(result, status="OUTER_ENVELOPE", lines=fallback)
    return result

def propose_control_boundary_from_print(
    *, family, episode_start, first_strict_index, established_pivots,
    candles, timeframe_ms, prefix_as_of_ms, observed_print,
):
    """Evaluate one already-validated publicTrade print in native TF coordinates.

    The caller supplies an event-ordered, gap-free *local candle prefix*
    before this print, including any earlier prints in the active candle.
    This does not certify complete exchange coverage or publish geometry.
    Derive point 2 from that prefix, never from a completed future candle
    or a caller-provided extreme. Process a new candle on its first print;
    process a further extreme in the same candle without waiting for close.
    """
    from numbers import Integral
    import pandas as pd

    unavailable = {"status": "REBUILD_UNAVAILABLE", "lines": []}
    try:
        event_ms = observed_print.timestamp_ms
        receipt_ms = observed_print.received_at_ms
        trade_id = observed_print.trade_id
        price = Decimal(str(observed_print.price))
        if (family not in ("falling", "rising")
                or timeframe_ms not in (60_000, 300_000)
                or type(prefix_as_of_ms) is not int
                or type(event_ms) is not int or type(receipt_ms) is not int
                or not 0 < prefix_as_of_ms <= event_ms
                or receipt_ms <= 0 or not isinstance(trade_id, str) or not trade_id
                or not price.is_finite() or price <= 0
                or type(episode_start) is not int
                or type(first_strict_index) is not int
                or not 0 <= episode_start <= first_strict_index < len(candles)):
            return unavailable
        opens = list(candles["open_time_ms"])
        if any(not isinstance(t, Integral) or isinstance(t, bool)
               or t <= 0 or t % timeframe_ms for t in opens):
            return unavailable
        if any(b - a != timeframe_ms for a, b in zip(opens, opens[1:])):
            return unavailable
        event_open = event_ms // timeframe_ms * timeframe_ms
        last_open = int(opens[-1])
        if (not last_open <= prefix_as_of_ms <= last_open + timeframe_ms
                or event_open not in (last_open, last_open + timeframe_ms)):
            return unavailable
        extreme_column = "low" if family == "falling" else "high"
        prior = [Decimal(str(v)) for v in candles[extreme_column].iloc[episode_start:]]
        if not all(v.is_finite() and v > 0 for v in prior):
            return unavailable
        old = min(prior) if family == "falling" else max(prior)
        if not (price < old if family == "falling" else price > old):
            return {"status": "UNCHANGED", "lines": []}

        # Only the actual prefix plus this print may influence wick tests.
        # Keep the frozen caller-owned candle frame untouched.
        columns = ["open_time_ms", "open", "high", "low", "close"]
        if event_open == last_open:
            row = candles.iloc[-1]
            high, low, opening = (
                Decimal(str(row[name])) for name in ("high", "low", "open")
            )
            if not all(v.is_finite() and v > 0 for v in (high, low, opening)):
                return unavailable
            if not low <= opening <= high:
                return unavailable
            base = candles[columns].iloc[:-1]
            row = [event_open, opening, max(high, price), min(low, price), price]
        else:
            base = candles[columns]
            row = [event_open, price, price, price, price]
        event_prefix = pd.concat(
            [base, pd.DataFrame([row], columns=columns)], ignore_index=True,
        )
        result = propose_control_boundary(
            family=family, episode_start=episode_start,
            first_strict_index=first_strict_index, previous_extreme=old,
            trade_price=price, event_index=len(event_prefix)-1,
            event_time_ms=event_ms, established_pivots=established_pivots,
            candles=event_prefix,
        )
        return dict(result, source_trade_id=trade_id, received_at_ms=receipt_ms,
                    previous_extreme=str(old), source_bar_open_ms=event_open)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError,
            InvalidOperation, OverflowError):
        return unavailable

def load_control_anchor_seed(record, *, directory=None):
    """Restore an observation seed from the exact immutable native signal.

    No substitution of Robot's projected M1 geometry, current chart candles,
    or guessed START. The returned prefix ends at the Scanner decision bar.
    Its pivots are established as of that closed-bar cutoff, not guessed
    historical confirmation times. Missing or inconsistent evidence is not
    a new signal and must not authorize a revision.
    """
    import pandas as pd
    from signal_archive import load_frozen_signal_geometry
    from signal_geometry_snapshot import validate_snapshot
    from pivots import find_pivots
    from .triangle_boundaries import local_alternation_pivots

    try:
        signal = record.signal_snapshot
        candidate_id = record.candidate_id
        symbol = record.symbol.value
        family = {"Falling Wedge": "falling", "Rising Wedge": "rising"}.get(
            signal.get("pattern")
        )
        if family is None or signal.get("symbol") != symbol:
            return None
        timeframe = str(signal.get("timeframe", ""))
        interval = {"1": 60_000, "5": 300_000}.get(timeframe)
        if interval is None:
            return None
        source = load_frozen_signal_geometry(candidate_id, directory=directory)
        if source is None:
            return None
        _, digest = validate_snapshot(
            source, candidate_id=candidate_id, symbol=symbol, timeframe=timeframe,
        )
        geometry = signal["geometry"]
        current, start, end = (geometry[k] for k in
                               ("current_index", "start_index", "end_index"))
        if (any(type(i) is not int for i in (current, start, end))
                or not 0 <= start < end <= current < len(source["bars"])):
            return None
        bars = source["bars"][:current+1]
        times = [bar["open_time_ms"] for bar in bars]
        if (any(t <= 0 or t % interval for t in times)
                or any(b-a != interval for a, b in zip(times, times[1:]))):
            return None
        cutoff = times[-1] + interval
        boundaries = {b["boundary_id"]: b for b in source["boundaries"]}
        first_indices = []
        for side in ("upper", "lower"):
            line = geometry[side+"_line"]
            boundary = boundaries[side]
            first, second = line["anchor_index"], line["second_index"]
            if (line.get("model") != "anchor" or boundary["kind"] != "ray"
                    or type(first) is not int or type(second) is not int
                    or not start <= first < second <= end):
                return None
            wick = "high" if side == "upper" else "low"
            for index, field, point in zip(
                (first, second), ("anchor_price", "second_price"), boundary["anchors"],
            ):
                price = Decimal(str(line[field]))
                if (point["bar_open_time_ms"] != times[index]
                        or price != Decimal(str(point["price"]))
                        or price != Decimal(str(bars[index][wick]))):
                    return None
            first_indices.append(first)
        if min(first_indices) != start:
            return None
        strict_side = "upper" if family == "falling" else "lower"
        strict_index = geometry[strict_side+"_line"]["anchor_index"]
        strict_second = geometry[strict_side+"_line"]["second_index"]
        frame = pd.DataFrame(bars)
        # Same global and local confirmed-pivot sources as wedge construction.
        global_highs, global_lows = find_pivots(frame.copy())
        local_highs, local_lows = local_alternation_pivots(frame, current)
        pivots = (global_highs + local_highs if family == "falling"
                  else global_lows + local_lows)
        established = {
            p["index"]: {"index": p["index"], "price": float(p["price"]),
                         "known_at_ms": cutoff}
            for p in pivots if strict_index <= p["index"] <= current
        }
        if not {strict_index, strict_second}.issubset(established):
            return None
        return {
            "candidate_id": candidate_id, "symbol": symbol, "family": family,
            "timeframe_ms": interval, "source_geometry_sha256": digest,
            "episode_start": start, "first_strict_index": strict_index,
            "prefix_as_of_ms": cutoff, "candles": frame,
            "established_pivots": [established[i] for i in sorted(established)],
            "original_strict_line": dict(geometry[strict_side+"_line"]),
            "original_opposite_line": dict(geometry[("lower" if strict_side == "upper" else "upper")+"_line"]),
        }
    except (AttributeError, KeyError, TypeError, ValueError, IndexError,
            InvalidOperation, OverflowError):
        return None


def validate_revision_pairs(*, family, episode_start, original_opposite_line,
                            proposed_lines, candles):
    """Revalidate exact proposed contacts in the native wedge pair engine.

    The last row is the event-time partial candle, never a confirmed
    right-side pivot. Preserve the original opposite ray and START; do
    not rank a different formation or substitute an unrelated boundary.
    Only clean, canonical, still-converging pairs are returned.
    """
    import math
    from pivots import find_pivots
    from .candidate import build_candidate_lines
    from .evaluation import evaluate_candidate_pair
    from .engine import _is_candidate_local, _is_boundary_structurally_valid, _is_anchor_sequence_valid
    from .wedge_boundaries import (
        build_strict_wedge_support_lines, build_wedge_hull_support_lines,
        strict_support_pair_allowed, wedge_hull_pair_allowed,
    )

    def identity(line):
        return tuple(line[k] for k in (
            "anchor_index", "anchor_price", "second_index", "second_price",
            "slope", "intercept",
        ))

    try:
        if family not in ("falling", "rising") or not proposed_lines or len(candles) < 2:
            return []
        current = len(candles)-1
        if type(episode_start) is not int or not 0 <= episode_start < current:
            return []
        strict_side = "upper" if family == "falling" else "lower"
        proposed = {identity(line) for line in proposed_lines
                    if evaluate_strict_wedge_wicks(line, candles, strict_side,
                                                   current, current) == []}
        if not proposed:
            return []
        opposite = identity(original_opposite_line)
        frame = candles.copy()
        for col in ("open", "high", "low", "close"):
            frame[col] = frame[col].astype(float)
        closed = frame.iloc[:-1].copy()
        highs, lows = find_pivots(closed.copy())
        upper = build_candidate_lines(highs)
        lower = build_candidate_lines(lows)
        su, sl = build_strict_wedge_support_lines(
            highs, lows, upper, lower, closed, len(closed)-1,
        )
        hu, hl = build_wedge_hull_support_lines(
            highs, lows, upper, lower, closed, len(closed)-1,
        )
        upper, lower = upper+su+hu, lower+sl+hl
        if family == "falling":
            upper = [c for c in upper if identity(c["line"]) in proposed]
            lower = [c for c in lower if identity(c["line"]) == opposite]
        else:
            lower = [c for c in lower if identity(c["line"]) in proposed]
            upper = [c for c in upper if identity(c["line"]) == opposite]
        accepted = []
        for u in upper:
            for l in lower:
                if not strict_support_pair_allowed(u, l):
                    continue
                if not wedge_hull_pair_allowed(u, l, highs, lows, frame, current):
                    continue
                g = evaluate_candidate_pair(u, l, highs=highs, lows=lows,
                                            current_index=current, candles=frame)
                if g is None or g.start_index != episode_start:
                    continue
                metrics = g.pair_metrics
                if (not g.validation.get("valid") or not _is_candidate_local(g, current)
                        or not _is_boundary_structurally_valid(g)
                        or not _is_anchor_sequence_valid(g)
                        or metrics.get("geometry_mode") != "CANONICAL"
                        or metrics.get("anchor_sequence", {}).get("family") != family
                        or not metrics.get("true_converging")
                        or metrics.get("strict_wick_exception_index") is not None
                        or not g.apex or not math.isfinite(g.apex["index"])
                        or not math.isfinite(g.apex["price"])
                        or g.apex["index"] <= current or g.apex["price"] <= 0):
                    continue
                accepted.append(g.to_dict())
        return accepted
    except (AttributeError, KeyError, TypeError, ValueError, IndexError,
            ArithmeticError):
        return []


class ControlAnchorObservation:
    """Stateful non-executing consumer of one existing publicTrade inbox.

    The caller must establish the source-to-seed coverage boundary before
    construction. Neither an inbox attachment nor consecutive candle times
    prove that coverage. With a journal path this object commits observational
    revisions only; otherwise it produces proposals. It never changes the
    frozen signal or trade authority. After a gap, discard and reseed;
    existing history requires exact source-time replay, not blind resume.
    """

    def __init__(self, seed, source, inbox, epoch, *, journal_database_path=None):
        self.seed = seed
        self.source = source
        self.inbox = inbox
        self.generation, self.invalid_frames = epoch
        self.rows = seed["candles"].to_dict("records")
        self.pivots = {p["index"]: dict(p) for p in seed["established_pivots"]}
        self.cutoff = seed["prefix_as_of_ms"]
        self.interval = seed["timeframe_ms"]
        self.family = seed["family"]
        self.line = dict(seed["original_strict_line"])
        self.broken = False
        self.valid = True
        self.journal_database_path = journal_database_path
        self.allow_publish = lambda: True
        self.control_anchor = self.pivots.get(self.line['second_index'])
        self.replay_history = []
        if journal_database_path is not None:
            from .wedge_revision_journal import load_revisions
            if self.control_anchor is None:
                raise ValueError('missing original control anchor')
            self.replay_history = load_revisions(journal_database_path, seed)
        self.revision = 0
        col = "low" if self.family == "falling" else "high"
        values = [Decimal(str(r[col])) for r in self.rows[seed["episode_start"]:]]
        self.extreme = min(values) if self.family == "falling" else max(values)

    def _current(self):
        return self.valid and self.source.print_inbox_current(
            self.inbox, self.generation, self.invalid_frames,
        )

    def _confirm_closed_pivots(self, cutoff):
        import pandas as pd
        from pivots import find_pivots
        from .triangle_boundaries import local_alternation_pivots

        frame = pd.DataFrame(self.rows)
        highs, lows = find_pivots(frame.copy())
        local_highs, local_lows = local_alternation_pivots(frame, len(frame)-1)
        points = highs + local_highs if self.family == "falling" else lows + local_lows
        for p in points:
            i = p["index"]
            if i >= self.seed["first_strict_index"] and i not in self.pivots:
                self.pivots[i] = {"index": i, "price": float(p["price"]),
                                  "known_at_ms": cutoff}

    def _advance(self, p):
        import pandas as pd

        ms, price = p.timestamp_ms, p.price
        if (type(ms) is not int or ms < self.cutoff
                or type(p.received_at_ms) is not int or p.received_at_ms <= 0
                or not price.is_finite() or price <= 0):
            self.valid = False
            return None
        bar_open = ms // self.interval * self.interval
        previous_open = self.rows[-1]["open_time_ms"]
        if bar_open == previous_open + self.interval:
            if len(self.rows) >= 2000:
                self.valid = False
                return None
            self._confirm_closed_pivots(bar_open)
            self.rows.append(dict(open_time_ms=bar_open, open=price,
                                  high=price, low=price, close=price))
        elif bar_open == previous_open and self.cutoff < previous_open + self.interval:
            row = self.rows[-1]
            row["high"] = max(Decimal(str(row["high"])), price)
            row["low"] = min(Decimal(str(row["low"])), price)
            row["close"] = price
        else:
            self.valid = False
            return None
        index = len(self.rows)-1
        projected = (Decimal(str(self.line["anchor_price"]))
                     + Decimal(str(self.line["second_price"] - self.line["anchor_price"]))
                     * Decimal(index-self.line["anchor_index"])
                     / Decimal(self.line["second_index"]-self.line["anchor_index"]))
        already_broken = self.broken
        if (price > projected if self.family == "falling" else price < projected):
            self.broken = True
        old = self.extreme
        new_extreme = price < old if self.family == "falling" else price > old
        self.cutoff = ms
        if not new_extreme:
            return None
        self.extreme = price  # advance even if rebuild is impossible
        if not already_broken:
            return None  # line break alone or pre-breakout extreme is not a trigger
        result = propose_control_boundary(
            family=self.family, episode_start=self.seed["episode_start"],
            first_strict_index=self.seed["first_strict_index"],
            previous_extreme=old, trade_price=price, event_index=index,
            event_time_ms=ms, established_pivots=self.pivots.values(),
            candles=pd.DataFrame(self.rows),
        )
        pairs = validate_revision_pairs(
            family=self.family, episode_start=self.seed["episode_start"],
            original_opposite_line=self.seed.get("original_opposite_line"),
            proposed_lines=result["lines"], candles=pd.DataFrame(self.rows),
        )
        return dict(result, validated_pairs=pairs, candidate_id=self.seed["candidate_id"],
                    source_trade_id=p.trade_id, received_at_ms=p.received_at_ms,
                    previous_extreme=str(old), previous_strict_line=dict(self.line))

    def _publish(self, proposal):
        """Select only among validated alternatives and persist before advancing."""
        from types import SimpleNamespace
        from .ranking import rank_geometry
        from .wedge_revision_journal import append_revision, _line
        import sqlite3

        pairs = proposal["validated_pairs"]
        if not pairs:
            return dict(proposal, revision_outcome="REBUILD_UNAVAILABLE")
        strict = "upper_line" if self.family == "falling" else "lower_line"
        try:
            geometry = max(pairs, key=lambda g: (
                rank_geometry(SimpleNamespace(**g)), g[strict]["second_index"],
            ))
            if _line(self.line) == _line(geometry[strict]):
                return dict(proposal, revision_outcome="UNCHANGED_RAY")
            if not self._current() or not self.allow_publish():
                raise ValueError("source or Robot owner epoch lost")
            if self.revision < len(self.replay_history):
                expected = self.replay_history[self.revision]
                if (proposal["source_trade_id"] != expected["source_trade_id"]
                        or _line(geometry[strict]) != expected["strict_line"]):
                    raise ValueError("unproven revision replay")
            record, created = append_revision(
                self.journal_database_path, self.seed, proposal, geometry,
                previous_control_anchor=self.control_anchor,
                previous_strict_line=self.line,
            )
            if (record is None or record["revision"] != self.revision+1
                    or (self.revision < len(self.replay_history)
                        and record != self.replay_history[self.revision])):
                raise ValueError("revision sequence conflict")
        except (ValueError, KeyError, TypeError, ArithmeticError, OSError, sqlite3.Error):
            self.valid = False
            return dict(proposal, revision_outcome="JOURNAL_BLOCKED")
        self.line = dict(geometry[strict])
        self.control_anchor = dict(proposal["control_anchor"])
        self.revision = record["revision"]
        self.broken = False
        return dict(proposal, revision_outcome="RECORDED" if created else "REPLAYED",
                    revision_record=record)

    def consume(self):
        """Consume fresh batches in order; never publish across a known gap."""
        from queue import Empty

        if not self._current():
            self.valid = False
            return ()
        try:
            gen, bad, prints = self.inbox.get_nowait()
        except Empty:
            return ()
        if (gen, bad) != (self.generation, self.invalid_frames):
            self.valid = False
            return ()
        proposals = []
        for p in prints:
            if not self._current():
                self.valid = False
                break
            if (self.revision < len(self.replay_history)
                    and p.timestamp_ms > self.replay_history[self.revision]["event_time_ms"]):
                self.valid = False
                break
            proposal = self._advance(p)
            if not self.valid:
                break
            if proposal is not None:
                if self.journal_database_path is not None:
                    proposal = self._publish(proposal)
                proposals.append(proposal)
                if not self.valid:
                    break
        if not self._current():
            self.valid = False
        # Durable events before a gap remain real; non-published proposals
        # from an invalidated batch must not escape as usable geometry.
        if not self.valid:
            return tuple(p for p in proposals if "revision_record" in p
                         or p.get("revision_outcome") == "JOURNAL_BLOCKED")
        return tuple(proposals)


def attach_control_anchor_observation(seed, source, *, journal_database_path=None):
    """Join an existing locally observed source without a second subscription.

    No arbitrary seed-to-current OHLC reconstruction. A source without a
    retained cutoff bracket cannot support a causal observation and returns
    None. A matching bracket proves only local observed continuity, never
    full exchange coverage or order authority.
    """
    from queue import Queue

    if seed is None or source.symbol != seed["symbol"]:
        return None
    inbox = Queue(maxsize=32)
    epoch = source.attach_print_inbox_from(inbox, seed["prefix_as_of_ms"])
    if epoch is None:
        return None
    try:
        return ControlAnchorObservation(seed, source, inbox, epoch,
                                        journal_database_path=journal_database_path)
    except Exception:
        source.detach_print_inbox(inbox)
        raise
