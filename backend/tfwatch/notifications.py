import http.client
import json
import logging
import re
import smtplib
from typing import Literal

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from .db import now
from .mail import send_mail
from .models import App, Channel, Delivery, Invite, StatusEvent, Subscription, User
from .outbound import https_target, post_json
from .security import db, limit, user_required
from .testflight import invite_url

router = APIRouter()
logger = logging.getLogger(__name__)
Kind = Literal["email", "telegram", "ntfy", "webhook"]
SEND_ERRORS = (ValueError, TypeError, OSError, InvalidToken, http.client.HTTPException, smtplib.SMTPException)
STATUS_LABELS = {"open": "开放", "full": "满员", "closed": "关闭"}


class ChannelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=60)
    enabled: bool = True
    config: dict[str, str] | None = None


class ChannelCreate(ChannelInput):
    kind: Kind


def clean_config(kind, values):
    allowed = {
        "email": set(), "telegram": {"bot_token", "chat_id"},
        "ntfy": {"url", "topic", "token"}, "webhook": {"url", "token"},
    }[kind]
    if values.keys() - allowed:
        raise ValueError("渠道配置字段不正确")
    if kind == "telegram":
        if not re.fullmatch(r"\d{3,20}:[A-Za-z0-9_-]{20,100}", values.get("bot_token", "")):
            raise ValueError("Telegram Bot Token 格式无效")
        if not re.fullmatch(r"-?\d{1,25}|@[A-Za-z0-9_]{5,32}", values.get("chat_id", "")):
            raise ValueError("Telegram Chat ID 格式无效")
    if kind in ("ntfy", "webhook"):
        _, _, _, query = https_target(values.get("url", ""))
        if kind == "ntfy":
            if query or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", values.get("topic", "")):
                raise ValueError("请输入有效的 ntfy 服务地址和主题")
        if not re.fullmatch(r"[!-~]{0,512}", values.get("token", "")):
            raise ValueError("令牌格式无效")
    return values


def encrypt(config, kind, values):
    try:
        payload = json.dumps(clean_config(kind, values)).encode()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    try:
        return config.cipher().encrypt(payload)
    except ValueError:
        raise HTTPException(503, "站点尚未配置通知加密密钥") from None


def channel_view(channel):
    return {"id": channel.id, "kind": channel.kind, "label": channel.label, "enabled": channel.enabled}


def own_channel(session, user, channel_id, lock=False):
    query = select(Channel).where(Channel.id == channel_id, Channel.user_id == user.id)
    channel = session.scalar(query.with_for_update() if lock else query)
    if channel is None:
        raise HTTPException(404, "未找到通知渠道")
    return channel


def cancel_pending(session, *conditions):
    session.execute(update(Delivery).where(Delivery.state == "pending", *conditions).values(state="cancelled"))


@router.put("/invites/{code}/follow")
def follow(code: str, request: Request, user=Depends(user_required), session=Depends(db)):
    limit(request, "follow", 120, 3600, user.id)
    invite = session.get(Invite, code)
    if invite is None:
        raise HTTPException(404, "未找到邀请")
    if session.get(Subscription, (user.id, code)) is None:
        session.add(Subscription(user_id=user.id, code=code))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.get(Subscription, (user.id, code)) is None:
                raise HTTPException(409, "邀请已更新，请重试") from None
    return {"followed": True, "status": invite.status}


@router.delete("/invites/{code}/follow", status_code=204)
def unfollow(code: str, user=Depends(user_required), session=Depends(db)):
    session.execute(delete(Subscription).where(Subscription.user_id == user.id, Subscription.code == code))
    cancel_pending(session,
                   Delivery.channel_id.in_(select(Channel.id).where(Channel.user_id == user.id)),
                   Delivery.event_id.in_(select(StatusEvent.id).where(StatusEvent.code == code)))
    session.commit()


@router.get("/channels")
def channels(user=Depends(user_required), session=Depends(db)):
    return [channel_view(channel) for channel in session.scalars(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    )]


def check_email(config, user):
    if not user.verified:
        raise HTTPException(422, "请先验证你的邮箱")
    if not config.smtp_host or not config.smtp_from:
        raise HTTPException(503, "站点尚未配置 SMTP")


@router.post("/channels", status_code=201)
def add_channel(data: ChannelCreate, request: Request, user=Depends(user_required), session=Depends(db)):
    limit(request, "add-channel", 15, 3600, user.id)
    if session.scalar(select(func.count()).select_from(Channel).where(Channel.user_id == user.id)) >= 20:
        raise HTTPException(409, "已达到通知渠道数量上限")
    config = request.app.state.config
    if data.kind == "email":
        check_email(config, user)
    channel = Channel(user_id=user.id, kind=data.kind, label=data.label, enabled=data.enabled,
                      encrypted=encrypt(config, data.kind, data.config or {}))
    session.add(channel)
    session.commit()
    return channel_view(channel)


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, data: ChannelInput, request: Request,
                   user=Depends(user_required), session=Depends(db)):
    channel = own_channel(session, user, channel_id, lock=True)
    config = request.app.state.config
    if data.enabled and channel.kind == "email":
        check_email(config, user)
    channel.label = data.label
    channel.enabled = data.enabled
    if data.config is not None:
        channel.encrypted = encrypt(config, channel.kind, data.config)
    if not data.enabled or data.config is not None:
        cancel_pending(session, Delivery.channel_id == channel.id)
    session.commit()
    return channel_view(channel)


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int, user=Depends(user_required), session=Depends(db)):
    session.delete(own_channel(session, user, channel_id, lock=True))
    session.commit()


