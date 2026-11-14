"""Runs: one agent working one goal. The run document holds the head of its ledger chain."""

import secrets

from gateway.canonical import now
from gateway.ledger import GENESIS


def start(db, agent_id: str, goal: str, label: str | None = None) -> dict:
    ident = db.identities.find_one({"_id": agent_id})
    run = {"_id": f"run_{now():%H%M%S}_{secrets.token_hex(2)}", "agent_id": agent_id,
           "on_behalf_of": ident["on_behalf_of"], "goal": goal, "status": "running", "started_at": now(),
           "last_hash": GENESIS, "next_seq": 1}
    if label:
        run["label"] = label
    db.runs.insert_one(run)
    return run


def finish(db, run_id: str) -> None:
    db.runs.update_one({"_id": run_id, "status": "running"}, {"$set": {"status": "completed", "ended_at": now()}})
