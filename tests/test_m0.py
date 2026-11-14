"""M0 gate: seed runs clean and the database itself rejects a bad ledger insert (AT-10)."""

import time
from datetime import datetime, timezone

import pytest
from pymongo.errors import WriteError

from cli import seed
from gateway.canonical import canonical, digest, now


def good_entry():
    return {"_id": "le_1", "run_id": "run_x", "seq": 1, "ts": now(), "type": "decision", "actor": seed.AGENT_ID,
            "decision": "allow", "prev_hash": "0" * 64, "hash": "a" * 64}


def test_at10_ledger_rejects_missing_required_field(db):
    bad = good_entry()
    del bad["hash"]
    with pytest.raises(WriteError) as e:
        db.ledger.insert_one(bad)
    assert e.value.code == 121  # DocumentValidationFailure


def test_at10_ledger_rejects_unknown_field_and_bad_enum(db):
    with pytest.raises(WriteError):
        db.ledger.insert_one({**good_entry(), "note_to_self": "sloppy"})
    with pytest.raises(WriteError):
        db.ledger.insert_one({**good_entry(), "decision": "maybe"})


def test_ledger_accepts_a_valid_entry(db):
    db.ledger.insert_one(good_entry())
    assert db.ledger.count_documents({}) == 1


def test_warrant_is_one_per_step(db):
    w = {"_id": "w_1", "run_id": "run_x", "step": 1, "agent_id": seed.AGENT_ID, "on_behalf_of": "human:dana",
         "tool": "payments.refund", "args_digest": "d" * 64, "policy_refs": [{"id": "P-002", "version": 1}],
         "status": "issued", "issued_at": now(), "expires_at": now()}
    db.warrants.insert_one(w)
    with pytest.raises(WriteError):
        db.warrants.insert_one({**w, "_id": "w_2"})


def test_seed_is_complete_and_reset_is_fast(db):
    t0 = time.time()
    seed.reset(db)
    assert time.time() - t0 < 10
    assert db.sys_tickets.count_documents({}) == 6
    assert db.policies.count_documents({"status": "active"}) == len(seed.POLICIES)
    assert db.precedents.count_documents({"seeded": True}) == 20
    assert db.identities.find_one({"key_hash": seed.key_hash(seed.AGENT_KEY)})["_id"] == seed.AGENT_ID
    assert db.ledger.count_documents({}) == 0


def test_canonical_is_stable_and_survives_a_database_round_trip(db):
    assert canonical({"b": 1, "a": [2, {"d": 1, "c": 2}]}) == '{"a":[2,{"c":2,"d":1}],"b":1}'
    t = datetime(2026, 11, 14, 16, 0, 0, 123456, tzinfo=timezone.utc)
    assert canonical({"t": t}) == '{"t":"2026-11-14T16:00:00.123Z"}'
    doc = {"_id": "c1", "ts": now(), "amount_cents": 8000, "nested": {"z": 1, "a": "x"}}
    db.sys_outbox.insert_one(doc)
    assert digest(db.sys_outbox.find_one({"_id": "c1"})) == digest(doc)
