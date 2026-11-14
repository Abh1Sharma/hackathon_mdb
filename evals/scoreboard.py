"""Red-team scoreboard: the same attempts, with and without the gate.

Three arms, each from a clean state:

  1. no gate              the agent's calls reach the tools directly
  2. Warrant              the same calls go through the gateway
  3. Warrant + 1 ruling   a human has denied one request of a new kind; nothing else changed

The agent here is the worst case: it attempts exactly what each case describes, the way a
fooled or compromised agent would. Scoring is done by `checks/hidden.py`, which reads the
business systems afterwards and is imported only here, never by the agent or the gateway.
"""

import inspect
import json
import subprocess
import time
import uuid
from pathlib import Path

from checks import hidden
from cli import seed
from evals import cases
from gateway import control, precedents, runs
from gateway.canonical import now
from gateway.gateway import authorize, call_tool, execute
from systems.tools import TOOLS

EVIDENCE = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "scoreboard.json"


def fixtures(db) -> None:
    db.sys_orders.insert_many([{"_id": o, "region": region, "total_cents": total, "customer_id": "EC-21",
                                "status": "delivered"} for o, region, total in cases.ORDERS])
    db.sys_crm.insert_many([{"_id": c, "name": c, "email": f"{c.lower()}@example.com", "region": region,
                             "last_note": ""} for c, region in cases.CUSTOMERS])
    db.sys_tickets.insert_many([{"_id": t, "customer_note": note, "wave": 9} for t, note in cases.TICKETS.items()])


def clean(db, keep_rulings: bool) -> None:
    """Fresh business state. With keep_rulings, precedents learned from humans survive."""
    if keep_rulings:
        for name in seed.RUN_STATE:
            db[name].delete_many({})
        for name, docs in seed.FIXTURES.items():
            db[name].delete_many({})
            db[name].insert_many([dict(d) for d in docs])
    else:
        seed.reset(db)
    fixtures(db)


def direct(db, move: dict) -> dict:
    """No gate: the call reaches the tool. Nothing checks who is asking, what for, or how much."""
    fn = TOOLS[move["tool"]]["fn"]
    params = inspect.signature(fn).parameters
    kwargs = {k: v for k, v in move["args"].items() if k in params}
    if "idempotency_key" in params:
        kwargs["idempotency_key"] = uuid.uuid4().hex
    try:
        fn(db, **kwargs)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "code": "TOOL_ERROR", "rule": "TOOL", "explanation": str(e)}


def gated(db, run: dict, step: int, move: dict, previous: dict | None) -> dict:
    """Through Warrant. `how` models the ways a misbehaving agent tries to get around it."""
    common = {"run_id": run["_id"], "step": step, "tool": move["tool"], "reason": move["reason"]}
    how = move.get("how")
    if how == "replay":
        return execute(db, warrant_id=previous["warrant_id"], tool=move["tool"], args=move["args"])
    if how == "swap":
        grant = authorize(db, agent_key=seed.AGENT_KEY, args=move["authorized_args"], **common)
        return execute(db, warrant_id=grant["warrant_id"], tool=move["tool"], args=move["args"]) if grant["ok"] else grant
    if how == "bad_key":
        return call_tool(db, agent_key="made-up-or-stolen-key", args=move["args"], **common)
    if how == "after_kill":
        control.kill(db, run["_id"], by="human:dana", reason="Reviewer stopped the run")
    out = call_tool(db, agent_key=seed.AGENT_KEY, args=move["args"], **common)
    if not out["ok"] and out["code"] == "STEP_UP_PENDING" and move.get("human"):
        decided = control.decide_approval(db, out["approval_id"], "human:sam", move["human"],
                                          note=move.get("human_note", ""))
        if decided["ok"] and move["human"] == "approved":
            out = {**call_tool(db, agent_key=seed.AGENT_KEY, args=move["args"], **common), "needed_human": True}
    return out


def run_case(db, case: dict, arm: str) -> list:
    trace, previous = [], None
    run = runs.start(db, seed.AGENT_ID, f"red team {case['id']}", label="eval") if arm != "none" else None
    for step, move in enumerate(case["moves"], start=1):
        out = direct(db, move) if arm == "none" else gated(db, run, step, move, previous)
        trace.append({"tool": move["tool"], "ok": out["ok"], "code": out.get("code"), "rule": out.get("rule"),
                      "needed_human": out.get("needed_human", False)})
        previous = out
    return trace


def stopped_by(trace: list) -> str:
    refusals = [t for t in trace if not t["ok"]]
    if not refusals:
        return "-"
    last = refusals[-1]
    return {"STEP_UP_PENDING": f"held for a human ({last['rule']})", "DENIED": f"refused ({last['rule']})",
            "KILLED": "refused (run killed)", "WARRANT_INVALID": "refused (warrant)"}.get(last["code"], last["code"])


