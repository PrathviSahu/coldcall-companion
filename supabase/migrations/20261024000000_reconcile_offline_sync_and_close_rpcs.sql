-- =============================================================================
-- Migration: Reconcile Offline Sync and Atomic Call Closure RPCs
-- Date: 2026-10-24
-- Version: 20261024000000
-- Description:
--   Forward idempotent migration that guarantees the complete required state
--   regardless of which migration was historically recorded under version 20261023:
--   - If 20261023 originally recorded only close_call_rpc, this migration ensures
--     client_call_id, calls_client_call_id_idx, and sync_offline_call_transaction are applied.
--   - If 20261023 recorded sync_offline_rpc, this migration idempotently confirms
--     all schema objects and permissions.
--
-- Guarantees:
--   1. public.calls.client_call_id column exists
--   2. public.calls_client_call_id_idx unique index exists with preflight duplicate checks
--   3. public.sync_offline_call_transaction exists with strict outcome validation,
--      advisory locks, empty search_path, and service_role execution rights
--   4. public.close_call_transaction exists with strict outcome/role validation,
--      row locking (FOR UPDATE), outcome conflict rejection, empty search_path,
--      and service_role execution rights
--   5. Both RPCs revoke execution from PUBLIC, anon, and authenticated
-- =============================================================================

alter table public.calls add column if not exists client_call_id text;

-- Ensure calls_client_call_id_idx exists with the exact required unique partial definition.
-- Note: 'CREATE INDEX IF NOT EXISTS' only checks relation name existence and will NOT
-- repair an index with the same name but an incorrect definition.
-- If an existing index with this name has an incompatible definition, we drop and recreate it.
do $$
declare
  v_idxdef text;
  v_dupe_count integer;
  v_sample_dupe text;
begin
  -- Preflight check: verify no duplicate (caller_id, client_call_id) pairs exist
  -- before creating or rebuilding the unique index.
  select count(*) into v_dupe_count from (
    select caller_id, client_call_id
    from public.calls
    where client_call_id is not null
    group by caller_id, client_call_id
    having count(*) > 1
  ) d;

  if v_dupe_count > 0 then
    select 'caller_id=' || coalesce(caller_id, '<null>') || ', client_call_id=' || coalesce(client_call_id, '<null>') || ' (' || count(*) || ' occurrences)'
    into v_sample_dupe
    from public.calls
    where client_call_id is not null
    group by caller_id, client_call_id
    having count(*) > 1
    limit 1;

    raise exception 'PreflightUniqueConstraintFailed: Cannot create unique index calls_client_call_id_idx because % duplicate (caller_id, client_call_id) groups exist in public.calls. Sample: %. Existing data must be deduplicated before applying this migration.',
      v_dupe_count, v_sample_dupe
      using errcode = '23505';
  end if;

  select indexdef into v_idxdef
  from pg_indexes
  where schemaname = 'public' and tablename = 'calls' and indexname = 'calls_client_call_id_idx';

  if v_idxdef is not null then
    if v_idxdef not like '%UNIQUE%'
       or v_idxdef not like '%(caller_id, client_call_id)%'
       or v_idxdef not like '%WHERE (client_call_id IS NOT NULL)%' then
      raise notice 'Existing calls_client_call_id_idx has incompatible definition (%), dropping and recreating', v_idxdef;
      drop index public.calls_client_call_id_idx;
      create unique index calls_client_call_id_idx
        on public.calls(caller_id, client_call_id)
        where client_call_id is not null;
    end if;
  else
    create unique index calls_client_call_id_idx
      on public.calls(caller_id, client_call_id)
      where client_call_id is not null;
  end if;
end;
$$;


-- Performs call creation, all stage result upserts, and call closure atomically
-- inside a single PostgreSQL transaction. Retrying with the same client_call_id
-- is idempotent and returns the existing record without creating duplicates.
--
-- OUTCOME & NULL SEMANTICS:
-- Offline sync can represent an open call in progress; p_outcome may legitimately
-- be NULL if and only if p_ended_at is also NULL. If p_ended_at is provided,
-- p_outcome must be one of the 11 canonical outcomes and cannot be NULL or blank.
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
  v_clean_outcome pg_catalog.text;
  v_effective_ended_at pg_catalog.timestamptz;
