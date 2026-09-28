"""Audit trail integrity and the review queue (C4.5)."""

import json

from parakh.audit.review_queue import ReviewQueue
from parakh.audit.trail import AuditTrail


def test_trail_chain_verifies_and_detects_tampering(tmp_path) -> None:
    trail = AuditTrail(tmp_path / "audit.jsonl")
    trail.append("run.started", run_id="r1")
    trail.append("verdict.issued", run_id="r1", verdict="HOLD")
    assert trail.verify()

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["data"]["verdict"] = "BUY"
    lines[1] = json.dumps(record)
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not trail.verify()


def test_review_queue_round_trip(tmp_path) -> None:
    queue = ReviewQueue(tmp_path / "queue.json")
    item = queue.add(kind="summary", payload={"title": "T"}, reason="low confidence")
    assert [i.id for i in queue.pending()] == [item.id]
    queue.decide(item.id, approved=True, by="owner")
    assert queue.pending() == []
