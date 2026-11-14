"""Warrant CLI. Run through the ./warrant wrapper so .env is loaded."""

import argparse
import time

from cli import seed
from gateway import schema
from gateway.db import get_db


def cmd_setup(args):
    db = get_db()
    for note in schema.setup(db):
        print("note:", note)
    seed.reset(db)
    print(f"setup done on database '{db.name}'. search indexes: {schema.search_status(db)}")


def cmd_reset(args):
    db = get_db()
    t0 = time.time()
    seed.reset(db)
    print(f"reset in {time.time() - t0:.1f}s. search indexes: {schema.search_status(db)}")


def cmd_precedents(args):
    from gateway import precedents
    result = precedents.search(get_db(), args.text, tool=args.tool, k=args.k)
    print(f"mode: {result['mode']}  ({result['ms']} ms, one aggregation: $rankFusion -> $rerank)")
    for h in result["hits"]:
        rerank = f"{h['rerank_score']:.3f}" if "rerank_score" in h else "  -  "
        print(f"  {h['_id']}  {h['decision']:<8}  rerank {rerank}  fusion {h['fusion_score']:.4f}  {h['summary'][:110]}")


def _run_id(db, given):
    if given:
        return given
    latest = db.runs.find_one(sort=[("started_at", -1)])
    if not latest:
        raise SystemExit("no runs yet")
    return latest["_id"]


def cmd_replay(args):
    from gateway import control
    db = get_db()
    account = control.reconstruct(db, _run_id(db, args.run_id))
    run = account["run"]
    print(f"run {run['_id']}   {run['agent_id']} on behalf of {run['on_behalf_of']}   status: {run['status']}")
    print(f"goal: {run['goal']}\n")
    for s in account["steps"]:
        policies = ", ".join(s["policies"]) or s.get("rule", "-")
        print(f"step {s['step']:>2}  {s['tool'] or '-':<20} {str(s['decision']).upper():<8} {policies:<18} "
              f"{s['result']:<13} verified={s['verified']}")
        print(f"         who: {s['who']} for {s['on_behalf_of']}   why: {s['why']}")
        for p in s["precedents"][:1]:
            print(f"         nearest precedent: {p['id']} ({p['decision']}, score {p['score']})")
        if "approval" in s:
            a = s["approval"]
            print(f"         human: {a['decision']} by {a['by']} via {a['channel']}" + (f'  "{a["note"]}"' if a["note"] else ""))
        for v in s.get("violations", []):
            print(f"         violation: {v['code']}" + (f" ({v['why']})" if v["why"] else ""))
        if "rollback" in s:
            r = s["rollback"]
            print(f"         rollback by {r['by']}: " + (f"undone, {r['how']}" if r["undone"] else r["follow_up"]))
    for c in account["controls"]:
        print(f"\nKILL by {c['by']}: {c['reason']}  ({c['warrants_revoked']} warrants revoked)")
    chain = account["chain"]
    print("\nchain: " + (f"intact, {chain['entries']} entries, head {chain['head'][:16]}..." if chain["ok"]
                          else f"BROKEN at entry {chain['broken_at']}: {chain['why']}"))


def cmd_verify(args):
    from gateway import ledger
    db = get_db()
    run_id = _run_id(db, args.run_id)
    result = ledger.verify(db, run_id)
    if result["ok"]:
        print(f"{run_id}: chain intact, {result['entries']} entries, head {result['head']}")
    else:
        print(f"{run_id}: chain BROKEN at entry {result['broken_at']}: {result['why']}")
        raise SystemExit(1)


def cmd_demo(args):
    import os
    import threading
    import urllib.request

    import uvicorn
    db = get_db()
    if not args.keep:
        seed.reset(db)
    os.environ["WARRANT_AGENT_MODE"] = "scripted" if args.scripted else "live"
    url = f"http://127.0.0.1:{args.port}"
    print(f"database: {db.name} on the Atlas sandbox   search indexes: {schema.search_status(db)}")
    print(f"agent mode: {os.environ['WARRANT_AGENT_MODE']}\nconsole: {url}\n")
    if args.go:
        def kick():
            request = urllib.request.Request(f"{url}/runs", data=b"{}", headers={"Content-Type": "application/json"})
            for _ in range(40):
                try:
                    urllib.request.urlopen(request, timeout=5)
                    return
                except OSError:
                    time.sleep(0.25)
        threading.Thread(target=kick, daemon=True).start()
    uvicorn.run("control.api:app", host="127.0.0.1", port=args.port, log_level="warning")


def cmd_scoreboard(args):
    """Runs in the test database, so the demo state is untouched."""
    import os
    os.environ["MONGODB_DB"] = args.database
    from evals import scoreboard
    from gateway.db import client
    db = client()[args.database]
    schema.setup(db)
    print(f"red team: 12 attacks and 8 legitimate tasks, three arms, on database '{db.name}' ...")
    result = scoreboard.run(db)
    scoreboard.save(result)
    print()
    print(scoreboard.table(result))
    print(f"\none human ruling, searchable in Atlas after {result['ruling']['indexed_after_seconds']} s. "
          f"policy documents changed: {'yes' if result['policies_changed'] else 'no'}")
    print("receipt: docs/evidence/scoreboard.json")


def main():
    parser = argparse.ArgumentParser(prog="warrant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="create collections, validators and indexes, then seed").set_defaults(fn=cmd_setup)
    sub.add_parser("reset", help="back to a freshly seeded state").set_defaults(fn=cmd_reset)
    p = sub.add_parser("precedents", help="search past decisions for a request text")
    p.add_argument("text")
    p.add_argument("--tool")
    p.add_argument("-k", type=int, default=3)
    p.set_defaults(fn=cmd_precedents)
    p = sub.add_parser("replay", help="print the reconstruction of a run (default: the latest)")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("verify", help="check the hash chain of a run (default: the latest)")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("demo", help="reset, start the control API and console, run the agent from the console")
    p.add_argument("--scripted", action="store_true", help="scripted agent, no model calls")
    p.add_argument("--go", action="store_true", help="start a run immediately instead of from the console")
    p.add_argument("--keep", action="store_true", help="do not reset first")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_demo)
    p = sub.add_parser("scoreboard", help="red team: the same attempts with and without the gate")
    p.add_argument("--database", default="warrant_test")
    p.set_defaults(fn=cmd_scoreboard)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
