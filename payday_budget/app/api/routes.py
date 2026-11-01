"""Route handlers. Each write commits once after the service call."""

import asyncio
import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import ActorDep, IngressOnly, SessionDep, TodayDep
from app.events import Broadcaster
from app.schemas import (
    BudgetCreate,
    BudgetUpdate,
    CategoryCreate,
    CategoryUpdate,
    Kind,
    PeriodCreate,
    PeriodUpdate,
    RecurringBody,
    SettingsUpdate,
    SetupRequest,
    TagBody,
    TransactionBody,
)
from app.services import (
    budgets,
    categories,
    periods,
    recurring,
    reports,
    settings,
    setup,
    tags,
    transactions,
    users,
)

router = APIRouter(prefix="/api/v1")
NO_CONTENT = Response(status_code=204)
SSE_KEEPALIVE_SECONDS = 25.0


# --- settings & setup -------------------------------------------------------


@router.get("/currencies")
def list_currencies() -> dict[str, Any]:
    """K1/K2: ISO 4217 codes with their minor-unit exponent, for the UI."""
    return {"items": settings.currencies()}


@router.get("/users")
def list_users(session: SessionDep) -> dict[str, Any]:
    """People who created transactions or periods (T3), for the user filter."""
    return {"items": users.listing(session)}


@router.get("/settings")
def get_settings(session: SessionDep) -> dict[str, Any]:
    return settings.serialize(settings.get(session))


@router.patch("/settings")
def patch_settings(body: SettingsUpdate, session: SessionDep) -> dict[str, Any]:
    result = settings.change_currency(session, body.currency, confirm=body.confirm)
    session.commit()
    return settings.serialize(result)


@router.get("/token", dependencies=[IngressOnly])
def get_token(request: Request) -> dict[str, Any]:
    """§6.3 manual config flow fallback: the token is shown in the add-on UI."""
    return {"token": request.app.state.token}


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """SSE: `changed` after every write and after scheduler runs."""
    broadcaster: Broadcaster = request.app.state.broadcaster
    queue = broadcaster.subscribe()

    async def stream() -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), SSE_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                else:
                    yield f"event: {event}\ndata: {{}}\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/setup")
def get_setup(session: SessionDep) -> dict[str, Any]:
    return {"setup_completed": settings.get(session).setup_completed}


@router.post("/setup", status_code=201)
def post_setup(
    body: SetupRequest, session: SessionDep, actor: ActorDep, today: TodayDep
) -> dict[str, Any]:
    result = setup.run(
        session,
        currency=body.currency,
        first_period=body.first_period.model_dump(),
        budget_specs=[b.model_dump() for b in body.budgets],
        actor=actor,
        today=today,
    )
    session.commit()
    return settings.serialize(result)


# --- periods ----------------------------------------------------------------


@router.get("/periods")
def list_periods(session: SessionDep, today: TodayDep) -> dict[str, Any]:
    return {"items": periods.serialize_all(session, today)}


@router.get("/periods/history")
def periods_history(
    session: SessionDep, today: TodayDep, limit: int = Query(12, ge=1, le=120)
) -> dict[str, Any]:
    return reports.history(session, limit, today)


@router.post("/periods", status_code=201)
def create_period(
    body: PeriodCreate, session: SessionDep, actor: ActorDep, today: TodayDep
) -> dict[str, Any]:
    period = periods.create(
        session, start_date=body.start_date, name=body.name, actor=actor, today=today
    )
    session.commit()
    return periods.serialize_detail(session, period, today)


@router.get("/periods/{period_id}")
def get_period(period_id: int, session: SessionDep, today: TodayDep) -> dict[str, Any]:
    return periods.serialize_detail(session, periods.get(session, period_id), today)


@router.patch("/periods/{period_id}")
def update_period(
    period_id: int, body: PeriodUpdate, session: SessionDep, today: TodayDep
) -> dict[str, Any]:
    period = periods.update(
        session, periods.get(session, period_id), fields=body.given(), today=today
    )
    session.commit()
    return periods.serialize_detail(session, period, today)


@router.delete("/periods/{period_id}", status_code=204)
def delete_period(period_id: int, session: SessionDep) -> Response:
    periods.remove(session, periods.get(session, period_id))
    session.commit()
    return NO_CONTENT


# --- budgets ----------------------------------------------------------------


@router.get("/budgets")
def list_budgets(session: SessionDep) -> dict[str, Any]:
    return budgets.serialize_list(session)


@router.post("/budgets", status_code=201)
def create_budget(body: BudgetCreate, session: SessionDep, today: TodayDep) -> dict[str, Any]:
    budget = budgets.create(
        session, name=body.name, percent=body.percent, sort_order=body.sort_order, today=today
    )
    session.commit()
    return budgets.serialize(budget)


@router.get("/budgets/{budget_id}")
def get_budget(budget_id: int, session: SessionDep) -> dict[str, Any]:
    return budgets.serialize(budgets.get(session, budget_id))


@router.patch("/budgets/{budget_id}")
def update_budget(
    budget_id: int, body: BudgetUpdate, session: SessionDep, today: TodayDep
) -> dict[str, Any]:
    budget = budgets.update(
        session, budgets.get(session, budget_id), fields=body.given(), today=today
    )
    session.commit()
    return budgets.serialize(budget)


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: int, session: SessionDep) -> Response:
    budgets.remove(session, budgets.get(session, budget_id))
    session.commit()
    return NO_CONTENT


