from datetime import datetime, timezone
import json
import os
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
import httpx
from app import app, STARTER_STAGES
import app as app_module

# Explicit, high-entropy test tokens (never hardcoded in application runtime)
VALID_CALLER_A_TOKEN = "alpha-secret-token-v884"
VALID_CALLER_B_TOKEN = "beta-secret-token-x912"
VALID_ADMIN_TOKEN = "admin-secret-token-z331"

os.environ["CALLER_AUTH_TOKENS"] = (
    f"rep-alpha:{VALID_CALLER_A_TOKEN},"
    f"rep-beta:{VALID_CALLER_B_TOKEN},"
    f"admin-lead:{VALID_ADMIN_TOKEN}:admin"
)

client = TestClient(app)
client.headers.update({"Authorization": f"Bearer {VALID_CALLER_A_TOKEN}"})


# -----------------------------------------------------------------------------
# In-Memory Supabase Client Mock for Deterministic Persistence Testing
# -----------------------------------------------------------------------------
class MockTableQuery:
    def __init__(self, table_name: str, db_state: dict):
        self.table_name = table_name
        self.db = db_state
        self.filters = []
        self._order_by = None
        self._desc = False
        self._range = None
        self._is_single = False
        self._action = "select"
        self._insert_data = None
        self._update_data = None
        self._upsert_conflict = None

    def select(self, fields="*", count=None):
        self._action = "select"
        self._count = count
        return self

    def insert(self, row):
        self._action = "insert"
        self._insert_data = row
        return self

    def upsert(self, row, on_conflict=None):
        self._action = "upsert"
        self._insert_data = row
        self._upsert_conflict = on_conflict
        return self

    def update(self, data):
        self._action = "update"
        self._update_data = data
        return self

    def eq(self, column, value):
        self.filters.append((column, "eq", value))
        return self

    def is_(self, column, value):
        self.filters.append((column, "is", value))
        return self

    def order(self, column, desc=False):
        self._order_by = column
        self._desc = desc
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def maybe_single(self):
        self._is_single = True
        return self

    def execute(self):
        class Result:
            def __init__(self, data, count=None):
                self.data = data
                self.count = count

        table = self.db.setdefault(self.table_name, [])

        if self._action == "insert":
            row = dict(self._insert_data)
            if "id" not in row:
                row["id"] = str(uuid4())
            if "created_at" not in row:
                row["created_at"] = datetime.now(timezone.utc).isoformat()
            if "started_at" not in row:
                row["started_at"] = datetime.now(timezone.utc).isoformat()
            if "ended_at" not in row:
                row["ended_at"] = None
            if "outcome" not in row:
                row["outcome"] = None
            if "outcome_notes" not in row:
                row["outcome_notes"] = None
            if "ai_summary" not in row:
                row["ai_summary"] = None
            table.append(row)
            return Result([dict(row)])

        if self._action == "upsert":
            row = dict(self._insert_data)
            if "id" not in row:
                row["id"] = str(uuid4())
            if "created_at" not in row:
                row["created_at"] = datetime.now(timezone.utc).isoformat()
            found_idx = None
            if self._upsert_conflict == "call_id,stage_id":
                for idx, existing in enumerate(table):
                    if (
                        str(existing.get("call_id")) == str(row.get("call_id"))
                        and str(existing.get("stage_id")) == str(row.get("stage_id"))
                    ):
                        found_idx = idx
                        break
            if found_idx is not None:
                table[found_idx].update(row)
                return Result([dict(table[found_idx])])
            else:
                table.append(row)
                return Result([dict(row)])

        # Apply filters
        filtered = []
        for item in table:
            matches = True
            for col, op, val in self.filters:
                item_val = item.get(col)
                if op == "eq":
                    if str(item_val) != str(val):
                        matches = False
                        break
                elif op == "is":
                    if val == "null":
                        if item_val is not None:
                            matches = False
                            break
                    elif item_val != val:
                        matches = False
                        break
            if matches:
                filtered.append(item)

        if self._action == "update":
            updated = []
            for item in filtered:
                item.update(self._update_data)
                updated.append(dict(item))
            return Result(updated)

        # Select action
        if self._order_by:
            filtered.sort(key=lambda x: str(x.get(self._order_by, "")), reverse=self._desc)

        if self._range:
            start, end = self._range
            filtered = filtered[start : end + 1]

        if self._is_single:
            return Result(dict(filtered[0]) if filtered else None)

        return Result([dict(x) for x in filtered], count=len(filtered))


