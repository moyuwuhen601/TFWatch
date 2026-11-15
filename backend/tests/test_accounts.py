from fastapi.testclient import TestClient

from conftest import PASSWORD, login, register


def test_registration_login_and_logout(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/session").json()["user"] is None
    user = register(client)
    assert not user["is_admin"]
    assert client.get("/api/session").json()["user"] == user
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/session").json()["user"] is None
    assert "HttpOnly" in login(client, user["email"]).headers["set-cookie"]


def test_csrf_and_login_limits(app, client):
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/auth/logout").status_code == 403
    for _ in range(12):
        response = client.post("/api/auth/login", json={"email": "missing@example.org", "password": "incorrect"})
        assert response.status_code == 401
    assert client.post("/api/auth/login", json={"email": "missing@example.org", "password": "x"}).status_code == 429


def test_email_verification_and_password_reset(client, monkeypatch):
    sent = []
    monkeypatch.setattr("tfwatch.accounts.send_mail", lambda config, email, subject, text: sent.append(text))
    register(client)
    assert client.post("/api/auth/verify-request").status_code == 204
    token = sent[-1].split("#token=")[1]
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400
    assert client.get("/api/session").json()["user"]["verified"]

    assert client.post("/api/auth/reset-request", json={"email": "person@example.org"}).status_code == 204
    reset = sent[-1].split("#token=")[1]
    new_password = PASSWORD + " new"
    assert client.post("/api/auth/reset-password", json={"token": reset, "password": new_password}).status_code == 204
    assert client.get("/api/session").json()["user"] is None
    login(client, "person@example.org", new_password)
