# 03 Architecture

## 1. Components

```
 Demo agent (LangGraph)        Claude Desktop / Claude Code (stretch)
          |                               |
          +---------- MCP tools/call -----+
                          |
                 +------------------+        change streams
                 |  Warrant gateway |<-------------------------+
                 |  (the product)   |                          |
                 +------------------+                          |
                   |      |      |                             |
        identity   | policy| ledger (transaction)              |
                   v      v      v                             |
                 +------------------+        +----------------------------+
                 |  MongoDB Atlas   |<------>| Control API + reviewer UI  |
                 |  (sandbox)       |  SSE   | kill, rollback, approvals  |
                 +------------------+        +----------------------------+
                          ^                             ^
                          |                             |
                 Mock business systems           ElevenLabs voice agent
                 (orders, payments, CRM, email)  (stretch)
```

| Component | Responsibility | Suggested tech |
|---|---|---|
| Gateway | Intercept every tool call: identify, decide, warrant, record, execute, verify | Python, FastMCP with tool-call middleware. Fallback: a plain Python wrapper around tool functions |
| Policy engine | Evaluate stored policies against the request and history | Pure Python evaluator over policy documents |
| Control API | Runs, kill, rollback, approvals, reconstruction, event stream | FastAPI |
| Reviewer console | Live timeline and controls | One page, plain React or HTML, fed by server-sent events |
| CLI | `replay`, `verify`, `seed`, `demo` | Python (Typer or argparse) |
| Demo agent | Works the refund queue through the gateway | LangGraph with the MongoDB checkpointer, LangSmith tracing on |
| Mock systems | Orders, payments, CRM, email outbox | Collections in the same Atlas cluster, behind tool functions |

The gateway is the product. If the MCP proxy route costs more than 45 minutes, switch to the wrapper fallback: the demo agent's tools are plain functions decorated by the gateway. Everything else in this document stays the same.

## 2. The tool-call flow

