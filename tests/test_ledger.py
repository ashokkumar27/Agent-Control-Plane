import tempfile
import unittest
from pathlib import Path

from agent_control_plane import InMemoryAuditLedger, SQLiteAuditLedger


class LedgerTests(unittest.TestCase):
    def test_in_memory_hash_chain(self):
        ledger = InMemoryAuditLedger()
        first = ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
        second = ledger.append(run_id="r1", agent_id="a1", event_type="end", payload={"y": 2})
        self.assertIsNone(first.previous_hash)
        self.assertEqual(second.previous_hash, first.evidence_hash)

    def test_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.sqlite"
            ledger = SQLiteAuditLedger(db)
            ledger.append(run_id="r1", agent_id="a1", event_type="start", payload={"x": 1})
            records = SQLiteAuditLedger(db).list_records("r1")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].payload["x"], 1)


if __name__ == "__main__":
    unittest.main()
