"""The gateway. Every tool call goes through `call_tool`, and nothing else calls a tool.

    identify -> resolve facts -> search precedents -> decide (transaction) -> warrant
             -> execute -> verify -> record

Policy is enforced here, outside the model. The decision, the warrant (or the
approval request) and the ledger entry commit in one transaction, so there is
no action without a record and no record without a decision.
"""

import hashlib
import inspect
from datetime import timedelta

from pymongo import ReturnDocument

from gateway import killswitch, ledger, policies, precedents
from gateway.canonical import digest, now
from systems.tools import TOOLS

WARRANT_TTL = timedelta(seconds=120)
APPROVAL_TTL = timedelta(minutes=15)
SENSITIVE = {"body", "email"}  # stored as a digest, never in clear


def refusal(code: str, rule: str, explanation: str, **extra) -> dict:
    """A structured refusal the agent can read: DENIED, STEP_UP_PENDING, KILLED or WARRANT_INVALID."""
    return {"ok": False, "code": code, "rule": rule, "explanation": explanation, **extra}


def redact(args: dict) -> dict:
    return {k: ({"redacted": True, "sha256": digest(v)} if k in SENSITIVE else v) for k, v in args.items()}


def identify(db, agent_key: str):
    ident = db.identities.find_one({"key_hash": hashlib.sha256((agent_key or "").encode()).hexdigest()})
    return ident if ident and ident.get("status") == "active" else None


def resolve(db, tool: str, args: dict) -> tuple[dict, str]:
    """Facts policy needs about the record a call touches, and the untrusted text behind the request."""
    resource = {}
    spec = TOOLS.get(tool)
    if spec and spec["resource"]:
        collection, arg = spec["resource"]
        doc = db[collection].find_one({"_id": args.get(arg)})
        if doc:
            resource = {"id": doc["_id"], "region": doc.get("region"), "total_cents": doc.get("total_cents")}
    ticket = db.sys_tickets.find_one({"_id": args["ticket_id"]}) if args.get("ticket_id") else None
    return resource, (ticket or {}).get("customer_note", "")


def refund_total(db, run_id: str, session=None) -> int:
    """History metric for P-007: what this run has already refunded, computed from the ledger."""
    rows = list(db.ledger.aggregate([
        {"$match": {"run_id": run_id, "type": "execution", "tool": "payments.refund", "payload.ok": True}},
        {"$group": {"_id": None, "total": {"$sum": "$payload.args.amount_cents"}}},
    ], session=session))
    return rows[0]["total"] if rows else 0


