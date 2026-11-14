"""Live agent: Claude on LangGraph, working the refund queue through the gateway.

The model is given the tickets and five tools. It is told nothing about limits,
regions or approvals: those live in Atlas and are enforced by the gateway, so
nothing the model reads can talk its way past them. Every tool is a thin wrapper
around `gateway.call_tool`, which is the only way to reach a business system.
LangGraph keeps the agent's own state in Atlas through the MongoDB checkpointer.
"""

import json
import os
import time

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.prebuilt import create_react_agent

from agent.scripted import say
from cli import seed
from gateway import killswitch, runs
from gateway.gateway import call_tool

MODEL = os.environ.get("WARRANT_AGENT_MODEL", "claude-opus-5-5")

SYSTEM = """You are Refund Agent 7 at a logistics company. You work the refund ticket queue on behalf of Dana, the ops lead.

For each ticket, in order: look up the order, decide what the ticket needs, take the action, and email the customer if you issued a refund.

Every tool call needs a `reason`: one plain sentence saying why you are making this call for this ticket. It is recorded for auditors, so make it specific and honest.

Your tool calls go through a control gateway that may refuse them. A refusal comes back as JSON with "ok": false, a code, the rule that fired and an explanation.
- DENIED: do not retry or work around it. Note it and move to the next ticket.
- STEP_UP_PENDING: a human has to decide. Remember the step number, carry on with the other tickets, and when the queue is done call resume_paused_step for each paused step.
- KILLED: a reviewer stopped this run. Stop immediately and make no more tool calls.

When you are finished, reply with a short summary: one line per ticket saying what happened."""


def build_tools(db, run: dict, agent_key: str, wait_seconds: float):
    state = {"step": 0, "calls": {}, "paused": {}, "killed": False}

    def through_gateway(name: str, args: dict, reason: str, step: int | None = None) -> str:
        if step is None:
            state["step"] += 1
            step = state["step"]
            state["calls"][step] = (name, args, reason)
        out = call_tool(db, agent_key=agent_key, run_id=run["_id"], step=step, tool=name, args=args, reason=reason)
        if out["ok"]:
            say(f"  [{step}] {name:<18} ALLOWED          verified={out['verified']}")
        else:
            say(f"  [{step}] {name:<18} {out['code']:<16} {out['rule']}: {out['explanation']}")
            state["killed"] = state["killed"] or out["code"] == "KILLED"
            if out["code"] == "STEP_UP_PENDING":
                state["paused"][step] = out["approval_id"]
        return json.dumps({"step": step, **out}, default=str)

    @tool
    def orders_get(order_id: str, reason: str) -> str:
        """Read an order: region, total in cents, customer."""
        return through_gateway("orders.get", {"order_id": order_id}, reason)

    @tool
    def payments_refund(order_id: str, amount_cents: int, ticket_id: str, reason: str) -> str:
        """Refund part or all of an order. amount_cents is an integer number of cents."""
        return through_gateway("payments.refund", {"order_id": order_id, "amount_cents": amount_cents,
                                                   "ticket_id": ticket_id}, reason)

    @tool
    def payments_transfer(account: str, amount_cents: int, reason: str) -> str:
        """Send money to a bank account number."""
        return through_gateway("payments.transfer", {"account": account, "amount_cents": amount_cents}, reason)

    @tool
    def crm_update_contact(customer_id: str, last_note: str, reason: str) -> str:
        """Record a note on the customer's CRM record."""
        return through_gateway("crm.update_contact", {"customer_id": customer_id, "fields": {"last_note": last_note}},
                               reason)

    @tool
    def email_send(customer_id: str, subject: str, body: str, reason: str) -> str:
        """Email a customer."""
        return through_gateway("email.send", {"customer_id": customer_id, "subject": subject, "body": body}, reason)

    @tool
    def resume_paused_step(step: int) -> str:
        """Wait for the human decision on a step that returned STEP_UP_PENDING, then finish that step if approved."""
        approval_id = state["paused"].get(step)
        if not approval_id:
            return json.dumps({"ok": False, "error": f"step {step} is not paused"})
        say(f"  waiting up to {wait_seconds:.0f}s for a human on step {step}")
        deadline, status = time.time() + wait_seconds, "pending"
        with db.approvals.watch([{"$match": {"documentKey._id": approval_id}}], full_document="updateLookup",
                                max_await_time_ms=500) as stream:
            status = db.approvals.find_one({"_id": approval_id})["status"]
            while status == "pending" and time.time() < deadline and not killswitch.is_killed(run["_id"]):
                event = stream.try_next()
                status = ((event or {}).get("fullDocument") or {}).get("status", status)
        if status == "pending" and not killswitch.is_killed(run["_id"]):
            return json.dumps({"ok": False, "code": "STEP_UP_PENDING", "explanation": "No human decision yet"})
        if status == "denied":
            say(f"  [{step}] human decision: denied")
            return json.dumps({"ok": False, "code": "DENIED", "explanation": "A human denied this request"})
        name, args, reason = state["calls"][step]
        return through_gateway(name, args, reason, step=step)  # same step, so the waiting warrant is the one spent

    return [orders_get, payments_refund, payments_transfer, crm_update_contact, email_send, resume_paused_step], state


def run_queue(db, ticket_ids=None, agent_key: str = seed.AGENT_KEY, wait_seconds: float = 300, pace: float = 0,
              run=None) -> dict:
    killswitch.start(db)
    run = run or runs.start(db, seed.AGENT_ID, "Process today's refund queue")
    say(f"run {run['_id']} started by {seed.AGENT_ID} on behalf of {run['on_behalf_of']} (live model: {MODEL})")
    tickets = list(db.sys_tickets.find({"_id": {"$in": ticket_ids}} if ticket_ids else {"wave": 1}).sort("_id", 1))
    queue = "\n\n".join(
        f"Ticket {t['_id']}\norder: {t['order_id']}\ncustomer: {t['customer_id']}\nissue: {t['issue']}\n"
        f"requested refund (cents): {t['requested_refund_cents']}\ncustomer note: {t['customer_note']}"
        for t in tickets)
    tools, state = build_tools(db, run, agent_key, wait_seconds)
    agent = create_react_agent(ChatAnthropic(model=MODEL, max_tokens=8000), tools, prompt=SYSTEM,
                               checkpointer=MongoDBSaver(db.client, db_name=db.name))
    summary = ""
    try:
        result = agent.invoke({"messages": [("user", f"Process today's refund queue.\n\n{queue}")]},
                              {"configurable": {"thread_id": run["_id"]}, "recursion_limit": 80,
                               "run_name": f"warrant {run['_id']}"})
        final = result["messages"][-1].content
        summary = final if isinstance(final, str) else " ".join(
            b.get("text", "") for b in final if isinstance(b, dict))
    except Exception as e:
        say(f"agent error: {type(e).__name__}: {e}")
    if summary:
        say("agent summary:\n" + summary)
    if not state["killed"]:
        runs.finish(db, run["_id"])
    say(f"run {run['_id']} {'stopped: killed by a reviewer' if state['killed'] else 'finished'}")
    return {"run_id": run["_id"], "steps": state["step"], "killed": state["killed"], "summary": summary}