class MockSupabaseClient:
    def __init__(self):
        self.db_state = {
            "call_stages": [dict(s) for s in STARTER_STAGES],
            "calls": [],
            "call_stage_results": [],
        }

    def table(self, name: str):
        return MockTableQuery(name, self.db_state)


@pytest.fixture
def mock_db(monkeypatch):
    fake_client = MockSupabaseClient()
    monkeypatch.setattr(app_module, "supabase", fake_client)
    monkeypatch.setattr(app_module, "db", lambda: fake_client)
    return fake_client


# -----------------------------------------------------------------------------
# Base Stage & Validation Tests
# -----------------------------------------------------------------------------
def test_health_available():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "database" in data
    assert "llm" in data
    assert data["service"] == "coldcall-companion-api"


def test_eight_stages_are_present_in_exact_order():
    response = client.get("/stages")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    expected_order = [
        "opening",
        "purpose",
        "permission",
        "their_business",
        "their_need",
        "objection",
        "next_step",
        "close",
    ]
    actual_ids = [x["id"] for x in data]
    assert actual_ids == expected_order
    assert [x["position"] for x in data] == list(range(1, 9))
    for stage in data:
        assert stage["title"]
        assert stage["purpose"]
        assert stage["guidance"]
        assert isinstance(stage.get("prospect_patterns"), list)
        assert len(stage["prospect_patterns"]) >= 2
        assert isinstance(stage.get("stage_taps"), list)
        assert len(stage["stage_taps"]) >= 3


def test_calls_input_validation():
    res = client.get("/calls?limit=-1")
    assert res.status_code == 400

    res = client.get("/calls?limit=500")
    assert res.status_code == 400

    res = client.get("/calls?offset=-5")
    assert res.status_code == 400


def test_stage_results_input_validation():
    res = client.post(
        "/calls/invalid-uuid/stage-results",
        json={"stage_id": "opening", "result": "completed"},
    )
    assert res.status_code == 422

    res = client.post("/calls", json={"prospect_name": "x" * 200})
    assert res.status_code == 422


def test_unconfigured_database_returns_503(monkeypatch):
    monkeypatch.setattr(app_module, "supabase", None)
    call_id = str(uuid4())
    res = client.post("/calls", json={"prospect_name": "Test"})
    assert res.status_code == 503
    assert "Database is not configured" in res.json()["detail"]

    res = client.get(f"/calls/{call_id}")
    assert res.status_code == 503

    res = client.post(
        f"/calls/{call_id}/stage-results",
        json={"stage_id": "opening", "result": "completed"},
    )
    assert res.status_code == 503

    res = client.patch(f"/calls/{call_id}/stage", json={"stage_id": "purpose"})
    assert res.status_code == 503

    res = client.post(f"/calls/{call_id}/close", json={"outcome": "meeting_booked"})
    assert res.status_code == 503


# -----------------------------------------------------------------------------
# Database Persistence Tests (Using Mock Supabase)
# -----------------------------------------------------------------------------
def test_create_call_persistence_flow(mock_db):
    res = client.post(
        "/calls",
        json={"prospect_name": "Rohan Mehta", "company_name": "Aether Dynamics"},
    )
    assert res.status_code == 200
    call = res.json()
    assert call["id"]
    assert call["prospect_name"] == "Rohan Mehta"
    assert call["company_name"] == "Aether Dynamics"
    assert call["current_stage_id"] == "opening"
    assert call["ended_at"] is None


