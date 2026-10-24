import os, secrets, time
from datetime import timedelta
from pathlib import Path
from collections import defaultdict
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from .db import *
from .security import digest
from .ranking import utc
from .paper import article_key

app = FastAPI(title="newschops", docs_url=None, redoc_url=None, openapi_url=None)
ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:38475").rstrip("/")
ph = PasswordHasher()
attempts = defaultdict(list)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class Preferences(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=50)
    excluded: list[str] = Field(default_factory=list, max_length=50)
    sources: list[str] = Field(default_factory=list, max_length=10)
    excluded_categories: list[str] = Field(default_factory=list, max_length=10)
    format: str = "short"


class IssueState(BaseModel):
    saved: bool = False
    read: bool = False
    hidden: bool = False
    feedback: str = Field(default="", max_length=200)


class NewUser(Credentials):
    admin: bool = False


@app.middleware("http")
async def safeguards(request, call_next):
    if request.url.path.startswith("/api") and request.method not in (
        "GET",
        "HEAD",
        "OPTIONS",
    ):
        if request.headers.get("origin") != ORIGIN:
            return Response(status_code=403)
    result = await call_next(request)
    result.headers["Cache-Control"] = (
        "no-store"
        if request.url.path.startswith("/api") or request.url.path == "/"
        else "no-cache"
    )
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "no-referrer"
    result.headers["X-Frame-Options"] = "DENY"
    result.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return result


def auth(request: Request):
    token = request.cookies.get("session", "")
    with Session() as db:
        login = db.get(Login, digest(token))
        if not login or utc(login.expires) < now():
            raise HTTPException(401, "로그인 필요")
        user = db.get(User, login.user_id)
        if not user or not user.active:
            raise HTTPException(401, "로그인 필요")
        if request.method not in ("GET", "HEAD") and not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), login.csrf
        ):
            raise HTTPException(403, "CSRF 검증 실패")
        return user


def admin(user=Depends(auth)):
    if not user.admin:
        raise HTTPException(403, "관리자 권한 필요")
    return user


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
def login(data: Credentials, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    at = time.time()
    attempts[ip] = [t for t in attempts[ip] if t > at - 900]
    if len(attempts[ip]) >= 10:
        raise HTTPException(429, "잠시 후 다시 시도하세요")
    attempts[ip].append(at)
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.username == data.username))
        try:
            valid = ph.verify(
                user.password if user else ph.hash(secrets.token_hex(16)), data.password
            )
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or not user or not user.active:
            raise HTTPException(401, "계정 또는 비밀번호 확인")
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_hex(32)
        db.add(
            Login(
                token=digest(token),
                user_id=user.id,
                csrf=csrf,
                expires=now() + timedelta(hours=12),
            )
        )
        response.set_cookie(
            "session",
            token,
            httponly=True,
            secure=ORIGIN.startswith("https://"),
            samesite="strict",
            max_age=43200,
            path="/",
        )
        attempts.pop(ip, None)
        return {"username": user.username, "admin": user.admin, "csrf": csrf}


@app.get("/api/me")
def me(request: Request, user=Depends(auth)):
    with Session() as db:
        login = db.get(Login, digest(request.cookies["session"]))
        return {
            "username": user.username,
            "admin": user.admin,
            "csrf": login.csrf,
            "preferences": user.preferences,
        }


@app.post("/api/logout")
def logout(request: Request, response: Response, user=Depends(auth)):
    with Session.begin() as db:
        db.execute(
            delete(Login).where(Login.token == digest(request.cookies["session"]))
        )
    response.delete_cookie("session", path="/")
    return {"ok": True}


@app.post("/api/password")
def password(data: Credentials, user=Depends(auth)):
    if len(data.password) < 14:
        raise HTTPException(422, "비밀번호 14자 이상 필요")
    with Session.begin() as db:
        db.get(User, user.id).password = ph.hash(data.password)
        db.execute(delete(Login).where(Login.user_id == user.id))
    return {"ok": True}


