"""Run control: kill, approvals, rollback and reconstruction.

These are the reviewer's and approver's actions. Each one is recorded in the
same ledger as the agent's actions, in the same transaction as its effect.
"""

from gateway import ledger
from gateway.canonical import digest, now
from gateway.gateway import WARRANT_TTL
from systems import tools


def kill(db, run_id: str, by: str, reason: str) -> dict:
    """Stop a run. Its next tool call is refused and every unused warrant is revoked."""
    def tx(session):
        run = db.runs.find_one({"_id": run_id}, session=session)
        if not run:
            raise ValueError(f"no run {run_id}")
        if run["status"] in ("killed", "rolled_back"):
            return {"ok": True, "already": True, "revoked": 0}
        db.runs.update_one({"_id": run_id}, {"$set": {
            "status": "killed", "ended_at": now(), "kill": {"by": by, "at": now(), "reason": reason}}},
            session=session)
        revoked = db.warrants.update_many({"run_id": run_id, "status": "issued"},
                                          {"$set": {"status": "revoked"}}, session=session).modified_count
        expired = db.approvals.update_many({"run_id": run_id, "status": "pending"},
                                           {"$set": {"status": "expired", "decided_at": now()}},
                                           session=session).modified_count
        ledger.append(db, session, run_id, {"type": "kill", "actor": by, "reason": reason, "payload": {
            "warrants_revoked": revoked, "approvals_cancelled": expired}})
        return {"ok": True, "revoked": revoked, "approvals_cancelled": expired}

    with db.client.start_session() as session:
        return session.with_transaction(tx)


def decide_approval(db, approval_id: str, approver: str, decision: str, channel: str = "web",
                    note: str = "", evidence: dict | None = None) -> dict:
    """A human decides a step-up. Approval issues the warrant. Either way it becomes a precedent."""
    if decision not in ("approved", "denied"):
        raise ValueError("decision must be 'approved' or 'denied'")
    human = db.identities.find_one({"_id": approver, "kind": "human", "status": "active"})
    if not human or "approve.refund" not in human.get("scopes", []):
        return {"ok": False, "error": f"{approver} is not allowed to approve"}

    def tx(session):
        approval = db.approvals.find_one({"_id": approval_id}, session=session)
        if not approval:
            return {"ok": False, "error": "no such approval"}
        if approval["status"] != "pending":
            return {"ok": False, "error": f"already {approval['status']}"}
        run = db.runs.find_one({"_id": approval["run_id"]}, session=session)
        if run["status"] != "running":
            return {"ok": False, "error": f"run is {run['status']}"}
        t = now()
        if approval["expires_at"] <= t:
            db.approvals.update_one({"_id": approval_id}, {"$set": {"status": "expired"}}, session=session)
            return {"ok": False, "error": "approval request expired"}
        if channel == "voice":
            spoken = "".join(ch for ch in str((evidence or {}).get("challenge_code", "")) if ch.isdigit())
            if spoken != approval.get("challenge"):
                return {"ok": False, "error": "challenge code did not match"}
        request = approval["request"]
        db.approvals.update_one({"_id": approval_id}, {"$set": {
            "status": decision, "approver_id": approver, "channel": channel, "note": note,
            "evidence": evidence or {}, "decided_at": t}}, session=session)
        warrant_id = None
        if decision == "approved":
            warrant_id = f"w_{approval['run_id']}_{approval['step']}"
            db.warrants.insert_one({
                "_id": warrant_id, "run_id": approval["run_id"], "step": approval["step"],
                "agent_id": request["agent_id"], "on_behalf_of": request["on_behalf_of"],
                "tool": request["tool"], "args_digest": request["args_digest"],
                "policy_refs": request["policy_refs"], "status": "issued", "issued_at": t,
                "expires_at": t + WARRANT_TTL, "approval_id": approval_id}, session=session)
        shown = [{"id": p["_id"], "decision": p["decision"],
                  "score": round(p.get("rerank_score", p.get("fusion_score", 0.0)), 4)}
                 for p in approval.get("precedents", [])]
        ledger.append(db, session, approval["run_id"], {
            "type": "approval", "actor": approver, "on_behalf_of": request["on_behalf_of"],
            "step": approval["step"], "tool": request["tool"], "reason": note or None,
            "warrant_id": warrant_id, "policy_refs": request["policy_refs"], "precedent_refs": shown or None,
            "payload": {"approval_id": approval_id, "decision": decision, "channel": channel,
                        "rule": request["rule"], "evidence": evidence or {}}})
        return {"ok": True, "decision": decision, "warrant_id": warrant_id, "approval": approval}

    with db.client.start_session() as session:
        out = session.with_transaction(tx)
    if out["ok"]:
        # The human's decision and their own words become case law for the next similar request.
        request = out.pop("approval")["request"]
        db.precedents.insert_one({
            "_id": f"PR-{approval_id}", "tool": request["tool"], "amount_cents": request["args"].get("amount_cents"),
            "region": request["resource"].get("region"), "reason": request["reason"], "note": request["note"],
            "summary": request["summary"], "decision": decision, "decided_by": approver, "channel": channel,
            "outcome_note": note, "approval_id": approval_id, "seeded": False, "created_at": now()})
    return out


