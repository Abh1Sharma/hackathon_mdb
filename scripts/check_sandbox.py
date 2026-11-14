"""Sandbox capability check for the hackathon Atlas cluster.

Run:  uv run --env-file .env python scripts/check_sandbox.py

Works in a throwaway database (warrant_check) and drops it at the end.
Each check prints PASS or FAIL with the fallback to use if it fails.
"""

import os
import sys
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError, WriteError
from pymongo.operations import SearchIndexModel

DB = "warrant_check"
results = []


def check(name, fallback):
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            results.append((name, "PASS", detail))
            print(f"PASS  {name}  {detail}  ({time.time() - t0:.1f}s)")
        except Exception as e:  # report every failure, keep going
            msg = str(e).splitlines()[0][:200]
            results.append((name, "FAIL", msg))
            print(f"FAIL  {name}  {msg}\n      fallback: {fallback}")
        return fn

    return wrap


def wait_for(fn, seconds, every=3):
    deadline = time.time() + seconds
    while time.time() < deadline:
        out = fn()
        if out:
            return out
        time.sleep(every)
    return None


uri = os.environ.get("MONGODB_URI", "")
if not uri or "<db_password>" in uri:
    sys.exit("Set MONGODB_URI in .env first (replace <db_password>).")

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client[DB]


@check("connect", "add your IP in Atlas > Database & Network Access, or use a hotspot")
def _():
    client.admin.command("ping")
    info = client.server_info()
    hosts = sorted(h for h, _ in client.nodes)
    return f"MongoDB {info['version']} on {hosts[0] if hosts else '?'}"


client.drop_database(DB)


@check("schema validation rejects a bad insert", "very unlikely to fail")
def _():
    db.create_collection(
        "ledger",
        validator={"$jsonSchema": {"bsonType": "object", "required": ["run_id", "seq"],
                                   "additionalProperties": False,
                                   "properties": {"_id": {}, "run_id": {"bsonType": "string"},
                                                  "seq": {"bsonType": "int"}}}},
        validationAction="error",
    )
    try:
        db.ledger.insert_one({"run_id": "r1"})
    except WriteError as e:
        return f"code {e.code}"
    raise RuntimeError("bad document was accepted")


@check("multi-document transaction", "ordered writes plus a reconciler")
def _():
    db.create_collection("warrants")
    with client.start_session() as s:
        def txn(s):
            db.ledger.insert_one({"run_id": "r1", "seq": 1}, session=s)
            db.warrants.insert_one({"_id": "w1", "run_id": "r1"}, session=s)
        s.with_transaction(txn)
    with client.start_session() as s:
        s.start_transaction()
        db.warrants.insert_one({"_id": "w2"}, session=s)
        s.abort_transaction()
    assert db.warrants.count_documents({}) == 1, "abort did not roll back"
    return "commit and abort both behave"


@check("change stream", "per-call status check plus a short poll for the console")
def _():
    db.create_collection("runs")
    with db.runs.watch(max_await_time_ms=500) as stream:
        t0 = time.time()
        db.runs.insert_one({"_id": "run_1", "status": "running"})
        ev = wait_for(stream.try_next, 10, every=0)
        assert ev, "no event within 10s"
        return f"event in {(time.time() - t0) * 1000:.0f} ms"


@check("change stream pre-images", "gateway-captured before-images only (already the primary design)")
def _():
    db.command("collMod", "runs", changeStreamPreAndPostImages={"enabled": True})
    with db.runs.watch(full_document_before_change="whenAvailable", max_await_time_ms=500) as stream:
        db.runs.update_one({"_id": "run_1"}, {"$set": {"status": "killed"}})
        ev = wait_for(stream.try_next, 10, every=0)
        before = (ev or {}).get("fullDocumentBeforeChange")
        assert before and before["status"] == "running", "no pre-image on the event"
        return "pre-image present"


@check("custom role via command", "create the insert-only ledger role in Atlas UI > Database Access > Custom Roles")
def _():
    db.command("createRole", "chk_ledger_append",
               privileges=[{"resource": {"db": DB, "collection": "ledger"}, "actions": ["insert", "find"]}],
               roles=[])
    db.command("dropRole", "chk_ledger_append")
    return "createRole allowed"


