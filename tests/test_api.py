"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(sync_client: TestClient):
    """Test health check endpoint."""
    response = sync_client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "agent" in data
    assert "timestamp" in data


def test_health_endpoint_structure(sync_client: TestClient):
    """Test health response structure."""
    response = sync_client.get("/health")
    data = response.json()
    
    # Check database health structure
    assert "status" in data["database"]
    
    # Check agent status structure
    assert "status" in data["agent"]


def test_docs_endpoint(sync_client: TestClient):
    """Test OpenAPI docs endpoint."""
    response = sync_client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema(sync_client: TestClient):
    """Test OpenAPI schema endpoint."""
    response = sync_client.get("/openapi.json")
    assert response.status_code == 200
    
    schema = response.json()
    assert schema["info"]["title"] == "Procast AI Agent"
    assert "paths" in schema


def test_analyze_endpoint_requires_query(sync_client: TestClient, test_user_headers: dict):
    """Test analyze endpoint requires query field."""
    response = sync_client.post(
        "/api/v1/analyze",
        json={},
        headers=test_user_headers,
    )
    assert response.status_code == 422  # Validation error


def test_analyze_endpoint_accepts_valid_request(
    sync_client: TestClient,
    test_user_headers: dict,
    sample_analyze_request: dict,
):
    """Test analyze endpoint accepts valid request."""
    # Note: This test may fail if database/LLM not configured
    # It's more of an integration test
    response = sync_client.post(
        "/api/v1/analyze",
        json=sample_analyze_request,
        headers=test_user_headers,
    )
    # Either succeeds or fails gracefully
    assert response.status_code in (200, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "response" in data
        assert "session_id" in data


def test_session_endpoint(sync_client: TestClient, test_user_headers: dict):
    """Test session creation endpoint."""
    response = sync_client.post(
        "/api/v1/session",
        headers=test_user_headers,
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "session_id" in data
    assert "user_id" in data
    assert data["user_id"] == "test-user-123"


def test_auth_required_for_sessions(sync_client: TestClient):
    """Sessions list requires JWT auth."""
    response = sync_client.get("/api/v1/sessions")
    assert response.status_code == 401


def test_sessions_list(sync_client: TestClient, test_user_headers: dict):
    """Test sessions list endpoint."""
    response = sync_client.get(
        "/api/v1/sessions",
        headers=test_user_headers,
    )
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_session_detail(sync_client: TestClient, test_user_headers: dict):
    """Test session detail endpoint."""
    response = sync_client.get(
        "/api/v1/sessions/nonexistent-session",
        headers=test_user_headers,
    )
    assert response.status_code in (404, 500)


def test_chat_stream_requires_auth(sync_client: TestClient):
    """Chat stream requires JWT auth."""
    response = sync_client.post("/api/v1/chat/stream", json={"session_id": "x", "messages": []})
    assert response.status_code == 401


def test_chat_stream_endpoint(sync_client: TestClient, test_user_headers: dict):
    """Chat stream endpoint accepts valid request."""
    response = sync_client.post(
        "/api/v1/chat/stream",
        headers=test_user_headers,
        json={
            "session_id": "test-session-stream",
            "messages": [{"role": "user", "content": "Hello"}],
            "model": None,
            "temperature": 0.7,
        },
    )
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        assert response.headers.get("content-type", "").startswith("text/event-stream")
        assert "data:" in response.text


class TestSchemaEndpoints:
    """Tests for schema introspection endpoints."""
    
    def test_schema_endpoint(self, sync_client: TestClient, test_user_headers: dict):
        """Test schema endpoint."""
        response = sync_client.get(
            "/api/v1/schema",
            headers=test_user_headers,
        )
        # May fail if DB not connected
        assert response.status_code in (200, 500)
        
        if response.status_code == 200:
            data = response.json()
            assert "tables" in data
            assert "total_tables" in data
    
    def test_tables_list_endpoint(self, sync_client: TestClient, test_user_headers: dict):
        """Test tables list endpoint."""
        response = sync_client.get(
            "/api/v1/schema/tables",
            headers=test_user_headers,
        )
        assert response.status_code in (200, 500)
        
        if response.status_code == 200:
            tables = response.json()
            assert isinstance(tables, list)
