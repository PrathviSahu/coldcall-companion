from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Self
from uuid import UUID
import json
import ipaddress

from fastapi import FastAPI, HTTPException, Security, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

try:
    from supabase import create_client, Client
except ImportError:  # allows local health/stage previews before installing optional DB dependency
    Client = Any  # type: ignore[misc,assignment]
    create_client = None

app = FastAPI(title="ColdCall Companion API", version="0.3.0")

# -----------------------------------------------------------------------------
# CORS Policy (Explicit Origins, No Wildcard with Credentials)
# -----------------------------------------------------------------------------
raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
allowed_origins = [x.strip() for x in raw_cors.split(",") if x.strip()]
# Strip wildcard to ensure secure credentials exchange
allowed_origins = [o for o in allowed_origins if o != "*"]
if not allowed_origins:
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

supabase: Client | None = None
_sb_url = (os.getenv("SUPABASE_URL") or "").strip()
_sb_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
if create_client is not None and _sb_url and _sb_key:
    supabase = create_client(_sb_url, _sb_key)

# -----------------------------------------------------------------------------
# Caller Authentication & Authorization Model
# -----------------------------------------------------------------------------
class Caller(BaseModel):
    id: str
    name: str = ""
    role: str = "caller"  # "caller" | "admin"

security_bearer = HTTPBearer(auto_error=False)

def parse_auth_tokens() -> dict[str, Caller]:
    """
    Parses configured tokens from environment variable CALLER_AUTH_TOKENS.
    Format: comma-separated list of entries:
      - caller_id:token (role defaults to 'caller')
      - caller_id:token:role (e.g. ops_lead:strong_secret_token_123:admin)
    Fails closed: returns an empty mapping if CALLER_AUTH_TOKENS is unset or empty.
    Never injects hardcoded default credentials or wildcard tokens.
    """
    raw = os.getenv("CALLER_AUTH_TOKENS", "").strip()
    mapping: dict[str, Caller] = {}
    if not raw:
        return mapping

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(":") if p.strip()]
        if len(parts) == 2:
            cid, token = parts
            mapping[token] = Caller(id=cid, name=f"Caller {cid}", role="caller")
        elif len(parts) >= 3:
            cid, token, role = parts[:3]
            clean_role = "admin" if role.lower() == "admin" else "caller"
            mapping[token] = Caller(id=cid, name=f"Caller {cid}", role=clean_role)
    return mapping


