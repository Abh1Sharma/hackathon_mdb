"""M1 acceptance tests, against a freshly seeded sandbox database."""

from agent import scripted
from cli import seed
from gateway import ledger, runs
from gateway.gateway import authorize, call_tool, execute

KEY = seed.AGENT_KEY
T1 = {"order_id": "O-1001", "amount_cents": 8000, "ticket_id": "T1"}


def step_entries(db, run_id, step):
    return [e for e in ledger.entries(db, run_id) if e.get("step") == step]


def test_at01_allowed_refund_is_executed_verified_and_recorded(db):
    out = scripted.run_queue(db, ["T1"])
    refunds = list(db.sys_payments.find({"type": "refund"}))
    assert [r["amount_cents"] for r in refunds] == [8000]
    step = out["outcomes"]["T1"]["step"]
    decision, execution, verification = step_entries(db, out["run_id"], step)
    assert (decision["type"], decision["decision"]) == ("decision", "allow")
    assert {"id": "P-002", "version": 1} in decision["policy_refs"]
    assert decision["actor"] == seed.AGENT_ID and decision["on_behalf_of"] == "human:dana"
    assert execution["type"] == "execution" and execution["payload"]["ok"] is True
    assert verification["type"] == "verification" and verification["payload"]["verified"] is True
    assert ledger.verify(db, out["run_id"])["ok"]


def test_at02_out_of_region_is_denied_before_it_runs(db):
    out = scripted.run_queue(db, ["T4"])
    assert db.sys_payments.count_documents({}) == 0
    denies = [e for e in ledger.entries(db, out["run_id"]) if e.get("decision") == "deny"]
    assert denies and {"id": "P-005", "version": 1} in denies[0]["policy_refs"]
    assert out["outcomes"]["T4"]["code"] == "DENIED" and out["outcomes"]["T4"]["rule"] == "P-005"


def test_at03_injected_transfer_is_attempted_and_denied(db):
    out = scripted.run_queue(db, ["T5"])
    assert db.sys_payments.count_documents({"type": "transfer"}) == 0
    attempt = [e for e in ledger.entries(db, out["run_id"]) if e.get("tool") == "payments.transfer"]
    assert len(attempt) == 1 and attempt[0]["decision"] == "deny"
    assert {"id": "P-006", "version": 1} in attempt[0]["policy_refs"]
    assert "transfer $5,000" in attempt[0]["reason"]  # what the agent said it was doing is on the record


def test_at04_a_used_warrant_cannot_be_replayed(db):
    run = runs.start(db, seed.AGENT_ID, "test")
    first = call_tool(db, agent_key=KEY, run_id=run["_id"], step=1, tool="payments.refund", args=T1, reason="late")
    assert first["ok"]
    again = execute(db, warrant_id=first["warrant_id"], tool="payments.refund", args=T1)
    assert again["code"] == "WARRANT_INVALID" and "replay" in again["explanation"]
    assert db.sys_payments.count_documents({"type": "refund"}) == 1
    violations = [e for e in ledger.entries(db, run["_id"]) if e["type"] == "violation"]
    assert violations and "replay" in violations[0]["payload"]["why"]


def test_at05_a_warrant_is_bound_to_its_arguments(db):
    run = runs.start(db, seed.AGENT_ID, "test")
    grant = authorize(db, agent_key=KEY, run_id=run["_id"], step=1, tool="payments.refund", args=T1, reason="late")
    assert grant["ok"]
    bigger = execute(db, warrant_id=grant["warrant_id"], tool="payments.refund", args={**T1, "amount_cents": 80000})
    assert bigger["code"] == "WARRANT_INVALID" and "digest mismatch" in bigger["explanation"]
    assert db.sys_payments.count_documents({}) == 0
    assert db.warrants.find_one({"_id": grant["warrant_id"]})["status"] == "issued"  # still unspent


def test_fr01_fr02_identity_and_reason_are_required(db):
    run = runs.start(db, seed.AGENT_ID, "test")
    nobody = call_tool(db, agent_key="wrong-key", run_id=run["_id"], step=1, tool="orders.get",
                       args={"order_id": "O-1001"}, reason="look")
    assert nobody["code"] == "DENIED" and nobody["rule"] == "IDENTITY"
    silent = call_tool(db, agent_key=KEY, run_id=run["_id"], step=1, tool="orders.get",
                       args={"order_id": "O-1001"}, reason="  ")
    assert silent["code"] == "DENIED" and silent["rule"] == "FR-02"
    db.identities.update_one({"_id": seed.AGENT_ID}, {"$set": {"status": "suspended"}})
    suspended = call_tool(db, agent_key=KEY, run_id=run["_id"], step=2, tool="orders.get",
                          args={"order_id": "O-1001"}, reason="look")
    assert suspended["rule"] == "IDENTITY"


def test_at12_run_cap_is_computed_from_the_ledger(db):
    db.sys_orders.insert_one({"_id": "O-BIG", "region": "ON", "total_cents": 5000000, "customer_id": "C-01"})
    run = runs.start(db, seed.AGENT_ID, "test")
    for step, amount in enumerate([50000] * 5 + [40000], start=1):  # $2,900 in total
        out = call_tool(db, agent_key=KEY, run_id=run["_id"], step=step, tool="payments.refund",
                        args={"order_id": "O-BIG", "amount_cents": amount}, reason="Late delivery credit under SLA")
        assert out["ok"], out
    over = call_tool(db, agent_key=KEY, run_id=run["_id"], step=7, tool="payments.refund",
                     args={"order_id": "O-BIG", "amount_cents": 20000}, reason="Late delivery credit under SLA")
    assert over["code"] == "DENIED" and over["rule"] == "P-007"
    assert sum(p["amount_cents"] for p in db.sys_payments.find()) == 290000


def test_tampering_with_the_ledger_is_detected(db):
    out = scripted.run_queue(db, ["T1"])
    assert ledger.verify(db, out["run_id"])["ok"]
    db.ledger.update_one({"run_id": out["run_id"], "seq": 2}, {"$set": {"reason": "nothing to see here"}})
    broken = ledger.verify(db, out["run_id"])
    assert broken == {"ok": False, "broken_at": 2, "why": "content does not match its hash"}
