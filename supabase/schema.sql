create extension if not exists pgcrypto;

create table if not exists public.call_stages (
  id text primary key,
  position integer not null unique,
  title text not null,
  purpose text not null,
  guidance text not null,
  prospect_patterns jsonb not null default '[]'::jsonb,
  stage_taps jsonb not null default '[]'::jsonb
);

-- Upgrade column if table already exists
alter table public.call_stages add column if not exists stage_taps jsonb not null default '[]'::jsonb;

create table if not exists public.calls (
  id uuid primary key default gen_random_uuid(),
  prospect_name text,
  company_name text,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  current_stage_id text references public.call_stages(id),
  outcome text,
  outcome_notes text,
  ai_summary jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.call_stage_results (
  id uuid primary key default gen_random_uuid(),
  call_id uuid not null references public.calls(id) on delete cascade,
  stage_id text not null references public.call_stages(id),
  result text not null,
  prospect_words text not null default '',
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(call_id, stage_id)
);

create index if not exists calls_started_at_idx on public.calls(started_at desc);
create index if not exists call_stage_results_call_idx on public.call_stage_results(call_id, created_at);

-- The API uses the server-only service-role key. Do not expose this key to a browser.
alter table public.call_stages enable row level security;
alter table public.calls enable row level security;
alter table public.call_stage_results enable row level security;

-- Seed the 8 cold-call stages with aggregated, paraphrased behavioral patterns
insert into public.call_stages (id, position, title, purpose, guidance, prospect_patterns, stage_taps) values
(
  'opening',
  1,
  'Opening',
  'Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.',
  'Be brief, direct, and natural. Verify identity immediately; do not pitch to an assistant or switchboard.',
  '["Could you clarify which company you represent?","The concerned manager is someone else; I can share their direct extension.","The person you are inquiring about has left the organization."]'::jsonb,
  '["Reached right person","Wrong person / referral","Contact left company","Switchboard / PA barrier"]'::jsonb
),
(
  'purpose',
  2,
  'Purpose',
  'Say in one or two sentences why you called, in words the prospect can repeat to a colleague. A purpose they cannot repeat is a purpose they did not hear.',
  'Give a concrete reason for calling without corporate jargon. Avoid sounding like a scripted telemarketer.',
  '["Can you give me a one-sentence summary of what your company does?","Where did you get my contact number?","Is this an outbound sales inquiry?"]'::jsonb,
  '["Asked what we do","Asked where we got number","Said it is a sales call","Let me go on"]'::jsonb
),
(
  'permission',
  3,
  'Permission',
  'Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes. Talking on without one is not.',
  'Test whether they have time right now. Never talk over a busy prospect; secure a specific callback window.',
  '["I am currently in a client meeting; please call back after 2 PM.","I am currently in transit, but you have one minute to explain.","Please share details on WhatsApp or email prior to a call."]'::jsonb,
  '["Agreed to talk now","Callback requested (named time)","Driving / in meeting","Send WhatsApp/Email first"]'::jsonb
),
(
  'their_business',
  4,
  'Their business',
  'Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.',
  'Ask an informed, open question about their operations or focus. Let them speak first; do not jump to the pitch.',
  '["Tell me about your firm first before we discuss our operations.","We are market leaders; that operational model does not apply to us.","That falls under manufacturing; I only manage corporate strategy."]'::jsonb,
  '["Shared operations & setup","Corrected business model","Turned question to caller","Gave minimal 1-line answer"]'::jsonb
),
(
  'their_need',
  5,
  'Their need, in their words',
  'Hear what they are trying to do or struggling with, in their own words. This is the one stage where the caller writes down exactly what was said.',
  'Log their exact words verbatim in the quote box. Do not summarize or paraphrase what they said.',
  '["Our current priority is improving plant capacity utilization and export margins.","Our current business operations are completely stable; no advisory is required.","We are an early-stage startup with limited budget for external consultants."]'::jsonb,
  '["Stated specific priority/bottleneck","Said everything is fine / no need","Startup / too early for advisory","Asked what we can do for them"]'::jsonb
),
(
  'objection',
  6,
  'Objection',
  'Hear the reason for a no and understand it. A reason you understand can be answered on this call or the next; a reason you talked over cannot.',
  'Acknowledge the objection without becoming defensive. Clarify whether it is contract lock-in, internal capability, or bad timing.',
  '["We have a multi-year global contract with an enterprise advisory partner.","We have a robust internal team and process for operational problem solving.","This is not an active priority for us at this time."]'::jsonb,
  '["Global contract / locked vendor","Internal team / robust process","No budget / not a priority","Send info in writing first"]'::jsonb
),
(
  'next_step',
  7,
  'Next step',
  'Agree on one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting. One thing, named, with a time or a channel.',
  'Lock down a specific channel or date/time. A time named by them is worth more than a time proposed by you.',
  '["Please send a summary on WhatsApp and I will review it.","Please send documentation to my official corporate email address.","Call me on Tuesday at 11:30 AM following our management review."]'::jsonb,
  '["Specific callback time set","Official email deck agreed","WhatsApp brief requested","Referred to colleague with contact"]'::jsonb
),
(
  'close',
  8,
  'Close',
  'End the call clearly and record what happened: the outcome, the next step, and the prospect''s words from stage 5. The record is what the next call is built on.',
  'End professionally and immediately record the honest outcome. Never log an outcome that contradicts what the prospect said.',
  '["Confirmed; send the email and we will speak next week.","Thank you for reaching out; have a good day.","[Call disconnected / line dropped]"]'::jsonb,
  '["Confirmed next step & closed clean","Polite exit after objection","Line dropped / hung up","Logged discrepancy for next call"]'::jsonb
)
on conflict (id) do update set
  position = excluded.position,
  title = excluded.title,
  purpose = excluded.purpose,
  guidance = excluded.guidance,
  prospect_patterns = excluded.prospect_patterns,
  stage_taps = excluded.stage_taps;

-- Safe upgrade if tables were created by an earlier version
alter table public.calls add column if not exists ai_summary jsonb;
