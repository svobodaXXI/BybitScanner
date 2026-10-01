"""GEO-U1 Slice H1: one exact 5m crypto PERSISTENT_COMPRESSION Gold case."""

import hashlib
import json
import unittest

import pandas as pd

import geometry.consensus_calibration_population as population
from geometry.consensus_calibration import concentration_summary
from geometry.consensus_calibration_population import (
    CRYPTO_LINEAR_PERPETUAL,
    POLICY_V1,
    classify_cases,
    readiness_by_population,
)
from geometry.consensus_evidence_readiness import case_facts, exact_source_time_case_problems
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS, build_gold_case_report
from tests.geometry_gold import ROOT, _analyze, _load_frame, geometry_identity, load_manifest
from wedge.detector import detect_structure

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
V1, V2, V3, V4 = (load_manifest(GOLD / f"source_time_manifest_v{i}.json") for i in (1, 2, 3, 4))
METAS = [json.loads((GOLD / f"instrument_metadata_v{i}.json").read_text(encoding="utf-8"))
         for i in (1, 2, 3)]
NEW = "NXPCUSDT-5m-src1789996800000"
CANONICAL_SHA256 = "5475ad7d134259ba1e684dababb33cacb4b33bc08ed0444160da2f2d03f7609e"
# Semantic hashes of every pre-existing Gold manifest/fixture/metadata and the
# H0 calibration result at base 625fc8c.
EXISTING_SEMANTIC_SHA256 = "8a26299515748e936cf588d66a16af741e94ab20185de5743c3f9c93963aee23"
DEFAULTS_AT_BASE = {
    "inlier_band_atr": 0.2, "separation_atr": 0.75, "touch_band_atr": 0.2,
    "minimum_swing_width_fraction": 0.30, "minimum_swing_atr": 0.5,
    "minimum_side_touch_clusters": 2, "min_cross_boundary_traversals": 1,
    "min_alternating_touches": 3, "min_touch_balance": 0.25,
    "min_shared_support_coverage": 0.25, "max_support_gap_fraction": 0.5,
    "terminal_window_bars": 30, "terminal_segments": 3,
    "compression_max_ratio": 0.9, "expansion_min_ratio": 1.1,
    "segment_tolerance": 0.05, "single_bar_narrow_ratio": 0.5,
}


