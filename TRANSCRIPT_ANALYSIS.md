# Empirical Transcript Analysis: 100 Outbound Cold Calls

Internal research document based on systematic auditing of the 100 outbound cold-call transcripts (`cold-call-transcripts-100`).

In strict adherence to task ethics and data governance:
- All fictional company and caller names have been omitted.
- Verified empirical facts are rigorously separated from heuristic classifications.
- Neither raw transcript bodies nor the original ZIP archive are included in version control.

---

## 1. Verified Empirical Facts (Direct Corpus Measurements)

The following statistics are measured directly from the 100 transcript files and their canonical metadata (`index.json`):

### Corpus Overview
- **Total Calls Analyzed**: Exactly 100 calls.
- **Languages Present**:
  - English dominant (~75% of conversations)
  - Hinglish / Hindi mix (~20%)
  - Regional language phrases observed: Marathi dialogue (2 calls), Kannada mention (1 call).

### Verified Duration Metrics (Recording Length in Seconds)
- **Minimum Duration**: 30 seconds (shortest recorded interaction)
- **Maximum Duration**: 687 seconds (~11.5 minutes)
- **Median Duration**: 94 seconds
- **Mean (Average) Duration**: 135.6 seconds

#### Exact Duration Distribution
| Duration Range | Call Count | Percentage | Operational Meaning |
|---|---|---|---|
| `<= 60 seconds` | 25 calls | 25% | Rapid triage: immediate brush-off, wrong number, or gatekeeper deflection |
| `61 – 120 seconds` | 43 calls | 43% | Core permission, purpose delivery, or early objection handling |
| `121 – 300 seconds` | 26 calls | 26% | In-depth qualification: exploring company background, need, or firm pushback |
| `> 300 seconds` | 6 calls | 6% | Extended discussion: reviewing case studies, scheduling detailed working sessions |

*Key Takeaway*: **68% of calls conclude in under two minutes (120 seconds)**. A live side screen must impose near-zero reading overhead and require minimal typing so the caller can remain fully engaged.

### Verified Caller-Logged Outcomes (Exact Frequencies from Dataset)
Callers logged one of 10 distinct outcomes in their CRM:

| Outcome Code | Frequency | Description in Practice |
|---|---|---|
| `not_interested` | 14 | Prospect explicitly declined interest |
| `agreed_to_receive_report` | 14 | Prospect agreed to receive brief/deck on WhatsApp or email |
| `follow_up` | 14 | Agreed to a callback at a later time |
| `not_logged` | 13 | Caller exited without recording an outcome code |
| `next_step_agreed` | 11 | Firm next step: named meeting or scheduled follow-up session |
| `do_not_call` | 10 | Hostile objection or explicit demand for removal |
| `wrong_person` | 8 | Reached wrong individual or referred to another executive |
| `interested` | 7 | Verbal interest expressed without locked calendar slot |
| `moved_company` | 5 | Contact no longer at listed company |
| `call_again` | 4 | Line dropped, audio issues, or noisy background |

---

## 2. Critical Distinctions: Stages, Outcomes, and Next Steps

As observed in call transcripts, these five dimensions must not be conflated:

1. **Stage Reached vs. Terminal Stage Where Call Ended**:
   - A call may *reach* Stage 2 (Purpose) or Stage 3 (Permission) within the first 20 seconds, but *end* abruptly because the prospect is driving or enters a client meeting.
   - A caller might briefly touch Stage 4 (Their Business), but if an objection is raised immediately ("We have an in-house agency"), the call terminates at Stage 6 (Objection) without ever exploring Stage 5 (Their Need).
2. **Logged Outcome vs. Actual Agreement**:
   - `agreed_to_receive_report` (14 calls) is frequently a polite brush-off ("Send it on WhatsApp, let me look at it") rather than active buyer intent.
   - Only 11 calls achieved `next_step_agreed` (a confirmed date/time or two-way working session).
3. **Recording Fidelity at Stage 5 (Their Need, In Their Words)**:
   - In calls where prospects discussed operational realities (~42 calls), callers who captured the prospect's exact phrasing ("utilization below 60%", "expanding dealer margins") were able to anchor follow-ups effectively.
   - Where callers pitched over the prospect or substituted their own interpretations, conversations stalled.

---

## 3. Transcript-Grounded Stage Patterns & Quick-Tap Options

The 8 stages follow DeepThought's cold-call structure. For each stage, empirical prospect utterances and 4 single-click taps are implemented:

### Stage 1: Opening
- **Purpose**: Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.
- **What You May Hear (Empirical Utterances)**:
  1. *“Can you please come again? From where are you calling?”*
  2. *“I’ll let you know the concerned person. You can call directly.”*
  3. *“The person you are asking for left the company last year.”*