def authorize(db, *, agent_key: str, run_id: str, step: int, tool: str, args: dict, reason: str,
              trace_id: str | None = None) -> dict:
    """Decide. Returns {"ok": True, "warrant_id"} or a refusal. Never executes anything."""
    ident = identify(db, agent_key)
    if not ident:
        return refusal("DENIED", "IDENTITY", "Unknown or suspended agent identity")
    base = {"actor": ident["_id"], "on_behalf_of": ident.get("on_behalf_of"), "step": step, "tool": tool,
            "trace_id": trace_id}
    if not reason or not reason.strip():
        ledger.append_tx(db, run_id, {**base, "type": "violation",
                                      "payload": {"code": "NO_REASON", "args": redact(args)}})
        return refusal("DENIED", "FR-02", "Every tool call must state a reason")

    def killed(run, session=None):
        entry = {**base, "type": "violation", "reason": reason, "payload": {"code": "KILLED", "args": redact(args)}}
        ledger.append(db, session, run_id, entry) if session else ledger.append_tx(db, run_id, entry)
        kill = run.get("kill", {})
        return refusal("KILLED", "KILL", f"Run killed by {kill.get('by')}: {kill.get('reason')}")

    if killswitch.is_killed(run_id):  # fast path, fed by a change stream
        return killed(db.runs.find_one({"_id": run_id}))

    args_digest = digest(args)
    warrant = db.warrants.find_one({"run_id": run_id, "step": step})
    if warrant:
        if warrant["status"] == "issued" and warrant["tool"] == tool and warrant["args_digest"] == args_digest:
            return {"ok": True, "warrant_id": warrant["_id"], "decision": "allow", "resumed": True}
        why = f"step {step} already has a warrant ({warrant['status']}) for a different or finished call"
        ledger.append_tx(db, run_id, {**base, "type": "violation", "warrant_id": warrant["_id"], "reason": reason,
                                      "payload": {"code": "WARRANT_INVALID", "why": why, "args": redact(args)}})
        return refusal("WARRANT_INVALID", "WARRANT", why)
    approval = db.approvals.find_one({"run_id": run_id, "step": step})
    if approval and approval["status"] == "pending":
        return refusal("STEP_UP_PENDING", approval["request"]["rule"], "Waiting for a human decision",
                       approval_id=approval["_id"])
    if approval:
        run = db.runs.find_one({"_id": run_id})
        if run["status"] == "killed":
            return killed(run)
        return refusal("DENIED", approval["request"]["rule"], f"A human decision on this step: {approval['status']}",
                       approval_id=approval["_id"])

    resource, note = resolve(db, tool, args)
    active = list(db.policies.find({"status": "active"}))
    ctx = {"tool": tool, "args": args, "resource": resource, "history": {}, "precedent": {},
           "identity": {"id": ident["_id"], "class": ident.get("class"), "regions": ident.get("regions", [])}}

    # Precedent search runs before the transaction and only supplies facts. If it fails, fail closed.
    text = precedents.summary(tool, args.get("amount_cents"), resource.get("region"), reason, note)
    found = None
    searching = [p for p in active if policies.uses_precedents(p, tool)]
    if searching:
        try:
            found = precedents.search(db, text, tool=tool)
            ctx["precedent"] = precedents.facts(found, searching[0].get("params", {}).get("min_score", 0.7))
        except Exception as e:
            ctx["precedent"] = {"denied_match": True, "mode": "error", "error": str(e)[:200]}

    def decide(session):
        run = db.runs.find_one({"_id": run_id}, session=session)
        if not run:
            raise ValueError(f"no run {run_id}")
        if run["status"] == "killed":  # re-checked here, so a lagging change stream cannot be raced
            return killed(run, session)
        if tool == "payments.refund":
            total = refund_total(db, run_id, session)
            ctx["history"] = {"run_refund_total_cents": total,
                              "run_refund_total_after_cents": total + int(args.get("amount_cents") or 0)}
        verdict = policies.evaluate(active, ctx)
        ledger.append(db, session, run_id, {
            **base, "type": "decision", "reason": reason, "decision": verdict["decision"],
            "policy_refs": verdict["policy_refs"], "precedent_refs": precedents.refs(found) if found else None,
            "payload": {"args": redact(args), "rule": verdict["rule"], "resource": resource,
                        "history": ctx["history"], "precedent": ctx["precedent"]}})
        if verdict["decision"] == "allow":
            issued = now()
            warrant_id = f"w_{run_id}_{step}"
            db.warrants.insert_one({
                "_id": warrant_id, "run_id": run_id, "step": step, "agent_id": ident["_id"],
                "on_behalf_of": ident["on_behalf_of"], "tool": tool, "args_digest": args_digest,
                "policy_refs": verdict["policy_refs"], "status": "issued", "issued_at": issued,
                "expires_at": issued + WARRANT_TTL}, session=session)
            return {"ok": True, "warrant_id": warrant_id, "decision": "allow", "rule": verdict["rule"]}
        if verdict["decision"] == "step_up":
            created = now()
            approval_id = f"ap_{run_id}_{step}"
            db.approvals.insert_one({
                "_id": approval_id, "run_id": run_id, "step": step, "status": "pending",
                "request": {"tool": tool, "args": args, "args_digest": args_digest, "reason": reason,
                            "rule": verdict["rule"], "explanation": verdict["explanation"],
                            "policy_refs": verdict["policy_refs"], "agent_id": ident["_id"],
                            "on_behalf_of": ident["on_behalf_of"], "resource": resource, "note": note,
                            "summary": text},
                "precedents": found["hits"] if found else [], "precedent_mode": found["mode"] if found else None,
                "created_at": created, "expires_at": created + APPROVAL_TTL}, session=session)
            return refusal("STEP_UP_PENDING", verdict["rule"], verdict["explanation"], approval_id=approval_id)
        return refusal("DENIED", verdict["rule"], verdict["explanation"])

    with db.client.start_session() as session:
        return session.with_transaction(decide)


