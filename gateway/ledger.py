"""The append-only, hash-chained ledger.

Every entry gets the next sequence number of its run and the hash of the entry
before it. `hash` is SHA-256 over the canonical entry without the hash field.
Appends always happen inside a transaction, so sequence, chain head and entry
commit together or not at all.
"""

from pymongo import ReturnDocument

from gateway.canonical import digest, now

GENESIS = "0" * 64


def append(db, session, run_id: str, entry: dict) -> dict:
    """Append one entry. Must be called inside a transaction."""
    run = db.runs.find_one_and_update({"_id": run_id}, {"$inc": {"next_seq": 1}},
                                      return_document=ReturnDocument.BEFORE, session=session)
    seq = run["next_seq"]
    body = {"_id": f"{run_id}:{seq:04d}", "run_id": run_id, "seq": seq, "ts": now(),
            **{k: v for k, v in entry.items() if v is not None}, "prev_hash": run["last_hash"]}
    body["hash"] = digest(body)
    db.ledger.insert_one(body, session=session)
    db.runs.update_one({"_id": run_id}, {"$set": {"last_hash": body["hash"]}}, session=session)
    return body


def append_tx(db, run_id: str, *entries: dict) -> list:
    """Append entries in their own transaction."""
    with db.client.start_session() as session:
        return session.with_transaction(lambda s: [append(db, s, run_id, e) for e in entries])


def entries(db, run_id: str) -> list:
    return list(db.ledger.find({"run_id": run_id}).sort("seq", 1))


def verify(db, run_id: str) -> dict:
    """Recompute the chain. Reports the first entry that was altered, removed or reordered."""
    prev, expected_seq, count = GENESIS, 1, 0
    for e in entries(db, run_id):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e["seq"] != expected_seq:
            return {"ok": False, "broken_at": expected_seq, "why": f"entry {expected_seq} is missing"}
        if e["prev_hash"] != prev:
            return {"ok": False, "broken_at": e["seq"], "why": "does not link to the entry before it"}
        if digest(body) != e["hash"]:
            return {"ok": False, "broken_at": e["seq"], "why": "content does not match its hash"}
        prev, expected_seq, count = e["hash"], expected_seq + 1, count + 1
    run = db.runs.find_one({"_id": run_id}) or {}
    if run.get("last_hash", prev) != prev:
        return {"ok": False, "broken_at": expected_seq, "why": "entries were removed from the end"}
    return {"ok": True, "entries": count, "head": prev}
