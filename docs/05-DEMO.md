# 05 Demo

The live slot may be as short as 1 minute (the earlier plan assumed about 3). The core script below fits 60 seconds and is also the 1-minute video. If the slot turns out to be 3 minutes, add the items under "If you have 3 minutes".

If there is room for one extra sentence, or a judge asks: "Everything you are about to see was built since 10:45 this morning."

## The story in plain words

An AI agent that can move money obeys every written rule and still pays requests nobody wrote a rule for, and afterwards nobody can say who allowed it. Warrant is a checkpoint between the agent and the money: every action is checked in MongoDB Atlas, first against the written rules and then against every decision a human has made before, and the decision is recorded in the same transaction. What is special is that Sam says no once, out loud, and about a second later Atlas has stored, embedded and indexed that ruling, so the next similar request is stopped, citing his words, with no retraining, no prompt edit and no new rule.

Who is who: Sam runs payments at a freight company and is the only human in the story. An AI support agent handles refund requests for him. A customer asks for a refund.

## Setup

    ./warrant demo --scripted        # resets, then serves http://127.0.0.1:8000

- Open http://127.0.0.1:8000 in Chrome, in a wide window. Voice needs the microphone, so allow it when Chrome asks.
- Wear the headset for the voice step.
- Click an empty area of the page before using the keys, so they are not typed into a text box.
- Press **Reset** between runs. It waits until Atlas has dropped the last session's rulings from the search index, and it restores the threshold, so step 1 is paid again.

The page has four tabs: **Demo**, **MongoDB live**, **Proof** and **Audit trail**. Demo opens with "Meet Sam" and three cards: The problem, The checkpoint, The payoff. The demo is keys **1**, **2** and **3**. Key **4** undoes the first payment. Key **5** is the other direction, where Warrant asks Sam.

## The 60-second script

| Time | Say | Do |
|---|---|---|
| 0:00 | "This is Sam. An AI agent handles refunds for him. Watch this one." | Press **1**. Step 1, "A request no rule covers" |
| 0:06 | "Three hundred dollars, to someone else's card. It broke no rule, so it was paid. A person would have said no." | The request is allowed and paid |
| 0:14 | "Sam is watching, and he speaks up." | Press **2**. Step 2, "Sam speaks up". Warrant says "Warrant here. Go ahead, Sam." |
| 0:18 | To Warrant: "Hey Warrant, Sam here. Flag this one. Refunds only go back to the original payment method." | The ruling appears in the Atlas column as a new document |
| 0:28 | Warrant confirms and asks about the threshold. Answer: "Make it eighty percent." | The policy diff appears: 0.7 becomes 0.8, version 2 |
| 0:40 | "Two writes to MongoDB Atlas. His ruling, which Atlas embedded itself, and one number on the rule." | Point at the "MongoDB Atlas, live" column |
| 0:46 | "The same request again." | Press **3**. Step 3, "It never happens again" |
| 0:50 | "Stopped. It cites what Sam said twenty seconds ago. Nothing was retrained." | The request is held, with Sam's words on the card |
| 0:56 | "Twelve attacks: twelve get through with no gate, one with Warrant, zero after one ruling." | Open the **Proof** tab |

The voice exchange in step 2 is the long part, about 25 seconds. To save about 10 seconds, answer the threshold question with "No, keep it".

Fallbacks for step 2: type the rule and press **Flag it**, or use **Type to Warrant** for the same conversation in text. The threshold also has a slider in the Atlas column. If the network dies, play the video and narrate.

Do not say "no rule was edited" after changing the threshold. Say "nothing was retrained and no rule was rewritten".

## The 3-minute live demo

Use the **Pitch** tab for the story and the **Demo** tab for the proof. **P** opens Pitch, the arrow keys move between slides, **N** shows speaker notes, and **1**, **2**, **3** jump to the demo from anywhere.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Pitch 1, The problem | "AI agents follow the rules. The damage happens where no rule exists. We measured it: Claude, with the rules in its prompt, broke none of them and still paid out six times in nine where no rule was written." |
| 0:25 | Pitch 3, Warrant | "Warrant is a checkpoint between the agent and the money. The written rules first, then every decision a human has already made." |
| 0:40 | Demo, keys 1, 2, 3 | The 60-second script above |
| 1:45 | Pitch 5, What MongoDB Atlas made possible | "One cluster. Atlas embedded Sam's ruling itself, one aggregation searched it, and one transaction recorded the decision." |
| 2:10 | Pitch 6, Proof | "Twelve attacks: twelve, one, zero. Forty-six tests against the live cluster." |
| 2:30 | Pitch 7, The bigger picture | "Anywhere an agent can do something you cannot easily undo." |
| 2:45 | MongoDB live, if a judge asks | Show the real documents and the search pipeline |

## If you have 3 minutes

Run the 60-second script first, then add these in order:

- **Undo.** Press **4**, "Undo the first payment". The $300 refund from step 1 is reversed. The email is marked "cannot undo", because it was already sent.
- **Warrant asks Sam.** Press **5**. A $900 request is over the agent's limit, so the checkpoint asks Sam. He decides by voice and reads the three-digit code, or types a reason and clicks **Deny**.
- **MongoDB live.** Open the tab: the collections, what the database enforces on each, the search pipeline and the ledger's validator.
- **The full support queue.** Open **Audit trail** and run the full queue. It shows an allowed refund, a refusal because the order is outside the agent's region, and an injected $5,000 transfer that is refused.
- **Kill.** In **Audit trail**, press **Kill run** while a run is going. The agent's next call is refused and recorded.
- **Replay.** In a terminal, run `./warrant replay`. It prints who acted, on whose behalf, what, why, which rule, and whether the effect was verified.
- **The numbers.** Open **Proof** and give the model-alone result: Claude Opus 5.5, with the rules in its prompt and no gate, broke a written rule in 0 of 15 runs and still paid out in 6 of 9 runs where no rule was written.
- **What was hard.** "The decision, the warrant and the ledger entry commit in one transaction, and a warrant is bound to the exact arguments, so a replayed or altered call is refused."

For the finals, open with the buyer: "If your agents move money or touch customer records, this is the layer your risk team asks for." You can also open with your own story from this morning: an AI support agent refunded you in two minutes with no human involved.

## 1-minute video

The video is the 60-second script above, recorded in one take.

- Record with Shift-Command-5: Record Selected Portion, microphone on, Show Mouse Clicks.
- The recorder captures the microphone and not system audio. So the agent's voice must come through the speakers, or use the typed reason for step 2.
- Trim in QuickTime so it runs under 60 seconds.
- Upload to YouTube as Unlisted, then play the link in a private window with sound.
- Start recording by 3:45 PM.

The submission asks for code as well as functionality. If the take runs short, end on two seconds of `gateway/precedents.py` showing the aggregation.

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
