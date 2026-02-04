"""Pytest configuration and fixtures."""

import asyncio
import os
import time
from typing import AsyncGenerator, Generator

import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


# Ensure JWT settings for tests
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_ISSUER", "procast-ai")
os.environ.setdefault("JWT_AUDIENCE", "procast-ui")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_user_headers() -> dict[str, str]:
    """Headers for authenticated test requests."""
    now_epoch = int(time.time())
    payload = {
        "sub": "test-user-123",
        "email": "test@procast.local",
        "roles": ["user"],
        "scope": "budget:read budget:analyze",
        "iat": now_epoch,
        "exp": now_epoch + 3600,
        "iss": os.environ["JWT_ISSUER"],
        "aud": os.environ["JWT_AUDIENCE"],
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
    return {
        "Authorization": f"Bearer {token}",
    }


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API tests."""
    from src.api.main import app
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sync_client() -> Generator[TestClient, None, None]:
    """Create sync HTTP client for simple API tests."""
    from src.api.main import app
    
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_analyze_request() -> dict:
    """Sample analyze request payload."""
    return {
        "query": "What is the total budget for all projects?",
        "context": None,
        "session_id": None,
    }


@pytest.fixture
def sample_query_results() -> list[dict]:
    """Sample query results for testing analysis."""
    return [
        {
            "project_name": "Summit 2026",
            "budgeted": 500000,
            "committed": 425000,
            "percentage_used": 85,
        },
        {
            "project_name": "Conference Q2",
            "budgeted": 200000,
            "committed": 180000,
            "percentage_used": 90,
        },
    ]
