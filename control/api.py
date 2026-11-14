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
WATCHED = ["ledger", "runs", "approvals"]
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
    mode: str | None = None  # defaults to WARRANT_AGENT_MODE, else scripted
    pace: float = 1.0
    wait_seconds: float = 300


class Kill(BaseModel):
    by: str = "human:dana"
    reason: str = "Stopped by reviewer"


class Rollback(BaseModel):
    by: str = "human:dana"


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
                                              "pace": body.pace, "run": run}
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
    return out(list(get_db().approvals.find({"status": status}).sort("created_at", 1)))


@app.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, body: Decision):
    result = control.decide_approval(get_db(), approval_id, body.approver, body.decision, channel=body.channel,
                                     note=body.note, evidence=body.evidence)
    if not result["ok"]:
        raise HTTPException(409, result["error"])
    threading.Thread(target=_announce_learned, args=(approval_id,), daemon=True).start()
    return out(result)


def _announce_learned(approval_id: str):
    """Tell the console when Atlas has embedded and indexed the precedent this decision created."""
    from gateway import precedents
    db = get_db()
    ruling = db.precedents.find_one({"approval_id": approval_id})
    if not ruling:
        return
    seconds = precedents.wait_until_searchable(db, ruling)
    message = json.dumps({"coll": "precedents", "op": "indexed", "doc": {
        "_id": ruling["_id"], "decision": ruling["decision"], "outcome_note": ruling.get("outcome_note", ""),
        "seconds": seconds}}, default=str)
    for q in list(_subscribers):
        q.put(message)


@app.get("/precedents/similar")
def similar(approval_id: str):
    approval = get_db().approvals.find_one({"_id": approval_id})
    if not approval:
        raise HTTPException(404, "no such approval")
    return out({"mode": approval.get("precedent_mode"), "precedents": approval.get("precedents", [])})


@app.get("/precedents/learned")
def learned():
    """Rulings made since the last reset."""
    return out(list(get_db().precedents.find({"seeded": False}, {"decision": 1, "outcome_note": 1, "decided_by": 1,
                                                                 "channel": 1, "created_at": 1})))


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