def test_save_stage_results_verbatim_preservation_stage_5(mock_db):
    # 1. Create call
    call_res = client.post(
        "/calls",
        json={"prospect_name": "Pooja Varma", "company_name": "Kalyan Textiles"},
    )
    assert call_res.status_code == 200
    call_id = call_res.json()["id"]

    # 2. Save Stage 1 (Opening) quick tap
    s1_res = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "opening",
            "result": "Reached right person",
            "notes": "Spoke directly with VP Operations",
        },
    )
    assert s1_res.status_code == 200

    # 3. Save Stage 5 (Their need, in their words) with exact verbatim quote
    exact_verbatim_quote = (
        "“We have three fabrication plants in Pune running at 65% capacity. "
        "Our main bottleneck is supply variance in high-tensile steel, which dropped Q2 margins by 3.8%.”"
    )
    s5_res = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "their_need",
            "result": "Stated specific priority/bottleneck",
            "prospect_words": exact_verbatim_quote,
            "notes": "Prospect was very open regarding supply chain issues.",
        },
    )
    assert s5_res.status_code == 200
    assert s5_res.json()["prospect_words"] == exact_verbatim_quote

    # 4. Fetch full call and verify exact verbatim wording is preserved
    detail_res = client.get(f"/calls/{call_id}")
    assert detail_res.status_code == 200
    call_detail = detail_res.json()
    assert call_detail["current_stage_id"] == "their_need"

    stage_results = {s["stage_id"]: s for s in call_detail["stage_results"]}
    assert "their_need" in stage_results
    assert stage_results["their_need"]["prospect_words"] == exact_verbatim_quote
    assert stage_results["their_need"]["result"] == "Stated specific priority/bottleneck"


def test_ending_call_from_any_stage(mock_db):
    # Case A: Ending early from Stage 2 (Purpose) - wrong person or brush-off
    c1 = client.post("/calls", json={"prospect_name": "Person 1"}).json()
    close1 = client.post(
        f"/calls/{c1['id']}/close",
        json={"outcome": "wrong_person", "outcome_notes": "Directed to Bangalore office"},
    )
    assert close1.status_code == 200
    assert close1.json()["outcome"] == "wrong_person"
    assert close1.json()["ended_at"] is not None

    # Verify closed call cannot accept further stage updates (409 Conflict)
    save_after_close = client.post(
        f"/calls/{c1['id']}/stage-results",
        json={"stage_id": "permission", "result": "Agreed to talk now"},
    )
    assert save_after_close.status_code == 409

    # Case B: Ending from Stage 4 (Their Business) - objection / firm no
    c2 = client.post("/calls", json={"prospect_name": "Person 2"}).json()
    client.patch(f"/calls/{c2['id']}/stage", json={"stage_id": "their_business"})
    close2 = client.post(
        f"/calls/{c2['id']}/close",
        json={"outcome": "not_interested", "outcome_notes": "Satisfied with internal vendor"},
    )
    assert close2.status_code == 200
    assert close2.json()["outcome"] == "not_interested"
    assert close2.json()["ended_at"] is not None

    # Case C: Ending from Stage 8 (Close) - next step agreed
    c3 = client.post("/calls", json={"prospect_name": "Person 3"}).json()
    client.patch(f"/calls/{c3['id']}/stage", json={"stage_id": "close"})
    close3 = client.post(
        f"/calls/{c3['id']}/close",
        json={
            "outcome": "next_step_agreed",
            "outcome_notes": "WhatsApp brief sent; follow-up scheduled Tuesday 11:30 AM",
        },
    )
    assert close3.status_code == 200
    assert close3.json()["outcome"] == "next_step_agreed"
    assert close3.json()["ended_at"] is not None


def test_duplicate_stage_write_idempotency_upsert(mock_db):
    call = client.post("/calls", json={"prospect_name": "Arjun Rao"}).json()
    call_id = call["id"]

    # First write to Stage 3
    res1 = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "permission",
            "result": "Agreed to talk now",
            "notes": "Prospect has 2 minutes",
        },
    )
    assert res1.status_code == 200

    # Second write to Stage 3 (caller modifies quick tap / note)
    res2 = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "permission",
            "result": "Callback requested (named time)",
            "notes": "Prospect asked to call back after 3 PM",
        },
    )
    assert res2.status_code == 200

    # Ensure only 1 record exists for Stage 3 in call history
    detail = client.get(f"/calls/{call_id}").json()
    stage3_records = [s for s in detail["stage_results"] if s["stage_id"] == "permission"]
    assert len(stage3_records) == 1
    assert stage3_records[0]["result"] == "Callback requested (named time)"
    assert stage3_records[0]["notes"] == "Prospect asked to call back after 3 PM"


