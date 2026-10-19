from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    youtube = "youtube"
    upload = "upload"


class SourceStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"
    downloaded = "downloaded"


class SegmentLang(str, Enum):
    kreol = "kreol"
    fr = "fr"
    en = "en"
    mix = "mix"


class SegmentStatus(str, Enum):
    raw = "raw"
    corrected = "corrected"
    validated = "validated"
    ignored = "ignored"


class SegmentSplit(str, Enum):
    train = "train"
    test = "test"


class ReviewStatus(str, Enum):
    todo = "todo"
    done = "done"
    validated = "validated"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, Enum):
    ingest = "ingest"
    transcribe = "transcribe"


class SourceCreateYouTube(BaseModel):
    youtube_url: str
    title: str | None = None
    license_notes: str | None = None
    default_lang: SegmentLang = SegmentLang.mix


class BulkSegmentLangUpdate(BaseModel):
    segment_ids: list[int] = Field(min_length=1)
    lang: SegmentLang


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    label: str
    display_name: str | None
    color: str


class SpeakerUpdate(BaseModel):
    display_name: str | None = None
    color: str | None = None


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    speaker_id: int
    start_sec: float
    end_sec: float
    audio_path: str | None
    text_raw: str | None
    text_corrected: str | None
    lang: SegmentLang
    status: SegmentStatus
    split: SegmentSplit = SegmentSplit.train
    model_version_used: str | None
    annotator: str | None
    review_comment: str | None = None
    review_comment_by: str | None = None


class SegmentUpdate(BaseModel):
    text_corrected: str | None = None
    lang: SegmentLang | None = None
    status: SegmentStatus | None = None
    annotator: str | None = None


class SegmentReviewCommentUpdate(BaseModel):
    comment: str | None = None


class ReviewUpdateRequest(BaseModel):
    status: ReviewStatus
    note: str | None = None


class ReviewHours(BaseModel):
    todo: float = 0.0
    done: float = 0.0
    validated: float = 0.0
    downloaded: float = 0.0
    downloaded_by_category: dict[str, float] = Field(default_factory=dict)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    label: str


class CategoryCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)


class SourceCategoryUpdate(BaseModel):
    category_id: int | None = None
    assigned_to_user_id: int | None = None


class PromoteRequest(BaseModel):
    source_ids: list[int] = Field(min_length=1)


class CatalogSampleRequest(BaseModel):
    target_hours: float = Field(gt=0, le=100)
    weights: dict[str, float] = Field(default_factory=dict)
    source_ids: list[int] | None = None


class CatalogSampleResult(BaseModel):
    source_ids: list[int]
    seconds_by_category: dict[str, float]
    total_seconds: float


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    job_type: JobType
    status: JobStatus
    progress: float
    phase: str | None = None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: SourceType
    source_url: str | None
    original_filename: str | None
    title: str | None
    duration_sec: float | None
    license_notes: str | None
    default_lang: SegmentLang
    audio_path: str | None
    status: SourceStatus
    error: str | None
    created_at: datetime
    review_status: ReviewStatus = ReviewStatus.todo
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    assigned_to_user_id: int | None = None
    assigned_to_email: str | None = None
    category: CategoryOut | None = None
    jobs: list[JobOut] = Field(default_factory=list)


class PipelinePhase(BaseModel):
    id: str
    label: str
    status: str
    progress: float | None = None
    detail: str | None = None


class SourcePipeline(BaseModel):
    overall_progress: float
    current_label: str
    phases: list[PipelinePhase]
    can_cancel: bool
    can_delete: bool
    error: str | None = None
    queue_position: int | None = None
    restart_note: str
    diarization_status: str | None = None
    diarization_error: str | None = None
    speaker_count: int | None = None


class SystemAlert(BaseModel):
    id: str
    severity: str
    message: str
    hint: str | None = None


