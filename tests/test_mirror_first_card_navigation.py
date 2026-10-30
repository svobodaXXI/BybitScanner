"""MIRROR «К сигналу»: an unpatterned level opens its first campaign card."""

from unittest.mock import patch

from mirror_scanner import mirror_first_card_archive_id
from signal_archive import load_original_signal, record_original_signal
import telegram_monitoring


def test_first_card_is_immutable_and_level_scoped(tmp_path):
    first_id = mirror_first_card_archive_id("TESTUSDT", "5", "level-A")
    assert first_id != mirror_first_card_archive_id("TESTUSDT", "5", "level-B")
    assert first_id != mirror_first_card_archive_id("OTHERUSDT", "5", "level-A")
    assert record_original_signal(
        first_id, symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="🪞 MIRROR · пробой", image_bytes=b"first", directory=tmp_path,
    )
    # An eventual retest or delivery retry must not overwrite the first card.
    assert record_original_signal(
        first_id, symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="🪞 MIRROR · первый ретест", image_bytes=b"later", directory=tmp_path,
    )
    first = load_original_signal([first_id], directory=tmp_path)
    assert first["text"] == "🪞 MIRROR · пробой"
    assert open(first["image_path"], "rb").read() == b"first"
    assert record_original_signal(
        "mirror-origin:retest", symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="Ретест", image_bytes=b"later", source_campaign_first_id=first_id,
        directory=tmp_path,
    )
    assert load_original_signal(["mirror-origin:retest"], directory=tmp_path)[
        "source_campaign_first_id"] == first_id


def _callback():
    return {"data": "mirror:source:" + "a" * 24, "id": "cb",
            "from": {"id": 123}, "message": {"chat": {"id": 123}}}


def test_naked_mirror_button_reposts_first_card_not_current_retest():
    first_id = mirror_first_card_archive_id("TESTUSDT", "5", "level-A")
    mirror = {"source_campaign_first_id": first_id, "source_formation_ids": []}
    first = {"text": "Пробой", "symbol": "TESTUSDT", "image_path": "first.png"}
    def lookup(ids):
        if ids == ["mirror-origin:" + "a" * 24]:
            return mirror
        if ids == [first_id]:
            return first
        return None
    with patch.object(telegram_monitoring, "_is_owner", return_value=True), \
         patch.object(telegram_monitoring, "_owner_id", return_value="123"), \
         patch.object(telegram_monitoring, "_answer_callback"), \
         patch.object(telegram_monitoring.signal_archive, "load_original_signal",
                      side_effect=lookup), \
         patch.object(telegram_monitoring, "_repost_original_signal",
                      return_value=True) as repost, \
         patch.object(telegram_monitoring, "_send_text") as send_text:
        assert telegram_monitoring._process_mirror_source_callback(_callback())
    repost.assert_called_once_with(123, first)
    send_text.assert_not_called()


def test_pattern_card_takes_precedence_over_campaign_first():
    first_id = mirror_first_card_archive_id("TESTUSDT", "5", "level-A")
    pattern_id = "origin:TESTUSDT:5:formation-123"
    mirror = {"source_campaign_first_id": first_id,
              "source_formation_ids": [pattern_id]}
    pattern = {"text": "Клин", "symbol": "TESTUSDT", "image_path": "pattern.png"}
    def lookup(ids):
        if ids == ["mirror-origin:" + "a" * 24]:
            return mirror
        if ids == [pattern_id]:
            return pattern
        raise AssertionError(f"unexpected fallback: {ids}")
    with patch.object(telegram_monitoring, "_is_owner", return_value=True), \
         patch.object(telegram_monitoring, "_owner_id", return_value="123"), \
         patch.object(telegram_monitoring, "_answer_callback"), \
         patch.object(telegram_monitoring.signal_archive, "load_original_signal",
                      side_effect=lookup), \
         patch.object(telegram_monitoring, "_repost_original_signal",
                      return_value=True) as repost:
        assert telegram_monitoring._process_mirror_source_callback(_callback())
    repost.assert_called_once_with(123, pattern)


def test_missing_first_card_does_not_fabricate_source():
    first_id = mirror_first_card_archive_id("TESTUSDT", "5", "level-A")
    mirror = {"source_campaign_first_id": first_id, "source_formation_ids": []}
    def lookup(ids):
        return mirror if ids == ["mirror-origin:" + "a" * 24] else None
    with patch.object(telegram_monitoring, "_is_owner", return_value=True), \
         patch.object(telegram_monitoring, "_owner_id", return_value="123"), \
         patch.object(telegram_monitoring, "_answer_callback"), \
         patch.object(telegram_monitoring.signal_archive, "load_original_signal",
                      side_effect=lookup), \
         patch.object(telegram_monitoring, "_repost_original_signal",
                      return_value=True) as repost, \
         patch.object(telegram_monitoring, "_send_text") as send_text:
        assert telegram_monitoring._process_mirror_source_callback(_callback())
    repost.assert_called_once_with(123, mirror)
    assert "не сохранена" in send_text.call_args.args[1]
