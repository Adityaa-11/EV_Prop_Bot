"""Helpers for feed-health / dry-spell ops alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def should_send_alert(
    prior: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    cooldown_hours: float = 6.0,
) -> bool:
    """Return True when no alert was sent within the cooldown window."""
    now = now or utc_now()
    if not prior:
        return True
    last = parse_utc(prior.get("sent_at") or prior.get("at"))
    if last is None:
        # Legacy once-per-day keys used {"date": "YYYY-MM-DD"}.
        if prior.get("date") == now.date().isoformat():
            return False
        return True
    return (now - last).total_seconds() >= cooldown_hours * 3600


def platform_play_counts(plays: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for play in plays:
        platform = str((play.get("prop") or {}).get("platform") or play.get("platform") or "unknown")
        counts[platform] = counts.get(platform, 0) + 1
    return counts


def hours_since(value: str | None, *, now: datetime | None = None) -> float | None:
    parsed = parse_utc(value)
    if parsed is None:
        return None
    now = now or utc_now()
    return max(0.0, (now - parsed).total_seconds() / 3600)


def dry_spell_should_alert(
    *,
    last_entry_created_at: str | None,
    dry_spell_hours: float,
    prior_alert: dict[str, Any] | None,
    now: datetime | None = None,
    cooldown_hours: float = 12.0,
) -> tuple[bool, float | None]:
    """Alert when no paper slips have been created for too long."""
    now = now or utc_now()
    elapsed = hours_since(last_entry_created_at, now=now)
    if elapsed is None:
        # Never created a slip in this DB — still worth one alert if cooldown allows.
        if should_send_alert(prior_alert, now=now, cooldown_hours=cooldown_hours):
            return True, None
        return False, None
    if elapsed < dry_spell_hours:
        return False, elapsed
    if not should_send_alert(prior_alert, now=now, cooldown_hours=cooldown_hours):
        return False, elapsed
    return True, elapsed
