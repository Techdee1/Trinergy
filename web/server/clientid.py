"""Who is the client, for the rate limiter. Never trusts the leftmost X-Forwarded-For entry (the client writes it).

Order (only when TRUST_PROXY=1, i.e. the server really sits behind a proxy that overwrites/appends these headers):
  1. CF-Connecting-IP   set by Cloudflare itself (Render's edge); a client cannot choose it there
  2. X-Forwarded-For    the entry the trusted proxy appended: `TRUSTED_PROXY_HOPS` from the RIGHT (1 = the last entry)
  3. the connection address
With TRUST_PROXY=0 every proxy header is ignored (they are client-controlled on a directly exposed server).
An unparsable address is skipped, never used as a key.
"""

from __future__ import annotations

import ipaddress
from typing import Mapping


def _valid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_identity(headers: Mapping[str, str], client_host: str | None, trust_proxy: bool, hops: int = 1) -> tuple[str, str]:
    """(address used as the bucket key, source label). Headers are case-insensitive (Starlette's Headers)."""
    if trust_proxy:
        cf = _valid(headers.get("cf-connecting-ip"))
        if cf:
            return cf, "cf-connecting-ip"
        parts = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
        if hops >= 1 and len(parts) >= hops:
            xff = _valid(parts[-hops])
            if xff:
                return xff, "x-forwarded-for"
    return _valid(client_host) or client_host or "unknown", "client-address"


def identity_mode(trust_proxy: bool, hops: int) -> str:
    if not trust_proxy:
        return "direct: connection address only, proxy headers ignored (TRUST_PROXY=0)"
    return f"proxy: CF-Connecting-IP, else X-Forwarded-For entry {hops} from the right, else connection address (TRUST_PROXY=1)"
