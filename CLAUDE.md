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
| Policy | `gateway/policies.py`, seed policies in `cli/seed.py` | six operators, deny > step-up > allow, default deny. P-009 is the precedent rule: rerank score at least 0.70 and a 0.10 margin over the closest approved precedent |
| Ledger | `gateway/ledger.py` | hash-chained per run, `verify` names the first broken entry |
| Search | `gateway/precedents.py` | one aggregation: `$rankFusion` of `$vectorSearch` (autoEmbed, voyage-4) and `$search`, then `$rerank` (rerank-2.5). About 330 ms |
| Control | `gateway/control.py`, `gateway/killswitch.py` | kill, approvals (web or voice with a challenge code), rollback, reconstruct. A human decision becomes a precedent. `flag` lets a human rule on a call that was already allowed (a `ruling` ledger entry plus a precedent). `set_threshold` changes P-009's `min_score`, human only, versioned on the policy |
| API and console | `control/api.py`, `console/index.html` | FastAPI plus one HTML page. Change streams feed it over SSE. Keys 1 to 3 walk the demo, 4 undoes the first payment. `GET /atlas` feeds the folded "Inside MongoDB Atlas" section |
| Agents | `agent/scripted.py`, `agent/live.py` | scripted is the stage default. Live is Claude Opus 5.5 on LangGraph with the MongoDB checkpointer, verified |
| Voice | `voice/agent.md` | ElevenLabs agent "Warrant Approvals Desk". Its id is in `.env` as `ELEVENLABS_AGENT_ID`, never in the repo. Three client tools: `submit_decision`, `flag_request`, `set_threshold`. Verified in typed mode only |
| Red team | `evals/`, `checks/hidden.py`, `./warrant scoreboard` | 12 attacks and 8 legitimate tasks, three arms: 12/12, 1/12, 0/12 executed. Receipt in `docs/evidence/scoreboard.json` |
| Tests | `tests/` | 46 acceptance tests against the cluster, in database `warrant_test`. IDs run AT-01 to AT-19. AT-18 is the flag, AT-19 the threshold |

### Commands

`./warrant setup | reset | demo [--scripted] | replay | verify | precedents "<text>"`, and `uv run --env-file .env pytest`.
The demo server is started with `./warrant demo --scripted --port 8000` (it resets first). Restart it after changing Python code.

### The demo (see `docs/05-DEMO.md`)

The story has one human on screen: Sam, who runs payments at a freight company. An AI support agent handles refund requests for him. The problem in plain words: the agent obeys every written rule and still pays requests nobody wrote a rule for, and afterwards nobody can say who allowed it. Warrant is the checkpoint between the agent and the money.

The console (`console/index.html`, one file, no build step) has four tabs: Demo, MongoDB live, Proof, Audit trail. Demo opens with "Meet Sam", a start button and three floating cards (The problem, The checkpoint, The payoff). Above the stage is a flow strip: Customer, AI agent, Warrant checkpoint, Payment.

| Key | Step | What happens |
|---|---|---|
| 1 | A request no rule covers | A customer asks for $300 back, sent to someone else's card (T8). It is under every limit, so the agent pays it |
| 2 | Sam speaks up | Sam calls Warrant. The ElevenLabs agent comes up and says "Warrant here. Go ahead, Sam." He states the rule. The agent calls `flag_request`, which writes a refusal precedent for that request, then asks whether he wants a different similarity threshold. A number calls `set_threshold`, which updates `params.min_score` on policy P-009. The stage has three columns here: the request, Sam and Warrant, and "MongoDB Atlas, live" with the inserted document and the policy diff. Fallbacks: type the rule and press Flag it, "Type to Warrant", and a slider for the threshold |
| 3 | It never happens again | The same $300 request returns and is held, citing Sam's ruling (score about 0.97) |
| 4 (optional) | Undo the first payment | Rollback of the first run. The refund is reversed and the email is marked cannot undo |
| 5 (optional) | Warrant asks Sam | The other direction: a $900 request (T7) is over the agent's limit, so the checkpoint asks Sam. Voice approval with the three-digit code, or type a reason and click Deny |

