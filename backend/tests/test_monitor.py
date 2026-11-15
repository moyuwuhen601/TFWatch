from types import SimpleNamespace

import httpx
import pytest

from conftest import register
from tfwatch.checks import claim_invite, record_check
from tfwatch.db import now
from tfwatch.models import Invite
from tfwatch.testflight import Observation, check, invite_code, parse_page
from tfwatch.timeline import summarize

CODE = "aBcD1234"
URL = f"https://testflight.apple.com/join/{CODE}"


def page(message, code=CODE):
    return f"""
    <meta property="og:title" content="Join the Example &amp; App beta">
    <div class="beta-status"><div class="app-icon"></div><span>{message}</span></div>
    <a href="itms-beta://testflight.apple.com/join/{code}">View in TestFlight</a>
    """


@pytest.mark.parametrize(("status", "message"), [
    ("open", "To join the Example beta, open the link after you install TestFlight."),
    ("full", "This beta is full."),
    ("closed", "This beta isn&#39;t accepting any new testers right now."),
    ("unknown", "We are experiencing a problem."),
])
def test_sample_markers(status, message):
    fixture = page(message)
    assert parse_page(CODE, 200, fixture).status == status
    assert parse_page(CODE, 503, fixture).status == "unknown"
    assert parse_page(CODE, 404, fixture).status == "unknown"


def test_generic_content_and_network_errors_are_unknown():
    assert parse_page(CODE, 200, "<p>This beta is full.</p>").status == "unknown"
    assert parse_page(CODE, 200, page("To join the beta, open the link after you install TestFlight.",
                                      code="00000000")).status == "unknown"

    def timeout(request):
        raise httpx.ReadTimeout("timeout")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        assert check(client, CODE).status == "unknown"


@pytest.mark.parametrize("url", [
    "http://testflight.apple.com/join/aBcD1234",
    "https://testflight.apple.com.evil.test/join/aBcD1234",
    "https://evil.test@testflight.apple.com/join/aBcD1234",
    "https://testflight.apple.com/join/%61BcD1234",
])
def test_only_apple_public_invites(url):
    with pytest.raises(ValueError):
        invite_code(url)
    assert invite_code(URL + "/?share=1#ignored") == CODE


def test_shared_catalog_claims_and_public_timeline(app, client, monkeypatch):
    timestamp = now() - 25 * 60
    monkeypatch.setattr("tfwatch.checks.randint", lambda low, high: low)
    assert client.post("/api/apps", json={"url": URL}).status_code == 401
    register(client)
    with monkeypatch.context() as context:
        context.setattr("tfwatch.catalog.now", lambda: timestamp)
        created = client.post("/api/apps", json={"url": URL}).json()
    assert not created["duplicate"]
    assert client.post("/api/apps", json={"url": URL + "?share=1"}).json() == {**created, "duplicate": True}

    sessions = app.state.sessions
    code, lease = claim_invite(sessions, timestamp)
    assert not claim_invite(sessions, timestamp)
    assert not record_check(sessions, code, lease + 1, Observation("full"), timestamp)
    assert record_check(sessions, code, lease, Observation("open", "Sample Beta"), timestamp)
    for elapsed, status in [(300, "open"), (600, "unknown"), (1200, "open"), (1500, "closed")]:
        assert record_check(sessions, *claim_invite(sessions, timestamp + elapsed),
                            Observation(status), timestamp + elapsed)

    client.post("/api/auth/logout")
    matches = client.get("/api/apps", params={"q": "samPLE", "status": "closed"}).json()["items"]
    assert [item["id"] for item in matches] == [created["app_id"]]
    summary = client.get(f"/api/invites/{CODE}/timeline?days=all").json()
    assert summary["open_periods"] == 2
    assert summary["observed_open_seconds"] == 300
    assert [event["status"] for event in summary["events"]] == ["closed", "open", "unknown", "open"]


def test_many_submissions_are_staggered_and_claimed_when_due(app, client, monkeypatch):
    timestamp = now()
    offsets = iter(range(20, 4, -1))

    def draw_offset(low, high):
        assert (low, high) == (0, 30)
        return next(offsets)

    monkeypatch.setattr("tfwatch.catalog.now", lambda: timestamp)
    monkeypatch.setattr("tfwatch.checks.randint", draw_offset)
    register(client)
    codes = [f"Queue{i:03d}" for i in range(16)]
    for code in codes:
        response = client.post("/api/apps", json={"url": f"https://testflight.apple.com/join/{code}"})
        assert response.status_code == 202
        assert not response.json()["duplicate"]

    sessions = app.state.sessions
    assert claim_invite(sessions, timestamp + 4) is None
    code, lease = claim_invite(sessions, timestamp + 5)
    assert code == codes[-1]
    monkeypatch.setattr("tfwatch.checks.randint", lambda low, high: high)
    assert record_check(sessions, code, lease, Observation("open"), timestamp + 5)
    with sessions() as session:
        assert session.get(Invite, code).due_at == timestamp + 5 + 300 + 30
    assert claim_invite(sessions, timestamp + 5) is None
    assert claim_invite(sessions, timestamp + 6)[0] == codes[-2]


def test_time_gap_does_not_count_as_open_duration():
    checks = [SimpleNamespace(checked_at=t, status="open", interval=60) for t in (100, 300)]
    summary = summarize(checks, 0, 400)
    assert summary["open_periods"] == 2
    assert summary["average_open_seconds"] is None
