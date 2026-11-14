# 06 The voice angle (ElevenLabs)

## Is it worth doing?

Yes, as a 30-minute stretch after the core is green, and only in the form below.

| For | Against |
|---|---|
| A separate prize: "Best Project Built with ElevenLabs" (3 months of the Scale tier). Fewer teams will integrate voice well, so the odds are better than for the main podium | The cash prizes do not depend on it |
| Finals weight creativity at 25%. A spoken approval is memorable | A loud room and venue Wi-Fi can wreck a live voice demo |
| It fits the product: a human authorizing a risky action is naturally a conversation | Voice bolted on for its own sake reads as a gimmick |
| One judge is the CTO of a voice AI company | 30 minutes spent here is 30 minutes not spent on depth |

Rule: voice is evidence and convenience on top of the approval flow. The approval flow must work by button first.

## Three ways to use voice, ranked

### A. Spoken step-up approval (recommended)

When policy escalates an action, a voice agent briefs the approver and takes the decision.

> "Refund agent 7, acting for Dana, wants to refund $1,200 on order 4417. The limit is $500. The stated reason is damaged goods with photos attached. A similar request was approved last Tuesday. Do you approve?"
> "Approve, this one only."
> "Please read the challenge code on your screen."
> "Four, one, nine."
> "Approved. Recorded under your name."

What makes it more than a gimmick:
- The briefing is generated from the approval request and the policy that escalated it, not canned.
- The challenge code shown in the console ties the voice to the logged-in approver (a simple step-up check).
- The conversation ID and transcript excerpt are stored in `approvals.evidence` and referenced from the ledger. The reviewer's reconstruction shows "approved by voice, transcript attached".

### B. Ask the auditor

A voice agent that answers questions over the ledger: "What did the refund agent do in the last run, and who authorized the large refund?" It calls a tool that runs the reconstruction query and reads back a summary. Good for a finals flourish, but it adds nothing to the core claims. Build only if A is done and working.

### C. The agent phones the approver

Same as A, over an outbound phone call to your mobile on speaker. Most theatrical, most fragile: it needs a Twilio number imported into ElevenLabs, a public webhook URL, and phone audio in a loud room. Skip unless everything else is finished by 3:00 PM.

## How to build option A

ElevenLabs agents have three kinds of tools: client tools that run in the browser, webhook tools that call your server, and built-in system tools such as ending the call.

Use **client tools in the browser**. The voice session runs inside the reviewer console through the ElevenLabs JavaScript SDK, and the client tools call your local control API directly. That avoids a public tunnel entirely.

Steps:
1. Create one agent in the ElevenLabs dashboard (or through their CLI or hosted MCP server from Claude Code). System prompt: you are an approvals officer, you brief the approver on exactly one request, you never decide yourself, you must collect the challenge code before submitting.
2. Pass the approval request into the session as dynamic variables: agent name, principal, tool, amount, limit, reason, closest precedent.
3. Define two client tools:
   - `submit_decision(approval_id, decision, note, challenge_code)` posts to `POST /approvals/{id}/decision` with channel `voice`.
   - `repeat_details(approval_id)` returns the request again if the approver asks.
4. In the console, the approval card gets a "Brief me" button that starts the session. The Approve and Deny buttons stay.
5. On session end, store the conversation ID in `approvals.evidence`. If time allows, fetch the transcript through the conversations API or a post-call webhook and store an excerpt.

If client tools give trouble, fall back to a webhook tool pointing at your control API through ngrok or cloudflared. Test the tunnel on venue Wi-Fi before committing to it.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Room noise | Headset with a close mic. Keep the exchange to one decision and one code |
| Wi-Fi drops the session | The button path is always available. Say "and by button if you prefer" and move on |
| Speech misheard as approve or deny | The agent reads the decision back before calling the tool, and the challenge code must match |
| No ElevenLabs credits provided | Check tonight how many agent minutes your own plan includes. A demo needs only a few |
| Latency makes the demo drag | Pre-warm the session before the demo starts. Keep the briefing under 12 seconds |
| Judges cannot hear it | Laptop speakers at full volume for the agent's side. In Round 1 rooms this is fine. On stage, ask the AV person for audio in advance |

## What to say about it

"Approval is a conversation, so we made it one. The voice channel is not the control, the policy is. The voice session is recorded as evidence on the approval, with a challenge code binding it to the approver."
