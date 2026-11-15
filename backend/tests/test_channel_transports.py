import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from tfwatch.config import Config
from tfwatch.notifications import deliver

PAYLOAD = {"title": "TFWatch · 样本", "message": "检测到开放", "url": "https://testflight.apple.com/join/aBcD1234"}


@pytest.mark.parametrize(("kind", "settings", "address", "field"), [
    ("telegram", {"bot_token": "1234:testtoken01234567890123", "chat_id": "-1234"},
     "https://api.telegram.org/bot1234:testtoken01234567890123/sendMessage", "chat_id"),
    ("ntfy", {"url": "https://ntfy.example.org", "topic": "tfwatch", "token": "example"},
     "https://ntfy.example.org", "topic"),
    ("webhook", {"url": "https://hooks.example.org/notify", "token": "example"},
     "https://hooks.example.org/notify", "url"),
])
def test_json_channel_payloads(monkeypatch, kind, settings, address, field):
    config = Config(encryption_key=Fernet.generate_key().decode())
    channel = SimpleNamespace(kind=kind, encrypted=config.cipher().encrypt(json.dumps(settings).encode()))
    requests = []
    monkeypatch.setattr("tfwatch.notifications.post_json", lambda *args: requests.append(args))
    deliver(config, None, channel, PAYLOAD, "delivery-1")
    assert requests[0][0] == address
    assert field in requests[0][1]
    if kind != "telegram":
        assert requests[0][2] == {"Authorization": "Bearer example", "Idempotency-Key": "delivery-1"}


def test_email_uses_verified_account_and_stable_message_id(monkeypatch):
    config = Config(encryption_key=Fernet.generate_key().decode())
    channel = SimpleNamespace(kind="email", encrypted=config.cipher().encrypt(b"{}"))
    user = SimpleNamespace(verified=False, email="user@example.org")
    requests = []
    monkeypatch.setattr("tfwatch.notifications.send_mail", lambda *args, **kwargs: requests.append((args, kwargs)))
    with pytest.raises(ValueError):
        deliver(config, user, channel, PAYLOAD, "delivery-1")
    assert requests == []
    user.verified = True
    deliver(config, user, channel, PAYLOAD, "delivery-1")
    assert requests == [((config, user.email, PAYLOAD["title"], PAYLOAD["message"] + "\n" + PAYLOAD["url"]),
                         {"message_id": "<delivery-1@tfwatch>"})]
