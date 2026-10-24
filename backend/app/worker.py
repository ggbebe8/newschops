import os, time, logging, random
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, text, delete
from .db import *
from .ranking import rank, utc
from .collector import collect
from .paper import collect_paper

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def tick():
    with engine.connect() as lock:
        if engine.dialect.name == "postgresql" and not lock.scalar(
            text("SELECT pg_try_advisory_lock(7123402)")
        ):
            return
        try:
            at = now()
            with Session.begin() as db:
                heartbeat = db.get(Job, "heartbeat")
                if not heartbeat:
                    db.add(Job(key="heartbeat", updated=at))
                else:
                    heartbeat.updated = at
                due = []
                for s in db.scalars(select(Source).where(Source.enabled == True)):
                    interval = min(
                        int(os.getenv("COLLECTION_INTERVAL_SECONDS", "900"))
                        * 2 ** min(s.failures, 4),
                        14400,
                    )
                    if (
                        float((s.capabilities or {}).get("retry_until", 0))
                        > at.timestamp()
                    ):
                        continue
                    interval *= 1 + random.random() * 0.1
                    manual = db.get(Job, "collect:" + s.id)
                    if (
                        manual
                        or s.last_attempt is None
                        or (at - utc(s.last_attempt)).total_seconds() >= interval
                    ):
                        due.append(s.id)
                        if manual:
                            db.delete(manual)
            with ThreadPoolExecutor(
                max_workers=min(
                    4, max(1, int(os.getenv("COLLECTION_CONCURRENCY", "3")))
                )
            ) as pool:
                list(pool.map(collect, due))
            if "donga" in due:
                collect_paper()
            at = now()
            with Session.begin() as db:
                correction = db.get(Job, "ranking-correction")
                if correction:
                    for period in ("current", "hour", "today", "week", "7days"):
                        data = rank(db, period, at)
                        data["correction_reason"] = correction.payload["reason"]
                        db.add(
                            Snapshot(
                                period=period,
                                slot=at.isoformat() + ":correction",
                                data=data,
                            )
                        )
                    db.delete(correction)
                for period in (
                    "current",
                    "hour",
                    "today",
                    "week",
                    "7days",
                    "daily-final",
                    "weekly-final",
                ):
                    local = at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Seoul"))
                    if (
                        period == "daily-final"
                        and local.hour == 0
                        and local.minute < 10
                    ):
                        continue
                    if (
                        period == "weekly-final"
                        and local.weekday() == 0
                        and local.hour == 0
                        and local.minute < 20
                    ):
                        continue
                    slot = at.strftime("%Y-%m-%dT%H")
                    if period == "daily-final":
                        slot = local.strftime("%Y-%m-%d")
                    if period == "weekly-final":
                        slot = (local - timedelta(days=local.weekday())).strftime(
                            "%Y-%m-%d"
                        )
                    if not db.scalar(
                        select(Snapshot).where(
                            Snapshot.period == period, Snapshot.slot == slot
                        )
                    ):
                        db.add(
                            Snapshot(
                                period=period, slot=slot, data=rank(db, period, at)
                            )
                        )
                db.execute(
                    delete(Audit).where(Audit.created < at - timedelta(days=365))
                )
                db.execute(
                    delete(AIResult).where(AIResult.created < at - timedelta(days=90))
                )
                db.execute(
                    delete(PaperEntry).where(
                        PaperEntry.observed < at - timedelta(days=30)
                    )
                )
                db.execute(delete(Login).where(Login.expires < at))
                db.execute(delete(Run).where(Run.created < at - timedelta(days=30)))
                db.execute(
                    delete(Snapshot).where(Snapshot.created < at - timedelta(days=90))
                )
                db.execute(
                    delete(Article).where(
                        Article.collected
                        < at
                        - timedelta(days=int(os.getenv("ARTICLE_RETENTION_DAYS", "90")))
                    )
                )
                db.execute(delete(Issue).where(~Issue.id.in_(select(Article.issue_id))))
        finally:
            if engine.dialect.name == "postgresql":
                lock.execute(text("SELECT pg_advisory_unlock(7123402)"))
                lock.commit()


if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception as e:
            logging.error('{"worker_error":"%s"}', type(e).__name__)
        time.sleep(20 + random.random() * 5)
