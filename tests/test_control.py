"""M2 and M3 acceptance tests: kill, rollback, step-up approval, reconstruction."""

import time

from agent import scripted
from cli import seed
from gateway import control, ledger, runs
from gateway.gateway import authorize, call_tool, execute

KEY = seed.AGENT_KEY
T1 = {"order_id": "O-1001", "amount_cents": 8000, "ticket_id": "T1"}
T2 = {"order_id": "O-1002", "amount_cents": 24000, "ticket_id": "T2"}


def call(db, run, step, tool, args, reason="Late delivery credit under SLA"):
    return call_tool(db, agent_key=KEY, run_id=run["_id"], step=step, tool=tool, args=args, reason=reason)


def test_at06_kill_refuses_the_next_call_and_revokes_unused_warrants(db):
    run = runs.start(db, seed.AGENT_ID, "test")
    assert call(db, run, 1, "payments.refund", T1)["ok"]
    unused = authorize(db, agent_key=KEY, run_id=run["_id"], step=2, tool="payments.refund", args=T2, reason="damage")
    assert unused["ok"]

    t0 = time.time()
    killed = control.kill(db, run["_id"], by="human:dana", reason="agent is misbehaving")
    after = call(db, run, 3, "orders.get", {"order_id": "O-1003"}, "look up")
    assert time.time() - t0 < 2
    assert after["code"] == "KILLED" and "human:dana" in after["explanation"]
    assert killed["revoked"] == 1
    assert db.warrants.find_one({"_id": unused["warrant_id"]})["status"] == "revoked"
    spent = execute(db, warrant_id=unused["warrant_id"], tool="payments.refund", args=T2)
    assert spent["code"] == "WARRANT_INVALID" and "revoked" in spent["explanation"]
    assert db.sys_payments.count_documents({"type": "refund"}) == 1
    types = [e["type"] for e in ledger.entries(db, run["_id"])]
    assert "kill" in types and types.count("violation") == 2
    assert ledger.verify(db, run["_id"])["ok"]


def test_at07_rollback_compensates_reversible_steps_and_reports_the_rest(db):
    run = runs.start(db, seed.AGENT_ID, "test")
    before = db.sys_crm.find_one({"_id": "C-01"})
    assert call(db, run, 1, "payments.refund", T1)["ok"]
    assert call(db, run, 2, "payments.refund", T2, "One carton damaged, photo attached")["ok"]
    assert call(db, run, 3, "crm.update_contact",
                {"customer_id": "C-01", "fields": {"last_note": "Refunded $80 for late delivery"}},
                "Record the refund on the customer")["ok"]
    assert call(db, run, 4, "email.send", {"customer_id": "C-01", "subject": "Your refund", "body": "Refunded $80"},
                "Tell the customer")["ok"]
    assert control.rollback(db, run["_id"], by="human:dana")["ok"] is False  # must be stopped first
    control.kill(db, run["_id"], by="human:dana", reason="undo this run")

    report = control.rollback(db, run["_id"], by="human:dana")
    assert [u["tool"] for u in report["undone"]] == ["crm.update_contact", "payments.refund", "payments.refund"]
    assert [n["tool"] for n in report["not_undone"]] == ["email.send"]
    assert "cannot undo" in report["not_undone"][0]["follow_up"]
    assert db.sys_payments.count_documents({"type": "reversal"}) == 2
    assert {p["status"] for p in db.sys_payments.find({"type": "refund"})} == {"reversed"}
    assert db.sys_crm.find_one({"_id": "C-01"}) == before
    assert db.sys_outbox.count_documents({}) == 1  # the email really was sent, and we say so
    assert db.runs.find_one({"_id": run["_id"]})["status"] == "rolled_back"
    assert [e["type"] for e in ledger.entries(db, run["_id"])].count("rollback") == 4
    assert ledger.verify(db, run["_id"])["ok"]
    assert control.rollback(db, run["_id"], by="human:dana")["already"] is True


