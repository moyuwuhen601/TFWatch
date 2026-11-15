import logging
import signal
from threading import Event, Thread

import httpx
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from .checks import claim_invite, record_check
from .config import Config
from .db import database, now
from .models import AccountToken, SessionToken
from .notifications import enqueue, process_delivery
from .testflight import check

logger = logging.getLogger(__name__)


def watch_invites(sessions, stop):
    last_cleanup = 0
    with httpx.Client(timeout=8, follow_redirects=False, trust_env=False, headers={
        "User-Agent": "TFWatch/0.1 (+self-hosted TestFlight monitor)", "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }) as http:
        while not stop.is_set():
            try:
                timestamp = now()
                if timestamp - last_cleanup >= 3600:
                    with sessions.begin() as session:
                        for table in (AccountToken, SessionToken):
                            session.execute(delete(table).where(table.expires <= timestamp))
                    last_cleanup = timestamp
                job = claim_invite(sessions, timestamp)
                if job:
                    code, lease = job
                    record_check(sessions, code, lease, check(http, code), now(), enqueue)
                stop.wait(1 if job else 3)
            except SQLAlchemyError:
                logger.error("Check database operation failed; retrying")
                stop.wait(10)


def send_notifications(sessions, config, stop):
    while not stop.is_set():
        try:
            processed = process_delivery(sessions, config, now())
            stop.wait(0.1 if processed else 3)
        except SQLAlchemyError:
            logger.error("Delivery database operation failed; retrying")
            stop.wait(10)


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    config = Config()
    config.cipher()
    sessions = database(config.database_url)
    sender = Thread(target=send_notifications, args=(sessions, config, stop), daemon=True)
    sender.start()
    try:
        watch_invites(sessions, stop)
    finally:
        stop.set()
        sender.join(timeout=8)


if __name__ == "__main__":
    run()
