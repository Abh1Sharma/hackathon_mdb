"""Policy evaluator against the seed policies. No database."""

import pytest

from cli import seed
from gateway.policies import evaluate

AGENT = {"id": seed.AGENT_ID, "class": "refund-agent", "regions": ["ON"]}
ON_ORDER = {"id": "O-1", "region": "ON", "total_cents": 150000}
BC_ORDER = {"id": "O-2", "region": "BC", "total_cents": 30000}


def ctx(tool, args=None, resource=None, history=None, precedent=None, identity=AGENT):
    return {"tool": tool, "args": args or {}, "resource": resource or {}, "history": history or {},
            "precedent": precedent or {}, "identity": identity}


def refund(amount, resource=ON_ORDER, **kw):
    return ctx("payments.refund", {"amount_cents": amount}, resource, **kw)


@pytest.mark.parametrize("name, context, decision, rule", [
    ("small refund", refund(8000), "allow", "P-002"),
    ("exactly $500", refund(50000), "allow", "P-002"),
    ("over $500 needs a human", refund(120000), "step_up", "P-003"),
    ("over $2,000", refund(250000, {"id": "O", "region": "ON", "total_cents": 900000}), "deny", "P-004"),
    ("more than the order total", refund(40000, {"id": "O", "region": "ON", "total_cents": 30000}), "deny", "DEFAULT-DENY"),
    ("out of region refund", refund(15000, BC_ORDER), "deny", "P-005"),
    ("out of region read", ctx("orders.get", {}, BC_ORDER), "deny", "P-005"),
    ("in region read", ctx("orders.get", {}, ON_ORDER), "allow", "P-001"),
    ("transfer is never allowed", ctx("payments.transfer", {"amount_cents": 500000}), "deny", "P-006"),
    ("unknown tool", ctx("db.drop_everything"), "deny", "DEFAULT-DENY"),
    ("order not found", refund(8000, {}), "deny", "DEFAULT-DENY"),
    ("run cap", refund(20000, history={"run_refund_total_after_cents": 310000}), "deny", "P-007"),
    ("resembles a denied precedent", refund(48000, precedent={"denied_match": True}), "step_up", "P-009"),
    ("email in region", ctx("email.send", {}, {"id": "C", "region": "ON"}), "allow", "P-011"),
])
def test_seed_policies(name, context, decision, rule):
    verdict = evaluate(seed.POLICIES, context)
    assert (verdict["decision"], verdict["rule"]) == (decision, rule), name


def test_at15_precedents_can_never_loosen_a_decision():
    """Whatever search says, a deterministic deny stays a deny and a step-up stays a step-up."""
    friendly = {"denied_match": False, "nearest_decision": "approved", "score": 0.99}
    assert evaluate(seed.POLICIES, refund(250000, {"id": "O", "region": "ON", "total_cents": 900000},
                                          precedent=friendly))["decision"] == "deny"
    assert evaluate(seed.POLICIES, refund(15000, BC_ORDER, precedent=friendly))["decision"] == "deny"
    assert evaluate(seed.POLICIES, refund(120000, precedent=friendly))["decision"] == "step_up"
    assert evaluate(seed.POLICIES, ctx("payments.transfer", precedent=friendly))["decision"] == "deny"
    assert not [p for p in seed.POLICIES if p["effect"] == "allow"
                and any(c["field"].startswith("precedent.") for c in p["when"])]


def test_decision_records_policy_versions():
    verdict = evaluate(seed.POLICIES, refund(8000))
    assert verdict["policy_refs"] == [{"id": "P-002", "version": 1}]


def test_retired_policies_are_ignored():
    retired = [{**p, "status": "retired"} if p["_id"] == "P-002" else p for p in seed.POLICIES]
    assert evaluate(retired, refund(8000))["decision"] == "deny"
