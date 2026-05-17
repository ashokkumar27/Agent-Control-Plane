import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_control_plane import InMemoryAuditLedger, SQLiteAuditLedger


class LedgerTests(unittest.TestCase):
    def test_in_memory_hash_chain(self):
        ledger = InMemoryAuditLedger()
        first = ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
        second = ledger.append(run_id="r1", agent_id="a1", event_type="end", payload={"y": 2})
        self.assertIsNone(first.previous_hash)
        self.assertEqual(second.previous_hash, first.evidence_hash)
        self.assertTrue(ledger.verify().valid)

    def test_in_memory_verification_detects_tampering(self):
        ledger = InMemoryAuditLedger()
        ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
        ledger.list_records()[0].payload["x"] = 99

        result = ledger.verify()

        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "evidence_hash_mismatch")

    def test_in_memory_append_snapshots_payload(self):
        ledger = InMemoryAuditLedger()
        payload = {"result": {"status": "success"}}
        ledger.append(run_id="r1", agent_id="a1", event_type="tool_call_executed", payload=payload)
        payload["result"]["idempotency"] = {"replayed": False}

        records = ledger.list_records()

        self.assertNotIn("idempotency", records[0].payload["result"])
        self.assertTrue(ledger.verify().valid)

    def test_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.sqlite"
            ledger = SQLiteAuditLedger(db)
            ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
            records = SQLiteAuditLedger(db).list_records("r1")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].payload["x"], 1)

    def test_sqlite_verification_uses_append_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.sqlite"
            ledger = SQLiteAuditLedger(db)
            ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"index": 1})
            ledger.append(run_id="r2", agent_id="a1", event_type="middle", payload={"index": 2})
            ledger.append(run_id="r1", agent_id="a1", event_type="end", payload={"index": 3})

            records = SQLiteAuditLedger(db).list_records()

            self.assertEqual([record.payload["index"] for record in records], [1, 2, 3])
            self.assertEqual(records[1].previous_hash, records[0].evidence_hash)
            self.assertEqual(records[2].previous_hash, records[1].evidence_hash)
            self.assertTrue(SQLiteAuditLedger(db).verify().valid)

    def test_sqlite_verification_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.sqlite"
            ledger = SQLiteAuditLedger(db)
            record = ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
            with closing(sqlite3.connect(db)) as conn:
                conn.execute(
                    "UPDATE evidence_records SET payload_json = ? WHERE record_id = ?",
                    ('{"x": 99}', record.record_id),
                )
                conn.commit()

            result = SQLiteAuditLedger(db).verify()

            self.assertFalse(result.valid)
            self.assertEqual(result.issues[0].code, "evidence_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