def rollback(db, run_id: str, by: str) -> dict:
    """Undo a run. Reversible steps are compensated newest first. Irreversible ones are reported honestly."""
    run = db.runs.find_one({"_id": run_id})
    if not run:
        raise ValueError(f"no run {run_id}")
    if run["status"] == "rolled_back":
        return {"ok": True, "already": True, "undone": [], "not_undone": []}
    if run["status"] == "running":
        return {"ok": False, "error": "kill the run before rolling it back"}
    entries = ledger.entries(db, run_id)
    done = {e["payload"]["undoes_seq"] for e in entries if e["type"] == "rollback" and "undoes_seq" in e["payload"]}
    undone, not_undone = [], []
    for e in reversed(entries):
        if e["type"] != "execution" or not e["payload"]["ok"] or e["seq"] in done:
            continue
        reversible = e["payload"].get("reversible")
        if reversible is None:
            continue  # read only
        item = {"seq": e["seq"], "step": e["step"], "tool": e["tool"]}
        payload = {"undoes_seq": e["seq"], "undone": False}
        if reversible and e["tool"] == "payments.refund":
            reversal = tools.payments_reverse(db, e["payload"]["result_id"], digest({"undo": e["_id"]}))
            payload.update(undone=True, compensation="reversal entry", result_id=reversal["_id"],
                           amount_cents=reversal["amount_cents"])
        elif reversible and e["tool"] == "crm.update_contact":
            before = e["payload"]["before_image"]
            db.sys_crm.replace_one({"_id": before["_id"]}, before)
            payload.update(undone=True, compensation="restored the captured before-image", result_id=before["_id"])
        else:
            payload.update(compensation="none possible", follow_up="cannot undo: already sent, follow-up needed")
        ledger.append_tx(db, run_id, {"type": "rollback", "actor": by, "on_behalf_of": e.get("on_behalf_of"),
                                      "step": e["step"], "tool": e["tool"], "payload": payload})
        (undone if payload["undone"] else not_undone).append({**item, **payload})
    db.runs.update_one({"_id": run_id}, {"$set": {"status": "rolled_back", "rolled_back_by": by,
                                                  "rolled_back_at": now()}})
    return {"ok": True, "undone": undone, "not_undone": not_undone}


def reconstruct(db, run_id: str) -> dict:
    """The ordered, human-readable account of a run: who, on whose behalf, what, why, which policy, result."""
    run = db.runs.find_one({"_id": run_id})
    if not run:
        raise ValueError(f"no run {run_id}")
    steps, controls = {}, []
    for e in ledger.entries(db, run_id):
        if e["type"] == "kill":
            controls.append({"seq": e["seq"], "ts": e["ts"], "type": "kill", "by": e["actor"],
                             "reason": e.get("reason"), **e["payload"]})
            continue
        s = steps.setdefault(e["step"], {"step": e["step"], "tool": e.get("tool"), "who": None,
                                         "on_behalf_of": None, "why": None, "decision": None, "policies": [],
                                         "precedents": [], "result": "not executed", "verified": None,
                                         "events": []})
        s["events"].append({"seq": e["seq"], "type": e["type"], "ts": e["ts"]})
        payload = e["payload"]
        if e["type"] == "decision":
            s.update(who=e["actor"], on_behalf_of=e.get("on_behalf_of"), why=e.get("reason"),
                     decision=e["decision"], rule=payload["rule"], args=payload["args"],
                     policies=[f"{p['id']} v{p['version']}" for p in e.get("policy_refs", [])],
                     precedents=e.get("precedent_refs", []), trace_id=e.get("trace_id"))
        elif e["type"] == "approval":
            s["approval"] = {"by": e["actor"], "decision": payload["decision"], "channel": payload["channel"],
                             "note": e.get("reason"), "precedents_shown": e.get("precedent_refs", [])}
        elif e["type"] == "execution":
            s["result"] = "executed" if payload["ok"] else f"failed: {payload['error']}"
            s["result_id"] = payload.get("result_id")
        elif e["type"] == "verification":
            s["verified"], s["verification"] = payload["verified"], payload["detail"]
        elif e["type"] == "rollback":
            s["rollback"] = {"by": e["actor"], "undone": payload["undone"],
                             "how": payload.get("compensation"), "follow_up": payload.get("follow_up")}
        elif e["type"] == "violation":
            s.setdefault("violations", []).append({"code": payload["code"], "why": payload.get("why")})
            if s["who"] is None:
                s.update(who=e["actor"], on_behalf_of=e.get("on_behalf_of"), why=e.get("reason"),
                         result=f"refused: {payload['code']}")
    return {"run": {k: run.get(k) for k in ("_id", "agent_id", "on_behalf_of", "goal", "status", "started_at",
                                             "ended_at", "kill")},
            "steps": [steps[k] for k in sorted(steps)], "controls": controls,
            "chain": ledger.verify(db, run_id)}
