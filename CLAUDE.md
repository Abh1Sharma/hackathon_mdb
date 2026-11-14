# CLAUDE.md: handoff for the build session

You are helping Abhi build **Warrant** at a one-day hackathon. The clock is the main constraint: hacking runs 10:45 AM to 5:00 PM, and the submission goes in at 4:45 PM.

## Read first

0. `docs/00-SCOPE.md` for the scope lock. It overrides the other docs where they conflict. `docs/MDB-REFERENCE.md` has verified Atlas syntax for search, reranking and the core features.
1. `docs/02-SPEC.md` for requirements (FR-xx) and acceptance tests (AT-xx).
2. `docs/03-ARCHITECTURE.md` for components, the tool-call flow, the Atlas data model and the control API contract.
3. `docs/04-BUILD-PLAN.md` for milestones, gates and cut lines.

The other docs are for Abhi. Read `docs/06-VOICE-ELEVENLABS.md` only if asked to build voice.

## What we are building

A gateway between an AI agent and its tools. Every tool call is identified, checked against policies stored in MongoDB Atlas, given a single-use warrant, recorded in an append-only hash-chained ledger, executed, and verified. A reviewer can reconstruct a run, kill it mid-run, and roll it back. Problem statement: "Agents You Can Audit".

## Hard rules

- Everything in this repo is written today. Do not import code from other projects of Abhi's, and do not suggest reusing any.
- The repo is public. Never write secrets to files. Use `.env` (git-ignored) and keep `.env.example` current.
- MongoDB must be the hackathon's Atlas sandbox cluster. The connection string comes from `.env`.
- Not allowed by the event: Streamlit, a basic RAG app, or a project whose main feature is a dashboard. Keep the reviewer console thin.
- Policy enforcement happens in the gateway, never in a prompt.
- Default deny. If no policy matches, the answer is deny.

## Working agreement

- Work one milestone at a time, in the order in the build plan. State which milestone and which AT-xx you are working on.
- Test first: write the acceptance test for the requirement, then the code that passes it. Tests run against a freshly seeded database.
- Prefer boring, direct code. No abstractions that are not needed by an acceptance test.
- Keep modules small and names matching the spec (`warrants`, `ledger`, `policies`, `approvals`, `runs`, `identities`).
- When the plan's gate time arrives and the gate is not green, stop and tell Abhi which cut line applies. Do not keep going silently.
- If a sandbox limit blocks something (transactions, change streams, custom roles, vector index), say so immediately and propose the fallback from `docs/07-RISKS-AND-OPEN-QUESTIONS.md` section 1.
- Commit after every passing acceptance test, with the AT-xx ID in the message.
- Ask before adding a dependency that is not listed below.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 for the backend and CLI |
| Database | MongoDB Atlas via PyMongo |
| Gateway | FastMCP server with tool-call middleware, proxying the mock tool server. Fallback: decorator around plain tool functions |
| Control API | FastAPI, server-sent events for the live feed |
| Console | One page. React via Vite is fine, plain HTML is fine. No component library needed |
| Demo agent | LangGraph, `langgraph-checkpoint-mongodb` for its state, LangSmith tracing through environment variables |
| Stretch | ElevenLabs JavaScript SDK in the console, or Atlas Vector Search for precedents |

## Conventions

- IDs are readable strings where possible (`agent:refund-agent-7`, `P-002`, `run_...`).
- Times are UTC datetimes.
- Hashing: SHA-256 over canonical JSON (sorted keys, compact separators). Put the canonicalizer in one place and test it.
- Refusals returned to the agent are structured: a code (`DENIED`, `STEP_UP_PENDING`, `KILLED`, `WARRANT_INVALID`), the rule ID, and a one-line explanation.
- Money is stored in cents as integers.

## Commands the repo must end up with

| Command | Does |
|---|---|
| `reset` | Drops and reseeds the database in under 10 seconds |
| `demo` | Starts the gateway, control API and console, then runs the agent on the seeded queue |
| `demo --scripted` | Same, with the scripted agent and no model calls |
| `replay <run_id>` | Prints the reconstruction of a run |
| `verify <run_id>` | Checks the hash chain and reports the first broken entry |

## Kickoff prompt

Paste this to start the session at 10:45:

> Read CLAUDE.md, then docs/02-SPEC.md, docs/03-ARCHITECTURE.md and docs/04-BUILD-PLAN.md. We are starting milestone M0. First, list any ambiguities that would block M0 or M1 and your proposed resolution for each, in under 15 lines. Then scaffold the repo layout from the architecture doc, create the connection module, and write the script that creates the collections with their validators and indexes. Finish M0 by making AT-10 pass. Tell me when the M0 gate is green.

