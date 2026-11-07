"""Secret hygiene. The key is never logged, returned or stored; anything that might carry it goes through `redact`."""

from __future__ import annotations

import logging
import re

_PATTERNS = [re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}"), re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{12,}", re.I)]
_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    if value and len(value) >= 8:
        _secrets.add(value)


def redact(text: object) -> str:
    s = str(text)
    for sec in _secrets:
        s = s.replace(sec, "***")
    for rx in _PATTERNS:
        s = rx.sub("***", s)
    return s


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            red = redact(msg)
            if red != msg:                       # touch the record only when it carried a secret (uvicorn formats from args)
                record.msg, record.args = red, ()
        except Exception:  # noqa: BLE001 - a logging filter must never raise
            pass
        return True


def install_log_redaction() -> None:
    """Add the filter to every handler of the root, uvicorn and archive_qa loggers (idempotent)."""
    f = RedactFilter()
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "archive_qa", "web.server"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, RedactFilter) for x in lg.filters):
            lg.addFilter(f)
        for h in lg.handlers:
            if not any(isinstance(x, RedactFilter) for x in h.filters):
                h.addFilter(f)
