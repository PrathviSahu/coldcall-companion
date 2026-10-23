-- =============================================================================
-- COLDCALL COMPANION — SUPABASE POSTGRESQL SCHEMA & RLS POLICIES
-- =============================================================================

create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- 1. Call Stages Table
-- -----------------------------------------------------------------------------
create table if not exists public.call_stages (
  id text primary key,
  position integer not null unique,
  title text not null,
  purpose text not null,
  guidance text not null,
  prospect_patterns jsonb not null default '[]'::jsonb,
  stage_taps jsonb not null default '[]'::jsonb
);

-- Upgrade column if table already exists from earlier migrations
alter table public.call_stages add column if not exists stage_taps jsonb not null default '[]'::jsonb;

-- -----------------------------------------------------------------------------
-- 2. Calls Table (Caller Isolation & State)
-- -----------------------------------------------------------------------------
create table if not exists public.calls (
  id uuid primary key default gen_random_uuid(),
  caller_id text not null default 'anonymous-caller',
  client_call_id text,
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

-- Safe column upgrade for existing databases
alter table public.calls add column if not exists caller_id text not null default 'anonymous-caller';
alter table public.calls add column if not exists ai_summary jsonb;
alter table public.calls add column if not exists client_call_id text;
create unique index if not exists calls_client_call_id_idx on public.calls(caller_id, client_call_id) where client_call_id is not null;

-- -----------------------------------------------------------------------------
-- Legacy Record Migration & Ownership Reassignment Procedure
-- -----------------------------------------------------------------------------
-- Pre-existing calls created before authentication was introduced received
-- caller_id = 'anonymous-caller'.
-- Under caller-isolation rules, 'anonymous-caller' records are hidden from standard
-- sales reps and are only visible to administrators (role='admin').
--
-- IMPORTANT: Do NOT run a blanket update blindly assigning all records to a single rep.
-- 1. First audit existing unassigned records to determine true ownership:
--      SELECT id, prospect_name, company_name, started_at, outcome
--      FROM public.calls
--      WHERE caller_id = 'anonymous-caller'
--      ORDER BY started_at DESC;
--
-- 2. Selectively reassign records to specific sales reps based on account ownership:
--      UPDATE public.calls
--      SET caller_id = 'rep-alpha'
--      WHERE caller_id = 'anonymous-caller'
--        AND company_name IN ('Target Enterprise A', 'Target Enterprise B');
--
-- NEVER execute destructive DELETE statements on legacy calls.

-- -----------------------------------------------------------------------------
-- 3. Stage Results Table (Idempotent Upsert on call_id, stage_id)
-- -----------------------------------------------------------------------------
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

-- Indexes for performant filtering and sorting
create index if not exists calls_started_at_idx on public.calls(started_at desc);
create index if not exists calls_caller_started_idx on public.calls(caller_id, started_at desc);
create index if not exists call_stage_results_call_idx on public.call_stage_results(call_id, created_at);

-- -----------------------------------------------------------------------------
-- 4. Row Level Security (RLS) & Access Policies
-- -----------------------------------------------------------------------------
alter table public.call_stages enable row level security;
alter table public.calls enable row level security;
alter table public.call_stage_results enable row level security;

-- Stages Policy: Public read-only for application reference
drop policy if exists "call_stages_read_all" on public.call_stages;
create policy "call_stages_read_all" on public.call_stages
  for select using (true);

-- Calls Policy: Authenticated caller isolation + Service Role full access
drop policy if exists "calls_caller_isolation" on public.calls;
create policy "calls_caller_isolation" on public.calls
  for all using (
    auth.role() = 'service_role' or
    (auth.uid() is not null and caller_id = auth.uid()::text)
  );

-- Stage Results Policy: Cascade isolation through parent call
drop policy if exists "stage_results_caller_isolation" on public.call_stage_results;
create policy "stage_results_caller_isolation" on public.call_stage_results
  for all using (
    auth.role() = 'service_role' or
    exists (
      select 1 from public.calls c
      where c.id = call_stage_results.call_id
      and (auth.role() = 'service_role' or (auth.uid() is not null and c.caller_id = auth.uid()::text))
    )
  );

-- -----------------------------------------------------------------------------
-- 5. Seed the Eight Outbound Stages
-- -----------------------------------------------------------------------------
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
  '["Understood & listening","Asked what company does","Asked where we got number","Flagged as sales call"]'::jsonb
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


-- -----------------------------------------------------------------------------
-- 7. Transactional Offline Call Sync (Atomic & Idempotent RPC)
-- -----------------------------------------------------------------------------
-- Performs call creation, all stage result upserts, and call closure atomically
-- inside a single PostgreSQL transaction. Retrying with the same client_call_id
-- is idempotent and returns the existing record without creating duplicates.
--
-- SECURITY HARDENING:
-- 1. Fixed empty search_path (SET search_path = '') prevents search-path hijacking.
-- 2. Fully schema-qualified references (public.*, pg_catalog.*) protect execution integrity.
-- 3. Default execution privileges REVOKED from PUBLIC, anon, and authenticated.
-- 4. EXECUTE is GRANTED SOLELY to service_role (the server-side FastAPI client).
--    Direct public REST/RPC invocation by anonymous callers is completely blocked.
create or replace function public.sync_offline_call_transaction(
  p_caller_id text,
  p_client_call_id text,
  p_prospect_name text,
  p_company_name text,
  p_current_stage_id text,
  p_started_at timestamptz,
  p_ended_at timestamptz,
  p_outcome text,
  p_outcome_notes text,
  p_stage_results jsonb
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_call_id pg_catalog.uuid;
  v_call record;
  v_sr pg_catalog.jsonb;
  v_stage_id pg_catalog.text;
  v_result pg_catalog.text;
  v_words pg_catalog.text;
  v_notes pg_catalog.text;
  v_result_json pg_catalog.jsonb;
  v_clean_client_id pg_catalog.text;
begin
  -- Normalize client_call_id: nullify empty or whitespace strings
  v_clean_client_id := null;
  if p_client_call_id is not null and trim(p_client_call_id) <> '' then
    v_clean_client_id := trim(p_client_call_id);
  end if;

  -- Validate incoming finalization parameters:
  -- Reject requests where ended_at is provided but outcome is null.
  -- Valid open calls must have both ended_at and outcome as null.
  if p_ended_at is not null and p_outcome is null then
    raise exception 'DataIntegrityError: ended_at cannot be set without a valid outcome'
      using errcode = '23514';
  end if;

  -- 1. Idempotency & Concurrency: If client_call_id is present, serialize and look up
  if v_clean_client_id is not null then
    -- Transaction-level advisory lock serializes concurrent syncs with the exact same caller & client_call_id
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext(p_caller_id || ':' || v_clean_client_id));

    -- Loop to handle racing non-advisory insertions (e.g. from POST /calls)
    loop
      select * into v_call from public.calls
      where caller_id = p_caller_id and client_call_id = v_clean_client_id
      for update;

      if found then
        v_call_id := v_call.id;

        -- Inconsistent state check
        if v_call.ended_at is not null and v_call.outcome is null then
          raise exception 'DataIntegrityError: Call % has ended_at set but outcome is null', v_call_id
            using errcode = '23514';
        end if;

        -- Check if already finalized
        if v_call.outcome is not null then
          if p_outcome is not null and v_call.outcome <> p_outcome then
            raise exception 'Conflict: Call % is already finalized with outcome %', v_call_id, v_call.outcome
              using errcode = '23505';
          end if;
          -- Already finalized: preserve outcome, outcome_notes, and ended_at as immutable.
          -- Do NOT overwrite them on matching outcome retries.
        else
          -- Call is open: if outcome provided, finalize it now; otherwise update progress
          if p_outcome is not null then
            update public.calls
            set outcome = p_outcome,
                outcome_notes = coalesce(p_outcome_notes, outcome_notes),
                ended_at = coalesce(p_ended_at, pg_catalog.now()),
                current_stage_id = coalesce(p_current_stage_id, current_stage_id)
            where id = v_call_id;
          elsif p_current_stage_id is not null then
            update public.calls
            set current_stage_id = p_current_stage_id
            where id = v_call_id;
          end if;
        end if;
        exit;
      else
        begin
          -- Defensive check before keyed insert
          if p_ended_at is not null and p_outcome is null then
            raise exception 'DataIntegrityError: cannot insert call with ended_at set but outcome null'
              using errcode = '23514';
          end if;

          insert into public.calls (
            caller_id, client_call_id, prospect_name, company_name,
            current_stage_id, started_at, ended_at, outcome, outcome_notes
          ) values (
            p_caller_id, v_clean_client_id, p_prospect_name, p_company_name,
            p_current_stage_id, coalesce(p_started_at, pg_catalog.now()), p_ended_at, p_outcome, p_outcome_notes
          ) returning id into v_call_id;
          exit;
        exception when unique_violation then
          -- A competing insert committed. Loop back, acquire row lock with FOR UPDATE,
          -- and enforce the outcome-conflict check atomically.
        end;
      end if;
    end loop;
  else
    -- Deliberate null client_call_id path: creates an unkeyed call record
    -- Defensive check before unkeyed insert
    if p_ended_at is not null and p_outcome is null then
      raise exception 'DataIntegrityError: cannot insert call with ended_at set but outcome null'
        using errcode = '23514';
    end if;

    insert into public.calls (
      caller_id, client_call_id, prospect_name, company_name,
      current_stage_id, started_at, ended_at, outcome, outcome_notes
    ) values (
      p_caller_id, null, p_prospect_name, p_company_name,
      p_current_stage_id, coalesce(p_started_at, pg_catalog.now()), p_ended_at, p_outcome, p_outcome_notes
    ) returning id into v_call_id;
  end if;

  -- 2. Insert / upsert all stage results within the same transaction
  if p_stage_results is not null and pg_catalog.jsonb_array_length(p_stage_results) > 0 then
    for v_sr in select * from pg_catalog.jsonb_array_elements(p_stage_results) loop
      v_stage_id := v_sr->>'stage_id';
      v_result := coalesce(v_sr->>'result', 'completed');
      v_words := coalesce(v_sr->>'prospect_words', '');
      v_notes := coalesce(v_sr->>'notes', '');

      insert into public.call_stage_results (call_id, stage_id, result, prospect_words, notes, updated_at)
      values (v_call_id, v_stage_id, v_result, v_words, v_notes, pg_catalog.now())
      on conflict (call_id, stage_id) do update
      set result = excluded.result,
          prospect_words = excluded.prospect_words,
          notes = excluded.notes,
          updated_at = excluded.updated_at;
    end loop;
  end if;

  -- 3. Construct and return full call object including stage_results
  select pg_catalog.jsonb_build_object(
    'id', c.id,
    'caller_id', c.caller_id,
    'client_call_id', c.client_call_id,
    'prospect_name', c.prospect_name,
    'company_name', c.company_name,
    'current_stage_id', c.current_stage_id,
    'started_at', c.started_at,
    'ended_at', c.ended_at,
    'outcome', c.outcome,
    'outcome_notes', c.outcome_notes,
    'created_at', c.created_at,
    'stage_results', coalesce(
      (select pg_catalog.jsonb_agg(pg_catalog.to_jsonb(csr)) from public.call_stage_results csr where csr.call_id = c.id),
      '[]'::pg_catalog.jsonb
    )
  ) into v_result_json
  from public.calls c where c.id = v_call_id;

  return v_result_json;
end;
$$;

-- -----------------------------------------------------------------------------
-- Privilege Hardening: Restrict RPC execution to service_role ONLY
-- -----------------------------------------------------------------------------
revoke all on function public.sync_offline_call_transaction(
  text, text, text, text, text, timestamptz, timestamptz, text, text, jsonb
) from public;

revoke all on function public.sync_offline_call_transaction(
  text, text, text, text, text, timestamptz, timestamptz, text, text, jsonb
) from anon;

revoke all on function public.sync_offline_call_transaction(
  text, text, text, text, text, timestamptz, timestamptz, text, text, jsonb
) from authenticated;

grant execute on function public.sync_offline_call_transaction(
  text, text, text, text, text, timestamptz, timestamptz, text, text, jsonb
) to service_role;


-- -----------------------------------------------------------------------------
-- 8. Atomic Call Closure (Row-Locked & Idempotent RPC)
-- -----------------------------------------------------------------------------
-- Locks the call record with FOR UPDATE to prevent race conditions between
-- concurrent close requests. Enforces outcome validation, authorization, and
-- idempotent matching retries atomically in PostgreSQL.
create or replace function public.close_call_transaction(
  p_call_id uuid,
  p_caller_id text,
  p_caller_role text,
  p_outcome text,
  p_outcome_notes text default null,
  p_ended_at timestamptz default null
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_call record;
  v_res jsonb;
begin
  -- 1. Acquire row lock on call record
  select * into v_call from public.calls
  where id = p_call_id
  for update;

  if not found then
    raise exception 'NotFound: Call % not found', p_call_id
      using errcode = 'P0002';
  end if;

  -- 2. Authorization check
  if v_call.caller_id <> p_caller_id and p_caller_role <> 'admin' then
    raise exception 'Forbidden: You are not authorized to close this call'
      using errcode = '42501';
  end if;

  -- 3. Detect inconsistent records (ended_at set but outcome is null)
  if v_call.ended_at is not null and v_call.outcome is null then
    raise exception 'DataIntegrityError: Call % has ended_at set but outcome is null', p_call_id
      using errcode = '23514';
  end if;

  -- 4. Finalization integrity check
  if v_call.outcome is not null then
    if v_call.outcome <> p_outcome then
      raise exception 'Conflict: Call % is already finalized with outcome %', p_call_id, v_call.outcome
        using errcode = '23505';
    end if;
    -- Already finalized with matching outcome: idempotent retry, do not mutate persisted outcome/notes/ended_at
  else
    -- Call is open: finalize atomically
    update public.calls
    set outcome = p_outcome,
        outcome_notes = coalesce(p_outcome_notes, outcome_notes),
        ended_at = coalesce(p_ended_at, pg_catalog.now())
    where id = p_call_id;
  end if;

  -- 4. Construct and return full call object including stage_results
  select pg_catalog.jsonb_build_object(
    'id', c.id,
    'caller_id', c.caller_id,
    'client_call_id', c.client_call_id,
    'prospect_name', c.prospect_name,
    'company_name', c.company_name,
    'current_stage_id', c.current_stage_id,
    'started_at', c.started_at,
    'ended_at', c.ended_at,
    'outcome', c.outcome,
    'outcome_notes', c.outcome_notes,
    'created_at', c.created_at,
    'stage_results', coalesce(
      (select pg_catalog.jsonb_agg(pg_catalog.to_jsonb(csr)) from public.call_stage_results csr where csr.call_id = c.id),
      '[]'::pg_catalog.jsonb
    )
  ) into v_res
  from public.calls c where c.id = p_call_id;

  return v_res;
end;
$$;

revoke all on function public.close_call_transaction(uuid, text, text, text, text, timestamptz) from public;
revoke all on function public.close_call_transaction(uuid, text, text, text, text, timestamptz) from anon;
revoke all on function public.close_call_transaction(uuid, text, text, text, text, timestamptz) from authenticated;
grant execute on function public.close_call_transaction(uuid, text, text, text, text, timestamptz) to service_role;