def get_current_caller(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> Caller:
    """
    Enforces authentication for call data operations. Returns the authenticated Caller.
    Strictly verifies token against configured CALLER_AUTH_TOKENS.
    No prefix inference, no dynamic fallbacks, no hardcoded defaults.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: Provide a valid Bearer token in Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials.strip()
    auth_tokens = parse_auth_tokens()
    caller = auth_tokens.get(token)

    if not caller:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token: Access denied",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return caller


# -----------------------------------------------------------------------------
# Eight Verified Cold-Call Stages
# -----------------------------------------------------------------------------
STARTER_STAGES: list[dict[str, Any]] = [
    {
        "id": "opening",
        "position": 1,
        "title": "Opening",
        "purpose": "Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.",
        "guidance": "Be brief, direct, and natural. Verify identity immediately; do not pitch to an assistant or switchboard.",
        "prospect_patterns": [
            "Could you clarify which company you represent?",
            "The concerned manager is someone else; I can share their direct extension.",
            "The person you are inquiring about has left the organization."
        ],
        "stage_taps": [
            "Reached right person",
            "Wrong person / referral",
            "Contact left company",
            "Switchboard / PA barrier",
        ],
    },
    {
        "id": "purpose",
        "position": 2,
        "title": "Purpose",
        "purpose": "Say in one or two sentences why you called, in words the prospect can repeat to a colleague. A purpose they cannot repeat is a purpose they did not hear.",
        "guidance": "Give a concrete reason for calling without corporate jargon. Avoid sounding like a scripted telemarketer.",
        "prospect_patterns": [
            "Can you give me a one-sentence summary of what your company does?",
            "Where did you get my contact number?",
            "Is this an outbound sales inquiry?"
        ],
        "stage_taps": [
            "Understood & listening",
            "Asked what company does",
            "Asked where we got number",
            "Flagged as sales call",
        ],
    },
    {
        "id": "permission",
        "position": 3,
        "title": "Permission",
        "purpose": "Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes. Talking on without one is not.",
        "guidance": "Test whether they have time right now. Never talk over a busy prospect; secure a specific callback window.",
        "prospect_patterns": [
            "I am currently in a client meeting; please call back after 2 PM.",
            "I am currently in transit, but you have one minute to explain.",
            "Please share details on WhatsApp or email prior to a call."
        ],
        "stage_taps": [
            "Agreed to talk now",
            "Callback requested (named time)",
            "Driving / in meeting",
            "Send WhatsApp/Email first",
        ],
    },
    {
        "id": "their_business",
        "position": 4,
        "title": "Their business",
        "purpose": "Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.",
        "guidance": "Ask an informed, open question about their operations or focus. Let them speak first; do not jump to the pitch.",
        "prospect_patterns": [
            "Tell me about your firm first before we discuss our operations.",
            "We are market leaders; that operational model does not apply to us.",
            "That falls under manufacturing; I only manage corporate strategy."
        ],
        "stage_taps": [
            "Shared operations & setup",
            "Corrected business model",
            "Turned question to caller",
            "Gave minimal 1-line answer",
        ],
    },
    {
        "id": "their_need",
        "position": 5,
        "title": "Their need, in their words",
        "purpose": "Hear what they are trying to do or struggling with, in their own words. This is the one stage where the caller writes down exactly what was said.",
        "guidance": "Log their exact words verbatim in the quote box. Do not summarize or paraphrase what they said.",
        "prospect_patterns": [
            "Our current priority is improving plant capacity utilization and export margins.",
            "Our current business operations are completely stable; no advisory is required.",
            "We are an early-stage startup with limited budget for external consultants."
        ],
        "stage_taps": [
            "Stated specific priority/bottleneck",
            "Said everything is fine / no need",
            "Startup / too early for advisory",
            "Asked what we can do for them",
        ],
    },
    {
        "id": "objection",
        "position": 6,
        "title": "Objection",
        "purpose": "Hear the reason for a no and understand it. A reason you understand can be answered on this call or the next; a reason you talked over cannot.",
        "guidance": "Acknowledge the objection without becoming defensive. Clarify whether it is contract lock-in, internal capability, or bad timing.",
        "prospect_patterns": [
            "We have a multi-year global contract with an enterprise advisory partner.",
            "We have a robust internal team and process for operational problem solving.",
            "This is not an active priority for us at this time."
        ],
        "stage_taps": [
            "Global contract / locked vendor",
            "Internal team / robust process",
            "No budget / not a priority",
            "Send info in writing first",
        ],
    },
    {
        "id": "next_step",
        "position": 7,
        "title": "Next step",
        "purpose": "Agree one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting. One thing, named, with a time or a channel.",
        "guidance": "Lock down a specific channel or date/time. A time named by them is worth more than a time proposed by you.",
        "prospect_patterns": [
            "Please send a summary on WhatsApp and I will review it.",
            "Please send documentation to my official corporate email address.",
            "Call me on Tuesday at 11:30 AM following our management review."
        ],
        "stage_taps": [
            "Specific callback time set",
            "Official email deck agreed",
            "WhatsApp brief requested",
            "Referred to colleague with contact",
        ],
    },
    {
        "id": "close",
        "position": 8,
        "title": "Close",
        "purpose": "End the call clearly and record what happened: the outcome, the next step, and the prospect's words from stage 5. The record is what the next call is built on.",
        "guidance": "End professionally and immediately record the honest outcome. Never log an outcome that contradicts what the prospect said.",
        "prospect_patterns": [
            "Confirmed; send the email and we will speak next week.",
            "Thank you for reaching out; have a good day.",
            "[Call disconnected / line dropped]",
        ],
        "stage_taps": [
            "Confirmed next step & closed clean",
            "Polite exit after objection",
            "Line dropped / hung up",
            "Logged discrepancy for next call",
        ],
    },
]

# -----------------------------------------------------------------------------
# Allowed Outcome Types
# -----------------------------------------------------------------------------
ALLOWED_OUTCOMES = {
    "meeting_booked",
    "next_step_agreed",
    "agreed_to_receive_report",
    "follow_up",
    "interested",
    "not_interested",
    "do_not_call",
    "wrong_person",
    "moved_company",
    "no_answer",
    "other",
}

# -----------------------------------------------------------------------------
# Input Validation Schemas
# -----------------------------------------------------------------------------
class StartCall(BaseModel):
    client_call_id: str | None = Field(default=None, max_length=120)
    prospect_name: str | None = Field(default=None, max_length=160)
    company_name: str | None = Field(default=None, max_length=180)
    started_at: datetime | None = None

class SaveStage(BaseModel):
    stage_id: str
    result: str = Field(default="completed", max_length=160)
    prospect_words: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=4000)

class CloseCall(BaseModel):
    outcome: str = Field(..., max_length=100)
    outcome_notes: str = Field(default="", max_length=4000)
    ended_at: datetime | None = None

class SyncOfflineCall(BaseModel):
    client_call_id: str | None = Field(default=None, max_length=120)
    prospect_name: str | None = Field(default=None, max_length=160)
    company_name: str | None = Field(default=None, max_length=180)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    outcome: str | None = Field(default=None, max_length=100)
    outcome_notes: str = Field(default="", max_length=4000)
    current_stage_id: str | None = None
    stage_results: list[SaveStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_finalization_consistency(self) -> Self:
        clean_outcome = self.outcome.strip() if self.outcome is not None and self.outcome.strip() else None
        if self.outcome is not None and not clean_outcome:
            raise ValueError("Outcome cannot be blank or whitespace-only")
        if clean_outcome and clean_outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid outcome: '{self.outcome}'. Must be one of: {sorted(ALLOWED_OUTCOMES)}")
        if self.ended_at is not None and not clean_outcome:
            raise ValueError("Inconsistent call state: ended_at cannot be set without a valid outcome")
        return self

class UpdateStage(BaseModel):
    stage_id: str


def fetch_one(query: Any) -> dict[str, Any] | None:
    """Executes a Supabase table query and returns the first matching record dict, or None."""
    res = query.execute()
    data = res.data
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if len(data) > 0 else None
    if isinstance(data, dict):
        return data
    return None


def db() -> Client:
    if supabase is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return supabase


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    """Public health probe for uptime monitors and load balancers."""
    configured = supabase is not None
    llm_configured = bool(os.getenv("LLM_API_KEY"))
    if not configured:
        return {
            "status": "ok",
            "database": "not_configured",
            "llm": "configured" if llm_configured else "disabled",
            "auth": "enforced",
            "service": "coldcall-companion-api",
            "version": "0.3.0"
        }
    try:
        db().table("call_stages").select("id").limit(1).execute()
        return {
            "status": "ok",
            "database": "connected",
            "llm": "configured" if llm_configured else "disabled",
            "auth": "enforced",
            "service": "coldcall-companion-api",
            "version": "0.3.0"
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "database": "error",
            "llm": "configured" if llm_configured else "disabled",
            "auth": "enforced",
            "detail": str(exc)[:180],
            "service": "coldcall-companion-api",
            "version": "0.3.0"
        }


@app.get("/stages")
def list_stages() -> list[dict[str, Any]]:
    """Returns the eight cold-call stages with prospect cues and quick taps."""
    if supabase is None:
        return STARTER_STAGES
    try:
        response = db().table("call_stages").select("*").order("position").execute()
        if response.data and len(response.data) == 8:
            return response.data
        return STARTER_STAGES
    except Exception:
        return STARTER_STAGES


@app.post("/calls")
def start_call(payload: StartCall, caller: Caller = Depends(get_current_caller)) -> dict[str, Any]:
    """Creates a new persistent call stamped with the authenticated caller's identity."""
    d = db()
    clean_client_id = payload.client_call_id.strip() if payload.client_call_id and payload.client_call_id.strip() else None

    # Idempotency check if client_call_id is provided
    if clean_client_id:
        existing = fetch_one(
            d.table("calls")
            .select("*")
            .eq("caller_id", caller.id)
            .eq("client_call_id", clean_client_id)
        )
        if existing:
            return existing

    stages = list_stages()
    first_stage_id = stages[0]["id"] if stages else "opening"
    row: dict[str, Any] = {
        "caller_id": caller.id,
        "client_call_id": clean_client_id,
        "prospect_name": payload.prospect_name,
        "company_name": payload.company_name,
        "current_stage_id": first_stage_id,
    }
    if payload.started_at:
        row["started_at"] = payload.started_at.isoformat()

    try:
        response = d.table("calls").insert(row).execute()
        if not response.data:
            raise HTTPException(500, "Could not create call")
        return response.data[0]
    except Exception as exc:
        err_msg = str(exc)
        # Safely handle concurrent race on unique index (caller_id, client_call_id)
        if clean_client_id and ("calls_client_call_id_idx" in err_msg or "23505" in err_msg or "duplicate key" in err_msg.lower()):
            existing = fetch_one(
                d.table("calls")
                .select("*")
                .eq("caller_id", caller.id)
                .eq("client_call_id", clean_client_id)
            )
            if existing:
                return existing
        raise HTTPException(500, f"Could not create call: {exc}")


@app.post("/calls/{call_id}/stage-results")
def save_stage(
    call_id: UUID,
    payload: SaveStage,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """Saves or updates notes, exact words, and quick taps. Enforces caller ownership and closed-call restrictions."""
    d = db()
    valid_stages = {s["id"] for s in list_stages()}
    if payload.stage_id not in valid_stages:
        raise HTTPException(400, f"Unknown stage_id: {payload.stage_id}")

    call = fetch_one(d.table("calls").select("id,caller_id,ended_at").eq("id", str(call_id)))
    if not call:
        raise HTTPException(404, "Call not found")
    if call.get("caller_id") != caller.id and caller.role != "admin":
        raise HTTPException(403, "Forbidden: You are not authorized to update this call")
    if call.get("ended_at"):
        raise HTTPException(409, "Call is already closed")

    row = {
        "call_id": str(call_id),
        "stage_id": payload.stage_id,
        "result": payload.result,
        "prospect_words": payload.prospect_words,
        "notes": payload.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = d.table("call_stage_results").upsert(row, on_conflict="call_id,stage_id").execute()
    d.table("calls").update({"current_stage_id": payload.stage_id}).eq("id", str(call_id)).execute()
    if not response.data:
        raise HTTPException(500, "Could not save stage result")
    return response.data[0]


@app.patch("/calls/{call_id}/stage")
def set_current_stage(
    call_id: UUID,
    payload: UpdateStage,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """Updates active stage tracker position. Enforces caller ownership and open call status."""
    d = db()
    valid_stages = {s["id"] for s in list_stages()}
    if payload.stage_id not in valid_stages:
        raise HTTPException(400, f"Unknown stage_id: {payload.stage_id}")

    call = fetch_one(d.table("calls").select("id,caller_id,ended_at").eq("id", str(call_id)))
    if not call:
        raise HTTPException(404, "Call not found")
    if call.get("caller_id") != caller.id and caller.role != "admin":
        raise HTTPException(403, "Forbidden: You are not authorized to update this call")
    if call.get("ended_at"):
        raise HTTPException(409, "Call is already closed")

    response = d.table("calls").update({"current_stage_id": payload.stage_id}).eq("id", str(call_id)).execute()
    if not response.data:
        raise HTTPException(404, "Could not update call stage")
    return response.data[0]


@app.post("/calls/{call_id}/close")
def close_call(
    call_id: UUID,
    payload: CloseCall,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """Closes an active call with outcome and context notes. Enforces outcome validation and safe idempotency on retry."""
    d = db()
    if payload.outcome not in ALLOWED_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid outcome: '{payload.outcome}'. Must be one of: {sorted(ALLOWED_OUTCOMES)}"
        )

    ended_at_val = payload.ended_at.isoformat() if payload.ended_at else datetime.now(timezone.utc).isoformat()

    # 1. Attempt Atomic PostgreSQL Transactional RPC (Primary row-locked path)
    # The RPC acquires a row lock (FOR UPDATE), enforces authorization, and guarantees
    # that concurrent requests with different outcomes cannot overwrite one another.
    try:
        rpc_res = d.rpc("close_call_transaction", {
            "p_call_id": str(call_id),
            "p_caller_id": caller.id,
            "p_caller_role": caller.role,
            "p_outcome": payload.outcome,
            "p_outcome_notes": payload.outcome_notes,
            "p_ended_at": ended_at_val,
        }).execute()
        if rpc_res and rpc_res.data:
            return rpc_res.data
    except Exception as exc:
        err_msg = str(exc)
        if "NotFound" in err_msg or "P0002" in err_msg:
            raise HTTPException(404, "Call not found")
        if "Forbidden" in err_msg or "42501" in err_msg:
            raise HTTPException(403, "Forbidden: You are not authorized to close this call")
        if "DataIntegrityError" in err_msg or "23514" in err_msg:
            raise HTTPException(
                status_code=409,
                detail=f"Inconsistent call state: call has ended_at set but outcome is null ({err_msg})"
            )
        if "already finalized" in err_msg or "Conflict" in err_msg or "23505" in err_msg:
            raise HTTPException(
                status_code=409,
                detail=f"Call is already closed with conflicting outcome: {err_msg}"
            )
        # If the RPC function does not exist in mock or database, use the atomic conditional table update below
        err_lower = err_msg.lower()
        is_missing_rpc = (
            "close_call_transaction" in err_lower
            and any(k in err_lower for k in [
                "not exist",
                "could not find",
                "not found",
                "pgrst202",
                "42883",
                "schema cache",
                "not implemented",
            ])
        ) or "pgrst202" in err_lower
        if not is_missing_rpc:
            raise HTTPException(500, f"Could not close call: {exc}")

    # 2. Atomic Conditional Table Update (Defense-in-depth / Mock fallback)
    call = fetch_one(d.table("calls").select("id,caller_id,ended_at,outcome,outcome_notes").eq("id", str(call_id)))
    if not call:
        raise HTTPException(404, "Call not found")
    if call.get("caller_id") != caller.id and caller.role != "admin":
        raise HTTPException(403, "Forbidden: You are not authorized to close this call")
    if call.get("ended_at") is not None and call.get("outcome") is None:
        raise HTTPException(
            status_code=409,
            detail=f"Inconsistent call state: call {call_id} has ended_at set but outcome is null"
        )
    if call.get("ended_at") is not None or call.get("outcome") is not None:
        if call.get("outcome") == payload.outcome:
            full = fetch_one(d.table("calls").select("*").eq("id", str(call_id)))
            return full or call
        raise HTTPException(
            status_code=409,
            detail=f"Call is already closed with conflicting outcome '{call.get('outcome')}'"
        )

    # Atomic conditional update: only update if ended_at is still null
    response = d.table("calls").update({
        "outcome": payload.outcome,
        "outcome_notes": payload.outcome_notes,
        "ended_at": ended_at_val,
    }).eq("id", str(call_id)).is_("ended_at", "null").execute()

    if not response.data:
        # Concurrent request finalized the call between read and update; re-check outcome
        recheck = fetch_one(d.table("calls").select("*").eq("id", str(call_id)))
        if recheck and recheck.get("outcome") == payload.outcome:
            return recheck
        conflict_outcome = recheck.get("outcome") if recheck else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Call is already closed with conflicting outcome '{conflict_outcome}'"
        )

    return response.data[0]


@app.post("/calls/sync-offline")
def sync_offline_call(
    payload: SyncOfflineCall,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """
    Synchronizes an offline-created call, its stage results, and optional close outcome
    atomically into Supabase under the authenticated caller's identity.
    Validates all inputs BEFORE persistence, supports PostgreSQL RPC transactions,
    and guarantees idempotency via client_call_id.
    """
    d = db()
    stages = list_stages()
    valid_stages = {s["id"] for s in stages}
    first_stage_id = stages[0]["id"] if stages else "opening"

    # 1. Pre-validate current_stage_id before any database write
    current_stage = payload.current_stage_id or first_stage_id
    if current_stage not in valid_stages:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid current_stage_id: '{payload.current_stage_id}'. Must be one of: {sorted(valid_stages)}"
        )

    # 2. Pre-validate all stage results and reject duplicates before any database write
    seen_stages = set()
    for sr in payload.stage_results:
        if sr.stage_id not in valid_stages:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid stage_id in stage_results: '{sr.stage_id}'. Must be one of: {sorted(valid_stages)}"
            )
        if sr.stage_id in seen_stages:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate stage_id '{sr.stage_id}' in stage_results. Each stage may only appear once."
            )
        seen_stages.add(sr.stage_id)

    # 3. Pre-validate outcome: reject blank/whitespace or invalid outcomes
    clean_outcome = payload.outcome.strip() if payload.outcome is not None and payload.outcome.strip() else None
    if payload.outcome is not None and not clean_outcome:
        raise HTTPException(
            status_code=422,
            detail="Outcome cannot be blank or whitespace-only"
        )
    if clean_outcome and clean_outcome not in ALLOWED_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid outcome: '{payload.outcome}'. Must be one of: {sorted(ALLOWED_OUTCOMES)}"
        )

    # 4. Pre-validate timestamps
    if payload.started_at and payload.ended_at and payload.ended_at < payload.started_at:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid timestamps: ended_at ({payload.ended_at.isoformat()}) cannot be before started_at ({payload.started_at.isoformat()})"
        )

    # 4b. Pre-validate finalization state consistency
    if payload.ended_at is not None and not clean_outcome:
        raise HTTPException(
            status_code=422,
            detail="Inconsistent call state: ended_at cannot be set without a valid outcome"
        )

    started_at_str = payload.started_at.isoformat() if payload.started_at else datetime.now(timezone.utc).isoformat()
    ended_at_str = payload.ended_at.isoformat() if payload.ended_at else None

    # 5. Normalize client_call_id: strip whitespace, handle deliberate null ID
    clean_client_id = payload.client_call_id.strip() if payload.client_call_id and payload.client_call_id.strip() else None

    # 6. Execute PostgreSQL Transactional RPC (Sole atomic persistence path)
    # The RPC atomically enforces pg_advisory_xact_lock on (caller_id, client_call_id),
    # detects outcome conflicts on finalized calls, and uses ON CONFLICT DO UPDATE
    # to eliminate concurrent insertion race conditions in PostgreSQL.
    stages_json = [sr.model_dump() for sr in payload.stage_results]
    try:
        rpc_call = d.rpc("sync_offline_call_transaction", {
            "p_caller_id": caller.id,
            "p_client_call_id": clean_client_id,
            "p_prospect_name": payload.prospect_name,
            "p_company_name": payload.company_name,
            "p_current_stage_id": current_stage,
            "p_started_at": started_at_str,
            "p_ended_at": ended_at_str,
            "p_outcome": clean_outcome,
            "p_outcome_notes": payload.outcome_notes,
            "p_stage_results": stages_json,
        }).execute()
        if rpc_call and rpc_call.data:
            return rpc_call.data
        raise HTTPException(500, "Database transaction returned empty payload")
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "DataIntegrityError" in err_msg or "23514" in err_msg:
            raise HTTPException(
                status_code=409,
                detail=f"Inconsistent call state: call has ended_at set but outcome is null ({err_msg})"
            )
        if "already finalized" in err_msg or "23505" in err_msg or "Conflict" in err_msg:
            raise HTTPException(status_code=409, detail=err_msg)
        if "function" in err_msg.lower() and ("does not exist" in err_msg.lower() or "not found" in err_msg.lower()):
            raise HTTPException(
                status_code=503,
                detail="Database migration required: sync_offline_call_transaction RPC function does not exist in Supabase. Run supabase/schema.sql (or supabase/migrations/20261023_secure_sync_offline_rpc.sql) in Supabase SQL Editor to enable atomic offline sync."
            )
        raise HTTPException(status_code=500, detail=f"Database transaction rolled back: {err_msg}")



