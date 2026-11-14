"""AT-16: precedent retrieval is one aggregation ($rankFusion of vector and text, then $rerank)."""

import time

import pytest

from cli import seed
from gateway import precedents, schema

ORDERS = {o["_id"]: o for o in seed.ORDERS}


def ticket_text(ticket_id):
    t = next(t for t in seed.TICKETS if t["_id"] == ticket_id)
    return precedents.summary("payments.refund", t["requested_refund_cents"], ORDERS[t["order_id"]]["region"],
                              t["issue"], t["customer_note"])


@pytest.fixture
def indexed(db):
    """Search indexes build and embed in the background. Wait until both answer queries."""
    deadline = time.time() + 240
    while time.time() < deadline:
        status = schema.search_status(db)
        if status and all(v == "READY" for v in status.values()):
            if len(precedents.search(db, "refund for damaged goods", k=3)["hits"]) == 3:
                return db
        time.sleep(5)
    pytest.fail(f"search indexes not ready: {schema.search_status(db)}")


def test_at16_pipeline_shape():
    stages = precedents.pipeline("x", tool="payments.refund")
    assert list(stages[0]) == ["$rankFusion"]
    fused = stages[0]["$rankFusion"]["input"]["pipelines"]
    assert "$vectorSearch" in fused["semantic"][0] and "$search" in fused["lexical"][0]
    assert fused["semantic"][0]["$vectorSearch"]["query"] == {"text": "x"}  # Atlas embeds the query
    assert any("$rerank" in s for s in stages)


def test_at16_override_request_matches_a_denied_precedent(indexed):
    result = precedents.search(indexed, ticket_text("T6"), tool="payments.refund")
    top = result["hits"][0]
    assert top["decision"] == "denied" and top["_id"] in {"PR-002", "PR-013"}
    assert "fusion_score" in top
    assert precedents.facts(result, min_score=0.7)["denied_match"] is True


def test_at16_ordinary_requests_match_approved_precedents(indexed):
    for ticket in ("T1", "T2", "T3"):
        result = precedents.search(indexed, ticket_text(ticket), tool="payments.refund")
        assert result["hits"][0]["decision"] == "approved", ticket
        assert precedents.facts(result, min_score=0.7)["denied_match"] is False


def test_tool_filter_is_applied(indexed):
    hits = precedents.search(indexed, ticket_text("T6"), tool="payments.refund", k=5)["hits"]
    assert {h["tool"] for h in hits} == {"payments.refund"}


def test_at14_override_refund_is_raised_to_step_up_by_precedent(indexed):
    from agent import scripted
    from gateway import ledger

    out = scripted.run_queue(indexed, ["T6"])
    result = out["outcomes"]["T6"]
    assert result["code"] == "STEP_UP_PENDING" and result["rule"] == "P-009"
    assert indexed.sys_payments.count_documents({}) == 0
    decision = [e for e in ledger.entries(indexed, out["run_id"]) if e.get("tool") == "payments.refund"][0]
    assert decision["decision"] == "step_up" and {"id": "P-009", "version": 1} in decision["policy_refs"]
    assert decision["precedent_refs"][0]["decision"] == "denied"
    assert decision["payload"]["precedent"]["score"] >= decision["payload"]["precedent"]["min_score"]

    # The same call with the precedent policy retired is an ordinary allowed refund (P-002).
    from cli import seed
    seed.reset(indexed)
    indexed.policies.update_one({"_id": "P-009"}, {"$set": {"status": "retired"}})
    assert scripted.run_queue(indexed, ["T6"])["outcomes"]["T6"]["ok"] is True


def test_at13_step_up_request_carries_precedents(indexed):
    from agent import scripted
    from gateway import ledger

    out = scripted.run_queue(indexed, ["T3"])
    assert out["outcomes"]["T3"]["code"] == "STEP_UP_PENDING" and out["outcomes"]["T3"]["rule"] == "P-003"
    approval = indexed.approvals.find_one({"_id": out["outcomes"]["T3"]["approval_id"]})
    assert approval["status"] == "pending" and len(approval["precedents"]) == 3
    assert approval["precedents"][0]["decision"] == "approved" and "rerank_score" in approval["precedents"][0]
    decision = [e for e in ledger.entries(indexed, out["run_id"]) if e.get("decision") == "step_up"][0]
    assert [r["id"] for r in decision["precedent_refs"]] == [p["_id"] for p in approval["precedents"]]


def test_at17_a_human_ruling_tightens_the_next_similar_request(indexed):
    """The learning loop. Same ticket, before and after a human ruled on a similar one. No rule is edited."""
    from agent import scripted
    from cli import seed
    from gateway import control, ledger

    before = scripted.run_queue(indexed, ["T8"])["outcomes"]["T8"]
    assert before["ok"] is True  # $300, in region, under every limit, nothing like it was ever refused

    seed.reset(indexed)
    policies_before = list(indexed.policies.find().sort("_id", 1))
    first = scripted.run_queue(indexed, ["T7"])
    paused = first["outcomes"]["T7"]
    assert paused["code"] == "STEP_UP_PENDING"
    indexed.runs.update_one({"_id": first["run_id"]}, {"$set": {"status": "running"}})
    words = "Refunds only go back to the original payment method."
    assert control.decide_approval(indexed, paused["approval_id"], "human:sam", "denied", note=words)["ok"]
    ruling = indexed.precedents.find_one({"approval_id": paused["approval_id"]})
    assert precedents.wait_until_searchable(indexed, ruling) is not None  # Atlas embeds it asynchronously

    later = scripted.run_queue(indexed, ["T8"])  # a different run: the knowledge lives in Atlas, not in the agent
    after = later["outcomes"]["T8"]
    assert after["code"] == "STEP_UP_PENDING" and after["rule"] == "P-009"
    assert indexed.sys_payments.count_documents({}) == 0
    decision = [e for e in ledger.entries(indexed, later["run_id"]) if e.get("tool") == "payments.refund"][0]
    assert decision["precedent_refs"][0]["id"] == ruling["_id"]
    card = indexed.approvals.find_one({"_id": after["approval_id"]})["precedents"][0]
    assert card["outcome_note"] == words and card["seeded"] is False  # the approver sees the human's own words
    assert list(indexed.policies.find().sort("_id", 1)) == policies_before
