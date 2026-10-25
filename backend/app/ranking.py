import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import Counter

KST = ZoneInfo("Asia/Seoul")


def utc(t):
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def window(period, at):
    local = at.astimezone(KST)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "daily-final":
        return (
            (midnight - timedelta(days=1)).astimezone(timezone.utc),
            midnight.astimezone(timezone.utc),
            24,
        )
    if period == "weekly-final":
        monday = midnight - timedelta(days=local.weekday())
        return (
            (monday - timedelta(days=7)).astimezone(timezone.utc),
            monday.astimezone(timezone.utc),
            168,
        )
    start = {
        "current": at - timedelta(hours=24),
        "hour": at - timedelta(hours=1),
        "today": midnight,
        "week": midnight - timedelta(days=local.weekday()),
        "7days": at - timedelta(days=7),
    }[period]
    return (
        start.astimezone(timezone.utc),
        at,
        168 if period in ("week", "7days") else 24 if period == "today" else 12,
    )


def score(k, h, half, prominence=None, impact=None):
    values = {
        "spread": 100 * min(k, 10) / 10,
        "prominence": prominence,
        "impact": impact,
        "recency": 100 * 2 ** (-max(h, 0) / half),
    }
    weights = {"spread": 0.30, "prominence": 0.30, "impact": 0.25, "recency": 0.15}
    observed = sum(weights[n] for n, v in values.items() if v is not None)
    return {
        "score": round(
            sum(weights[n] * v for n, v in values.items() if v is not None) / observed,
            4,
        ),
        "factors": values,
        "evidence": observed,
        "missing": [n for n, v in values.items() if v is None],
    }


