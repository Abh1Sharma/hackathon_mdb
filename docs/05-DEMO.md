# 05 Demo

Round 1: about 3 minutes live plus Q&A, to a few judges. Finals: 3 minutes on stage. The submission also needs a 1-minute video. This version replaces the script written the night before: it is built around the learning loop.

Say once: "Everything you are about to see was built since 10:45 this morning."

## Setup

    ./warrant demo --scripted        # resets, then serves http://127.0.0.1:8000

Console full screen. A terminal behind it with `./warrant replay` typed and not yet run. Headset on if using voice. The five demo steps are keys **1** to **5**. Click an empty area first so the keys are not typed into a text box.

Between rehearsals press **Reset**. It waits until Atlas has dropped the last session's rulings from the search index, so step 1 goes through again.

## Round 1 script (3:00)

| Time | Say | Do |
|---|---|---|
| 0:00 | "This morning an AI support agent refunded me in two minutes, with no human involved. Great for me. Now be that company. Here a customer asks for $300 back, sent to someone else's card. It is under every limit. Watch." | **1**. The customer's message appears, then: allowed, executed, verified |
| 0:16 | "Nothing broke a rule. A person would have said no. Rules only catch what someone wrote down." | |
| 0:24 | "Warrant sits between the agent and its tools. Every call: who is asking and for whom, policy stored in Atlas, a single-use warrant, all in one transaction." | **2**. Queue runs: allowed, refused by region, injected $5,000 transfer refused |
| 0:50 | "This one is over the limit, so a human decides. These are the closest past decisions, from one Atlas pipeline: vector and text search fused, then reranked." | Point at the pipeline strip and the precedents |
| 1:05 | Speak: "Deny. Refunds only go back to the original payment method." Then read the code | **3** (voice). Fallback: type the reason, press Deny |
| 1:35 | "Atlas embedded that ruling itself. There is no embedding code in this app." | "Learned" notice |
| 1:42 | "Same $300 request again." | **4**. Stopped: resembles the ruling, score about 0.82, my words on the card |
| 1:58 | "No rule was edited. Search can tighten a decision automatically. Only a human can loosen one." | |
| 2:08 | "And the one that got through at the start: undo it." | **5**. Refund reversed. Email marked "cannot undo" |
| 2:22 | "We measured it. Twelve attacks, scored by checks the agent never sees. No gate: twelve get through. Warrant: one. After that single ruling: zero. And every legitimate task still completes." | Point at the Red team panel |
| 2:36 | "What was hard: decision, warrant and ledger entry commit in one transaction, and a warrant is bound to the exact arguments, so a replayed or altered call is refused." | Terminal: `./warrant replay` |
| 2:45 | "Warrant. Policy is the statute, precedents are the case law, and both live in Atlas." | |

If something breaks: every step is also a button. If voice fails, type the reason. If the network dies, play the video and narrate.

## Finals (3:00, four criteria weighted equally)

Open with the buyer: "If your agents move money or touch customer records, this is the layer your risk team asks for." Keep steps 1, 3, 4 and 5. Cut the queue narration to one sentence. Close with the live Claude agent going through the same gate (`./warrant demo`, then **2**).

## 1-minute video

| Seconds | Shot |
|---|---|
| 0 to 5 | Console on screen. "A $300 refund that passes every rule. It shouldn't." |
| 5 to 12 | Step 1: it is paid. Caption: "Rules only catch what someone wrote down" |
| 12 to 40 | Uncut: deny the $900 request with a reason, the Learned notice, step 4 stopped with the citation |
| 40 to 52 | Proof: the aggregation in `gateway/precedents.py`, `pytest` passing, `git log` showing today's commits |
| 52 to 58 | "Warrant. Built today on MongoDB Atlas." |

Record with Shift-Command-5 (Record Selected Portion, microphone on, Show Mouse Clicks). The recorder captures the microphone, not system audio, so narrate over the voice step or use the typed reason. Trim in QuickTime. Upload to YouTube as Unlisted and play the link in a private window with sound. Start recording by 3:45 PM.

## One sentence for each judge

