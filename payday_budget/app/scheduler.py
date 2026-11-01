"""Recurring scheduler (R2): on add-on start, then daily at 00:05 local time.

An asyncio task; the DB work runs in a worker thread.
"""

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.orm import Session, sessionmaker

from app.services import recurring

_LOGGER = logging.getLogger(__name__)

RUN_AT = dt.time(0, 5)
# Re-check the clock at least hourly so clock or timezone changes can't delay a run by long.
MAX_SLEEP_SECONDS = 3600.0


def next_run(now: dt.datetime) -> dt.datetime:
    """The next 00:05 strictly after `now`, in `now`'s timezone."""
    assert now.tzinfo is not None
    candidate = dt.datetime.combine(now.date(), RUN_AT, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate = dt.datetime.combine(
            now.date() + dt.timedelta(days=1), RUN_AT, tzinfo=now.tzinfo
        )
    return candidate


def seconds_until(target: dt.datetime, now: dt.datetime) -> float:
    # Compare in UTC: subtracting aware datetimes that share a tzinfo ignores DST shifts.
    return (target.astimezone(dt.UTC) - now.astimezone(dt.UTC)).total_seconds()


def run_once(factory: sessionmaker[Session], today: Callable[[], dt.date]) -> int:
    """Generate all due occurrences in one transaction."""
    with factory() as session:
        created = recurring.generate_all(session, today())
        session.commit()
    _LOGGER.info("Recurring scheduler created %d transaction(s)", created)
    return created


class Scheduler:
    def __init__(
        self,
        job: Callable[[], object],
        now: Callable[[], dt.datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._job = job
        self._now = now
        self._sleep = sleep

    async def run_job(self) -> None:
        try:
            await asyncio.to_thread(self._job)
        except Exception:
            _LOGGER.exception("Recurring scheduler run failed")

    async def run_daily(self) -> None:
        """Wait for each 00:05 and run the job. Runs until cancelled."""
        while True:
            target = next_run(self._now())
            while (remaining := seconds_until(target, self._now())) > 0:
                await self._sleep(min(remaining, MAX_SLEEP_SECONDS))
            await self.run_job()
