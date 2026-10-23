# ColdCall Companion

A focused, editorial live-call side screen for outbound callers reaching Indian business leaders. Follow the eight proven call stages, anticipate authentic prospect responses derived from 100 empirical transcripts, log single-tap outcomes and exact verbatim prospect words, and review completed and abandoned calls.

---

## Live System & Architecture

- **Frontend**: React + Vite (`DM Sans`, `DM Mono`, `Playfair Display`), responsive editorial layout.
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
   - Analysis of 100 transcripts revealed that 68% of calls last between 31 and 120 seconds. Callers cannot type long notes during live calls.
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

---

## Local Development & Setup

### 1. Database (Supabase)
Run `supabase/schema.sql` in the Supabase SQL Editor. This idempotently creates tables (`call_stages`, `calls`, `call_stage_results`), indexes, and seeds the 8 stages with prospect patterns and quick taps.

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
LLM_API_KEY=YOUR_SERVER_ONLY_LLM_KEY
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_MODEL=gpt-4o-mini
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

---

## Endpoints

- `GET /health`: Health and service connectivity status.
- `GET /stages`: Returns the 8 ordered stages with prospect patterns and stage taps.
- `POST /calls`: Create a new call.
- `POST /calls/{id}/stage-results`: Upsert stage outcome, verbatim words, and caller notes.
- `PATCH /calls/{id}/stage`: Update active stage position.
- `POST /calls/{id}/close`: Conclude call with terminal outcome and context notes.
- `GET /calls`: List calls with stage outcomes and timestamps.
- `GET /calls/{id}`: Detailed call record.
- `POST /calls/{id}/ai-summary`: Generate post-call coaching debrief.