def verify_effect(db, tool: str, args: dict, result) -> tuple:
    """Read the target system back. Returns (verified, detail). verified is True, False, "n/a" or "unknown"."""
    if tool == "orders.get":
        return "n/a", "read only"
    if tool in ("payments.refund", "payments.transfer"):
        doc = db.sys_payments.find_one({"_id": result["_id"]})
        present = bool(doc) and doc["amount_cents"] == args["amount_cents"] and doc["status"] == "settled"
        return present, f"payment {result['_id']} {'present' if present else 'NOT present'} in sys_payments"
    if tool == "crm.update_contact":
        doc = db.sys_crm.find_one({"_id": args["customer_id"]}) or {}
        present = all(doc.get(k) == v for k, v in args["fields"].items())
        return present, "customer record matches the requested fields" if present else "customer record differs"
    if tool == "email.send":
        queued = db.sys_outbox.count_documents({"_id": result["_id"]}) == 1
        return "unknown", ("queued in outbox, " if queued else "NOT in outbox, ") + "delivery cannot be read back or undone"
    return False, "no verifier for this tool"


def execute(db, *, warrant_id: str, tool: str, args: dict, trace_id: str | None = None) -> dict:
    """Spend a warrant: single use, bound to the tool and the exact arguments, not expired, not revoked."""
    t = now()
    warrant = db.warrants.find_one_and_update(
        {"_id": warrant_id, "status": "issued", "tool": tool, "args_digest": digest(args), "expires_at": {"$gt": t}},
        {"$set": {"status": "used", "used_at": t}}, return_document=ReturnDocument.BEFORE)
    if not warrant:
        seen = db.warrants.find_one({"_id": warrant_id})
        if not seen:
            return refusal("WARRANT_INVALID", "WARRANT", "No such warrant")
        if seen["status"] == "used":
            why = "replay: this warrant was already used"
        elif seen["status"] == "revoked":
            why = "this warrant was revoked"
        elif seen["tool"] != tool or seen["args_digest"] != digest(args):
            why = "argument digest mismatch: the warrant was issued for a different call"
        else:
            why = "this warrant has expired"
        ledger.append_tx(db, seen["run_id"], {
            "type": "violation", "actor": seen["agent_id"], "on_behalf_of": seen["on_behalf_of"],
            "step": seen["step"], "tool": tool, "warrant_id": warrant_id, "trace_id": trace_id,
            "payload": {"code": "WARRANT_INVALID", "why": why, "args": redact(args)}})
        return refusal("WARRANT_INVALID", "WARRANT", why)

    spec = TOOLS[tool]
    params = inspect.signature(spec["fn"]).parameters
    kwargs = {k: v for k, v in args.items() if k in params}
    if "idempotency_key" in params:  # derived from the warrant, so a retry can never apply twice
        kwargs["idempotency_key"] = digest({"warrant": warrant_id})
    before = db.sys_crm.find_one({"_id": args.get("customer_id")}) if tool == "crm.update_contact" else None
    try:
        result, error = spec["fn"](db, **kwargs), None
        verified, detail = verify_effect(db, tool, args, result)
    except Exception as e:
        result, error, verified, detail = None, f"{type(e).__name__}: {e}", False, "tool raised"

    base = {"actor": warrant["agent_id"], "on_behalf_of": warrant["on_behalf_of"], "step": warrant["step"],
            "tool": tool, "warrant_id": warrant_id, "trace_id": trace_id}
    ledger.append_tx(
        db, warrant["run_id"],
        {**base, "type": "execution", "payload": {
            "ok": error is None, "args": redact(args), "error": error, "reversible": spec["reversible"],
            "result_id": result.get("_id") if isinstance(result, dict) else None,
            "result_digest": digest(result) if result is not None else None, "before_image": before}},
        {**base, "type": "verification", "payload": {"verified": verified, "detail": detail}})
    if error:
        return refusal("TOOL_ERROR", "TOOL", error, warrant_id=warrant_id)
    return {"ok": True, "result": result, "warrant_id": warrant_id, "verified": verified, "detail": detail}


def call_tool(db, *, agent_key: str, run_id: str, step: int, tool: str, args: dict, reason: str,
              trace_id: str | None = None) -> dict:
    """The one entry point for agents: authorize, then execute if a warrant was issued."""
    grant = authorize(db, agent_key=agent_key, run_id=run_id, step=step, tool=tool, args=args, reason=reason,
                      trace_id=trace_id)
    if not grant["ok"]:
        return grant
    done = execute(db, warrant_id=grant["warrant_id"], tool=tool, args=args, trace_id=trace_id)
    return {**done, "rule": grant.get("rule")} if done["ok"] else done
