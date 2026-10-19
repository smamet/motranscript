"""Category lookup helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from apps.annotator.db.models import Category

# Import collection labels (docs/youtube-sources.md) → category slug
COLLECTION_TO_SLUG = {
    "Lir Ekril Kreol Morisien": "lir-ekril",
    "Lir Ekril": "lir-ekril",
    "Komiko": "komiko",
    "Tempo La So": "tempo-la-so",
}


def list_categories(db: Session) -> list[Category]:
    return db.query(Category).order_by(Category.label).all()


def get_category_by_slug(db: Session, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug).first()


def resolve_category_id(db: Session, *, collection: str | None = None, slug: str | None = None) -> int | None:
    if slug:
        cat = get_category_by_slug(db, slug)
        return cat.id if cat else None
    if collection:
        mapped = COLLECTION_TO_SLUG.get(collection.strip())
        if mapped:
            cat = get_category_by_slug(db, mapped)
            return cat.id if cat else None
    return None


def create_category(db: Session, slug: str, label: str) -> Category:
    existing = get_category_by_slug(db, slug)
    if existing:
        return existing
    cat = Category(slug=slug, label=label)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
