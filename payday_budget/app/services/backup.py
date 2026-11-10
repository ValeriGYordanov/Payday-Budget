"""Export and import in Payday Budget's own format (v1.2 §5, EX1-EX6).

A zip with `manifest.json` and one CSV per table. IDs are kept, so references survive.
Import replaces everything in the caller's transaction: the preview rolls it back, the real
import commits it (all or nothing, EX3).
"""

import csv
import datetime as dt
import io
import json
import zipfile
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    Select,
    String,
    Table,
    delete,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import currency
from app.errors import ApiError, InvalidInput, RuleViolation
from app.models import (
    Budget,
    Category,
    Period,
    PeriodBudget,
    RecurringRule,
    Reminder,
    ReminderOccurrence,
    Settings,
    Tag,
    Transaction,
    TransactionTag,
    iso_utc,
)
from app.money import FULL_PERCENT_BP, format_percent, parse_percent
from app.services import recurring, reminders
from app.services.categories import ICON_RE

FORMAT = 1
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
_CHUNK = 1000


# Insert order: every table after the ones it references. Deletes run in reverse.
def _table(model: type[Any]) -> Table:
    table: Table = model.__table__
    return table


TABLES: tuple[Table, ...] = tuple(
    _table(model)
    for model in (
        Settings,
        Period,
        Budget,
        PeriodBudget,
        Category,
        Tag,
        RecurringRule,
        Transaction,
        TransactionTag,
        Reminder,
        ReminderOccurrence,
    )
)


# §5.1: percents are decimal strings ("50.00") in the CSV, integer hundredths in the DB.
PERCENT_COLUMN = "percent_bp"


def file_name(table: Table) -> str:
    return f"{table.name}.csv"


def csv_name(column: Any) -> str:
    return "percent" if column.name == PERCENT_COLUMN else str(column.name)


def _counts(session: Session) -> dict[str, int]:
    return {t.name: int(session.scalar(select(func.count()).select_from(t)) or 0) for t in TABLES}


# --- export (EX1) -------------------------------------------------------------


def _dump(column: Any, value: Any) -> str:
    if value is None:
        return ""
    if column.name == PERCENT_COLUMN:
        return format_percent(value)
    if isinstance(column.type, Boolean):
        return "true" if value else "false"
    if isinstance(column.type, DateTime):
        return iso_utc(value)
    if isinstance(column.type, Date):
        return str(value.isoformat())
    if isinstance(column.type, JSON):
        return json.dumps(value)
    return str(value)


