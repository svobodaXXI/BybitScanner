import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools" / "training" / "install_reference_archive.ps1"
SYMBOL = "AEONUSDT"
CASE_ID = "ikigai_box_15m_20260817_01"
DESTINATION = f"training/reference_patterns/{SYMBOL}/{CASE_ID}"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\noriginal-chart-bytes\x00\xff"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReferenceArchiveInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.downloads = Path(self.temp.name) / "downloads"
        self.process_temp = Path(self.temp.name) / "process-temp"
        (self.root / "training/reference_patterns").mkdir(parents=True)
        self.downloads.mkdir()
        self.process_temp.mkdir()
        self.archive = self.downloads / "reference.zip"

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, files=None):
        if files is None:
            files = [
                {
                    "source": "payload/manual.png",
                    "destination": "manual.png",
                    "role": "original_source_image",
                    "sha256": sha256(IMAGE_BYTES),
                    "original_filename": "uploaded-chart.png",
                    "preserve_exact_bytes": True,
                    "install_policy": "create_or_identical",
                }
            ]
        return {
            "schema_version": "1.0",
            "archive_type": "BYBITSCANNER_TRAINING_REFERENCE",
            "canonical_symbol": SYMBOL,
            "case_id": CASE_ID,
            "reference_type": "ikigai_box_15m",
            "canonical_destination": DESTINATION,
            "files": files,
            "superseded_artifacts": [],
        }

    def write_archive(self, manifest=None, payload=None, extras=None, raw_manifest=None):
        manifest = self.manifest() if manifest is None else manifest
        payload = {"payload/manual.png": IMAGE_BYTES} if payload is None else payload
        extras = {} if extras is None else extras
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr(
                "reference-archive.json",
                raw_manifest if raw_manifest is not None else json.dumps(manifest),
            )
            for name, data in payload.items():
                archive.writestr(name, data)
            for name, data in extras.items():
                archive.writestr(name, data)
        return self.archive

    def run_installer(self, archive=None):
        archive = self.archive if archive is None else archive
        environment = os.environ.copy()
        environment["TEMP"] = str(self.process_temp)
        environment["TMP"] = str(self.process_temp)
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(INSTALLER),
                "-ArchivePath",
                str(archive),
                "-ProjectRoot",
                str(self.root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )

    def case_root(self):
        return self.root / DESTINATION

    def reference_snapshot(self):
        base = self.root / "training/reference_patterns"
        return {
            str(path.relative_to(base)): sha256(path.read_bytes())
            for path in base.rglob("*")
            if path.is_file()
        }

    def assert_temp_clean(self):
        tails = list(self.process_temp.glob("BybitScannerReferenceInstall-*"))
        self.assertEqual([], tails)

    def test_valid_install_preserves_original_bytes_and_zip(self):
        self.write_archive()
        result = self.run_installer()
        installed = self.case_root() / "manual.png"
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("CREATE:", result.stdout)
        self.assertEqual(IMAGE_BYTES, installed.read_bytes())
        self.assertEqual(sha256(IMAGE_BYTES), sha256(installed.read_bytes()))
        self.assertTrue(self.archive.exists())
        self.assert_temp_clean()

    def test_identical_repeat_is_noop(self):
        self.write_archive()
        self.assertEqual(0, self.run_installer().returncode)
        before = self.reference_snapshot()
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("IDENTICAL_NOOP:", result.stdout)
        self.assertEqual(before, self.reference_snapshot())

    def test_add_to_existing_case_without_overwriting_prior_example(self):
        case = self.case_root()
        case.mkdir(parents=True)
        prior = case / "outcome_01.png"
        prior.write_bytes(b"prior-example")
        self.write_archive()
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ADD_TO_EXISTING_CASE:", result.stdout)
        self.assertEqual(b"prior-example", prior.read_bytes())

    def test_independent_case_ids_for_one_symbol_coexist(self):
        self.write_archive()
        self.assertEqual(0, self.run_installer().returncode)
        first = self.case_root() / "manual.png"
        second_case = "ikigai_box_15m_20260817_02"
        manifest = self.manifest()
        manifest["case_id"] = second_case
        manifest["canonical_destination"] = (
            f"training/reference_patterns/{SYMBOL}/{second_case}"
        )
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        second = (
            self.root
            / "training/reference_patterns"
            / SYMBOL
            / second_case
            / "manual.png"
        )
        self.assertEqual(IMAGE_BYTES, first.read_bytes())
        self.assertEqual(IMAGE_BYTES, second.read_bytes())

    def test_authorized_hash_matched_replacement(self):
        old = b"old-authorized-content"
        case = self.case_root()
        case.mkdir(parents=True)
        target = case / "manual.png"
        target.write_bytes(old)
        manifest = self.manifest()
        file_record = manifest["files"][0]
        file_record["install_policy"] = "authorized_replace"
        file_record["replacement_authorization"] = {
            "authorized": True,
            "expected_current_sha256": sha256(old),
            "reason": "Correct assistant-created artifact",
        }
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("AUTHORIZED_REPLACE:", result.stdout)
        self.assertEqual(IMAGE_BYTES, target.read_bytes())

    def test_replacement_hash_mismatch_does_not_overwrite(self):
        old = b"user-changed-content"
        case = self.case_root()
        case.mkdir(parents=True)
        target = case / "manual.png"
        target.write_bytes(old)
        manifest = self.manifest()
        file_record = manifest["files"][0]
        file_record["install_policy"] = "authorized_replace"
        file_record["replacement_authorization"] = {
            "authorized": True,
            "expected_current_sha256": sha256(b"different-old-content"),
            "reason": "Expected assistant-created artifact",
        }
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(4, result.returncode)
        self.assertEqual(old, target.read_bytes())

    def test_missing_or_malformed_manifest_returns_schema_failure(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("payload/manual.png", IMAGE_BYTES)
        missing = self.run_installer()
        self.assertEqual(2, missing.returncode)
        self.assert_temp_clean()
        self.write_archive(raw_manifest="{broken")
        malformed = self.run_installer()
        self.assertEqual(2, malformed.returncode)
        self.assert_temp_clean()

    def test_undeclared_payload_file_fails_without_mutation(self):
        self.write_archive(extras={"payload/duplicate.png": b"garbage"})
        before = self.reference_snapshot()
        result = self.run_installer()
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, self.reference_snapshot())

    def test_file_outside_manifest_payload_layout_fails(self):
        self.write_archive(extras={"install.ps1": b"duplicated installer logic"})
        result = self.run_installer()
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.case_root().exists())

    def test_unsafe_zip_entries_are_rejected(self):
        for unsafe in ("../escape.png", "/rooted.png", "C:/drive.png", "payload/../escape.png"):
            with self.subTest(unsafe=unsafe):
                self.write_archive(extras={unsafe: b"unsafe"})
                result = self.run_installer()
                self.assertEqual(3, result.returncode, result.stderr)
                self.assertFalse(self.case_root().exists())
                self.assert_temp_clean()

    def test_link_like_zip_entry_is_rejected(self):
        manifest = self.manifest()
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("reference-archive.json", json.dumps(manifest))
            link = zipfile.ZipInfo("payload/manual.png")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            archive.writestr(link, b"target")
        result = self.run_installer()
        self.assertEqual(3, result.returncode)
        self.assertFalse(self.case_root().exists())

    def test_destination_outside_root_and_symbol_mismatch_fail(self):
        for destination in (
            "training/reference_patterns/OTHERUSDT/case",
            "training/reference_patterns/AEONUSDT",
            "outside/AEONUSDT/case",
        ):
            with self.subTest(destination=destination):
                manifest = self.manifest()
                manifest["canonical_destination"] = destination
                self.write_archive(manifest)
                result = self.run_installer()
                self.assertEqual(2, result.returncode)
                self.assertFalse(self.case_root().exists())

    def test_existing_different_user_file_is_not_overwritten(self):
        case = self.case_root()
        case.mkdir(parents=True)
        target = case / "manual.png"
        target.write_bytes(b"user-file")
        self.write_archive()
        result = self.run_installer()
        self.assertEqual(4, result.returncode)
        self.assertEqual(b"user-file", target.read_bytes())

    def test_unauthorized_cleanup_fails_without_deletion(self):
        wrong = self.root / "training/reference_patterns/WRONGUSDT/bad/manual.png"
        wrong.parent.mkdir(parents=True)
        wrong.write_bytes(b"assistant-error")
        manifest = self.manifest()
        manifest["superseded_artifacts"] = [
            {
                "path": "training/reference_patterns/WRONGUSDT/bad/manual.png",
                "expected_sha256": sha256(b"assistant-error"),
                "created_by": "assistant_workflow",
                "cleanup_authorized": False,
                "reason": "Wrong symbol",
            }
        ]
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(4, result.returncode)
        self.assertTrue(wrong.exists())
        self.assertFalse(self.case_root().exists())

    def test_cleanup_hash_mismatch_fails_without_deletion(self):
        wrong = self.root / "training/reference_patterns/WRONGUSDT/bad/manual.png"
        wrong.parent.mkdir(parents=True)
        wrong.write_bytes(b"changed-user-content")
        manifest = self.manifest()
        manifest["superseded_artifacts"] = [
            {
                "path": "training/reference_patterns/WRONGUSDT/bad/manual.png",
                "expected_sha256": sha256(b"old-assistant-content"),
                "created_by": "assistant_workflow",
                "cleanup_authorized": True,
                "reason": "Wrong symbol",
            }
        ]
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(4, result.returncode)
        self.assertEqual(b"changed-user-content", wrong.read_bytes())
        self.assertFalse(self.case_root().exists())

    def test_authorized_cleanup_removes_exact_file_and_empty_directory(self):
        wrong_dir = self.root / "training/reference_patterns/WRONGUSDT/bad"
        wrong_dir.mkdir(parents=True)
        wrong = wrong_dir / "manual.png"
        wrong.write_bytes(b"assistant-error")
        manifest = self.manifest()
        manifest["superseded_artifacts"] = [
            {
                "path": "training/reference_patterns/WRONGUSDT/bad/manual.png",
                "expected_sha256": sha256(b"assistant-error"),
                "created_by": "assistant_workflow",
                "cleanup_authorized": True,
                "reason": "Wrong symbol",
            }
        ]
        manifest["cleanup_empty_directories"] = [
            "training/reference_patterns/WRONGUSDT/bad"
        ]
        self.write_archive(manifest)
        result = self.run_installer()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(wrong.exists())
        self.assertFalse(wrong_dir.exists())

    def test_blocking_conflict_preflight_leaves_no_partial_install(self):
        case = self.case_root()
        case.mkdir(parents=True)
        conflict = case / "second.json"
        conflict.write_bytes(b"user-content")
        second = b'{"valid": true}'
        files = self.manifest()["files"] + [
            {
                "source": "payload/second.json",
                "destination": "second.json",
                "role": "annotation",
                "sha256": sha256(second),
                "install_policy": "create_or_identical",
            }
        ]
        self.write_archive(self.manifest(files), payload={
            "payload/manual.png": IMAGE_BYTES,
            "payload/second.json": second,
        })
        before = self.reference_snapshot()
        result = self.run_installer()
        self.assertEqual(4, result.returncode)
        self.assertEqual(before, self.reference_snapshot())
        self.assertFalse((case / "manual.png").exists())

    def test_invalid_archive_and_case_identity_exit_codes(self):
        bad_archive = self.downloads / "not-zip.zip"
        bad_archive.write_bytes(b"not a zip")
        self.assertEqual(1, self.run_installer(bad_archive).returncode)
        manifest = self.manifest()
        manifest["case_id"] = "../bad"
        self.write_archive(manifest)
        self.assertEqual(2, self.run_installer().returncode)

    def test_temp_extraction_removed_on_failure_and_zip_retained(self):
        self.write_archive(extras={"payload/undeclared.bin": b"x"})
        result = self.run_installer()
        self.assertEqual(2, result.returncode)
        self.assert_temp_clean()
        self.assertTrue(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
