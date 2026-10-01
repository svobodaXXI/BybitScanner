"""GEO-U1 Slice G0: calibration-population eligibility gate contracts."""

import hashlib
import inspect
import json
import unittest

import geometry.consensus_calibration_population as population
import geometry.consensus_evidence_readiness as readiness
from geometry.consensus_calibration_population import (
    CRYPTO_LINEAR_PERPETUAL,
    EQUITY_LINKED_LINEAR,
    OTHER_LINEAR,
    POLICY_V1,
    UNKNOWN,
    classify_cases,
    instrument_class,
    readiness_by_population,
)
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS
from tests.geometry_gold import ROOT, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
META = json.loads((GOLD / "instrument_metadata_v1.json").read_text(encoding="utf-8"))
V1 = load_manifest(GOLD / "source_time_manifest_v1.json")
V2 = load_manifest(GOLD / "source_time_manifest_v2.json")
FACTS = V2["observed_slice_d_case_facts"]
# Semantic hashes of every pre-existing Gold manifest/fixture at base 6fceb03.
EXISTING_SEMANTIC_SHA256 = "8a14f714cba610892cf2ebe78bccb2d176d2d39d683e2a2cc19f12819d510c74"


def _semantic(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _existing_paths():
    paths = [GOLD / "manifest_v1.json", GOLD / "source_time_manifest_v1.json",
             GOLD / "source_time_manifest_v2.json"]
    for manifest in (load_manifest(), V1, V2):
        paths += [ROOT / c["fixture_ref"] for c in manifest["cases"]]
    return paths


def _classification():
    return classify_cases(META["case_instruments"], META["instruments"])


def _readiness(facts):
    return readiness_by_population(
        facts, _classification(),
        newly_recovered_case_ids={c["case_id"] for c in V2["cases"]},
        provenance_complete_case_ids={f["case_id"] for f in FACTS},
        unrecoverable_targets=[t["target"] for t in V1["unrecoverable_targets"]],
        reproduced_case_ids=set(V2["reproducibility"]))


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class ClassificationTests(unittest.TestCase):
    def test_every_exact_case_has_a_class_from_pinned_metadata(self):        # A
        classification = _classification()
        self.assertEqual(set(classification), {f["case_id"] for f in FACTS})
        self.assertEqual(len(classification), 16)
        for row in classification.values():
            self.assertNotEqual(row["instrument_class"], UNKNOWN)
        self.assertEqual([classification[k] for k in sorted(classification)],
                         META["observed_case_classification"])

    def test_mcd_is_equity_linked_from_factual_metadata(self):                # C
        mcd = META["instruments"]["MCDUSDT"]
        self.assertEqual((mcd["symbolType"], mcd["fullName"], mcd["underlyingTicker"]),
                         ("stock", "McDonalds Corp", "MCD"))
        row = _classification()["MCDUSDT-5m-src1790004300000"]
        self.assertEqual(row["instrument_class"], EQUITY_LINKED_LINEAR)
        self.assertFalse(row["calibration_eligible"])
        only_mcd = [r for r in _classification().values()
                    if r["instrument_class"] != CRYPTO_LINEAR_PERPETUAL]
        self.assertEqual([r["case_id"] for r in only_mcd],
                         ["MCDUSDT-5m-src1790004300000"])
        resolved = {c["fixture_symbol"]: c for c in META["case_instruments"]
                    if c["method"] == "OHLC_EXACT_MATCH"}
        self.assertEqual({k: v["instrument_symbol"] for k, v in resolved.items()},
                         {"PONS": "PONSUSDT", "AEVO": "AEVOUSDT"})

    def test_eligibility_ignores_trend_and_shadow_results(self):             # B
        source = inspect.getsource(population.instrument_class) + inspect.getsource(
            population.classify_cases)
        for forbidden in ("terminal", "trend", "selection", "shadow", "pattern"):
            self.assertNotIn(forbidden, source.lower())
        self.assertEqual(inspect.signature(classify_cases).parameters.keys()
                         & {"facts", "reports"}, set())
        flipped = [dict(f, terminal_width_trend="EXPANSION", selection_status="SELECTED")
                   for f in FACTS]
        self.assertEqual(
            {f["case_id"] for f in flipped
             if _classification()[f["case_id"]]["calibration_eligible"]},
            {f["case_id"] for f in FACTS
             if _classification()[f["case_id"]]["calibration_eligible"]})

    def test_unknown_or_unproven_metadata_fails_closed(self):                 # I
        for metadata in (None, {}, {"contractType": "LinearPerpetual", "quoteCoin": "USDT"},
                         {"contractType": "LinearFutures", "quoteCoin": "USDT", "symbolType": ""},
                         {"contractType": "LinearPerpetual", "quoteCoin": "USDC", "symbolType": ""},
                         {"contractType": "LinearPerpetual", "quoteCoin": "USDT",
                          "symbolType": "brand-new"}):
            with self.subTest(metadata=metadata):
                self.assertEqual(instrument_class(metadata), UNKNOWN)
        rows = classify_cases([{"case_id": "x", "instrument_symbol": "NOPEUSDT",
                                "method": "RECORDED_SYMBOL"}], META["instruments"])
        self.assertFalse(rows["x"]["calibration_eligible"])
        self.assertEqual(POLICY_V1.eligible_instrument_classes, (CRYPTO_LINEAR_PERPETUAL,))
        self.assertEqual(set(POLICY_V1.excluded_instrument_classes),
                         {EQUITY_LINKED_LINEAR, OTHER_LINEAR})


class PopulationReadinessTests(unittest.TestCase):
    def test_all_linear_stays_the_historical_slice_f_result(self):          # E
        result = _readiness(FACTS)["ALL_LINEAR"]
        self.assertTrue(result.calibration_ready)
        self.assertEqual(json.loads(_dumps(result.__dict__)), V2["observed_readiness"])

    def test_target_population_readiness_is_deterministic(self):           # D, F
        result = _readiness(FACTS)["TARGET_POPULATION"]
        self.assertEqual(json.loads(_dumps(result.__dict__)),
                         META["observed_target_population_readiness"])
        self.assertEqual(_dumps(_readiness(FACTS[::-1])["TARGET_POPULATION"].__dict__),
                         _dumps(result.__dict__))
        self.assertFalse(result.calibration_ready)
        self.assertEqual(result.exact_case_count, 15)
        self.assertEqual((result.persistent_compression_count, result.expansion_count),
                         (3, 1))
        self.assertEqual(result.calibration_blockers, ("EXPANSION: have 1, need >= 2",))

    def test_unclassified_case_is_rejected(self):
        with self.assertRaises(ValueError):
            readiness_by_population(
                FACTS + [dict(FACTS[0], case_id="unclassified")], _classification(),
                newly_recovered_case_ids=set(), provenance_complete_case_ids=set(),
                unrecoverable_targets=(), reproduced_case_ids=set())


class InvarianceTests(unittest.TestCase):
    def test_thresholds_constants_and_fixtures_unchanged(self):              # G, H
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS["terminal_window_bars"], 30)
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS["compression_max_ratio"], 0.9)
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS["expansion_min_ratio"], 1.1)
        self.assertEqual(len(DEFAULT_SHADOW_REPORT_PARAMETERS), 17)
        self.assertEqual(
            (readiness.MIN_EXACT_CASES, readiness.MIN_PERSISTENT_COMPRESSION,
             readiness.MIN_EXPANSION, readiness.MIN_NO_TREND,
             readiness.MIN_NO_ADMISSIBLE, readiness.MIN_PRODUCTION_DETECTED),
            (12, 3, 2, 3, 2, 3))
        joined = "".join(_semantic(p) for p in _existing_paths())
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(),
                         EXISTING_SEMANTIC_SHA256)

    def test_no_calibration_logic(self):                                     # J
        source = inspect.getsource(population).lower()
        for forbidden in ("calibrate(", "fit_threshold", "optimi", "grid_search",
                          "default_shadow_report_parameters"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
