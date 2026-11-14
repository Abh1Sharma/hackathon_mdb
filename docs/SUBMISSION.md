# Submission text

Paste-ready text for the Cerebral Valley form. Trim to fit each field.

## Field: Project Description (2748 of 3,000 characters)

Warrant is a checkpoint between an AI agent and the money. Built solo, and everything was written today.

THE PROBLEM. AI agents follow the rules. The damage happens where no rule exists. We gave Claude Opus 5.5 the rules in its prompt and no checkpoint: over three trials it broke a written rule in 0 of 15 runs, and still paid out in 6 of 9 runs where no rule was written. Obedience is not the gap. The gap is everything nobody wrote a rule for, and a prompt leaves no record of who allowed it. Writing more rules only covers yesterday's incidents, retraining takes weeks, and a human reviewing everything means you no longer have an agent.

WHAT IT DOES. Warrant sits between the agent and its tools, so the agent never holds the keys. For each call it identifies the agent and the person it acts for, checks the written rules (default deny), and then checks every decision a human has made before. It issues a single-use warrant bound to the exact arguments, holds the call for a human, or refuses it. Every decision is recorded in a hash-chained ledger. A reviewer can replay a run, kill it mid-run, and roll back what can be undone. Rules are the statute and human decisions are the case law: search can tighten a decision, and only a person can loosen one.

THE DEMO. An agent pays a $300 refund to someone else's card, because no rule forbids it. Sam, who runs payments, tells Warrant out loud that refunds only go back to the original payment method, and sets how similar a request must be before it is held. His ruling is searchable about a second later. The same request is sent again and is stopped, citing his words. Nothing was retrained and no rule was rewritten.

EVIDENCE. 12 attacks and 8 legitimate tasks, scored by checks the agent never sees: 12 attacks executed with no gate, 1 with Warrant, 0 after one human ruling, and 8 of 8 legitimate tasks completed each time. The suite's agent is scripted to attempt every attack, which is the worst case. 46 acceptance tests run against the live cluster.

VOICE. An ElevenLabs agent takes Sam's spoken rule, records it as a precedent through a client tool, asks whether he wants a different similarity threshold, and updates the policy. It also handles step-up approvals tied to a challenge code shown on screen.

WHERE ELSE. Anywhere an agent can do something that is hard to undo: customer records, access and credentials, procurement, deploys and migrations. The pattern is the same: a rule set, a memory of human decisions, and a record.

WHAT IS MOCKED. The business systems (orders, payments, CRM, email) are collections and identities are demo keys. The stage demo uses a scripted agent so it is repeatable. The same gateway also runs a live Claude Opus 5.5 agent on LangGraph.

## Field: Describe your use of MongoDB products (2527 of 3,000 characters)

MongoDB Atlas is the identity, policy, memory and audit layer of Warrant. Everything runs on the hackathon's Atlas sandbox cluster (MongoDB 9.0.7). Each feature below is load-bearing: remove one and part of the demo stops working.

AUTOMATED EMBEDDING (voyage-4). Human rulings are documents in a precedents collection, with an autoEmbed vector index on one text field. When Sam rules by voice, the app inserts a plain document and Atlas embeds it. It is searchable about a second later. There is no embedding code and no embedding service in the app.

HYBRID SEARCH AND RERANK IN ONE AGGREGATION. Every refund runs one pipeline: $rankFusion over $vectorSearch (queried by text) and $search, then $rerank (rerank-2.5), typically in 0.3 to 0.5 seconds. The rerank score of the closest refused precedent becomes a fact inside the authorization decision, compared with a threshold stored on a policy document. Search can only make a decision stricter.

POLICIES AS DOCUMENTS. Rules live in a policies collection and are read on every call, so a change applies to the next decision of an agent that is already running. The similarity threshold is one field on a policy. Sam changes it by voice, the policy version is bumped, and each decision records the policy versions it used.

MULTI-DOCUMENT TRANSACTIONS. The decision, the single-use warrant (or the approval request) and the ledger entry commit together or not at all. A kill is checked again inside that transaction.

SCHEMA VALIDATION AND INDEXES. $jsonSchema validators with validationAction "error" make the database reject a malformed ledger entry or warrant. Unique indexes allow one warrant per step and one ledger entry per sequence number. A TTL index removes expired warrants.

