# 05 Demo

Round 1: about 3 minutes live plus 1 to 2 minutes of Q&A, in a room, to a small group of judges. Finals: 3 minutes on stage plus 2 minutes of Q&A. The submission also needs a 1-minute video.

Rule to respect: show only what was built today. Say so once: "Everything you are about to see was built since 10:45 this morning."

## Screen layout

Left half: reviewer console (timeline, run controls). Right half: terminal with the agent's output. Keep Atlas Data Explorer open in a second tab for the tamper moment.

## 3-minute script

| Time | Say | Do |
|---|---|---|
| 0:00 | "Agents stall at pilot for one reason: nobody can prove what the agent did, who allowed it, or stop it. Rules in a prompt are suggestions. Warrant puts the rules in the database." | Title on screen |
| 0:15 | "This is a refunds agent at a logistics company, working a queue of five tickets. Every tool call goes through our gateway. No call runs without a warrant: a single-use authorization checked against policy in Atlas, before the action." | Start the run. Timeline fills: T1 and T2 allowed, executed, verified |
| 0:40 | "Ticket 4 is in British Columbia. This agent is scoped to Ontario. Denied before it ran, and here is the rule and its version." | Click the denied entry |
| 0:55 | "Ticket 5 has a prompt injection in the customer note. The model falls for it and tries to transfer $5,000. The gateway does not care what the model thinks. Denied." | Show the terminal line where the agent attempts the transfer, then the deny entry |
| 1:15 | "Ticket 3 is a $1,200 refund, over this agent's limit. That is a step-up. The run pauses for a human." | Approval card appears. Approve (button, or voice if built) |
| 1:35 | "Now the part everyone asks about. Stop it." | Click Kill mid-run. Next call is refused. Warrants show revoked |
| 1:50 | "And undo it. Reversible steps are compensated from the record's before-image. The email it already sent cannot be unsent, and we say so." | Click Rollback. Show the report |
| 2:10 | "A reviewer can reconstruct the whole run: who, on whose behalf, what, why, which policy version, and whether the effect was verified." | Run `replay` in the terminal |
| 2:25 | "The ledger is append-only and hash-chained. Watch me try to edit it." | Attempt the edit in Atlas. Rejected, or `verify` flags the entry |
| 2:40 | "Under the hood: schema validation on the ledger, the decision and the record in one transaction, single-use warrants on a TTL index, change streams for the kill switch. It is a gateway, so it works with any agent that calls tools." | Architecture slide or the Atlas collections view |
| 2:55 | "Warrant. No agent action without a warrant." | |

If something breaks: switch to scripted agent mode (no model calls) and keep talking. If the network dies: play the 1-minute video and narrate.

## Finals additions

Finals weight creativity and impact equally with the rest. Add, in this order if built:
- Voice step-up at 1:15, spoken live. One exchange, under 15 seconds.
- Precedent card: "It found a similar approval from last week and showed it to the approver."
- A different agent (Claude Desktop) governed by the same gateway: one blocked call.

Open with the buyer: "If you run agents that move money or touch customer records, this is the layer your risk team is going to ask for."

## 1-minute video script

| Time | Content |
|---|---|
| 0:00 to 0:08 | Problem in one sentence over the title |
| 0:08 to 0:25 | Run starts, allowed steps, the out-of-scope deny |
| 0:25 to 0:35 | Prompt injection denied |
| 0:35 to 0:47 | Kill, then rollback |
| 0:47 to 0:55 | `replay` and the tamper attempt |
| 0:55 to 1:00 | Name and one line |

Record it at 4:30 PM from a clean reset, screen plus voice, one take. Upload unlisted and test the link in a private window.

## Q&A bank

**Why MongoDB for this and not Postgres?**
The ledger entries, warrants, policies and tool payloads are differently shaped documents that evolve per tool. Schema validation gives strictness where it matters and flexibility in the payload. Change streams give the kill switch and live view without extra infrastructure. Policy over history is one aggregation next to the data.

**What happens if the gateway crashes between executing and recording?**
The warrant is marked used before execution and the decision entry already exists. On restart, a reconciler finds used warrants with no execution entry, reads the target system to see whether the effect happened, and writes the missing entries. The idempotency key prevents a double effect on retry.

**Is the kill switch really immediate?**
The change stream gives sub-second notification. Correctness does not depend on it: every decision transaction re-reads the run status, so a killed run cannot get a new warrant even if the stream lags.

**How is this different from guardrails or prompt rules?**
Those run inside or beside the model and can be argued with. This is enforcement at the tool boundary, outside the model, with a database record of every decision.

**Can someone with database access rewrite history?**
The gateway's database user can insert and read the ledger, not update or delete. Entries are hash-chained, so any edit by a privileged user is detectable. (If the sandbox did not allow a custom role, say: in the sandbox we rely on the chain, in production you add the role.)

**How do identities work in production?**
The demo uses API keys. The model maps directly to workload identity plus delegated user identity from an identity provider: the agent's credential says which agent, the token it carries says on whose behalf.

**How does it scale to hundreds of agents?**
Decisions are indexed lookups and one small transaction. The chain is per run, so runs do not contend. Policies are data, so adding a team is adding documents.

**What about actions that cannot be undone?**
They are marked irreversible in the tool registry, policy can require a step-up for them, and rollback reports them honestly.

**What did you build today, and what is a library?**
Built today: gateway, policy engine, warrant and ledger model, kill and rollback, console, CLI, mock systems, demo agent. Libraries: the MongoDB driver, the web framework, LangGraph and its MongoDB checkpointer for the demo agent's own state.

**Where does Vector Search come in?**
Precedents: human decisions are embedded and retrieved when a similar request appears. (If not built, say it is the next step and why.)

## Teammate runbook (if you are not in the room)

1. Open the repo README. Run the reset command, then the demo command.
2. Open the console URL printed in the terminal. Arrange the screen as in "Screen layout".
3. Follow the 3-minute script row by row. The buttons are labelled Kill, Rollback, Approve.
4. If the model is slow, add the scripted flag shown in the README.
5. For Q&A, the answers above are enough. If asked something you cannot answer, say "the gateway design doc in the repo covers that" and point to `/docs/03-ARCHITECTURE.md`.
6. Submission details and the video link are in the README footer.
