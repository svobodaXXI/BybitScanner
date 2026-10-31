"""MIRROR owner 'К сигналу': exact source lineage without same-ticker fallback."""

from pathlib import Path
from unittest.mock import patch

import mirror_scanner
import signal_archive
import telegram_monitoring

PNG_A = b"frozen-first-png"
PNG_B = b"later-other-campaign-png"


def test_first_card_archive_id_is_exact_level_scoped(tmp_path):
    first_id = mirror_scanner.mirror_first_card_archive_id("TESTUSDT", "5", "level-A")
    assert first_id != mirror_scanner.mirror_first_card_archive_id("TESTUSDT", "5", "level-B")
    assert first_id != mirror_scanner.mirror_first_card_archive_id("TESTUSDT", "1", "level-A")
    assert signal_archive.record_original_signal(
        first_id, symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="first card", image_bytes=PNG_A, directory=tmp_path,
    )
    assert signal_archive.record_original_signal(
        first_id, symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="later retest", image_bytes=PNG_B, directory=tmp_path,
    )
    original = signal_archive.load_original_signal([first_id], directory=tmp_path)
    assert original["text"] == "first card"
    assert Path(original["image_path"]).read_bytes() == PNG_A
    assert signal_archive.record_original_signal(
        "mirror-origin:event", symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="event", image_bytes=PNG_B, source_campaign_first_id=first_id,
        directory=tmp_path,
    )
    assert signal_archive.load_original_signal(
        ["mirror-origin:event"], directory=tmp_path
    )["source_campaign_first_id"] == first_id


def _callback():
    return {"data": "mirror:source:" + "a" * 24, "id": "cb",
            "from": {"id": 123}, "message": {"chat": {"id": 123}}}


def _run_callback(lookup):
    with patch.object(telegram_monitoring, "_is_owner", return_value=True), \
         patch.object(telegram_monitoring, "_owner_id", return_value="123"), \
         patch.object(telegram_monitoring, "_answer_callback"), \
         patch.object(telegram_monitoring.signal_archive, "load_original_signal",
                      side_effect=lookup), \
         patch.object(telegram_monitoring, "_repost_original_signal",
                      return_value=True) as repost, \
         patch.object(telegram_monitoring, "_send_text") as send_text:
        assert telegram_monitoring._process_mirror_source_callback(_callback())
        return repost.call_args.args[1], send_text.call_args_list


def test_bare_level_opens_first_campaign_card_not_retest_or_same_ticker():
    first_id = mirror_scanner.mirror_first_card_archive_id("TESTUSDT", "5", "A")
    mirror = {"source_campaign_first_id": first_id, "source_formation_ids": []}
    original = {"candidate_id": first_id, "text": "first", "image_path": "first.png"}
    unrelated = {"candidate_id": "elsewhere", "text": "not first"}

    def lookup(ids):
        if ids == ["mirror-origin:" + "a" * 24]:
            return mirror
        if ids == [first_id]:
            return original
        return unrelated

    reposted, texts = _run_callback(lookup)
    assert reposted is original
    assert not texts


def test_parent_pattern_archive_has_priority_over_first_mirror_card():
    first_id = mirror_scanner.mirror_first_card_archive_id("TESTUSDT", "5", "A")
    parent_id = "origin:TESTUSDT:5:formation"
    mirror = {"source_campaign_first_id": first_id, "source_formation_ids": [parent_id]}
    pattern = {"candidate_id": parent_id, "text": "actual source pattern"}

    def lookup(ids):
        if ids == ["mirror-origin:" + "a" * 24]:
            return mirror
        if ids == [parent_id]:
            return pattern
        raise AssertionError("first MIRROR card should not replace a proven pattern source")

    reposted, texts = _run_callback(lookup)
    assert reposted is pattern
    assert not texts


def test_legacy_missing_first_uses_original_event_with_explicit_warning():
    mirror = {"source_formation_ids": [], "text": "old frozen event"}

    def lookup(ids):
        return mirror if ids == ["mirror-origin:" + "a" * 24] else None

    reposted, texts = _run_callback(lookup)
    assert reposted is mirror
    assert len(texts) == 1
    assert "не сохранена" in texts[0].args[1]
