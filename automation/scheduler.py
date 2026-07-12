"""Always-on Railway paper scheduler.

Runs inside the FastAPI process lifespan. Local Hermes is optional.
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiohttp


PaperTickFn = Callable[[str], Awaitable[dict[str, Any]]]
SettleFn = Callable[[], Awaitable[dict[str, Any]]]
DeliverFn = Callable[[], Awaitable[dict[str, Any]]]


class PaperScheduler:
    """Five-minute heartbeat that delegates all decisions to deterministic services."""

    def __init__(
        self,
        *,
        store: Any,
        tick_sport: PaperTickFn,
        settle_open: SettleFn,
        deliver_pending: DeliverFn,
        sports: list[str] | None = None,
        heartbeat_seconds: int | None = None,
        enabled: bool | None = None,
    ):
        self.store = store
        self.tick_sport = tick_sport
        self.settle_open = settle_open
        self.deliver_pending = deliver_pending
        self.sports = sports or [
            sport.strip().lower()
            for sport in os.getenv("PAPER_SPORTS", "mlb,nba,nfl,nhl").split(",")
            if sport.strip()
        ]
        self.heartbeat_seconds = heartbeat_seconds or int(
            os.getenv("PAPER_HEARTBEAT_SECONDS", "300")
        )
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("PAPER_SCHEDULER_ENABLED", "false").lower() in {"1", "true", "yes"}
        )
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def status(self) -> dict[str, Any]:
        latest = self.store.get_state("paper_scheduler") or {}
        return {
            "enabled": self.enabled,
            "worker_id": self.worker_id,
            "heartbeat_seconds": self.heartbeat_seconds,
            "sports": self.sports,
            "running": self._task is not None and not self._task.done(),
            **latest,
        }

    async def start(self) -> None:
        if not self.enabled:
            self.store.set_state(
                "paper_scheduler",
                {
                    "status": "disabled",
                    "message": "PAPER_SCHEDULER_ENABLED is false",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="paper-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def heartbeat_once(self) -> dict[str, Any]:
        """Single scheduler cycle used by lifespan and tests."""
        lease = self.store.acquire_lease(
            "paper_scheduler",
            owner=self.worker_id,
            ttl_seconds=self.heartbeat_seconds + 60,
        )
        if not lease:
            result = {
                "status": "skipped",
                "message": "lease_held_by_another_worker",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.store.set_state("paper_scheduler", result)
            return result

        ticks = []
        for sport in self.sports:
            try:
                ticks.append({"sport": sport, **(await self.tick_sport(sport))})
            except Exception as exc:  # noqa: BLE001
                ticks.append({"sport": sport, "status": "error", "message": str(exc)[:300]})

        delivery = await self.deliver_pending()
        settlement = await self.settle_open()
        checked_at = datetime.now(timezone.utc).isoformat()
        result = {
            "status": "ok",
            "checked_at": checked_at,
            "worker_id": self.worker_id,
            "ticks": ticks,
            "delivery": delivery,
            "settlement": settlement,
            "created_count": sum(int(tick.get("created_count") or 0) for tick in ticks),
        }
        self.store.set_state("paper_scheduler", result)
        self.store.release_lease("paper_scheduler", owner=self.worker_id)
        return result

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.heartbeat_once()
            except Exception as exc:  # noqa: BLE001
                self.store.set_state(
                    "paper_scheduler",
                    {
                        "status": "error",
                        "message": str(exc)[:300],
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.heartbeat_seconds)
            except asyncio.TimeoutError:
                continue
