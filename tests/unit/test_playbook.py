"""The playbook: one entry per candle pattern, with its name, lean and shape (spec appendix 3, section 4)."""

from jev_trader.dataset.candle_patterns import DETECTORS, TALIB_VERSION, playbook


def _entries():
    return {(e.detector, e.lean): e for e in playbook()}


def test_there_are_61_detectors_and_the_version_is_pinned():
    assert len(DETECTORS) == 61
    assert TALIB_VERSION == "0.8.3"


def test_every_detector_has_at_least_one_entry():
    assert {e.detector for e in playbook()} == set(DETECTORS)


def test_a_detector_with_a_rising_and_a_falling_version_gives_two_entries():
    entries = _entries()
    assert entries["CDLENGULFING", "bullish"].name == "bullish engulfing"
    assert entries["CDLENGULFING", "bearish"].name == "bearish engulfing"
    assert entries["CDLHARAMI", "bullish"].name == "bullish harami"
    assert entries["CDLBELTHOLD", "bearish"].name == "bearish belt-hold"


def test_a_one_sided_detector_gives_one_entry_with_no_lean_in_its_name():
    entries = _entries()
    assert entries["CDLHAMMER", "bullish"].name == "hammer"
    assert ("CDLHAMMER", "bearish") not in entries
    assert entries["CDLSHOOTINGSTAR", "bearish"].name == "shooting star"
    assert entries["CDL2CROWS", "bearish"].name == "two crows"


def test_the_seven_exceptions_to_the_sign_rule():
    entries = _entries()
    for detector, name in [
        ("CDLDOJI", "doji"),
        ("CDLLONGLEGGEDDOJI", "long legged doji"),
        ("CDLRICKSHAWMAN", "rickshaw man"),
        ("CDLHIGHWAVE", "high-wave candle"),
        ("CDLSHORTLINE", "short line candle"),
        ("CDLSPINNINGTOP", "spinning top"),
    ]:
        assert [(d, lean) for d, lean in entries if d == detector] == [
            (detector, "neutral")
        ]
        assert entries[detector, "neutral"].name == name
    assert [lean for d, lean in entries if d == "CDLGRAVESTONEDOJI"] == ["bearish"]
    assert entries["CDLGRAVESTONEDOJI", "bearish"].name == "gravestone doji"


def test_colour_signed_detectors_keep_their_sign_as_the_lean():
    entries = _entries()
    for detector in ["CDLLONGLINE", "CDLMARUBOZU", "CDLCLOSINGMARUBOZU", "CDLBELTHOLD"]:
        assert (detector, "bullish") in entries
        assert (detector, "bearish") in entries


def test_entry_count_names_and_shapes():
    entries = playbook()
    # 61 detectors, 24 of which give a rising and a falling version.
    assert len(entries) == 85
    assert len({e.name for e in entries}) == 85
    assert all(e.shape and e.shape.endswith(".") for e in entries)
    assert all(e.lean in ("bullish", "bearish", "neutral") for e in entries)
