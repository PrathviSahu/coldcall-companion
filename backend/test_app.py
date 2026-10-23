import concurrent.futures
import threading
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

    def delete(self):
        self._action = "delete"
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
            if self.table_name == "calls" and row.get("client_call_id"):
                for existing in table:
                    if existing.get("caller_id") == row.get("caller_id") and existing.get("client_call_id") == row.get("client_call_id"):
                        raise Exception("duplicate key value violates unique constraint 'calls_client_call_id_idx'")
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

        if self._action == "delete":
            deleted = []
            for item in list(filtered):
                table.remove(item)
                deleted.append(dict(item))
            return Result(deleted)

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
        self._simulate_rpc_failure = False
        self._lock = threading.Lock()

    def table(self, name: str):
        return MockTableQuery(name, self.db_state)

    def rpc(self, func_name: str, params: dict):
        class MockRpcQuery:
            def __init__(self, client, fn, p):
                self.client = client
                self.fn = fn
                self.params = p

            def execute(self):
                class Result:
                    def __init__(self, data):
                        self.data = data

                if getattr(self.client, "_simulate_missing_rpc", False):
                    raise Exception("function sync_offline_call_transaction does not exist")

                if self.fn == "close_call_transaction":
                    with getattr(self.client, "_lock", threading.Lock()):
                        call_id = self.params.get("p_call_id")
                        caller_id = self.params.get("p_caller_id")
                        caller_role = self.params.get("p_caller_role")
                        outcome = self.params.get("p_outcome")
                        notes = self.params.get("p_outcome_notes")
                        ended_at = self.params.get("p_ended_at") or datetime.now(timezone.utc).isoformat()

                        calls = self.client.db_state["calls"]
                        target = None
                        for c in calls:
                            if str(c.get("id")) == str(call_id):
                                target = c
                                break
                        if not target:
                            raise Exception(f"NotFound: Call {call_id} not found")

                        if target.get("caller_id") != caller_id and caller_role != "admin":
                            raise Exception("Forbidden: You are not authorized to close this call")

                        if target.get("ended_at") or target.get("outcome"):
                            if target.get("outcome") != outcome:
                                raise Exception(f"Conflict: Call {call_id} is already finalized with outcome {target.get('outcome')}")
                            # Matching outcome: idempotent retry
                        else:
                            target["outcome"] = outcome
                            target["outcome_notes"] = notes or target.get("outcome_notes") or ""
                            target["ended_at"] = ended_at

                        res_obj = dict(target)
                        res_obj["stage_results"] = [s for s in self.client.db_state["call_stage_results"] if str(s.get("call_id")) == str(call_id)]
                        return Result(res_obj)

                if self.fn == "sync_offline_call_transaction":
                    with getattr(self.client, "_lock", threading.Lock()):
                        if getattr(self.client, "_simulate_rpc_failure", False):
                            raise Exception("Simulated PostgreSQL transactional failure during stage write")

                        # PostgreSQL transaction scratchpad
                        scratch_calls = [dict(c) for c in self.client.db_state["calls"]]
                        scratch_stages = [dict(s) for s in self.client.db_state["call_stage_results"]]

                        caller_id = self.params.get("p_caller_id")
                        raw_client_id = self.params.get("p_client_call_id")
                        clean_client_id = str(raw_client_id).strip() if raw_client_id and str(raw_client_id).strip() else None

                        existing_call = None
                        if clean_client_id:
                            for c in scratch_calls:
                                if c.get("caller_id") == caller_id and c.get("client_call_id") == clean_client_id:
                                    existing_call = c
                                    break

                        if existing_call:
                            call_id = existing_call["id"]
                            if self.params.get("p_outcome"):
                                if existing_call.get("outcome") and existing_call.get("outcome") != self.params.get("p_outcome"):
                                    raise Exception(f"Conflict: Call {call_id} is already finalized with outcome {existing_call.get('outcome')}")
                                existing_call["outcome"] = self.params.get("p_outcome")
                                existing_call["outcome_notes"] = self.params.get("p_outcome_notes") or ""
                                if self.params.get("p_ended_at"):
                                    existing_call["ended_at"] = self.params.get("p_ended_at")
                            target_call = existing_call
                        else:
                            call_id = str(uuid4())
                            target_call = {
                                "id": call_id,
                                "caller_id": caller_id,
                                "client_call_id": clean_client_id,
                                "prospect_name": self.params.get("p_prospect_name"),
                                "company_name": self.params.get("p_company_name"),
                                "current_stage_id": self.params.get("p_current_stage_id"),
                                "started_at": self.params.get("p_started_at") or datetime.now(timezone.utc).isoformat(),
                                "ended_at": self.params.get("p_ended_at"),
                                "outcome": self.params.get("p_outcome"),
                                "outcome_notes": self.params.get("p_outcome_notes") or "",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "ai_summary": None,
                            }
                            scratch_calls.append(target_call)

                        stages = self.params.get("p_stage_results") or []
                        for idx, sr in enumerate(stages):
                            # Mid-transaction failure simulation: fails AFTER call insert and 1st stage
                            if getattr(self.client, "_simulate_failure_after_first_stage", False) and idx >= 1:
                                raise Exception("Simulated PostgreSQL transactional crash after writing 1 stage")

                            st_id = sr.get("stage_id")
                            res = sr.get("result", "completed")
                            words = sr.get("prospect_words", "")
                            notes = sr.get("notes", "")

                            found = False
                            for existing_sr in scratch_stages:
                                if existing_sr.get("call_id") == call_id and existing_sr.get("stage_id") == st_id:
                                    existing_sr.update({
                                        "result": res,
                                        "prospect_words": words,
                                        "notes": notes,
                                        "updated_at": datetime.now(timezone.utc).isoformat(),
                                    })
                                    found = True
                                    break
                            if not found:
                                scratch_stages.append({
                                    "id": str(uuid4()),
                                    "call_id": call_id,
                                    "stage_id": st_id,
                                    "result": res,
                                    "prospect_words": words,
                                    "notes": notes,
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                })

                        # Commit scratch state to committed db_state only if transaction succeeded
                        self.client.db_state["calls"] = scratch_calls
                        self.client.db_state["call_stage_results"] = scratch_stages

                        saved_stages = [sr for sr in scratch_stages if sr.get("call_id") == call_id]
                        res_obj = dict(target_call)
                        res_obj["stage_results"] = saved_stages
                        return Result(res_obj)

                raise NotImplementedError(f"RPC {self.fn} not implemented in mock")

        return MockRpcQuery(self, func_name, params)


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


