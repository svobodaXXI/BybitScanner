"""CLI boundary for a single Bybit public-trade Wedge-only SIMULATION run."""
import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.simulator_v2.trade_range import (
    TradeDayProof, _ordered_proofs, import_local_trade_range,
)
from research.simulator_v2.wedge_cli import (
    PROFILE_SCHEMA, MANIFEST_SCHEMA, _read_json,
    parse_utc_minute, parse_manifest, run_from_time_machine_config,
)
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner
from tests.test_simulator_v2_trade_range import (
    START_DAY, START_MS, DAY_MS, SYMBOL, fixture_file,
)

M = 60_000
BOUNDARY = START_MS + DAY_MS


def provenance(proofs):
    source, first, end = _ordered_proofs(
        proofs, symbol=SYMBOL, latest_closed_boundary_ms=BOUNDARY,
    )
    return {
        "schema": MANIFEST_SCHEMA, "namespace": "SIMULATION",
        "raw_trade_archives_embedded": False,
        "symbol": SYMBOL,
        "start_day": proofs[0].utc_day.isoformat(),
        "days": len(proofs), "start_ms": first, "end_ms": end,
        "source_id": source,
        "day_provenance": [p.to_payload(symbol=SYMBOL) for p in proofs],
    }


def selection():
    return {
        "schema": PROFILE_SCHEMA, "namespace": "SIMULATION",
        "simulation_run_id": "wedge_json",
        "symbol": SYMBOL, "selected_strategies": [
            "WEDGE_FALLING", "WEDGE_RISING",
        ],
        "start_utc": "2026-10-01T02:00",
        "end_utc_inclusive": "2026-10-01T04:14",
        "initial_balance": "1000",
        "scanner": {"window_bars": 50, "mode": "hunter", "min_score": 50},
        "risk": {
            "tick_size": "0.01",
            "contracts_per_working_volume": "1",
            "quantity_step": "0.01",
            "minimum_quantity": "0.01",
            "max_notional_usdt": "200",
            "max_risk_usdt": "5",
            "entry_fee_rate": "0.0006",
            "exit_fee_rate": "0.0006",
            "terms_source": "explicit-local-research-test-fixture",
        },
    }


def fake_proofs():
    return (TradeDayProof(START_DAY, "a"*64, "b"*64),)


