from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from apps.annotator.api.auth import (
    SESSION_USER_KEY,
    hash_password,
    require_admin,
    require_user,
    verify_password,
)
from apps.annotator.api.assignment import (
    AssignmentError,
    operator_can_access_source,
    operator_can_edit_source,
    set_source_assignment,
)
from apps.annotator.api.normalizer_service import (
    export_normalization_check,
    normalize_segment,
    normalize_source,
    normalization_warnings,
)
from apps.annotator.api.dedupe import DuplicateSourceError
from apps.annotator.api.review import (
    ReviewError,
    aggregate_review_hours,
    can_validate_segment,
    set_review_status,
    set_segment_review_comment,
)
from apps.annotator.api.categories import create_category, list_categories
from apps.annotator.api.source_management import (
    aggregate_catalog_hours,
    cancel_source,
    catalog_sample_for_sources,
    delete_source,
    list_sources_with_pipeline,
    promote_sources,
    resume_source,
    retranscribe_source,
    set_source_category,
)
from apps.annotator.api.schemas import (
    AuditKeepRequest,
    AuditRowOut,
    AuditRuleOut,
    BulkActionResult,
    BulkIgnoreRequest,
    BulkNormalizeResult,
    BulkSegmentLangUpdate,
    CatalogSampleRequest,
    CatalogSampleResult,
    CategoryCreateRequest,
    CategoryOut,
    EditorSession,
    ExportAllResult,
    ExportCheckResult,
    ExportResult,
    FrozenTestResult,
    JobOut,
    LexiconEntryCreate,
    LexiconEntryOut,
    LexiconEntryUpdate,
    LexiconImportRequest,
    LexiconImportResult,
    LexiconSuggestionOut,
    LoginRequest,
    ModelActivateRequest,
    ModelRegisterRequest,
    ModelVersionOut,
    NormalizePreview,
    NormalizeRequest,
    PromoteRequest,
    ReplaceApplyRequest,
    ReplaceApplyResult,
    ReplacePreviewRequest,
    ReplacePreviewRow,
    ReviewHours,
    ReviewUpdateRequest,
    RevisionBatchOut,
    RollbackResult,
    SearchHitOut,
    SearchRequest,
    SegmentOut,
    SegmentReviewCommentUpdate,
    SegmentUpdate,
    SourceCategoryUpdate,
    SourceCreateYouTube,
    SourceListItem,
    SourceListResponse,
    SourceOut,
    SpeakerOut,
    SpeakerUpdate,
    UserCreateRequest,
    UserDeleteResult,
    UserOut,
    UserRoleOut,
    UserTimeEventOut,
    UserTimeResetRequest,
    UserUpdateRequest,
    PaymentPeriodOut,
    WaveformPeaksOut,
    WordClusterOut,
    WordStatOut,
)
from apps.annotator.api.services import (
    bulk_update_segment_lang,
    create_source_from_upload,
    create_source_from_youtube,
    export_validated_segments,
    export_all_validated_segments,
    get_editor_session,
    get_source_detail,
    mark_source_as_frozen_test,
    register_model_version,
)
from apps.annotator.api.system_health import collect_global_alerts, normalizer_load_error, pyannote_import_error
from apps.annotator.config import get_settings
from apps.annotator.api.user_management import (
    UserManagementError,
    delete_user,
    restore_user,
)
from apps.annotator.api.user_time import (
    UserTimeError,
    list_payment_periods,
    list_time_events,
    reset_validated,
    rollback_reset,
    user_time_summary,
)
from apps.annotator.db.models import (
    Job,
    JobStatus,
    ModelVersion,
    ReviewStatus,
    Segment,
    SegmentLang,
    SegmentStatus,
    Source,
    SourceStatus,
    Speaker,
    User,
    UserRole,
)
from apps.annotator.db.session import get_db
from apps.annotator.pipeline.inference import verify_audio_signature
from apps.annotator.worker.heartbeat import is_worker_alive, read_heartbeat

router = APIRouter(prefix="/api")


