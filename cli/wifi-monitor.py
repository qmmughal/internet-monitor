#!/usr/bin/env python3
"""Former entry point name, kept so existing scripts keep working. Use cli/internet-monitor.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from internet_monitor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
