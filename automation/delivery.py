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
