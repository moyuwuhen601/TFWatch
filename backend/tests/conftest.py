import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tfwatch.config import Config
from tfwatch.main import create_app
from tfwatch.models import App, Settings, User
from tfwatch.security import passwords

PASSWORD = "a password long enough"
WRITE = {"X-TFWatch-Request": "1"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("DATABASE_URL", url)
    migration = AlembicConfig(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(migration, "head")
    app = create_app(Config(database_url=url, encryption_key=Fernet.generate_key().decode(),
                            smtp_host="mail.example.org", smtp_from="test@example.org"))
    with app.state.sessions.begin() as session:
        session.execute(delete(App))
        session.execute(delete(User))
        settings = session.get(Settings, 1)
        settings.registration = True
        settings.anonymous = True
        settings.interval = 300
        session.add(User(email="admin@example.org", password_hash=passwords.hash(PASSWORD), is_admin=True))
    yield app
    app.state.sessions.kw["bind"].dispose()


@pytest.fixture
def client(app):
    with TestClient(app, headers=WRITE) as client:
        yield client


def register(client, email="person@example.org"):
    response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email="admin@example.org", password=PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response
