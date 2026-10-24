"""Read only the publicly visible newspaper table of contents, never gated pages/PDF."""

import re
from html.parser import HTMLParser
from datetime import datetime, timezone
from sqlalchemy import select
from .db import Session, Source, PaperEntry, Placement, Article, now
from .security import fetch, canonical, validate_url

URL = "https://www.donga.com/news"


class Node:
    def __init__(self, tag="", attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find(self, tag=None, cls=None):
        result = []
        if (tag is None or self.tag == tag) and (
            cls is None or cls in self.attrs.get("class", "").split()
        ):
            result.append(self)
        for c in self.children:
            if isinstance(c, Node):
                result.extend(c.find(tag, cls))
        return result


class Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in (
            "br",
            "hr",
            "meta",
            "link",
            "input",
            "img",
            "source",
            "wbr",
            "area",
            "base",
            "embed",
            "param",
        ):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_paper(html):
    tree = Tree()
    tree.feed(html)
    if "지면 목차" not in tree.root.text():
        raise ValueError("지면 목차 표식 없음")
    dates = tree.root.find("button", "date")
    if not dates:
        raise ValueError("지면 날짜 없음")
    match = re.fullmatch(
        r"\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*", dates[0].text()
    )
    if not match:
        raise ValueError("지면 날짜 형식 변경")
    date = datetime(*map(int, match.groups()), tzinfo=timezone.utc).strftime("%Y-%m-%d")
    results = []
    for container in tree.root.find("div", "desc_cont"):
        pages = container.find("span", "tit")
        if not pages:
            continue
        page = re.fullmatch(r"([A-Z]+)(\d+)", pages[0].text().strip())
        if not page:
            continue
        position = 0
        for listing in container.find("ul", "desc_list"):
            for a in listing.find("a"):
                url = canonical(a.attrs.get("href", ""))
                if (
                    not url.startswith("https://www.donga.com/news/")
                    or "/article/" not in url
                ):
                    continue
                position += 1
                results.append(
                    {
                        "date": date,
                        "section": page[1],
                        "page": int(page[2]),
                        "position": position,
                        "title": a.text().strip()[:1000],
                        "url": url,
                    }
                )
    if not results:
        raise ValueError("공개 지면 기사 목록 없음")
    return results


def article_key(url):
    m = re.search(r"/(\d{8})/(\d{8,})/\d+(?:$|\?)", url)
    return m[2] if m else url


def collect_paper():
    try:
        _, body, _ = fetch(URL, "donga.com")
        entries = parse_paper(body.decode("utf-8"))
        with Session.begin() as db:
            source = db.get(Source, "donga")
            articles = {
                article_key(a.url): a
                for a in db.scalars(select(Article).where(Article.source_id == "donga"))
            }
            for entry in entries:
                existing = db.scalar(
                    select(PaperEntry).where(
                        PaperEntry.date == entry["date"],
                        PaperEntry.section == entry["section"],
                        PaperEntry.page == entry["page"],
                        PaperEntry.position == entry["position"],
                    )
                )
                if not existing:
                    db.add(PaperEntry(**entry, evidence_url=URL))
                article = articles.get(article_key(entry["url"]))
                if (
                    article
                    and entry["section"] == "A"
                    and entry["page"] == 1
                    and not db.scalar(
                        select(Placement).where(
                            Placement.article_id == article.id,
                            Placement.evidence_url == URL,
                        )
                    )
                ):
                    db.add(Placement(article_id=article.id, score=85, evidence_url=URL))
            source.capabilities = {
                **source.capabilities,
                "paper": "정상 · 공개 목차",
                "paper_checked": now().isoformat(),
                "paper_date": entries[0]["date"],
                "placement": "1면 기타만 관측 / 주요 배치 미확인",
            }
    except Exception as exc:
        with Session.begin() as db:
            source = db.get(Source, "donga")
            if source:
                source.capabilities = {
                    **source.capabilities,
                    "paper": "확인 실패: " + type(exc).__name__,
                    "paper_checked": now().isoformat(),
                }
