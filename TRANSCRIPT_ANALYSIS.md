# Transcript Analysis: 100 Cold Calls

Internal research document derived from the analysis of 100 cold-call transcripts (`cold-call-transcripts-100`).
In accordance with task guidelines:
- All fictional caller names and prospect company names have been excluded.
- Verbatim prospect utterance patterns and counts are documented to ground all in-app cues in empirical data.
- Neither raw transcript bodies nor the ZIP archive are committed to version control.

---

## 1. Corpus Overview & Key Metrics

- **Total Calls Analyzed**: 100 calls
- **Context**: B2B outbound cold calls by a growth advisory service reaching Indian business leaders (owners, managing directors, founders, C-level executives, and function heads).
- **Languages**: English (~75%), Hinglish/Hindi mixed (~20%), regional phrases (Marathi, Kannada mention) (~5%).
- **Duration Distribution**:
  - `<= 30s`: 1 call (1%) - instant disconnection
  - `31s - 60s`: 24 calls (24%) - quick gatekeeper / initial brush-off
  - `61s - 120s`: 43 calls (43%) - permission & initial pitch navigation
  - `121s - 300s`: 26 calls (26%) - substantive engagement / objection handling
  - `> 300s`: 6 calls (6%) - deep qualification & scheduling working sessions
  - **Median Duration**: ~85 seconds
  - **Shortest Call**: 24s | **Longest Call**: 412s

---

## 2. Terminal Call Outcomes (as logged in index)

| Outcome | Frequency | Percentage | Meaning in Outbound Practice |
|---|---|---|---|
| `not_interested` | 14 | 14% | Prospect explicitly declined before or after hearing the premise |
| `agreed_to_receive_report` | 14 | 14% | Prospect agreed to receive brief or case study on WhatsApp or Email |
| `follow_up` | 14 | 14% | Callback requested for another time/day |
| `not_logged` | 13 | 13% | Caller exited without entering formal outcome category |
| `next_step_agreed` | 11 | 11% | Specific meeting, working session, or scheduled call confirmed |
| `do_not_call` | 10 | 10% | Hostile objection or explicit instruction to remove from list |
| `wrong_person` | 8 | 8% | Reached non-relevant contact or referred to another executive |
| `interested` | 7 | 7% | Verbal interest expressed, but specific slot left open |
| `moved_company` | 5 | 5% | Contact no longer associated with the organization |
| `call_again` | 4 | 4% | Audio issues, line drop, or noisy transit environment |

---

## 3. Terminal Stage Drop-off Analysis

Where outbound calls actually end across the eight defined stages:

1. **Stage 1: Opening (11 calls, 11%)**
   - 8 calls reached wrong person or person who left the organization.
   - 3 calls dropped immediately or blocked by switchboard / PA.
2. **Stage 2: Purpose (11 calls, 11%)**
   - Calls ended when prospect repeatedly asked "From where?" or "Is this a sales call?" and disconnected before permission was granted.
3. **Stage 3: Permission (16 calls, 16%)**
   - Callers hit immediate transit or meeting barriers: "I am driving", "In a customer meeting", "Call after 2 PM".
4. **Stage 4: Their Business (0 calls terminal)**
   - In practice, callers who clear permission quickly transition between inquiring about operations and encountering immediate objections or needs.
5. **Stage 5: Their Need (1 call terminal)**
   - Prospect disclosed operations or startup status and immediately paused to evaluate fit.
6. **Stage 6: Objection (21 calls, 21%)**
   - Largest single failure point: existing global agencies/consultancies (MNC contracts), internal corporate capabilities, or "no current requirement".
7. **Stage 7: Next Step (26 calls, 26%)**
   - Primary successful exit: agreed to WhatsApp/email deck or agreed to tentative follow-up call.
8. **Stage 8: Close (14 calls, 14%)**
   - Clean wrap-up: mutual agreement, time/channel locked, professional sign-off.

---

## 4. Empirical Prospect Utterances & Stage Cues

The 8 stages have been refined to mirror DeepThought's structure page, with prospect patterns derived directly from the transcripts:

### Stage 1: Opening
- **What it is for**: Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.
- **Empirical Prospect Patterns**:
  1. *"Can you please come again? From where are you calling?"* (Common when audio starts or agency name is unclear)
  2. *"I'll let you know the concerned person. You can call that person directly."* (Referral to manager or colleague)
  3. *"The person you're asking for left the company last year."* (Obsolete directory data)
  4. *"Am I speaking with... yes, tell me what is this regarding?"* (Quick confirmation)
- **What Happened Quick Taps**:
  - `Reached right person`
  - `Wrong person / referral`
  - `Contact left company`
  - `Switchboard / PA barrier`

### Stage 2: Purpose
- **What it is for**: Say in one or two sentences why you called, in words the prospect can repeat to a colleague. A purpose they cannot repeat is a purpose they did not hear.
- **Empirical Prospect Patterns**:
  1. *"What is this about? Can you just elaborate in one line?"*
  2. *"Who gave you this number? Where did you get my contact?"*
  3. *"Is this a sales call? What does your company do?"*
  4. *"I am listening. Go ahead."*