class SourceListItem(BaseModel):
    id: int
    source_type: SourceType
    title: str | None
    original_filename: str | None
    duration_sec: float | None
    net_audio_sec: float = 0
    status: SourceStatus
    error: str | None = None
    created_at: datetime
    pipeline: SourcePipeline
    pipeline_meta: dict | None = None
    alerts: list[SystemAlert] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.todo
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    partial: bool = False
    touched_count: int = 0
    segment_count: int = 0
    comment_count: int = 0
    can_mark_done: bool = False
    category: CategoryOut | None = None
    source_url: str | None = None
    assigned_to_user_id: int | None = None
    assigned_to_email: str | None = None


class SourceListResponse(BaseModel):
    sources: list[SourceListItem]
    hours: ReviewHours


class EditorSession(BaseModel):
    """Payload shape shared by mock data and API — used by the React editor."""

    source: SourceOut
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]
    audio_url: str
    alerts: list[SystemAlert] = Field(default_factory=list)
    pipeline_meta: dict | None = None


class WaveformPeaksOut(BaseModel):
    """Precomputed peaks for WaveSurfer (skips browser decode)."""

    version: int = 1
    duration: float
    peaks: list[list[float]]


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hf_repo: str | None
    is_current: bool
    metrics_json: dict | None


class ModelActivateRequest(BaseModel):
    name: str


class ModelRegisterRequest(BaseModel):
    name: str
    hf_repo: str
    make_current: bool = True


class FrozenTestResult(BaseModel):
    source_id: int
    segment_count: int


class ExportAllResult(BaseModel):
    jsonl_path: str
    wav_count: int
    segment_count: int


class ExportResult(BaseModel):
    jsonl_path: str
    wav_count: int
    segment_count: int
    normalization_warnings: list[str] = Field(default_factory=list)


class WordChangeOut(BaseModel):
    original: str
    normalized: str
    start: int
    end: int


class NormalizePreview(BaseModel):
    segment_id: int
    original: str
    proposed: str
    changed: bool
    changes: list[WordChangeOut]
    unknown_tokens: list[str] = Field(default_factory=list)


class NormalizeRequest(BaseModel):
    apply: bool = False
    text: str | None = None


class BulkNormalizeResult(BaseModel):
    previews: list[NormalizePreview]
    applied_count: int = 0


class ExportCheckResult(BaseModel):
    validated_count: int
    needs_normalization_count: int
    segment_ids: list[int]


class UserRoleOut(str, Enum):
    admin = "admin"
    operator = "operator"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: UserRoleOut
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None = None
    hourly_rate_mur: float = 0
    in_progress_audio_sec: float = 0
    in_progress_hours: float = 0
    in_progress_mur: float = 0
    done_audio_sec: float = 0
    done_hours: float = 0
    done_mur: float = 0
    validated_audio_sec: float = 0
    validated_hours: float = 0
    owed_mur: float = 0
    can_rollback: bool = False
    last_event_kind: str | None = None
    last_event_at: datetime | None = None
    last_period_kind: str | None = None
    last_period_at: datetime | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreateRequest(BaseModel):
    email: str
    password: str = Field(min_length=4)
    role: UserRoleOut = UserRoleOut.operator


class UserUpdateRequest(BaseModel):
    email: str | None = None
    role: UserRoleOut | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)
    hourly_rate_mur: float | None = Field(default=None, ge=0)


class UserDeleteResult(BaseModel):
    mode: str  # hard | soft
    user: UserOut | None = None


class UserTimeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    kind: str
    bucket: str | None = None
    audio_sec: float
    source_id: int | None = None
    related_event_id: int | None = None
    created_by_user_id: int | None = None
    created_at: datetime


class UserTimeResetRequest(BaseModel):
    note: str | None = None


class PaymentPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    reset_event_id: int
    audio_sec: float
    hourly_rate_mur: float
    amount_mur: float
    period_started_at: datetime | None = None
    closed_at: datetime
    created_by_user_id: int | None = None
    note: str | None = None
    rolled_back_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Cleanup / lexicon
# ---------------------------------------------------------------------------


class LexiconKindOut(str, Enum):
    official = "official"
    alias = "alias"
    skip = "skip"


