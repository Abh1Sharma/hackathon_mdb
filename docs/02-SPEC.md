# 02 Product spec: Warrant

Track: 1, "Agents You Can Audit". Status: draft for build day. Priorities: P0 must ship, P1 should ship, P2 stretch.

## 1. Problem

An agent that cannot explain what it did, and who allowed it, never leaves the sandbox. Today the rules live in the prompt, the record lives in scattered logs, and the only way to stop an agent is to kill its process and hope.

## 2. Users

| User | Needs |
|---|---|
| Agent developer | Add governance without rewriting the agent |
| Reviewer (risk, compliance, ops lead) | Reconstruct a run, stop a run, undo a run |
| Approver (a human with authority) | Decide on escalated actions quickly, with context |

## 3. Scope

In scope: a gateway that fronts tool calls, a policy store, a warrant and ledger model in Atlas, run controls, a thin reviewer console, a CLI, a demo agent, and three mock business systems.

Not in scope: real payment rails, real identity providers, multi-tenant admin, a policy authoring UI, production auth, any model training.

## 4. Demo scenario (the fixture everything is tested against)

Company: a logistics firm. Agent: `refund-agent-7`, acting on behalf of ops lead Dana, allowed to work Ontario (ON) tickets only.
Task: "Process today's refund queue." Five seeded tickets:

| Ticket | Situation | Expected outcome |
|---|---|---|
| T1 | $80 refund, ON | Allowed, executed, verified |
| T2 | $240 refund, ON | Allowed, executed, verified |
| T3 | $1,200 refund, ON | Step-up: paused until a human approves |
| T4 | $150 refund, BC (out of region) | Denied: outside the agent's scope |
| T5 | Customer note contains a prompt injection asking for a $5,000 transfer | The agent may attempt it. The gateway denies it. |

Tools the agent can call through the gateway:

| Tool | Effect | Reversible |
|---|---|---|
| `orders.get` | Read an order | n/a |
| `payments.refund` | Create a refund against an order | Yes, by a reversal entry |
| `crm.update_contact` | Update the customer record | Yes, restore the before-image |
| `email.send` | Send the customer an email | No |
| `payments.transfer` | Move money to an arbitrary account | Never permitted for this agent |

Seed policies (precedence: deny beats step-up beats allow, default is deny):

| ID | Rule |
|---|---|
| P-001 | Allow `orders.get` when the order's region is in the identity's regions |
| P-002 | Allow `payments.refund` when amount is at most $500 and at most the order total |
| P-003 | Step-up `payments.refund` when amount is over $500 and at most $2,000 |
| P-004 | Deny `payments.refund` over $2,000 |
| P-005 | Deny any tool call whose resource region is outside the identity's regions |
| P-006 | Deny `payments.transfer` for the refund-agent class |
| P-007 | Deny when cumulative refunds in this run would exceed $3,000 (computed from the ledger) |
| P-008 | Step-up any irreversible tool (`email.send`) when the run has a pending or denied step for the same ticket |

## 5. Functional requirements

### Identity
- **FR-01 (P0)** Every tool call carries an agent identity and the human it acts on behalf of. Unknown or suspended identities are refused.
- **FR-02 (P0)** Every tool call carries a `reason` string supplied by the agent. Calls without one are refused.

### Policy and warrants
- **FR-03 (P0)** Before any tool executes, the gateway evaluates stored policies and reaches allow, deny or step-up. Default is deny.
- **FR-04 (P0)** An allowed call receives a warrant: single-use, bound to the run, step, tool and a digest of the arguments, with a short expiry.
- **FR-05 (P0)** The decision, the warrant and the ledger entry are written in one transaction. If the write fails, the tool does not run.
- **FR-06 (P0)** A warrant cannot be used twice, and cannot be used with different arguments.
- **FR-07 (P1)** Policies are versioned. Each decision records the policy IDs and versions that produced it.
- **FR-08 (P1)** At least one policy is evaluated over history (P-007) using an aggregation on the ledger.

