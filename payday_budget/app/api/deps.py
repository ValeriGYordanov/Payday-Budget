"""Request dependencies."""

import datetime as dt
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import INGRESS
from app.db import session_scope
from app.errors import Forbidden
from app.users import Actor, actor_from_request


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


def get_today(request: Request) -> dt.date:
    """P9: local date in HA's timezone (injectable via `create_app(today=...)`)."""
    today: dt.date = request.app.state.today()
    return today


SessionDep = Annotated[Session, Depends(get_session)]
TodayDep = Annotated[dt.date, Depends(get_today)]
ActorDep = Annotated[Actor, Depends(actor_from_request)]


def require_ingress(request: Request) -> None:
    """Only reachable from the add-on UI (Ingress), never with the bearer token."""
    context = getattr(request.state, "auth", None)
    if context is None or context.source != INGRESS:
        raise Forbidden("Only available from the add-on UI")


IngressOnly = Depends(require_ingress)
