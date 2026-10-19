"""Admin user delete / restore helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from apps.annotator.db.models import PaymentPeriod, Segment, Source, User, UserTimeEvent


class UserManagementError(ValueError):
    """Invalid user management action."""


def user_has_linked_data(db: Session, user: User) -> bool:
    email = (user.email or "").strip()
    if (
        db.query(UserTimeEvent.id)
        .filter(
            or_(
                UserTimeEvent.user_id == user.id,
                UserTimeEvent.created_by_user_id == user.id,
            )
        )
        .first()
        is not None
    ):
        return True
    if (
        db.query(PaymentPeriod.id)
        .filter(
            or_(
                PaymentPeriod.user_id == user.id,
                PaymentPeriod.created_by_user_id == user.id,
            )
        )
        .first()
        is not None
    ):
        return True
    if (
        db.query(Source.id).filter(Source.assigned_to_user_id == user.id).first()
        is not None
    ):
        return True
    if email:
        if (
            db.query(Segment.id)
            .filter(
                or_(
                    Segment.annotator == email,
                    Segment.review_comment_by == email,
                )
            )
            .first()
            is not None
        ):
            return True
        if (
            db.query(Source.id).filter(Source.reviewed_by == email).first() is not None
        ):
            return True
    return False


def delete_user(db: Session, user: User, *, actor: User) -> tuple[str, User | None]:
    """Hard or soft delete. Returns (mode, user_or_none)."""
    if user.id == actor.id:
        raise UserManagementError("Cannot delete yourself")
    if user.deleted_at is not None:
        raise UserManagementError("User is already deleted")

    if user_has_linked_data(db, user):
        user.deleted_at = datetime.now(timezone.utc)
        user.is_active = False
        db.flush()
        return "soft", user

    db.delete(user)
    db.flush()
    return "hard", None


def restore_user(db: Session, user: User) -> User:
    user.deleted_at = None
    user.is_active = True
    db.flush()
    return user