def export_zip(session: Session, *, app_version: str, now: dt.datetime) -> bytes:
    buffer = io.BytesIO()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in TABLES:
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow([csv_name(c) for c in table.columns])
            rows = session.execute(select(table).order_by(*table.primary_key.columns)).all()
            for row in rows:
                writer.writerow([_dump(c, row._mapping[c.name]) for c in table.columns])
            archive.writestr(file_name(table), out.getvalue())
            counts[table.name] = len(rows)
        settings_row = session.get(Settings, 1)
        manifest = {
            "format": FORMAT,
            "app_version": app_version,
            "exported_at": iso_utc(now),
            "currency": settings_row.currency if settings_row else None,
            "counts": counts,
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return buffer.getvalue()


# --- import (EX2-EX6) -----------------------------------------------------------


def _fail(where: str, message: str, code: str | None = None) -> ApiError:
    """EX4: the first error, with file and row (and the rule ID when a rule is broken)."""
    if code is None:
        return InvalidInput(f"{where}: {message}", field=where)
    return RuleViolation(code, f"{where}: {message}", field=where)


def _load(column: Any, text: str, where: str) -> Any:
    if text == "":
        if column.nullable:
            return None
        raise _fail(where, f"{csv_name(column)} is required")
    if column.name == PERCENT_COLUMN:
        bp = parse_percent(text)
        if bp is None:
            raise _fail(where, "percent must be 0-100 with at most 2 decimals", "B1")
        return bp
    try:
        if isinstance(column.type, Boolean):
            if text not in ("true", "false"):
                raise ValueError("expected true or false")
            return text == "true"
        if isinstance(column.type, Integer):
            return int(text)
        if isinstance(column.type, DateTime):
            value = dt.datetime.fromisoformat(text)
            if value.tzinfo is not None:  # stored as naive UTC, like the app writes it
                value = value.astimezone(dt.UTC).replace(tzinfo=None)
            return value
        if isinstance(column.type, Date):
            return dt.date.fromisoformat(text)
        if isinstance(column.type, JSON):
            value = json.loads(text)
            if not isinstance(value, list) or not all(
                isinstance(i, int) and not isinstance(i, bool) for i in value
            ):
                raise ValueError("expected a list of ids")
            return value
    except ValueError as err:
        raise _fail(where, f"{column.name}: {err}") from err
    if isinstance(column.type, String) and column.type.length and len(text) > column.type.length:
        raise _fail(where, f"{column.name} is longer than {column.type.length} characters")
    return text


def read_archive(data: bytes) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    """The manifest and the raw CSV rows per table, after checking the file's shape."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidInput("The file is larger than 50 MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as err:
        raise InvalidInput("Not a Payday Budget backup (not a zip file)") from err
    with archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED_BYTES:
            raise InvalidInput("The backup unpacks to more than 200 MB")
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise InvalidInput("Not a Payday Budget backup (manifest.json missing)")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except ValueError as err:
            raise _fail("manifest.json", "not valid JSON") from err
        version = manifest.get("format") if isinstance(manifest, dict) else None
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise _fail("manifest.json", "format must be a positive integer")
        if version > FORMAT:  # EX5; older formats would be migrated here
            raise _fail(
                "manifest.json",
                f"format {version} is newer than this app supports ({FORMAT}); update the app",
                "EX5",
            )
        tables: dict[str, list[dict[str, str]]] = {}
        for table in TABLES:
            name = file_name(table)
            if name not in names:
                raise _fail(name, "missing from the backup")
            text = archive.read(name).decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text, newline=""))
            header = set(reader.fieldnames or [])
            expected = {csv_name(c) for c in table.columns}
            if header != expected:
                missing, extra = expected - header, header - expected
                detail = ", ".join(
                    part
                    for part in (
                        f"missing {sorted(missing)}" if missing else "",
                        f"unexpected {sorted(extra)}" if extra else "",
                    )
                    if part
                )
                raise _fail(f"{name} row 1", f"columns do not match ({detail})")
            tables[table.name] = list(reader)
    return manifest, tables


def _insert(session: Session, table: Table, rows: list[dict[str, Any]]) -> None:
    """Insert in chunks; on a constraint error, find and report the first bad row."""
    connection = session.connection()
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        try:
            with connection.begin_nested():
                connection.execute(table.insert(), chunk)
        except IntegrityError:
            for offset, row in enumerate(chunk):
                try:
                    with connection.begin_nested():
                        connection.execute(table.insert(), row)
                except IntegrityError as err:
                    where = f"{file_name(table)} row {start + offset + 2}"
                    raise _fail(where, _constraint(err)) from err
            raise


def _constraint(err: IntegrityError) -> str:
    text = str(err.orig)
    if "FOREIGN KEY" in text:
        return "refers to a row that does not exist"
    if "UNIQUE" in text:
        return f"duplicate ({text.split(':', 1)[-1].strip()})"
    if "CHECK" in text:
        return f"invalid value ({text.split(':', 1)[-1].strip()})"
    return text


def _first(session: Session, query: Select[Any]) -> Any:
    return session.execute(query.limit(1)).scalar()


def _check_rules(session: Session, lines: dict[str, dict[Any, int]], today: dt.date) -> None:
    """EX4: the rules the database constraints don't cover."""

    def where(table: Table, key: Any) -> str:
        return f"{file_name(table)} row {lines[table.name].get(key, '?')}"

    settings_row = session.get(Settings, 1)
    if settings_row is None:
        raise _fail("settings.csv", "exactly one row (id 1) is required")
    if currency.exponent(settings_row.currency) is None:
        raise _fail(where(_table(Settings), 1), "currency is not ISO 4217", "K1")

    named: tuple[tuple[Table, Any, Any], ...] = (
        (_table(Period), Period.id, Period.name),
        (_table(Budget), Budget.id, Budget.name),
        (_table(Category), Category.id, Category.name),
        (_table(Tag), Tag.id, Tag.name),
        (_table(Reminder), Reminder.id, Reminder.name),
    )
    for table, id_column, name_column in named:
        blank = _first(session, select(id_column).where(func.trim(name_column) == ""))
        if blank is not None:
            raise _fail(where(table, blank), "name must not be empty")

    future = _first(session, select(Period.id).where(Period.start_date > today))
    if future is not None:
        raise _fail(where(_table(Period), future), "a period cannot start in the future", "P2")
    earliest = session.scalar(select(func.min(Period.start_date)))
    early_query = select(Transaction.id).order_by(Transaction.id)
    if earliest is not None:
        early_query = early_query.where(Transaction.date < earliest)
    early = _first(session, early_query)
    if early is not None:
        raise _fail(
            where(_table(Transaction), early),
            "transactions before the first period are not allowed",
            "P6",
        )

    active_bp = session.scalar(
        select(func.coalesce(func.sum(Budget.percent_bp), 0)).where(Budget.archived.is_(False))
    )
    if int(active_bp or 0) > FULL_PERCENT_BP:
        raise _fail("budgets.csv", "active budgets sum to more than 100%", "B1")

    for icon_id, icon in session.execute(select(Category.id, Category.icon)):
        if not ICON_RE.match(icon):
            raise _fail(where(_table(Category), icon_id), "icon must be an mdi:… name")

    # (table, id, kind, category_id, budget_id, expenses need a budget)
    entries: tuple[tuple[Table, Any, Any, Any, Any, bool], ...] = (
        (
            _table(Transaction),
            Transaction.id,
            Transaction.kind,
            Transaction.category_id,
            Transaction.budget_id,
            True,
        ),
        (
            _table(RecurringRule),
            RecurringRule.id,
            RecurringRule.kind,
            RecurringRule.category_id,
            RecurringRule.budget_id,
            True,
        ),
        # A reminder's category and budget are an optional pre-fill.
        (
            _table(Reminder),
            Reminder.id,
            Reminder.kind,
            Reminder.category_id,
            Reminder.budget_id,
            False,
        ),
    )
    for table, id_column, kind, category_id, budget_id, needs_budget in entries:
        mismatch = _first(
            session,
            select(id_column)
            .join(Category, Category.id == category_id)
            .where(Category.kind != kind),
        )
        if mismatch is not None:
            raise _fail(where(table, mismatch), "category kind must match the kind", "T2")
        income_budget = _first(
            session, select(id_column).where(kind == "income", budget_id.is_not(None))
        )
        if income_budget is not None:
            raise _fail(where(table, income_budget), "incomes must not have a budget", "B6")
        if needs_budget:
            no_budget = _first(
                session, select(id_column).where(kind == "expense", budget_id.is_(None))
            )
            if no_budget is not None:
                raise _fail(where(table, no_budget), "expenses require a budget", "B6")

    schedules: tuple[tuple[Table, Any, Any, Any, str], ...] = (
        (
            _table(RecurringRule),
            RecurringRule.id,
            RecurringRule.anchor_date,
            RecurringRule.end_date,
            "R1",
        ),
        (_table(Reminder), Reminder.id, Reminder.anchor_date, Reminder.end_date, "RM1"),
    )
    for table, id_column, anchor, end, code in schedules:
        backwards = _first(session, select(id_column).where(end.is_not(None), end < anchor))
        if backwards is not None:
            raise _fail(where(table, backwards), "end_date must not be before anchor_date", code)


def run_import(session: Session, data: bytes, *, today: dt.date, apply: bool) -> dict[str, Any]:
    """Validate the backup by loading it in place of the current data (EX2-EX4).

    The caller commits when `apply` is true and rolls back otherwise. With `apply`, the
    scheduler runs once afterwards (EX6). Returns the manifest and the row counts.
    """
    manifest, raw = read_archive(data)
    current = _counts(session)
    connection = session.connection()
    for table in reversed(TABLES):
        connection.execute(delete(table))
    lines: dict[str, dict[Any, int]] = {}
    for table in TABLES:
        columns = list(table.columns)
        rows = []
        lines[table.name] = {}
        for index, record in enumerate(raw[table.name]):
            line = index + 2  # the header is line 1
            where = f"{file_name(table)} row {line}"
            rows.append({c.name: _load(c, record[csv_name(c)] or "", where) for c in columns})
            if len(table.primary_key.columns) == 1:
                key = rows[-1][next(iter(table.primary_key.columns)).name]
                lines[table.name][key] = line
        _insert(session, table, rows)
    session.expire_all()
    _check_rules(session, lines, today)
    if apply:
        recurring.generate_all(session, today)
        reminders.open_all(session, today)
    return {
        "manifest": manifest,
        "counts": {t.name: {"file": len(raw[t.name]), "current": current[t.name]} for t in TABLES},
    }
