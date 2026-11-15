from random import randint

from sqlalchemy import select, update

from .models import App, CheckLog, Invite, Settings, StatusEvent


def first_check_due(timestamp):
    return timestamp + randint(0, 30)


def claim_invite(sessions, timestamp):
    due = (Invite.due_at <= timestamp, Invite.lease_until <= timestamp)
    with sessions.begin() as session:
        code = session.scalar(select(Invite.code).where(*due).order_by(Invite.due_at, Invite.code).limit(1))
        if code is None:
            return None
        lease = timestamp + 120
        claim = session.execute(update(Invite).where(Invite.code == code, *due).values(lease_until=lease))
        if claim.rowcount:
            return code, lease
    return None


def record_check(sessions, code, lease, observation, timestamp, enqueue=None):
    with sessions.begin() as session:
        guard = session.execute(update(Invite).where(
            Invite.code == code, Invite.lease_until == lease,
        ).values(lease_until=0))
        if not guard.rowcount:
            return False
        invite = session.get(Invite, code)

        interval = session.get(Settings, 1).interval
        status = observation.status
        invite.failures = min(invite.failures + 1, 6) if status == "unknown" else 0
        if invite.failures:
            delay = min(interval * (2 ** invite.failures), 3600)
        else:
            delay = interval + randint(0, min(interval // 10, 30))
        invite.due_at = timestamp + delay
        invite.lease_until = 0
        session.add(CheckLog(code=code, checked_at=timestamp, status=status, interval=interval))

        if invite.checked_at is None or invite.status != status:
            event = StatusEvent(code=code, checked_at=timestamp, status=status,
                                previous=invite.status if invite.checked_at is not None else None)
            session.add(event)
            if enqueue and status != "unknown" and status != invite.last_known:
                session.flush()
                enqueue(session, event, invite.last_known)

        invite.checked_at = timestamp
        invite.status = status
        if status != "unknown":
            invite.last_known = status
        app = session.get(App, invite.app_id)
        if observation.name and app.name == code:
            app.name = observation.name
        if observation.icon and not app.icon:
            app.icon = observation.icon
    return True

