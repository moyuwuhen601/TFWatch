import logging
import secrets
import smtplib
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .db import now
from .mail import send_mail
from .models import AccountToken, SessionToken, User
from .security import (
    COOKIE, SESSION_LIFETIME, current_user, db, digest, dummy_password,
    limit, passwords, site, user_required, verify_password,
)

router = APIRouter()
logger = logging.getLogger(__name__)
Password = Annotated[str, Field(min_length=10, max_length=128)]
TokenString = Annotated[str, Field(min_length=32, max_length=128)]


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Registration(Credentials):
    password: Password


class EmailInput(BaseModel):
    email: EmailStr


class TokenInput(BaseModel):
    token: TokenString


class ResetInput(TokenInput):
    password: Password


class ChangeInput(BaseModel):
    current_password: str = Field(max_length=128)
    password: Password


class Preferences(BaseModel):
    notify_mode: Literal["open", "changes"]


def profile(user):
    return {
        "id": user.id, "email": user.email, "is_admin": user.is_admin,
        "verified": user.verified, "notify_mode": user.notify_mode,
    }


def sign_in(request, response, session, user):
    raw = secrets.token_urlsafe(32)
    current = request.cookies.get(COOKIE, "")
    if current and len(current) <= 128:
        session.execute(delete(SessionToken).where(SessionToken.digest == digest(current)))
    session.add(SessionToken(digest=digest(raw), user_id=user.id, expires=now() + SESSION_LIFETIME))
    session.commit()
    response.set_cookie(COOKIE, raw, max_age=SESSION_LIFETIME, httponly=True,
                        secure=request.app.state.config.secure_cookie, samesite="lax")
    return profile(user)


@router.get("/session")
def session_info(request: Request, user=Depends(current_user), session=Depends(db)):
    settings = site(session)
    config = request.app.state.config
    return {
        "user": profile(user) if user else None, "registration": settings.registration,
        "anonymous": settings.anonymous, "mail_available": bool(config.smtp_host and config.smtp_from),
        "source_url": "/api/source" if (
            config.source_url.startswith(("https://", "http://"))
            or (config.static_dir / "tfwatch-source.tar.gz").is_file()
        ) else None,
    }


@router.post("/auth/register", status_code=201)
def register(data: Registration, request: Request, response: Response, session=Depends(db)):
    limit(request, "register", 8, 3600)
    if not site(session).registration:
        raise HTTPException(403, "注册已关闭")
    user = User(email=data.email.lower(), password_hash=passwords.hash(data.password))
    session.add(user)
    try:
        session.flush()
        return sign_in(request, response, session, user)
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "无法使用此邮箱注册") from None


@router.post("/auth/login")
def login(data: Credentials, request: Request, response: Response, session=Depends(db)):
    limit(request, "login", 20, 300)
    email = data.email.lower()
    limit(request, "login-account", 12, 300, email)
    user = session.scalar(select(User).where(User.email == email))
    valid = verify_password(user.password_hash if user else dummy_password, data.password)
    if not user or not user.active or not valid:
        raise HTTPException(401, "邮箱或密码无效")
    if passwords.check_needs_rehash(user.password_hash):
        user.password_hash = passwords.hash(data.password)
    return sign_in(request, response, session, user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session=Depends(db)):
    raw = request.cookies.get(COOKIE, "")
    if raw and len(raw) <= 128:
        session.execute(delete(SessionToken).where(SessionToken.digest == digest(raw)))
        session.commit()
    response.delete_cookie(COOKIE, secure=request.app.state.config.secure_cookie, httponly=True)


def send_token(config, session, user, purpose):
    raw = secrets.token_urlsafe(32)
    session.add(AccountToken(digest=digest(raw), user_id=user.id,
                             purpose=purpose, expires=now() + 1800))
    session.commit()
    path = "verify-email" if purpose == "verify" else "reset-password"
    subject = "验证 TFWatch 邮箱" if purpose == "verify" else "重置 TFWatch 密码"
    send_mail(config, user.email, subject,
              f"打开以下链接完成操作。链接 30 分钟内有效。\n\n{config.public_url}/{path}#token={raw}")


@router.post("/auth/verify-request", status_code=204)
def verify_request(request: Request, user=Depends(user_required), session=Depends(db)):
    limit(request, "verify-ip", 20, 3600)
    limit(request, "verify-user", 3, 3600, user.id)
    if user.verified:
        return
    try:
        send_token(request.app.state.config, session, user, "verify")
    except (ValueError, OSError, smtplib.SMTPException):
        raise HTTPException(503, "暂时无法发送验证邮件") from None


def send_reset(config, sessions, email):
    with sessions() as session:
        user = session.scalar(select(User).where(User.email == email, User.active, User.verified))
        if user:
            try:
                send_token(config, session, user, "reset")
            except (ValueError, OSError, smtplib.SMTPException):
                logger.warning("Password reset mail could not be delivered")


@router.post("/auth/reset-request", status_code=204)
def reset_request(data: EmailInput, request: Request, background_tasks: BackgroundTasks):
    limit(request, "reset", 10, 3600)
    email = data.email.lower()
    limit(request, "reset-account", 3, 3600, email)
    background_tasks.add_task(send_reset, request.app.state.config, request.app.state.sessions, email)


def consume_token(session, token, purpose):
    user_id = session.scalar(
        delete(AccountToken).where(AccountToken.digest == digest(token),
                                   AccountToken.purpose == purpose, AccountToken.expires > now())
        .returning(AccountToken.user_id)
    )
    user = session.get(User, user_id) if user_id is not None else None
    if user is None or not user.active:
        raise HTTPException(400, "链接无效或已过期")
    return user


@router.post("/auth/verify-email", status_code=204)
def verify_email(data: TokenInput, request: Request, session=Depends(db)):
    limit(request, "consume-verification", 20, 300)
    user = consume_token(session, data.token, "verify")
    user.verified = True
    session.commit()


def invalidate_sessions(session, user):
    session.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    session.execute(delete(AccountToken).where(AccountToken.user_id == user.id))


@router.post("/auth/reset-password", status_code=204)
def reset_password(data: ResetInput, request: Request, session=Depends(db)):
    limit(request, "consume-reset", 12, 300)
    user = consume_token(session, data.token, "reset")
    user.password_hash = passwords.hash(data.password)
    invalidate_sessions(session, user)
    session.commit()


@router.post("/account/password")
def change_password(data: ChangeInput, request: Request, response: Response,
                    user=Depends(user_required), session=Depends(db)):
    limit(request, "change-password", 10, 300, user.id)
    if not verify_password(user.password_hash, data.current_password):
        raise HTTPException(400, "当前密码错误")
    user.password_hash = passwords.hash(data.password)
    invalidate_sessions(session, user)
    return sign_in(request, response, session, user)


@router.patch("/account")
def preferences(data: Preferences, user=Depends(user_required), session=Depends(db)):
    user.notify_mode = data.notify_mode
    session.commit()
    return profile(user)

