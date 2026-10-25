import os

os.environ["DATABASE_URL"] = "sqlite://"
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.app import main
from backend.app.db import Base, User, Issue, Article, State, Login, Snapshot
from backend.app.ranking import score, window, rank
from backend.app.security import canonical, validate_url
from backend.app.collector import parse_feed


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "Session", factory)
    with factory.begin() as s:
        s.add(
            User(
                username="admin",
                password=main.ph.hash("a-long-test-password"),
                admin=True,
            )
        )
        s.add(
            User(
                username="reader",
                password=main.ph.hash("a-long-test-password"),
                admin=False,
            )
        )
    yield factory
    engine.dispose()


def test_auth_csrf_roles_and_logout(db):
    c = TestClient(main.app)
    h = {"Origin": "http://localhost:38475"}
    assert c.get("/api/admin/status").status_code == 401
    assert (
        c.post(
            "/api/login",
            json={"username": "reader", "password": "a-long-test-password"},
        ).status_code
        == 403
    )
    r = c.post(
        "/api/login",
        headers=h,
        json={"username": "reader", "password": "a-long-test-password"},
    )
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/admin/status").status_code == 403
    assert c.put("/api/preferences", headers=h, json={}).status_code == 403
    h["X-CSRF-Token"] = r.json()["csrf"]
    assert (
        c.put("/api/preferences", headers=h, json={"keywords": ["반도체"]}).status_code
        == 200
    )
    assert c.get("/api/me").headers["cache-control"] == "no-store"
    assert c.post("/api/logout", headers=h).status_code == 200
    assert c.get("/api/me").status_code == 401


def test_user_isolation_and_password_revoke(db):
    a = TestClient(main.app)
    b = TestClient(main.app)
    h = {"Origin": "http://localhost:38475"}
    ra = a.post(
        "/api/login",
        headers=h,
        json={"username": "admin", "password": "a-long-test-password"},
    ).json()
    rb = b.post(
        "/api/login",
        headers=h,
        json={"username": "reader", "password": "a-long-test-password"},
    ).json()
    a.put(
        "/api/preferences",
        headers={**h, "X-CSRF-Token": ra["csrf"]},
        json={"keywords": ["private"]},
    )
    assert b.get("/api/me").json()["preferences"] == {}
    assert (
        b.post(
            "/api/password",
            headers={**h, "X-CSRF-Token": rb["csrf"]},
            json={"username": "ignored", "password": "new-long-test-password"},
        ).status_code
        == 200
    )
    assert b.get("/api/me").status_code == 401
    assert a.get("/api/me").status_code == 200


def test_password_min_length(db):
    c = TestClient(main.app)
    h = {"Origin": "http://localhost:38475"}
    r = c.post(
        "/api/login",
        headers=h,
        json={"username": "reader", "password": "a-long-test-password"},
    ).json()
    csrf_h = {**h, "X-CSRF-Token": r["csrf"]}
    # 5자리는 422 실패
    assert (
        c.post(
            "/api/password",
            headers=csrf_h,
            json={"username": "reader", "password": "12345"},
        ).status_code
        == 422
    )
    # 6자리는 200 성공
    assert (
        c.post(
            "/api/password",
            headers=csrf_h,
            json={"username": "reader", "password": "123456"},
        ).status_code
        == 200
    )


def test_score_missing_and_no_inflation():
    r = score(2, 0, 12)
    assert r["missing"] == ["prominence", "impact"]
    assert r["score"] == pytest.approx((0.3 * 20 + 0.15 * 100) / 0.45, abs=0.0001)
    assert score(2, 12, 12)["score"] < r["score"]
    assert score(0, 0, 12)["factors"]["spread"] == 0


def test_kst_boundaries():
    at = datetime(2026, 10, 25, 15, 5, tzinfo=timezone.utc)  # Monday KST
    start, end, _ = window("week", at)
    assert start == datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
    start, end, _ = window("daily-final", at)
    assert end == datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)
    start, end, _ = window("weekly-final", at)
    assert end - start == timedelta(days=7)