def test_sync_offline_call_idempotent_retry_same_client_call_id(mock_db):
    """
    REGRESSION TEST: Verify that repeated sync requests with the same client_call_id
    are idempotent, return the same server record, and never create duplicate calls.
    """
    client_call_id = "test-client-uuid-987"
    payload = {
        "client_call_id": client_call_id,
        "prospect_name": "Idempotent Prospect",
        "company_name": "Idempotent Tech Ltd",
        "started_at": "2026-10-23T15:00:00+00:00",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person", "notes": "First attempt note"}
        ],
    }

    # First attempt: call created
    res1 = client.post("/calls/sync-offline", json=payload)
    assert res1.status_code == 200, res1.text
    call1 = res1.json()

    # Second attempt (simulating lost response or user retry): same client_call_id
    payload["stage_results"][0]["notes"] = "Updated draft note on retry"
    res2 = client.post("/calls/sync-offline", json=payload)
    assert res2.status_code == 200, res2.text
    call2 = res2.json()

    # Verify same call ID returned and only 1 call exists in database
    assert call1["id"] == call2["id"]
    calls_in_db = [c for c in mock_db.db_state["calls"] if c.get("client_call_id") == client_call_id]
    assert len(calls_in_db) == 1, f"Expected exactly 1 call, got {len(calls_in_db)}"


def test_sync_offline_call_rejects_invalid_stage_before_persistence(mock_db):
    """
    REGRESSION TEST: Verify that any invalid stage ID in stage_results causes the entire
    request to be rejected with 422 BEFORE inserting any call record into the database.
    """
    initial_calls_count = len(mock_db.db_state["calls"])
    payload = {
        "client_call_id": "invalid-stage-test-uuid",
        "prospect_name": "Corrupt Stage Prospect",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person"},
            {"stage_id": "invalid_nonexistent_stage", "result": "bogus"},
        ],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 422
    assert "Invalid stage_id" in res.text

    # Verify zero calls were written
    assert len(mock_db.db_state["calls"]) == initial_calls_count