@app.get("/api/rankings")
def rankings(
    period: str = "current",
    category: str = "",
    source: str = "",
    q: str = "",
    view: str = "",
    user=Depends(auth),
):
    with Session() as db:
        snapshot = db.scalar(
            select(Snapshot)
            .where(Snapshot.period == period)
            .order_by(Snapshot.created.desc())
            .limit(1)
        )
        data = (
            dict(snapshot.data)
            if snapshot
            else {"entries": [], "notice": "수집·순위 작업 대기 중"}
        )
        states = {
            s.issue_id: {
                "saved": s.saved,
                "read": s.read,
                "hidden": s.hidden,
                "feedback": s.feedback,
            }
            for s in db.scalars(select(State).where(State.user_id == user.id))
        }
        entries = []
        for original in data["entries"]:
            r = {**original, "state": states.get(original["id"], {})}
            if (
                r["state"].get("hidden")
                or category
                and r["category"] != category
                or source
                and source not in r["sources"]
                or q
                and q not in r["title"]
            ):
                continue
            if view == "saved" and not r["state"].get("saved"):
                continue
            pref = user.preferences or {}
            if view == "interest":
                matches = [k for k in pref.get("keywords", []) if k in r["title"]]
                if not matches and not set(pref.get("sources", [])).intersection(
                    r["sources"]
                ):
                    continue
                if any(k in r["title"] for k in pref.get("excluded", [])) or r[
                    "category"
                ] in pref.get("excluded_categories", []):
                    continue
                r["match_reason"] = matches or ["선호 매체"]
            entries.append(r)
        data["entries"] = entries
        return data


@app.get("/api/feed")
def feed(
    view: str = "",
    category: str = "",
    source: str = "",
    q: str = "",
    user=Depends(auth),
):
    with Session() as db:
        states = {
            s.issue_id: s
            for s in db.scalars(select(State).where(State.user_id == user.id))
        }
        names = {s.id: s.name for s in db.scalars(select(Source))}
        entries = []
        pref = user.preferences or {}
        issues = db.scalars(select(Issue).order_by(Issue.discovered.desc()).limit(1000))
        if view == "saved":
            issues = db.scalars(
                select(Issue)
                .join(State, State.issue_id == Issue.id)
                .where(State.user_id == user.id, State.saved == True)
                .order_by(Issue.discovered.desc())
                .limit(1000)
            )
        for i in issues:
            st = states.get(i.id)
            if (
                st
                and st.hidden
                or category
                and i.category != category
                or q
                and q not in i.title
            ):
                continue
            articles = list(db.scalars(select(Article).where(Article.issue_id == i.id)))
            publishers = sorted({names[a.source_id] for a in articles})
            if source and source not in publishers:
                continue
            matches = [k for k in pref.get("keywords", []) if k and k in i.title]
            if view == "interest":
                if not matches and not set(pref.get("sources", [])).intersection(
                    publishers
                ):
                    continue
                if any(
                    k and k in i.title for k in pref.get("excluded", [])
                ) or i.category in pref.get("excluded_categories", []):
                    continue
            entries.append(
                {
                    "id": i.id,
                    "title": i.title,
                    "category": i.category,
                    "occurred": i.occurred,
                    "time_estimated": i.time_estimated,
                    "sources": publishers,
                    "state": {
                        "saved": st.saved,
                        "read": st.read,
                        "hidden": st.hidden,
                        "feedback": st.feedback,
                    }
                    if st
                    else {},
                    "score": 0,
                    "missing": ["prominence", "impact"],
                    "independent_origins": 0,
                    "evidence": 0,
                    "confidence": "목록 탐색 · 순위 미적용",
                    "match_reason": matches if view == "interest" else None,
                }
            )
            if len(entries) >= 100:
                break
        return {
            "entries": entries,
            "notice": "최근 1,000개 후보 중 최대 100개 표시 · 개인 관심 필터는 종합 순위에 영향을 주지 않습니다.",
        }


class MergeRequest(BaseModel):
    target_id: str


class SplitRequest(BaseModel):
    article_ids: list[str] = Field(min_length=1, max_length=100)


@app.post("/api/admin/issues/{iid}/merge")
def merge_issue(iid: str, data: MergeRequest, user=Depends(admin)):
    if iid == data.target_id:
        raise HTTPException(400)
    with Session.begin() as db:
        original = db.get(Issue, iid)
        target = db.get(Issue, data.target_id)
        if not original or not target:
            raise HTTPException(404)
        for a in db.scalars(select(Article).where(Article.issue_id == iid)):
            a.issue_id = target.id
        db.add(
            IssueEvent(
                issue_id=target.id,
                kind="관리자 병합",
                data={"from": iid, "actor": user.id},
            )
        )
        db.add(
            Audit(
                actor=user.id, action="이슈 병합", data={"from": iid, "to": target.id}
            )
        )
        # Retain the old identity and saved state; immutable snapshots remain unchanged.
    return {"ok": True, "target": data.target_id}


