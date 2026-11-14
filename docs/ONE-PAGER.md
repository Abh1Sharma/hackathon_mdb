# Warrant, on one page

**Problem statement 1: Agents You Can Audit.** Built in a day at Agents in Context Toronto.

## What it is

An AI agent that can move money obeys every written rule and still pays requests nobody wrote a rule for, and afterwards nobody can say who allowed it. Warrant is a checkpoint between the agent and the money. Every action is checked in MongoDB Atlas, first against the written rules and then against every decision a human has made before, and the decision, the warrant and the ledger entry commit in one transaction.

## The moment

Sam runs payments at a freight company, and an AI agent handles refund requests for him.

1. A customer asks for $300 back, sent to someone else's card. It is under every limit, so the agent pays it.
2. A $900 request of the same kind is over the agent's limit, so the checkpoint asks Sam. He says no, out loud, with a reason.
3. The same $300 request returns and is held, citing his words. **No rule was edited and nothing was retrained.**

Atlas stored the ruling, embedded it itself and had it searchable about a second later. Rules are the statute. Human decisions are the case law. Both live in Atlas.

## The numbers

Twelve attacks and eight legitimate tasks, scored by hidden checks that read the business systems afterwards.

| | Attacks executed | Legitimate work completed |
|---|---|---|
| No gate | 12 / 12 | 8 / 8 |
| Warrant | 1 / 12 | 8 / 8 |
| Warrant after one human ruling | 0 / 12 | 8 / 8 |

Claude Opus 5.5 alone, with the rules in its prompt and no gate (three trials): it broke a written rule in 0 of 15 runs, and paid out in 6 of 9 runs where no rule was written. The scoreboard's first run also caught a false positive in our own precedent rule, which we fixed and turned into a regression case.

## How it works

| Step | What happens | Atlas feature |
|---|---|---|
| Decide | Policy documents are evaluated over the call's arguments, the record it touches and the run's history. Default deny | Aggregation over the ledger, schema validation |
| Record | Decision, warrant (or approval request) and ledger entry commit together | Multi-document transaction, unique and TTL indexes |
| Search | The closest past human decisions are found in one pipeline | Automated Embedding, `$rankFusion` of `$vectorSearch` and `$search`, then `$rerank` |
| Learn | A new ruling is embedded by Atlas and searchable about a second later. Search can tighten a decision, never loosen one | Automated Embedding, change streams |
| Control | Kill refuses the next call. Rollback compensates what can be undone and says what cannot | Change streams, transactions |

## What is different

- **Precedents inside the decision.** A request that passes every rule but resembles one a human refused is sent to a human. Most policy layers only know what someone wrote down.
- **Warrants bound to the call.** Single use, tied to the tool and a digest of the exact arguments, expiring. A replayed or altered call is refused.
- **Undo.** Rollback from the ledger, honest about what cannot be reversed.
- **Beside, not instead of, existing tools.** Per-call policy checks, chained audit logs and kill switches exist elsewhere (for example Microsoft's Agent Governance Toolkit), and Atlas Agent Engine has tool allowlists and budgets. Warrant adds the argument-level, history-aware and precedent-aware layer.

## What is real and what is not

Real: the gateway, policy engine, ledger, search pipeline, voice approval, kill, rollback, a live Claude agent on LangGraph, and 44 acceptance tests that run against the Atlas cluster.

Mocked or limited: the business systems (orders, payments, CRM, email) are collections. Identities are demo keys. The ledger is append-only by convention plus a hash chain, not yet by database role. The similarity threshold is tuned on a small seed set. The scoreboard's agent is scripted to attempt each attack, and the model baseline is three trials per case.

## What I would like your view on

**MongoDB search**
1. We use the `$rerank` score as a threshold inside an authorization decision. Would you stand behind that, or threshold differently?
2. A new document was searchable about 1.4 seconds after insert. Is there a way to know a specific document is indexed without querying for it?

**MongoDB product**
3. Agent Engine's policy engine is allowlists and budgets today. Would a layer like this sit beside it or inside it?

**Identity**
4. Every ledger entry names two principals, the agent and the human it acts for. Would you expect a delegated token to carry that instead?

**Fintech**
5. What would your risk team need to see before an agent issues refunds under a limit unsupervised? Is "resembles a refused case" a signal they would trust?

**Voice**
6. Is a spoken approval with an on-screen challenge code enough, or would you want speaker verification?

**Everyone**
7. What is the first thing you would try to break?
8. Which twenty seconds would you cut from the demo?
