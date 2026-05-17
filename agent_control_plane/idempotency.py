from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import stable_hash, utc_now_iso


@dataclass(slots=True)
class IdempotencyRecord:
    key: str
    request_hash: str
    status: str
    result: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "request_hash": self.request_hash,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class IdempotencyStore(Protocol):
    def start(self, key: str, request_hash: str) -> tuple[IdempotencyRecord, bool]: ...
    def complete(self, key: str, request_hash: str, result: dict[str, Any]) -> IdempotencyRecord: ...
    def get(self, key: str) -> IdempotencyRecord | None: ...


def tool_call_fingerprint(*, agent_id: str, user_id: str | None, tool_name: str, args: dict[str, Any]) -> str:
    return stable_hash(
        {
            "agent_id": agent_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "args": args,
        }
    )


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}

    def start(self, key: str, request_hash: str) -> tuple[IdempotencyRecord, bool]:
        existing = self._records.get(key)
        if existing is not None:
            return existing, False
        now = utc_now_iso()
        record = IdempotencyRecord(
            key=key,
            request_hash=request_hash,
            status="in_progress",
            created_at=now,
            updated_at=now,
        )
        self._records[key] = record
        return record, True

    def complete(self, key: str, request_hash: str, result: dict[str, Any]) -> IdempotencyRecord:
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"Idempotency key '{key}' was not started")
        if record.request_hash != request_hash:
            raise ValueError(f"Idempotency key '{key}' was already used for a different request")
        record.status = "completed"
        record.result = result
        record.updated_at = utc_now_iso()
        return record

    def get(self, key: str) -> IdempotencyRecord | None:
        return self._records.get(key)


class SQLiteIdempotencyStore:
    """SQLite-backed idempotency store for retry-safe pilot deployments."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_status ON idempotency_records(status)")
            conn.commit()

    def start(self, key: str, request_hash: str) -> tuple[IdempotencyRecord, bool]:
        now = utc_now_iso()
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO idempotency_records
                    (key, request_hash, status, result_json, created_at, updated_at)
                    VALUES (?, ?, 'in_progress', NULL, ?, ?)
                    """,
                    (key, request_hash, now, now),
                )
                conn.commit()
            return IdempotencyRecord(key=key, request_hash=request_hash, status="in_progress", created_at=now, updated_at=now), True
        except sqlite3.IntegrityError:
            existing = self.get(key)
            if existing is None:  # pragma: no cover - defensive for unexpected SQLite behavior
                raise KeyError(f"Idempotency key '{key}' was not found after conflict")
            return existing, False

    def complete(self, key: str, request_hash: str, result: dict[str, Any]) -> IdempotencyRecord:
        now = utc_now_iso()
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE idempotency_records
                SET status = 'completed',
                    result_json = ?,
                    updated_at = ?
                WHERE key = ? AND request_hash = ?
                """,
                (json.dumps(result, sort_keys=True), now, key, request_hash),
            )
            conn.commit()
        if cursor.rowcount == 0:
            record = self.get(key)
            if record is None:
                raise KeyError(f"Idempotency key '{key}' was not started")
            raise ValueError(f"Idempotency key '{key}' was already used for a different request")
        completed = self.get(key)
        if completed is None:  # pragma: no cover - defensive
            raise KeyError(f"Idempotency key '{key}' was not found after completion")
        return completed

    def get(self, key: str) -> IdempotencyRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT key, request_hash, status, result_json, created_at, updated_at
                FROM idempotency_records
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return IdempotencyRecord(
            key=row[0],
            request_hash=row[1],
            status=row[2],
            result=json.loads(row[3]) if row[3] is not None else None,
            created_at=row[4],
            updated_at=row[5],
        )