@app.post("/api/admin/issues/{iid}/split")
def split_issue(iid: str, data: SplitRequest, user=Depends(admin)):
    with Session.begin() as db:
        original = db.get(Issue, iid)
        if not original:
            raise HTTPException(404)
        articles = list(
            db.scalars(
                select(Article).where(
                    Article.issue_id == iid, Article.id.in_(data.article_ids)
                )
            )
        )
        if len(articles) != len(set(data.article_ids)):
            raise HTTPException(400, "해당 이슈의 기사만 분리 가능")
        new_id = secrets.token_hex(32)
        db.add(
            Issue(
                id=new_id,
                title=articles[0].title,
                category=original.category,
                occurred=original.occurred,
            )
        )
        db.flush()
        for a in articles:
            a.issue_id = new_id
        db.add(
            IssueEvent(
                issue_id=new_id,
                kind="관리자 분리",
                data={"from": iid, "articles": data.article_ids, "actor": user.id},
            )
        )
        db.add(
            Audit(actor=user.id, action="이슈 분리", data={"from": iid, "to": new_id})
        )
    return {"ok": True, "target": new_id}


@app.get("/api/issues/{iid}")
def issue(iid: str, user=Depends(auth)):
    with Session() as db:
        i = db.get(Issue, iid)
        if not i:
            raise HTTPException(404)
        sources = {s.id: s.name for s in db.scalars(select(Source))}
        paper_map = {}
        for p in db.scalars(select(PaperEntry)):
            paper_map.setdefault(article_key(p.url), []).append(
                f"{p.date} {p.section}{p.page}면 {p.position}번째"
            )
        articles = [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source": sources[a.source_id],
                "published": a.published,
                "modified": a.modified,
                "published_estimated": a.published is None,
                "basis": "제목 기반",
                "paper": " / ".join(paper_map.get(article_key(a.url), []))
                if a.source_id == "donga" and article_key(a.url) in paper_map
                else "지면 미확인",
            }
            for a in db.scalars(select(Article).where(Article.issue_id == iid))
        ]
        return {
            "id": i.id,
            "title": i.title,
            "articles": articles,
            "comparison": "비교 불가: 이용이 허용된 본문 근거가 확보되지 않았습니다.",
            "facts": [],
        }


@app.put("/api/issues/{iid}/state")
def update_state(iid: str, data: IssueState, user=Depends(auth)):
    with Session.begin() as db:
        if not db.get(Issue, iid):
            raise HTTPException(404)
        state = db.scalar(
            select(State).where(State.user_id == user.id, State.issue_id == iid)
        )
        if not state:
            state = State(user_id=user.id, issue_id=iid)
            db.add(state)
        for k, v in data.model_dump().items():
            setattr(state, k, v)
    return {"ok": True}


@app.put("/api/preferences")
def preferences(data: Preferences, user=Depends(auth)):
    with Session.begin() as db:
        db.get(User, user.id).preferences = data.model_dump()
    return {"ok": True}


def source_status(source):
    if not source.enabled:
        return "일시중지"
    if (
        source.state == "정상"
        and source.last_success
        and (now() - utc(source.last_success)).total_seconds() > 3600
    ):
        return "지연"
    return source.state


@app.get("/api/sources")
def sources(user=Depends(auth)):
    with Session() as db:
        return [
            {
                "id": s.id,
                "name": s.name,
                "state": source_status(s),
                "paper": (s.capabilities or {}).get("paper", "미지원"),
            }
            for s in db.scalars(select(Source))
            if not (s.capabilities or {}).get("archived")
        ]


@app.get("/api/paper")
def paper(date: str = "", user=Depends(auth)):
    with Session() as db:
        latest = db.scalar(
            select(PaperEntry.date).order_by(PaperEntry.date.desc()).limit(1)
        )
        selected = date or latest
        entries = [
            {
                "date": p.date,
                "section": p.section,
                "page": p.page,
                "position": p.position,
                "title": p.title,
                "url": p.url,
                "evidence_url": p.evidence_url,
                "observed": p.observed,
            }
            for p in db.scalars(
                select(PaperEntry)
                .where(PaperEntry.date == selected)
                .order_by(PaperEntry.section, PaperEntry.page, PaperEntry.position)
            )
        ]
        return {
            "supported": bool(entries),
            "date": selected,
            "dates": list(
                db.scalars(
                    select(PaperEntry.date).distinct().order_by(PaperEntry.date.desc())
                )
            ),
            "entries": entries,
            "url": "https://www.donga.com/news",
            "message": "공개 지면 목차에서 확인한 목록입니다. 지면 이미지/PDF는 수집하지 않습니다."
            if entries
            else "공개 지면 목차 수집 대기 또는 확인 실패",
        }


