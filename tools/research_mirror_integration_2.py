"""MIRROR-INTEGRATION-2: replay the OBSERVE_ONLY path over the saved RETEST-4 cases.

Offline, cache-only (no network, no runtime, no PAPER DB). For each of the 67
frozen RETEST-4 boundaries the cached 5m candles are fed one closed candle at a
time through ``mirror_retest_observer`` (1m resolves ambiguous contacts, as in
RETEST-5); observations are written to an idempotent JSONL journal. No account
facts exist offline, so every active-campaign decision is WAIT by design. The
final phase is cross-checked against the published RETEST-5 refined outcome.

    python -I tools/research_mirror_integration_2.py --retest4 <r4 summary.json> \
        --retest5 <r5 summary.json> --klines <dir> --out <dir>
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geometry.naked_retest import Boundary  # noqa: E402
from mirror_retest_observer import ObservationJournal, observe_history  # noqa: E402
from tools.research_mirror_retest_4 import COARSE_MS, FINE_MS, candles  # noqa: E402


def boundary_from_manifest(item: dict) -> Boundary:
    return Boundary(item["boundary_id"], item["anchor_time_ms"], item["anchor_price"],
                    item["slope_per_ms"], item["as_of_ms"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retest4", type=Path, required=True)
    parser.add_argument("--retest5", type=Path, required=True)
    parser.add_argument("--klines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.retest4.read_text(encoding="utf-8"))["manifest"]
    expected = {c["boundary_id"]: c["refined_outcome"]
                for c in json.loads(args.retest5.read_text(encoding="utf-8"))["cases_detail"]}
    journal = ObservationJournal(args.out / "observations.jsonl")
    phases, events, decisions, reasons, mismatches = Counter(), Counter(), Counter(), Counter(), []
    written = 0
    for item in manifest:
        cid = item["boundary_id"].split(":")[0]
        coarse = candles(json.loads((args.klines / f"{cid}_5.json").read_text()), COARSE_MS)
        fine = sorted(candles(json.loads((args.klines / f"{cid}_1_0.json").read_text()), FINE_MS)
                      + candles(json.loads((args.klines / f"{cid}_1_1.json").read_text()), FINE_MS),
                      key=lambda c: c["open_time_ms"])
        state, records = observe_history(boundary_from_manifest(item), coarse, symbol=item["symbol"],
                                         fine_candles=fine)
        written += journal.append(records)
        phases[state["phase"]] += 1
        for record in records:
            events[record.event] += 1
            decisions[f"{record.event}:{record.decision}"] += 1
            reasons.update(record.reasons)
            if record.executable or record.admission_allowed:
                raise SystemExit("invariant broken: executable observation")
        if expected.get(item["boundary_id"]) != state["phase"]:
            mismatches.append({"boundary_id": item["boundary_id"], "observer": state["phase"],
                               "retest5": expected.get(item["boundary_id"])})

    summary = {
        "cases": len(manifest), "observations_written": written,
        "final_phase": dict(phases), "events": dict(events), "event_decisions": dict(decisions),
        "reasons": dict(reasons), "phase_mismatches_vs_retest5": mismatches,
        "executable_observations": 0, "admission_allowed_observations": 0,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
