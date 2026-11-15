from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError

from .db import now
from .models import App, CheckLog, Invite, StatusEvent, Subscription
from .security import browsing, db, limit, user_required
from .testflight import invite_code, invite_url
from .timeline import summarize

router = APIRouter()
Status = Literal["open", "full", "closed", "unknown"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]


class Submission(BaseModel):
    url: str = Field(max_length=1000)
    name: Name | None = None
    app_id: int | None = Field(default=None, ge=1)


def app_view(app, **fields):
    return {"id": app.id, "name": app.name, "icon": app.icon,
            "description": app.description, **fields}


def invite_view(invite, followed=False):
    return {
        "code": invite.code, "url": invite_url(invite.code), "status": invite.status,
        "checked_at": invite.checked_at, "followed": followed,
    }


def app_status():
    def has(states):
        return select(Invite.code).where(Invite.app_id == App.id, Invite.status.in_(states)).exists()

    return case(
        (has(["open"]), "open"),
        (has(["full"]), "full"),
        (has(["unknown"]), "unknown"),
        else_="closed",
    )


@router.get("/apps")
def list_apps(q: str = Query("", max_length=120), status: Status | None = None,
              page: int = Query(1, ge=1, le=100000), followed: bool = False,
              user=Depends(browsing), session=Depends(db)):
    state = app_status()
    query = select(App, state.label("status")).where(
        select(Invite.code).where(Invite.app_id == App.id).exists()
    )
    if q.strip():
        term = q.strip().lower()
        match = select(Invite.code).where(Invite.app_id == App.id,
                                         func.lower(Invite.code).contains(term, autoescape=True)).exists()
        query = query.where(or_(func.lower(App.name).contains(term, autoescape=True),
                                func.lower(App.aliases).contains(term, autoescape=True), match))
    if status:
        query = query.where(state == status)
    if followed:
        if user is None:
            raise HTTPException(401, "请先登录")
        query = query.where(
            select(Subscription.code).join(Invite, Invite.code == Subscription.code)
            .where(Subscription.user_id == user.id, Invite.app_id == App.id).exists()
        )
    query = query.order_by(func.lower(App.name), App.id).offset((page - 1) * 24).limit(25)
    rows = session.execute(query).all()
    ids = [app.id for app, _ in rows[:24]]
    invites = session.scalars(select(Invite).where(Invite.app_id.in_(ids)).order_by(Invite.code)).all()
    subscriptions = set()
    if user and invites:
        subscriptions = set(session.scalars(select(Subscription.code).where(
            Subscription.user_id == user.id, Subscription.code.in_([item.code for item in invites])
        )))
    by_app = {app_id: [] for app_id in ids}
    for invite in invites:
        by_app[invite.app_id].append(invite_view(invite, invite.code in subscriptions))
    return {"items": [app_view(app, status=state, invites=by_app[app.id]) for app, state in rows[:24]],
            "has_more": len(rows) > 24}


@router.get("/apps/{app_id}")
def get_app(app_id: int, user=Depends(browsing), session=Depends(db)):
    app = session.get(App, app_id)
    if app is None:
        raise HTTPException(404, "未找到软件")
    invites = session.scalars(select(Invite).where(Invite.app_id == app_id).order_by(Invite.code))
    entries = [invite_view(invite, bool(user and session.get(Subscription, (user.id, invite.code))))
               for invite in invites]
    return app_view(app, invites=entries)


@router.post("/apps", status_code=202)
def submit(data: Submission, request: Request, user=Depends(user_required), session=Depends(db)):
    try:
        code = invite_code(data.url)
    except ValueError:
        raise HTTPException(422, "请输入有效的 TestFlight 公开邀请链接") from None

    existing = session.get(Invite, code)
    if existing:
        return {"app_id": existing.app_id, "code": code, "duplicate": True}

    limit(request, "submission", 12, 3600, user.id)
    if data.app_id:
        app = session.get(App, data.app_id)
        if app is None:
            raise HTTPException(404, "未找到软件")
    else:
        app = App(name=data.name or code)
        session.add(app)
    try:
        session.flush()
        invite = Invite(code=code, app_id=app.id)
        session.add(invite)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.get(Invite, code)
        if existing:
            return {"app_id": existing.app_id, "code": code, "duplicate": True}
        raise HTTPException(409, "软件库已更新，请重试") from None
    return {"app_id": app.id, "code": code, "duplicate": False}


@router.get("/invites/{code}/timeline")
def timeline(code: str, days: Literal["7", "30", "90", "all"] = "30",
             before: int | None = Query(None, ge=1), _=Depends(browsing), session=Depends(db)):
    invite = session.get(Invite, code)
    if invite is None:
        raise HTTPException(404, "未找到邀请")
    timestamp = now()
    start = 0 if days == "all" else timestamp - int(days) * 86400
    events_query = select(StatusEvent).where(StatusEvent.code == code, StatusEvent.checked_at >= start)
    if before is not None:
        events_query = events_query.where(StatusEvent.id < before)
    events = session.scalars(events_query.order_by(StatusEvent.id.desc()).limit(51)).all()
    paging = {
        "events": [{"id": event.id, "checked_at": event.checked_at, "status": event.status,
                    "previous": event.previous} for event in events[:50]],
        "next_before": events[49].id if len(events) > 50 else None,
    }
    if before is not None:
        return paging

    if days == "all":
        first = session.scalar(select(func.min(CheckLog.checked_at)).where(CheckLog.code == code))
        start = first if first is not None else timestamp
    query = select(CheckLog).where(CheckLog.code == code, CheckLog.checked_at >= start,
                                   CheckLog.checked_at <= timestamp).order_by(CheckLog.checked_at, CheckLog.id)
    summary = summarize(session.scalars(query.execution_options(yield_per=1000)), start, timestamp)
    return {**summary, **paging}
