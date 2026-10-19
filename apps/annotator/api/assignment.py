"""Source assignment: claim (operator) and admin assign/reassign."""

from __future__ import annotations

from sqlalchemy.orm import Session

from apps.annotator.db.models import ReviewStatus, Source, User, UserRole


class AssignmentError(ValueError):
    """Invalid assignment transition."""


def operator_can_access_source(source: Source, user: User) -> bool:
    if user.role == UserRole.admin:
        return True
    return source.assigned_to_user_id is None or source.assigned_to_user_id == user.id


def operator_can_edit_source(source: Source, user: User) -> bool:
    if user.role == UserRole.admin:
        return True
    return source.assigned_to_user_id == user.id


def set_source_assignment(
    db: Session,
    source: Source,
    *,
    assigned_to_user_id: int | None,
    actor: User,
) -> Source:
    """Assign, claim, or clear assignment. Only allowed while review_status is todo."""
    if source.review_status != ReviewStatus.todo:
        raise AssignmentError(
            "Cannot change assignment while source is done or validated — reopen to todo first"
        )

    current = source.assigned_to_user_id
    is_admin = actor.role == UserRole.admin

    if not is_admin:
        # Operator claim only: null → self
        if assigned_to_user_id != actor.id:
            raise AssignmentError("Operators can only claim a source for themselves")
        if current is not None and current != actor.id:
            raise AssignmentError("Source is already assigned to someone else")
        if current == actor.id:
            return source
        if current is not None:
            raise AssignmentError("Source is already assigned")
    else:
        if assigned_to_user_id is not None:
            target = db.get(User, assigned_to_user_id)
            if not target or target.deleted_at is not None or not target.is_active:
                raise AssignmentError("Assigned user not found or inactive")

    source.assigned_to_user_id = assigned_to_user_id
    db.commit()
    db.refresh(source)
    return source