def test_future_and_late_articles_excluded(db):
    from backend.app.db import Source

    at = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
    with db.begin() as s:
        s.add(
            Source(
                id="test",
                name="test",
                domain="example.com",
                endpoint="https://example.com",
            )
        )
        for name, occurred, discovered in [
            ("past", at - timedelta(hours=1), at - timedelta(minutes=30)),
            ("future", at + timedelta(hours=1), at),
            ("late", at - timedelta(hours=1), at + timedelta(hours=1)),
        ]:
            s.add(Issue(id=name, title=name, occurred=occurred, discovered=discovered))
            s.flush()
            s.add(
                Article(
                    id=name,
                    issue_id=name,
                    source_id="test",
                    title=name,
                    url="https://example.com/" + name,
                    origin="unknown:wire",
                    published=occurred,
                    discovered=discovered,
                    collected=discovered,
                )
            )
    with db() as s:
        r = rank(s, "current", at)
        assert [e["id"] for e in r["entries"]] == ["past"]
        assert r["entries"][0]["independent_origins"] == 0


def test_ssrf_and_canonical(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError):
        validate_url("https://example.com", "example.com")
    for url in [
        "http://example.com",
        "https://example.com.evil.org",
        "https://user:pass@example.com",
        "https://example.com:444",
    ]:
        with pytest.raises(ValueError):
            validate_url(url, "example.com")
    assert (
        canonical("https://example.com/a?utm_source=x&id=1#xx")
        == "https://example.com/a?id=1"
    )


def test_feed_missing_dates_and_html():
    body = b'<rss version="2.0"><channel><title>x</title><item><title>&lt;script&gt;x&lt;/script&gt; News</title><link>https://example.com/a</link></item></channel></rss>'
    result = parse_feed(body)
    assert result[0]["published"] is None
    assert "<script>" not in result[0]["title"]
    with pytest.raises(ValueError):
        parse_feed(b"<html>blocked</html>")


def test_collect_zero_failure_and_recovery(db, monkeypatch):
    from backend.app import collector
    from backend.app.db import Source, Run

    monkeypatch.setattr(collector, "Session", db)
    with db.begin() as s:
        s.add(
            Source(
                id="test",
                name="fixture",
                domain="example.com",
                endpoint="https://example.com/rss",
                capabilities={},
            )
        )

    def failure(*args):
        raise TimeoutError("secret-not-for-logs")

    monkeypatch.setattr(collector, "fetch", failure)
    collector.collect("test")
    with db() as s:
        assert s.get(Source, "test").failures == 1
        assert "secret" not in s.scalar(select(Run)).error
    monkeypatch.setattr(
        collector,
        "fetch",
        lambda *a: (
            200,
            b'<rss version="2.0"><channel><title>x</title></channel></rss>',
            {},
        ),
    )
    collector.collect("test")
    with db() as s:
        assert s.get(Source, "test").state == "정상"
        assert s.get(Source, "test").failures == 0
        assert s.get(Source, "test").last_new is None
        assert len(list(s.scalars(select(Run)))) == 2


def test_empty_response_is_not_feed():
    with pytest.raises(ValueError):
        parse_feed(b"")


def test_safe_redirect_and_304(monkeypatch):
    import httpx
    from backend.app import security

    calls = []
    monkeypatch.setattr(
        security,
        "validate_url",
        lambda url, domain: (
            "1.1.1.1"
            if "example.com" in url
            else (_ for _ in ()).throw(ValueError("blocked redirect"))
        ),
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, method, url, headers, extensions):
            calls.append((str(url), headers, extensions))
            from contextlib import nullcontext

            return nullcontext(httpx.Response(304, request=httpx.Request(method, url)))

    monkeypatch.setattr(security.httpx, "Client", Client)
    assert security.fetch("https://example.com/feed", "example.com")[0] == 304
    assert calls[0][0] == "https://1.1.1.1/feed"
    assert calls[0][1]["Host"] == "example.com"
    assert calls[0][2]["sni_hostname"] == "example.com"


def test_paper_requires_actual_index_and_preserves_page_order():
    from pathlib import Path
    from backend.app.paper import parse_paper, article_key

    result = parse_paper(Path("tests/fixtures/donga-paper.html").read_text())
    assert len(result) == 2
    assert [(r["date"], r["section"], r["page"], r["position"]) for r in result] == [
        ("2026-10-24", "A", 1, 1),
        ("2026-10-24", "A", 2, 1),
    ]
    assert article_key(result[0]["url"]) == "134899958"
    with pytest.raises(ValueError):
        parse_paper("<html>일반 뉴스 목록</html>")
    with pytest.raises(ValueError):
        parse_paper("<h3>지면 목차</h3>")


