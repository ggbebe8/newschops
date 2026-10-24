"""Limited live probe. Does not persist article bodies or full feeds."""

import json, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from backend.app.sources import SOURCES
from backend.app.security import fetch
from backend.app.collector import parse_feed


def probe(source):
    sid, name, domain, url = source
    at = time.monotonic()
    result = {
        "id": sid,
        "name": name,
        "endpoint": url,
        "checked": datetime.now(timezone.utc).isoformat(),
    }
    try:
        status, body, headers = fetch(url, domain)
        entries = parse_feed(body)
        result.update(
            status=status,
            count=len(entries),
            sample=[
                {"title": e["title"], "url": e["url"], "published": str(e["published"])}
                for e in entries[:1]
            ],
        )
    except Exception as exc:
        result.update(
            error=type(exc).__name__,
            http_status=getattr(getattr(exc, "response", None), "status_code", None),
        )
    result["duration_ms"] = int((time.monotonic() - at) * 1000)
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(probe, SOURCES))
    with open("docs/source-smoke.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    for r in results:
        print(
            r["name"],
            r.get("status", r.get("error")),
            r.get("count", r.get("http_status")),
        )
