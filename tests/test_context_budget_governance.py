import json
import tempfile
import unittest
from pathlib import Path

from tools.project_sync.governance.context_budget import (
    build_budget_report,
    duplicate_candidates,
    extract_markdown_section,
    measure_reference,
)


class ContextBudgetGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "DOCUMENTS").mkdir()
        (self.root / "runtime/context").mkdir(parents=True)
        (self.root / "AGENTS.md").write_text("# Agent\n\nCompact route.\n", encoding="utf-8")
        (self.root / "DOCUMENTS/CR.md").write_text(
            "# Request\n\nDurable state.\n", encoding="utf-8"
        )
        repeated = (
            "This deliberately long recovery paragraph is repeated across two sources "
            "so that it becomes a deterministic classification candidate."
        )
        (self.root / "DOCUMENTS/A.md").write_text(
            f"# ACTIVE\n\n{repeated}\n\n# OTHER\n\nExcluded.\n", encoding="utf-8"
        )
        (self.root / "DOCUMENTS/B.md").write_text(
            f"# RULE\n\n{repeated}\n", encoding="utf-8"
        )
        (self.root / "runtime/context/CR.md").write_text(
            "NON-AUTHORITATIVE\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_file_measurement_uses_raw_bytes_and_deterministic_counts(self):
        result = measure_reference(self.root, "AGENTS.md")
        payload = (self.root / "AGENTS.md").read_bytes()
        self.assertEqual(len(payload), result.bytes)
        self.assertEqual(len(payload.decode("utf-8")), result.characters)
        self.assertEqual(3, result.lines)

    def test_section_measurement_excludes_unrelated_heading(self):
        result = measure_reference(self.root, "DOCUMENTS/A.md#ACTIVE")
        self.assertGreater(result.bytes, 0)
        section = extract_markdown_section(
            (self.root / "DOCUMENTS/A.md").read_bytes().decode("utf-8"), "ACTIVE"
        )
        self.assertNotIn("Excluded", section)
        self.assertEqual(len(section.encode("utf-8")), result.bytes)

    def test_report_measures_lightweight_durable_and_context_paths(self):
        report = build_budget_report(
            self.root,
            "DOCUMENTS/CR.md",
            context_dump="runtime/context/CR.md",
            lightweight_references=["DOCUMENTS/A.md#ACTIVE"],
            durable_references=["DOCUMENTS/B.md#RULE"],
        )
        self.assertEqual(
            report.agents.bytes + report.lightweight_sources[0].bytes,
            report.lightweight_bytes,
        )
        self.assertEqual(
            report.agents.bytes
            + report.change_request.bytes
            + report.durable_sources[0].bytes,
            report.durable_bytes,
        )
        self.assertEqual(19, report.context_dump.bytes)

    def test_duplicate_candidates_are_cross_source_and_normalized(self):
        candidates = duplicate_candidates(
            self.root,
            ["DOCUMENTS/A.md#ACTIVE", "DOCUMENTS/B.md#RULE"],
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual(
            ("DOCUMENTS/A.md#ACTIVE", "DOCUMENTS/B.md#RULE"),
            candidates[0].sources,
        )

    def test_duplicate_candidates_do_not_report_single_source_repetition(self):
        candidates = duplicate_candidates(self.root, ["DOCUMENTS/A.md#ACTIVE"])
        self.assertEqual((), candidates)

    def test_utf16_bom_source_is_measured_without_encoding_migration(self):
        text = "# TREE\r\n\r\nCanonical path.\r\n"
        (self.root / "DOCUMENTS/TREE.md").write_bytes(
            b"\xff\xfe" + text.encode("utf-16-le")
        )
        result = measure_reference(self.root, "DOCUMENTS/TREE.md#TREE")
        self.assertEqual(len(text.encode("utf-8")), result.bytes)

    def test_missing_source_and_heading_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "cannot be resolved"):
            measure_reference(self.root, "missing.md")
        with self.assertRaisesRegex(ValueError, "cannot be resolved"):
            measure_reference(self.root, "DOCUMENTS/A.md#MISSING")

    def test_report_is_json_serializable_without_writing_artifacts(self):
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        report = build_budget_report(self.root, "DOCUMENTS/CR.md")
        json.dumps(report, default=lambda value: value.__dict__)
        after = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