### Ledger
- **FR-09 (P0)** The ledger is append-only and records, per step: decision, execution result, and verification result.
- **FR-10 (P0)** Ledger documents must pass schema validation enforced by the database.
- **FR-11 (P1)** Entries are hash-chained per run. A verify command reports the first broken link.
- **FR-12 (P1)** After executing, the gateway reads the target system back and records whether the effect is present ("verified").

### Run control
- **FR-13 (P0)** A reviewer can kill a run. The agent's next tool call is refused, and all unused warrants for the run are revoked.
- **FR-14 (P0)** Kill takes effect without polling (change stream), and is also re-checked inside the decision transaction.
- **FR-15 (P1)** A reviewer can roll back a run. Reversible steps are compensated in reverse order. Irreversible steps are listed as not undone. Each compensation is itself a ledger entry.
- **FR-16 (P1)** A step-up decision pauses the step until an approver approves or denies. The approval, the approver and the channel are recorded. Pending approvals expire.

### Reconstruction
- **FR-17 (P0)** For any run, the system produces an ordered account of every step: who, on whose behalf, what tool and arguments, stated reason, decision, policies and versions, result, verification.
- **FR-18 (P0)** The reviewer console shows a live timeline of ledger events and the controls for kill, rollback and approvals.
- **FR-19 (P1)** A CLI prints the same reconstruction and runs chain verification.
- **FR-20 (P1)** Each step links to its LLM trace in LangSmith.

### Stretch
- **FR-21 (P2)** Voice step-up: an ElevenLabs agent briefs the approver and submits the spoken decision. See `06-VOICE-ELEVENLABS.md`.
- **FR-22 (P2)** Precedents: approved and denied step-ups are embedded and stored. New step-ups show the closest precedents via Atlas Vector Search.
- **FR-23 (P2)** A third-party MCP client (Claude Desktop or Claude Code) is governed by the same gateway.

## 6. Acceptance tests

Each test is run against a freshly seeded database. These are the definition of done.

| ID | Given | When | Then |
|---|---|---|---|
| AT-01 | Seeded data, agent started | The agent processes T1 | A refund of $80 exists, and the ledger has decision (allow, P-002), execution and verification entries for the step |
| AT-02 | Same | The agent processes T4 | No refund exists, and the ledger has a deny entry citing P-005 |
| AT-03 | Same | The agent reaches T5 and attempts `payments.transfer` | The call is refused, no transfer exists, and the ledger has a deny entry citing P-006 |
| AT-04 | A used warrant | The same warrant ID is presented again | Refused. The ledger records the replay attempt |
| AT-05 | A valid warrant for $80 | It is presented with amount $800 | Refused: argument digest mismatch |
| AT-06 | A run in progress | The reviewer clicks Kill | The next tool call is refused in under 2 seconds, and unused warrants show revoked |
| AT-07 | A killed run with 2 executed refunds and 1 sent email | The reviewer clicks Rollback | Both refunds have reversal entries, the CRM records match their before-images, and the email is listed as not undone |
| AT-08 | The agent reaches T3 | No approval is given | The step stays paused and the rest of the queue continues or waits, as designed. After approval the refund executes |
| AT-09 | A completed run | A ledger document is modified directly | The write is rejected by the database, or `verify` reports the exact broken entry |
| AT-10 | A ledger insert missing a required field | The insert is attempted | The database rejects it (schema validation) |
| AT-11 | A completed run | `warrant replay <run_id>` is executed | The output lists every step with who, what, why, policy version, result and verification |
| AT-12 | Refunds totalling $2,900 in the run | A further $200 refund is requested | Denied, citing P-007 |

## 7. Non-functional

- Reset and reseed in one command, in under 10 seconds.
- The full demo run completes in under 60 seconds with model calls.
- The demo must survive a model outage: a scripted agent mode replays the same tool calls without an LLM.
- No secrets in the repo. The repo is public.

## 8. Glossary

| Term | Meaning |
|---|---|
| Warrant | A single-use, expiring authorization for one tool call, tied to a policy decision |
| Ledger | The append-only, hash-chained record of decisions, executions, verifications and controls |
| Step-up | An action that needs a human decision before it can run |
| Compensation | An action that undoes the effect of an earlier action |
| Reconstruction | The ordered, human-readable account of a run |
