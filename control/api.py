"""Control API for reviewers and approvers, plus the live event feed.

The feed is one database-level change stream on ledger, runs and approvals,
fanned out to browsers as server-sent events. Nothing here polls.
"""

import json
import os
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from agent import scripted
from cli import seed
from gateway import control, killswitch, ledger, runs, schema
from gateway.db import get_db

app = FastAPI(title="Warrant control API")
CONSOLE = Path(__file__).resolve().parent.parent / "console" / "index.html"
WATCHED = ["ledger", "runs", "approvals", "policies"]
_subscribers: set[queue.Queue] = set()
_feed_started = False


def _feed():
    db = get_db()
    pipeline = [{"$match": {"ns.coll": {"$in": WATCHED}, "operationType": {"$in": ["insert", "update", "replace"]}}}]
    while True:
        try:
            with db.watch(pipeline, full_document="updateLookup") as stream:
                for event in stream:
                    message = json.dumps({"coll": event["ns"]["coll"], "op": event["operationType"],
                                          "doc": event.get("fullDocument")}, default=str)
                    for q in list(_subscribers):
                        q.put(message)
        except PyMongoError:
            time.sleep(1)


@app.on_event("startup")
def startup():
    global _feed_started
    db = get_db()
    killswitch.start(db)
    if not _feed_started:
        _feed_started = True
        threading.Thread(target=_feed, daemon=True, name="event-feed").start()
        threading.Thread(target=_warm, daemon=True, name="warm-search").start()


def _warm():
    """The first search after a quiet period is slow. Pay that cost at start, not on stage."""
    from gateway import precedents
    try:
        precedents.search(get_db(), "refund for goods damaged in transit", tool="payments.refund")
    except Exception:
        pass


def out(value):
    return jsonable_encoder(value)


class StartRun(BaseModel):
    tickets: list[str] | None = None
    label: str | None = None
    lookup: bool = True
    mode: str | None = None  # defaults to WARRANT_AGENT_MODE, else scripted
    pace: float = 1.0
    wait_seconds: float = 300


class Kill(BaseModel):
    by: str = "human:dana"
    reason: str = "Stopped by reviewer"


class Rollback(BaseModel):
    by: str = "human:dana"


class Flag(BaseModel):
    step: int
    by: str = "human:sam"
    note: str
    channel: str = "web"
    evidence: dict | None = None


class Threshold(BaseModel):
    by: str = "human:sam"
    percent: float
    channel: str = "web"


class Decision(BaseModel):
    approver: str = "human:sam"
    decision: str
    channel: str = "web"
    note: str = ""
    evidence: dict | None = None


@app.get("/")
def console():
    return FileResponse(CONSOLE)


@app.get("/config")
def config():
    return {"elevenlabs_agent_id": os.environ.get("ELEVENLABS_AGENT_ID", ""),
            "mode": os.environ.get("WARRANT_AGENT_MODE", "scripted")}


@app.post("/runs")
def start_run(body: StartRun):
    db = get_db()
    run = runs.start(db, seed.AGENT_ID, "Process today's refund queue", label=body.label)
    mode = body.mode or os.environ.get("WARRANT_AGENT_MODE", "scripted")
    if mode == "live":
        from agent import live  # imported lazily: needs the model SDK and an API key
        target, kwargs = live.run_queue, {"ticket_ids": body.tickets, "wait_seconds": body.wait_seconds, "run": run}
    else:
        target, kwargs = scripted.run_queue, {"ticket_ids": body.tickets, "wait_seconds": body.wait_seconds,
                                              "pace": body.pace, "run": run, "lookup": body.lookup}
    threading.Thread(target=target, args=(db,), kwargs=kwargs, daemon=True, name=run["_id"]).start()
    return out({"run_id": run["_id"], "mode": mode})


@app.get("/runs")
def list_runs():
    return out(list(get_db().runs.find().sort("started_at", -1).limit(10)))


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    db = get_db()
    run = db.runs.find_one({"_id": run_id})
    if not run:
        raise HTTPException(404, "no such run")
    return out({**run, "warrants": {s: db.warrants.count_documents({"run_id": run_id, "status": s})
                                    for s in ("issued", "used", "revoked")}})


@app.get("/runs/{run_id}/ledger")
def get_ledger(run_id: str):
    return out(ledger.entries(get_db(), run_id))


@app.post("/runs/{run_id}/kill")
def kill_run(run_id: str, body: Kill):
    return out(control.kill(get_db(), run_id, by=body.by, reason=body.reason))


@app.post("/runs/{run_id}/rollback")
def rollback_run(run_id: str, body: Rollback):
    return out(control.rollback(get_db(), run_id, by=body.by))


@app.get("/runs/{run_id}/reconstruct")
def reconstruct_run(run_id: str):
    return out(control.reconstruct(get_db(), run_id))


@app.get("/runs/{run_id}/verify")
def verify_run(run_id: str):
    return out(ledger.verify(get_db(), run_id))


@app.get("/approvals")
def list_approvals(status: str = "pending"):
    query = {} if status == "all" else {"status": status}
    return out(list(get_db().approvals.find(query).sort("created_at", 1)))


@app.get("/policies")
def list_policies():
    """The written rules, as stored in Atlas. `uses_precedents` marks the rule that searches past decisions."""
    return out([{"_id": p["_id"], "effect": p["effect"], "description": p["description"], "version": p["version"],
                 "params": p.get("params", {}), "history": p.get("history", []),
                 "uses_precedents": any(c["field"].startswith("precedent.") for c in p["when"])}
                for p in get_db().policies.find({"status": "active"}).sort("_id", 1)])


