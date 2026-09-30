"""RVL-G4 real-source Ikigai first-impulse regression.

BSVUSDT is the current-production RED defect.
CPUSDT/RPLUSDT are historical owner-reference controls used only to bound the
intraleg corrective-swing rule; they are not asserted as current detections.
"""

import json
import unittest
from pathlib import Path

import pandas as pd

from geometry.ikigai_box import detect_ikigai_box


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "geometry_gold"

BSV = FIXTURES / "BSVUSDT_5m_false_box_20260928.json"
CPU = FIXTURES / "CPUSDT_5m_historical_first_impulse_20260923.json"
RPLUS = FIXTURES / "RPLUSDT_5m_historical_first_impulse_20260923.json"


def _load(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["candles"])
    for column in ("time", "open", "high", "low", "close", "volume", "turnover"):
        frame[column] = pd.to_numeric(frame[column])
    return payload, frame


def _anchor_indices(payload, frame):
    a = int(frame.index[frame["time"] == payload["anchor_a_time_ms"]][0])
    b = int(frame.index[frame["time"] == payload["anchor_b_time_ms"]][0])
    return a, b


def _max_counter_close_vs_prior_progress(payload, frame):
    start, end = _anchor_indices(payload, frame)
    segment = frame.loc[start:end]
    sign = -1 if payload["direction"] == "LONG" else 1
    anchor = (
        float(segment.iloc[0]["high"])
        if sign == -1
        else float(segment.iloc[0]["low"])
    )
    maximum = 0.0

    for offset in range(1, len(segment)):
        previous = segment.iloc[:offset]
        current_close = float(segment.iloc[offset]["close"])
        if sign == -1:
            best_close = float(previous["close"].min())
            progress = anchor - best_close
            counter = current_close - best_close
        else:
            best_close = float(previous["close"].max())
            progress = best_close - anchor
            counter = best_close - current_close
        if progress > 0:
            maximum = max(maximum, counter / progress)

    return maximum


class IkigaiBoxG4RealSourceTests(unittest.TestCase):
    def test_real_reference_windows_bound_counter_close_rule(self):
        bsv_payload, bsv_frame = _load(BSV)
        cpu_payload, cpu_frame = _load(CPU)
        rplus_payload, rplus_frame = _load(RPLUS)

        self.assertGreater(
            _max_counter_close_vs_prior_progress(bsv_payload, bsv_frame),
            0.25,
        )
        self.assertLess(
            _max_counter_close_vs_prior_progress(cpu_payload, cpu_frame),
            0.25,
        )
        self.assertLess(
            _max_counter_close_vs_prior_progress(rplus_payload, rplus_frame),
            0.25,
        )

    def test_bsv_internal_corrective_swing_forbids_owner_rejected_box(self):
        payload, frame = _load(BSV)
        found = detect_ikigai_box(
            frame,
            as_of_index=int(payload["decision_index"]),
        )

        forbidden = False
        if found is not None:
            forbidden = (
                found.direction == payload["direction"]
                and int(frame.iloc[found.anchor_start_index]["time"])
                == payload["anchor_a_time_ms"]
                and int(frame.iloc[found.anchor_end_index]["time"])
                == payload["anchor_b_time_ms"]
            )

        self.assertFalse(
            forbidden,
            "owner-rejected BSV A/B is still admitted despite its material "
            "internal corrective swing",
        )


if __name__ == "__main__":
    unittest.main()