CHANGE STREAMS. One database-level change stream feeds the live console over server-sent events, so the console never polls. Another is the kill switch. The waiting agent resumes from a change stream when a human decides.

AGGREGATION OVER THE LEDGER. A per-run spending cap is computed from the ledger at decision time.

AGENT STATE. The live Claude agent runs on LangGraph with the MongoDB checkpointer, so its state is in the same cluster.

WHERE TO SEE IT. The console's "MongoDB live" tab reads all of this from the cluster: collection counts, what the database enforces on each collection, the actual search pipeline, the ledger validator, and the two documents that change when Sam speaks. gateway/precedents.py holds the pipeline and gateway/schema.py the validators and indexes.

## Field: Feedback for MongoDB (127 of 150 characters)

Automated Embedding with $rankFusion and $rerank in one pipeline was the unlock. Wish: a signal that a new document is indexed.

## Project name

Warrant

## One line

The checkpoint between an AI agent and the money. A person says no once, out loud, and the next similar request is stopped about a second later.

## Short description

AI agents follow the written rules and still act where no rule exists, and afterwards nobody can say who allowed it. Warrant is a gateway between an agent and its tools. Every action is checked in MongoDB Atlas against the written rules and against every decision a human has made before, then recorded in a hash-chained ledger in the same transaction. When a person rules by voice, Atlas embeds that ruling itself, and the next similar request is held about a second later.

## Full description

Problem statement: Agents You Can Audit. Built solo, and everything was written today.

The problem. We gave Claude Opus 5.5 the rules in its prompt and no checkpoint. Over three trials it broke a written rule in 0 of 15 runs, and still paid out in 6 of 9 runs where no rule was written. Obedience is not the gap. The gap is everything nobody wrote a rule for, and a prompt leaves no record of who allowed it.

What Warrant does. It sits between the agent and its tools. For each call it identifies the agent and the person it acts for, evaluates policy documents stored in Atlas with default deny, and searches past human decisions. It then issues a single-use warrant bound to the exact arguments, holds the call for a human, or refuses it. The decision, the warrant and the ledger entry commit in one transaction. A reviewer can replay a run, kill it mid-run, and roll back what can be undone.

The demo. An agent pays a $300 refund to someone else's card, because no rule forbids it. Sam, who runs payments, tells Warrant by voice that refunds only go back to the original payment method, and sets how similar a request must be before it is held. The same request returns and is stopped, citing his words. Nothing was retrained and no rule was rewritten. The only thing that changed is data in Atlas: his ruling, and one number on a policy document.

How MongoDB Atlas is used. Automated Embedding (voyage-4) makes a new ruling searchable about a second after it is saved, with no embedding code in the app. One aggregation runs $rankFusion over $vectorSearch and $search, then $rerank, inside the authorization decision. Search can only make a decision stricter. Multi-document transactions, $jsonSchema validators, unique and TTL indexes and change streams do the rest: the kill switch, the live console and the waiting agent all react to the database.

Evidence. A red-team suite of 12 attacks and 8 legitimate tasks, scored by checks the agent never sees: 12 attacks executed with no gate, 1 with Warrant, and 0 after one human ruling, with 8 of 8 legitimate tasks completed each time. The suite's agent is scripted to attempt every attack, which is the worst case. 46 acceptance tests run against the live cluster.

What is mocked. The business systems (orders, payments, CRM, email) are collections, and identities are demo keys. The ledger is append-only by convention, with a hash chain that makes edits detectable. The stage demo uses a scripted agent so it is repeatable, and the same gateway also runs a live Claude Opus 5.5 agent on LangGraph.

## Built with

MongoDB Atlas (Automated Embedding, Vector Search, Atlas Search, $rankFusion, $rerank, transactions, change streams, schema validation), Voyage AI models through Atlas, ElevenLabs Agents, Claude Opus 5.5 on LangGraph with the MongoDB checkpointer, Python, PyMongo, FastAPI.

## ElevenLabs

Voice is how the human rules. An ElevenLabs agent listens to Sam's spoken rule, writes it to Atlas as a precedent through a client tool, asks whether he wants a different similarity threshold, and updates the policy with his answer. The same agent handles step-up approvals, where a spoken decision is tied to a challenge code shown on screen.

## Links

- Repository: https://github.com/Abh1Sharma/hackathon_mdb
- Video: add the link after upload
