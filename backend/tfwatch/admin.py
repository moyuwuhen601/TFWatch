from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func, select, update

from .accounts import invalidate_sessions
from .catalog import Name, app_view
from .db import now
from .models import App, Channel, Delivery, Invite, User
from .notifications import cancel_pending
from .security import admin_required, db, site

router = APIRouter(prefix="/admin", dependencies=[Depends(admin_required)])


class SiteInput(BaseModel):
    registration: bool
    anonymous: bool
    interval: int = Field(ge=60, le=3600)


class UserInput(BaseModel):
    active: bool


class AppInput(BaseModel):
    name: Name
    aliases: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


def user_view(user):
    return {"id": user.id, "email": user.email, "active": user.active,
            "is_admin": user.is_admin, "verified": user.verified}


def settings_view(settings):
    return {"registration": settings.registration, "anonymous": settings.anonymous, "interval": settings.interval}


@router.get("/settings")
def get_settings(session=Depends(db)):
    return settings_view(site(session))


@router.put("/settings")
def put_settings(data: SiteInput, session=Depends(db)):
    settings = site(session)
    if data.interval < settings.interval:
        deadline = now() + data.interval
        session.execute(update(Invite).where(Invite.due_at > deadline, Invite.failures == 0).values(due_at=deadline))
    for key, value in data.model_dump().items():
        setattr(settings, key, value)
    session.commit()
    return settings_view(settings)


@router.get("/users")
def users(q: str = Query("", max_length=120), page: int = Query(1, ge=1, le=100000), session=Depends(db)):
    query = select(User).where(func.lower(User.email).contains(q.lower().strip(), autoescape=True))
    rows = session.scalars(query.order_by(User.id).offset((page - 1) * 30).limit(31)).all()
    return {"items": [user_view(user) for user in rows[:30]], "has_more": len(rows) > 30}


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserInput, session=Depends(db)):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "未找到账号")
    if user.is_admin:
        raise HTTPException(409, "管理员账号通过服务器管理")
    user.active = data.active
    if not data.active:
        invalidate_sessions(session, user)
        cancel_pending(session, Delivery.channel_id.in_(select(Channel.id).where(Channel.user_id == user_id)))
    session.commit()
    return user_view(user)


@router.get("/apps/{app_id}")
def get_app(app_id: int, session=Depends(db)):
    app = session.get(App, app_id)
    if app is None:
        raise HTTPException(404, "未找到软件")
    return app_view(app, aliases=app.aliases)


@router.patch("/apps/{app_id}")
def update_app(app_id: int, data: AppInput, session=Depends(db)):
    app = session.get(App, app_id)
    if app is None:
        raise HTTPException(404, "未找到软件")
    for key, value in data.model_dump().items():
        setattr(app, key, value)
    session.commit()
    return app_view(app, aliases=app.aliases)


@router.delete("/apps/{app_id}", status_code=204)
def delete_app(app_id: int, session=Depends(db)):
    session.execute(delete(App).where(App.id == app_id))
    session.commit()


@router.delete("/invites/{code}", status_code=204)
def delete_invite(code: str, session=Depends(db)):
    invite = session.get(Invite, code)
    if invite:
        app_id = invite.app_id
        session.delete(invite)
        session.flush()
        if session.scalar(select(Invite.code).where(Invite.app_id == app_id).limit(1)) is None:
            session.execute(delete(App).where(App.id == app_id))
        session.commit()
