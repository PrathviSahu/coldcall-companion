# ColdCall Companion

A focused, editorial live-call side screen for outbound callers reaching Indian business leaders. Follow the eight proven call stages, anticipate aggregated prospect response patterns derived from 100 empirical transcripts, log single-tap outcomes and exact verbatim prospect words, and review completed and abandoned calls.

- **GitHub Repository**: [https://github.com/PrathviSahu/coldcall-companion](https://github.com/PrathviSahu/coldcall-companion)

---

## Live System & Architecture

- **Frontend**: React + Vite (`DM Sans`, `DM Mono`, `Playfair Display`), responsive editorial layout with stage stepper, quick-tap cards, verbatim text area, and history audit table.
- **Backend**: Python 3.13 + FastAPI (`/health`, `/stages`, `/calls`, `/calls/{id}/stage-results`, `/calls/{id}/close`, `/calls/{id}/ai-summary`).
- **Persistence**: Supabase Postgres with row-level security and idempotent migrations (`supabase/schema.sql`).
- **Local Fallback**: Full offline resilience via `localStorage` with honest `Offline / Local` labeling (never pretends to be synced).
- **AI Debrief**: Server-side LLM endpoint (OpenAI-compatible) generating post-call summaries, objection classification, signals, follow-up recommendations, and data gaps without altering raw notes.

---

## The Eight Cold-Call Stages

Derived directly from the DeepThought cold-call structure guidelines and empirical research across 100 outbound transcripts:

1. **Opening**: Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.
2. **Purpose**: Say why you called in one or two sentences the prospect can repeat to a colleague.
3. **Permission**: Find out whether they are willing to talk now (clear yes, clear no, or a named callback window).
4. **Their business**: Ask about their company, operations, and market before talking about yours.
5. **Their need, in their words**: Hear what they are trying to do or struggling with. The one stage where the caller logs exact verbatim quotes.
6. **Objection**: Hear the reason for resistance and understand it (vendor lock-in, internal capability, timing).
7. **Next step**: Agree on one concrete thing: a document on WhatsApp or email, a named callback slot, or a meeting.
8. **Close**: End the call clearly and record what happened: the outcome, the next step, and the prospect's words from stage 5.

---

## Key Engineering & Product Decisions

1. **Empirical Utterances & Quick Taps**:
   - Analysis of 100 transcripts revealed that 68% of calls conclude in two minutes (120 seconds) or less (25% under 60 seconds, 43% between 61 and 120 seconds). Callers cannot type long notes during live calls.
   - Each stage features 4 quick outcome taps for single-click logging alongside empirical "What you may hear" cues.
2. **Zero Async Race Conditions**:
   - Stage transitions (`goToStage`) strictly await the persistence of the current stage before moving to the target index, preventing dropped quotes or overwriting unsaved notes.
3. **Honest Persistence & Deduplication**:
   - Calls created offline are labeled `Offline (Local)` and stored in browser memory.
   - When viewing history, server-backed records and local fallback records are merged by `id` without duplication.
4. **Guardrailed AI Debrief**:
   - The LLM runs server-side only; API keys are never exposed in the client bundle.
   - If `LLM_API_KEY` is unset, the endpoint returns a non-failing disabled-state message rather than throwing errors.
   - Raw notes remain untouched; the AI only surfaces review metadata (summary, objection category, signals, follow-ups, gaps).
5. **Caller Authentication, Authorization & Interim Access Model**:
   - **Interim Internal Model**: Authentication uses server-configured static bearer tokens via `CALLER_AUTH_TOKENS`. This is an interim internal access model designed for operational sales reps, not a full OAuth/session-expiring system. Generate high-entropy tokens per caller (e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) and keep them strictly out of source control.
   - **Fail-Closed Security**: If `CALLER_AUTH_TOKENS` is unconfigured, all authenticated endpoints fail closed (401 Unauthorized). Prefix-based token bypasses (`fde-*`, `caller-*`, `admin-*`) are strictly disallowed. Administrator status requires an explicit `:admin` token configuration.
   - **Cross-Caller Isolation**: Reps only access calls they created; unauthorized cross-caller access returns `403 Forbidden`. Call history (`GET /calls`) filters strictly by `caller_id`, while administrators can query all calls or filter by specific reps via `?caller_id=...`.
   - **Outcome Validation & Immutability**: Outcomes are validated against `ALLOWED_OUTCOMES` (422 on invalid input), and closed calls cannot be modified (409 Conflict).
   - **Supabase Defense-in-Depth**: `supabase/schema.sql` includes RLS policies (`auth.uid() = caller_id`). In backend service-role architecture, the FastAPI application layer enforces authoritative isolation boundaries.
6. **Quotation Integrity (Read-Only Sample Patterns)**:
   - Behavioral cues (`prospect_patterns`) derived from transcript analysis are presented as read-only situational cues (`OBSERVED CUES (READ-ONLY)`).
   - The UI does not provide auto-append buttons into verbatim fields. Actual prospect quotes must be explicitly typed by the caller to ensure synthetic phrases never pollute compliance records.
7. **Per-Stage Sync Tracking & Exhaustive Retry**:
   - **Per-Stage Status**: Every stage record maintains independent synchronization tracking (`synced: boolean`, `sync_error`). A successful save on a later stage NEVER clears an earlier failed save; the UI checks all recorded stages and displays exactly which stages remain pending.
   - **Retry All Pending**: The retry mechanism triggers `retrySyncAllPending()`, which provisions the call in Supabase if started offline and uploads every outstanding stage result.
8. **Guaranteed Cloud Save on Call Wrap-Up**:
   - `closeCall()` strictly verifies that all stage records are synchronized to Supabase before marking a call closed.
   - If network writes fail during close, the modal blocks silent dismissal and warns the caller with explicit dual actions:
     - **Retry Cloud Close**: Retries syncing all pending records and finalizing the cloud record.
     - **Save as Offline Draft**: Preserves the complete draft locally with an `UNSYNCED DRAFT` tag so callers can wrap up without data loss.
9. **Offline Draft Recovery & Cloud Replay (`POST /calls/sync-offline`)**:
   - Calls recorded while offline or saved locally can be synchronized to Supabase anytime from the Call History table or Call Detail view.
   - The backend `POST /calls/sync-offline` endpoint atomically establishes the call, inserts all historical stage notes, and sets the outcome with authentic start and end timestamps.

---

## Local Development & Setup

### 1. Database (Supabase)
1. In your Supabase dashboard, open the **SQL Editor**.
2. Paste and run the entire contents of `supabase/schema.sql`.
3. This creates:
   - `public.call_stages` (and seeds all 8 stages with prospect patterns and quick taps)
   - `public.calls` (with outcome constraints, stage tracking, and AI debrief column)
   - `public.call_stage_results` (with composite unique key on `call_id, stage_id`)
   - Indexes and Row Level Security policies.
   The script is fully idempotent (`ON CONFLICT (id) DO UPDATE`).

4. **Selective Legacy Record Audit & Reassignment**:
   Pre-existing call records created prior to caller authentication have `caller_id = 'anonymous-caller'`. Under strict isolation, regular sales reps will not see these records; only administrators (configured with `:admin` role) have visibility.
   
   **IMPORTANT**: Do NOT execute a blanket update assigning all records to a single rep without reviewing deal ownership.
   1. Audit unassigned calls:
      ```sql
      SELECT id, prospect_name, company_name, started_at, outcome
      FROM public.calls
      WHERE caller_id = 'anonymous-caller'
      ORDER BY started_at DESC;
      ```
   2. Selectively reassign based on true account ownership:
      ```sql
      UPDATE public.calls
      SET caller_id = 'rep-alpha'
      WHERE caller_id = 'anonymous-caller'
        AND company_name IN ('Target Enterprise A', 'Target Enterprise B');
      ```
   *NEVER execute destructive DELETE statements on legacy calls.*

### 2. Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```
Run automated test suite:
```bash
pytest -v test_app.py
```

### 3. Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Build for production:
```bash
npm run build
```

---

## Environment Configuration

### Frontend (`frontend/.env`)
```env
VITE_API_BASE_URL=http://localhost:8000
```

### Backend (`backend/.env`)
```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_ONLY_KEY
CALLER_AUTH_TOKENS=rep-alpha:strong-token-alpha,rep-beta:strong-token-beta,admin-lead:strong-admin-token:admin
LLM_API_KEY=YOUR_SERVER_ONLY_LLM_KEY
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_MODEL=gpt-4o-mini
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

---

## Deployment Steps

### 1. Backend Deployment (Render)
1. In Render Dashboard, click **New Web Service** and connect the repository (`PrathviSahu/coldcall-companion`).
2. Set **Root Directory** to `backend`.
3. Set **Runtime** to `Python 3`.
4. Set **Build Command**: `pip install -r requirements.txt`.
5. Set **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`.
6. Add Environment Variables:
   - `SUPABASE_URL`: Your Supabase project URL (`https://your-id.supabase.co`)
   - `SUPABASE_SERVICE_ROLE_KEY`: Your server-only service-role key
   - `CALLER_AUTH_TOKENS`: e.g. `rep-alpha:token1,rep-beta:token2,admin-lead:token3:admin` (generated securely, kept out of git)
   - `LLM_API_KEY`: Your LLM provider API key
   - `LLM_MODEL`: e.g. `gpt-4o-mini`
   - `CORS_ORIGINS`: Your Vercel frontend URL (or `*` during initial staging)
7. Deploy and verify health via `GET /health`.

### 2. Frontend Deployment (Vercel)
1. In Vercel Dashboard, click **Add New Project** and select `PrathviSahu/coldcall-companion`.
2. Set **Root Directory** to `frontend`.
3. Framework Preset: **Vite**.
4. Configure Environment Variable:
   - `VITE_API_BASE_URL`: Live Render backend URL from step 1 (e.g. `https://your-backend.onrender.com`).
5. Deploy and verify live calling flow and history screen.

---

## Endpoints

- `GET /health`: Health and service connectivity status (`ok` / `degraded`, database state, LLM state).
- `GET /stages`: Returns the 8 ordered stages with prospect patterns and stage taps.
- `POST /calls`: Create a new call with optional prospect/company names.
- `POST /calls/{id}/stage-results`: Upsert stage outcome, verbatim words, and caller notes.
- `PATCH /calls/{id}/stage`: Update active stage position.
- `POST /calls/{id}/close`: Conclude call with terminal outcome and next-step context notes.
- `GET /calls`: List calls with stage outcomes and timestamps (paginated).
- `GET /calls/{id}`: Detailed call record with all stage-by-stage notes.
- `POST /calls/{id}/ai-summary`: Generate post-call coaching debrief from caller notes.

---

## Six-Minute Video Demo Outline (Applicant-Recorded)

The demo must be recorded on camera by the applicant (no synthesized avatars) and shared via Google Drive with public viewer access:

- **0:00–0:35 — Introduce the Problem**: Show yourself and the app. Explain why cold callers need a calm, single-screen guide rather than complex dashboards.
- **0:35–1:15 — Start a Conversation**: Begin a call with an optional prospect name. Explain rapid entry.
- **1:15–2:20 — Walk Through the Eight Stages**: Demonstrate stage purpose and empirical "What you may hear" cues derived from the 100 transcripts.
- **2:20–3:25 — Capture the Conversation**: Tap a single-click outcome, type verbatim prospect words in Stage 5, and demonstrate atomic stage switching.
- **3:25–4:10 — Wrap-Up & History Audit**: Close the call with a true outcome. Review the call history screen, showing the stage reached and outcome badge.
- **4:10–5:15 — Defend an Engineering Decision**: Explain atomic stage persistence (eliminating async races) and honest offline fallback.
- **5:15–6:00 — Architecture & Closing**: Show the stack (FastAPI, React + Vite, Supabase, server-side LLM debrief), `/health` endpoint, and what you would iterate next.
