# 00 Scope lock (written 11:20 AM on build day)

Status: **proposed, waiting for Abhi's confirmation.** Where this file conflicts with `02-SPEC.md`, `03-ARCHITECTURE.md` or `04-BUILD-PLAN.md`, this file wins.

Known as of 11:35 AM: solo entry, staying through the finals, own Anthropic key for the demo agent, ElevenLabs credits and headset still pending.

## Verified on the sandbox cluster (11:30 AM, throwaway database `warrant_check`)

| Check | Result |
|---|---|
| Cluster | M10, MongoDB 9.0.7, AWS US_WEST_1, user is `atlasAdmin`, venue IP allowed |
| `autoEmbed` vector index (voyage-4) | Created, not blocked by org policy. Queryable about 3 minutes after the first search index on the cluster |
| `$vectorSearch` with query text | Works. T6-style query returns the denied "manager override" precedent first (0.81), then approved ones (0.75, 0.74). Scores are close together, so they are a poor threshold on their own |
| Atlas Search index and `$search` | Works. Same precedent first |
| `$rankFusion` (vector + text, filter on tool) | Works. Top 2 are both denied social-engineering precedents. A benign late-delivery query returns only approved precedents |
| `$rerank` | Blocked with 403 until "Native Reranking" is switched on in Project Settings. Until then P-009 uses a rank rule: the top fused precedent is a denial |
| Transactions, change streams, pre-images, validator | Not yet run. `scripts/check_sandbox.py` covers them once the password is in `.env` |

## Decision

Stay on **Problem Statement 1, "Agents You Can Audit"**, and build Warrant. Change one thing: **search stops being a stretch goal and becomes the second half of the product.**

> Policy in the database decides. Search over past decisions explains the decision to the human, and tightens the guardrail when a request looks like something that was refused before.

One line for the room: *"Policy is the statute. Precedents are the case law. Both live in Atlas, and every decision cites both."*

## Why (from this morning's doc research and the judge conversation)

1. **The cluster is M10 on MongoDB 9.0.7.** That removes most sandbox risk (transactions, change streams, pre-images, search nodes) and unlocks the newest search features: Automated Embedding (`autoEmbed` index type, query by text) and the native `$rerank` stage, which needs 9.0 and M10. These are the features the MongoDB search engineers on the judging panel work on. Almost nobody else will use `$rankFusion` then `$rerank` in one pipeline today.
2. **MongoDB already ships coarse governance in Atlas Agent Engine** (Policy Engine: tool allowlists and execution budgets. Human-in-the-loop. Content guardrails). Its documented limits are exactly Warrant's features: no argument-level or data-aware rules, no acting-on-behalf-of identity, policy changes do not affect in-flight executions, and no policy means no restriction. So the category is validated by MongoDB, and Warrant is the fine-grained layer next to it. That is the answer to "how is this different from Agent Engine?"
3. **Track 2 competes head-on with a MongoDB product** (Agent Engine memory service with extraction and four memory types) and reads as RAG. Track 3's headline is a library call. Track 1 is still the least commoditized.
4. **The event blurb says "agents that adapt their own guardrails".** Precedents are that, with an audit trail.
5. Track 1's statement does not require Vector Search, so a search feature here has to earn its place. It does: it sits in the enforcement path and in the approval path, and it is not retrieval-for-generation (basic RAG is banned).

## The search half, precisely

**Precedent** = one past decision, written by the gateway as a document with a deterministic one-sentence `summary` (no LLM): who asked, which tool, amount, region, the agent's stated reason, the untrusted text the request was based on (the ticket note), the rule that fired, and the outcome.

Precedents are written when a human decides a step-up, and when the gateway denies a call that carries a reason. About 24 historical precedents are seeded so the index is warm.

**One retrieval pipeline, all native to Atlas, no embedding code in the app:**

```
$rankFusion
  semantic: $vectorSearch  (autoEmbed index on summary, voyage-4, query by text, filter on tool)
  lexical:  $search        (Atlas Search index on summary, reason, note)
-> $rerank                 (Voyage reranker, top 10 -> top 3)
```

**Used in two places:**

| Use | What happens | Why it is not a gimmick |
|---|---|---|
| A. Approval card | When policy escalates (T3), the approver sees the 3 closest past decisions with outcome and score. The approval ledger entry stores the precedent IDs shown | The human decides with context, and the record shows what they were shown |
| B. Tighten-only guardrail (P-009) | For money-moving tools, if the request is close (rerank score over a recorded threshold) to a **denied** precedent, an otherwise-allowed call is raised to step-up. The decision entry cites the precedent ID, score and threshold | Catches what static rules miss, and the probabilistic part is fully recorded |

**The governance rule that makes this defensible:** *search can tighten automatically, only a human can loosen.* A precedent can never turn a deny into an allow or a step-up into an allow. If search errors or times out, the result is step-up (fail closed). Search is a fact provider. The policy engine still decides.

