import hashlib, ipaddress, socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import httpx


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def canonical(url):
    p = urlsplit(url)
    return urlunsplit(
        (
            p.scheme,
            p.netloc.lower(),
            p.path,
            urlencode(
                [
                    (k, v)
                    for k, v in parse_qsl(p.query)
                    if not k.startswith("utm_") and k not in ("fbclid", "gclid")
                ]
            ),
            "",
        )
    )


def validate_url(url, domain):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.username
        or p.password
        or p.port not in (None, 443)
        or not p.hostname
        or not (p.hostname == domain or p.hostname.endswith("." + domain))
    ):
        raise ValueError("허용되지 않은 URL")
    addresses = [
        info[4][0]
        for info in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    ]
    if not addresses:
        raise ValueError("DNS 결과 없음")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ValueError("비공개 IP 차단")
    return addresses[0]


def fetch(url, domain, headers=None):
    # Redirects are individually checked. Environment proxies are not inherited.
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as c:
        for _ in range(4):
            address = validate_url(url, domain)
            hostname = urlsplit(url).hostname
            pinned = httpx.URL(url).copy_with(host=address)
            # Pin the validated IP while preserving certificate verification and TLS SNI.
            request_headers = {**(headers or {}), "Host": hostname}
            with c.stream(
                "GET",
                pinned,
                headers=request_headers,
                extensions={"sni_hostname": hostname},
            ) as r:
                if r.status_code == 304:
                    return 304, b"", dict(r.headers)
                if r.is_redirect:
                    from urllib.parse import urljoin

                    url = urljoin(url, r.headers["location"])
                    continue
                r.raise_for_status()
                chunks = []
                size = 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError("응답 크기 제한")
                    chunks.append(chunk)
                return r.status_code, b"".join(chunks), dict(r.headers)
        raise ValueError("리다이렉트 제한")