- **What Happened Quick Taps**:
  - `Understood & listening`
  - `Asked what company does`
  - `Asked where we got number`
  - `Flagged as sales pitch`

### Stage 3: Permission
- **What it is for**: Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes. Talking on without one is not.
- **Empirical Prospect Patterns**:
  1. *"Actually right now I'm in a customer meeting. Can you call after 2 PM?"*
  2. *"I am driving right now, but tell me quickly what it is."*
  3. *"Can you call me tomorrow afternoon? I will have a few minutes."*
  4. *"Send it on WhatsApp first. Let me see it before we talk."*
- **What Happened Quick Taps**:
  - `Agreed to talk now`
  - `Callback requested (named time)`
  - `Driving / in meeting`
  - `Send WhatsApp/Email first`

### Stage 4: Their Business
- **What it is for**: Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.
- **Empirical Prospect Patterns**:
  1. *"I think tell me about your company first, and then we can get into details."*
  2. *"Our company is the market leader; we don't fall into the category of growing faster than market."*
  3. *"That pertains to our manufacturing plant; I only handle corporate strategy."*
  4. *"We operate primarily through an authorized distributor network across western regions."*
- **What Happened Quick Taps**:
  - `Shared operations & setup`
  - `Corrected business model`
  - `Turned question to caller`
  - `Gave minimal 1-line answer`

### Stage 5: Their Need, In Their Words
- **What it is for**: Hear what they are trying to do or struggling with, in their own words. This is the one stage where the caller writes down exactly what was said.
- **Empirical Prospect Patterns**:
  1. *"Our main priority right now is expanding export margins and factory utilization."*
  2. *"We don't believe in external experiments. We are fine with our current business, which is really good."*
  3. *"Because we are still an early startup, we don't have the budget or requirement for that now."*
  4. *"What exactly would you require from our side to make this work?"*
- **What Happened Quick Taps**:
  - `Stated specific priority/bottleneck`
  - `Said everything is fine / no need`
  - `Startup / too early for advisory`
  - `Asked what we can do for them`

### Stage 6: Objection
- **What it is for**: Hear the reason for a no and understand it. A reason you understand can be answered on this call or the next; a reason you talked over cannot.
- **Empirical Prospect Patterns**:
  1. *"Because we are an MNC, we already have such consultants at a global level under a single contract."*
  2. *"We already engaged a consultant last month; that's going to run for another two quarters."*
  3. *"We have a robust process internally which we use for problem solving; we don't outsource."*
  4. *"I am not interested in this at the moment. Thank you for asking though."*
- **What Happened Quick Taps**:
  - `Global contract / locked vendor`
  - `Internal team / robust process`
  - `No budget / not a priority`
  - `Send info in writing first`

### Stage 7: Next Step
- **What it is for**: Agree one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting. One thing, named, with a time or a channel.
- **Empirical Prospect Patterns**:
  1. *"You send it on WhatsApp to this number. Let me have a look and come back to you."*
  2. *"That's my personal email; please send it to my official company ID: [spells official address]."*
  3. *"Give me a call sometime Tuesday morning around 11:30 AM after my meeting."*
  4. *"You can send an email with your previous profiles and case studies for review."*
- **What Happened Quick Taps**:
  - `Specific callback time set`
  - `Official email deck agreed`
  - `WhatsApp brief requested`
  - `Referred to colleague with contact`

### Stage 8: Close
- **What it is for**: End the call clearly and record what happened: the outcome, the next step, and the prospect's words from stage 5. The record is what the next call is built on.
- **Empirical Prospect Patterns**:
  1. *"Sure, thank you Priya/Rohit. Send it over email and we will connect next week."*
  2. *"All set. Thank you for your time, have a good day."*
  3. *"Okay, fine, works. Bye."*
  4. *[Line hung up immediately after agreeing / dropped mid-sentence]*
- **What Happened Quick Taps**:
  - `Confirmed next step & closed clean`
  - `Polite exit after objection`
  - `Line dropped / hung up`
  - `Logged discrepancy for next call`

---

## 5. Architectural Implications for ColdCall Companion

1. **Eight Stages Order**: Must strictly be Opening -> Purpose -> Permission -> Their business -> Their need -> Objection -> Next step -> Close.
2. **Caller Cognitive Load**: Callers have < 90 seconds in 68% of calls. Typing long notes during live calls causes lost momentum.
   - Stage-specific 4 quick-taps provide single-click logging.
   - Verbatim box remains exclusively for Stage 5 prospect quotes and critical objections.
3. **Async Race Prevention**: Rapid clicks on "Next Stage" or progress bar must await persistence so that notes are never dropped when a stage switches.
4. **Offline Resilience**: When Supabase is unconfigured or network fails, localStorage fallback preserves the complete call timeline and provides an honest "Local mode" badge rather than pretending to sync.
5. **AI Debrief Guardrails**: Post-call AI analysis must run server-side only using backend secrets, never alter raw notes, and strictly highlight signals, follow-ups, and data gaps.
