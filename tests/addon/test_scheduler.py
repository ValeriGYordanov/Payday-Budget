"""R2 scheduler timing: daily at 00:05 local time."""

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.scheduler import MAX_SLEEP_SECONDS, Scheduler, next_run, seconds_until

SOFIA = ZoneInfo("Europe/Sofia")


def _at(year: int, month: int, day: int, hour: int, minute: int) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=SOFIA)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (_at(2026, 11, 1, 0, 4), _at(2026, 11, 1, 0, 5)),
        (_at(2026, 11, 1, 0, 5), _at(2026, 11, 2, 0, 5)),
        (_at(2026, 11, 1, 23, 59), _at(2026, 11, 2, 0, 5)),
        (_at(2026, 12, 31, 12, 0), _at(2027, 1, 1, 0, 5)),
    ],
)
def test_R2_next_run_is_next_0005_local(now: dt.datetime, expected: dt.datetime) -> None:
    assert next_run(now) == expected


def test_R2_wait_accounts_for_dst() -> None:
    # Europe/Sofia springs forward at 03:00 on 2026-03-29: that day has 23 hours.
    now = _at(2026, 3, 29, 0, 6)
    assert seconds_until(next_run(now), now) == 23 * 3600 - 60


def test_R2_scheduler_runs_daily_at_0005() -> None:
    clock = {"now": _at(2026, 11, 1, 22, 30)}
    runs: list[dt.datetime] = []
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += dt.timedelta(seconds=seconds)

    def job() -> None:
        runs.append(clock["now"])
        clock["now"] += dt.timedelta(seconds=2)  # the job takes a moment
        if len(runs) == 3:
            raise asyncio.CancelledError

    async def main() -> None:
        scheduler = Scheduler(job=job, now=lambda: clock["now"], sleep=fake_sleep)
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_daily()

    asyncio.run(main())
    assert runs == [_at(2026, 11, 2, 0, 5), _at(2026, 11, 3, 0, 5), _at(2026, 11, 4, 0, 5)]
    assert max(sleeps) <= MAX_SLEEP_SECONDS


def test_R2_failed_run_is_logged_and_scheduler_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def job() -> None:
        raise RuntimeError("db locked")

    scheduler = Scheduler(job=job, now=lambda: _at(2026, 11, 1, 0, 0))
    asyncio.run(scheduler.run_job())
    assert "Recurring scheduler run failed" in caplog.text