def test_call_history_retrieval_and_detail(mock_db):
    # Create 3 calls
    c1 = client.post("/calls", json={"prospect_name": "A", "company_name": "Corp A"}).json()
    c2 = client.post("/calls", json={"prospect_name": "B", "company_name": "Corp B"}).json()
    c3 = client.post("/calls", json={"prospect_name": "C", "company_name": "Corp C"}).json()

    # List calls
    list_res = client.get("/calls?limit=10&offset=0")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 3
    retrieved_ids = {item["id"] for item in items}
    assert c1["id"] in retrieved_ids
    assert c2["id"] in retrieved_ids
    assert c3["id"] in retrieved_ids

    # Detail call
    detail_res = client.get(f"/calls/{c1['id']}")
    assert detail_res.status_code == 200
    assert detail_res.json()["prospect_name"] == "A"
    assert "stage_results" in detail_res.json()

    # Non-existent call returns 404
    missing_res = client.get(f"/calls/{uuid4()}")
    assert missing_res.status_code == 404


# -----------------------------------------------------------------------------
# LLM Provider, Debrief, Caching & Failure Isolation Tests
# -----------------------------------------------------------------------------
def test_llm_disabled_when_api_key_unconfigured(mock_db, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    call = client.post("/calls", json={"prospect_name": "Suresh Nair"}).json()

    res = client.post(f"/calls/{call['id']}/ai-summary", json={"refresh": False})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "disabled"
    assert data["configured"] is False
    assert "LLM_API_KEY" in data["message"]
    assert data["summary"] is None


def test_llm_debrief_success_mock(mock_db, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "mock-sk-valid-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

    call = client.post(
        "/calls",
        json={"prospect_name": "Vikram Patel", "company_name": "Apex Engineering"},
    ).json()
    call_id = call["id"]

    # Add Stage 5 verbatim note and Stage 6 objection
    client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "their_need",
            "result": "Stated specific priority/bottleneck",
            "prospect_words": "Need to cut tool re-calibration downtime by 15%.",
        },
    )
    client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "objection",
            "result": "Global contract / locked vendor",
            "notes": "Parent MNC has strict enterprise vendor roster.",
        },
    )
    client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "follow_up", "outcome_notes": "Send whitepaper first"},
    )

    mock_llm_response = {
        "summary": "Call qualified technical interest in tooling efficiency, but encountered multi-year enterprise lock-in.",
        "objection_classification": "Vendor Lock-in (Global Contract)",
        "signals": [
            "Clear technical pain regarding machine recalibration",
            "Open to receiving educational whitepaper",
        ],
        "follow_up": "Send tooling case study with ROI benchmarks on Thursday.",
        "data_gaps": ["Budget authority unknown"],
    }

    class MockAsyncResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": json.dumps(self._data)}}
                ]
            }

    async def fake_post(self, *args, **kwargs):
        return MockAsyncResponse(mock_llm_response)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # Call AI debrief endpoint
    res = client.post(f"/calls/{call_id}/ai-summary", json={"refresh": False})
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "ready"
    assert res_data["configured"] is True
    assert res_data["cached"] is False
    assert (
        res_data["summary"]["objection_classification"]
        == "Vendor Lock-in (Global Contract)"
    )
    assert res_data["summary"]["model"] == "gpt-4o-mini"
    assert "generated_at" in res_data["summary"]

    # Verify persistence: call record now holds ai_summary
    detail = client.get(f"/calls/{call_id}").json()
    assert detail["ai_summary"] is not None
    assert detail["ai_summary"]["objection_classification"] == "Vendor Lock-in (Global Contract)"

    # Second call without refresh should return cached response
    res_cached = client.post(f"/calls/{call_id}/ai-summary", json={"refresh": False})
    assert res_cached.status_code == 200
    assert res_cached.json()["cached"] is True


