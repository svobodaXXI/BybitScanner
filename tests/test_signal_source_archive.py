"""Exact formation identity must resolve to the archived original chart."""

from signal_archive import load_original_signal, record_original_signal


def test_archived_formation_source_identity_is_exact(tmp_path):
    image = b"\x89PNG\r\n\x1a\nexample"
    original_id = "origin:TESTUSDT:5:formation-abc"
    assert record_original_signal(
        original_id, symbol="TESTUSDT", timeframe="5",
        pattern="Rising Wedge", text="Первоначальный клин",
        image_bytes=image, directory=tmp_path,
    )
    original = load_original_signal([original_id], directory=tmp_path)
    assert original is not None
    assert original["symbol"] == "TESTUSDT"
    assert original["image_path"]
    assert load_original_signal(
        ["origin:OTHERUSDT:5:formation-abc"], directory=tmp_path
    ) is None


def test_mirror_origin_carries_source_id_for_exact_navigation(tmp_path):
    image = b"\x89PNG\r\n\x1a\nmirror"
    id_ = "mirror-origin:deadbeef1234567890abcdef"
    assert record_original_signal(
        id_, symbol="TESTUSDT", timeframe="5", pattern="MIRROR",
        text="MIRROR: ретест", image_bytes=image,
        source_formation_ids=["origin:TESTUSDT:5:formation-abc"],
        directory=tmp_path,
    )
    card = load_original_signal([id_], directory=tmp_path)
    assert card is not None
    assert card["source_formation_ids"] == ["origin:TESTUSDT:5:formation-abc"]
