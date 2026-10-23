-- =============================================================================
-- Migration: Secure Transactional Offline Call Sync RPC
-- Date: 2026-10-23
-- Description:
--   1. Adds client_call_id column and unique index for idempotency
--   2. Updates public.sync_offline_call_transaction with fixed search_path = ''
--   3. Explicitly schema-qualifies all relations and functions
--   4. Revokes execution from public, anon, and authenticated
--   5. Grants execution solely to service_role
-- =============================================================================

alter table public.calls add column if not exists client_call_id text;
create unique index if not exists calls_client_call_id_idx
  on public.calls(caller_id, client_call_id)
  where client_call_id is not null;

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
