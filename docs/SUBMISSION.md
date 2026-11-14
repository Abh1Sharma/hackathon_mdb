# Submission text

Paste-ready text for the Cerebral Valley form. Trim to fit each field.

## Project Description field (2811 of 3,000 characters)

Warrant is a checkpoint between an AI agent and the money. Built solo, and everything was written today.

THE PROBLEM. We gave Claude Opus 5.5 the rules in its prompt and no checkpoint. Over three trials it broke a written rule in 0 of 15 runs, and still paid out in 6 of 9 runs where no rule was written. Obedience is not the gap. The gap is everything nobody wrote a rule for, and a prompt leaves no record of who allowed it.

WHAT IT DOES. Warrant sits between the agent and its tools. For each call it identifies the agent and the person it acts for, evaluates policy documents stored in MongoDB Atlas with default deny, and searches past human decisions. It then issues a single-use warrant bound to the exact arguments, holds the call for a human, or refuses it. The decision, the warrant and a hash-chained ledger entry commit in one transaction. A reviewer can replay a run, kill it mid-run, and roll back what can be undone.

THE DEMO. An agent pays a $300 refund to someone else's card, because no rule forbids it. Sam, who runs payments, tells Warrant by voice that refunds only go back to the original payment method, and sets how similar a request must be before it is held. The same request returns and is stopped, citing his words. Nothing was retrained and no rule was rewritten. The only thing that changed is data in Atlas: his ruling, and one number on a policy document.

HOW ATLAS IS USED. Automated Embedding (voyage-4) makes a new ruling searchable about a second after it is saved, with no embedding code in the app. One aggregation runs $rankFusion over $vectorSearch and $search, then $rerank, inside the authorization decision. Search can only make a decision stricter. Transactions, $jsonSchema validators, unique and TTL indexes and change streams do the rest: the kill switch, the live console and the waiting agent all react to the database.

EVIDENCE. 12 attacks and 8 legitimate tasks, scored by checks the agent never sees: 12 attacks executed with no gate, 1 with Warrant, 0 after one human ruling, and 8 of 8 legitimate tasks completed each time. The suite's agent is scripted to attempt every attack. 46 acceptance tests run against the live cluster.

VOICE. An ElevenLabs agent takes Sam's spoken rule, writes it to Atlas as a precedent through a client tool, asks whether he wants a different similarity threshold, and updates the policy. It also handles step-up approvals tied to a challenge code on screen.

WHAT IS MOCKED. The business systems (orders, payments, CRM, email) are collections and identities are demo keys. The stage demo uses a scripted agent so it is repeatable. The same gateway also runs a live Claude Opus 5.5 agent on LangGraph.

Built with MongoDB Atlas, Voyage AI through Atlas, ElevenLabs Agents, Claude on LangGraph, Python, PyMongo and FastAPI.

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
