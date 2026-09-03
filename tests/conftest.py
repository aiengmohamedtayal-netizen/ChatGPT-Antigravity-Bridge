"""Pytest fixtures and test database setup."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "testing"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import database
from app.config import get_settings
from app.database import Base, get_db
from app.models.project import Project
from app.models.api_key import ApiKey, ApiScope
from app.core.security import generate_api_key
from app.main import app
from app.providers.registry import provider_registry
from app.providers.simulated import SimulatedAgentProvider

# Use in-memory SQLite with StaticPool so all connections share the same memory DB
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Patch global database engine & session maker during tests
database.engine = engine
database.SessionLocal = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Force simulated provider with 0 delay for fast automated tests
    fast_sim = SimulatedAgentProvider(step_delay=0.01)
    provider_registry.register(fast_sim)
    settings = get_settings()
    settings.DEFAULT_AGENT_PROVIDER = "simulated"


@pytest.fixture(autouse=True)
def init_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_project(db_session):
    project = Project(
        id="proj_test_123",
        name="Test Codebase",
        workspace_path=os.path.abspath(os.getcwd()),
        description="Test project for unit tests",
        instructions="Test instructions and rules",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def admin_api_key(db_session):
    raw_key, hashed, prefix = generate_api_key()
    key = ApiKey(
        id="key_admin_test",
        name="Admin Test Key",
        key_prefix=prefix,
        hashed_key=hashed,
        scopes=ApiScope.ALL_SCOPES,
        is_active=True,
    )
    db_session.add(key)
    db_session.commit()
    return {"raw_key": raw_key, "key_model": key}


@pytest.fixture
def read_only_api_key(db_session):
    raw_key, hashed, prefix = generate_api_key()
    key = ApiKey(
        id="key_read_only",
        name="Read Only Test Key",
        key_prefix=prefix,
        hashed_key=hashed,
        scopes=[ApiScope.TASKS_READ, ApiScope.PROJECTS_READ],
        is_active=True,
    )
    db_session.add(key)
    db_session.commit()
    return {"raw_key": raw_key, "key_model": key}
