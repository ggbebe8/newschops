import re
from difflib import SequenceMatcher
from datetime import timedelta
from sqlalchemy import select
from .db import Issue, now
from .ranking import utc

# 언론사 말머리, 꼬리말, 섹션 태그 정규표현식 ([속보], (종합), 【포토】 등)
TAG_PATTERN = re.compile(r"\[[^\]]*\]|\([^\)]*\)|<[^>]*>|【[^】]*】|〔[^〕]*〕|〈[^〉]*〉")
# 불필요한 특수기호 및 따옴표
PUNCT_PATTERN = re.compile(r"[\'\"‘’“”·…,\.!\?~·―—\-_\[\]\(\)<>【】〔〕〈〉/·:;]")


def clean_title(title: str) -> str:
    """기사 제목에서 말머리 태그, 언론사 표식, 특수기호를 제거하고 공백을 정규화합니다."""
    # 1. [속보], (종합), [단독], [포토] 등 대괄호/소괄호 말머리 태그 제거
    t = TAG_PATTERN.sub(" ", title)
    # 2. 특수기호 및 문장부호 공백 치환
    t = PUNCT_PATTERN.sub(" ", t)
    # 3. 연속 공백 단일화 및 양쪽 여백 제거
    return re.sub(r"\s+", " ", t).strip()


def tokenize(title: str) -> set[str]:
    """2글자 이상의 의미 있는 단어 집합을 추출합니다."""
    cleaned = clean_title(title)
    return {w for w in cleaned.split() if len(w) >= 2}


def is_similar_title(t1: str, t2: str) -> bool:
    """
    두 기사 제목이 동일한 사건/이슈를 다루는지 판별합니다.
    - 정규화된 제목 완전 일치
    - 공통 핵심 키워드 3개 이상 일치
    - 자카드 유사도 0.35 이상이면서 공통 키워드 2개 이상
    - 문자열 시퀀스 유사도 0.60 이상이면서 공통 키워드 1개 이상
    """
    c1 = clean_title(t1)
    c2 = clean_title(t2)
    if c1 == c2:
        return True

    s1 = tokenize(t1)
    s2 = tokenize(t2)
    if not s1 or not s2:
        return False

    common = s1 & s2
    if len(common) >= 3:
        return True

    union = s1 | s2
    jaccard = len(common) / len(union)
    if jaccard >= 0.35 and len(common) >= 2:
        return True

    ratio = SequenceMatcher(None, c1, c2).ratio()
    if ratio >= 0.60 and len(common) >= 1:
        return True

    return False


def find_matching_issue(db, title: str, occurred, time_window_hours: int = 36):
    """
    최근 시간 범위 내에 동일한 사건을 다루는 기존 Issue가 있는지 탐색합니다.
    있으면 해당 Issue를 반환하고, 없으면 None을 반환합니다.
    """
    occ = utc(occurred)
    start = occ - timedelta(hours=time_window_hours)
    end = occ + timedelta(hours=time_window_hours)

    recent_issues = list(
        db.scalars(
            select(Issue)
            .where(Issue.occurred >= start, Issue.occurred <= end)
            .order_by(Issue.occurred.desc())
            .limit(300)
        )
    )

    # 1차: 제목 완전 일치 우선
    c_new = clean_title(title)
    for issue in recent_issues:
        if clean_title(issue.title) == c_new:
            return issue

    # 2차: 유사도 기반 판별
    for issue in recent_issues:
        if is_similar_title(issue.title, title):
            return issue

    return None


def recluster_all(db):
    """
    기존에 수집된 모든 기사들을 유사도 기반으로 재클러스터링하여
    동일 사건 기사들의 issue_id를 하나로 통합하고 빈 Issue를 정리합니다.
    """
    from .db import Article, State

    articles = list(db.scalars(select(Article).order_by(Article.discovered.desc())))
    clusters = []

    for a in articles:
        matched = False
        a_time = utc(a.discovered)
        for c in clusters:
            rep = c[0]
            rep_time = utc(rep.discovered)
            time_diff = abs((a_time - rep_time).total_seconds())
            if time_diff <= 48 * 3600 and is_similar_title(rep.title, a.title):
                c.append(a)
                matched = True
                break
        if not matched:
            clusters.append([a])

    # 각 클러스터별로 issue_id 통일
    updated_articles = 0
    used_issue_ids = set()
    for c in clusters:
        rep_issue_id = c[0].issue_id
        used_issue_ids.add(rep_issue_id)
        for a in c[1:]:
            if a.issue_id != rep_issue_id:
                old_iid = a.issue_id
                a.issue_id = rep_issue_id
                updated_articles += 1

    db.flush()

    # 기사가 하나도 연결되지 않은 고립 Issue 정리 (단, 사용자가 저장한 상태 State가 없는 경우만)
    all_issues = list(db.scalars(select(Issue)))
    deleted_issues = 0
    for issue in all_issues:
        if issue.id not in used_issue_ids:
            has_articles = db.scalar(
                select(Article.id).where(Article.issue_id == issue.id).limit(1)
            )
            if not has_articles:
                # State 정리
                db.execute(
                    Issue.__table__.delete().where(Issue.id == issue.id)
                )
                deleted_issues += 1

    db.flush()
    return {
        "total_articles": len(articles),
        "total_clusters": len(clusters),
        "updated_articles": updated_articles,
        "deleted_issues": deleted_issues,
    }
