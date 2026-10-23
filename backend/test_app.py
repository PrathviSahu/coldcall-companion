from uuid import uuid4
from fastapi.testclient import TestClient
from app import app, STARTER_STAGES
import app as app_module

client = TestClient(app)

def test_health_available():
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] in {'ok', 'degraded'}
    assert 'database' in data
    assert 'llm' in data
    assert data['service'] == 'coldcall-companion-api'

def test_eight_stages_are_present_in_exact_order():
    response = client.get('/stages')
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    expected_order = [
        'opening',
        'purpose',
        'permission',
        'their_business',
        'their_need',
        'objection',
        'next_step',
        'close'
    ]
    actual_ids = [x['id'] for x in data]
    assert actual_ids == expected_order
    assert [x['position'] for x in data] == list(range(1, 9))
    for stage in data:
        assert stage['title']
        assert stage['purpose']
        assert stage['guidance']
        assert isinstance(stage.get('prospect_patterns'), list)
        assert len(stage['prospect_patterns']) >= 2
        assert isinstance(stage.get('stage_taps'), list)
        assert len(stage['stage_taps']) >= 3

def test_calls_input_validation():
    # Negative limit
    res = client.get('/calls?limit=-1')
    assert res.status_code == 400

    # Limit too large
    res = client.get('/calls?limit=500')
    assert res.status_code == 400

    # Negative offset
    res = client.get('/calls?offset=-5')
    assert res.status_code == 400

def test_stage_results_input_validation():
    # Invalid UUID
    res = client.post('/calls/invalid-uuid/stage-results', json={
        'stage_id': 'opening',
        'result': 'completed'
    })
    assert res.status_code == 422

    # String too long for prospect name in StartCall
    res = client.post('/calls', json={
        'prospect_name': 'x' * 200
    })
    assert res.status_code == 422

def test_unconfigured_database_returns_503():
    # If Supabase is unconfigured, verify endpoints fail gracefully with 503
    if app_module.supabase is None:
        call_id = str(uuid4())
        res = client.post('/calls', json={'prospect_name': 'Test'})
        assert res.status_code == 503
        assert 'Database is not configured' in res.json()['detail']

        res = client.get(f'/calls/{call_id}')
        assert res.status_code == 503

        res = client.post(f'/calls/{call_id}/stage-results', json={
            'stage_id': 'opening',
            'result': 'completed'
        })
        assert res.status_code == 503

        res = client.patch(f'/calls/{call_id}/stage', json={'stage_id': 'purpose'})
        assert res.status_code == 503

        res = client.post(f'/calls/{call_id}/close', json={'outcome': 'meeting_booked'})
        assert res.status_code == 503
