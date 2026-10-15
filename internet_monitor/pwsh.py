"""Run fixed PowerShell scripts (Windows only) and parse their JSON output.

Scripts are constants in this package, passed with ``-EncodedCommand`` so no
quoting or user input is involved. Parameters are numbers validated by callers.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional, Tuple

from .runner import run


def run_json(script: str, timeout: float = 20.0, runner=run) -> Tuple[Optional[Any], Optional[str]]:
    """Return (parsed JSON, None) or (None, error)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    res = runner(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                  "-EncodedCommand", encoded], timeout=timeout)
    if res.error:
        return None, f"PowerShell unavailable ({res.error})"
    text = (res.stdout or "").strip()
    if res.returncode != 0 and not text:
        err = (res.stderr or "").strip().splitlines()
        return None, err[0][:200] if err else f"PowerShell exited with {res.returncode}"
    if not text:
        return [], None
    try:
        return json.loads(text), None
    except ValueError:
        return None, "unexpected PowerShell output"
