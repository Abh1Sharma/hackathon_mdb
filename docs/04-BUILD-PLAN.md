# 04 Build plan

Hacking: 10:45 AM to 5:00 PM. Target: submit at 4:45 PM. Every milestone ends in a gate. If a gate is not green by its time, cut scope using the cut line, do not push the schedule.

## Timeline

| Time | Milestone | Output | Gate (must be true to move on) |
|---|---|---|---|
| 9:00 to 10:45 | Pre-hack, no code | Check-in, team, sandbox checks, questions answered | You know the sandbox limits and which stretch goal is realistic |
| 10:45 to 11:30 | **M0 Foundations** | Public repo with docs committed, Atlas connected, collections with validators and indexes, seed and reset command, mock systems and tools | `seed` runs clean, and a bad ledger insert is rejected by the database (AT-10) |
| 11:30 to 1:00 | **M1 Gateway core** | Identify, decide, warrant, ledger, execute, verify. Scripted agent runs T1, T2, T4, T5 through the gateway | AT-01, AT-02, AT-03 pass from the terminal |
| 1:00 to 1:15 | Lunch | Eat. Rerun the gate checks | |
| 1:15 to 2:30 | **M2 Control and visibility** | Control API, change-stream event feed, console timeline, Kill, reconstruction view, `replay` CLI | AT-06 and AT-11 pass. You can demo the core story end to end |
| 2:30 to 3:30 | **M3 Depth** | Step-up approval (web), rollback, hash chain and `verify`, replay and digest checks, history policy P-007, LangGraph agent with LangSmith traces | AT-04, AT-05, AT-07, AT-08, AT-09, AT-12 pass |
| 3:30 to 4:00 | **M4 One stretch** | Voice approval, or precedents. Not both | It works twice in a row, or it is removed from the demo |
| 4:00 to 4:30 | **Freeze and rehearse** | No new features. Reset, run the full demo three times, fix only what breaks | Three clean runs |
| 4:30 to 4:45 | **Package** | 1-minute video, README, repo public check, teammates added to the submission | Submission form complete |
| 4:45 | **Submit** | | |
| 5:15 to 6:45 | Round 1 | Live demo | |

## Cut lines

| If this is not done by | Then cut |
|---|---|
| 1:00 PM (M1 gate) | The MCP proxy. Use the plain wrapper around tool functions. Drop FR-23 |
| 2:30 PM (M2 gate) | The React console. Serve one plain HTML page with a timeline and three buttons. Keep the CLI |
| 3:30 PM (M3 gate) | In this order: P-007 history policy, LangSmith links, hash chain verify UI (keep the CLI), rollback of CRM (keep refunds). Do not start M4 |
| 4:00 PM | The stretch goal, whatever state it is in |

Never cut: the policy gate, the ledger, the kill switch, the reconstruction. Those four are the project.

## Task breakdown

### M0 Foundations (45 min)
- Repo, licence, `.gitignore`, `.env.example`. Commit the docs folder first.
- Connection module. Confirm transactions and change streams work on the sandbox cluster.
- Create collections with validators and indexes from `03-ARCHITECTURE.md` section 4.
- Seed: identities (agent, Dana, an approver), policies P-001 to P-008, five tickets, orders, customers.
- `reset` command: drop and reseed in under 10 seconds.
- Mock tools as plain functions over the `sys_*` collections.

### M1 Gateway core (90 min)
- Policy evaluator with the six operators and precedence rules. Unit-test it against the seed policies.
- Decision transaction: re-read run, evaluate, write ledger entry, insert warrant.
- Execute path: before-image capture, idempotency key, mark warrant used, read-back verification, ledger entries.
- Structured refusals.
- Scripted agent: a fixed list of tool calls for the five tickets, including the injected transfer attempt.

### M2 Control and visibility (75 min)
- Control API endpoints from the contract.
- Change stream listeners on `runs`, `ledger`, `approvals`, fanned out as server-sent events.
- Kill: status update, warrant revocation, gateway flag.
- Console: timeline, run header with Kill and Rollback, approval inbox, step detail drawer.
- `replay` CLI.

### M3 Depth (60 min)
- Step-up flow: approval request, pause, decision endpoint, warrant issue, agent retry.
- Rollback with compensators and report.
- Hash chain on write, `verify` command, tamper demo script.
- Warrant replay and digest mismatch checks.
- P-007 aggregation.
- Swap the scripted agent for the LangGraph agent with the MongoDB checkpointer. Keep scripted mode behind a flag.

### M4 Stretch (30 min, pick one)
- **Voice approval** if the room and network allow it, you have a headset, and an ElevenLabs key works. Follow `06-VOICE-ELEVENLABS.md` option A.
- **Precedents** otherwise: embed approval summaries, one vector index, show the top 2 precedents in the approval card.

## Working with Claude Code

One session is enough for M0 and M1. From M2, parallel sessions pay off, because the API contract separates the work:

| Session | Owns | Must not touch |
|---|---|---|
| A | `/gateway`, `/systems`, `/cli` | `/console` |
| B | `/control`, `/console` | `/gateway` internals |
| C (from M3) | `/agent`, `/voice` | `/gateway` internals |

Use separate git worktrees or commit often on one branch and pull before each task. Give every session `CLAUDE.md` and the relevant acceptance test IDs. Ask for the acceptance test to be written first, then the code to pass it.

With a teammate: one person takes sessions A and C, the other takes B plus the demo script, video and submission form.

## Definition of done for the submission

- [ ] Repo is public and has a README stating which problem statement it addresses and what was built today.
- [ ] All P0 acceptance tests pass on a fresh seed.
- [ ] `reset` then `demo` reproduces the stage demo.
- [ ] 1-minute video uploaded and its link opens in a private window.
- [ ] Every teammate is added on the submission page.
- [ ] The project lives in the hackathon's Atlas sandbox organization.
