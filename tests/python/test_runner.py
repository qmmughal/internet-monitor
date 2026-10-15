import sys

import pytest

from internet_monitor import runner


def test_missing_tool():
    assert runner.run(["definitely-not-a-real-tool-xyz"]).error == "not_found"


def test_timeout():
    r = runner.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)
    assert r.error == "timeout"


def test_success_and_output_captured():
    r = runner.run([sys.executable, "-c", "print('hi')"])
    assert r.ok and r.stdout.strip() == "hi"


def test_nonzero_exit_is_not_ok():
    r = runner.run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert not r.ok and r.returncode == 3 and r.error is None


def test_rejects_non_list_args():
    with pytest.raises(ValueError):
        runner.run("netsh wlan show interfaces")  # type: ignore[arg-type]
