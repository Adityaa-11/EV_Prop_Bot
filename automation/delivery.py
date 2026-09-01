"""Idempotent Discord delivery for paper slips."""

from __future__ import annotations

import os
from typing import Any

import aiohttp


def webhook_for_platform(platform: str) -> str | None:
    if platform == "prizepicks":
        return os.getenv("DISCORD_WEBHOOK_PRIZEPICKS")
    if platform == "underdog":
        return os.getenv("DISCORD_WEBHOOK_UNDERDOG")
    return None


def ops_webhook() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_OPS") or os.getenv("DISCORD_WEBHOOK_PRIZEPICKS")


def format_ops_alert(title: str, message: str, *, color: int = 0xF59E0B) -> dict[str, Any]:
    return {
        "embeds": [
            {
                "title": title,
                "description": message,
                "color": color,
            }
        ]
    }


async def deliver_ops_alert(
    session: aiohttp.ClientSession,
    title: str,
    message: str,
    *,
    color: int = 0xF59E0B,
) -> dict[str, Any]:
    webhook = ops_webhook()
    if not webhook:
        return {"success": False, "status": "skipped", "error": "No ops webhook configured"}
    payload = format_ops_alert(title, message, color=color)
    try:
        async with session.post(webhook, json=payload, timeout=20) as response:
            if response.status in {200, 204}:
                return {"success": True, "status": "sent", "error": None}
            text = (await response.text())[:300]
            return {
                "success": False,
                "status": "failed",
                "error": f"HTTP {response.status}: {text}",
            }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "status": "failed", "error": str(exc)[:300]}


def format_paper_slip(entry: dict[str, Any]) -> dict[str, Any]:
    legs = "\n".join(
        (
            f"• **{leg['player_name']}** — {leg['side']} {leg['line']} "
            f"{leg['stat_type']} ({leg['win_probability']:.1f}%, {leg['book_count']} books)"
        )
        for leg in entry.get("legs", [])
    )
    description = (
        f"**PAPER — NO REAL WAGER**\n"
        f"Platform: **{entry['platform'].title()}** | Tier: **{entry['tier'].title()}**\n"
        f"Stake: **${entry['stake']:.2f}** → **${entry['potential_payout']:.2f}** "
        f"| Expected ROI: **{entry['expected_roi']:.2f}%**\n"
        f"{legs}\n"
        f"Locks: `{entry.get('lock_time')}`\n"
        f"Slip ID: `{entry['id']}`"
    )
    return {
        "embeds": [
            {
                "title": f"Paper Slip · {entry['sport']} · {entry['platform'].title()}",
                "description": description,
                "color": 0x22C55E if entry.get("tier") == "excellent" else 0x3B82F6,
            }
        ]
    }


async def deliver_paper_entry(
    session: aiohttp.ClientSession,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Send one paper slip exactly once when delivery_status is pending/failed."""
    webhook = webhook_for_platform(entry.get("platform", ""))
    if not webhook:
        return {
            "success": False,
            "status": "failed",
            "error": f"No Discord webhook configured for {entry.get('platform')}",
        }

    payload = format_paper_slip(entry)
    try:
        async with session.post(webhook, json=payload, timeout=20) as response:
            if response.status in {200, 204}:
                return {"success": True, "status": "sent", "error": None}
            text = (await response.text())[:300]
            return {
                "success": False,
                "status": "failed",
                "error": f"HTTP {response.status}: {text}",
            }
    except Exception as exc:  # noqa: BLE001 - surface delivery failures to audit trail
        return {"success": False, "status": "failed", "error": str(exc)[:300]}


def format_live_slip(
    entry: dict[str, Any],
    *,
    status_label: str,
    extra: str = "",
) -> dict[str, Any]:
    legs = "\n".join(
        (
            f"• **{leg['player_name']}** — {leg['side']} {leg['line']} "
            f"{leg['stat_type']}"
        )
        for leg in entry.get("legs", [])
    )
    shadow = " (SHADOW — no submit)" if entry.get("execution_shadow") else ""
    description = (
        f"**{status_label}{shadow}**\n"
        f"Platform: **{entry['platform'].title()}** | Tier: **{entry['tier'].title()}**\n"
        f"Stake: **${entry['stake']:.2f}** → **${entry['potential_payout']:.2f}**\n"
        f"{legs}\n"
        f"Slip ID: `{entry['id']}`"
    )
    if extra:
        description = f"{description}\n{extra}"
    color_map = {
        "LIVE — SUBMITTING": 0xF59E0B,
        "LIVE — PLACED": 0x22C55E,
        "LIVE — FAILED": 0xEF4444,
    }
    return {
        "embeds": [
            {
                "title": f"Live Slip · {entry['sport']} · {entry['platform'].title()}",
                "description": description,
                "color": color_map.get(status_label, 0x3B82F6),
            }
        ]
    }


async def deliver_live_status(
    session: aiohttp.ClientSession,
    entry: dict[str, Any],
    *,
    status_label: str,
    extra: str = "",
) -> dict[str, Any]:
    webhook = webhook_for_platform(entry.get("platform", "")) or ops_webhook()
    if not webhook:
        return {"success": False, "status": "skipped", "error": "No webhook configured"}
    payload = format_live_slip(entry, status_label=status_label, extra=extra)
    try:
        async with session.post(webhook, json=payload, timeout=20) as response:
            if response.status in {200, 204}:
                return {"success": True, "status": "sent", "error": None}
            text = (await response.text())[:300]
            return {
                "success": False,
                "status": "failed",
                "error": f"HTTP {response.status}: {text}",
            }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "status": "failed", "error": str(exc)[:300]}
