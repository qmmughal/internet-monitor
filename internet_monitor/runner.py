"""Safe execution of OS commands.

* Arguments are always passed as a list; ``shell=True`` is never used.
* Every call has a timeout and a bounded output size.
* Failures are returned as data, never raised, so callers can report them.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

MAX_OUTPUT_CHARS = 512 * 1024


@dataclass
class CommandResult:
    args: Sequence[str]
    returncode: Optional[int]
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None  # "not_found" | "timeout" | "os_error: ..."

    @property
    def ok(self) -> bool:
        return self.error is None and self.returncode == 0


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def run(args: Sequence[str], timeout: float = 5.0) -> CommandResult:
    if not isinstance(args, (list, tuple)) or not args or not all(isinstance(a, str) for a in args):
        raise ValueError("args must be a non-empty list of strings")

    exe = shutil.which(args[0])  # also accepts absolute paths
    if exe is None:
        return CommandResult(args, None, error="not_found")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            [exe, *args[1:]],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(args, None, error="timeout")
    except FileNotFoundError:
        return CommandResult(args, None, error="not_found")
    except OSError as exc:
        return CommandResult(args, None, error=f"os_error: {exc.strerror or exc}")

    return CommandResult(
        args,
        proc.returncode,
        stdout=_decode(proc.stdout)[:MAX_OUTPUT_CHARS],
        stderr=_decode(proc.stderr)[:MAX_OUTPUT_CHARS],
    )


def _decode(raw: bytes) -> str:
    """Decode console output. Windows tools may emit the OEM code page."""
    if not raw:
        return ""
    for enc in ("utf-8", _oem_encoding()):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _oem_encoding() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:  # pragma: no cover - only reachable on odd Windows setups
        return None
