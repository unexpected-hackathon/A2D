from __future__ import annotations

import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))


def now() -> dt.datetime:
    return dt.datetime.now(KST).replace(microsecond=0)


def iso(t: dt.datetime | None) -> str | None:
    if t is None:
        return None
    return t.astimezone(KST).replace(microsecond=0).isoformat()


def now_iso() -> str:
    return iso(now())  # type: ignore[return-value]


def parse(s: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(s) if s else None