**New demo ticket T6:** a $480 Ontario refund. It passes every deterministic rule. The customer note says a manager override applies and verification should be skipped. The gateway raises it to step-up: "resembles denied precedent PR-014, score 0.9". This is the moment for the search judges.

## Voice (ElevenLabs), the one stretch

The approver's spoken reason is the richest "why" in the whole system, so voice feeds the precedent engine instead of sitting beside it:

1. Policy escalates. A voice agent briefs the approver from the approval request and reads the closest precedent ("a similar $1,150 refund was approved last month with a carrier damage report").
2. The approver answers in a sentence and reads the challenge code shown in the console.
3. The decision and the transcript go on the approval. **The spoken reason becomes the text of the new precedent**, so the next similar request retrieves the human's own words.

Built only after the M3 gate is green, with the button path always working. Needs ElevenLabs credits and a headset.

## Requirements added

| ID | Priority | Requirement |
|---|---|---|
| FR-24 | P1 | Human step-up decisions and reasoned denials are written to `precedents` with a deterministic `summary` |
| FR-25 | P1 | Retrieval is one aggregation: `$rankFusion` of `$vectorSearch` (autoEmbed) and `$search`, then `$rerank`. Per-stage scores are kept |
| FR-26 | P1 | A step-up approval request carries the top 3 precedents. The approval ledger entry records their IDs |
| FR-27 | P1 | P-009: tighten-only. Similarity to a denied precedent raises allow to step-up for money-moving tools. Score, threshold and precedent ID go in the decision entry. Fail closed |
| FR-28 | P2 | `warrant search "<question>"`: hybrid search over the ledger with facets by decision, tool and agent |

| ID | Given | When | Then |
|---|---|---|---|
| AT-13 | Seeded precedents, index ready | T3 escalates | The approval request lists at least 1 precedent with ID, outcome and score, and the approval ledger entry stores them |
| AT-14 | A denied override-style precedent exists | The agent requests the T6 refund | Decision is step-up citing P-009 and the precedent ID. With precedents removed, the same call is allowed by P-002 |
| AT-15 | Any request the deterministic rules deny | Precedents say "approved" | Still denied (evaluator unit test) |
| AT-16 | Seeded precedents | `warrant precedents "<text>"` runs | Prints top 3 with fusion and rerank scores, from one aggregation |

## Cuts made now, to pay for it

| Cut | Replacement |
|---|---|
| MCP proxy via FastMCP, and FR-23 | Plain Python wrapper around tool functions from the start. Say "the same gate sits behind an MCP server" in Q&A |
| React console | One plain HTML page with a timeline, an approval card and three buttons |
| CRM rollback | Roll back refunds only. Email stays "cannot undo" |
| P-008 | Dropped |
| Precedents-or-voice choice at 3:30 | Precedents are core. Voice is the only stretch, and it reads the top precedent aloud |

Never cut: the policy gate, the ledger, the kill switch, the reconstruction, and now the precedent pipeline.

## Design notes that matter

- **Embedding is asynchronous.** Auto-embedding is driven by change streams, so a precedent written mid-run becomes searchable a few seconds later. The demo relies on seeded precedents. `reset` must not drop `precedents` or its indexes: it deletes only run-created precedents (`seeded: false`). A separate `seed --full` rebuilds the indexes.
- **Create the search indexes in M0**, before anything else, because they build in the background.
- **Search runs before the decision transaction**, like resource resolution, and its result is written inside the transaction with the decision.
- **Threshold calibration is a task**, not a guess: a script prints rerank scores for T1 to T6 against the seed set, and the threshold is chosen from that and stored on the policy document.
- **Fallbacks:** if the org blocks `autoEmbed`, embed client-side with a Voyage key from Atlas "AI Model APIs" into a normal `vector` index. If `$rerank` is not enabled, keep `$rankFusion` and use its score.

## Timeline (replaces 04-BUILD-PLAN timings)

| Time | Milestone | Gate |
|---|---|---|
| now to 11:45 | Decisions confirmed, password in `.env`, `scripts/check_sandbox.py` green | Capability report read |
| 11:45 to 12:20 | M0: collections, validators, indexes including both search indexes, seed with precedents, `reset` | AT-10 |
| 12:20 to 12:40 | Search spike: the full pipeline returns sane results for T3 and T6 text | AT-16 |
| 12:40 to 1:45 | M1: gate, warrants, ledger with hash chain, scripted agent | AT-01, 02, 03, 04, 05 |
| 1:45 to 2:45 | M2: control API, change-stream feed, kill, replay CLI, HTML console, step-up | AT-06, 08, 11 |
| 2:45 to 3:30 | M3: precedents on the approval card, P-009, rollback of refunds, verify | AT-07, 09, 13, 14, 15 |
| 3:30 to 4:00 | LangGraph live agent behind a flag. Voice only if everything above is green | |
| 4:00 to 4:45 | Freeze, three clean runs, video, README, submit | |

## Open questions for Abhi

See the chat. They are: confirm this scope, solo or team and the concert constraint, which LLM key, ElevenLabs access, and whether the organizers answered the planning-docs question.