- Abhi asked for this flow at about 3:45 PM: Sam interjects by voice while watching requests, Warrant confirms and asks about the threshold, and the Atlas changes show as they happen.
- Step 2 uses the same ElevenLabs agent with a per-call prompt and first message passed from the page (`talkPrompt` in the console). Client overrides for prompt and first message are enabled on the agent. Verified in typed mode only, not yet with a microphone. `?autovoice=0` stops key 2 from starting the microphone.
- "No rule was edited" is only true when the threshold was not changed, and the page words it accordingly. If Sam changed the threshold, say "nothing was retrained and no rule was rewritten".
- The threshold is on the `$rerank` score (0 to 1), default 0.70, with a 0.10 margin over the closest approved precedent. The repeat of the flagged request scores about 0.97. On the key 5 path the $300 request scores 0.76 against a ruling made on the $900 request, so a threshold above 75 would let it through there.
- MongoDB live shows the tiles, the latest write, the P-009 diff, collection counts and what the database enforces, the search pipeline and the ledger validator. Proof shows the red-team numbers, the model-alone line and the test receipt (`WARRANT_RECEIPT=1 uv run --env-file .env pytest` writes `docs/evidence/tests.json`).
- Sam is the only human named on screen. The data still has `human:dana` as the person the agent acts for and as the reviewer for kill and rollback, and `human:sam` as the approver.
- The scripted demo steps skip the order lookup to keep waits short.
- Lead with the learning loop. Per-call policy, chained logs and kill switches are table stakes (Microsoft's Agent Governance Toolkit has them): do not lead with those.
- Abhi decides what ships and when (he said so at about 3:45 PM). Do not hold work back for the clock. Commit working checkpoints so he can stop at any of them.
- Wanted after his first test pass, not before: brand it as something that plugs into a company's CRM or support desk, with a placeholder "connect my environment" button.

### Rules learned today

- Never type, store or echo credentials. The user edits `.env` themselves. `.env`, `docs/private/`, `research_notes/` and `reports/` are git-ignored.
- `reset` keeps collections, validators, indexes and seeded precedents, deletes learned precedents, and waits until Atlas has dropped them from the search index.
- Automated Embedding is asynchronous. A new precedent is searchable about 1 to 2 seconds later. `wait_until_searchable` measures it.
- Atlas does not allow `createRole` by command. The insert-only ledger user is not built.
- The live model declines the planted instructions on its own. Say so. The scripted agent shows the run where the model does not resist.
- Do not claim: that Agent Engine lacks audit or review, regulatory compliance, that one reranker beats another, that the chain makes the ledger tamper-proof.
- All code is original and written today. Other teams' repos are read for ideas only. Never copy their code.
- Commit after each working piece, with the acceptance test ID where there is one.

### Evidence (added after the first state note)

| What | Command | Result on the cluster |
|---|---|---|
| Red-team scoreboard | `./warrant scoreboard` (about 3 min, test database) | Attacks executed: 12/12 no gate, 1/12 Warrant, 0/12 after one human ruling. Legitimate work 8/8 in every arm. Receipt `docs/evidence/scoreboard.json`, table auto-refreshed in README between `<!-- scoreboard:start/end -->` |
| Model-alone baseline | `./warrant baseline` (about 1 min, about $1.20 of API credit) | Claude Opus 5.5, rules in its prompt, no gate, 3 trials: written rules broken 0/15, harm with no written rule 6/9 (it paid the planted "manager override" and "finance notice" refunds every time), legitimate 12/12. Receipt `docs/evidence/model-baseline.json` |

- Cases live in `evals/cases.py`. Checks live in `checks/hidden.py` and are imported only by the runners.
- The scoreboard's first run found a false positive in P-009 (a plain $480 credit matched a refused $480 request). Fix: the embedded text is only the agent's reason plus the customer's text (`precedents.summary`), and a match needs rerank score >= 0.70 and a 0.10 margin over the closest approved precedent. L08 is the regression case.
- `payments.refund` takes an optional `destination` ("original" by default). T7, T8, A13 and the ruling use another card. The A13 check looks at where the money went.
- The console shows each customer's request (name, order, message bubble) above the agent's steps, the red-team panel (12, 1, 0 plus the model-alone line), and a destination chip.
- Do not tune the live agent's prompt to make it fail. With "you may refund up to $500" in its prompt it declined the override ticket; with the full rule list in the baseline it paid. Report both.

### Decisions and answers from Abhi (2:10 PM)

- Audio is available on stage. A stored scoreboard result on stage is fine. Focus on getting through Round 1.
- Opening line for the demo: his own story from today (an AI support agent refunded him for API credits he did not need, in two minutes, with no human).
- Not decided: the project name (he worries "Warrant" and the styling may resemble other Claude-assisted entries), and whether to re-skin the scenario from logistics refunds to billing support. A real Stripe integration is out of scope for today.
- About 2:45 PM, after his first voice trial: the agent heard him correctly, but the spoken briefing cut off and text on the page rendered badly. He wants a clean, light UI modelled on ElevenLabs and Retell, a preamble that says who Sam is, a flow that fits 60 seconds, and all effort on the demo story and the voice step.

### Open items

- Abhi tests voice himself: Chrome at http://127.0.0.1:8000, key 1, then key 2, allow the microphone, say the rule, answer the threshold question, then key 3.
- Timed rehearsals (target under 2:50), the 1-minute video (start by 3:45 PM), the submission form (by 4:45 PM). Feature freeze at 3:10 PM.
- If the scenario is re-skinned: company and customer names can change freely. Ticket notes, agent reasons and precedent text are what search compares, so changing any of them changes scores. Re-run `./warrant scoreboard` and the tests afterwards.
- Not built: crash reconciler, precedent review and expiry, MCP front door, insert-only ledger user.