# --- categories -------------------------------------------------------------


@router.get("/categories")
def list_categories(
    session: SessionDep, kind: Kind | None = None, archived: bool | None = None
) -> dict[str, Any]:
    return {"items": [categories.serialize(c) for c in categories.listing(session, kind, archived)]}


@router.post("/categories", status_code=201)
def create_category(body: CategoryCreate, session: SessionDep) -> dict[str, Any]:
    category = categories.create(session, name=body.name, kind=body.kind, icon=body.icon)
    session.commit()
    return categories.serialize(category)


@router.get("/categories/{category_id}")
def get_category(category_id: int, session: SessionDep) -> dict[str, Any]:
    return categories.serialize(categories.get(session, category_id))


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryUpdate, session: SessionDep) -> dict[str, Any]:
    category = categories.update(session, categories.get(session, category_id), fields=body.given())
    session.commit()
    return categories.serialize(category)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, session: SessionDep) -> Response:
    categories.remove(session, categories.get(session, category_id))
    session.commit()
    return NO_CONTENT


# --- tags -------------------------------------------------------------------


@router.get("/tags")
def list_tags(session: SessionDep) -> dict[str, Any]:
    return {"items": [tags.serialize(t) for t in tags.listing(session)]}


@router.post("/tags", status_code=201)
def create_tag(body: TagBody, session: SessionDep) -> dict[str, Any]:
    tag = tags.create(session, name=body.name)
    session.commit()
    return tags.serialize(tag)


@router.get("/tags/{tag_id}")
def get_tag(tag_id: int, session: SessionDep) -> dict[str, Any]:
    return tags.serialize(tags.get(session, tag_id))


@router.patch("/tags/{tag_id}")
def update_tag(tag_id: int, body: TagBody, session: SessionDep) -> dict[str, Any]:
    tag = tags.rename(session, tags.get(session, tag_id), name=body.name)
    session.commit()
    return tags.serialize(tag)


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: SessionDep) -> Response:
    tags.remove(session, tags.get(session, tag_id))
    session.commit()
    return NO_CONTENT


# --- transactions -----------------------------------------------------------


@router.get("/transactions")
def list_transactions(
    session: SessionDep,
    today: TodayDep,
    period: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    kind: Kind | None = None,
    category: int | None = None,
    budget: int | None = None,
    tag: int | None = None,
    user: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    filters = transactions.Filters(
        period=period,
        date_from=date_from,
        date_to=date_to,
        kind=kind,
        category=category,
        budget=budget,
        tag=tag,
        user=user,
        q=q,
    )
    return transactions.listing(session, filters, limit=limit, offset=offset, today=today)


@router.post("/transactions", status_code=201)
def create_transaction(
    body: TransactionBody, session: SessionDep, actor: ActorDep, today: TodayDep
) -> dict[str, Any]:
    transaction = transactions.create(session, values=body.model_dump(), actor=actor, today=today)
    session.commit()
    return transactions.serialize_one(session, transaction)


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, session: SessionDep) -> dict[str, Any]:
    return transactions.serialize_one(session, transactions.get(session, transaction_id))


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int, body: TransactionBody, session: SessionDep
) -> dict[str, Any]:
    transaction = transactions.update(
        session, transactions.get(session, transaction_id), fields=body.given()
    )
    session.commit()
    return transactions.serialize_one(session, transaction)


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, session: SessionDep) -> Response:
    transactions.remove(session, transactions.get(session, transaction_id))
    session.commit()
    return NO_CONTENT


# --- recurring --------------------------------------------------------------


@router.get("/recurring")
def list_recurring(session: SessionDep) -> dict[str, Any]:
    return {"items": [recurring.serialize(session, r) for r in recurring.listing(session)]}


@router.post("/recurring", status_code=201)
def create_recurring(body: RecurringBody, session: SessionDep, today: TodayDep) -> dict[str, Any]:
    rule = recurring.create(session, values=body.model_dump(), today=today)
    session.commit()
    return recurring.serialize(session, rule)


@router.get("/recurring/{rule_id}")
def get_recurring(rule_id: int, session: SessionDep) -> dict[str, Any]:
    return recurring.serialize(session, recurring.get(session, rule_id))


@router.patch("/recurring/{rule_id}")
def update_recurring(
    rule_id: int, body: RecurringBody, session: SessionDep, today: TodayDep
) -> dict[str, Any]:
    rule = recurring.update(
        session, recurring.get(session, rule_id), fields=body.given(), today=today
    )
    session.commit()
    return recurring.serialize(session, rule)


@router.delete("/recurring/{rule_id}", status_code=204)
def delete_recurring(rule_id: int, session: SessionDep) -> Response:
    recurring.remove(session, recurring.get(session, rule_id))
    session.commit()
    return NO_CONTENT


# --- reports ----------------------------------------------------------------


@router.get("/summary")
def get_summary(session: SessionDep, today: TodayDep, period: str = "current") -> dict[str, Any]:
    return reports.summary(session, periods.resolve(session, period, today), today)


@router.get("/breakdown")
def get_breakdown(
    session: SessionDep, today: TodayDep, period: str = "current", budget: int | None = None
) -> dict[str, Any]:
    return reports.breakdown(session, periods.resolve(session, period, today), budget, today)


@router.get("/daily")
def get_daily(session: SessionDep, today: TodayDep, period: str = "current") -> dict[str, Any]:
    return reports.daily(session, periods.resolve(session, period, today), today)
