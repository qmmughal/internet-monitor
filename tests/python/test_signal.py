import pytest

from wifi_monitor import signal as s


@pytest.mark.parametrize("dbm,pct", [(-30, 100), (-50, 100), (-75, 50), (-60, 80), (-100, 0), (-110, 0)])
def test_dbm_to_percent(dbm, pct):
    assert s.dbm_to_percent(dbm) == pct


@pytest.mark.parametrize("pct,dbm", [(100, -50), (0, -100), (60, -70), (150, -50), (-5, -100)])
def test_percent_to_dbm_estimate(pct, dbm):
    assert s.percent_to_dbm_estimate(pct) == dbm


@pytest.mark.parametrize(
    "ch,band,freq",
    [(1, None, 2412), (6, None, 2437), (13, None, 2472), (14, None, 2484), (36, None, 5180),
     (149, None, 5745), (165, None, 5825), (1, "6 GHz", 5955), (37, "6 GHz", 6135), (2, "6 GHz", 5935),
     (233, "6 GHz", 7115)],
)
def test_channel_to_freq(ch, band, freq):
    assert s.channel_to_freq(ch, band) == freq


@pytest.mark.parametrize("freq", [2412, 2437, 2484, 5180, 5745, 5955, 6135, 7115])
def test_freq_channel_roundtrip(freq):
    band = s.freq_to_band(freq)
    assert s.channel_to_freq(s.freq_to_channel(freq), band) == freq


def test_channel_band_is_ambiguous_above_177():
    assert s.channel_band(181) is None


def test_resolve_channel_prefers_frequency_for_band():
    assert s.resolve_channel(37, 6135, None) == (37, 6135, "6 GHz")
    assert s.resolve_channel(37, None, None) == (37, 5185, "5 GHz")  # without freq/band the 5 GHz reading wins
    assert s.resolve_channel(None, None, None) == (None, None, None)


@pytest.mark.parametrize("text,band", [("2.4 GHz", "2.4 GHz"), ("2,4 GHz", "2.4 GHz"), ("5 GHz", "5 GHz"), ("6 GHz", "6 GHz"), ("x", None)])
def test_normalize_band(text, band):
    assert s.normalize_band(text) == band


def test_quality_labels():
    assert [s.quality_label(v) for v in (-45, -55, -65, -80)] == ["Excellent", "Good", "Fair", "Poor"]
