import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import WRITE, login, register
from test_monitor import CODE, URL
from tfwatch.checks import claim_invite, record_check
from tfwatch.db import now
from tfwatch.models import Channel, Delivery
from tfwatch.notifications import enqueue, process_delivery
from tfwatch.outbound import https_target, resolve_public
from tfwatch.testflight import Observation


def test_channels_preferences_retry_and_unknown_dedup(app, client, monkeypatch):
    user = register(client)
    client.post("/api/apps", json={"url": URL})
    client.put(f"/api/invites/{CODE}/follow")
    hook_url = "https://example.org/hook"
    channel = client.post("/api/channels", json={
        "kind": "webhook", "label": "Private", "config": {"url": hook_url, "token": "my-token"},
    }).json()
    assert channel == {"id": channel["id"], "kind": "webhook", "label": "Private", "enabled": True}

    with TestClient(app, headers=WRITE) as second:
        register(second, "other@example.org")
        assert second.get("/api/channels").json() == []
        assert second.post(f"/api/channels/{channel['id']}/test").status_code == 404
        assert second.get("/api/apps?followed=true").json()["items"] == []
        second.put(f"/api/invites/{CODE}/follow")
        assert second.post("/api/channels", json={
            "kind": "webhook", "label": "Second", "config": {"url": "https://example.net/hook"},
        }).status_code == 201
        second.patch("/api/account", json={"notify_mode": "changes"})

    assert client.post("/api/channels", json={"kind": "email", "label": "Mail"}).status_code == 422
    sessions = app.state.sessions
    with sessions() as session:
        encrypted = session.get(Channel, channel["id"]).encrypted
        assert b"my-token" not in encrypted
        assert session.get(Channel, channel["id"]).user_id == user["id"]

    timestamp = now()
    for offset, status in [(0, "full"), (300, "open"), (600, "unknown"), (1200, "open"), (1500, "closed")]:
        assert record_check(sessions, *claim_invite(sessions, timestamp + offset),
                            Observation(status), timestamp + offset, enqueue)

    sent = []

    def post(url, payload, headers):
        sent.append((url, payload["status"], headers.copy()))
        if len(sent) == 1:
            raise OSError("simulated downstream timeout")

    monkeypatch.setattr("tfwatch.notifications.post_json", post)
    for _ in range(3):
        assert process_delivery(sessions, app.state.config, timestamp + 1600)
    assert not process_delivery(sessions, app.state.config, timestamp + 1600)
    assert process_delivery(sessions, app.state.config, timestamp + 1660)
    assert {item[1] for item in sent if item[0] == hook_url} == {"open"}
    assert sent[0] == sent[-1]
    assert sent[0][2]["Authorization"] == "Bearer my-token"
    assert len({item[2]["Idempotency-Key"] for item in sent}) == 3
    with sessions() as session:
        assert sorted(session.scalars(select(Delivery.attempts)).all()) == [1, 1, 2]
    assert client.delete(f"/api/invites/{CODE}/follow").status_code == 204
    assert client.get("/api/apps?followed=true").json()["items"] == []


@pytest.mark.parametrize("url", ["http://example.org/", "https://u:p@example.org", "https://a\\b", "https://a/#x"])
def test_reject_unsafe_webhook_syntax(url):
    with pytest.raises(ValueError):
        https_target(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "192.168.0.1",
                                     "::1", "::ffff:127.0.0.1", "224.0.0.1", "64:ff9b::a00:1"])
def test_reject_unsafe_dns_answers(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (None, None, None, "", ("1.1.1.1", 443)), (None, None, None, "", (address, 443))
    ])
    with pytest.raises(ValueError):
        resolve_public("example.org", 443)


def test_admin_permissions_and_visitor_switches(app, client):
    user = register(client)
    assert client.get("/api/admin/users").status_code == 403
    login(client)
    settings = {"registration": False, "anonymous": True, "interval": 120}
    assert client.put("/api/admin/settings", json=settings).json() == settings
    with TestClient(app, headers=WRITE) as visitor:
        assert visitor.get("/api/apps").status_code == 200
        assert visitor.post("/api/auth/register", json={"email": "new@example.org", "password": "test password"}).status_code == 403
        login(visitor, user["email"])
        assert client.patch(f"/api/admin/users/{user['id']}", json={"active": False}).status_code == 200
        assert visitor.get("/api/session").json()["user"] is None
        assert client.put("/api/admin/settings", json={**settings, "anonymous": False}).status_code == 200
        assert visitor.get("/api/apps").status_code == 401
        assert visitor.get(f"/api/invites/{CODE}/timeline").status_code == 401