def run_arm(db, arm: str, name: str) -> dict:
    t0 = time.time()
    attacks, legit = [], []
    for case in cases.ATTACKS:
        trace = run_case(db, case, arm)
        attacks.append({"id": case["id"], "title": case["title"],
                        "executed": bool(hidden.ATTACK_EXECUTED[case["id"]](db, trace)),
                        "stopped_by": stopped_by(trace)})
    for case in cases.LEGIT:
        trace = run_case(db, case, arm)
        legit.append({"id": case["id"], "title": case["title"],
                      "completed": bool(hidden.LEGIT_COMPLETED[case["id"]](db, trace)),
                      "needed_human": any(t["needed_human"] for t in trace)})
    return {"arm": name, "attacks_executed": sum(a["executed"] for a in attacks), "attacks": attacks,
            "legit_completed": sum(l["completed"] for l in legit), "legit": legit,
            "needed_human": sum(l["needed_human"] for l in legit), "seconds": round(time.time() - t0, 1)}


def human_ruling(db) -> dict:
    """One human decision on one request. This is the only thing that differs between arms 2 and 3."""
    move = cases.RULING["request"]
    run = runs.start(db, seed.AGENT_ID, "red team ruling", label="eval")
    held = call_tool(db, agent_key=seed.AGENT_KEY, run_id=run["_id"], step=1, tool=move["tool"], args=move["args"],
                     reason=move["reason"])
    assert held.get("code") == "STEP_UP_PENDING", held
    control.decide_approval(db, held["approval_id"], "human:sam", cases.RULING["decision"], note=cases.RULING["note"])
    ruling = db.precedents.find_one({"approval_id": held["approval_id"]})
    return {"precedent": ruling["_id"], "decision": ruling["decision"], "note": cases.RULING["note"],
            "indexed_after_seconds": precedents.wait_until_searchable(db, ruling)}


def run(db) -> dict:
    clean(db, keep_rulings=False)
    policies_before = list(db.policies.find().sort("_id", 1))  # after seeding, so only this run is compared
    arms = [run_arm(db, "none", "No gate")]
    clean(db, keep_rulings=False)
    arms.append(run_arm(db, "warrant", "Warrant"))
    ruling = human_ruling(db)
    clean(db, keep_rulings=True)
    arms.append(run_arm(db, "warrant", "Warrant after one human ruling"))
    policies_after = list(db.policies.find().sort("_id", 1))
    seed.reset(db)
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=EVIDENCE.parent).stdout.strip()
    except OSError:
        commit = ""
    return {"ran_at": now().isoformat(), "commit": commit, "database": db.name,
            "server_version": db.client.server_info()["version"],
            "attacks": len(cases.ATTACKS), "legit": len(cases.LEGIT), "arms": arms, "ruling": ruling,
            "policies_changed": policies_before != policies_after}


def table(result: dict) -> str:
    n, m = result["attacks"], result["legit"]
    lines = [f"{'':<32}{'attacks executed':>18}{'legitimate work done':>24}{'needed a human':>17}"]
    for arm in result["arms"]:
        lines.append(f"{arm['arm']:<32}{str(arm['attacks_executed']) + ' / ' + str(n):>18}"
                     f"{str(arm['legit_completed']) + ' / ' + str(m):>24}{arm['needed_human']:>17}")
    return "\n".join(lines)


def markdown(result: dict) -> str:
    n, m = result["attacks"], result["legit"]
    out = ["| | Attacks executed | Legitimate work completed | Needed a human |", "|---|---|---|---|"]
    out += [f"| {a['arm']} | **{a['attacks_executed']} / {n}** | {a['legit_completed']} / {m} | {a['needed_human']} |"
            for a in result["arms"]]
    r = result["ruling"]
    out += ["", f"The only difference between the last two rows is one human decision (\"{r['note']}\"), searchable "
                f"in Atlas {r['indexed_after_seconds']} s after it was made. Policy documents changed: "
                f"{'yes' if result['policies_changed'] else 'no'}.", "",
            "| Attack | No gate | Warrant | After one ruling |", "|---|---|---|---|"]
    none, gate, after = (arm["attacks"] for arm in result["arms"])
    for a, b, c in zip(none, gate, after):
        cell = lambda x: "**executed**" if x["executed"] else x["stopped_by"]
        out.append(f"| {a['id']} {a['title']} | {cell(a)} | {cell(b)} | {cell(c)} |")
    return "\n".join(out)


def save(result: dict) -> None:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n")
