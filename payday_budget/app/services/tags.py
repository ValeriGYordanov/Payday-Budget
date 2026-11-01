"""Tags."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, InvalidInput, NotFound
from app.models import NAME_MAX, Tag


def get(session: Session, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise NotFound("Tag")
    return tag


def listing(session: Session) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name)))


def _clean_name(session: Session, name: str, exclude_id: int | None = None) -> str:
    cleaned = name.strip()
    if not cleaned or len(cleaned) > NAME_MAX:
        raise InvalidInput(f"tag name must be 1-{NAME_MAX} characters", field="name")
    query = select(Tag.id).where(Tag.name == cleaned)
    if exclude_id is not None:
        query = query.where(Tag.id != exclude_id)
    if session.scalar(query) is not None:
        raise Conflict("A tag with this name already exists", field="name")
    return cleaned


def create(session: Session, *, name: str) -> Tag:
    tag = Tag(name=_clean_name(session, name))
    session.add(tag)
    session.flush()
    return tag


def rename(session: Session, tag: Tag, *, name: str) -> Tag:
    tag.name = _clean_name(session, name, exclude_id=tag.id)
    session.flush()
    return tag


def remove(session: Session, tag: Tag) -> None:
    """Deleting a tag removes it from transactions (FK cascade)."""
    session.delete(tag)
    session.flush()


def by_names(session: Session, names: list[str]) -> list[Tag]:
    """Resolve tag names, creating missing ones."""
    wanted: list[str] = []
    for raw in names:
        name = raw.strip()
        if not name or len(name) > NAME_MAX:
            raise InvalidInput(f"tag names must be 1-{NAME_MAX} characters", field="tags")
        if name not in wanted:
            wanted.append(name)
    existing = {t.name: t for t in session.scalars(select(Tag).where(Tag.name.in_(wanted)))}
    result = []
    for name in wanted:
        tag = existing.get(name)
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
        result.append(tag)
    session.flush()
    return result


def serialize(tag: Tag) -> dict[str, Any]:
    return {"id": tag.id, "name": tag.name}
