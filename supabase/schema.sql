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

-- Seed the exact 8 cold call stages in authentic sequence with empirical prospect patterns
insert into public.call_stages (id, position, title, purpose, guidance, prospect_patterns, stage_taps) values
(
  'opening',
  1,
  'Opening',
  'Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.',
  'Be brief, direct, and natural. Verify identity immediately; do not pitch to an assistant or switchboard.',
  '["Can you please come again? From where are you calling?","I''ll let you know the concerned person. You can call directly.","The person you are asking for left the company last year."]'::jsonb,
  '["Reached right person","Wrong person / referral","Contact left company","Switchboard / PA barrier"]'::jsonb
),
(
  'purpose',
  2,
  'Purpose',
  'Say in one or two sentences why you called, in words the prospect can repeat to a colleague. A purpose they cannot repeat is a purpose they did not hear.',
  'Give a concrete reason for calling without corporate jargon. Avoid sounding like a scripted telemarketer.',
  '["What is this about? Can you just elaborate?","Uh, from where? What does your company do?","Who gave you this number? Where did you get my contact?","Is this a sales call? What are you proposing?"]'::jsonb,
  '["Understood & listening","Asked what company does","Asked where we got number","Flagged as sales call"]'::jsonb
),
(
  'permission',
  3,
  'Permission',
  'Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes. Talking on without one is not.',
  'Test whether they have time right now. Never talk over a busy prospect; secure a specific callback window.',
  '["Actually right now I''m in a customer meeting. Can you call after 2 PM?","I am driving right now, but tell me quickly.","Can you call me tomorrow afternoon? I will have a few minutes.","Send it on WhatsApp first. Let me see it before we talk."]'::jsonb,
  '["Agreed to talk now","Callback requested (named time)","Driving / in meeting","Send WhatsApp/Email first"]'::jsonb
),
(
  'their_business',
  4,
  'Their business',
  'Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.',
  'Ask an informed, open question about their operations or focus. Let them speak first; do not jump to the pitch.',
  '["Tell me about your company first, then we can get into details.","Our company is the market leader; we don''t fit that profile.","That pertains to manufacturing; I only handle corporate strategy.","We operate primarily through an authorized distributor network."]'::jsonb,
  '["Shared operations & setup","Corrected business model","Turned question to caller","Gave minimal 1-line answer"]'::jsonb
),
(
  'their_need',
  5,
  'Their need, in their words',
  'Hear what they are trying to do or struggling with, in their own words. This is the one stage where the caller writes down exactly what was said.',
  'Log their exact words verbatim in the quote box. Do not summarize or paraphrase what they said.',
  '["Our main priority right now is expanding export margins and plant utilization.","We don''t believe in external experiments. We are fine with our current business.","Because we are still an early startup, we don''t have the budget or requirement for that now.","What exactly would you require from our side to make this work?"]'::jsonb,
  '["Stated specific priority/bottleneck","Said everything is fine / no need","Startup / too early for advisory","Asked what we can do for them"]'::jsonb
),
(
  'objection',
  6,
  'Objection',
  'Hear the reason for a no and understand it. A reason you understand can be answered on this call or the next; a reason you talked over cannot.',
  'Acknowledge the objection without becoming defensive. Clarify whether it is contract lock-in, internal capability, or bad timing.',
  '["Because we are an MNC, we already have such consultants at a global level under a single contract.","We already engaged a consultant last month; that''s going to run for two quarters.","We have a robust process internally which we use for problem solving; we don''t outsource.","I am not interested in this at the moment. Thank you for asking though."]'::jsonb,
  '["Global contract / locked vendor","Internal team / robust process","No budget / not a priority","Send info in writing first"]'::jsonb
),
(
  'next_step',
  7,
  'Next step',
  'Agree one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting. One thing, named, with a time or a channel.',
  'Lock down a specific channel or date/time. A time named by them is worth more than a time proposed by you.',
  '["You send it on WhatsApp to this number. Let me have a look and come back to you.","That''s my personal email; please send it to my official company ID.","Give me a call sometime Tuesday morning around 11:30 AM after my meeting.","You can send an email with your previous profiles and case studies for review."]'::jsonb,
  '["Specific callback time set","Official email deck agreed","WhatsApp brief requested","Referred to colleague with contact"]'::jsonb
),
(
  'close',
  8,
  'Close',
  'End the call clearly and record what happened: the outcome, the next step, and the prospect''s words from stage 5. The record is what the next call is built on.',
  'End professionally and immediately record the honest outcome. Never log an outcome that contradicts what the prospect said.',
  '["Sure, thank you Priya/Rohit. Send it over email and we will connect next week.","All set. Thank you for your time, have a good day.","Okay, fine, works. Bye.","[Call disconnected / line dropped]"]'::jsonb,
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
