from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "test_agroguardian_pytest.db"
TEST_ADMIN_USERNAME = "test-admin"
TEST_ADMIN_EMAIL = "test-admin@example.test"
TEST_ADMIN_PASSWORD = secrets.token_urlsafe(24)

os.environ["DATABASE_URL"] = "sqlite:///./test_agroguardian_pytest.db"
os.environ["ENABLE_OVERPASS_GEO"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["AUTO_SEED_DEMO"] = "false"
os.environ["INITIAL_ADMIN_USERNAME"] = TEST_ADMIN_USERNAME
os.environ["INITIAL_ADMIN_EMAIL"] = TEST_ADMIN_EMAIL
os.environ["INITIAL_ADMIN_PASSWORD"] = TEST_ADMIN_PASSWORD

if DB_PATH.exists():
    DB_PATH.unlink()

alembic_config = Config(str(ROOT_DIR / "alembic.ini"))
command.upgrade(alembic_config, "head")

from backend.database import SessionLocal, engine
from backend.database_seed import seed_database_from_environment

seed_database_from_environment()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_database():
    yield
    engine.dispose()
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            pass


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
