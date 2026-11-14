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
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
