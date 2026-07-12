"""Durable pipeline snapshots and Hermes-facing audit history."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineStore:
    """Small SQLite store for runs, candidates, and settled outcomes."""

    def __init__(self, database_path: str | None = None):
        configured_path = database_path or os.getenv("DATABASE_PATH", ".data/ev_bot.db")
        self.database_path = Path(configured_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    status TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_lookup
                ON pipeline_runs (run_type, sport, id DESC);

                CREATE TABLE IF NOT EXISTS candidate_outcomes (
                    candidate_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'open',
                    result TEXT,
                    stake REAL,
                    payout REAL,
                    closing_line REAL,
                    notes TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS candidate_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    event_id TEXT,
                    player_name TEXT NOT NULL,
                    market_key TEXT NOT NULL,
                    side TEXT NOT NULL,
                    line REAL NOT NULL,
                    win_probability REAL NOT NULL,
                    book_count INTEGER NOT NULL,
                    dispersion REAL NOT NULL,
                    game_time TEXT,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_candidate_observations_identity
                ON candidate_observations (
                    platform, sport, event_id, player_name, market_key, side, id DESC
                );

                CREATE TABLE IF NOT EXISTS paper_entries (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    execution_mode TEXT NOT NULL DEFAULT 'paper',
                    tier TEXT NOT NULL,
                    stake REAL NOT NULL,
                    expected_roi REAL NOT NULL,
                    potential_payout REAL NOT NULL,
                    lock_time TEXT,
                    created_at TEXT NOT NULL,
                    settled_at TEXT,
                    result TEXT,
                    payout REAL,
                    profit REAL,
                    delivery_status TEXT NOT NULL DEFAULT 'pending',
                    delivery_attempts INTEGER NOT NULL DEFAULT 0,
                    delivery_error TEXT,
                    delivery_updated_at TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_paper_entries_created
                ON paper_entries (created_at DESC);

                CREATE TABLE IF NOT EXISTS automation_state (
                    state_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scan_leases (
                    lease_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Additive column migrations for existing databases."""
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(paper_entries)").fetchall()
        }
        alterations = {
            "delivery_attempts": "ALTER TABLE paper_entries ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0",
            "delivery_error": "ALTER TABLE paper_entries ADD COLUMN delivery_error TEXT",
            "delivery_updated_at": "ALTER TABLE paper_entries ADD COLUMN delivery_updated_at TEXT",
        }
        for column, statement in alterations.items():
            if column not in columns:
                connection.execute(statement)

    def save_run(
        self,
        run_type: str,
        sport: str,
        status: str,
        payload: dict[str, Any],
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs
                    (run_type, sport, status, captured_at, payload_json, metrics_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_type,
                    sport.lower(),
                    status,
                    _utc_now(),
                    json.dumps(payload, separators=(",", ":"), default=str),
                    json.dumps(metrics or {}, separators=(",", ":"), default=str),
                    error,
                ),
            )
            return int(cursor.lastrowid)

    def latest_run(self, run_type: str, sport: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, run_type, sport, status, captured_at, payload_json, metrics_json, error
                FROM pipeline_runs
                WHERE run_type = ? AND sport = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (run_type, sport.lower()),
            ).fetchone()

        if row is None:
            return None

        return {
            "id": row["id"],
            "run_type": row["run_type"],
            "sport": row["sport"],
            "status": row["status"],
            "captured_at": row["captured_at"],
            "payload": json.loads(row["payload_json"]),
            "metrics": json.loads(row["metrics_json"]),
            "error": row["error"],
        }

    def recent_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, run_type, sport, status, captured_at, metrics_json, error
                FROM pipeline_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "run_type": row["run_type"],
                "sport": row["sport"],
                "status": row["status"],
                "captured_at": row["captured_at"],
                "metrics": json.loads(row["metrics_json"]),
                "error": row["error"],
            }
            for row in rows
        ]

    def record_outcome(
        self,
        candidate_id: str,
        *,
        status: str,
        result: str | None = None,
        stake: float | None = None,
        payout: float | None = None,
        closing_line: float | None = None,
        notes: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO candidate_outcomes
                    (candidate_id, status, result, stake, payout, closing_line, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    status = excluded.status,
                    result = excluded.result,
                    stake = excluded.stake,
                    payout = excluded.payout,
                    closing_line = excluded.closing_line,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_id,
                    status,
                    result,
                    stake,
                    payout,
                    closing_line,
                    notes,
                    _utc_now(),
                ),
            )

    def record_candidate_observations(self, plays: list[dict[str, Any]]) -> None:
        observed_at = _utc_now()
        rows = []
        for play in plays:
            prop = play.get("prop", {})
            consensus = play.get("consensus", {})
            market_key = prop.get("market_key") or play.get("sharp_odds", {}).get("market")
            candidate_id = play.get("candidate_id")
            if not candidate_id or not market_key:
                continue
            rows.append(
                (
                    candidate_id,
                    prop.get("platform", ""),
                    prop.get("sport", ""),
                    prop.get("event_id"),
                    prop.get("player_name", ""),
                    market_key,
                    play.get("recommended_play", ""),
                    float(prop.get("line", 0)),
                    float(play.get("win_probability", 0)),
                    int(consensus.get("book_count", 0)),
                    float(consensus.get("dispersion", 0)),
                    prop.get("game_time"),
                    observed_at,
                    json.dumps(play, separators=(",", ":"), default=str),
                )
            )
        if not rows:
            return
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO candidate_observations (
                    candidate_id, platform, sport, event_id, player_name,
                    market_key, side, line, win_probability, book_count,
                    dispersion, game_time, observed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def update_open_entry_closing_lines(self, plays: list[dict[str, Any]]) -> int:
        """Apply the latest pregame line/probability observation to open slips."""
        now = datetime.now(timezone.utc)
        updated = 0
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, platform, payload_json, lock_time FROM paper_entries WHERE status = 'open'"
            ).fetchall()
            for row in rows:
                try:
                    lock_time = datetime.fromisoformat(row["lock_time"])
                except (TypeError, ValueError):
                    continue
                if lock_time <= now:
                    continue

                payload = json.loads(row["payload_json"])
                changed = False
                for leg in payload.get("legs", []):
                    for play in plays:
                        prop = play.get("prop", {})
                        if prop.get("platform") != row["platform"]:
                            continue
                        if prop.get("player_name") != leg.get("player_name"):
                            continue
                        if prop.get("market_key") != leg.get("market_key"):
                            continue
                        if leg.get("event_id") and prop.get("event_id") != leg.get("event_id"):
                            continue

                        closing_line = float(prop.get("line", leg["entry_line"]))
                        entry_line = float(leg["entry_line"])
                        side = leg["side"]
                        line_clv = (
                            closing_line - entry_line
                            if side == "OVER"
                            else entry_line - closing_line
                        )
                        closing_probability = float(
                            play.get("sharp_odds", {}).get(
                                "over_probability" if side == "OVER" else "under_probability",
                                0,
                            )
                        )
                        leg["closing_line"] = closing_line
                        leg["line_clv"] = round(line_clv, 3)
                        if abs(closing_line - entry_line) <= 0.001 and closing_probability:
                            leg["closing_probability"] = closing_probability
                            leg["probability_clv"] = round(
                                closing_probability - float(leg["win_probability"]),
                                2,
                            )
                        else:
                            leg["closing_probability"] = None
                            leg["probability_clv"] = None
                        leg["closing_observed_at"] = now.isoformat()
                        changed = True
                        break

                if changed:
                    connection.execute(
                        "UPDATE paper_entries SET payload_json = ? WHERE id = ?",
                        (
                            json.dumps(payload, separators=(",", ":"), default=str),
                            row["id"],
                        ),
                    )
                    updated += 1
        return updated

    def candidate_stability(self, candidate_id: str, limit: int = 2) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT side, line, observed_at
                FROM candidate_observations
                WHERE candidate_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (candidate_id, max(1, limit)),
            ).fetchall()
        stable = len(rows) >= limit and len({(row["side"], row["line"]) for row in rows}) == 1
        return {
            "observation_count": len(rows),
            "stable": stable,
            "last_observed_at": rows[0]["observed_at"] if rows else None,
        }

    def create_paper_entry(self, entry: dict[str, Any]) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO paper_entries (
                    id, fingerprint, platform, sport, status, execution_mode,
                    tier, stake, expected_roi, potential_payout, lock_time,
                    created_at, delivery_status, payload_json
                ) VALUES (?, ?, ?, ?, 'open', 'paper', ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    entry["id"],
                    entry["fingerprint"],
                    entry["platform"],
                    entry["sport"].lower(),
                    entry["tier"],
                    entry["stake"],
                    entry["expected_roi"],
                    entry["potential_payout"],
                    entry.get("lock_time"),
                    entry["created_at"],
                    json.dumps(entry, separators=(",", ":"), default=str),
                ),
            )
            return cursor.rowcount == 1

    def list_paper_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, platform, sport, status, execution_mode, tier, stake,
                       expected_roi, potential_payout, lock_time, created_at,
                       settled_at, result, payout, profit, delivery_status,
                       delivery_attempts, delivery_error, delivery_updated_at, payload_json
                FROM paper_entries
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        entries = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.update(
                {
                    "id": row["id"],
                    "platform": row["platform"],
                    "sport": row["sport"].upper(),
                    "status": row["status"],
                    "execution_mode": row["execution_mode"],
                    "tier": row["tier"],
                    "stake": row["stake"],
                    "expected_roi": row["expected_roi"],
                    "potential_payout": row["potential_payout"],
                    "lock_time": row["lock_time"],
                    "created_at": row["created_at"],
                    "settled_at": row["settled_at"],
                    "result": row["result"],
                    "payout": row["payout"],
                    "profit": row["profit"],
                    "delivery_status": row["delivery_status"],
                    "delivery_attempts": row["delivery_attempts"],
                    "delivery_error": row["delivery_error"],
                    "delivery_updated_at": row["delivery_updated_at"],
                }
            )
            entries.append(payload)
        return entries

    def settle_paper_entry(self, entry_id: str, *, result: str, payout: float) -> bool:
        settled_at = _utc_now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT stake FROM paper_entries WHERE id = ? AND status = 'open'",
                (entry_id,),
            ).fetchone()
            if row is None:
                return False
            profit = float(payout) - float(row["stake"])
            connection.execute(
                """
                UPDATE paper_entries
                SET status = 'settled', settled_at = ?, result = ?, payout = ?, profit = ?
                WHERE id = ?
                """,
                (settled_at, result, float(payout), profit, entry_id),
            )
            return True

    def paper_summary(self, starting_bankroll: float) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS entries,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_entries,
                    SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) AS losses,
                    SUM(CASE WHEN result IN ('push', 'void') THEN 1 ELSE 0 END) AS pushes,
                    COALESCE(SUM(CASE WHEN status = 'open' THEN stake ELSE 0 END), 0) AS exposure,
                    COALESCE(SUM(CASE WHEN status = 'settled' THEN profit ELSE 0 END), 0) AS profit,
                    COALESCE(SUM(CASE WHEN substr(created_at, 1, 10) = ? THEN stake ELSE 0 END), 0)
                        AS daily_staked,
                    COALESCE(SUM(
                        CASE WHEN substr(settled_at, 1, 10) = ? THEN profit ELSE 0 END
                    ), 0) AS daily_profit,
                    MAX(created_at) AS last_updated
                FROM paper_entries
                """,
                (today, today),
            ).fetchone()
        profit = float(totals["profit"] or 0)
        wins = int(totals["wins"] or 0)
        losses = int(totals["losses"] or 0)
        decided = wins + losses
        return {
            "starting_bankroll": round(starting_bankroll, 2),
            "bankroll": round(starting_bankroll + profit, 2),
            "profit": round(profit, 2),
            "exposure": round(float(totals["exposure"] or 0), 2),
            "entries": int(totals["entries"] or 0),
            "open_entries": int(totals["open_entries"] or 0),
            "wins": wins,
            "losses": losses,
            "pushes": int(totals["pushes"] or 0),
            "win_rate": round(wins / decided * 100, 2) if decided else 0.0,
            "daily_staked": round(float(totals["daily_staked"] or 0), 2),
            "daily_profit": round(float(totals["daily_profit"] or 0), 2),
            "last_updated": totals["last_updated"],
        }

    def get_state(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM automation_state WHERE state_key = ?",
                (key,),
            ).fetchone()
        return json.loads(row["value_json"]) if row else None

    def set_state(self, key: str, value: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO automation_state (state_key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    json.dumps(value, separators=(",", ":"), default=str),
                    _utc_now(),
                ),
            )

    def acquire_lease(self, lease_key: str, *, owner: str, ttl_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + ttl_seconds
        expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT owner, expires_at FROM scan_leases WHERE lease_key = ?",
                (lease_key,),
            ).fetchone()
            if row is not None:
                try:
                    current_expires = datetime.fromisoformat(row["expires_at"])
                except ValueError:
                    current_expires = now
                if row["owner"] != owner and current_expires > now:
                    return False
            connection.execute(
                """
                INSERT INTO scan_leases (lease_key, owner, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lease_key) DO UPDATE SET
                    owner = excluded.owner,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (lease_key, owner, expires_iso, _utc_now()),
            )
            return True

    def release_lease(self, lease_key: str, *, owner: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM scan_leases WHERE lease_key = ? AND owner = ?",
                (lease_key, owner),
            )

    def list_open_paper_entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.list_paper_entries(500) if entry.get("status") == "open"]

    def list_pending_delivery(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = self.list_paper_entries(limit)
        return [
            entry
            for entry in entries
            if entry.get("delivery_status") in {"pending", "failed"}
        ]

    def mark_delivery(
        self,
        entry_id: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE paper_entries
                SET delivery_status = ?,
                    delivery_attempts = delivery_attempts + 1,
                    delivery_error = ?,
                    delivery_updated_at = ?
                WHERE id = ?
                """,
                (status, error, _utc_now(), entry_id),
            )

    def freeze_closing_lines_past_lock(self) -> int:
        """Mark closing lines as frozen once lock time has passed."""
        now = datetime.now(timezone.utc)
        updated = 0
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, payload_json, lock_time FROM paper_entries WHERE status = 'open'"
            ).fetchall()
            for row in rows:
                try:
                    lock_time = datetime.fromisoformat(row["lock_time"])
                except (TypeError, ValueError):
                    continue
                if lock_time > now:
                    continue
                payload = json.loads(row["payload_json"])
                changed = False
                for leg in payload.get("legs", []):
                    if leg.get("closing_frozen"):
                        continue
                    if leg.get("closing_line") is None:
                        leg["closing_line"] = None
                        leg["line_clv"] = None
                        leg["closing_unavailable"] = True
                    leg["closing_frozen"] = True
                    changed = True
                if changed:
                    connection.execute(
                        "UPDATE paper_entries SET payload_json = ? WHERE id = ?",
                        (json.dumps(payload, separators=(",", ":"), default=str), row["id"]),
                    )
                    updated += 1
        return updated

    def apply_settlement(
        self,
        entry_id: str,
        *,
        result: str,
        payout: float,
        legs: list[dict[str, Any]] | None = None,
        provenance: str | None = None,
    ) -> bool:
        settled_at = _utc_now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT stake, payload_json FROM paper_entries WHERE id = ? AND status = 'open'",
                (entry_id,),
            ).fetchone()
            if row is None:
                return False
            payload = json.loads(row["payload_json"])
            if legs is not None:
                payload["legs"] = legs
            if provenance:
                payload["settlement_provenance"] = provenance
            profit = float(payout) - float(row["stake"])
            connection.execute(
                """
                UPDATE paper_entries
                SET status = 'settled',
                    settled_at = ?,
                    result = ?,
                    payout = ?,
                    profit = ?,
                    payload_json = ?
                WHERE id = ?
                """,
                (
                    settled_at,
                    result,
                    float(payout),
                    profit,
                    json.dumps(payload, separators=(",", ":"), default=str),
                    entry_id,
                ),
            )
            return True

    def observation_history(
        self,
        *,
        limit: int = 100,
        sport: str | None = None,
        platform: str | None = None,
        player: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if sport:
            clauses.append("LOWER(sport) = ?")
            params.append(sport.lower())
        if platform:
            clauses.append("platform = ?")
            params.append(platform.lower())
        if player:
            clauses.append("LOWER(player_name) LIKE ?")
            params.append(f"%{player.lower()}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT candidate_id, platform, sport, event_id, player_name, market_key,
                       side, line, win_probability, book_count, dispersion, game_time, observed_at
                FROM candidate_observations
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def delivery_failure_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM paper_entries WHERE delivery_status = 'failed'"
            ).fetchone()
        return int(row["count"] or 0)

    def settlement_backlog_count(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_entries
                WHERE status = 'open' AND lock_time IS NOT NULL AND lock_time < ?
                """,
                (now,),
            ).fetchone()
        return int(row["count"] or 0)


