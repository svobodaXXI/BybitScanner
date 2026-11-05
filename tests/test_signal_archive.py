import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import signal_archive

PNG_A = b"\x89PNG-A" + b"a" * 64
PNG_B = b"\x89PNG-B" + b"b" * 64


def _photo_response(file_id="FILE-ID-1", message_id=77):
    return {"ok": True, "result": {"message_id": message_id, "photo": [
        {"file_id": "small", "width": 90}, {"file_id": file_id, "width": 1280},
    ]}}


class SignalArchiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _record(self, candidate_id="cand-1", image=PNG_A, **kwargs):
        defaults = dict(symbol="ENAUSDT", timeframe="5", pattern="Falling Wedge",
                        text="Сканер: ENAUSDT", photo_response=_photo_response(),
                        sent_at_ms=1_792_000_000_000, directory=self.dir)
        defaults.update(kwargs)
        return signal_archive.record_original_signal(candidate_id, image_bytes=image, **defaults)

    def test_round_trip_keeps_exact_bytes_text_time_and_largest_file_id(self):
        self.assertTrue(self._record())
        original = signal_archive.load_original_signal(["cand-1"], directory=self.dir)
        self.assertEqual(Path(original["image_path"]).read_bytes(), PNG_A)
        self.assertEqual(original["text"], "Сканер: ENAUSDT")
        self.assertEqual(original["sent_at_ms"], 1_792_000_000_000)
        self.assertEqual(original["photo_file_id"], "FILE-ID-1")
        self.assertEqual(original["photo_message_id"], 77)
        self.assertEqual(original["image_sha256"], hashlib.sha256(PNG_A).hexdigest())

    def test_first_record_wins_and_is_never_replaced(self):
        self.assertTrue(self._record(image=PNG_A, text="first"))
        self.assertTrue(self._record(image=PNG_B, text="second", sent_at_ms=1_793_000_000_000))
        original = signal_archive.load_original_signal(["cand-1"], directory=self.dir)
        self.assertEqual(original["text"], "first")
        self.assertEqual(Path(original["image_path"]).read_bytes(), PNG_A)

    def test_several_signals_of_one_ticker_are_distinguished_by_exact_candidate_id(self):
        self._record("cand-old", image=PNG_A, text="old signal")
        self._record("cand-new", image=PNG_B, text="new signal")
        old = signal_archive.load_original_signal(["cand-old"], directory=self.dir)
        new = signal_archive.load_original_signal(["cand-new"], directory=self.dir)
        self.assertEqual((old["text"], new["text"]), ("old signal", "new signal"))
        self.assertEqual(Path(old["image_path"]).read_bytes(), PNG_A)
        self.assertEqual(Path(new["image_path"]).read_bytes(), PNG_B)

    def test_unknown_candidate_returns_none_even_if_same_ticker_is_archived(self):
        self._record("cand-1")
        self.assertIsNone(signal_archive.load_original_signal(["cand-other"], directory=self.dir))
        self.assertIsNone(signal_archive.load_original_signal([], directory=self.dir))
        self.assertIsNone(signal_archive.load_original_signal(["", None], directory=self.dir))

    def test_box_handoff_is_found_through_the_plan_id_only(self):
        self._record("box-plan-1", pattern="Ikigai Box")
        self.assertIsNone(signal_archive.load_original_signal(["robot-1"], directory=self.dir))
        original = signal_archive.load_original_signal(["robot-1", "box-plan-1"], directory=self.dir)
        self.assertEqual(original["candidate_id"], "box-plan-1")

    def test_tampered_or_missing_image_is_treated_as_not_archived(self):
        self._record()
        image = next(self.dir.glob("*.png"))
        image.write_bytes(b"tampered")
        self.assertIsNone(signal_archive.load_original_signal(["cand-1"], directory=self.dir))
        image.unlink()
        self.assertIsNone(signal_archive.load_original_signal(["cand-1"], directory=self.dir))

    def test_foreign_or_corrupt_metadata_is_rejected(self):
        self._record()
        meta_path = next(self.dir.glob("*.json"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["candidate_id"] = "somebody-else"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.assertIsNone(signal_archive.load_original_signal(["cand-1"], directory=self.dir))
        meta_path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(signal_archive.load_original_signal(["cand-1"], directory=self.dir))

    def test_unsafe_candidate_id_cannot_escape_the_archive_directory(self):
        self.assertTrue(self._record("../../evil"))
        for path in self.dir.rglob("*"):
            self.assertEqual(path.parent, self.dir)
        self.assertEqual(len(list(self.dir.glob("*.json"))), 1)

    def test_invalid_input_stores_nothing_and_never_raises(self):
        self.assertFalse(self._record(""))
        self.assertFalse(self._record("cand-1", image=b""))
        self.assertFalse(self._record("cand-1", image=None))
        self.assertEqual(list(self.dir.glob("*")), [])

    def test_storage_failure_is_swallowed_so_signal_delivery_is_unaffected(self):
        with patch.object(signal_archive.os, "replace", side_effect=OSError("disk full")):
            self.assertFalse(self._record())
        self.assertIsNone(signal_archive.load_original_signal(["cand-1"], directory=self.dir))

    def test_failed_photo_response_stores_no_file_id(self):
        self._record(photo_response={"ok": False})
        original = signal_archive.load_original_signal(["cand-1"], directory=self.dir)
        self.assertIsNone(original["photo_file_id"])
        self.assertIsNone(original["photo_message_id"])

    def test_directory_can_be_overridden_by_environment(self):
        with patch.dict("os.environ", {signal_archive.ARCHIVE_ENV: str(self.dir)}):
            self.assertEqual(signal_archive.archive_dir(), self.dir)
            self.assertTrue(signal_archive.record_original_signal(
                "cand-env", symbol="X", timeframe="1", pattern="p", text="t", image_bytes=PNG_A))
            self.assertIsNotNone(signal_archive.load_original_signal(["cand-env"]))


if __name__ == "__main__":
    unittest.main()
