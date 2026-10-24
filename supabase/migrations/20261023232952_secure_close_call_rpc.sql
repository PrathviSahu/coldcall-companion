-- Migration: Atomic Call Closure RPC
-- Date: 2026-10-23
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
