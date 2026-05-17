from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import EvidenceRecord, new_id, stable_hash


@dataclass(slots=True)
class LedgerVerificationIssue:
    index: int
    record_id: str | None
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "record_id": self.record_id,
            "code": self.code,
            "message": self.message,
        }


@dataclass(slots=True)
class LedgerVerificationResult:
    valid: bool
    record_count: int
    issues: list[LedgerVerificationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "record_count": self.record_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class AuditLedger(Protocol):
    def append(self, *, run_id: str, agent_id: str, event_type: str, payload: dict) -> EvidenceRecord: ...
    def list_records(self, run_id: str | None = None) -> list[EvidenceRecord]: ...
    def verify(self) -> LedgerVerificationResult: ...


def _expected_hash(record: EvidenceRecord) -> str:
    return stable_hash(
        {
            "record_id": record.record_id,
            "run_id": record.run_id,
            "agent_id": record.agent_id,
            "event_type": record.event_type,
            "payload": record.payload,
            "timestamp": record.timestamp,
            "previous_hash": record.previous_hash,
        }
    )


def _verify_records(records: list[EvidenceRecord]) -> LedgerVerificationResult:
    issues: list[LedgerVerificationIssue] = []
    previous_hash: str | None = None

    for index, record in enumerate(records):
        if record.previous_hash != previous_hash:
            issues.append(
                LedgerVerificationIssue(
                    index=index,
                    record_id=record.record_id,
                    code="previous_hash_mismatch",
                    message="Record previous_hash does not match the prior evidence_hash.",
                )
            )

        if record.evidence_hash is None:
            issues.append(
                LedgerVerificationIssue(
                    index=index,
                    record_id=record.record_id,
                    code="missing_evidence_hash",
                    message="Record is missing evidence_hash.",
                )
            )
        elif record.evidence_hash != _expected_hash(record):
            issues.append(
                LedgerVerificationIssue(
                    index=index,
                    record_id=record.record_id,
                    code="evidence_hash_mismatch",
                    message="Record evidence_hash does not match its sealed content.",
                )
            )

        previous_hash = record.evidence_hash

    return LedgerVerificationResult(valid=not issues, record_count=len(records), issues=issues)


class InMemoryAuditLedger:
    """Append-only in-memory audit ledger with hash chaining."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def append(self, *, run_id: str, agent_id: str, event_type: str, payload: dict) -> EvidenceRecord:
        previous_hash = self._records[-1].evidence_hash if self._records else None
        record = EvidenceRecord(
            record_id=new_id("evidence"),
            run_id=run_id,
            agent_id=agent_id,
            event_type=event_type,
            payload=payload,
            previous_hash=previous_hash,
        ).seal()
        self._records.append(record)
        return record

    def list_records(self, run_id: str | None = None) -> list[EvidenceRecord]:
        if run_id is None:
            return list(self._records)
        return [record for record in self._records if record.run_id == run_id]

    def verify(self) -> LedgerVerificationResult:
        return _verify_records(self.list_records())


class SQLiteAuditLedger:
    """SQLite-backed audit ledger.

    Suitable for development, demos, and small internal deployments. For highly
    regulated environments, back this interface with an enterprise audit store.
    """

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
                CREATE TABLE IF NOT EXISTS evidence_records (
                    record_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    previous_hash TEXT,
                    evidence_hash TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence_records(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_agent ON evidence_records(agent_id)")
            conn.commit()

    def _last_hash(self) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT evidence_hash FROM evidence_records ORDER BY rowid DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def append(self, *, run_id: str, agent_id: str, event_type: str, payload: dict) -> EvidenceRecord:
        record = EvidenceRecord(
            record_id=new_id("evidence"),
            run_id=run_id,
            agent_id=agent_id,
            event_type=event_type,
            payload=payload,
            previous_hash=self._last_hash(),
        ).seal()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO evidence_records
                (record_id, run_id, agent_id, event_type, payload_json, timestamp, previous_hash, evidence_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.run_id,
                    record.agent_id,
                    record.event_type,
                    json.dumps(record.payload, sort_keys=True),
                    record.timestamp,
                    record.previous_hash,
                    record.evidence_hash,
                ),
            )
            conn.commit()
        return record

    def list_records(self, run_id: str | None = None) -> list[EvidenceRecord]:
        sql = "SELECT record_id, run_id, agent_id, event_type, payload_json, timestamp, previous_hash, evidence_hash FROM evidence_records"
        params: tuple[str, ...] = ()
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params = (run_id,)
        sql += " ORDER BY rowid ASC"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            EvidenceRecord(
                record_id=row[0],
                run_id=row[1],
                agent_id=row[2],
                event_type=row[3],
                payload=json.loads(row[4]),
                timestamp=row[5],
                previous_hash=row[6],
                evidence_hash=row[7],
            )
            for row in rows
        ]

    def verify(self) -> LedgerVerificationResult:
        return _verify_records(self.list_records())
