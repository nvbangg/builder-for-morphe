import os
import sys
import threading
from typing import Never

IS_GITHUB: bool = os.getenv("GITHUB_ACTIONS") == "true"
_lock = threading.Lock()


def _log(color: str, symbol: str, msg: str, gh_level: str | None = None) -> None:
    if IS_GITHUB and gh_level:
        line = f"::{gh_level}::{msg}"
    else:
        line = f"\033[0;{color}m[{symbol}] {msg}\033[0m"

    with _lock:
        print(line, file=sys.stderr)

def pr(msg: str) -> None:
    _log("32", "+", msg)

def epr(msg: str) -> None:
    _log("31", "-", msg, "error")

def wpr(msg: str) -> None:
    _log("33", "!", msg, "warning")

def abort(msg: str) -> Never:
    epr(f"ABORT: {msg}")
    sys.exit(1)