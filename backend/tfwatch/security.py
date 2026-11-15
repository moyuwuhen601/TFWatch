import hashlib
import secrets
import time
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import now
from .models import SessionToken, Settings, User

COOKIE = "tfwatch_session"
SESSION_LIFETIME = 14 * 86400
passwords = PasswordHasher()
dummy_password = passwords.hash(secrets.token_urlsafe())


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(encoded, password):
    try:
        return passwords.verify(encoded, password)
    except VerifyMismatchError:
        return False


def db(request: Request):
    with request.app.state.sessions() as session:
        yield session


def site(session):
    settings = session.get(Settings, 1)
    if settings is None:
        raise HTTPException(503, "数据库尚未初始化")
    return settings


def current_user(request: Request, session=Depends(db)):
    raw = request.cookies.get(COOKIE, "")
    if not raw or len(raw) > 128:
        return None
    return session.scalar(
        select(User).join(SessionToken, SessionToken.user_id == User.id)
        .where(SessionToken.digest == digest(raw), SessionToken.expires > now(), User.active)
    )


def user_required(user=Depends(current_user)):
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def admin_required(user=Depends(user_required)):
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user


def browsing(user=Depends(current_user), session=Depends(db)):
    if user is None and not site(session).anonymous:
        raise HTTPException(401, "该站点仅允许登录后浏览")
    return user


class RateLimiter:
    def __init__(self):
        self.entries = {}
        self.lock = Lock()
        self.last_cleanup = 0

    def check(self, key, limit, window):
        timestamp = time.monotonic()
        with self.lock:
            if timestamp - self.last_cleanup >= 60:
                self.entries = {k: v for k, v in self.entries.items() if v[1] > timestamp}
                self.last_cleanup = timestamp
            if len(self.entries) >= 10000 and key not in self.entries:
                raise HTTPException(429, "请求过多，请稍后重试")
            count, expiry = self.entries.get(key, (0, timestamp + window))
            if expiry <= timestamp:
                count, expiry = 0, timestamp + window
            if count >= limit:
                raise HTTPException(429, "请求过多，请稍后重试")
            self.entries[key] = count + 1, expiry


def limit(request, action, count, window, subject=None):
    address = request.client.host if request.client else "local"
    request.app.state.limiter.check((action, address if subject is None else subject), count, window)