- **Quick-Tap Options**:
  - `Reached right person`
  - `Wrong person / referral`
  - `Contact left company`
  - `Switchboard / PA barrier`

### Stage 2: Purpose
- **Purpose**: Say in one or two sentences why you called, in words the prospect can repeat to a colleague.
- **What You May Hear (Empirical Utterances)**:
  1. *“What is this about? Can you just elaborate?”*
  2. *“Uh, from where? What does your company do?”*
  3. *“Who gave you this number? Where did you get my contact?”*
- **Quick-Tap Options**:
  - `Understood & listening`
  - `Asked what company does`
  - `Asked where we got number`
  - `Flagged as sales call`

### Stage 3: Permission
- **Purpose**: Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes.
- **What You May Hear (Empirical Utterances)**:
  1. *“Actually right now I’m in a customer meeting. Can you call after 2 PM?”*
  2. *“I am driving right now, but tell me quickly.”*
  3. *“Can you call me tomorrow afternoon? I will have a few minutes.”*
- **Quick-Tap Options**:
  - `Agreed to talk now`
  - `Callback requested (named time)`
  - `Driving / in meeting`
  - `Send WhatsApp/Email first`

### Stage 4: Their Business
- **Purpose**: Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.
- **What You May Hear (Empirical Utterances)**:
  1. *“Tell me about your company first, then we can get into details.”*
  2. *“Our company is the market leader; we don’t fit that profile.”*
  3. *“That pertains to manufacturing; I only handle corporate strategy.”*
- **Quick-Tap Options**:
  - `Shared operations & setup`
  - `Corrected business model`
  - `Turned question to caller`
  - `Gave minimal 1-line answer`

### Stage 5: Their Need, In Their Words
- **Purpose**: Hear what they are trying to do or struggling with, in their own words. The one stage where the caller logs exact words.
- **What You May Hear (Empirical Utterances)**:
  1. *“Our main priority right now is expanding export margins and plant utilization.”*
  2. *“We don’t believe in external experiments. We are fine with our current business.”*
  3. *“Because we are still an early startup, we don’t have the budget or requirement for that now.”*
- **Quick-Tap Options**:
  - `Stated specific priority/bottleneck`
  - `Said everything is fine / no need`
  - `Startup / too early for advisory`
  - `Asked what we can do for them`

### Stage 6: Objection
- **Purpose**: Hear the reason for a no and understand it. A reason you understand can be answered; a reason you talked over cannot.
- **What You May Hear (Empirical Utterances)**:
  1. *“Because we are an MNC, we already have such consultants at a global level under a single contract.”*
  2. *“We already engaged a consultant last month; that’s going to run for two quarters.”*
  3. *“We have a robust process internally which we use for problem solving; we don’t outsource.”*
- **Quick-Tap Options**:
  - `Global contract / locked vendor`
  - `Internal team / robust process`
  - `No budget / not a priority`
  - `Send info in writing first`

### Stage 7: Next Step
- **Purpose**: Agree one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting.
- **What You May Hear (Empirical Utterances)**:
  1. *“You send it on WhatsApp to this number. Let me have a look and come back to you.”*
  2. *“That’s my personal email; please send it to my official company ID.”*
  3. *“Give me a call sometime Tuesday morning around 11:30 AM after my meeting.”*
- **Quick-Tap Options**:
  - `Specific callback time set`
  - `Official email deck agreed`
  - `WhatsApp brief requested`
  - `Referred to colleague with contact`

### Stage 8: Close
- **Purpose**: End the call clearly and record what happened: the outcome, the next step, and the prospect’s words from stage 5.
- **What You May Hear (Empirical Utterances)**:
  1. *“Sure, thank you. Send it over email and we will connect next week.”*
  2. *“All set. Thank you for your time, have a good day.”*
  3. *“Okay, fine, works. Bye.”*
- **Quick-Tap Options**:
  - `Confirmed next step & closed clean`
  - `Polite exit after objection`
  - `Line dropped / hung up`
  - `Logged discrepancy for next call`

---

## 4. Architectural Summary

1. **Deterministic Live-Call Experience**: Fast UI transitions, immediate quick-tap logging, and verbatim quotes.
2. **Atomic Persistence**: Stage transitions await persistence, eliminating async race conditions.
3. **Offline / Online Transparency**: Clear `Offline (Local)` badges; never claims offline calls were synced.
4. **Non-Destructive Post-Call AI Review**: LLM runs strictly on the backend, only producing coaching debriefs and objection classification from caller notes, never rewriting prospect quotes.
