# Antigravity build prompt

Open this repository in Antigravity and continue from the current implementation rather than replacing it with a generic template.

## Assignment goals
Build a polished, reliable cold-call side screen for an actual caller: show which of eight call stages they are in and what that stage is for; show evidence-backed prospect utterance patterns from the provided 100 transcripts; let the caller record what happened and the prospect's exact words at each stage; allow progressing through stages; close with a call outcome; persist calls/stage data in Supabase; provide a history screen that shows calls and stage reached.

## Current implementation
- `frontend/`: React + Vite, responsive workspace, stage stepper, notes panel, outcome modal, history screen.
- `backend/app.py`: FastAPI health, stage, call create, stage update, stage-result upsert, call close, list/detail APIs.
- `supabase/schema.sql`: tables and starter stages.
- `README.md`: local setup and deployment outline.

## Must-do tasks (do not skip)
1. Read both assignment pages:
   - https://sainikpuri.deepthought.education/fde-hyderabad-v2/structure
   - https://sainikpuri.deepthought.education/fde-hyderabad-v2/reference
   Download and analyze `https://sainikpuri.deepthought.education/fde/cold-call-transcripts-100.zip`. If unavailable, ask the human to upload screenshots/pages/ZIP. Do not claim starter cue copy is transcript-derived. Build a transcript-derived summary for every stage, cite the counts/patterns internally in a notes file, but never show names of the fictional callers/companies. Do not publish transcript bodies or commit the ZIP.
2. Improve the eight stage definitions using the structure page, preserving exactly eight stages in correct order.
3. Ensure frontend API interactions support real persistence. Fix any async race in `saveStage(); switchStage()` and make it await the save before changing stage. On history open, merge server records and local fallback records without duplicates. For local/offline calls, allow end-to-end flow and show a clear offline label; never pretend they synced.
4. LLM feature is required. Add a small server-side endpoint using the provider key configured only on Render (never client bundle). Use it for a safe post-call summary and optionally classify the prospect's objection using saved words/notes. It must never invent or rewrite direct quotations; label AI output and keep raw caller notes separate. If no provider key is configured, give a non-failing disabled-state message. Document which provider/model and purpose are used.
5. Test start call, save result, move stages, finish call, list/detail history, input validation, and `/health`. Add basic automated backend tests. Ensure starter stage records can be seeded/re-run idempotently in Supabase SQL.
6. Check frontend for mobile layout, keyboard focus, empty/error/loading states, readable live-call hierarchy and no broken buttons. Run `npm install`, `npm run build`, backend tests, and lint or syntax checks.
7. Deploy backend to Render free tier and frontend to Vercel free tier. Configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS`, and LLM credentials only as server environment variables. Set Vercel `VITE_API_BASE_URL` to Render URL. Never commit secret keys.
8. Update README with the actual public GitHub repo, actual Vercel URL, actual Render URL and health URL, model used, feature description, local run instructions, and limitations. Do not insert placeholder URLs as if they are live.
9. Prepare a six-minute demo outline, but the applicant must record themselves on camera and upload it to Google Drive with “Anyone with the link” viewer access. Do not synthesize a fake applicant video.

## UX direction
Use a quiet editorial interface: warm off-white canvas, dark evergreen sidebar, restrained green status markers, generous whitespace, compact monospace labels, readable type, real visible focus states. The first screen should let the caller begin quickly; during a call, the primary content is current stage purpose, evidence-backed “what you may hear”, outcome taps, verbatim prospect words, concise private notes and large next-stage control. Do not add charts or bulky dashboards that distract from the live conversation.
