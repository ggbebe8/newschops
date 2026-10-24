import calendar, re, time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import feedparser
from sqlalchemy import select
from .db import *
from .security import fetch, canonical, digest, validate_url


def parse_feed(body):
    feed = feedparser.parse(body)
    if not feed.get("version"):
        raise ValueError("RSS/Atom 포맷 미확인")
    result = []
    for e in feed.entries[:150]:
        if not e.get("title") or not e.get("link"):
            continue
        title = re.sub("<[^>]+>", "", e.title).strip()[:1000]
        date = e.get("published_parsed")
        published = (
            datetime.fromtimestamp(calendar.timegm(date), timezone.utc)
            if date
            else None
        )
        if published is None and e.get("published"):
            try:
                parsed = parsedate_to_datetime(e.published)
                if parsed.tzinfo:
                    published = parsed.astimezone(timezone.utc)
            except (ValueError, TypeError):
                pass
        modified = dict.get(e, "updated_parsed")
        result.append(
            {
                "title": title,
                "url": canonical(e.link),
                "published": published,
                "modified": datetime.fromtimestamp(
                    calendar.timegm(modified), timezone.utc
                )
                if modified
                else None,
            }
        )
    return result


def is_korean_article(title: str, url: str) -> bool:
    lower_url = url.lower()
    # 1. URL 경로에 명시적인 외국어 섹션(/jp/, /en/, /cn/, /japanese/, /english/, /chinese/ 등) 제외
    if re.search(r"/(jp|en|cn|japanese|english|chinese)(/|-|\.|$)", lower_url):
        return False
    # 2. 일본어(히라가나, 가타카나)가 포함된 경우 제외
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", title):
        return False
    # 3. 한글이 전혀 없는 경우 (순수 외국어 제목) 제외
    if not re.search(r"[\uAC00-\uD7A3\u1100-\u11FF]", title):
        return False
    return True


