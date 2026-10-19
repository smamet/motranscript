"""Auth helpers: password hashing and role gates."""

import pytest
from fastapi import HTTPException

from apps.annotator.api.auth import hash_password, require_admin, verify_password
from apps.annotator.db.models import User, UserRole


def test_hash_and_verify_password():
    hashed = hash_password("admin")
    assert hashed != "admin"
    assert verify_password("admin", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_rejects_garbage():
    assert not verify_password("admin", "not-a-bcrypt-hash")


def test_require_admin_allows_admin():
    user = User(id=1, email="a@b.c", password_hash="x", role=UserRole.admin, is_active=True)
    assert require_admin(user) is user


def test_require_admin_rejects_operator():
    user = User(id=2, email="op@b.c", password_hash="x", role=UserRole.operator, is_active=True)
    with pytest.raises(HTTPException) as exc:
        require_admin(user)
    assert exc.value.status_code == 403
