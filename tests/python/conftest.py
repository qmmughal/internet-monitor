import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never read or write the real user configuration during tests."""
    home = tmp_path / "wm-home"
    monkeypatch.setenv("INTERNET_MONITOR_HOME", str(home))
    return home