@pytest.mark.parametrize(
    "source_id",
    [
        "donga",
        "chosun",
        "seoul",
        "hani",
        "khan",
        "segye",
        "yna",
        "sbs",
        "mk",
        "hankyung",
    ],
)
def test_source_feed_fixtures(source_id):
    from pathlib import Path
    from backend.app.sources import SOURCES
    from urllib.parse import urlsplit

    row = next(s for s in SOURCES if s[0] == source_id)
    entries = parse_feed(Path(f"tests/fixtures/rss/{source_id}.xml").read_bytes())
    assert len(entries) == 1
    assert urlsplit(entries[0]["url"]).hostname.endswith(row[2])
    assert entries[0]["title"]


def test_nonstandard_rfc_date_and_modified_are_distinct():
    result = parse_feed(
        b'<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>x</title><link>https://example.com/1</link><pubDate>Sun,25 Oct 2026 05:52:56 +0900</pubDate></item><item><title>y</title><link>https://example.com/2</link><dc:date>2026-10-25T07:00:02+09:00</dc:date></item></channel></rss>'
    )
    assert result[0]["published"] == datetime(
        2026, 10, 24, 20, 52, 56, tzinfo=timezone.utc
    )
    assert result[0]["modified"] is None
    assert result[1]["published"] is None
    assert result[1]["modified"] is not None


def test_multi_source_spread_boosts_ranking(db):
    from backend.app.db import Source

    at = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    with db.begin() as s:
        s.add(
            Source(
                id="src_a",
                name="A일보",
                domain="a.com",
                endpoint="https://a.com",
            )
        )
        s.add(
            Source(
                id="src_b",
                name="B뉴스",
                domain="b.com",
                endpoint="https://b.com",
            )
        )
        # 3일 전 다수 매체 보도 이슈 (major)
        three_days_ago = at - timedelta(days=3)
        s.add(
            Issue(
                id="major",
                title="주요 대형 사건",
                occurred=three_days_ago,
                discovered=three_days_ago,
            )
        )
        s.flush()
        s.add(
            Article(
                id="art_a",
                issue_id="major",
                source_id="src_a",
                title="주요 대형 사건",
                url="https://a.com/major",
                origin="unknown:major",
                published=three_days_ago,
                discovered=three_days_ago,
                collected=three_days_ago,
            )
        )
        s.add(
            Article(
                id="art_b",
                issue_id="major",
                source_id="src_b",
                title="주요 대형 사건",
                url="https://b.com/major",
                origin="unknown:major",
                published=three_days_ago,
                discovered=three_days_ago,
                collected=three_days_ago,
            )
        )
        # 10분 전 단일 매체 단신 이슈 (minor)
        ten_mins_ago = at - timedelta(minutes=10)
        s.add(
            Issue(
                id="minor",
                title="방금 올라온 단신",
                occurred=ten_mins_ago,
                discovered=ten_mins_ago,
            )
        )
        s.flush()
        s.add(
            Article(
                id="art_c",
                issue_id="minor",
                source_id="src_a",
                title="방금 올라온 단신",
                url="https://a.com/minor",
                origin="unknown:minor",
                published=ten_mins_ago,
                discovered=ten_mins_ago,
                collected=ten_mins_ago,
            )
        )

    with db() as s:
        r = rank(s, "week", at)
        entries = r["entries"]
        assert len(entries) == 2
        # major 이슈가 2개 매체 보도로 확산도(k=2) 가점을 받아 1위를 차지해야 함
        assert entries[0]["id"] == "major"
        assert entries[0]["independent_origins"] == 2
        assert entries[0]["score"] > entries[1]["score"]
        assert entries[1]["id"] == "minor"
        assert entries[1]["independent_origins"] == 0


