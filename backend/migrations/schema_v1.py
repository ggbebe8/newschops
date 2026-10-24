import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    String,
    Text,
    JSON,
    ForeignKey,
    DateTime,
    Boolean,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./test.db"))
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = mapped_column(Integer, primary_key=True)
    username = mapped_column(String(100), unique=True)
    password = mapped_column(Text)
    admin = mapped_column(Boolean, default=False)
    active = mapped_column(Boolean, default=True)
    preferences = mapped_column(JSON, default=dict)


class Login(Base):
    __tablename__ = "sessions"
    token = mapped_column(String(64), primary_key=True)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf = mapped_column(String(64))
    expires = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = "sources"
    id = mapped_column(String(30), primary_key=True)
    name = mapped_column(Text)
    domain = mapped_column(Text)
    endpoint = mapped_column(Text)
    enabled = mapped_column(Boolean, default=True)
    state = mapped_column(Text, default="설정 필요")
    failures = mapped_column(Integer, default=0)
    last_attempt = mapped_column(DateTime(timezone=True), nullable=True)
    last_success = mapped_column(DateTime(timezone=True), nullable=True)
    last_new = mapped_column(DateTime(timezone=True), nullable=True)
    etag = mapped_column(Text, nullable=True)
    modified = mapped_column(Text, nullable=True)
    capabilities = mapped_column(JSON, default=dict)


class Issue(Base):
    __tablename__ = "issues"
    id = mapped_column(String(64), primary_key=True)
    title = mapped_column(Text)
    category = mapped_column(Text, default="사회")
    occurred = mapped_column(DateTime(timezone=True))
    discovered = mapped_column(DateTime(timezone=True), default=now)


class Article(Base):
    __tablename__ = "articles"
    id = mapped_column(String(64), primary_key=True)
    issue_id = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    source_id = mapped_column(ForeignKey("sources.id"))
    url = mapped_column(Text, unique=True)
    title = mapped_column(Text)
    origin = mapped_column(Text)
    published = mapped_column(DateTime(timezone=True), nullable=True)
    discovered = mapped_column(DateTime(timezone=True), default=now)
    collected = mapped_column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = "ranking_snapshots"
    __table_args__ = (UniqueConstraint("period", "slot"),)
    id = mapped_column(Integer, primary_key=True)
    period = mapped_column(Text)
    slot = mapped_column(String(64))
    created = mapped_column(DateTime(timezone=True), default=now)
    data = mapped_column(JSON)


class Run(Base):
    __tablename__ = "collection_runs"
    id = mapped_column(Integer, primary_key=True)
    source_id = mapped_column(ForeignKey("sources.id"))
    created = mapped_column(DateTime(timezone=True), default=now)
    status = mapped_column(Text)
    count = mapped_column(Integer, default=0)
    duration_ms = mapped_column(Integer, default=0)
    error = mapped_column(Text, nullable=True)


class State(Base):
    __tablename__ = "user_issue_states"
    __table_args__ = (UniqueConstraint("user_id", "issue_id"),)
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    issue_id = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    saved = mapped_column(Boolean, default=False)
    read = mapped_column(Boolean, default=False)
    hidden = mapped_column(Boolean, default=False)
    feedback = mapped_column(Text, default="")


class Job(Base):
    __tablename__ = "jobs"
    key = mapped_column(String(100), primary_key=True)
    payload = mapped_column(JSON, default=dict)
    updated = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "audit_events"
    id = mapped_column(Integer, primary_key=True)
    created = mapped_column(DateTime(timezone=True), default=now)
    actor = mapped_column(Integer, nullable=True)
    action = mapped_column(Text)
    data = mapped_column(JSON, default=dict)


class IssueEvent(Base):
    __tablename__ = "issue_events"
    id = mapped_column(Integer, primary_key=True)
    issue_id = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    created = mapped_column(DateTime(timezone=True), default=now)
    kind = mapped_column(Text)
    data = mapped_column(JSON, default=dict)


class OriginGroup(Base):
    __tablename__ = "origin_groups"
    id = mapped_column(String(64), primary_key=True)
    confidence = mapped_column(Text)
    evidence = mapped_column(JSON, default=dict)


class Placement(Base):
    __tablename__ = "placement_observations"
    id = mapped_column(Integer, primary_key=True)
    article_id = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    observed = mapped_column(DateTime(timezone=True), default=now)
    score = mapped_column(Integer)
    evidence_url = mapped_column(Text)


class SettingVersion(Base):
    __tablename__ = "settings_versions"
    id = mapped_column(Integer, primary_key=True)
    created = mapped_column(DateTime(timezone=True), default=now)
    data = mapped_column(JSON)


class AIResult(Base):
    __tablename__ = "ai_results"
    key = mapped_column(String(64), primary_key=True)
    created = mapped_column(DateTime(timezone=True), default=now)
    model = mapped_column(Text)
    status = mapped_column(Text)
    data = mapped_column(JSON, default=dict)
    estimated_microusd = mapped_column(Integer, default=0)
    actual_microusd = mapped_column(Integer, nullable=True)