@router.post("/channels/{channel_id}/test", status_code=204)
def test_channel(channel_id: int, request: Request, user=Depends(user_required), session=Depends(db)):
    limit(request, "test-channel", 8, 3600, user.id)
    channel = own_channel(session, user, channel_id)
    config = request.app.state.config
    if channel.kind == "email":
        check_email(config, user)
    session.close()
    try:
        deliver(config, user, channel, {"event": "test", "title": "TFWatch 测试通知",
                                       "message": "此通知用于检查渠道配置。"})
    except SEND_ERRORS:
        raise HTTPException(502, "测试通知投递失败，请检查渠道设置") from None


def enqueue(session, event, previous):
    if previous is None and event.status != "open":
        return
    users = (User.notify_mode == "changes") | (event.status == "open")
    channel_ids = session.scalars(
        select(Channel.id).join(User, Channel.user_id == User.id)
        .join(Subscription, Subscription.user_id == User.id)
        .where(Subscription.code == event.code, Channel.enabled, User.active, users)
    )
    session.add_all([Delivery(event_id=event.id, channel_id=channel_id) for channel_id in channel_ids])


def deliver(config, user, channel, payload, key=None):
    settings = json.loads(config.cipher().decrypt(channel.encrypted))
    message = payload["message"] + ("\n" + payload["url"] if "url" in payload else "")
    if channel.kind == "email":
        if not user.verified:
            raise ValueError("邮箱未验证")
        send_mail(config, user.email, payload["title"], message,
                  message_id=f"<{key}@tfwatch>" if key else None)
    elif channel.kind == "telegram":
        post_json(f"https://api.telegram.org/bot{settings['bot_token']}/sendMessage",
                  {"chat_id": settings["chat_id"], "text": payload["title"] + "\n" + message})
    else:
        headers = {"Authorization": "Bearer " + settings["token"]} if settings.get("token") else {}
        if key:
            headers["Idempotency-Key"] = key
        if channel.kind == "ntfy":
            post_json(settings["url"], {"topic": settings["topic"], "title": payload["title"],
                                        "message": message}, headers)
        else:
            post_json(settings["url"], payload, headers)


def process_delivery(sessions, config, timestamp):
    due = (Delivery.state == "pending", Delivery.lease_until <= timestamp, Delivery.due_at <= timestamp)
    with sessions.begin() as session:
        delivery_id = session.scalar(select(Delivery.id).where(*due).order_by(Delivery.due_at, Delivery.id).limit(1))
        if delivery_id is None:
            return False
        lease = timestamp + 120
        claim = session.execute(update(Delivery).where(Delivery.id == delivery_id, *due).values(lease_until=lease))
        if not claim.rowcount:
            return False

    with sessions() as session:
        record = session.execute(
            select(Delivery, Channel, User, StatusEvent, App).join(Channel, Channel.id == Delivery.channel_id)
            .join(User, User.id == Channel.user_id).join(StatusEvent, StatusEvent.id == Delivery.event_id)
            .join(Invite, Invite.code == StatusEvent.code).join(App, App.id == Invite.app_id)
            .where(Delivery.id == delivery_id, Delivery.lease_until == lease)
        ).one_or_none()
        if record is None:
            return True
        delivery, channel, user, event, app = record
        eligible = (delivery.state == "pending" and channel.enabled and user.active
                    and (user.notify_mode == "changes" or event.status == "open")
                    and session.get(Subscription, (user.id, event.code)) is not None)

    attempts = delivery.attempts + 1
    state = "cancelled"
    if eligible:
        payload = {
            "event": "status_changed", "code": event.code, "status": event.status, "name": app.name,
            "checked_at": event.checked_at, "url": invite_url(event.code),
            "title": "TFWatch · " + " ".join(app.name.split()),
            "message": f"检测到 TestFlight 状态为「{STATUS_LABELS[event.status]}」。",
        }
        try:
            deliver(config, user, channel, payload, f"tfwatch-{delivery.id}-{event.id}")
            state = "sent"
        except SEND_ERRORS:
            state = "failed" if attempts >= 5 else "pending"
            logger.warning("Notification delivery %s attempt %s failed", delivery_id, attempts)

    with sessions.begin() as session:
        session.execute(update(Delivery).where(
            Delivery.id == delivery_id, Delivery.lease_until == lease, Delivery.state == "pending",
        ).values(state=state, attempts=attempts, lease_until=0, due_at=timestamp + 30 * 2 ** attempts))
    return True