def test_llm_failure_does_not_corrupt_call_data(mock_db, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "mock-sk-valid-key")

    call = client.post(
        "/calls",
        json={"prospect_name": "Meera Iyer", "company_name": "Indus Logistics"},
    ).json()
    call_id = call["id"]

    exact_quote = "“We are moving all freight booking to our internal portal.”"
    client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "their_need",
            "result": "Stated specific priority/bottleneck",
            "prospect_words": exact_quote,
            "notes": "Very firm on in-house portal.",
        },
    )
    client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "not_interested", "outcome_notes": "Closed due to in-house solution"},
    )

    # Simulate upstream LLM gateway error (502 / timeout)
    async def fake_failing_post(self, *args, **kwargs):
        req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        resp = httpx.Response(502, request=req)
        raise httpx.HTTPStatusError("Bad Gateway", request=req, response=resp)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_failing_post)

    # Trigger debrief - should fail safely with 502
    res = client.post(f"/calls/{call_id}/ai-summary", json={"refresh": False})
    assert res.status_code == 502
    assert "LLM provider returned HTTP 502" in res.json()["detail"]

    # CRITICAL: Verify saved call data is completely intact and UNCORRUPTED
    detail = client.get(f"/calls/{call_id}").json()
    assert detail["prospect_name"] == "Meera Iyer"
    assert detail["company_name"] == "Indus Logistics"
    assert detail["outcome"] == "not_interested"
    assert detail["outcome_notes"] == "Closed due to in-house solution"
    assert detail["ended_at"] is not None
    assert detail["ai_summary"] is None  # Remains uncorrupted

    stage_map = {s["stage_id"]: s for s in detail["stage_results"]}
    assert stage_map["their_need"]["prospect_words"] == exact_quote
    assert stage_map["their_need"]["notes"] == "Very firm on in-house portal."


# -----------------------------------------------------------------------------# Security & Authorization Tests (Authentication, Isolation, Validation)
# -----------------------------------------------------------------------------

def test_prefix_tokens_are_strictly_rejected(mock_db):
    test_client = TestClient(app)
    """
    REGRESSION TEST: Verify that prefix-based token bypasses are COMPLETELY eliminated.
    Tokens starting with 'fde-', 'caller-', or 'admin-' MUST be rejected with 401.
    """
    prefix_bypass_attempts = [
        "fde-rep-101",          # Previously hardcoded default
        "fde-rep-102",
        "fde-attacker",
        "fde-anything",
        "caller-rep",
        "caller-attacker",
        "caller-admin",
        "admin-anything",        # Prefix escalation attempt
        "admin-token-secret",    # Previously hardcoded default
        "admin-root",
        "admin-super",
        "arbitrary-token-12345",
        "Bearer",
        "",
    ]
    for bad_token in prefix_bypass_attempts:
        headers = {"Authorization": f"Bearer {bad_token}"} if bad_token else {}
        res = test_client.get("/calls", headers=headers)
        assert res.status_code == 401, f"Expected 401 for token '{bad_token}', got {res.status_code}"
        assert "Authentication required" in res.json()["detail"] or "Invalid authentication token" in res.json()["detail"]


def test_unconfigured_auth_fails_closed(mock_db, monkeypatch):
    """
    REGRESSION TEST: If CALLER_AUTH_TOKENS is empty or unset, server MUST fail closed (401),
    never permitting fallback to unauthenticated access or hardcoded defaults.
    """
    monkeypatch.setenv("CALLER_AUTH_TOKENS", "")
    res = client.get("/calls", headers={"Authorization": f"Bearer {VALID_CALLER_A_TOKEN}"})
    assert res.status_code == 401
    assert "Invalid authentication token" in res.json()["detail"]


def test_admin_privilege_cannot_be_inferred_from_prefix(mock_db, monkeypatch):
    """
    REGRESSION TEST: Administrator privileges CANNOT be attained via 'admin-*' prefix.
    Admin rights require an explicit ':admin' role configuration in CALLER_AUTH_TOKENS.
    """
    # 1. 'admin-impersonator' token is not in CALLER_AUTH_TOKENS -> 401
    res_fake = client.get("/calls", headers={"Authorization": "Bearer admin-impersonator"})
    assert res_fake.status_code == 401

    # 2. Add a token with 'admin-' in the token string, but configured with default 'caller' role
    monkeypatch.setenv(
        "CALLER_AUTH_TOKENS",
        f"caller-plain:admin-named-token,{os.environ['CALLER_AUTH_TOKENS']}"
    )
    # Caller A creates Call A
    call_a = client.post("/calls", json={"prospect_name": "Target Co"}).json()

    # The caller-plain user tries to access Call A -> 403 Forbidden (not an admin!)
    res_forbidden = client.get(
        f"/calls/{call_a['id']}",
        headers={"Authorization": "Bearer admin-named-token"}
    )
    assert res_forbidden.status_code == 403
    assert "Forbidden" in res_forbidden.json()["detail"]

    # 3. Explicitly configured admin user CAN view Call A
    res_admin = client.get(
        f"/calls/{call_a['id']}",
        headers={"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"}
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["id"] == call_a["id"]


def test_unauthenticated_requests_return_401(mock_db):
    unauthed_client = TestClient(app)  # No Authorization header
    call_id = str(uuid4())

    # 1. Starting a call without auth
    res = unauthed_client.post("/calls", json={"prospect_name": "Ghost"})
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]

    # 2. Reading history without auth
    res = unauthed_client.get("/calls")
    assert res.status_code == 401

    # 3. Reading call detail without auth
    res = unauthed_client.get(f"/calls/{call_id}")
    assert res.status_code == 401

    # 4. Saving stage without auth
    res = unauthed_client.post(
        f"/calls/{call_id}/stage-results",
        json={"stage_id": "opening", "result": "Reached right person"},
    )
    assert res.status_code == 401

    # 5. Closing call without auth
    res = unauthed_client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "meeting_booked"},
    )
    assert res.status_code == 401