def test_daily_final_window_and_published_coalesce(db):
    from backend.app.db import Source

    # at: 2026-10-25 15:00 UTC (KST 2026-10-26 00:00)
    at = datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
    yesterday_pub = datetime(2026, 10, 24, 20, tzinfo=timezone.utc)  # KST 10-25 05:00
    with db.begin() as s:
        s.add(
            Source(
                id="src_null",
                name="무일자일보",
                domain="null.com",
                endpoint="https://null.com",
            )
        )
        s.add(
            Issue(
                id="null_pub_issue",
                title="발행일자 결측 기사",
                occurred=yesterday_pub,
                discovered=yesterday_pub,
            )
        )
        s.flush()
        s.add(
            Article(
                id="null_pub_art",
                issue_id="null_pub_issue",
                source_id="src_null",
                title="발행일자 결측 기사",
                url="https://null.com/1",
                origin="unknown:null",
                published=None,  # pubDate 결측
                discovered=yesterday_pub,
                collected=yesterday_pub,
            )
        )

    with db() as s:
        # daily-final 구간에 coalesce(published, discovered)로 정상 포함되어야 함
        r = rank(s, "daily-final", at)
        assert any(e["id"] == "null_pub_issue" for e in r["entries"])


def test_is_korean_article_filter():
    from backend.app.collector import is_korean_article

    # 한국어 정상 기사
    assert is_korean_article("한국 경제 성장률 전망치 발표", "https://example.com/news/1")
    assert is_korean_article("[속보] 삼성전자, AI 반도체 발표", "https://example.com/news/2")

    # 일본어 포함 기사 (제외 대상)
    assert not is_korean_article(
        "キム・ジソン＆イ・ヒョニ、豊胸から乳腺炎まで…赤裸々トークで一体感『トンチミ",
        "https://www.chosun.com/jp/culture-life-jp/2026/10/25/abc/",
    )
    assert not is_korean_article(
        "「イ・ガンインがアトレティコを目覚めさせた」スペイン紙",
        "https://www.chosun.com/jp/sports-jp/2026/10/25/xyz/",
    )

    # URL 외국어 경로 기사 (제외 대상)
    assert not is_korean_article(
        "South Korea economy outlook", "https://example.com/en/news/1"
    )
    assert not is_korean_article(
        "한국어 제목이지만 일본어판 URL", "https://www.chosun.com/jp/news/1"
    )

    # 한글 미포함 순수 외국어 (제외 대상)
    assert not is_korean_article(
        "Global stock markets drop today", "https://example.com/article/1"
    )


def test_conservative_and_progressive_top10(db):
    from backend.app.db import Source

    at = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    with db.begin() as s:
        s.add(
            Source(
                id="chosun",
                name="조선일보",
                domain="chosun.com",
                endpoint="https://chosun.com",
            )
        )
        s.add(
            Source(
                id="hani",
                name="한겨레",
                domain="hani.co.kr",
                endpoint="https://hani.co.kr",
            )
        )

        # 보수 기사
        s.add(
            Issue(
                id="cons_issue",
                title="보수 주요 보도 사건",
                occurred=at - timedelta(hours=1),
                discovered=at - timedelta(hours=1),
            )
        )
        s.flush()
        s.add(
            Article(
                id="art_chosun",
                issue_id="cons_issue",
                source_id="chosun",
                title="보수 주요 보도 사건",
                url="https://chosun.com/1",
                origin="unknown:cons",
                published=at - timedelta(hours=1),
                discovered=at - timedelta(hours=1),
                collected=at - timedelta(hours=1),
            )
        )

        # 진보 기사
        s.add(
            Issue(
                id="prog_issue",
                title="진보 주요 보도 사건",
                occurred=at - timedelta(hours=2),
                discovered=at - timedelta(hours=2),
            )
        )
        s.flush()
        s.add(
            Article(
                id="art_hani",
                issue_id="prog_issue",
                source_id="hani",
                title="진보 주요 보도 사건",
                url="https://hani.co.kr/1",
                origin="unknown:prog",
                published=at - timedelta(hours=2),
                discovered=at - timedelta(hours=2),
                collected=at - timedelta(hours=2),
            )
        )

    with db() as s:
        r = rank(s, "current", at)
        by_cat = r.get("by_category", {})
        assert "보수" in by_cat
        assert "진보" in by_cat
        assert any(e["id"] == "cons_issue" for e in by_cat["보수"])
        assert any(e["id"] == "prog_issue" for e in by_cat["진보"])
        # 보수 순위에는 진보 기사 미포함
        assert not any(e["id"] == "prog_issue" for e in by_cat["보수"])
        # 진보 순위에는 보수 기사 미포함
        assert not any(e["id"] == "cons_issue" for e in by_cat["진보"])