## Milestone prompts

- **M1:** "Start M1. Write the policy evaluator with unit tests against the seed policies, then the decision transaction, then the execute and verify path. Build the scripted agent. Done when AT-01, AT-02 and AT-03 pass."
- **M2:** "Start M2. Implement the control API from the contract, the change-stream event feed, kill, the reconstruction endpoint, the replay CLI and the one-page console. Done when AT-06 and AT-11 pass."
- **M3:** "Start M3. Step-up approvals, rollback, hash chain and verify, warrant replay and digest checks, the history policy, then swap in the LangGraph agent behind a flag. Done when AT-04, AT-05, AT-07, AT-08, AT-09 and AT-12 pass."
- **Freeze:** "Feature freeze. Run reset and demo three times. Fix only failures. Then write the README: problem statement addressed, how to run, what was built today, architecture in ten lines."

## Current state (kept up to date during the build, read this first after a context reset)

**Scope is locked in `docs/00-SCOPE.md`.** Track 1, "Agents You Can Audit". Warrant = policy gate + ledger, with precedent search as the second half ("policy is the statute, precedents are the case law, search can tighten, only a human can loosen").

### What exists and works on the Atlas sandbox (M10, MongoDB 9.0.7, cluster host in `.env`)

| Area | Where | Notes |
|---|---|---|
| Gate | `gateway/gateway.py` (`authorize`, `execute`, `call_tool`) | identify, resolve facts, precedent search, decision in one transaction, single-use warrant bound to an argument digest, execute, verify, record |
| Policy | `gateway/policies.py`, seed policies in `cli/seed.py` | six operators, deny > step-up > allow, default deny. P-009 is the precedent rule, threshold 0.75 |
| Ledger | `gateway/ledger.py` | hash-chained per run, `verify` names the first broken entry |
| Search | `gateway/precedents.py` | one aggregation: `$rankFusion` of `$vectorSearch` (autoEmbed, voyage-4) and `$search`, then `$rerank` (rerank-2.5). About 330 ms |
| Control | `gateway/control.py`, `gateway/killswitch.py` | kill, approvals (web or voice with a challenge code), rollback, reconstruct. A human decision becomes a precedent |
| API and console | `control/api.py`, `console/index.html` | FastAPI plus one HTML page. Change streams feed it over SSE. Keys 1 to 5 walk the demo |
| Agents | `agent/scripted.py`, `agent/live.py` | scripted is the stage default. Live is Claude Opus 5.5 on LangGraph with the MongoDB checkpointer, verified |
| Voice | `voice/agent.md` | ElevenLabs agent "Warrant Approvals Desk". Its id is in `.env` as `ELEVENLABS_AGENT_ID`, never in the repo. Verified in typed mode only |
| Tests | `tests/` | 44 acceptance tests against the cluster, in database `warrant_test`. IDs match the spec (AT-01 to AT-17) |

### Commands

`./warrant setup | reset | demo [--scripted] | replay | verify | precedents "<text>"`, and `uv run --env-file .env pytest`.
The demo server is started with `./warrant demo --scripted --port 8000` (it resets first). Restart it after changing Python code.

### The demo (see `docs/05-DEMO.md`)

Five keys: 1 send a $300 request (T8, allowed), 2 run the queue (T1, T4, T5, T7), 3 a human denies T7 with a reason, 4 send the $300 request again (stopped, citing the ruling), 5 roll back the first run. The learning loop is the moment to lead with. Per-call policy, chained logs and kill switches are table stakes (Microsoft's Agent Governance Toolkit has them): do not lead with those.

### Rules learned today

- Never type, store or echo credentials. The user edits `.env` themselves. `.env`, `docs/private/`, `research_notes/` and `reports/` are git-ignored.
- `reset` keeps collections, validators, indexes and seeded precedents, deletes learned precedents, and waits until Atlas has dropped them from the search index.
- Automated Embedding is asynchronous. A new precedent is searchable about 1 to 2 seconds later. `wait_until_searchable` measures it.
- Atlas does not allow `createRole` by command. The insert-only ledger user is not built.
- The live model declines the planted instructions on its own. Say so. The scripted agent shows the run where the model does not resist.
- Do not claim: that Agent Engine lacks audit or review, regulatory compliance, that one reranker beats another, that the chain makes the ledger tamper-proof.
- All code is original and written today. Other teams' repos are read for ideas only. Never copy their code.
- Commit after each working piece, with the acceptance test ID where there is one.

### Open items

- Voice has not been tried with a microphone.
- Timed rehearsals, the 1-minute video (start by 3:45 PM), and the submission form (by 4:45 PM).
- Not built: crash reconciler, precedent review and expiry, MCP front door, insert-only ledger user.