@app.get("/calls")
def list_calls(
    limit: int = 50,
    offset: int = 0,
    caller_id: str | None = None,
    caller: Caller = Depends(get_current_caller)
) -> list[dict[str, Any]]:
    """Returns past call history. Callers only receive their own records; admins can inspect all or filter by caller_id."""
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(400, "limit must be 1-100 and offset must be non-negative")

    query = db().table("calls").select("*").order("started_at", desc=True)
    if caller.role == "admin":
        if caller_id:
            query = query.eq("caller_id", caller_id)
    else:
        query = query.eq("caller_id", caller.id)

    rows = query.range(offset, offset + limit - 1).execute().data or []
    for row in rows:
        stage_results = db().table("call_stage_results").select("stage_id,result,prospect_words,notes,created_at").eq("call_id", row["id"]).order("created_at").execute().data or []
        row["stage_results"] = stage_results
    return rows


@app.get("/calls/{call_id}")
def get_call(
    call_id: UUID,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """Retrieves full call details. Verifies caller ownership before returning record."""
    d = db()
    row = fetch_one(d.table("calls").select("*").eq("id", str(call_id)))
    if not row:
        raise HTTPException(404, "Call not found")
    if row.get("caller_id") != caller.id and caller.role != "admin":
        raise HTTPException(403, "Forbidden: You are not authorized to view this call")

    row["stage_results"] = d.table("call_stage_results").select("*").eq("call_id", str(call_id)).order("created_at").execute().data or []
    return row


class AISummaryRequest(BaseModel):
    refresh: bool = False

@app.post("/calls/{call_id}/ai-summary")
async def generate_ai_summary(
    call_id: UUID,
    payload: AISummaryRequest,
    caller: Caller = Depends(get_current_caller)
) -> dict[str, Any]:
    """Summarizes only the caller's saved notes; enforces caller ownership and never alters prospect quotations."""
    d = db()
    call = fetch_one(d.table("calls").select("*").eq("id", str(call_id)))
    if not call:
        raise HTTPException(404, "Call not found")
    if call.get("caller_id") != caller.id and caller.role != "admin":
        raise HTTPException(403, "Forbidden: You are not authorized to generate an AI summary for this call")

    if call.get("ai_summary") and not payload.refresh:
        return {"status": "ready", "configured": True, "summary": call["ai_summary"], "cached": True}

    raw_key = os.getenv("LLM_API_KEY")
    api_key = (raw_key or "").strip().strip("\"'").strip()

    if not api_key:
        return {
            "status": "disabled",
            "configured": False,
            "message": "AI debrief is not configured. Configure LLM_API_KEY on the server to enable post-call AI summaries and objection classification.",
            "summary": None,
            "cached": False
        }

    configured_url = os.getenv("LLM_API_URL")
    configured_model = os.getenv("LLM_MODEL")

    if configured_url and configured_url.strip():
        api_url = configured_url.strip()
        model = configured_model.strip() if configured_model and configured_model.strip() else "gpt-4o-mini"
    elif api_key.startswith("AIzaSy"):
        # Auto-route Google Gemini API keys to Gemini's OpenAI-compatible completions endpoint
        api_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        model = configured_model.strip() if configured_model and configured_model.strip() else "gemini-1.5-flash"
    elif api_key.startswith("gsk_"):
        # Auto-route Groq API keys
        api_url = "https://api.groq.com/openai/v1/chat/completions"
        model = configured_model.strip() if configured_model and configured_model.strip() else "llama-3.3-70b-versatile"
    elif api_key.startswith("sk-or-"):
        # Auto-route OpenRouter API keys
        api_url = "https://openrouter.ai/api/v1/chat/completions"
        model = configured_model.strip() if configured_model and configured_model.strip() else "openai/gpt-4o-mini"
    else:
        # Default: OpenAI
        api_url = "https://api.openai.com/v1/chat/completions"
        model = configured_model.strip() if configured_model and configured_model.strip() else "gpt-4o-mini"

    stage_rows = d.table("call_stage_results").select("stage_id,result,prospect_words,notes,created_at").eq("call_id", str(call_id)).order("created_at").execute().data or []
    safe_input = {
        "prospect_name": call.get("prospect_name"),
        "company_name": call.get("company_name"),
        "outcome": call.get("outcome"),
        "outcome_notes": call.get("outcome_notes"),
        "stages": stage_rows,
    }
    system_prompt = (
        "You are a careful sales-call review assistant. Use ONLY the supplied saved call fields. "
        "Never invent facts, infer prospect intent beyond the notes, or rewrite/complete direct quotations. "
        "Summarize the call for the caller, not the prospect. Return valid JSON with keys: "
        "summary (string), objection_classification (string or null, e.g., 'Vendor Lock-in (Global Contract)', 'Internal Process', 'Timing/Budget', 'Not Relevant', or null), "
        "signals (array of up to 3 short strings), follow_up (string), and data_gaps (array of short strings). "
        "If notes are sparse, explicitly state that in the summary."
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(safe_input, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            summary = json.loads(content)
    except httpx.HTTPStatusError as exc:
        err_detail = ""
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                err_detail = body.get("error", {}).get("message") or body.get("message") or ""
        except Exception:
            err_detail = exc.response.text[:120].strip()
        detail_msg = f"LLM provider returned HTTP {exc.response.status_code}"
        if err_detail:
            detail_msg += f": {err_detail}"
        raise HTTPException(502, detail_msg) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(502, "Could not generate a valid AI debrief") from exc

    summary["model"] = model
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    update = d.table("calls").update({"ai_summary": summary}).eq("id", str(call_id)).execute()
    if not update.data:
        raise HTTPException(500, "Generated summary but could not save it")
    return {"status": "ready", "configured": True, "summary": summary, "cached": False}


# -----------------------------------------------------------------------------
# Contact Submission & Support Dispatch (Server-Side Secrets & Rate Limiting)
# -----------------------------------------------------------------------------
class ContactPayload(BaseModel):
    name: str | None = None
    email: str
    message: str
    honeypot: str | None = None

    @model_validator(mode="after")
    def validate_contact(self) -> Self:
        clean_email = self.email.strip()
        if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
            raise ValueError("A valid email address is required.")
        if len(clean_email) > 254:
            raise ValueError("Email exceeds maximum allowable length.")
        self.email = clean_email

        clean_msg = self.message.strip()
        if not clean_msg or len(clean_msg) < 5:
            raise ValueError("Message must be at least 5 characters long.")
        if len(clean_msg) > 5000:
            raise ValueError("Message exceeds 5,000 character limit.")
        self.message = clean_msg

        if self.name:
            self.name = self.name.strip()[:100]
        return self


# -----------------------------------------------------------------------------
# Proxy-Aware Client IP Extraction & Sliding Window Rate Limiter
# -----------------------------------------------------------------------------
def is_trusted_proxy(host: str) -> bool:
    """
    Determines whether a connecting socket client is an explicitly trusted proxy.
    Only trusted proxies are permitted to supply client IP forwarding headers
    (CF-Connecting-IP, X-Forwarded-For, X-Real-IP).
    """
    if not host or host == "unknown":
        return False
    if host in ("testclient", "localhost"):
        return True

    trusted_env = os.getenv("TRUSTED_PROXY_IPS", "").strip()
    configured = [p.strip() for p in trusted_env.split(",") if p.strip()]
    if host in configured:
        return True

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return True
        for entry in configured:
            try:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                pass
        if os.getenv("TRUST_PRIVATE_PROXIES", "false").lower() in ("1", "true", "yes") and ip.is_private:
            return True
    except ValueError:
        pass
    return False


def validate_ip_candidate(candidate: str | None) -> str | None:
    """
    Validates and canonicalizes an IP candidate string (IPv4 or IPv6),
    stripping optional client port if supplied in IPv4 (e.g. 1.2.3.4:5678).
    Returns string IP if valid, None if invalid.
    """
    if not candidate:
        return None
    clean = candidate.strip()
    # Strip optional IPv4 port (e.g. 1.2.3.4:8080)
    if ":" in clean and not clean.startswith("[") and clean.count(":") == 1:
        clean = clean.split(":")[0].strip()
    # Strip bracketed IPv6 with port (e.g. [2001:db8::1]:8080)
    elif clean.startswith("[") and "]" in clean:
        clean = clean[1:clean.index("]")].strip()

    try:
        ipaddress.ip_address(clean)
        return clean
    except ValueError:
        return None


def extract_client_ip(req: Request) -> str:
    """
    Safely resolves client IP for rate limiting.
    Security Guard: If the immediate connecting host is NOT an explicitly trusted proxy,
    forwarding headers (CF-Connecting-IP, X-Forwarded-For, X-Real-IP) are strictly ignored
    to prevent client IP spoofing attacks.
    Additionally, forwarded IP candidates are validated using ipaddress to prevent injection
    or malformed values.
    """
    socket_host = req.client.host if req.client else "unknown"
    if not is_trusted_proxy(socket_host):
        return socket_host

    cf_connecting_ip = req.headers.get("cf-connecting-ip")
    if cf_connecting_ip:
        valid_cf = validate_ip_candidate(cf_connecting_ip)
        if valid_cf:
            return valid_cf

    x_forwarded_for = req.headers.get("x-forwarded-for")
    if x_forwarded_for and x_forwarded_for.strip():
        # In standard reverse proxy chaining (client, proxy1, proxy2), leftmost is the client
        client_candidate = x_forwarded_for.split(",")[0].strip()
        valid_xff = validate_ip_candidate(client_candidate)
        if valid_xff:
            return valid_xff

    x_real_ip = req.headers.get("x-real-ip")
    if x_real_ip:
        valid_x_real = validate_ip_candidate(x_real_ip)
        if valid_x_real:
            return valid_x_real

    return socket_host

# In-memory sliding window rate limiter: max 5 requests per 10 minutes per IP
# Architectural Note: This limiter operates in-memory per worker process.
# For distributed multi-instance production scale, configure an external Redis or Upstash key-value store.
_contact_rate_limit: dict[str, list[float]] = {}

@app.post("/contact")
async def handle_contact_submission(payload: ContactPayload, req: Request) -> dict[str, Any]:
    """
    Receives contact/support messages, validates payload, checks honeypot spam protection,
    enforces client rate limiting behind deployment proxies, and dispatches via server-side webhook secrets.
    Formats the payload to be natively compatible with Slack incoming webhooks, Discord webhooks,
    and generic JSON receivers (Zapier, Make, CRM webhooks).
    """
    # 1. Anti-spam honeypot: silently acknowledge if bot populated hidden field
    if payload.honeypot and payload.honeypot.strip():
        return {"status": "received", "message": "Feedback received."}

    # 2. Proxy-aware rate limiting by client IP
    client_ip = extract_client_ip(req)
    now_ts = datetime.now(timezone.utc).timestamp()
    history = [ts for ts in _contact_rate_limit.get(client_ip, []) if now_ts - ts < 600]
    if len(history) >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many contact submissions. Please wait several minutes before trying again."
        )
    history.append(now_ts)
    _contact_rate_limit[client_ip] = history

    # 3. Check for server-side secret destination
    webhook_url = os.getenv("CONTACT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="Contact support destination is not configured on the server. Please contact the administrator directly."
        )

    # 4. Construct provider-compatible webhook payload
    submitted_at = datetime.now(timezone.utc).isoformat()
    sender_name = payload.name or "Anonymous Caller"
    # Format message quote with markdown block quote
    quoted_message = payload.message.replace("\n", "\n> ")
    formatted_summary = (
        f"*New Sidecall Support Inquiry*\n"
        f"• *From:* {sender_name} <{payload.email}>\n"
        f"• *Submitted:* {submitted_at}\n"
        f"• *Message:*\n> {quoted_message}"
    )

    webhook_payload = {
        # Slack incoming webhook compatibility (Slack strictly requires 'text' or 'blocks'):
        "text": formatted_summary,
        # Discord webhook compatibility:
        "content": formatted_summary,
        # Generic structured JSON receivers (Zapier, Make, custom CRM/DB webhooks):
        "name": sender_name,
        "email": payload.email,
        "message": payload.message,
        "submitted_at": submitted_at,
        "source": "Sidecall Web Companion",
    }

    # 5. Dispatch to verified server-side webhook
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook_url,
                json=webhook_payload,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook provider rejected submission with HTTP {exc.response.status_code}."
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to deliver contact message to configured destination."
        ) from exc

    return {"status": "received", "message": "Thank you! Your message has been forwarded to support."}