class TimeMachineWedgeConfigTests(unittest.TestCase):
    def test_strict_utc_minutes_inclusive_and_independent_of_pc_timezone(self):
        self.assertEqual(parse_utc_minute("2026-10-01T02:00"), START_MS+120*M)
        self.assertEqual(parse_utc_minute("2026-10-01T04:14"), START_MS+254*M)
        for invalid in (
            "", "2026-10-01", "2026-10-01T4:14",
            "2026-02-30T02:00", "2026-10-01T24:00",
            "2026-10-01T04:14:00", "2026-10-01T04:14Z",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_utc_minute(invalid)

    def test_immutable_manifest_provenance_and_configured_one_symbol(self):
        manifest = provenance(fake_proofs())
        parsed_symbol, proofs = parse_manifest(
            manifest, latest_closed_boundary_ms=BOUNDARY,
        )
        self.assertEqual(parsed_symbol, SYMBOL)
        self.assertEqual(proofs, fake_proofs())
        selection_input = selection()
        with patch(
            "research.simulator_v2.wedge_cli.run_cached_wedge_trade_range",
            return_value="SENTINEL_RESEARCH",
        ) as runner:
            result = run_from_time_machine_config(
                config=selection_input, manifest=manifest,
                cache_dir=Path("sim-test-cache"),
                latest_closed_boundary_ms=BOUNDARY,
            )
        self.assertEqual(result, "SENTINEL_RESEARCH")
        args = runner.call_args.kwargs
        self.assertEqual(args["start_ms"], START_MS+120*M)
        self.assertEqual(args["end_inclusive_ms"], START_MS+254*M)
        self.assertEqual(args["robot_config"].selected_patterns,
                         frozenset({"Falling Wedge", "Rising Wedge"}))
        self.assertEqual(args["risk_settings"].contracts_per_working_volume, D("1"))
        self.assertEqual(args["proofs"], fake_proofs())
        self.assertEqual(args["initial_balance"], D("1000"))

    def test_unsupported_multistrategy_modes_dont_silently_run_only_wedges(self):
        manifest = provenance(fake_proofs())
        wrong = selection()
        for strategies in (
            [], ["IKIGAI_BOX"], ["MIRROR_LEVELS"],
            ["WEDGE_FALLING", "IKIGAI_BOX"],
            ["WEDGE_FALLING", "WEDGE_FALLING"],
            ["ALL"], ["H1_TREND", "WEDGE_RISING"],
        ):
            with self.subTest(strategies=strategies), self.assertRaisesRegex(
                ValueError, "only actually implemented",
            ):
                run_from_time_machine_config(
                    config={**wrong, "selected_strategies": strategies},
                    manifest=manifest,cache_dir=Path("sim-test-cache"),
                    latest_closed_boundary_ms=BOUNDARY,
                )
        with self.assertRaisesRegex(ValueError, "selected symbol differs"):
            run_from_time_machine_config(
                config={**wrong, "symbol":"ETHUSDT"},
                manifest=manifest, cache_dir=Path("sim-test-cache"),
                latest_closed_boundary_ms=BOUNDARY,
            )

    def test_manifest_sha_url_source_identity_and_risk_terms_are_fail_closed(self):
        manifest = provenance(fake_proofs())
        for key,value in (
            ("source_id", "FORGED_DATASET"),
            ("days", 2),
            ("end_ms", BOUNDARY+M),
            ("raw_trade_archives_embedded", True),
        ):
            with self.subTest(key=key),self.assertRaises(ValueError):
                parse_manifest(
                    {**manifest,key:value},latest_closed_boundary_ms=BOUNDARY,
                )
        broken = {
            **manifest,
            "day_provenance": [
                {**manifest["day_provenance"][0],
                 "source_url":"https://example.org/not-real"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "provenance"):
            parse_manifest(broken,latest_closed_boundary_ms=BOUNDARY)
        wrong=selection()
        for field,value in (
            ("terms_source", ""),("tick_size", "NaN"),
            ("quantity_step", "0"),("contracts_per_working_volume", "0"),
        ):
            with self.subTest(field=field),self.assertRaises(ValueError):
                run_from_time_machine_config(
                    config={
                        **wrong, "risk":{**wrong["risk"],field:value}
                    },
                    manifest=manifest,cache_dir=Path("sim-test-cache"),
                    latest_closed_boundary_ms=BOUNDARY,
                )
        with TemporaryDirectory() as tmp:
            file = Path(tmp)/"manifest.json"
            file.write_text(json.dumps(manifest),encoding="utf-8")
            self.assertEqual(_read_json(file,max_bytes=10000),manifest)
            with self.assertRaisesRegex(ValueError,"size bound"):
                _read_json(file,max_bytes=10)

    def test_actual_cached_bybit_format_can_run_exact_user_minute_window_offline(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archives = root/"archives"
            archives.mkdir()
            fixture_file(archives, START_DAY)
            cache = root/"cache"
            proofs = import_local_trade_range(
                archive_dir=archives, cache_dir=cache,symbol=SYMBOL,
                start_day=START_DAY,days=1, latest_closed_boundary_ms=BOUNDARY,
            )
            # The path needs NO raw files/network once public M1 was verified.
            archives.joinpath(f"{SYMBOL}{START_DAY.isoformat()}.csv.gz").unlink()
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                result = run_from_time_machine_config(
                    config=selection(), manifest=provenance(proofs),
                    cache_dir=cache,latest_closed_boundary_ms=BOUNDARY,
                )
            self.assertEqual(result.report.minutes,255)
            self.assertEqual(result.report.virtual_fills,0)
            self.assertEqual(result.report.total_net_pnl,D("0"))
            self.assertEqual(result.requested_start_ms,START_MS+120*M)
            self.assertEqual(result.requested_end_inclusive_ms,START_MS+254*M)
            self.assertEqual(len(result.archive_proofs),1)
            self.assertEqual(result.to_payload()["namespace"],"SIMULATION")


if __name__ == "__main__":
    unittest.main()
