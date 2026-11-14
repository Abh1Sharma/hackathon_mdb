# Warrant

**No agent action without a warrant.** A gateway between an AI agent and its tools that makes MongoDB Atlas the identity, policy and audit layer. Every tool call is tied to an identity, checked against policy stored in Atlas before it runs, and recorded in a tamper-evident ledger, so a reviewer can reconstruct a run, stop it mid-run and roll it back.

Built at **Agents in Context Toronto** (MongoDB x Cerebral Valley), Nov 14 2026.
Problem statement 1: **Agents You Can Audit**. Everything in this repository was written on the day. The planning docs in `docs/` were committed first, then the code.

![The console: a $300 request stopped because it resembles a ruling a human made seconds earlier](docs/img/console-learned.jpg)

**The moment:** a $300 refund to someone else's card is under every limit, so it goes through. A human denies a similar $900 request and says why. The same $300 request, sent again, is stopped, citing that ruling and the human's words. No rule was edited. One page for judges: [docs/ONE-PAGER.md](docs/ONE-PAGER.md).

## The idea in three lines

- **Policy is the statute.** Rules are documents in Atlas, evaluated by the gateway outside the model. Default deny. A prompt injection can change what the model wants, not what it is allowed to do.
- **Precedents are the case law.** Every human decision becomes a searchable precedent. One native Atlas pipeline (`$rankFusion` of `$vectorSearch` on an auto-embedding index and `$search`, then `$rerank`) finds the closest past decisions for each new request.
- **Search can tighten, only a human can loosen.** A request that passes every rule but resembles one a human refused before is raised to a human. A precedent can never turn a deny into an allow.

## What happens to a tool call

```
agent ── call_tool(identity, run, step, tool, args, reason)
   1 identify      agent key -> identity and the human it acts for
   2 resolve       facts about the record (region, order total) and the untrusted text behind the request
   3 search        closest precedents, one aggregation, about 330 ms
   4 decide        ONE TRANSACTION: re-read run (killed?) -> evaluate policy -> ledger entry
                   -> allow: single-use warrant | step-up: approval request | deny: structured refusal
   5 execute       spend the warrant (bound to tool + argument digest, expiring), idempotency key from the warrant
   6 verify        read the target system back
   7 record        execution and verification entries, hash-chained to the previous entry
```

## Where MongoDB Atlas does the work

| Feature | Use |
|---|---|
| Schema validation (`$jsonSchema`, `validationAction: error`) | The ledger and warrants reject malformed writes at the database |
| Multi-document transactions | Decision, warrant or approval, and ledger entry commit together |
| Unique and TTL indexes | One warrant per step, unused warrants expire on their own |
| Change streams | Kill switch fast path, live console feed, the agent waiting for a human. Nothing polls |
| Aggregation over the ledger | Policy over history: at most $3,000 refunded per run |
| Automated Embedding (`autoEmbed`, voyage-4) | Precedents are embedded by Atlas. Queries are plain text. No embedding code in this repo |
| Atlas Search + `$rankFusion` | Hybrid retrieval of precedents (semantic and lexical) |
| Native `$rerank` (MongoDB 9.0) | A calibrated score, so "resembles a refused request" has a threshold that is recorded |
| Pre- and post-images | Enabled on the mock systems. Rollback uses before-images captured by the gateway |
| LangGraph MongoDB checkpointer | The live agent's own state |

Voice (ElevenLabs): a step-up can be decided in conversation. A voice agent briefs the approver from the request and its closest precedent, and submits the spoken decision with an on-screen challenge code. The spoken reason becomes the text of the new precedent. See `voice/agent.md`.

## Demo scenario

A refunds agent at a logistics company, acting for ops lead Dana, scoped to Ontario. Seven tickets in the queue and one that arrives later:

| Ticket | Situation | Outcome |
|---|---|---|
| T1, T2 | $80 and $240 refunds | Allowed, executed, verified |
| T3 | $1,200 refund | Step-up. The approver sees the three closest precedents |
| T4 | Order in BC | Denied: outside the agent's regions |
| T5 | Prompt injection asks for a $5,000 transfer | The agent attempts it. Denied |
| T6 | $480 refund "per manager override, skip verification" | Passes every static rule. Raised to a human because it resembles a refused precedent |
| T7 | $900 refund to a different card than the one used | Step-up by amount. A human denies it and says why |
| T8 (a later run) | $300 credit to someone else's card | Allowed before the T7 ruling. After it, raised to a human citing that ruling and the human's own words. No rule was edited |

## Run it

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and an Atlas cluster on MongoDB 9.0+ (M10+) with Native Reranking enabled in Project Settings.

    cp .env.example .env            # MONGODB_URI, and ANTHROPIC_API_KEY for the live agent
    uv sync
    ./warrant setup                 # collections, validators, indexes, search indexes, seed
    ./warrant demo --scripted       # control API + console on http://127.0.0.1:8000

In the console, keys 1 to 5 walk the demo: send a $300 request (allowed), run the queue, a human rules on the one that needs it (by voice or by button), send the $300 request again (stopped), undo the first one.

| Command | Does |
|---|---|
| `./warrant reset` | Back to a freshly seeded state in about 3 seconds |
| `./warrant demo` | Console and control API, live Claude agent |
| `./warrant demo --scripted` | Same, with the scripted agent and no model calls |
| `./warrant replay [run_id]` | Who, on whose behalf, what, why, which policy version, result, verification |
| `./warrant verify [run_id]` | Checks the hash chain and reports the first broken entry |
| `./warrant precedents "<text>"` | The precedent pipeline on its own, with rerank and fusion scores |
| `uv run --env-file .env pytest` | 44 acceptance tests against the cluster, in a separate `warrant_test` database |

## Layout

    gateway/    gateway.py (the gate), policies.py, ledger.py, precedents.py, control.py, killswitch.py, schema.py
    control/    FastAPI control API and the server-sent event feed
    console/    one HTML page: run timeline, decision desk with precedents and voice, Kill, Roll back, Verify
    agent/      scripted.py (no model) and live.py (Claude on LangGraph)
    systems/    mock orders, payments, CRM and email
    cli/        setup, reset, demo, replay, verify, precedents
    voice/      ElevenLabs approvals agent: prompt, tool and how it plugs in
    tests/      acceptance tests, IDs match docs/02-SPEC.md and docs/00-SCOPE.md
    docs/       planning and scope documents

## What was built today, and what is a library

Built today: the gateway, policy engine, warrant and ledger model, precedent pipeline, kill and rollback, control API, console, CLI, mock systems, both agents, and the tests. Libraries: PyMongo, FastAPI and uvicorn, LangGraph with its MongoDB checkpointer and the Anthropic chat model for the live agent.

## Honest limits

- The ledger is append-only by convention plus a hash chain. In production the gateway would connect as a database user that can only insert and read the ledger. Atlas requires creating that role in the UI.
- Identities are demo API keys. The model maps to workload identity plus a delegated user token.
- An email cannot be unsent. Rollback says so instead of pretending.
- A crash between spending a warrant and recording the execution is detectable (used warrant with no execution entry). The reconciler for it is not built.