def _user_out(db: Session, user: User) -> UserOut:
    summary = user_time_summary(db, user)
    return UserOut(
        id=user.id,
        email=user.email,
        role=UserRoleOut(user.role.value),
        is_active=user.is_active,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
        **summary,
    )


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    worker_alive = is_worker_alive()
    pending = (
        db.query(Job)
        .filter(Job.status.in_([JobStatus.pending, JobStatus.running]))
        .count()
    )
    alerts = collect_global_alerts(worker_alive=worker_alive, needs_worker=pending > 0)
    status = "ok"
    if any(a["severity"] == "error" for a in alerts):
        status = "degraded"
    return {"status": status, "worker_alive": worker_alive, "alerts": alerts}


@router.get("/internal/audio/{source_id}")
def internal_audio(
    source_id: int,
    exp: int,
    sig: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Signed short-lived WAV URL for RunPod workers (no session cookie)."""
    if not verify_audio_signature(source_id, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")
    source = db.get(Source, source_id)
    if not source or not source.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    path = Path(source.audio_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file missing")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@router.post("/auth/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> UserOut:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or user.deleted_at is not None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session[SESSION_USER_KEY] = user.id
    return _user_out(db, user)


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(db: Session = Depends(get_db), user: User = Depends(require_user)) -> UserOut:
    return _user_out(db, user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserOut]:
    users = db.query(User).order_by(User.email).all()
    return [_user_out(db, u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserOut:
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole(payload.role.value),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    if "is_active" in data and data["is_active"] is False and user.id == current.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    if "email" in data and data["email"] is not None:
        email = str(data["email"]).strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email required")
        other = db.query(User).filter(User.email == email, User.id != user.id).first()
        if other:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = email
    if "role" in data and data["role"] is not None:
        user.role = UserRole(data["role"].value if isinstance(data["role"], UserRoleOut) else data["role"])
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = data["is_active"]
        if data["is_active"] is True:
            user.deleted_at = None
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
    if "hourly_rate_mur" in data and data["hourly_rate_mur"] is not None:
        user.hourly_rate_mur = data["hourly_rate_mur"]
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


@router.delete("/users/{user_id}", response_model=UserDeleteResult)
def remove_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> UserDeleteResult:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        mode, remaining = delete_user(db, user, actor=current)
    except UserManagementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    if mode == "hard":
        return UserDeleteResult(mode="hard", user=None)
    db.refresh(remaining)
    return UserDeleteResult(mode="soft", user=_user_out(db, remaining))


@router.post("/users/{user_id}/restore", response_model=UserOut)
def post_restore_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    restore_user(db, user)
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


@router.get("/users/{user_id}/time-events", response_model=list[UserTimeEventOut])
def get_user_time_events(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserTimeEventOut]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    events = list_time_events(db, user_id)
    return [
        UserTimeEventOut(
            id=e.id,
            user_id=e.user_id,
            kind=e.kind.value,
            bucket=e.bucket.value if e.bucket else None,
            audio_sec=float(e.audio_sec),
            source_id=e.source_id,
            related_event_id=e.related_event_id,
            created_by_user_id=e.created_by_user_id,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/users/{user_id}/time-reset", response_model=UserOut)
def post_user_time_reset(
    user_id: int,
    payload: UserTimeResetRequest = UserTimeResetRequest(),
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    reset_validated(db, user=user, created_by=current, note=payload.note)
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


@router.post("/users/{user_id}/time-rollback", response_model=UserOut)
def post_user_time_rollback(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        rollback_reset(db, user=user, created_by=current)
    except UserTimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


@router.get("/users/{user_id}/payment-periods", response_model=list[PaymentPeriodOut])
def get_user_payment_periods(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_user),
) -> list[PaymentPeriodOut]:
    if current.role != UserRole.admin and current.id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_admin = current.role == UserRole.admin
    periods = list_payment_periods(db, user_id)
    return [
        PaymentPeriodOut(
            id=p.id,
            user_id=p.user_id,
            reset_event_id=p.reset_event_id,
            audio_sec=float(p.audio_sec),
            hourly_rate_mur=float(p.hourly_rate_mur),
            amount_mur=float(p.amount_mur),
            period_started_at=p.period_started_at,
            closed_at=p.closed_at,
            created_by_user_id=p.created_by_user_id,
            note=p.note if is_admin else None,
            rolled_back_at=p.rolled_back_at,
            created_at=p.created_at,
        )
        for p in periods
    ]


@router.get("/config")
def config(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    settings = get_settings()
    heartbeat = read_heartbeat()
    worker_alive = is_worker_alive()
    pending = (
        db.query(Job)
        .filter(Job.status.in_([JobStatus.pending, JobStatus.running]))
        .count()
    )
    processing = db.query(Source).filter(Source.status == SourceStatus.processing).count()
    alerts = collect_global_alerts(
        worker_alive=worker_alive,
        needs_worker=pending > 0 or processing > 0,
    )
    return {
        "whisper_model": settings.whisper_model,
        "enable_diarization": settings.enable_diarization,
        "hf_token_configured": bool(settings.hf_token),
        "ytdlp_node_configured": __import__(
            "apps.annotator.pipeline.yt_dlp_args", fromlist=["resolve_node_executable"]
        ).resolve_node_executable()
        is not None,
        "diarization_ready": (
            bool(settings.enable_diarization and settings.hf_token)
            if (settings.inference_backend or "local").lower().strip() == "runpod"
            else bool(
                settings.enable_diarization
                and settings.hf_token
                and pyannote_import_error() is None
            )
        ),
        "inference_backend": (settings.inference_backend or "local").lower().strip(),
        "worker_alive": worker_alive,
        "worker_last_seen": heartbeat.isoformat() if heartbeat else None,
        "alerts": alerts,
    }


@router.get("/sources", response_model=SourceListResponse)
def list_sources(
    assigned_to: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> SourceListResponse:
    try:
        items = list_sources_with_pipeline(db, user=user, assigned_to=assigned_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    hours = aggregate_review_hours(db)
    downloaded_total, by_cat = aggregate_catalog_hours(db)
    hours["downloaded"] = downloaded_total
    hours["downloaded_by_category"] = by_cat
    return SourceListResponse(
        sources=[SourceListItem(**item) for item in items],
        hours=ReviewHours(**hours),
    )


@router.get("/categories", response_model=list[CategoryOut])
def get_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_user),
) -> list:
    return list_categories(db)


@router.post("/categories", response_model=CategoryOut)
def post_category(
    payload: CategoryCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CategoryOut:
    slug = payload.slug.strip().lower().replace(" ", "-")
    if not slug:
        raise HTTPException(status_code=400, detail="slug required")
    return create_category(db, slug=slug, label=payload.label.strip())


@router.post("/sources/promote", response_model=list[SourceOut])
def promote_sources_route(
    payload: PromoteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list:
    try:
        sources = promote_sources(db, payload.source_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [get_source_detail(db, s.id) for s in sources]  # type: ignore[misc]


@router.post("/sources/catalog-sample", response_model=CatalogSampleResult)
def catalog_sample_route(
    payload: CatalogSampleRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> CatalogSampleResult:
    result = catalog_sample_for_sources(
        db,
        target_hours=payload.target_hours,
        weights=payload.weights,
        source_ids=payload.source_ids,
    )
    return CatalogSampleResult(**result)


@router.patch("/sources/{source_id}", response_model=SourceOut)
def patch_source(
    source_id: int,
    payload: SourceCategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data:
        if user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Admin only")
        try:
            updated = set_source_category(db, source_id, data["category_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Source not found")
        source = updated

    if "assigned_to_user_id" in data:
        try:
            set_source_assignment(
                db,
                source,
                assigned_to_user_id=data["assigned_to_user_id"],
                actor=user,
            )
        except AssignmentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    detail = get_source_detail(db, source_id)
    return detail  # type: ignore[return-value]


@router.post("/sources/{source_id}/review", response_model=SourceOut)
def update_source_review(
    source_id: int,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        return set_review_status(
            db,
            source,
            ReviewStatus(payload.status.value),
            user,
            note=payload.note,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/youtube", response_model=SourceOut)
def create_youtube_source(
    payload: SourceCreateYouTube,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Source:
    try:
        return create_source_from_youtube(
            db,
            youtube_url=payload.youtube_url,
            title=payload.title,
            license_notes=payload.license_notes,
            default_lang=payload.default_lang,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sources/upload", response_model=SourceOut)
async def create_upload_source(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    license_notes: str | None = Form(None),
    default_lang: SegmentLang = Form(SegmentLang.mix),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Source:
    settings = get_settings()
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    temp_path = settings.uploads_dir / f"tmp_{datetime.now(timezone.utc).timestamp()}{suffix}"
    content = await file.read()
    temp_path.write_bytes(content)
    try:
        return create_source_from_upload(
            db,
            filename=file.filename or "upload",
            upload_path=temp_path,
            title=title,
            license_notes=license_notes,
            default_lang=default_lang,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Source:
    source = get_source_detail(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    return source


@router.get("/sources/{source_id}/session", response_model=EditorSession)
def get_session(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> EditorSession:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    session = get_editor_session(db, source_id)
    if not session:
        raise HTTPException(status_code=404, detail="Source not found")
    return EditorSession(**session)


@router.get("/sources/{source_id}/audio")
def get_source_audio(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> FileResponse:
    source = db.get(Source, source_id)
    if not source or not source.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    path = Path(source.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@router.get("/sources/{source_id}/peaks", response_model=WaveformPeaksOut)
def get_source_peaks(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> WaveformPeaksOut:
    from apps.annotator.pipeline.waveform_peaks import load_or_create_peaks

    source = db.get(Source, source_id)
    if not source or not source.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    path = Path(source.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing")
    try:
        payload = load_or_create_peaks(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=f"Peaks generation failed: {exc}") from exc
    return WaveformPeaksOut(**payload)


@router.get("/sources/{source_id}/segments", response_model=list[SegmentOut])
def list_segments(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[Segment]:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    return (
        db.query(Segment)
        .filter(Segment.source_id == source_id)
        .order_by(Segment.start_sec)
        .all()
    )


@router.get("/sources/{source_id}/speakers", response_model=list[SpeakerOut])
def list_speakers(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[Speaker]:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    return db.query(Speaker).filter(Speaker.source_id == source_id).order_by(Speaker.id).all()


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
def update_segment(
    segment_id: int,
    payload: SegmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Segment:
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    source = db.get(Source, segment.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_edit_source(source, user):
        raise HTTPException(status_code=403, detail="Claim or get assigned to this source first")
    if source.review_status == ReviewStatus.validated and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Validated sources are read-only for operators")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "annotator":
            continue
        setattr(segment, field, value)
    if segment.status == SegmentStatus.validated and not can_validate_segment(segment):
        raise HTTPException(
            status_code=400,
            detail="Cannot validate a segment with empty text; use ignored instead",
        )
    segment.annotator = user.email
    db.commit()
    db.refresh(segment)
    return segment


@router.patch("/segments/{segment_id}/review-comment", response_model=SegmentOut)
def update_segment_review_comment(
    segment_id: int,
    payload: SegmentReviewCommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Segment:
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    try:
        return set_segment_review_comment(db, segment, payload.comment, user)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/sources/{source_id}/segments/lang", response_model=list[SegmentOut])
def bulk_update_segments_lang(
    source_id: int,
    payload: BulkSegmentLangUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[Segment]:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_edit_source(source, user):
        raise HTTPException(status_code=403, detail="Claim or get assigned to this source first")
    if source.review_status == ReviewStatus.validated and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Validated sources are read-only for operators")
    try:
        return bulk_update_segment_lang(db, source_id, payload.segment_ids, payload.lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
def update_speaker(
    speaker_id: int,
    payload: SpeakerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_user),
) -> Speaker:
    speaker = db.get(Speaker, speaker_id)
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(speaker, field, value)
    db.commit()
    db.refresh(speaker)
    return speaker


@router.post("/sources/{source_id}/cancel", response_model=SourceOut)
def cancel_source_route(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Source:
    source = cancel_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    detail = get_source_detail(db, source_id)
    return detail  # type: ignore[return-value]


@router.post("/sources/{source_id}/resume", response_model=SourceOut)
def resume_source_route(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Source:
    try:
        source = resume_source(db, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    detail = get_source_detail(db, source_id)
    return detail  # type: ignore[return-value]


@router.post("/sources/{source_id}/retranscribe", response_model=SourceOut)
def retranscribe_source_route(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Source:
    try:
        source = retranscribe_source(db, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    detail = get_source_detail(db, source_id)
    return detail  # type: ignore[return-value]


@router.delete("/sources/{source_id}", status_code=204)
def delete_source_route(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    if not delete_source(db, source_id):
        raise HTTPException(status_code=404, detail="Source not found")


@router.post("/segments/{segment_id}/normalize", response_model=NormalizePreview)
def normalize_one_segment(
    segment_id: int,
    payload: NormalizeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user),
) -> NormalizePreview:
    norm_err = normalizer_load_error(db)
    if norm_err:
        raise HTTPException(status_code=503, detail=norm_err)
    try:
        result = normalize_segment(
            db, segment_id, apply=payload.apply, text=payload.text
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Normalization failed: {exc}") from exc
    if not result:
        raise HTTPException(status_code=404, detail="Segment not found")
    return NormalizePreview(**result)


@router.post("/sources/{source_id}/normalize", response_model=BulkNormalizeResult)
def normalize_all_segments(
    source_id: int,
    payload: NormalizeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user),
) -> BulkNormalizeResult:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    norm_err = normalizer_load_error(db)
    if norm_err:
        raise HTTPException(status_code=503, detail=norm_err)
    try:
        result = normalize_source(db, source_id, apply=payload.apply)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Normalization failed: {exc}") from exc
    return BulkNormalizeResult(**result)


@router.get("/sources/{source_id}/export-check", response_model=ExportCheckResult)
def check_export_normalization(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ExportCheckResult:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    norm_err = normalizer_load_error()
    if norm_err:
        raise HTTPException(status_code=503, detail=norm_err)
    try:
        payload = export_normalization_check(db, source_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Normalization check failed: {exc}") from exc
    return ExportCheckResult(**payload)


@router.post("/sources/{source_id}/mark-frozen-test", response_model=FrozenTestResult)
def mark_frozen_test_route(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> FrozenTestResult:
    try:
        count = mark_source_as_frozen_test(db, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FrozenTestResult(source_id=source_id, segment_count=count)


@router.post("/export/all", response_model=ExportAllResult)
def export_all_sources(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ExportAllResult:
    jsonl_path, wav_count, segment_count = export_all_validated_segments(db)
    return ExportAllResult(
        jsonl_path=str(jsonl_path),
        wav_count=wav_count,
        segment_count=segment_count,
    )


@router.post("/sources/{source_id}/export", response_model=ExportResult)
def export_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ExportResult:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    warnings = normalization_warnings(db, source_id)
    jsonl_path, wav_count = export_validated_segments(db, source_id)
    segment_count = (
        db.query(Segment)
        .filter(Segment.source_id == source_id, Segment.status == SegmentStatus.validated)
        .count()
    )
    return ExportResult(
        jsonl_path=str(jsonl_path),
        wav_count=wav_count,
        segment_count=segment_count,
        normalization_warnings=warnings,
    )


@router.get("/models", response_model=list[ModelVersionOut])
def list_models(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ModelVersion]:
    return db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()


@router.post("/models", response_model=ModelVersionOut)
def register_model(
    payload: ModelRegisterRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ModelVersion:
    return register_model_version(
        db,
        name=payload.name,
        hf_repo=payload.hf_repo,
        make_current=payload.make_current,
    )


@router.post("/models/current", response_model=ModelVersionOut)
def activate_model(
    payload: ModelActivateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ModelVersion:
    model = db.query(ModelVersion).filter(ModelVersion.name == payload.name).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model version not found")
    db.query(ModelVersion).update({ModelVersion.is_current: False})
    model.is_current = True
    db.commit()
    db.refresh(model)
    return model


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Cleanup + lexicon (admin)
# ---------------------------------------------------------------------------


def _segment_filter_from_query(
    source_id: int | None = None,
    category_id: int | None = None,
    lang: list[str] | None = None,
    status: list[str] | None = None,
    review_status: list[str] | None = None,
    split: list[str] | None = None,
    include_validated_sources: bool = False,
):
    from apps.annotator.api.cleanup import SegmentFilter

    return SegmentFilter(
        source_id=source_id,
        category_id=category_id,
        lang=lang,
        status=status,
        review_status=review_status,
        split=split,
        include_validated_sources=include_validated_sources,
    )


@router.get("/cleanup/audit/rules", response_model=list[AuditRuleOut])
def cleanup_audit_rules(_: User = Depends(require_admin)) -> list[AuditRuleOut]:
    from apps.annotator.api.cleanup import list_audit_rules

    return [AuditRuleOut(**r) for r in list_audit_rules()]


@router.get("/cleanup/audit", response_model=list[AuditRowOut])
def cleanup_audit(
    rule: str = "short_segment",
    max_sec: float | None = None,
    min_chars_per_sec: float | None = None,
    include_kept: bool = False,
    source_id: int | None = None,
    category_id: int | None = None,
    lang: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    review_status: list[str] | None = Query(None),
    split: list[str] | None = Query(None),
    include_validated_sources: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AuditRowOut]:
    from apps.annotator.api.cleanup import audit_find

    filt = _segment_filter_from_query(
        source_id, category_id, lang, status, review_status, split, include_validated_sources
    )
    params: dict = {}
    if max_sec is not None:
        params["max_sec"] = max_sec
    elif rule == "short_segment":
        params["max_sec"] = 1.0
    elif rule == "dense_text":
        params["max_sec"] = 2.0
    if min_chars_per_sec is not None:
        params["min_chars_per_sec"] = min_chars_per_sec
    try:
        rows = audit_find(
            db,
            rule_id=rule,
            filt=filt,
            params=params,
            include_kept=include_kept,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [AuditRowOut(**r) for r in rows]


@router.post("/cleanup/audit/keep", response_model=BulkActionResult)
def cleanup_audit_keep(
    payload: AuditKeepRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BulkActionResult:
    from apps.annotator.api.cleanup import keep_segments

    try:
        count = keep_segments(
            db, rule_id=payload.rule_id, segment_ids=payload.segment_ids, user=user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BulkActionResult(count=count)


@router.delete("/cleanup/audit/keep", response_model=BulkActionResult)
def cleanup_audit_unkeep(
    payload: AuditKeepRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> BulkActionResult:
    from apps.annotator.api.cleanup import unkeep_segments

    try:
        count = unkeep_segments(
            db, rule_id=payload.rule_id, segment_ids=payload.segment_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BulkActionResult(count=count)


@router.post("/cleanup/segments/ignore", response_model=BulkActionResult)
def cleanup_bulk_ignore(
    payload: BulkIgnoreRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BulkActionResult:
    from apps.annotator.api.cleanup import bulk_ignore_segments

    count = bulk_ignore_segments(db, segment_ids=payload.segment_ids, user=user)
    return BulkActionResult(count=count)


@router.get("/segments/{segment_id}/audio")
def get_segment_audio(
    segment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> FileResponse:
    from apps.annotator.api.cleanup import ensure_segment_clip

    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    source = db.get(Source, seg.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not operator_can_access_source(source, user):
        raise HTTPException(status_code=403, detail="Source is assigned to another operator")
    try:
        path = ensure_segment_clip(db, segment_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to cut clip: {exc}") from exc
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@router.get("/cleanup/vocabulary", response_model=list[WordStatOut])
def cleanup_vocabulary(
    min_count: int = 1,
    lexicon_status: str = "all",
    q: str | None = None,
    source_id: int | None = None,
    category_id: int | None = None,
    lang: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    review_status: list[str] | None = Query(None),
    split: list[str] | None = Query(None),
    include_validated_sources: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[WordStatOut]:
    from apps.annotator.api.cleanup import vocabulary_stats

    filt = _segment_filter_from_query(
        source_id, category_id, lang, status, review_status, split, include_validated_sources
    )
    rows = vocabulary_stats(
        db, filt=filt, min_count=min_count, lexicon_status=lexicon_status, q=q
    )
    return [WordStatOut(**r) for r in rows]


@router.get("/cleanup/vocabulary/clusters", response_model=list[WordClusterOut])
def cleanup_vocabulary_clusters(
    min_size: int = 2,
    source_id: int | None = None,
    category_id: int | None = None,
    lang: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    review_status: list[str] | None = Query(None),
    split: list[str] | None = Query(None),
    include_validated_sources: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[WordClusterOut]:
    from apps.annotator.api.cleanup import vocabulary_clusters

    filt = _segment_filter_from_query(
        source_id, category_id, lang, status, review_status, split, include_validated_sources
    )
    rows = vocabulary_clusters(db, filt=filt, min_size=min_size)
    return [WordClusterOut(**r) for r in rows]


@router.get("/cleanup/vocabulary/{word}/occurrences", response_model=list[SearchHitOut])
def cleanup_word_occurrences(
    word: str,
    limit: int = 100,
    source_id: int | None = None,
    category_id: int | None = None,
    lang: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    review_status: list[str] | None = Query(None),
    split: list[str] | None = Query(None),
    include_validated_sources: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SearchHitOut]:
    from apps.annotator.api.cleanup import word_occurrences

    filt = _segment_filter_from_query(
        source_id, category_id, lang, status, review_status, split, include_validated_sources
    )
    rows = word_occurrences(db, word=word, filt=filt, limit=limit)
    return [SearchHitOut(**r) for r in rows]


@router.post("/cleanup/search", response_model=list[SearchHitOut])
def cleanup_search(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SearchHitOut]:
    from apps.annotator.api.cleanup import SearchSpec, search_segments

    filt = _segment_filter_from_query(
        payload.source_id,
        payload.category_id,
        [x.value for x in payload.lang] if payload.lang else None,
        [x.value for x in payload.status] if payload.status else None,
        [x.value for x in payload.review_status] if payload.review_status else None,
        [x.value for x in payload.split] if payload.split else None,
        payload.include_validated_sources,
    )
    try:
        rows = search_segments(
            db,
            spec=SearchSpec(
                query=payload.query,
                mode=payload.mode.value,
                case_sensitive=payload.case_sensitive,
            ),
            filt=filt,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [SearchHitOut(**r) for r in rows]


@router.post("/cleanup/replace/preview", response_model=list[ReplacePreviewRow])
def cleanup_replace_preview(
    payload: ReplacePreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ReplacePreviewRow]:
    from apps.annotator.api.cleanup import SearchSpec, replace_preview

    filt = _segment_filter_from_query(
        payload.source_id,
        payload.category_id,
        [x.value for x in payload.lang] if payload.lang else None,
        [x.value for x in payload.status] if payload.status else None,
        [x.value for x in payload.review_status] if payload.review_status else None,
        [x.value for x in payload.split] if payload.split else None,
        payload.include_validated_sources,
    )
    try:
        rows = replace_preview(
            db,
            spec=SearchSpec(
                query=payload.query,
                mode=payload.mode.value,
                case_sensitive=payload.case_sensitive,
            ),
            replacement=payload.replacement,
            filt=filt,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [ReplacePreviewRow(**r) for r in rows]


@router.post("/cleanup/replace/apply", response_model=ReplaceApplyResult)
def cleanup_replace_apply(
    payload: ReplaceApplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> ReplaceApplyResult:
    from apps.annotator.api.cleanup import SearchSpec, replace_apply

    try:
        result = replace_apply(
            db,
            spec=SearchSpec(
                query=payload.query,
                mode=payload.mode.value,
                case_sensitive=payload.case_sensitive,
            ),
            replacement=payload.replacement,
            items=[item.model_dump() for item in payload.items],
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReplaceApplyResult(**result)


@router.get("/cleanup/revisions/batches", response_model=list[RevisionBatchOut])
def cleanup_revision_batches(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[RevisionBatchOut]:
    from apps.annotator.api.cleanup import list_revision_batches

    return [RevisionBatchOut(**r) for r in list_revision_batches(db, limit=limit)]


@router.post(
    "/cleanup/revisions/batches/{batch_id}/rollback",
    response_model=RollbackResult,
)
def cleanup_revision_rollback(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> RollbackResult:
    from apps.annotator.api.cleanup import rollback_batch

    try:
        result = rollback_batch(db, batch_id=batch_id, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RollbackResult(**result)


@router.get("/lexicon/entries", response_model=list[LexiconEntryOut])
def lexicon_list(
    kind: str | None = None,
    origin: str | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LexiconEntryOut]:
    from apps.annotator.api.lexicon import list_entries

    return list_entries(db, kind=kind, origin=origin, q=q, limit=limit, offset=offset)


@router.post("/lexicon/entries", response_model=LexiconEntryOut)
def lexicon_create(
    payload: LexiconEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> LexiconEntryOut:
    from apps.annotator.api.lexicon import upsert_entry

    try:
        entry = upsert_entry(
            db,
            word=payload.word,
            kind=payload.kind.value,
            canonical=payload.canonical,
            origin=payload.origin.value,
            note=payload.note,
            created_by_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LexiconEntryOut.model_validate(entry)


@router.patch("/lexicon/entries/{entry_id}", response_model=LexiconEntryOut)
def lexicon_update(
    entry_id: int,
    payload: LexiconEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> LexiconEntryOut:
    from apps.annotator.api.lexicon import invalidate_lexicon_cache
    from apps.annotator.db.models import LexiconEntry, LexiconKind, LexiconOrigin
    from normalizer.phonetic import strip_accents

    existing = db.get(LexiconEntry, entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    if payload.word is not None:
        existing.word = strip_accents(payload.word.strip().lower())
    if payload.kind is not None:
        existing.kind = LexiconKind(payload.kind.value)
    if payload.canonical is not None:
        existing.canonical = strip_accents(payload.canonical.strip().lower()) or None
    if payload.origin is not None:
        existing.origin = LexiconOrigin(payload.origin.value)
    if payload.note is not None:
        existing.note = payload.note

    if existing.kind == LexiconKind.alias and not existing.canonical:
        raise HTTPException(status_code=400, detail="alias requires canonical")
    if existing.kind != LexiconKind.alias:
        existing.canonical = None

    if existing.kind == LexiconKind.alias and existing.canonical:
        can = (
            db.query(LexiconEntry)
            .filter(LexiconEntry.word == existing.canonical)
            .one_or_none()
        )
        if can is None:
            db.add(
                LexiconEntry(
                    word=existing.canonical,
                    kind=LexiconKind.official,
                    origin=existing.origin,
                    created_by_user_id=user.id,
                )
            )

    db.commit()
    db.refresh(existing)
    invalidate_lexicon_cache()
    return LexiconEntryOut.model_validate(existing)


@router.delete("/lexicon/entries/{entry_id}", status_code=204)
def lexicon_delete(
    entry_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    from apps.annotator.api.lexicon import delete_entry

    if not delete_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")


@router.post("/lexicon/import", response_model=LexiconImportResult)
def lexicon_import(
    payload: LexiconImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> LexiconImportResult:
    from apps.annotator.api.lexicon import import_text

    result = import_text(
        db,
        text=payload.text,
        format=payload.format,
        origin=payload.origin.value,
        created_by_user_id=user.id,
    )
    return LexiconImportResult(**result)


@router.get("/lexicon/export")
def lexicon_export(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from apps.annotator.api.lexicon import export_text
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(export_text(db), media_type="text/plain")


@router.get("/lexicon/suggestions", response_model=list[LexiconSuggestionOut])
def lexicon_suggestions(
    min_count: int = 3,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LexiconSuggestionOut]:
    from apps.annotator.api.lexicon import suggest_from_corpus

    return [LexiconSuggestionOut(**r) for r in suggest_from_corpus(db, min_count=min_count)]
