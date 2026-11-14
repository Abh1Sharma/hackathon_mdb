"""Canonical JSON and SHA-256. The only place hashing rules live.

Rules: sorted keys, compact separators, datetimes as UTC ISO strings with
millisecond precision (MongoDB stores milliseconds, so anything finer would
not survive a round trip and the chain would not verify).
"""

import hashlib
import json
from datetime import datetime, timezone


def now() -> datetime:
    """UTC now, truncated to the millisecond precision MongoDB keeps."""
    t = datetime.now(timezone.utc)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


def _default(o):
    if isinstance(o, datetime):
        if o.tzinfo is None:
            o = o.replace(tzinfo=timezone.utc)
        o = o.astimezone(timezone.utc)
        return o.strftime("%Y-%m-%dT%H:%M:%S.") + f"{o.microsecond // 1000:03d}Z"
    return str(o)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default, ensure_ascii=False)


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()
