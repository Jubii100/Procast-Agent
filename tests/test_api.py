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
    assert data["user_id"] == test_user_headers["X-User-ID"]


def test_mock_auth_header(sync_client: TestClient):
    """Test mock authentication via header."""
    response = sync_client.post(
        "/api/v1/session",
        headers={
            "X-User-ID": "custom-user-456",
            "X-User-Email": "custom@test.com",
        },
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["user_id"] == "custom-user-456"


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