def collect(sid):
    started = time.monotonic()
    with Session.begin() as db:
        source = db.get(Source, sid)
        if not source or not source.enabled:
            return
        source.last_attempt = now()
        count = 0
        try:
            headers = {"User-Agent": "newschops/0.1 personal RSS reader"}
            if source.etag:
                headers["If-None-Match"] = source.etag
            if source.modified:
                headers["If-Modified-Since"] = source.modified
            status, body, response = fetch(source.endpoint, source.domain, headers)
            entries = [] if status == 304 else parse_feed(body)
            for entry in entries:
                if not is_korean_article(entry["title"], entry["url"]):
                    continue
                try:
                    validate_url(entry["url"], source.domain)
                except (ValueError, OSError):
                    continue
                aid = digest(entry["url"])
                existing = db.get(Article, aid)
                if existing:
                    if existing.published is None and entry["published"] is not None:
                        existing.published = entry["published"]
                        issue = db.get(Issue, existing.issue_id)
                        if issue.time_estimated:
                            issue.occurred = entry["published"]
                            issue.time_estimated = False
                    if entry["modified"] is not None:
                        existing.modified = entry["modified"]
                    continue
                # Conservative identity: exact normalized title only, within 24h. Similar titles are not auto-merged.
                key = re.sub(r"\s+", " ", entry["title"]).strip()
                occurred = entry["published"] or now()
                iid = digest(key + "|" + occurred.strftime("%Y-%m-%d"))
                if not db.get(Issue, iid):
                    db.add(
                        Issue(
                            id=iid,
                            title=entry["title"],
                            category=category(entry["url"], entry["title"]),
                            occurred=occurred,
                            time_estimated=entry["published"] is None,
                        )
                    )
                    db.flush()
                db.add(
                    Article(
                        id=aid,
                        issue_id=iid,
                        source_id=sid,
                        url=entry["url"],
                        title=entry["title"],
                        origin="unknown:" + digest(key),
                        published=entry["published"],
                        modified=entry["modified"],
                    )
                )
                count += 1
            recent = [e["published"] for e in entries if e["published"]]
            freshness = (
                "발행 시각 확인 필요"
                if entries and not recent
                else (
                    "최신성 경고: 최근 발행이 24시간 이상 지연"
                    if recent and (now() - max(recent)).total_seconds() > 86400
                    else "관측됨"
                )
            )
            source.state = "정상"
            source.failures = 0
            source.last_success = now()
            if count:
                source.last_new = now()
            source.etag = response.get("etag", source.etag)
            source.modified = response.get("last-modified", source.modified)
            source.capabilities = {
                **source.capabilities,
                "list": "정상",
                "freshness": freshness
                if status != 304
                else source.capabilities.get("freshness", "미확인"),
                "retry_until": 0,
            }
            db.add(
                Run(
                    source_id=sid,
                    status="정상",
                    count=count,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
        except Exception as exc:
            source.failures += 1
            source.state = "오류" if source.failures >= 6 else "지연"
            # Do not retain arbitrary error bodies, URLs or credentials.
            code = getattr(getattr(exc, "response", None), "status_code", None)
            error = f"HTTP {code}" if code else type(exc).__name__
            retry_until = 0
            if code == 429:
                retry = exc.response.headers.get("retry-after", "")
                try:
                    retry_until = time.time() + max(0, int(retry))
                except ValueError:
                    try:
                        retry_until = parsedate_to_datetime(retry).timestamp()
                    except (ValueError, TypeError):
                        retry_until = time.time() + 900
            if code in (401, 403, 404):
                source.state = "설정 필요"
            source.capabilities = {
                **source.capabilities,
                "list": error,
                "retry_until": retry_until,
            }
            db.add(
                Run(
                    source_id=sid,
                    status=source.state,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )


def category(url, title):
    url_l = url.lower()
    title_l = title.lower()
    for label, words in [
        (
            "연예",
            [
                "entertain",
                "연예",
                "연애",
                "아이돌",
                "배우",
                "가수",
                "드라마",
                "예능",
                "음원",
                "스타",
                "팬미팅",
                "컴백",
                "빌보드",
                "가요",
                "방송",
                "출산",
                "임신",
                "결혼",
                "이혼",
                "열애",
                "소지섭",
                "김지원",
                "은가은",
                "박현호",
            ],
        ),
        (
            "스포츠",
            [
                "sport",
                "야구",
                "축구",
                "골프",
                "농구",
                "배구",
                "선수",
                "리그",
                "올림픽",
                "kbo",
                "손흥민",
                "이강인",
                "김하성",
                "오타니",
                "감독",
                "승리",
                "패배",
                "경기",
                "득점",
                "투수",
                "타자",
                "홈런",
                "우승",
                "준우승",
            ],
        ),
        (
            "정치",
            [
                "politic",
                "정당",
                "국회",
                "대통령",
                "총리",
                "여당",
                "야당",
                "의원",
                "선거",
                "공천",
                "청와대",
                "법무부",
                "김정은",
                "북한",
                "북·중",
                "북중",
                "남북",
                "방중",
                "핵무기",
                "검찰",
                "장관",
                "비대위",
                "당대표",
                "원내대표",
                "국정",
                "안보",
            ],
        ),
        (
            "경제",
            [
                "econom",
                "finance",
                "biz",
                "증시",
                "코스피",
                "금리",
                "주가",
                "환율",
                "부동산",
                "물가",
                "기업",
                "매출",
                "영업이익",
                "상장",
                "금융",
                "은행",
                "채권",
                "투자",
                "소비자",
                "신용등급",
                "무디스",
                "수출",
                "수입",
                "통상",
            ],
        ),
        (
            "국제",
            [
                "world",
                "international",
                "global",
                "미국",
                "중국",
                "일본",
                "러시아",
                "우크라",
                "트럼프",
                "백악관",
                "외신",
                "이스라엘",
                "가자",
                "eu",
                "유럽",
                "프랑스",
                "독일",
                "영국",
                "그리스",
                "사우디",
                "후티",
                "중동",
                "이란",
                "시리아",
                "대만",
                "유엔",
                "해외",
                "외교",
                "왕후닝",
            ],
        ),
        (
            "산업/기술",
            [
                "tech",
                "industry",
                "it",
                "반도체",
                "인공지능",
                "ai",
                "스마트폰",
                "배터리",
                "전기차",
                "로봇",
                "플랫폼",
                "통신",
                "스타십",
                "우주선",
                "발사체",
            ],
        ),
        (
            "문화",
            [
                "culture",
                "문화",
                "공연",
                "전시",
                "도서",
                "문학",
                "예술",
                "출판",
                "영화",
                "축제",
                "단풍",
                "유적",
                "답사",
            ],
        ),
    ]:
        if any(w in url_l or w in title_l for w in words):
            return label
    return "사회"