def test_unauthorized_cross_caller_access_returns_403(mock_db):
    caller_a_client = TestClient(app)
    caller_a_client.headers.update({"Authorization": f"Bearer {VALID_CALLER_A_TOKEN}"})

    caller_b_client = TestClient(app)
    caller_b_client.headers.update({"Authorization": f"Bearer {VALID_CALLER_B_TOKEN}"})

    # Caller A creates a call
    create_res = caller_a_client.post(
        "/calls",
        json={"prospect_name": "Aman Gupta", "company_name": "BoAt Lifestyle"},
    )
    assert create_res.status_code == 200
    call_id = create_res.json()["id"]

    # Caller B attempts to view Caller A's call details -> 403 Forbidden
    view_res = caller_b_client.get(f"/calls/{call_id}")
    assert view_res.status_code == 403
    assert "Forbidden" in view_res.json()["detail"]

    # Caller B attempts to save stage results on Caller A's call -> 403 Forbidden
    save_res = caller_b_client.post(
        f"/calls/{call_id}/stage-results",
        json={"stage_id": "opening", "result": "Reached right person"},
    )
    assert save_res.status_code == 403
    assert "Forbidden" in save_res.json()["detail"]

    # Caller B attempts to update stage navigation on Caller A's call -> 403 Forbidden
    stage_res = caller_b_client.patch(
        f"/calls/{call_id}/stage",
        json={"stage_id": "purpose"},
    )
    assert stage_res.status_code == 403
    assert "Forbidden" in stage_res.json()["detail"]

    # Caller B attempts to close Caller A's call -> 403 Forbidden
    close_res = caller_b_client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "not_interested"},
    )
    assert close_res.status_code == 403
    assert "Forbidden" in close_res.json()["detail"]

    # Caller B attempts to generate AI summary on Caller A's call -> 403 Forbidden
    ai_res = caller_b_client.post(
        f"/calls/{call_id}/ai-summary",
        json={"refresh": False},
    )
    assert ai_res.status_code == 403
    assert "Forbidden" in ai_res.json()["detail"]


def test_caller_history_isolation(mock_db):
    caller_a = TestClient(app)
    caller_a.headers.update({"Authorization": f"Bearer {VALID_CALLER_A_TOKEN}"})

    caller_b = TestClient(app)
    caller_b.headers.update({"Authorization": f"Bearer {VALID_CALLER_B_TOKEN}"})

    admin = TestClient(app)
    admin.headers.update({"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"})

    # Caller A logs Call A
    caller_a.post("/calls", json={"prospect_name": "Alpha Corp Lead"})
    # Caller B logs Call B
    caller_b.post("/calls", json={"prospect_name": "Beta Industries Lead"})

    # Caller A history only shows Alpha Corp Lead
    history_a = caller_a.get("/calls").json()
    assert len(history_a) == 1
    assert history_a[0]["prospect_name"] == "Alpha Corp Lead"

    # Caller B history only shows Beta Industries Lead
    history_b = caller_b.get("/calls").json()
    assert len(history_b) == 1
    assert history_b[0]["prospect_name"] == "Beta Industries Lead"

    # Admin history sees both calls
    admin_history = admin.get("/calls").json()
    assert len(admin_history) >= 2