| Judge | Sentence |
|---|---|
| MongoDB search and product | "One aggregation: `$rankFusion` over an auto-embedding index and Atlas Search, then `$rerank` on 9.0, inside an authorization decision." |
| Identity (Okta) | "The ledger keeps the human who authorized separate from the agent that acted, and step-up is an out-of-band approval." |
| Fintech (Wealthsimple, Zafin) | "Defined human-approval points, a kill switch, and a traceable reason for every money movement." |
| Retrieval and research (Cohere, Vector Institute) | "Retrieved text is treated as untrusted, the reranker is one swappable stage, and the tests were written first." |
| Voice | "Voice is a channel, not the control. A challenge code binds it to the approver and the transcript is evidence." |
| Microsoft | "Per-call policy and chained logs exist already. We add warrants bound to the call, precedents, and undo." |

## Do not claim

- That Atlas Agent Engine lacks audit or human review. It has traces and a review action. The accurate gap is argument-level rules, default deny, in-flight policy changes and rollback, as documented in its preview.
- That Warrant is compliant with any regulation or guideline.
- That one vendor's reranker beats another's.
- That the hash chain makes the ledger tamper-proof. It makes edits detectable.
- That rollback is general. It compensates refunds and CRM updates in the mock systems.
- That Claude fails these attacks. With the rules in its prompt it broke a written rule in 0 of 15 runs. The measured gap is harm no rule covers: it paid two planted-claim refunds in 6 of 6 runs.
- That the scoreboard measures a model. Its agent is scripted to attempt each attack, which is the worst case.

## Q&A bank

**Why MongoDB and not Postgres?**
Ledger entries, warrants, policies and tool payloads are differently shaped documents. Schema validation is strict where it matters. Change streams give the kill switch and the live feed with no extra infrastructure. And the precedent search, embedding included, runs inside the database next to the data it protects.

**Why is search in an authorization path? Isn't that non-deterministic?**
Search only supplies a fact: is the closest past ruling a denial above a recorded threshold. Policy still decides, and that fact can only make the outcome stricter. The precedent, score and threshold are written into the ledger entry, so the decision is explainable afterwards. If search fails, the call goes to a human.

**What stops a bad ruling from poisoning everything?**
A denial can only cause more requests to reach a human. It cannot approve anything. Rulings carry who made them and through which channel. Review and expiry of precedents is the next thing to build.

**How is this different from Agent Engine's policy engine?**
As documented in preview, that is tool allowlists and budgets, checked against a snapshot taken when a run starts. Warrant decides per call on arguments, data and history, denies by default, and a kill or policy change applies to the next call of a running agent.

**How is this different from Microsoft's Agent Governance Toolkit?**
That already does per-call policy, hash-chained logs and kill switches. Warrant adds warrants bound to the call, precedent search and rollback, and keeps everything as data in the customer's own Atlas cluster.

**What if the gateway crashes between executing and recording?**
The warrant is already marked used and the decision entry exists, so the gap is detectable. The reconciler that repairs it is not built.

**Is the kill switch immediate?**
A change stream tells the gateway. Correctness does not depend on it: every call reads the run's status, and the decision transaction reads it again.

**Can someone with database access rewrite history?**
Edits are detectable through the hash chain. Preventing them needs a database user that can only insert into the ledger, which is a production step not done today.

**Did the model fall for the prompt injection?**
Claude declined both planted instructions on its own. That is the point: you cannot prove it will tomorrow. The scripted agent shows the run where the model does not resist, and the gateway refuses it.

**Isn't a good model enough?**
We measured it: Claude Opus 5.5, rules in its prompt, no gate, three trials. It broke a written rule in 0 of 15 runs, including the per-run cap. It also paid both planted-claim refunds every time, saying it ignored the planted text and that the amount was under its limit. Obedience was not the gap. Rules cover what someone wrote down, a prompt leaves no record, and four of our twelve attacks never touch the model at all.

**Your refund tool is a mock. What was actually prevented?**
The refund records a destination. The check for the redirect case looks at whether money went anywhere other than the original payment method. The first version of that check could not tell, the live model exposed it, and we fixed it.

**What did you build today, and what is a library?**
Built today: gateway, policy engine, ledger, precedent pipeline, kill and rollback, control API, console, CLI, mock systems, both agents, the tests. Libraries: PyMongo, FastAPI, LangGraph with its MongoDB checkpointer, the ElevenLabs browser SDK.

See `docs/ONE-PAGER.md` for the questions to ask judges before judging starts.