begin
  -- Normalize client_call_id: nullify empty or whitespace strings
  v_clean_client_id := null;
  if p_client_call_id is not null and trim(p_client_call_id) <> '' then
    v_clean_client_id := trim(p_client_call_id);
  end if;

  -- Validate and normalize outcome: reject blank/whitespace or invalid outcomes
  v_clean_outcome := null;
  if p_outcome is not null then
    if trim(p_outcome) = '' then
      raise exception 'DataIntegrityError: Outcome cannot be blank or whitespace-only'
        using errcode = '23514';
    end if;
    if trim(p_outcome) <> p_outcome then
      raise exception 'DataIntegrityError: Outcome cannot contain leading or trailing whitespace: %', p_outcome
        using errcode = '23514';
    end if;
    v_clean_outcome := p_outcome;
    if v_clean_outcome not in (
      'meeting_booked',
      'next_step_agreed',
      'agreed_to_receive_report',
      'follow_up',
      'interested',
      'not_interested',
      'do_not_call',
      'wrong_person',
      'moved_company',
      'no_answer',
      'other'
    ) then
      raise exception 'DataIntegrityError: Invalid outcome %', v_clean_outcome
        using errcode = '23514';
    end if;
  end if;

  -- Validate incoming finalization parameters:
  -- Reject requests where ended_at is provided but outcome is null or blank.
  -- Valid open calls must have both ended_at and outcome as null.
  if p_ended_at is not null and v_clean_outcome is null then
    raise exception 'DataIntegrityError: ended_at cannot be set without a valid outcome'
      using errcode = '23514';
  end if;

  -- Determine effective ended_at:
  -- If finalizing (v_clean_outcome is not null), ensure a non-null ended_at timestamp.
  -- If ended_at was omitted, assign pg_catalog.now().
  -- If open call (v_clean_outcome is null), ended_at remains null.
  v_effective_ended_at := null;
  if v_clean_outcome is not null then
    v_effective_ended_at := coalesce(p_ended_at, pg_catalog.now());
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
          if v_clean_outcome is not null and v_call.outcome <> v_clean_outcome then
            raise exception 'Conflict: Call % is already finalized with outcome %', v_call_id, v_call.outcome
              using errcode = '23505';
          end if;
          -- Already finalized: preserve outcome, outcome_notes, and ended_at as immutable.
          -- Do NOT overwrite them on matching outcome retries.
        else
          -- Call is open: if outcome provided, finalize it now; otherwise update progress
          if v_clean_outcome is not null then
            update public.calls
            set outcome = v_clean_outcome,
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
          -- Defensive checks before keyed insert:
          -- Finalized call requires non-null ended_at and valid outcome;
          -- open call requires both ended_at and outcome to be null.
          if v_clean_outcome is not null and v_effective_ended_at is null then
            raise exception 'DataIntegrityError: finalized call must have non-null ended_at'
              using errcode = '23514';
          end if;
          if v_clean_outcome is null and (v_effective_ended_at is not null or p_ended_at is not null) then
            raise exception 'DataIntegrityError: cannot insert call with ended_at set but outcome null'
              using errcode = '23514';
          end if;

          insert into public.calls (
            caller_id, client_call_id, prospect_name, company_name,
            current_stage_id, started_at, ended_at, outcome, outcome_notes
          ) values (
            p_caller_id, v_clean_client_id, p_prospect_name, p_company_name,
            p_current_stage_id, coalesce(p_started_at, pg_catalog.now()),
            v_effective_ended_at, v_clean_outcome, p_outcome_notes
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
    -- Defensive checks before unkeyed insert:
    -- Finalized call requires non-null ended_at and valid outcome;
    -- open call requires both ended_at and outcome to be null.
    if v_clean_outcome is not null and v_effective_ended_at is null then
      raise exception 'DataIntegrityError: finalized call must have non-null ended_at'
        using errcode = '23514';
    end if;
    if v_clean_outcome is null and (v_effective_ended_at is not null or p_ended_at is not null) then
      raise exception 'DataIntegrityError: cannot insert call with ended_at set but outcome null'
        using errcode = '23514';
    end if;

    insert into public.calls (
      caller_id, client_call_id, prospect_name, company_name,
      current_stage_id, started_at, ended_at, outcome, outcome_notes
    ) values (
      p_caller_id, null, p_prospect_name, p_company_name,
      p_current_stage_id, coalesce(p_started_at, pg_catalog.now()),
      v_effective_ended_at, v_clean_outcome, p_outcome_notes
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
--
-- OUTCOME & NULL SEMANTICS:
-- Unlike offline sync which may sync an in-progress open call with NULL outcome,
-- close_call_transaction is strictly a finalization operation. It strictly
-- rejects NULL, blank, whitespace-padded, or unsupported outcomes before updating.
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
  -- 1. Validate caller identity: reject null, blank, or whitespace-only
  if p_caller_id is null or trim(p_caller_id) = '' then
    raise exception 'Unauthorized: Caller ID cannot be null or blank'
      using errcode = '42501';
  end if;

  -- 2. Validate caller role: reject null or unsupported roles
  if p_caller_role is null or p_caller_role not in ('caller', 'admin') then
    raise exception 'Unauthorized: Invalid caller role %', coalesce(p_caller_role, '<null>')
      using errcode = '42501';
  end if;

  -- 3. Validate outcome: reject null, blank, whitespace-only, whitespace-padded, and unsupported outcomes
  if p_outcome is null or trim(p_outcome) = '' then
    raise exception 'DataIntegrityError: Outcome cannot be null or blank'
      using errcode = '23514';
  end if;

  if trim(p_outcome) <> p_outcome then
    raise exception 'DataIntegrityError: Outcome cannot contain leading or trailing whitespace: %', p_outcome
      using errcode = '23514';
  end if;

  if p_outcome not in (
    'meeting_booked',
    'next_step_agreed',
    'agreed_to_receive_report',
    'follow_up',
    'interested',
    'not_interested',
    'do_not_call',
    'wrong_person',
    'moved_company',
    'no_answer',
    'other'
  ) then
    raise exception 'DataIntegrityError: Invalid outcome %', p_outcome
      using errcode = '23514';
  end if;

  -- 4. Acquire row lock on call record
  select * into v_call from public.calls
  where id = p_call_id
  for update;

  if not found then
    raise exception 'NotFound: Call % not found', p_call_id
      using errcode = 'P0002';
  end if;

  -- 5. Authorization check with IS DISTINCT FROM (preserving admin exception)
  if (v_call.caller_id is distinct from p_caller_id) and (p_caller_role is distinct from 'admin') then
    raise exception 'Forbidden: You are not authorized to close this call'
      using errcode = '42501';
  end if;

  -- 6. Detect inconsistent records (ended_at set but outcome is null)
  if v_call.ended_at is not null and v_call.outcome is null then
    raise exception 'DataIntegrityError: Call % has ended_at set but outcome is null', p_call_id
      using errcode = '23514';
  end if;

  -- 7. Finalization integrity check
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

  -- 8. Construct and return full call object including stage_results
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