def test_at08_step_up_pauses_until_a_human_approves(db):
    out = scripted.run_queue(db, ["T3"])
    paused = out["outcomes"]["T3"]
    assert paused["code"] == "STEP_UP_PENDING" and db.sys_payments.count_documents({}) == 0
    args = {"order_id": "O-1003", "amount_cents": 120000, "ticket_id": "T3"}
    run = {"_id": out["run_id"]}
    db.runs.update_one(run, {"$set": {"status": "running"}})
    assert call(db, run, paused["step"], "payments.refund", args)["code"] == "STEP_UP_PENDING"  # still waiting

    assert control.decide_approval(db, paused["approval_id"], "human:dana", "approved")["ok"] is False  # no authority
    decided = control.decide_approval(db, paused["approval_id"], "human:sam", "approved", channel="web",
                                      note="Carrier damage report is on file.")
    assert decided["ok"] and decided["warrant_id"]
    done = call(db, run, paused["step"], "payments.refund", args, "Goods damaged in transit")
    assert done["ok"] and done["verified"] is True
    assert db.sys_payments.find_one({"type": "refund"})["amount_cents"] == 120000

    approval = [e for e in ledger.entries(db, out["run_id"]) if e["type"] == "approval"][0]
    assert approval["actor"] == "human:sam" and approval["payload"]["channel"] == "web"
    assert len(approval["precedent_refs"]) == 3  # what the approver was shown is on the record
    learned = db.precedents.find_one({"approval_id": paused["approval_id"]})
    assert learned["decision"] == "approved" and learned["seeded"] is False
    assert learned["outcome_note"] == "Carrier damage report is on file."
    assert control.decide_approval(db, paused["approval_id"], "human:sam", "denied")["ok"] is False  # decided once


def test_step_up_denied_by_a_human_stays_denied(db):
    out = scripted.run_queue(db, ["T3"])
    paused = out["outcomes"]["T3"]
    db.runs.update_one({"_id": out["run_id"]}, {"$set": {"status": "running"}})
    assert control.decide_approval(db, paused["approval_id"], "human:sam", "denied", note="No evidence")["ok"]
    again = call(db, {"_id": out["run_id"]}, paused["step"], "payments.refund",
                 {"order_id": "O-1003", "amount_cents": 120000, "ticket_id": "T3"})
    assert again["code"] == "DENIED" and db.sys_payments.count_documents({}) == 0


def test_at11_reconstruction_lists_every_step(db):
    out = scripted.run_queue(db, ["T1", "T4", "T5"])
    account = control.reconstruct(db, out["run_id"])
    assert account["run"]["agent_id"] == seed.AGENT_ID and account["chain"]["ok"]
    assert [s["step"] for s in account["steps"]] == list(range(1, out["steps"] + 1))
    for s in account["steps"]:
        assert s["who"] == seed.AGENT_ID and s["on_behalf_of"] == "human:dana"
        assert s["tool"] and s["why"] and s["decision"] in ("allow", "deny", "step_up")
    refund = next(s for s in account["steps"] if s["tool"] == "payments.refund")
    assert refund["policies"] == ["P-002 v1"] and refund["result"] == "executed" and refund["verified"] is True
    transfer = next(s for s in account["steps"] if s["tool"] == "payments.transfer")
    assert transfer["decision"] == "deny" and transfer["result"] == "not executed" and "P-006 v1" in transfer["policies"]


def test_voice_decision_needs_the_challenge_code(db):
    out = scripted.run_queue(db, ["T3"])
    paused = out["outcomes"]["T3"]
    db.runs.update_one({"_id": out["run_id"]}, {"$set": {"status": "running"}})
    code = db.approvals.find_one({"_id": paused["approval_id"]})["challenge"]
    assert len(code) == 3 and code.isdigit()
    wrong = "000" if code != "000" else "111"
    refused = control.decide_approval(db, paused["approval_id"], "human:sam", "approved", channel="voice",
                                      note="Carrier confirmed it", evidence={"challenge_code": wrong})
    assert refused == {"ok": False, "error": "challenge code did not match"}
    assert db.approvals.find_one({"_id": paused["approval_id"]})["status"] == "pending"
    spoken = control.decide_approval(db, paused["approval_id"], "human:sam", "approved", channel="voice",
                                     note="Carrier confirmed the damage", evidence={
                                         "challenge_code": " ".join(code), "conversation_id": "conv_test",
                                         "transcript": "Desk: Do you approve? | You: Approve, carrier confirmed it"})
    assert spoken["ok"]
    entry = [e for e in ledger.entries(db, out["run_id"]) if e["type"] == "approval"][0]
    assert entry["payload"]["channel"] == "voice" and entry["payload"]["evidence"]["conversation_id"] == "conv_test"
    assert entry["reason"] == "Carrier confirmed the damage"
    learned = db.precedents.find_one({"approval_id": paused["approval_id"]})
    assert learned["channel"] == "voice" and learned["outcome_note"] == "Carrier confirmed the damage"
