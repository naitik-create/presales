"""Tests run against TEST_DATABASE_URL (presales_test). Tables are truncated before each API test."""
import os

import pytest

from app.config import get_settings

settings = get_settings()
if not settings.TEST_DATABASE_URL:
    raise SystemExit("Set TEST_DATABASE_URL in backend/.env to run tests")
os.environ["DATABASE_URL"] = settings.TEST_DATABASE_URL
get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import db as dbmod  # noqa: E402

dbmod.configure(get_settings().DATABASE_URL)

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

HEADERS = {"X-Requested-With": "presales"}


@pytest.fixture()
def db():
    with dbmod.SessionLocal() as s:
        yield s


@pytest.fixture()
def clean_db():
    with dbmod.engine().begin() as conn:
        names = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        # triggers block DELETE on immutable tables; TRUNCATE is allowed for the test database owner
        conn.execute(text("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))
    with dbmod.SessionLocal() as s:
        pw = seed(s)
    from app.main import _hits
    _hits.clear()
    return pw


@pytest.fixture()
def client():
    return TestClient(app)


def login(client: TestClient, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()