1. **Receive** `tools/call` with: agent key, run ID, step number, tool name, arguments, reason.
2. **Identify.** Look up the identity by key hash. Refuse if unknown or suspended. Load the human it acts for.
3. **Resolve the resource.** For tools that touch a record, load the facts policy needs (for example the order's region and total).
4. **Decide, inside a transaction:**
   - Re-read the run. If it is killed, refuse.
   - Evaluate policies. Deny beats step-up beats allow. Default deny.
   - Write the decision ledger entry.
   - If allow: insert the warrant (unique on run and step).
   - If step-up: insert an approval request and mark the step paused.
   - Commit.
5. **Execute** (allow only). Capture the before-image of any record to be changed. Call the downstream tool with an idempotency key derived from the warrant ID. Mark the warrant used.
6. **Verify.** Read the target back. Record `verified: true` or false with what was found.
7. **Record** the execution and verification ledger entries, with result digest, before-image reference and the LangSmith trace ID.
8. **Return** the result, or a structured refusal the agent can read (`DENIED`, `STEP_UP_PENDING`, `KILLED`), including the rule that fired.

Step-up resume: when an approval is decided, the control API writes the approval ledger entry and, if approved, issues the warrant. The agent retries the step (it polls or is notified) and proceeds from step 5.

## 3. Kill and rollback

**Kill**
- The reviewer sets `runs.status = "killed"` with who and why.
- A change stream on `runs` flips an in-memory flag in the gateway and pushes the event to the console.
- The decision transaction re-reads the run, so there is no race window even if the stream lags.
- Unused warrants for the run are set to revoked in one update.
- A call already executing is allowed to finish and is recorded. It becomes a candidate for rollback.

**Rollback**
- Walk the run's executed, reversible steps in reverse order.
- Refund: insert a reversal entry. CRM update: restore the captured before-image.
- Irreversible steps (email) are reported as "not undone, follow-up needed".
- Each compensation is a ledger entry of type `rollback`. The run ends in status `rolled_back`.

Before-images: the gateway captures them itself by reading the record before writing. If the sandbox allows it, also enable change stream pre- and post-images on the mock system collections and mention it in the demo, but do not depend on it.

## 4. Atlas data model

Database: `warrant`. Mock systems: `sys_orders`, `sys_payments`, `sys_crm`, `sys_outbox`.

### `identities`
| Field | Notes |
|---|---|
| `_id` | For example `agent:refund-agent-7`, `human:dana` |
| `kind` | `agent`, `human`, `service` |
| `display` | Name |
| `on_behalf_of` | Human ID, for agents |
| `class` | For example `refund-agent` |
| `regions`, `scopes` | Arrays used by policy |
| `key_hash` | SHA-256 of the API key, agents only |
| `status` | `active`, `suspended` |

Index: unique on `key_hash` (sparse).

### `policies`
| Field | Notes |
|---|---|
| `_id` | For example `P-002` |
| `version` | Integer, incremented on change |
| `effect` | `allow`, `deny`, `step_up` |
| `match` | Tool name or pattern, identity class |
| `when` | A small condition list: field, operator, value. Fields come from the request, the resource, the identity, or a named history metric |
| `description` | Human-readable rule, shown to reviewers |
| `status` | `active`, `retired` |

Keep the condition language tiny: `eq`, `ne`, `lte`, `gt`, `in`, `not_in`. History metrics (for P-007) are named aggregations run against the ledger.

### `runs`
`_id`, `agent_id`, `on_behalf_of`, `goal`, `status` (`running`, `paused`, `killed`, `completed`, `rolled_back`), `started_at`, `ended_at`, `kill` (`by`, `at`, `reason`), `last_hash`, `next_seq`.

### `warrants`
| Field | Notes |
|---|---|
| `_id` | Warrant ID |
| `run_id`, `step` | Unique compound index: one warrant per step |
| `agent_id`, `on_behalf_of` | |
| `tool`, `args_digest` | Digest of canonical arguments |
| `policy_refs` | Array of policy ID plus version |
| `status` | `issued`, `used`, `revoked`, `expired` |
| `issued_at`, `expires_at` | TTL index on `expires_at` for unused warrants |
| `approval_id` | When issued after a step-up |

Schema validation: strict, `validationAction: "error"`.

### `ledger`
| Field | Notes |
|---|---|
| `_id` | |
| `run_id`, `seq` | Unique compound index. `seq` is allocated from `runs.next_seq` in the same transaction |
| `ts` | |
| `type` | `decision`, `execution`, `verification`, `approval`, `kill`, `rollback`, `violation` |
| `actor` | Identity ID |
| `on_behalf_of` | |
| `step`, `tool` | |
| `reason` | The agent's stated reason |
| `decision` | `allow`, `deny`, `step_up` (decision entries) |
| `policy_refs` | |
| `warrant_id` | |
| `payload` | Arguments (redacted where needed), result digest, before-image reference, verification detail |
| `trace_id` | LangSmith |
| `prev_hash`, `hash` | Per-run chain. `hash` is SHA-256 over `prev_hash` plus the canonical entry |

Schema validation: strict with enums, `additionalProperties: false`, `validationAction: "error"`.
Append-only: connect the gateway with a database user whose role has insert and find on `ledger` and no update or remove. If the sandbox does not allow custom roles, rely on the hash chain and say so.

### `approvals`
`_id`, `run_id`, `step`, `request` (tool, arguments, reason, rule that escalated), `status` (`pending`, `approved`, `denied`, `expired`), `approver_id`, `channel` (`web`, `voice`), `evidence` (conversation ID, transcript excerpt, challenge code), `created_at`, `expires_at` (TTL), `decided_at`.

### `precedents` (P2)
`_id`, `summary` (one sentence describing the request and context), `decision`, `approver_id`, `approval_id`, `embedding` or an auto-embedded text field, `created_at`. One Atlas Vector Search index with a filter on `tool`.

### Demo agent state
The LangGraph MongoDB checkpointer writes to its own `checkpoints` and `checkpoint_writes` collections. Leave them alone.

## 5. Control API contract

| Method and path | Purpose |
|---|---|
| `POST /runs` | Start a run for an agent and goal. Returns run ID |
| `GET /runs/{id}` | Run status and summary |
| `POST /runs/{id}/kill` | Body: who, reason |
| `POST /runs/{id}/rollback` | Body: who. Returns the compensation report |
| `GET /runs/{id}/reconstruct` | The ordered account of the run |
| `GET /runs/{id}/verify` | Chain verification result |
| `GET /approvals?status=pending` | Approval inbox |
| `POST /approvals/{id}/decision` | Body: approver, decision, channel, evidence |
| `GET /precedents/similar?approval_id=` | Closest precedents (P2) |
| `GET /events` | Server-sent events fed by change streams on `ledger`, `runs`, `approvals` |

Fix this contract first. It lets the gateway, console and agent be built in parallel.

## 6. Failure modes to design for

| Failure | Behavior |
|---|---|
| Transaction fails at decision time | Tool does not run. The agent gets a retryable error |
| Tool executes but the execution ledger write fails | The warrant is already `used`, and the decision entry exists. On restart, a reconciler finds used warrants without execution entries, verifies the effect by reading back, and writes the missing entries |
| Kill arrives during execution | The call finishes and is recorded. The next call is refused |
| Agent retries a step | Unique index on run and step returns the existing warrant. The idempotency key prevents a double effect |
| Model is down or slow during the demo | Scripted agent mode issues the same calls without a model |
| Change stream drops | The transaction re-check still enforces kill. The console falls back to refetch |

## 7. Repository layout (proposed)

```
/docs                 this spec pack
/gateway              gateway, policy engine, ledger, warrants
/control              FastAPI control API, SSE
/console              reviewer console (one page)
/agent                demo agent, scripted mode
/systems              mock business systems and tools
/cli                  seed, demo, replay, verify
/voice                ElevenLabs agent config and client (stretch)
README.md             what it is, how to run, what was built today
```
