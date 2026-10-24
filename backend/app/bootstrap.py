import os
from argon2 import PasswordHasher
from sqlalchemy import select, text
from .db import *
from .sources import SOURCES


def bootstrap():
    password = os.environ.get("ADMIN_PASSWORD", "")
    secret = os.environ.get("SESSION_SECRET", "")
    if (
        len(password) < 14
        or password.lower() in ("changeme12345678", "password12345678")
        or len(secret) < 32
    ):
        raise RuntimeError(
            "ADMIN_PASSWORD 14자 이상 및 SESSION_SECRET 32자 이상 설정 필요"
        )
    with Session.begin() as db:
        if not db.scalar(select(User).limit(1)):
            db.add(
                User(
                    username=os.environ.get("ADMIN_USERNAME", "admin"),
                    password=PasswordHasher().hash(password),
                    admin=True,
                )
            )
        for old, replacement in {
            "joongang": "seoul",
            "hankook": "segye",
            "kbs": "sbs",
        }.items():
            source = db.get(Source, old)
            if source:
                source.enabled = False
                source.capabilities = {
                    **source.capabilities,
                    "archived": True,
                    "replaced_by": replacement,
                }
        for sid, name, domain, url in SOURCES:
            if not db.get(Source, sid):
                db.add(
                    Source(
                        id=sid,
                        name=name,
                        domain=domain,
                        endpoint=url,
                        capabilities={
                            "list": "검증 대기",
                            "body": "미지원",
                            "paper": "미지원",
                            "placement": "미지원",
                            "ai": "비활성",
                            "terms": "제목·원문 링크 한정 / 재이용 조건 추가 확인 필요",
                        },
                    )
                )