def _semantic(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _classification():
    return classify_cases(sum((m["case_instruments"] for m in METAS), []),
                          {k: v for m in METAS for k, v in m["instruments"].items()})


def _target_cases():
    by_id = {c["case_id"]: c for m in (load_manifest(GOLD / "manifest_v1.json"), V1, V2, V3, V4)
             for c in m["cases"]}
    classification = _classification()
    return [by_id[f["case_id"]] for f in V4["observed_slice_d_case_facts"]
            if classification[f["case_id"]]["calibration_eligible"]]


class NewCaseTests(unittest.TestCase):
    case = V4["cases"][0]

    def test_case_is_5m_crypto_from_pinned_metadata(self):                 # A, B
        self.assertEqual([c["case_id"] for c in V4["cases"]], [NEW])
        self.assertEqual(self.case["timeframe"], "5")
        meta = METAS[2]["instruments"]["NXPCUSDT"]
        self.assertEqual((meta["contractType"], meta["quoteCoin"], meta["symbolType"]),
                         ("LinearPerpetual", "USDT", ""))
        row = _classification()[NEW]
        self.assertEqual(row["instrument_class"], CRYPTO_LINEAR_PERPETUAL)
        self.assertTrue(row["calibration_eligible"])
        self.assertEqual(METAS[2]["observed_case_classification"], [row])

    def test_fixture_complete_continuous_and_forming_candle_excluded(self):  # C, D
        payload = json.loads((ROOT / self.case["fixture_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(exact_source_time_case_problems(self.case, payload), ())
        provenance = payload["provenance"]
        self.assertEqual(provenance["interval_ms"], 300000)
        times = [row[0] for row in payload["candles"]]
        self.assertEqual(len(times), 199)
        self.assertEqual(len(set(times)), 199)
        self.assertEqual(times, [times[0] + i * 300000 for i in range(199)])
        self.assertEqual(times[-1], self.case["cutoff_candle_open_ms"])
        source = provenance["scanner_record"]["scanner_source_candle_time_ms"]
        self.assertEqual(provenance["excluded_forming_candle_open_ms"], source)
        self.assertEqual(source, times[-1] + 300000)
        self.assertNotIn(source, times)
        frame = _load_frame(self.case)
        for key, check in provenance["validation"]["anchor_price_checks"].items():
            column = "high" if key.startswith("upper_line") else "low"
            self.assertEqual(float(frame[column].iloc[int(key.split("=")[1])]),
                             check["recorded"])

    def test_shadow_selected_persistent_compression_reproducible(self):     # E, F, G, H
        frame = _load_frame(self.case)
        future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
        reports = [build_gold_case_report(self.case, frame),
                   build_gold_case_report(self.case, frame),
                   build_gold_case_report(self.case, pd.concat([frame, future],
                                                               ignore_index=True))]
        hashes = {hashlib.sha256(_dumps(r).encode()).hexdigest() for r in reports}
        self.assertEqual(hashes, {CANONICAL_SHA256})
        runs = V4["reproducibility"][NEW]["runs"]
        self.assertEqual(len(runs), 3)
        self.assertTrue(any(r["future_rows_appended"] for r in runs))
        self.assertEqual({r["canonical_report_sha256"] for r in runs}, {CANONICAL_SHA256})
        facts = json.loads(_dumps(case_facts(reports[0])))
        self.assertEqual((facts["selection_status"], facts["terminal_width_trend"]),
                         ("SELECTED", "PERSISTENT_COMPRESSION"))
        self.assertEqual(facts, V4["observed_slice_d_case_facts"][-1])


class InvarianceTests(unittest.TestCase):
    def test_existing_gold_and_h0_result_unchanged(self):                   # I, J, K
        names = ["manifest_v1.json", "source_time_manifest_v1.json",
                 "source_time_manifest_v2.json", "source_time_manifest_v3.json"]
        paths = [GOLD / n for n in names] + [GOLD / "instrument_metadata_v1.json",
                                             GOLD / "instrument_metadata_v2.json",
                                             GOLD / "calibration_result_v1.json"]
        for name in names:
            paths += [ROOT / c["fixture_ref"] for c in load_manifest(GOLD / name)["cases"]]
        joined = "".join(_semantic(p) for p in paths)
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(), EXISTING_SEMANTIC_SHA256)
        self.assertEqual(V4["observed_slice_d_case_facts"][:17], V3["observed_slice_d_case_facts"])
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, DEFAULTS_AT_BASE)

    def test_production_result_on_new_case_is_the_pinned_fact(self):        # L
        case = V4["cases"][0]
        frame = _load_frame(case)
        _, _, geometry = _analyze(frame)
        self.assertEqual(geometry_identity(geometry),
                         case["expectation"]["production_geometry_identity"])
        detected = detect_structure(geometry, candles=frame) if geometry else None
        self.assertEqual(bool(detected and detected.get("detected")),
                         case["expectation"]["production_detected"])

    def test_population_policy_unchanged(self):                             # M
        self.assertEqual(POLICY_V1.policy_version, "GEO-U1-POP-1")
        self.assertEqual(POLICY_V1.eligible_instrument_classes, (CRYPTO_LINEAR_PERPETUAL,))
        self.assertEqual(population._SYMBOL_TYPE_CLASS, {
            "": "CRYPTO_LINEAR_PERPETUAL", "innovation": "CRYPTO_LINEAR_PERPETUAL",
            "stock": "EQUITY_LINKED_LINEAR", "ETF": "EQUITY_LINKED_LINEAR",
            "commodity": "OTHER_LINEAR", "forex": "OTHER_LINEAR"})

    def test_no_screenshot_derived_oracle(self):                            # N
        payload = json.loads((ROOT / V4["cases"][0]["fixture_ref"]).read_text(encoding="utf-8"))
        provenance = payload["provenance"]
        self.assertTrue(provenance["owner_screenshot_link"].startswith("UNCONFIRMED"))
        self.assertTrue(provenance["source"].startswith("Bybit v5 public market kline"))
        self.assertTrue(provenance["validation"]["recorded_anchor_prices_match_fixture"])


class ReadinessAndConcentrationTests(unittest.TestCase):
    facts = V4["observed_slice_d_case_facts"]

    def _readiness(self, facts):
        reproduced = set(V2["reproducibility"]) | set(V3["reproducibility"]) | set(
            V4["reproducibility"])
        return readiness_by_population(
            facts, _classification(), newly_recovered_case_ids={NEW},
            provenance_complete_case_ids={f["case_id"] for f in facts},
            unrecoverable_targets=[t["target"] for t in V1["unrecoverable_targets"]],
            reproduced_case_ids=reproduced)

    def test_target_readiness_facts(self):
        result = self._readiness(self.facts)["TARGET_POPULATION"]
        self.assertEqual(json.loads(_dumps(result.__dict__)),
                         V4["observed_readiness_target_population"])
        self.assertEqual((result.exact_case_count, result.persistent_compression_count,
                          result.expansion_count, result.no_persistent_trend_count,
                          result.rejected_selection_count, result.production_detected_count),
                         (17, 4, 2, 9, 2, 4))
        self.assertTrue(result.calibration_ready)
        self.assertEqual(json.loads(_dumps(self._readiness(self.facts)["ALL_LINEAR"].__dict__)),
                         V4["observed_readiness_all_linear"])

    def test_concentration_recomputes_deterministically(self):              # O
        cases = _target_cases()
        facts = {f["case_id"]: f for f in self.facts}
        first = concentration_summary(cases, _classification(), facts)
        again = concentration_summary(list(reversed(cases)), _classification(),
                                      dict(reversed(list(facts.items()))))
        self.assertEqual(json.loads(_dumps(first)), V4["observed_target_concentration_h0_rule"])
        self.assertEqual(_dumps(first), _dumps(again))
        self.assertEqual(len(cases), 17)

    def test_compression_spans_1m_and_5m_and_blocker_cleared(self):        # P
        summary = V4["observed_target_concentration_h0_rule"]
        compression = summary["per_hard_gate_class"]["PERSISTENT_COMPRESSION"]
        self.assertEqual(compression["timeframes"], {"1": 3, "5": 1})
        self.assertEqual(summary["triggers"], [])
        self.assertFalse(summary["data_concentration_blocker"])


if __name__ == "__main__":
    unittest.main()
