"""Soft / hard user delete and restore."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.annotator.api.user_management import (
    UserManagementError,
    delete_user,
    restore_user,
    user_has_linked_data,
)
from apps.annotator.db.models import (
    Base,
    Source,
    SourceStatus,
    SourceType,
    User,
    UserRole,
    UserTimeBucket,
    UserTimeEvent,
    UserTimeEventKind,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _admin(db: Session) -> User:
    u = User(
        email="admin@example.com",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _op(db: Session, email: str = "op@example.com") -> User:
    u = User(
        email=email,
        password_hash="x",
        role=UserRole.operator,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def test_hard_delete_when_no_links(db: Session):
    admin = _admin(db)
    op = _op(db)
    assert not user_has_linked_data(db, op)
    mode, remaining = delete_user(db, op, actor=admin)
    db.commit()
    assert mode == "hard"
    assert remaining is None
    assert db.get(User, op.id) is None


def test_soft_delete_when_time_events(db: Session):
    admin = _admin(db)
    op = _op(db)
    db.add(
        UserTimeEvent(
            user_id=op.id,
            kind=UserTimeEventKind.credit,
            bucket=UserTimeBucket.done,
            audio_sec=60,
            created_by_user_id=op.id,
        )
    )
    db.flush()
    assert user_has_linked_data(db, op)
    mode, remaining = delete_user(db, op, actor=admin)
    db.commit()
    assert mode == "soft"
    assert remaining is not None
    assert remaining.deleted_at is not None
    assert remaining.is_active is False
    assert db.get(User, op.id) is not None


def test_soft_delete_when_reviewed_by_email(db: Session):
    admin = _admin(db)
    op = _op(db)
    db.add(
        Source(
            source_type=SourceType.upload,
            status=SourceStatus.ready,
            reviewed_by=op.email,
            title="t",
        )
    )
    db.flush()
    mode, remaining = delete_user(db, op, actor=admin)
    assert mode == "soft"
    assert remaining is not None


def test_cannot_delete_self(db: Session):
    admin = _admin(db)
    with pytest.raises(UserManagementError, match="yourself"):
        delete_user(db, admin, actor=admin)


def test_restore_clears_deleted_at(db: Session):
    admin = _admin(db)
    op = _op(db)
    db.add(
        UserTimeEvent(
            user_id=op.id,
            kind=UserTimeEventKind.credit,
            bucket=UserTimeBucket.validated,
            audio_sec=10,
            created_by_user_id=admin.id,
        )
    )
    db.flush()
    delete_user(db, op, actor=admin)
    db.flush()
    restored = restore_user(db, op)
    db.commit()
    assert restored.deleted_at is None
    assert restored.is_active is True
