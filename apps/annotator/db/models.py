import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.annotator.db.session import Base


class SourceType(str, enum.Enum):
    youtube = "youtube"
    upload = "upload"


class SourceStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"
    downloaded = "downloaded"


class JobType(str, enum.Enum):
    ingest = "ingest"
    transcribe = "transcribe"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class SegmentLang(str, enum.Enum):
    kreol = "kreol"
    fr = "fr"
    en = "en"
    mix = "mix"


class SegmentStatus(str, enum.Enum):
    raw = "raw"
    corrected = "corrected"
    validated = "validated"
    ignored = "ignored"


class SegmentSplit(str, enum.Enum):
    train = "train"
    test = "test"


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"


class ReviewStatus(str, enum.Enum):
    todo = "todo"
    done = "done"
    validated = "validated"


class UserTimeEventKind(str, enum.Enum):
    credit = "credit"
    reverse = "reverse"
    reset = "reset"
    rollback = "rollback"


class UserTimeBucket(str, enum.Enum):
    done = "done"
    validated = "validated"


class TextRevisionKind(str, enum.Enum):
    replace = "replace"
    rollback = "rollback"


class LexiconKind(str, enum.Enum):
    official = "official"
    alias = "alias"
    skip = "skip"


class LexiconOrigin(str, enum.Enum):
    pdf = "pdf"
    manual = "manual"
    corpus = "corpus"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.operator, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hourly_rate_mur: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    time_events: Mapped[list["UserTimeEvent"]] = relationship(
        back_populates="user",
        foreign_keys="UserTimeEvent.user_id",
        cascade="all, delete-orphan",
    )
    payment_periods: Mapped[list["PaymentPeriod"]] = relationship(
        back_populates="user",
        foreign_keys="PaymentPeriod.user_id",
        cascade="all, delete-orphan",
    )


class UserTimeEvent(Base):
    __tablename__ = "user_time_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[UserTimeEventKind] = mapped_column(Enum(UserTimeEventKind), nullable=False)
    bucket: Mapped[UserTimeBucket | None] = mapped_column(Enum(UserTimeBucket), nullable=True)
    audio_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    related_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_time_events.id"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(
        back_populates="time_events",
        foreign_keys=[user_id],
    )


class PaymentPeriod(Base):
    """Frozen payroll snapshot created when an admin resets validated time."""

    __tablename__ = "payment_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reset_event_id: Mapped[int] = mapped_column(
        ForeignKey("user_time_events.id"), nullable=False, unique=True
    )
    audio_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hourly_rate_mur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    amount_mur: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    period_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(
        back_populates="payment_periods",
        foreign_keys=[user_id],
    )
    reset_event: Mapped["UserTimeEvent"] = relationship(foreign_keys=[reset_event_id])


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)

    sources: Mapped[list["Source"]] = relationship(back_populates="category")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    original_filename: Mapped[str | None] = mapped_column(String(512))
    dedupe_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    title: Mapped[str | None] = mapped_column(String(512))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    license_notes: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    audio_path: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus), default=SourceStatus.pending, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    default_lang: Mapped[SegmentLang] = mapped_column(
        Enum(SegmentLang), default=SegmentLang.mix, nullable=False
    )
    pipeline_meta: Mapped[dict | None] = mapped_column(JSON)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.todo, nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(256))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(Text)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["Category | None"] = relationship(back_populates="sources")
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_user_id])
    jobs: Mapped[list["Job"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    speakers: Mapped[list["Speaker"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    @property
    def assigned_to_email(self) -> str | None:
        return self.assignee.email if self.assignee is not None else None


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.pending, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    phase: Mapped[str | None] = mapped_column(String(256))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="jobs")


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")

    source: Mapped["Source"] = relationship(back_populates="speakers")
    segments: Mapped[list["Segment"]] = relationship(back_populates="speaker")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id"), nullable=False, index=True)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(1024))
    text_raw: Mapped[str | None] = mapped_column(Text)
    text_corrected: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[SegmentLang] = mapped_column(
        Enum(SegmentLang), default=SegmentLang.mix, nullable=False
    )
    status: Mapped[SegmentStatus] = mapped_column(
        Enum(SegmentStatus), default=SegmentStatus.raw, nullable=False
    )
    split: Mapped["SegmentSplit"] = mapped_column(
        Enum(SegmentSplit), default=SegmentSplit.train, nullable=False
    )
    model_version_used: Mapped[str | None] = mapped_column(String(256))
    annotator: Mapped[str | None] = mapped_column(String(128))
    review_comment: Mapped[str | None] = mapped_column(Text)
    review_comment_by: Mapped[str | None] = mapped_column(String(256))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="segments")
    speaker: Mapped["Speaker"] = relationship(back_populates="segments")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    hf_repo: Mapped[str | None] = mapped_column(String(512))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SegmentAuditDismissal(Base):
    """Marks a segment as Keep for an audit rule so it no longer appears in that list."""

    __tablename__ = "segment_audit_dismissals"
    __table_args__ = (
        UniqueConstraint("segment_id", "rule_id", name="uq_segment_audit_dismissal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    segment: Mapped["Segment"] = relationship()


class TextRevision(Base):
    """Audit log for mass search/replace (and rollbacks)."""

    __tablename__ = "text_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"), nullable=False, index=True)
    text_before: Mapped[str] = mapped_column(Text, nullable=False)
    text_after: Mapped[str] = mapped_column(Text, nullable=False)
    status_before: Mapped[SegmentStatus] = mapped_column(Enum(SegmentStatus), nullable=False)
    kind: Mapped[TextRevisionKind] = mapped_column(
        Enum(TextRevisionKind), nullable=False, default=TextRevisionKind.replace
    )
    query: Mapped[str | None] = mapped_column(String(512), nullable=True)
    replacement: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    segment: Mapped["Segment"] = relationship()


class LexiconEntry(Base):
    """DB-backed Lortograf lexicon (official forms, ASR aliases, skip words)."""

    __tablename__ = "lexicon_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    kind: Mapped[LexiconKind] = mapped_column(Enum(LexiconKind), nullable=False)
    canonical: Mapped[str | None] = mapped_column(String(128), nullable=True)
    origin: Mapped[LexiconOrigin] = mapped_column(
        Enum(LexiconOrigin), nullable=False, default=LexiconOrigin.manual
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
