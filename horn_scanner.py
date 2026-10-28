"""Scanner -> Telegram OBSERVATION bridge for the Broadening Formation («Рупор»).

HORN-4 (DOCUMENTS/SCANNER_BROADENING_FORMATION_HORN_1.md, issue #504):
- detection reuses geometry.broadening.detect_broadening on the already fetched
  snapshot without its newest, possibly open candle;
- 4 confirmed alternating pivots = PRELIMINARY (shown, explicitly provisional),
  5+ = MATURE; no LONG/SHORT;
- observation only: no Robot candidate, no admission, no order, no Autopilot;
  HORN-5 (#509): the Telegram card is the canonical short text, then the chart
  with the shared keyboard (TradingView; owner also MetaScalp and review), and
  never a Robot button;
- Horn never suppresses or replaces Wedge/Triangle/Box/L-shape; a Wedge result
  on the same snapshot is stored next to the Horn for owner comparison;
- evidence is appended per event and fsynced immediately (detection, OHLC,
  delivery), never held only in memory until the end of the pass.
"""

import json
import os
import re
import time

import config
from geometry.broadening import detect_broadening
from geometry.broadening_chart import broadening_signal_text, render_broadening_chart
from notification import (
    build_tradingview_keyboard,
    get_telegram_chat_ids,
    get_telegram_owner_chat_id,
    send_message,
    send_photo,
)
from signal_memory import load_memory, save_memory

_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]+$")
DEFAULT_EVIDENCE_DIR = os.path.join("runtime", "terminal", "horn_observations")  # gitignored runtime data
EVENTS_FILE = "events.jsonl"
PROGRESS_FILE = "progress.json"


def horn_observation_enabled():
    """On by default; BYBITSCANNER_HORN_OBSERVATION=0 switches it off."""
    return os.environ.get("BYBITSCANNER_HORN_OBSERVATION", "1") != "0"


def evidence_root():
    return os.environ.get("BYBITSCANNER_HORN_EVIDENCE_DIR") or DEFAULT_EVIDENCE_DIR


def append_event(record, root=None):
    """Append one JSON line and fsync it, so it survives a stopped process."""
    root = root or evidence_root()
    os.makedirs(root, exist_ok=True)
    record = {"recorded_at_ms": int(time.time() * 1000), **record}
    with open(os.path.join(root, EVENTS_FILE), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_progress(progress, root=None):
    """Atomically replace progress.json with the current Scanner pass counters."""
    root = root or evidence_root()
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, PROGRESS_FILE)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"updated_at_ms": int(time.time() * 1000), **progress}, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _line(line, closed):
    """Boundary in window-index form plus the absolute time of its two anchors."""
    return {
        "slope": line["slope"],
        "intercept": line["intercept"],
        "anchor_index": line["anchor_index"],
        "anchor_time_ms": int(closed.iloc[line["anchor_index"]]["time"]),
        "anchor_price": line["anchor_price"],
        "second_index": line["second_index"],
        "second_time_ms": int(closed.iloc[line["second_index"]]["time"]),
        "second_price": line["second_price"],
    }


def _wedge_summary(wedge_result, candles):
    """The Wedge/Triangle geometry the Scanner already computed on this snapshot."""
    if not isinstance(wedge_result, dict):
        return None
    pattern = wedge_result.get("pattern")
    if pattern in (None, "", "No wedge", "Unknown"):
        return None
    geometry = wedge_result.get("geometry") or {}
    summary = {"pattern": pattern, "detected": wedge_result.get("detected")}
    try:
        start, end = int(geometry["start_index"]), int(geometry["end_index"])
        summary.update(
            start_time_ms=int(candles.iloc[start]["time"]),
            end_time_ms=int(candles.iloc[end]["time"]),
            upper_line={k: geometry["upper_line"].get(k) for k in ("slope", "intercept", "anchor_index", "second_index")},
            lower_line={k: geometry["lower_line"].get(k) for k in ("slope", "intercept", "anchor_index", "second_index")},
            line_index_base_time_ms=int(candles.iloc[0]["time"]),
        )
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        pass
    return summary


