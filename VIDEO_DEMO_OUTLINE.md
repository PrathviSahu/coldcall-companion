# Six-minute demo outline (recorded by the applicant)

Keep your camera visible for the full recording. Use one fictionalized transcript from the task materials after you have reviewed it. Do not read this as a script; use it only to remember the order. Speak naturally and explain decisions in your own words.

## 0:00–0:35 — Introduce the problem
Show yourself and the app. Explain the caller has a prospect on the phone and needs to keep track of the call structure without splitting attention across documents.

## 0:35–1:15 — Start a call
Create a call using a fictional prospect/company name from the provided materials. Explain why the name fields are optional and how a caller can begin quickly.

## 1:15–2:20 — Walk through the stages
Show all eight stages in order and explain how the current stage is visually distinct. Choose one stage and show its purpose and the cues you selected after reviewing the transcripts. Be ready to explain what pattern in the actual calls led to that choice; do not present starter examples as research findings.

## 2:20–3:25 — Capture the conversation
Use the transcript to demonstrate tapping an outcome and recording a prospect's own words. Explain why verbatim words are kept separate from the caller's interpretation/notes. Save the stage, move to the next stage, and show how progress remains visible.

## 3:25–4:10 — Finish the call and review history
Choose the transcript's true outcome, add next-step context, and close the call. Open the history screen and show the stage reached, outcome, prospect/company, and date. Open the record to show the saved stage notes.

## 4:10–5:15 — Explain one engineering/design decision
Pick one real decision you made and defend it. Examples: keep the stage purpose in the caller's primary visual path; preserve exact words separately; use an upsert keyed by call+stage to avoid duplicate results when a caller revisits a stage; keep the LLM server-side and send only saved call data for debriefs. Explain the trade-off and one alternative you rejected.

## 5:15–6:00 — Architecture and close
Show the README briefly: React/Vercel, FastAPI/Render, Supabase/Postgres, the LLM model and purpose, and the health endpoint. If relevant, explain what happens when the backend or model is unavailable. End by saying what you would improve next after observing callers use the product.

## Before uploading
- Record a real screen walkthrough with your face visible; do not synthesize an applicant video.
- Use Google Drive, set General access to “Anyone with the link” / Viewer, then test the link in a private/incognito window.
- Check that the video is at least six minutes and plays without asking for permission.
- Only claim transcript-derived patterns after you have analyzed the supplied 100 calls.