def test_invalid_outcome_validation_returns_422(mock_db):
    call = client.post("/calls", json={"prospect_name": "Test Outcome Prospect"}).json()
    call_id = call["id"]

    # Invalid outcome value
    res = client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "fake_outcome_value", "outcome_notes": "Attempting invalid outcome"},
    )
    assert res.status_code == 422
    assert "Invalid outcome" in res.json()["detail"]

    # Valid outcome value succeeds
    res_valid = client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "next_step_agreed", "outcome_notes": "Valid outcome notes"},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["outcome"] == "next_step_agreed"


def test_cannot_close_already_closed_call_returns_409(mock_db):
    call = client.post("/calls", json={"prospect_name": "Double Close Lead"}).json()
    call_id = call["id"]

    # First close succeeds
    res1 = client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "not_interested", "outcome_notes": "First close"},
    )
    assert res1.status_code == 200

    # Second close attempt returns 409 Conflict
    res2 = client.post(
        f"/calls/{call_id}/close",
        json={"outcome": "meeting_booked", "outcome_notes": "Attempt to change outcome"},
    )
    assert res2.status_code == 409
    assert "already closed" in res2.json()["detail"]


def test_real_supabase_live_connectivity_check():
    """
    Explicit check for live Supabase environment.
    Runs against real database if credentials exist; skips honestly when unset.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        pytest.skip(
            "Live Supabase credentials (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) not configured in local environment; "
            "skipping live cloud connection test in favor of in-memory client test."
        )

    from supabase import create_client
    live_client = create_client(url, key)
    stages = live_client.table("call_stages").select("id,position,title").order("position").execute()
    assert len(stages.data) == 8, f"Expected 8 stages in live Supabase, got {len(stages.data)}"


def test_sample_patterns_are_strictly_isolated_from_prospect_words(mock_db):
    """
    REGRESSION TEST: Verify that behavioral sample patterns (prospect_patterns)
    are strictly read-only cues and are NEVER injected or saved into prospect_words
    without explicit caller entry.
    """
    # 1. Verify stages return prospect_patterns as guidance
    stages = client.get("/stages").json()
    stage_5 = next(s for s in stages if s["id"] == "their_need")
    assert len(stage_5["prospect_patterns"]) >= 3
    sample_pattern = stage_5["prospect_patterns"][0]

    # 2. Start a call
    call = client.post("/calls", json={"prospect_name": "Quotation Integrity Test"}).json()
    call_id = call["id"]

    # 3. Caller saves stage 5 with explicit caller quote
    explicit_caller_quote = "Prospect said: 'We are expanding to Gujarat next quarter.'"
    client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "their_need",
            "result": "Stated specific priority/bottleneck",
            "prospect_words": explicit_caller_quote,
            "notes": "Verified caller input.",
        },
    )

    # 4. Verify that prospect_words ONLY contains explicit caller input, never sample pattern
    detail = client.get(f"/calls/{call_id}").json()
    s5_record = next(r for r in detail["stage_results"] if r["stage_id"] == "their_need")
    assert s5_record["prospect_words"] == explicit_caller_quote
    assert sample_pattern not in s5_record["prospect_words"]


def test_stage_save_retry_and_reconciliation(mock_db):
    """
    REGRESSION TEST: Verify that repeated saves / retries for the same (call_id, stage_id)
    perform an idempotent upsert, reconciling newer notes without creating duplicate records.
    """
    call = client.post("/calls", json={"prospect_name": "Reconciliation Prospect"}).json()
    call_id = call["id"]

    # First attempt: Draft notes saved
    res1 = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "opening",
            "result": "Reached right person",
            "prospect_words": "",
            "notes": "Initial draft note taken during first 10 seconds",
        },
    )
    assert res1.status_code == 200

    # Second attempt: Caller edits/updates notes during same stage
    res2 = client.post(
        f"/calls/{call_id}/stage-results",
        json={
            "stage_id": "opening",
            "result": "Reached right person",
            "prospect_words": "",
            "notes": "Reconciled note: confirmed VP Operations direct line",
        },
    )
    assert res2.status_code == 200

    # Verify that call_detail only has ONE stage result for 'opening' with latest reconciled notes
    detail = client.get(f"/calls/{call_id}").json()
    opening_records = [r for r in detail["stage_results"] if r["stage_id"] == "opening"]
    assert len(opening_records) == 1
    assert opening_records[0]["notes"] == "Reconciled note: confirmed VP Operations direct line"


def test_admin_can_filter_calls_by_caller_id(mock_db):
    """
    REGRESSION TEST: Verify that an administrator can query /calls with a specific
    caller_id parameter, enabling audit of specific sales reps or legacy records.
    """
    admin = TestClient(app)
    admin.headers.update({"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"})

    rep_a = TestClient(app)
    rep_a.headers.update({"Authorization": f"Bearer {VALID_CALLER_A_TOKEN}"})

    rep_b = TestClient(app)
    rep_b.headers.update({"Authorization": f"Bearer {VALID_CALLER_B_TOKEN}"})

    # Log calls
    c_a = rep_a.post("/calls", json={"prospect_name": "Rep Alpha Deal"}).json()
    c_b = rep_b.post("/calls", json={"prospect_name": "Rep Beta Deal"}).json()

    # Admin filters by rep-alpha
    res_a = admin.get("/calls?caller_id=rep-alpha").json()
    assert any(c["id"] == c_a["id"] for c in res_a)
    assert not any(c["id"] == c_b["id"] for c in res_a)

    # Admin filters by rep-beta
    res_b = admin.get("/calls?caller_id=rep-beta").json()
    assert any(c["id"] == c_b["id"] for c in res_b)
    assert not any(c["id"] == c_a["id"] for c in res_b)


def test_sync_offline_call_end_to_end(mock_db):
    """
    REGRESSION TEST: Verify that an entire offline-recorded call, including its
    historical timestamps, stage results, and outcome, can be synchronized to the backend
    atomically via POST /calls/sync-offline under the caller's identity.
    """
    payload = {
        "prospect_name": "Offline Prospect Corp",
        "company_name": "Apex Engineering Mumbai",
        "started_at": "2026-10-23T14:00:00+00:00",
        "ended_at": "2026-10-23T14:04:30+00:00",
        "outcome": "agreed_to_receive_report",
        "outcome_notes": "Agreed to review case study on WhatsApp; follow up next week",
        "current_stage_id": "their_need",
        "stage_results": [
            {
                "stage_id": "opening",
                "result": "Reached right person",
                "prospect_words": "Yes this is Rajesh speaking",
                "notes": "Verified title directly",
            },
            {
                "stage_id": "purpose",
                "result": "Gave 30 seconds",
                "prospect_words": "Make it quick please",
                "notes": "Tone was hurried but receptive",
            },
            {
                "stage_id": "their_need",
                "result": "Stated specific priority/bottleneck",
                "prospect_words": "Our current logistics vendor is delayed in Nhava Sheva",
                "notes": "Identified port clearance latency as core pain point",
            },
        ],
    }

    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 200, res.text
    call_data = res.json()
    assert call_data["id"] is not None
    assert call_data["caller_id"] == "rep-alpha"
    assert call_data["prospect_name"] == "Offline Prospect Corp"
    assert call_data["company_name"] == "Apex Engineering Mumbai"
    assert call_data["outcome"] == "agreed_to_receive_report"
    assert len(call_data["stage_results"]) == 3

    # Verify retrieval from GET /calls/{id}
    detail = client.get(f"/calls/{call_data['id']}").json()
    assert detail["id"] == call_data["id"]
    assert detail["ended_at"] is not None
    assert len(detail["stage_results"]) == 3


def test_sync_offline_call_invalid_outcome_rejected(mock_db):
    """
    REGRESSION TEST: Verify that offline sync still strictly validates final outcomes
    and rejects fraudulent or unrecognized outcome strings with 422.
    """
    payload = {
        "prospect_name": "Invalid Outcome Prospect",
        "outcome": "fraudulent_outcome_unregistered",
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 422


def test_sync_offline_call_requires_auth():
    """
    REGRESSION TEST: Verify that offline synchronization requires valid authentication.
    """
    unauthed = TestClient(app)
    payload = {"prospect_name": "Unauthed Prospect"}
    res = unauthed.post("/calls/sync-offline", json=payload)
    assert res.status_code == 401
