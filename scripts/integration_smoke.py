"""Run inside app container against its real HTTP server and PostgreSQL."""

import os, secrets, time, json
import httpx
from sqlalchemy import select, delete, text, func
from backend.app.db import Session, User, Login, Audit, Article, Issue, Snapshot, engine
from backend.app.ranking import rank
from backend.app.worker import tick
from backend.app.db import now

origin = os.environ["APP_ORIGIN"]
with (
    httpx.Client(base_url="http://localhost:8080", headers={"Origin": origin}) as admin,
    httpx.Client(
        base_url="http://localhost:8080", headers={"Origin": origin}
    ) as reader,
):
    assert reader.get("/api/admin/status").status_code == 401
    login = admin.post(
        "/api/login",
        json={
            "username": os.environ.get("ADMIN_USERNAME", "admin"),
            "password": os.environ["ADMIN_PASSWORD"],
        },
    )
    assert login.status_code == 200, login.status_code
    admin.headers["X-CSRF-Token"] = login.json()["csrf"]
    username = "smoke-" + secrets.token_hex(6)
    password = secrets.token_hex(16)
    try:
        assert (
            admin.post(
                "/api/admin/users", json={"username": username, "password": password}
            ).status_code
            == 200
        )
        lr = reader.post(
            "/api/login", json={"username": username, "password": password}
        )
        assert lr.status_code == 200
        reader.headers["X-CSRF-Token"] = lr.json()["csrf"]
        assert reader.get("/api/admin/status").status_code == 403
        assert (
            reader.put(
                "/api/preferences", json={"keywords": ["integration-private"]}
            ).status_code
            == 200
        )
        assert admin.get("/api/me").json()["preferences"].get("keywords") != [
            "integration-private"
        ]
        assert reader.post("/api/logout").status_code == 200
        assert reader.get("/api/me").status_code == 401
        assert admin.get("/api/rankings").status_code == 200
        status = admin.get("/api/admin/status").json()
        print("HTTP 로그인/권한/사용자 격리/로그아웃: PASS")
        print(
            "소스 상태:",
            json.dumps(
                {s["name"]: s["state"] for s in status["sources"]}, ensure_ascii=False
            ),
        )
    finally:
        with Session.begin() as db:
            u = db.scalar(select(User).where(User.username == username))
            if u:
                db.delete(u)
        admin.post("/api/logout")
with engine.connect() as lock:
    assert lock.scalar(text("SELECT pg_try_advisory_lock(7123402)"))
    started = time.monotonic()
    tick()
    assert time.monotonic() - started < 3
    lock.execute(text("SELECT pg_advisory_unlock(7123402)"))
    lock.commit()
print("PostgreSQL worker 중복 잠금: PASS")
with Session() as db:
    started = time.perf_counter()
    result = rank(db, "current", now())
    elapsed = (time.perf_counter() - started) * 1000
    print(
        json.dumps(
            {
                "articles": db.scalar(select(func.count()).select_from(Article)),
                "issues": db.scalar(select(func.count()).select_from(Issue)),
                "snapshots": db.scalar(select(func.count()).select_from(Snapshot)),
                "current_ranking_ms": round(elapsed, 2),
                "selected": len(result["entries"]),
                "ai_calls": 0,
            },
            ensure_ascii=False,
        )
    )
