#!/usr/bin/env python3
"""Backwards-compatible entry point for ``python cli/wifi-monitor.py``.

The implementation lives in the ``wifi_monitor`` package. After
``pip install .`` the same CLI is available as ``wifi-monitor``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wifi_monitor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