class LexiconOriginOut(str, Enum):
    pdf = "pdf"
    manual = "manual"
    corpus = "corpus"


class LexiconEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    kind: LexiconKindOut
    canonical: str | None = None
    origin: LexiconOriginOut
    note: str | None = None
    created_at: datetime | None = None


class LexiconEntryCreate(BaseModel):
    word: str
    kind: LexiconKindOut
    canonical: str | None = None
    origin: LexiconOriginOut = LexiconOriginOut.manual
    note: str | None = None
    occurrences_preview: bool = False


class LexiconEntryUpdate(BaseModel):
    word: str | None = None
    kind: LexiconKindOut | None = None
    canonical: str | None = None
    origin: LexiconOriginOut | None = None
    note: str | None = None


class LexiconImportRequest(BaseModel):
    text: str
    format: str = "auto"
    origin: LexiconOriginOut = LexiconOriginOut.manual


class LexiconImportResult(BaseModel):
    added: int
    updated: int


class LexiconSuggestionOut(BaseModel):
    word: str
    count: int


class AuditRuleOut(BaseModel):
    id: str
    label: str


class AuditRowOut(BaseModel):
    segment_id: int
    source_id: int
    source_title: str | None = None
    review_status: ReviewStatus
    status: SegmentStatus
    lang: SegmentLang
    start_sec: float
    end_sec: float
    duration_sec: float
    text: str
    kept: bool = False
    chars_per_sec: float | None = None
    char_count: int | None = None


class AuditKeepRequest(BaseModel):
    rule_id: str
    segment_ids: list[int] = Field(min_length=1)


class BulkIgnoreRequest(BaseModel):
    segment_ids: list[int] = Field(min_length=1)


class BulkActionResult(BaseModel):
    count: int


class MatchSpanOut(BaseModel):
    start: int
    end: int


class SearchHitOut(BaseModel):
    segment_id: int
    source_id: int
    source_title: str | None = None
    review_status: ReviewStatus
    status: SegmentStatus
    lang: SegmentLang | None = None
    text: str
    matches: list[MatchSpanOut]


class WordStatOut(BaseModel):
    word: str
    count: int
    segment_count: int
    lang_counts: dict[str, int]
    lexicon_status: str
    canonical: str | None = None
    cluster_key: str


class WordClusterOut(BaseModel):
    cluster_key: str
    total_count: int
    words: list[WordStatOut]


class SearchMode(str, Enum):
    word = "word"
    substring = "substring"
    regex = "regex"


class SearchRequest(BaseModel):
    query: str
    mode: SearchMode = SearchMode.word
    case_sensitive: bool = False
    source_id: int | None = None
    category_id: int | None = None
    lang: list[SegmentLang] | None = None
    status: list[SegmentStatus] | None = None
    review_status: list[ReviewStatus] | None = None
    split: list[SegmentSplit] | None = None
    include_validated_sources: bool = False
    limit: int = 500


class ReplacePreviewRequest(SearchRequest):
    replacement: str


class ReplacePreviewRow(BaseModel):
    segment_id: int
    source_id: int
    source_title: str | None = None
    review_status: ReviewStatus
    status: SegmentStatus
    text_before: str
    text_after: str
    matches: list[MatchSpanOut]


class ReplaceApplyItem(BaseModel):
    segment_id: int
    text_before: str | None = None
    match_indexes: list[int] | None = None


class ReplaceApplyRequest(BaseModel):
    query: str
    mode: SearchMode = SearchMode.word
    case_sensitive: bool = False
    replacement: str
    items: list[ReplaceApplyItem] = Field(min_length=1)


class ReplaceApplyResult(BaseModel):
    batch_id: str
    applied: int
    skipped: list[dict]


class RevisionBatchOut(BaseModel):
    batch_id: str
    created_at: datetime
    count: int
    query: str | None = None
    replacement: str | None = None
    created_by_email: str | None = None


class RollbackResult(BaseModel):
    batch_id: str
    restored: int
    skipped: list[dict]