@app.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, body: Decision):
    result = control.decide_approval(get_db(), approval_id, body.approver, body.decision, channel=body.channel,
                                     note=body.note, evidence=body.evidence)
    if not result["ok"]:
        raise HTTPException(409, result["error"])
    threading.Thread(target=_announce_learned, args=(approval_id,), daemon=True).start()
    return out(result)


@app.post("/runs/{run_id}/flag")
def flag(run_id: str, body: Flag):
    """A human rules on a call that was already allowed. Their words become a precedent."""
    result = control.flag(get_db(), run_id, body.step, body.by, body.note, channel=body.channel,
                          evidence=body.evidence)
    if not result["ok"]:
        raise HTTPException(409, result["error"])
    threading.Thread(target=_announce_learned, args=(result["precedent_id"],), daemon=True).start()
    return out(result)


@app.post("/policies/{policy_id}/threshold")
def threshold(policy_id: str, body: Threshold):
    """A human sets how similar a request must be to a refused one before it is held."""
    result = control.set_threshold(get_db(), body.by, body.percent / 100, channel=body.channel,
                                   policy_id=policy_id)
    if not result["ok"]:
        raise HTTPException(409, result["error"])
    return out(result)


def _announce_learned(key: str):
    """Tell the console when Atlas has embedded and indexed the precedent a decision or a flag created."""
    from gateway import precedents
    db = get_db()
    ruling = db.precedents.find_one({"$or": [{"approval_id": key}, {"_id": key}]})
    if not ruling:
        return
    seconds = precedents.wait_until_searchable(db, ruling)
    message = json.dumps({"coll": "precedents", "op": "indexed", "doc": {**ruling, "seconds": seconds}}, default=str)
    for q in list(_subscribers):
        q.put(message)


@app.get("/precedents/similar")
def similar(approval_id: str):
    approval = get_db().approvals.find_one({"_id": approval_id})
    if not approval:
        raise HTTPException(404, "no such approval")
    return out({"mode": approval.get("precedent_mode"), "precedents": approval.get("precedents", [])})


@app.get("/scoreboard")
def scoreboard():
    """The latest red-team receipt, written by `./warrant scoreboard`."""
    evidence = CONSOLE.parent.parent / "docs" / "evidence"
    path, baseline = evidence / "scoreboard.json", evidence / "model-baseline.json"
    result = json.loads(path.read_text()) if path.exists() else {}
    if baseline.exists():
        b = json.loads(baseline.read_text())
        result["model_baseline"] = {k: b[k] for k in ("model", "trials", "written_rule_runs", "written_rule_runs_violated",
                                                      "unwritten_runs", "unwritten_runs_violated", "legit_runs",
                                                      "legit_runs_completed")}
    tests = evidence / "tests.json"  # written by `WARRANT_RECEIPT=1 pytest`
    if tests.exists():
        result["tests"] = json.loads(tests.read_text())
    return result


@app.get("/tickets")
def tickets():
    """What each customer asked for, in their own words. Shown above the agent's steps."""
    db = get_db()
    names = {c["_id"]: c["name"] for c in db.sys_crm.find({}, {"name": 1})}
    return out([{**t, "customer": names.get(t.get("customer_id"), t.get("customer_id"))}
                for t in db.sys_tickets.find()])


WHAT = {
    "policies": "The written rules. Changing a document changes the next decision.",
    "identities": "Agents and humans, and who an agent acts for.",
    "warrants": "Single-use authorizations, bound to one call and its arguments.",
    "ledger": "Every decision, execution, approval, kill and rollback, hash-chained per run.",
    "approvals": "Requests waiting for a human, with the challenge code for voice.",
    "precedents": "Past human decisions. Atlas embeds them itself.",
    "runs": "One agent run. A change stream on this collection is the kill switch.",
}


@app.get("/atlas")
def atlas():
    """What is really in the database: collections, what Atlas enforces on each, and the search pipeline."""
    from gateway import precedents
    db = get_db()
    options = {c["name"]: c.get("options", {}) for c in db.list_collections()}
    rows = []
    for name, what in WHAT.items():
        features = []
        validator = options.get(name, {}).get("validator", {}).get("$jsonSchema")
        if validator:
            strict = validator.get("additionalProperties") is False
            features.append({"kind": "ok", "text": "$jsonSchema validator" + (", strict" if strict else "")})
        for index_name, spec in db[name].index_information().items():
            keys = ", ".join(k for k, _ in spec["key"])
            if spec.get("unique") and index_name != "_id_":
                features.append({"kind": "info", "text": f"unique index: {keys}"})
            if "expireAfterSeconds" in spec:
                features.append({"kind": "hold", "text": f"TTL index: {keys}"})
        if name == "precedents":
            for ix in db.precedents.list_search_indexes():
                kind = "Vector Search index, autoEmbed voyage-4" if ix["type"] == "vectorSearch" else "Atlas Search index"
                features.append({"kind": "vio", "text": kind})
        rows.append({"name": name, "count": db[name].estimated_document_count(), "features": features, "what": what})
    return out({"database": db.name, "collections": rows,
                "pipeline": precedents.pipeline("<the agent's stated reason and the customer's text>", tool="payments.refund", k=5),
                "ledger_validator": options.get("ledger", {}).get("validator", {})})


@app.get("/precedents/learned")
def learned():
    """Rulings made since the last reset."""
    return out(list(get_db().precedents.find({"seeded": False}).sort("created_at", 1)))


@app.post("/reset")
def reset():
    db = get_db()
    seed.reset(db)
    return out({"ok": True, "search_indexes": schema.search_status(db)})


@app.get("/events")
def events():
    q: queue.Queue = queue.Queue()
    _subscribers.add(q)

    def stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    yield f"data: {q.get(timeout=15)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            _subscribers.discard(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