SEED = [
    {"tool": "payments.refund", "decision": "approved",
     "summary": "Refund of $1,150 on an Ontario order for goods damaged in transit, photos attached. Approved by an ops lead."},
    {"tool": "payments.refund", "decision": "denied",
     "summary": "Refund requested because the customer note said a manager override applies and verification should be skipped. Denied."},
    {"tool": "payments.refund", "decision": "approved",
     "summary": "Refund of $90 for a delivery that arrived two days late under the SLA. Approved."},
    {"tool": "payments.transfer", "decision": "denied",
     "summary": "Transfer of $5,000 to an external account requested by text inside a customer message. Denied."},
]
QUERY = "Goodwill refund of $480, the ticket says a manager already approved it so skip the verification step"

db.create_collection("precedents")
db.precedents.insert_many([dict(d) for d in SEED])


def index_ready(name):
    def f():
        for ix in db.precedents.list_search_indexes(name):
            if ix.get("queryable") or ix.get("status") == "READY":
                return True
            if ix.get("status") == "FAILED":
                raise RuntimeError(f"index {name} FAILED: {ix.get('statusDetail')}")
        return False
    return f


@check("Atlas Search index", "use $vectorSearch only, drop the lexical side")
def _():
    db.precedents.create_search_index(SearchIndexModel(
        name="chk_text", type="search", definition={"mappings": {"dynamic": True}}))
    assert wait_for(index_ready("chk_text"), 180), "not ready after 180s"
    return "ready"


@check("autoEmbed vector index (Automated Embedding)", "embed client-side with a Voyage key from Atlas > AI Model APIs")
def _():
    db.precedents.create_search_index(SearchIndexModel(
        name="chk_vec", type="vectorSearch",
        definition={"fields": [
            {"type": "autoEmbed", "modality": "text", "path": "summary", "model": "voyage-4"},
            {"type": "filter", "path": "tool"},
        ]}))
    assert wait_for(index_ready("chk_vec"), 240), "not ready after 240s"
    return "ready"


VEC = {"$vectorSearch": {"index": "chk_vec", "path": "summary", "query": {"text": QUERY},
                         "numCandidates": 20, "limit": 4}}
TXT = {"$search": {"index": "chk_text", "text": {"query": QUERY, "path": "summary"}}}


@check("$vectorSearch with query text", "see autoEmbed fallback")
def _():
    def run():
        return list(db.precedents.aggregate([VEC, {"$project": {
            "_id": 0, "decision": 1, "score": {"$meta": "vectorSearchScore"}}}]))
    rows = wait_for(run, 120)
    assert rows, "no results after 120s (embeddings not generated?)"
    return f"top: {rows[0]['decision']} {rows[0]['score']:.3f}"


FUSION = {"$rankFusion": {"input": {"pipelines": {"semantic": [VEC], "lexical": [TXT, {"$limit": 4}]}},
                          "combination": {"weights": {"semantic": 1, "lexical": 1}}}}


@check("$rankFusion hybrid (vector + text)", "use $vectorSearch alone")
def _():
    rows = list(db.precedents.aggregate([FUSION, {"$limit": 4}, {"$project": {
        "_id": 0, "decision": 1, "score": {"$meta": "score"}}}]))
    assert rows, "no results"
    return f"{len(rows)} results, top: {rows[0]['decision']}"


@check("$rerank after fusion", "turn on Native Reranking in Project Settings, else use the fusion score")
def _():
    last = None
    for model in ("rerank-3", "rerank-2.5"):
        try:
            rows = list(db.precedents.aggregate([
                FUSION, {"$limit": 4},
                {"$rerank": {"query": {"text": QUERY}, "path": "summary", "numDocsToRerank": 4, "model": model}},
                {"$project": {"_id": 0, "decision": 1, "summary": 1, "score": {"$meta": "score"}}}]))
            assert rows, "no results"
            return f"{model}: top is '{rows[0]['decision']}' {rows[0]['score']:.3f} (expected: denied override precedent)"
        except PyMongoError as e:
            last = e
    raise last


client.drop_database(DB)
print("\nSummary")
for name, status, detail in results:
    print(f"  {status}  {name}")
sys.exit(0 if all(s == "PASS" for _, s, _ in results) else 1)