def observe_broadening(symbol, candles, *, timeframe, wedge_result=None, chart_dir="charts", root=None):
    """Detect a forming broadening on the closed prefix, persist evidence, render.

    Returns None when there is no current formation. The detection record and
    the exact OHLC the detector read are written before the chart, so a
    renderer failure never loses the observation.
    """
    if candles is None or len(candles) < 2:
        return None
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not _SAFE_SYMBOL.fullmatch(symbol) or not timeframe.isdecimal():
        raise ValueError("invalid Horn symbol or timeframe")
    closed = candles.iloc[:-1].reset_index(drop=True)
    formation = detect_broadening(closed)
    if formation is None:
        return None

    root = root or evidence_root()
    decision_ms = int(closed.iloc[formation.as_of_index]["time"])
    anchors = [
        {"time_ms": int(closed.iloc[index]["time"]), "side": side, "price": price}
        for index, side, price in formation.anchors
    ]
    start_ms = anchors[0]["time_ms"]
    identity = f"horn:{symbol}:{timeframe}:{start_ms}:{anchors[1]['time_ms']}"
    ohlc_path = os.path.join(root, "ohlc", f"{symbol}_{timeframe}_{decision_ms}.csv")
    os.makedirs(os.path.dirname(ohlc_path), exist_ok=True)
    closed.to_csv(ohlc_path, index=False)
    chart = os.path.join(chart_dir, "horn", f"{symbol}_{timeframe}_{start_ms}_{decision_ms}_{formation.stage}.png")
    observation = {
        "identity": identity,
        "symbol": symbol,
        "timeframe": timeframe,
        "stage": formation.stage,
        "decision_time_ms": decision_ms,
        "start_time_ms": start_ms,
        "anchors": anchors,
        "upper_line": _line(formation.upper_line, closed),
        "lower_line": _line(formation.lower_line, closed),
        "projection_at_decision": dict(zip(("upper", "lower"), formation.project(formation.as_of_index))),
        "diagnostics": formation.diagnostics,
        "wedge_on_same_snapshot": _wedge_summary(wedge_result, candles),
        "ohlc_path": ohlc_path,
        "ohlc_window_first_ms": int(closed.iloc[0]["time"]),
        "chart_path": chart,
    }
    append_event({"event": "horn_detected", **observation}, root)
    print(
        f"{symbol:<15} {timeframe}m HORN {formation.stage} anchors={len(anchors)} "
        f"start_ms={start_ms} decision_ms={decision_ms}"
        + (f" wedge={observation['wedge_on_same_snapshot']['pattern']}" if observation["wedge_on_same_snapshot"] else ""),
        flush=True,
    )
    os.makedirs(os.path.dirname(chart), exist_ok=True)
    render_broadening_chart(closed, formation, chart, symbol=symbol, timeframe=timeframe)
    observation["formation"] = formation
    return observation


def _deliver(event, send, key, stage, chat_id, test_mode, root):
    """One Telegram call; its outcome is appended to the evidence log."""
    result = {"event": event, "identity": key, "stage": stage,
              "chat_id": str(chat_id), "test_mode": bool(test_mode)}
    try:
        response = send()
        ok = isinstance(response, dict) and bool(response.get("ok"))
        result.update(ok=ok, message_id=((response or {}).get("result") or {}).get("message_id")
                      if isinstance(response, dict) else None)
    except Exception as error:
        ok = False
        result.update(ok=False, error=str(error)[:200])
    append_event(result, root)
    return ok


def send_broadening_observation(symbol, observation, *, timeframe, test_mode=False, root=None):
    """Send the card once per formation identity and stage.

    HORN-5 canonical card (as Ikigai Box): a short text, then the chart with
    the shared keyboard. The owner gets the shared MetaScalp and review
    buttons; other recipients only TradingView. There is never a Robot button.

    The first sighting (PRELIMINARY or MATURE) is delivered; a later upgrade to
    MATURE is delivered once more. Per-recipient text and chart delivery are
    remembered separately in the namespaced signal-memory key, so a failed
    recipient stays retryable without a repeated text and no card is sent
    twice. Every result is appended to the evidence log.
    """
    if not getattr(config, "TELEGRAM_ENABLED", False) or not observation:
        return False
    recipients = get_telegram_chat_ids()
    if not recipients:
        return False
    key, stage = observation["identity"], observation["stage"]
    memory = load_memory()
    seen = memory.get(key, {}) if not test_mode else {}
    delivered = {s: set(ids) for s, ids in (seen.get("stages_delivered") or {}).items()}
    texted = {s: set(ids) for s, ids in (seen.get("stages_text_delivered") or {}).items()}

    message = broadening_signal_text(symbol, timeframe, observation["formation"])
    if test_mode:
        message += "\n🧪 TEST MODE"
    owner_chat_id = get_telegram_owner_chat_id()

    def remember():
        if test_mode:
            return
        memory[key] = {
            "pattern": "Broadening",
            "stages_delivered": {s: sorted(ids) for s, ids in delivered.items()},
            "stages_text_delivered": {s: sorted(ids) for s, ids in texted.items()},
        }
        save_memory(memory)

    all_ok, sent_new = True, False
    for chat_id in recipients:
        if chat_id in delivered.get(stage, set()):
            continue
        if chat_id not in texted.get(stage, set()):
            if not _deliver("horn_text_delivery",
                            lambda: send_message(config.TELEGRAM_TOKEN, chat_id, message),
                            key, stage, chat_id, test_mode, root):
                all_ok = False
                continue
            texted[stage] = texted.get(stage, set()) | {chat_id}
            remember()
        is_owner = bool(owner_chat_id) and chat_id == owner_chat_id
        markup = build_tradingview_keyboard(symbol, timeframe, include_review_actions=is_owner)
        if not _deliver("horn_delivery",
                        lambda: send_photo(config.TELEGRAM_TOKEN, chat_id, observation["chart_path"],
                                           caption="", reply_markup=markup),
                        key, stage, chat_id, test_mode, root):
            all_ok = False
            continue
        sent_new = True
        delivered[stage] = delivered.get(stage, set()) | {chat_id}
        remember()
    return all_ok and sent_new
