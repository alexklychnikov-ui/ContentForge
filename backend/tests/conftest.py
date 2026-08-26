import os
from collections.abc import Generator

os.environ["TESTING"] = "1"
from cryptography.fernet import Fernet

if not (os.environ.get("TOKEN_ENCRYPTION_KEY") or "").strip():
    os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
if os.environ.get("TELEGRAM_SMOKE") != "1":
    os.environ["TELEGRAM_HTTPS_PROXY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.services.catalog_service import seed_default_years
from app.services.rate_limit import login_rate_limiter
from tests.telegram_mock import install_telegram_mock
from tests.vk_mock import install_vk_mock

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        seed_default_years(db)
        db.commit()
    finally:
        db.close()
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mock_telegram(monkeypatch) -> None:
    if os.environ.get("TELEGRAM_SMOKE") == "1":
        return
    install_telegram_mock(monkeypatch)


@pytest.fixture(autouse=True)
def _mock_vk(monkeypatch) -> None:
    if os.environ.get("VK_SMOKE") == "1":
        return
    install_vk_mock(monkeypatch)