def rank(db, period, at):
    from sqlalchemy import select, func
    from .db import Issue, Article, Source, Placement

    start, end, half = window(period, at)
    candidates = []
    all_sources = list(db.scalars(select(Source)))
    sources = {s.id: s.name for s in all_sources}
    eligible = select(Issue.id).where(
        Issue.occurred >= start,
        Issue.occurred < end,
        Issue.discovered <= at,
    )
    issues = list(db.scalars(select(Issue).where(Issue.id.in_(eligible))))
    effective_pub = func.coalesce(Article.published, Article.discovered)
    article_query = select(Article).where(
        Article.issue_id.in_(eligible),
        Article.discovered <= at,
        Article.collected <= at,
        effective_pub >= start,
        effective_pub < end,
    )
    by_issue = {}
    for article in db.scalars(article_query):
        by_issue.setdefault(article.issue_id, []).append(article)
    by_article = {}
    article_ids = select(Article.id).where(
        Article.issue_id.in_(eligible),
        Article.discovered <= at,
        Article.collected <= at,
        effective_pub >= start,
        effective_pub < end,
    )
    for observation in db.scalars(
        select(Placement).where(
            Placement.article_id.in_(article_ids), Placement.observed < end
        )
    ):
        by_article.setdefault(observation.article_id, []).append(observation)
    for issue in issues:
        articles = by_issue.get(issue.id, [])
        if not articles:
            continue
        # 일본어 및 외국어 전용 기사 배제
        if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", issue.title):
            continue
        known_count = len({a.origin for a in articles if a.origin.startswith("known:")})
        distinct_sources = len({a.source_id for a in articles})
        if known_count > 0:
            k = known_count
        elif distinct_sources >= 2:
            k = distinct_sources
        else:
            k = 0
        placements = {}
        placement_evidence = []
        for a in articles:
            observations = by_article.get(a.id, [])
            placement_evidence.extend(
                [
                    {
                        "article_id": a.id,
                        "url": p.evidence_url,
                        "observed": utc(p.observed).isoformat(),
                        "score": p.score,
                    }
                    for p in observations
                ]
            )
            if observations:
                placements[a.source_id] = max(
                    placements.get(a.source_id, 0), max(p.score for p in observations)
                )
        prominence = sum(placements.values()) / len(placements) if placements else None
        breakdown = score(
            k,
            (end - utc(issue.occurred)).total_seconds() / 3600,
            half,
            prominence=prominence,
        )
        confidence = (
            f"독립 보도 {k}개 매체 확인 · 확산도 반영"
            if k >= 2
            else "제한적 · 제목 기반 / 독립 취재 미확인"
        )
        candidates.append(
            {
                "id": issue.id,
                "title": issue.title,
                "url": articles[0].url if articles else "",
                "category": issue.category,
                "occurred": utc(issue.occurred).isoformat(),
                "sources": sorted({sources.get(a.source_id, a.source_id) for a in articles}),
                "articles": [a.id for a in articles],
                "independent_origins": k,
                "placement_evidence": placement_evidence,
                "confidence": confidence,
                **breakdown,
            }
        )
    candidates.sort(
        key=lambda r: (
            -r["score"],
            -r["independent_origins"],
            -r["evidence"],
            -datetime.fromisoformat(r["occurred"]).timestamp(),
            r["id"],
        )
    )
    counts = Counter()
    chosen = []
    rest = []
    for c in candidates:
        if counts[c["category"]] < 4 and len(chosen) < 10:
            chosen.append(c)
            counts[c["category"]] += 1
        else:
            rest.append(c)
    for c in rest:
        if len(chosen) >= 10:
            break
        c["selection_reason"] = "후보 부족으로 분야 제한 완화"
        chosen.append(c)
    by_category = {}
    for c in candidates:
        cat = c["category"]
        if cat not in by_category:
            by_category[cat] = []
        if len(by_category[cat]) < 10:
            by_category[cat].append(c)

    # 보수 / 진보 성향별 TOP 10 산출
    conservative_sources = {"chosun", "donga", "mk", "hankyung", "segye"}
    progressive_sources = {"hani", "khan", "seoul"}

    cons_candidates = []
    prog_candidates = []
    for issue in issues:
        articles = by_issue.get(issue.id, [])
        if not articles:
            continue
        if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", issue.title):
            continue

        c_articles = [a for a in articles if a.source_id in conservative_sources]
        if c_articles:
            k_c = len({a.source_id for a in c_articles})
            k_val = k_c if k_c >= 2 else 0
            h = (end - utc(issue.occurred)).total_seconds() / 3600
            bd = score(k_val, h, half)
            cons_candidates.append(
                {
                    "id": issue.id,
                    "title": issue.title,
                    "url": c_articles[0].url,
                    "category": issue.category,
                    "occurred": utc(issue.occurred).isoformat(),
                    "sources": sorted({sources.get(a.source_id, a.source_id) for a in c_articles}),
                    "articles": [a.id for a in c_articles],
                    "independent_origins": k_val,
                    "placement_evidence": [],
                    "confidence": f"보수 언론 {k_c}곳 보도" if k_c >= 2 else "보수 언론 단독 보도",
                    **bd,
                }
            )

        p_articles = [a for a in articles if a.source_id in progressive_sources]
        if p_articles:
            k_p = len({a.source_id for a in p_articles})
            k_val = k_p if k_p >= 2 else 0
            h = (end - utc(issue.occurred)).total_seconds() / 3600
            bd = score(k_val, h, half)
            prog_candidates.append(
                {
                    "id": issue.id,
                    "title": issue.title,
                    "url": p_articles[0].url,
                    "category": issue.category,
                    "occurred": utc(issue.occurred).isoformat(),
                    "sources": sorted({sources.get(a.source_id, a.source_id) for a in p_articles}),
                    "articles": [a.id for a in p_articles],
                    "independent_origins": k_val,
                    "placement_evidence": [],
                    "confidence": f"진보 언론 {k_p}곳 보도" if k_p >= 2 else "진보 언론 단독 보도",
                    **bd,
                }
            )

    cons_candidates.sort(
        key=lambda r: (
            -r["score"],
            -r["independent_origins"],
            -datetime.fromisoformat(r["occurred"]).timestamp(),
            r["id"],
        )
    )
    prog_candidates.sort(
        key=lambda r: (
            -r["score"],
            -r["independent_origins"],
            -datetime.fromisoformat(r["occurred"]).timestamp(),
            r["id"],
        )
    )

    by_category["보수"] = cons_candidates[:10]
    by_category["진보"] = prog_candidates[:10]

    for cat in ("정치", "경제", "사회", "국제", "연예", "스포츠", "산업/기술", "문화"):
        by_category[f"보수_{cat}"] = [c for c in cons_candidates if c.get("category") == cat][:10]
        by_category[f"진보_{cat}"] = [c for c in prog_candidates if c.get("category") == cat][:10]

    coverage = {
        s.id: s.state for s in all_sources if not (s.capabilities or {}).get("archived")
    }
    return {
        "entries": chosen,
        "by_category": by_category,
        "as_of": at.isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "version": "rules-1",
        "coverage": coverage,
        "notice": "수집 시작 이후 자료만 포함 · 제목 기반 순위 · 독립 취재/배치/영향 근거 부족",
    }