def test_sync_offline_call_rejects_duplicate_stage_entries(mock_db):
    """
    REGRESSION TEST: Verify that requests containing duplicate entries for the same stage
    are rejected with 422 before any database writes.
    """
    payload = {
        "client_call_id": "dup-stage-test-uuid",
        "prospect_name": "Duplicate Stage Prospect",
        "stage_results": [
            {"stage_id": "opening", "result": "Attempt 1"},
            {"stage_id": "opening", "result": "Attempt 2"},
        ],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 422
    assert "Duplicate stage_id" in res.text


def test_sync_offline_call_rejects_inverted_timestamps(mock_db):
    """
    REGRESSION TEST: Verify that ended_at earlier than started_at is rejected with 422.
    """
    payload = {
        "prospect_name": "Time Traveler Prospect",
        "started_at": "2026-10-23T16:00:00+00:00",
        "ended_at": "2026-10-23T15:00:00+00:00",
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 422
    assert "ended_at" in res.text


def test_close_call_idempotent_retry_success(mock_db):
    """
    REGRESSION TEST: Verify that an ambiguous network retry of an already-closed call
    with the same outcome returns 200 OK with the finalized call data.
    """
    call = client.post("/calls", json={"prospect_name": "Close Retry Prospect"}).json()
    call_id = call["id"]

    # First close
    close_payload = {"outcome": "meeting_booked", "outcome_notes": "VP Sales meeting set for Tuesday"}
    res1 = client.post(f"/calls/{call_id}/close", json=close_payload)
    assert res1.status_code == 200

    # Ambiguous network retry with identical outcome
    res2 = client.post(f"/calls/{call_id}/close", json=close_payload)
    assert res2.status_code == 200
    assert res2.json()["outcome"] == "meeting_booked"
    assert res2.json()["ended_at"] is not None


def test_close_call_conflicting_outcome_rejected_with_409(mock_db):
    """
    REGRESSION TEST: Verify that attempting to close an already-closed call with a
    conflicting outcome is strictly rejected with 409 Conflict.
    """
    call = client.post("/calls", json={"prospect_name": "Conflict Close Prospect"}).json()
    call_id = call["id"]

    # First close
    res1 = client.post(f"/calls/{call_id}/close", json={"outcome": "meeting_booked"})
    assert res1.status_code == 200

    # Retry with conflicting outcome
    res2 = client.post(f"/calls/{call_id}/close", json={"outcome": "not_interested"})
    assert res2.status_code == 409
    assert "conflicting outcome" in res2.text


def test_sync_offline_call_transactional_rollback(mock_db):
    """
    REGRESSION TEST: Verify that if an RPC failure occurs, the transaction rolls back
    and raises 500 without leaving an orphan or corrupt call record.
    """
    mock_db._simulate_rpc_failure = True
    initial_calls_count = len(mock_db.db_state["calls"])
    payload = {
        "client_call_id": "rollback-test-uuid",
        "prospect_name": "Rollback Prospect",
        "stage_results": [{"stage_id": "opening", "result": "Reached right person"}],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 500
    assert "rolled back" in res.text

    # Verify no orphan calls left in db
    assert len(mock_db.db_state["calls"]) == initial_calls_count


def test_sync_offline_call_mid_transaction_rollback_leaves_no_partial_records(mock_db):
    """
    REGRESSION TEST: Verify that if a failure occurs mid-transaction (after creating
    the call row and writing 1 stage), PostgreSQL rolls back the entire transaction.
    Zero call rows and zero stage rows must be committed to the database.
    """
    mock_db._simulate_failure_after_first_stage = True
    payload = {
        "client_call_id": "mid-tx-failure-uuid-555",
        "prospect_name": "Mid-TX Crash Prospect",
        "company_name": "Crash Tech",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person"},
            {"stage_id": "purpose", "result": "Stated purpose clearly"},
            {"stage_id": "permission", "result": "Gave 30 seconds"},
        ],
    }

    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 500
    assert "rolled back" in res.text

    # Verify zero calls and zero stage records remain in committed database state
    calls_in_db = [c for c in mock_db.db_state["calls"] if c.get("client_call_id") == "mid-tx-failure-uuid-555"]
    assert len(calls_in_db) == 0, f"Expected 0 committed calls after rollback, found {len(calls_in_db)}"
    stages_in_db = [s for s in mock_db.db_state["call_stage_results"]]
    assert len(stages_in_db) == 0, f"Expected 0 committed stages after rollback, found {len(stages_in_db)}"


def test_sync_offline_call_missing_rpc_returns_503_migration_guidance(mock_db):
    """
    REGRESSION TEST: Verify that if the sync_offline_call_transaction RPC does not
    exist in Supabase, the API returns 503 with actionable migration instructions,
    rather than silently falling back to a non-atomic multi-request path.
    """
    mock_db._simulate_missing_rpc = True
    payload = {
        "client_call_id": "missing-rpc-test-uuid",
        "prospect_name": "Unmigrated DB Prospect",
        "stage_results": [{"stage_id": "opening", "result": "Reached right person"}],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 503
    assert "Database migration required" in res.text
    assert "supabase/schema.sql" in res.text


def test_rpc_permissions_and_empty_search_path_in_schema():
    """
    SECURITY TEST: Verify that the Supabase schema and standalone migration strictly:
    1. Pin empty search_path (SET search_path = '') on sync_offline_call_transaction.
    2. Revoke execute privileges from PUBLIC, anon, and authenticated.
    3. Grant execute privilege SOLELY to service_role.
    """
    with open("supabase/schema.sql", "r") as f:
        schema_sql = f.read()

    with open("supabase/migrations/20261023_secure_sync_offline_rpc.sql", "r") as f:
        migration_sql = f.read()

    for content, filename in [(schema_sql, "schema.sql"), (migration_sql, "migration.sql")]:
        assert "pg_catalog.coalesce" not in content, f"Invalid pg_catalog.coalesce syntax in {filename}"
        assert "pg_catalog.trim" not in content, f"Invalid pg_catalog.trim syntax in {filename}"
        assert "set search_path = ''" in content, f"Missing set search_path = '' in {filename}"
        assert "revoke all on function public.sync_offline_call_transaction" in content, f"Missing revoke in {filename}"
        assert "from public" in content, f"Missing revoke from public in {filename}"
        assert "from anon" in content, f"Missing revoke from anon in {filename}"
        assert "from authenticated" in content, f"Missing revoke from authenticated in {filename}"
        assert "grant execute on function public.sync_offline_call_transaction" in content, f"Missing grant in {filename}"
        assert "to service_role" in content, f"Missing grant to service_role in {filename}"


def test_sync_offline_call_repeated_sync_after_lost_response(mock_db):
    """
    REGRESSION TEST: Verify that retrying sync after a successful server-side write
    whose HTTP response was lost recovers the exact same call and returns 200 OK.
    """
    client_call_id = "lost-response-uuid-777"
    payload = {
        "client_call_id": client_call_id,
        "prospect_name": "Lost Response Prospect",
        "company_name": "Network Drop Corp",
        "outcome": "agreed_to_receive_report",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person", "notes": "Connected successfully"},
            {"stage_id": "their_need", "result": "Stated specific priority/bottleneck", "notes": "Pain point noted"},
        ],
    }

    # Initial sync
    res1 = client.post("/calls/sync-offline", json=payload)
    assert res1.status_code == 200
    call1 = res1.json()

    # Repeated sync simulation (lost response retry)
    res2 = client.post("/calls/sync-offline", json=payload)
    assert res2.status_code == 200
    call2 = res2.json()

    assert call1["id"] == call2["id"]
    calls_in_db = [c for c in mock_db.db_state["calls"] if c.get("client_call_id") == client_call_id]
    assert len(calls_in_db) == 1


def test_concurrent_sync_same_client_call_id(mock_db):
    """
    CONCURRENCY TEST: Verify that concurrent requests using the same (caller_id, client_call_id)
    recover the same call record rather than creating duplicates or surfacing avoidable conflicts.

    MOCK LIMITATION DISCLOSURE:
    This unit test exercises the FastAPI application handlers and thread-safe mock RPC logic.
    It proves that the API layer and transaction contract handle concurrent retries cleanly.
    It CANNOT prove live PostgreSQL engine-level concurrency (such as physical WAL writes,
    PostgreSQL snapshot isolation locks, or live Supabase PostgREST connection pool limits).
    Those require live cloud Supabase testing with valid credentials.
    """
    client_call_id = "concurrent-race-call-888"
    payload = {
        "client_call_id": client_call_id,
        "prospect_name": "Concurrent Prospect",
        "company_name": "Race Conditions Ltd",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person"},
        ],
    }

    # Execute 5 concurrent requests with identical (caller_id, client_call_id)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(client.post, "/calls/sync-offline", json=payload) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All concurrent requests should succeed (200 OK)
    assert all(r.status_code == 200 for r in results), f"Statuses: {[r.status_code for r in results]}"
    call_ids = [r.json()["id"] for r in results]
    assert len(set(call_ids)) == 1, f"Expected 1 unique call ID, got: {set(call_ids)}"

    # Database must contain exactly one call record
    calls_in_db = [c for c in mock_db.db_state["calls"] if c.get("client_call_id") == client_call_id]
    assert len(calls_in_db) == 1


def test_sync_offline_call_derives_caller_from_authenticated_token(mock_db):
    """
    SECURITY TEST: Verify that the caller identity is strictly derived from the
    authenticated token (CallerIdentity), preventing callers from forging p_caller_id.
    """
    client_call_id = "caller-isolation-uuid-999"
    payload = {
        "client_call_id": client_call_id,
        "prospect_name": "Isolation Prospect",
        "stage_results": [{"stage_id": "opening", "result": "Reached right person"}],
    }

    # Caller A token is set on client headers: rep-alpha
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 200
    call_data = res.json()
    assert call_data["caller_id"] == "rep-alpha"

    # Caller B cannot access Caller A's synced call
    client_b = TestClient(app)
    client_b.headers.update({"Authorization": f"Bearer {VALID_CALLER_B_TOKEN}"})
    get_res = client_b.get(f"/calls/{call_data['id']}")
    assert get_res.status_code == 403


def test_sync_offline_call_missing_client_call_id(mock_db):
    """
    REGRESSION TEST: Verify that missing client_call_id in sync request executes
    safely via the deliberate null-ID path without uninitialized record errors.
    """
    payload = {
        "prospect_name": "No Client ID Prospect",
        "company_name": "Unkeyed Corp",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person"},
        ],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 200, res.text
    call_data = res.json()
    assert call_data["id"] is not None
    assert call_data["client_call_id"] is None
    assert call_data["prospect_name"] == "No Client ID Prospect"


def test_sync_offline_call_whitespace_client_call_id(mock_db):
    """
    REGRESSION TEST: Verify that whitespace-only client_call_id is normalized
    to None and safely handled via deliberate null-ID path.
    """
    payload = {
        "client_call_id": "   ",
        "prospect_name": "Whitespace Client ID Prospect",
        "company_name": "Spaces Ltd",
        "stage_results": [
            {"stage_id": "opening", "result": "Reached right person"},
        ],
    }
    res = client.post("/calls/sync-offline", json=payload)
    assert res.status_code == 200, res.text
    call_data = res.json()
    assert call_data["client_call_id"] is None


# -----------------------------------------------------------------------------
# REAL POSTGRESQL INTEGRATION TESTS (Verified Against Local PostgreSQL Instance)
# -----------------------------------------------------------------------------
import shutil
import subprocess

PSQL_BIN = shutil.which("psql") or "/opt/homebrew/opt/postgresql@16/bin/psql"


def _check_real_postgres():
    if not os.path.exists(PSQL_BIN) and not shutil.which("psql"):
        return False
    try:
        r = subprocess.run([PSQL_BIN, "-d", "coldcall_test", "-c", "SELECT 1;"], capture_output=True, text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def test_real_postgresql_rpc_syntax_and_execution():
    """
    REAL POSTGRESQL TEST: Applies migration to coldcall_test database and executes
    public.sync_offline_call_transaction directly in PostgreSQL, proving:
    1. Valid COALESCE(...) and TRIM(...) syntax executes without pg_catalog function-resolution errors.
    2. Empty search_path executes and returns valid JSONB.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    # Re-apply migration to ensure exact current SQL is loaded
    apply_res = subprocess.run([PSQL_BIN, "-d", "coldcall_test", "-f", "supabase/migrations/20261023_secure_sync_offline_rpc.sql"], capture_output=True, text=True)
    assert apply_res.returncode == 0, f"Migration failed: {apply_res.stderr}"

    # Execute function
    run_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        """
        SELECT public.sync_offline_call_transaction(
          'rep-alpha',
          'real-pg-test-001',
          'Postgres Prospect',
          'Postgres Corp',
          'opening',
          NOW(),
          NULL,
          NULL,
          NULL,
          '[{"stage_id": "opening", "result": "Reached right person"}]'::jsonb
        );
        """
    ]
    exec_res = subprocess.run(run_cmd, capture_output=True, text=True)
    assert exec_res.returncode == 0, f"Execution failed: {exec_res.stderr}"
    data = json.loads(exec_res.stdout.strip())
    assert data["client_call_id"] == "real-pg-test-001"
    assert data["caller_id"] == "rep-alpha"
    assert len(data["stage_results"]) == 1


def test_real_postgresql_concurrent_sync_same_client_id():
    """
    REAL POSTGRESQL TEST: Spawns 5 concurrent OS processes running psql transactions
    with the exact same (caller_id, client_call_id).
    Proves that pg_advisory_xact_lock and ON CONFLICT serialize concurrent requests,
    all succeed without 23505 unique constraint errors, all return identical call ID,
    and exactly 1 call row is written to public.calls.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    race_client_id = f"pg-concurrency-test-{uuid4()}"

    def run_worker(idx):
        cmd = [
            PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
            f"""
            SELECT public.sync_offline_call_transaction(
              'rep-alpha',
              '{race_client_id}',
              'Race Prospect {idx}',
              'Race Corp',
              'opening',
              NOW(),
              NULL,
              NULL,
              NULL,
              '[{{"stage_id": "opening", "result": "Reached right person"}}]'::jsonb
            );
            """
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_worker, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All must succeed
    assert all(r.returncode == 0 for r in results), f"Errors: {[r.stderr for r in results if r.returncode != 0]}"
    call_ids = {json.loads(r.stdout.strip())["id"] for r in results}
    assert len(call_ids) == 1, f"Expected 1 unique call ID across concurrent workers, got: {call_ids}"

    # Database must contain exactly 1 row
    count_cmd = [PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c", f"SELECT count(*) FROM public.calls WHERE client_call_id = '{race_client_id}';"]
    count_res = subprocess.run(count_cmd, capture_output=True, text=True)
    assert count_res.stdout.strip() == "1"


def test_real_postgresql_missing_and_whitespace_client_id():
    """
    REAL POSTGRESQL TEST: Tests deliberate null client_call_id and whitespace client_call_id
    against real PostgreSQL, verifying no 'record v_call is not assigned yet' errors occur.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    for test_id_val in ["NULL", "'   '"]:
        cmd = [
            PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
            f"""
            SELECT public.sync_offline_call_transaction(
              'rep-alpha',
              {test_id_val},
              'Null Client Prospect',
              'Null Corp',
              'opening',
              NOW(),
              NULL,
              NULL,
              NULL,
              '[]'::jsonb
            );
            """
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Execution failed for {test_id_val}: {res.stderr}"
        data = json.loads(res.stdout.strip())
        assert data["client_call_id"] is None


def test_real_postgresql_outcome_conflict_on_finalized_call():
    """
    REAL POSTGRESQL TEST: Finalizes a call with 'meeting_booked' and retries with
    'not_interested', verifying real PostgreSQL raises 23505 conflict exception.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    client_id = f"pg-conflict-test-{uuid4()}"
    # 1. Finalize call
    cmd1 = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        SELECT public.sync_offline_call_transaction(
          'rep-alpha',
          '{client_id}',
          'Finalized Prospect',
          'Final Corp',
          'permission',
          NOW(),
          NOW(),
          'meeting_booked',
          'Meeting scheduled',
          '[]'::jsonb
        );
        """
    ]
    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    assert r1.returncode == 0

    # 2. Conflicting outcome retry
    cmd2 = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        SELECT public.sync_offline_call_transaction(
          'rep-alpha',
          '{client_id}',
          'Finalized Prospect',
          'Final Corp',
          'permission',
          NOW(),
          NOW(),
          'not_interested',
          'Changed outcome',
          '[]'::jsonb
        );
        """
    ]
    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    assert r2.returncode != 0
    assert "already finalized with outcome meeting_booked" in r2.stderr


def test_real_postgresql_mid_transaction_rollback():
    """
    REAL POSTGRESQL TEST: Verifies that a crash during stage write causes PostgreSQL
    to roll back the entire transaction, leaving zero call rows and zero stage rows.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    rollback_client_id = f"pg-rollback-{uuid4()}"
    cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        DO $$
        BEGIN
          BEGIN
            PERFORM public.sync_offline_call_transaction(
              'rep-alpha',
              '{rollback_client_id}',
              'Crash Prospect',
              'Crash Corp',
              'opening',
              NOW(),
              NULL,
              NULL,
              NULL,
              '[{{"stage_id": "opening", "result": "ok"}}, {{"invalid_schema": 123}}]'::jsonb
            );
          EXCEPTION WHEN OTHERS THEN
            NULL; -- Expected exception
          END;
        END $$;
        """
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0

    # Verify zero calls exist in database for this client ID
    count_cmd = [PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c", f"SELECT count(*) FROM public.calls WHERE client_call_id = '{rollback_client_id}';"]
    count_res = subprocess.run(count_cmd, capture_output=True, text=True)
    assert count_res.stdout.strip() == "0"


def test_real_postgresql_rpc_privilege_enforcement():
    """
    REAL POSTGRESQL TEST: Verifies that anon and authenticated roles are denied execute
    on public.sync_offline_call_transaction, while service_role is granted execute.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    for role, should_succeed in [("anon", False), ("authenticated", False), ("service_role", True)]:
        cmd = [
            PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
            f"""
            SET ROLE {role};
            SELECT public.sync_offline_call_transaction(
              'rep-alpha',
              'perm-test-{role}',
              'Perm Prospect',
              'Perm Corp',
              'opening',
              NOW(),
              NULL,
              NULL,
              NULL,
              '[]'::jsonb
            );
            """
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if should_succeed:
            assert res.returncode == 0, f"Role {role} should succeed but failed: {res.stderr}"
        else:
            assert res.returncode != 0, f"Role {role} should fail but succeeded: {res.stdout}"
            assert "permission denied for function sync_offline_call_transaction" in res.stderr


def test_start_call_competing_insert_recovers_existing_call(mock_db, monkeypatch):
    """
    REGRESSION TEST: Verify that if a competing request inserts a call with the same
    (caller_id, client_call_id) right before this request's insert executes, start_call
    catches the unique constraint collision (calls_client_call_id_idx) and safely
    recovers and returns the existing call record instead of throwing an unhandled 500 error.
    """
    client_call_id = "competing-race-uuid-123"
    payload = {
        "client_call_id": client_call_id,
        "prospect_name": "Racing Prospect",
        "company_name": "Speedy Corp",
    }

    # First request: normal creation
    res1 = client.post("/calls", json=payload)
    assert res1.status_code == 200
    call1 = res1.json()

    # Second request: retry with same client_call_id returns existing call
    res2 = client.post("/calls", json=payload)
    assert res2.status_code == 200
    call2 = res2.json()
    assert call1["id"] == call2["id"]

    # Third simulation: force an insert-level unique conflict (simulating race condition)
    # where the pre-check didn't see the record, but insert collides on calls_client_call_id_idx
    orig_table = mock_db.table

    race_first_select_done = False

    class RaceTableQuery(MockTableQuery):
        def maybe_single(self):
            super().maybe_single()
            nonlocal race_first_select_done
            if not race_first_select_done:
                self._force_empty_select = True
                race_first_select_done = True
            return self

        def execute(self):
            if getattr(self, "_force_empty_select", False) and self._action == "select":
                class EmptyResult:
                    data = None
                    count = 0
                return EmptyResult()
            return super().execute()

    def racing_table(name: str):
        if name == "calls":
            return RaceTableQuery(name, mock_db.db_state)
        return orig_table(name)

    monkeypatch.setattr(mock_db, "table", racing_table)

    # Calling /calls will hit the simulated race where select returns None,
    # insert throws unique key violation, and catch handler recovers existing call
    res_race = client.post("/calls", json=payload)
    assert res_race.status_code == 200
    call_race = res_race.json()
    assert call_race["id"] == call1["id"]


def test_real_postgresql_competing_call_creation_and_conflicting_finalization():
    """
    REAL POSTGRESQL TEST: Proves that:
    1. A call inserted via normal call-creation (simulating POST /calls) with a client_call_id
       and finalized outcome cannot have its outcome silently overwritten by sync_offline_call_transaction.
    2. The PL/pgSQL upsert loop catches the racing insert, acquires the row lock, and enforces
       the outcome-conflict check atomically in PostgreSQL.
    3. The conflicting offline sync attempt fails with 23505 conflict exception.
    4. The original finalized outcome in public.calls remains unchanged.
    5. Exactly 1 call row exists in public.calls (zero duplicates).
    6. A subsequent retry with matching outcome succeeds and returns the existing call.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    # Re-apply migration to ensure exact current SQL is loaded
    subprocess.run([PSQL_BIN, "-d", "coldcall_test", "-f", "supabase/migrations/20261023_secure_sync_offline_rpc.sql"], capture_output=True, text=True)

    client_id = f"pg-competing-race-{uuid4()}"

    # Step 1: Simulate normal call creation and finalization (e.g. from POST /calls and close)
    insert_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        INSERT INTO public.calls (
          caller_id, client_call_id, prospect_name, company_name,
          current_stage_id, outcome, outcome_notes, started_at, ended_at
        ) VALUES (
          'rep-alpha', '{client_id}', 'Competing Prospect', 'Compete Ltd',
          'purpose', 'meeting_booked', 'Initial meeting scheduled', NOW(), NOW()
        ) RETURNING id;
        """
    ]
    ins_res = subprocess.run(insert_cmd, capture_output=True, text=True)
    assert ins_res.returncode == 0, f"Insert failed: {ins_res.stderr}"
    existing_id = ins_res.stdout.strip().splitlines()[0]

    # Step 2: Attempt conflicting offline sync with outcome 'not_interested'
    conflict_sync_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        SELECT public.sync_offline_call_transaction(
          'rep-alpha',
          '{client_id}',
          'Competing Prospect',
          'Compete Ltd',
          'purpose',
          NOW(),
          NOW(),
          'not_interested',
          'Attempted overwrite',
          '[]'::jsonb
        );
        """
    ]
    conf_res = subprocess.run(conflict_sync_cmd, capture_output=True, text=True)
    # Must fail with conflict exception
    assert conf_res.returncode != 0
    assert "already finalized with outcome meeting_booked" in conf_res.stderr

    # Step 3: Verify the outcome in public.calls was NOT overwritten
    verify_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"SELECT outcome FROM public.calls WHERE client_call_id = '{client_id}';"
    ]
    v_res = subprocess.run(verify_cmd, capture_output=True, text=True)
    assert v_res.stdout.strip() == "meeting_booked", f"Expected meeting_booked, got {v_res.stdout.strip()}"

    # Step 4: Verify exactly 1 call row exists in database
    count_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"SELECT count(*) FROM public.calls WHERE client_call_id = '{client_id}';"
    ]
    c_res = subprocess.run(count_cmd, capture_output=True, text=True)
    assert c_res.stdout.strip() == "1"

    # Step 5: Retry with matching outcome 'meeting_booked' succeeds and recovers existing call
    matching_sync_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        SELECT public.sync_offline_call_transaction(
          'rep-alpha',
          '{client_id}',
          'Competing Prospect',
          'Compete Ltd',
          'purpose',
          NOW(),
          NOW(),
          'meeting_booked',
          'Updated meeting notes',
          '[{{"stage_id": "opening", "result": "Reached right person"}}]'::jsonb
        );
        """
    ]
    match_res = subprocess.run(matching_sync_cmd, capture_output=True, text=True)
    assert match_res.returncode == 0, f"Matching retry failed: {match_res.stderr}"
    data = json.loads(match_res.stdout.strip())
    assert data["id"] == existing_id
    assert data["outcome"] == "meeting_booked"
    assert len(data["stage_results"]) == 1


def test_concurrent_close_requests_cannot_overwrite_conflicting_outcomes(mock_db):
    """
    CONCURRENCY TEST: Verify that when two concurrent close requests with different
    outcomes target the same open call, exactly one succeeds and the other receives
    HTTP 409 Conflict. The persisted outcome must never be overwritten.
    """
    # 1. Start an open call
    res_start = client.post("/calls", json={"prospect_name": "Race Close Prospect", "company_name": "Race Corp"})
    assert res_start.status_code == 200
    call_id = res_start.json()["id"]

    # 2. Concurrently execute two close requests with conflicting outcomes
    def do_close(outcome):
        return client.post(f"/calls/{call_id}/close", json={"outcome": outcome, "outcome_notes": f"Notes for {outcome}"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_close, "meeting_booked")
        f2 = executor.submit(do_close, "not_interested")
        r1, r2 = f1.result(), f2.result()

    statuses = {r1.status_code, r2.status_code}
    assert statuses == {200, 409}, f"Expected {200, 409}, got: {[r1.status_code, r2.status_code]}"

    # Determine winner
    winner = r1 if r1.status_code == 200 else r2
    winning_outcome = winner.json()["outcome"]

    # 3. Verify database outcome matches winner and was not overwritten
    db_call = [c for c in mock_db.db_state["calls"] if str(c.get("id")) == str(call_id)][0]
    assert db_call["outcome"] == winning_outcome

    # 4. Idempotent retry with winning outcome returns 200 OK
    retry_win = client.post(f"/calls/{call_id}/close", json={"outcome": winning_outcome})
    assert retry_win.status_code == 200
    assert retry_win.json()["outcome"] == winning_outcome

    # 5. Retry with conflicting outcome fails with 409 Conflict
    other_outcome = "not_interested" if winning_outcome == "meeting_booked" else "meeting_booked"
    retry_lose = client.post(f"/calls/{call_id}/close", json={"outcome": other_outcome})
    assert retry_lose.status_code == 409
    assert "conflicting outcome" in retry_lose.text


def test_real_postgresql_concurrent_close_call_conflict_rejection():
    """
    REAL POSTGRESQL TEST: Spawns 2 concurrent psql processes executing
    close_call_transaction on the same open call in PostgreSQL with different outcomes.
    Proves that PostgreSQL row-locking (FOR UPDATE) serializes execution, exactly 1 succeeds,
    the competing call receives 23505 conflict exception, the winner outcome is preserved,
    and matching outcome retry succeeds.
    """
    if not _check_real_postgres():
        pytest.skip("Local PostgreSQL database coldcall_test not available")

    # Re-apply migrations
    subprocess.run([PSQL_BIN, "-d", "coldcall_test", "-f", "supabase/migrations/20261023_secure_close_call_rpc.sql"], capture_output=True, text=True)

    # 1. Create open call with unique key
    test_close_key = f"pg-close-race-{uuid4()}"
    ins_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        INSERT INTO public.calls (
          caller_id, client_call_id, prospect_name, company_name, current_stage_id, started_at
        ) VALUES (
          'rep-alpha', '{test_close_key}', 'Close Race Prospect', 'Close Race Ltd', 'opening', NOW()
        ) RETURNING id;
        """
    ]
    ins_res = subprocess.run(ins_cmd, capture_output=True, text=True)
    assert ins_res.returncode == 0, f"Insert failed: {ins_res.stderr}"
    call_id = ins_res.stdout.strip().splitlines()[0]

    # 2. Concurrently execute close_call_transaction with conflicting outcomes
    def worker(outcome):
        cmd = [
            PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
            f"""
            SELECT public.close_call_transaction(
              '{call_id}'::uuid,
              'rep-alpha',
              'caller',
              '{outcome}',
              'Notes for {outcome}',
              NOW()
            );
            """
        ]
        return outcome, subprocess.run(cmd, capture_output=True, text=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, "meeting_booked")
        f2 = executor.submit(worker, "not_interested")
        res1, res2 = f1.result(), f2.result()

    results = [res1, res2]
    successes = [r for r in results if r[1].returncode == 0]
    conflicts = [r for r in results if r[1].returncode != 0]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(conflicts) == 1, f"Expected exactly 1 conflict, got {len(conflicts)}"
    assert "already finalized with outcome" in conflicts[0][1].stderr

    winner_outcome = successes[0][0]

    # 3. Verify database preserved winner outcome
    chk_cmd = [PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c", f"SELECT outcome FROM public.calls WHERE id = '{call_id}';"]
    chk_res = subprocess.run(chk_cmd, capture_output=True, text=True)
    assert chk_res.stdout.strip() == winner_outcome

    # 4. Matching outcome retry succeeds
    retry_cmd = [
        PSQL_BIN, "-d", "coldcall_test", "-t", "-A", "-c",
        f"""
        SELECT public.close_call_transaction(
          '{call_id}'::uuid,
          'rep-alpha',
          'caller',
          '{winner_outcome}',
          'Retry notes',
          NOW()
        );
        """
    ]
    r_res = subprocess.run(retry_cmd, capture_output=True, text=True)
    assert r_res.returncode == 0
    data = json.loads(r_res.stdout.strip())
    assert data["outcome"] == winner_outcome