@app.get("/api/admin/status")
def status(user=Depends(admin)):
    with Session() as db:
        return {
            "sources": [
                {
                    "id": s.id,
                    "name": s.name,
                    "state": source_status(s),
                    "enabled": s.enabled,
                    "failures": s.failures,
                    "last_attempt": s.last_attempt,
                    "last_success": s.last_success,
                    "last_new": s.last_new,
                    "capabilities": s.capabilities,
                    "runs": [
                        {
                            "status": r.status,
                            "count": r.count,
                            "error": r.error,
                            "created": r.created,
                            "duration_ms": r.duration_ms,
                        }
                        for r in db.scalars(
                            select(Run)
                            .where(Run.source_id == s.id)
                            .order_by(Run.id.desc())
                            .limit(8)
                        )
                    ],
                }
                for s in db.scalars(select(Source))
            ],
            "heartbeat": db.get(Job, "heartbeat").updated
            if db.get(Job, "heartbeat")
            else None,
            "ai": {
                "enabled": False,
                "reason": "본문 재이용 조건 및 공급자 구현 미검증; 외부 AI 전송 비활성",
            },
        }


class RankingCorrection(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@app.post("/api/admin/rankings/rebuild")
def rebuild_rankings(data: RankingCorrection, user=Depends(admin)):
    with Session.begin() as db:
        job = db.get(Job, "ranking-correction")
        if job:
            raise HTTPException(409, "순위 정정 대기 중")
        last = db.scalar(
            select(Audit)
            .where(Audit.action == "순위 정정 요청")
            .order_by(Audit.id.desc())
            .limit(1)
        )
        if last and (now() - utc(last.created)).total_seconds() < 60:
            raise HTTPException(429, "60초 후 재시도")
        db.add(
            Job(
                key="ranking-correction",
                payload={"reason": data.reason, "actor": user.id},
            )
        )
        db.add(
            Audit(actor=user.id, action="순위 정정 요청", data={"reason": data.reason})
        )
    return {"ok": True, "message": "worker 정정 버전 생성 대기"}


@app.post("/api/admin/sources/{sid}/{action}")
def source_action(sid: str, action: str, user=Depends(admin)):
    with Session.begin() as db:
        s = db.get(Source, sid)
        if not s or action not in ("collect", "pause", "resume"):
            raise HTTPException(404)
        if action == "collect":
            if s.last_attempt and (now() - utc(s.last_attempt)).total_seconds() < 60:
                raise HTTPException(429, "수동 수집 쿨다운 60초")
            if not db.get(Job, "collect:" + sid):
                db.add(Job(key="collect:" + sid))
        else:
            s.enabled = action == "resume"
        db.add(Audit(actor=user.id, action=action, data={"source": sid}))
    return {"ok": True}


@app.get("/api/admin/users")
def users(user=Depends(admin)):
    with Session() as db:
        return [
            {"id": u.id, "username": u.username, "admin": u.admin, "active": u.active}
            for u in db.scalars(select(User))
        ]


@app.post("/api/admin/users")
def create_user(data: NewUser, user=Depends(admin)):
    if len(data.password) < 14:
        raise HTTPException(422, "14자 이상 필요")
    with Session.begin() as db:
        if db.scalar(select(User).where(User.username == data.username)):
            raise HTTPException(409, "중복 계정")
        db.add(
            User(
                username=data.username,
                password=ph.hash(data.password),
                admin=data.admin,
            )
        )
        db.add(
            Audit(actor=user.id, action="사용자 생성", data={"username": data.username})
        )
    return {"ok": True}


@app.post("/api/admin/users/{uid}/reset-password")
def reset_password(uid: int, data: Credentials, user=Depends(admin)):
    if len(data.password) < 14:
        raise HTTPException(422, "14자 이상 필요")
    with Session.begin() as db:
        u = db.get(User, uid)
        if not u:
            raise HTTPException(404)
        u.password = ph.hash(data.password)
        db.execute(delete(Login).where(Login.user_id == uid))
        db.add(Audit(actor=user.id, action="비밀번호 초기화", data={"user": uid}))
    return {"ok": True}


@app.post("/api/admin/users/{uid}/disable")
def disable_user(uid: int, user=Depends(admin)):
    if uid == user.id:
        raise HTTPException(400, "자기 계정 비활성화 불가")
    with Session.begin() as db:
        u = db.get(User, uid)
        if not u:
            raise HTTPException(404)
        u.active = False
        db.execute(delete(Login).where(Login.user_id == uid))
        db.add(Audit(actor=user.id, action="사용자 비활성화", data={"user": uid}))
    return {"ok": True}


DIST = Path(os.getenv("STATIC_DIR", "frontend/dist"))
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (DIST / path).resolve()
        if f.is_relative_to(DIST.resolve()) and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
