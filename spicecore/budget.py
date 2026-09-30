"""Atomic local-development budget. Never share this SQLite file in production."""
import datetime
import sqlite3
import uuid


class BudgetLedger:
    def __init__(self, path: str, daily_cap_cents: int):
        if not path or path == ':memory:' or type(daily_cap_cents) is not int or daily_cap_cents <= 0:
            raise ValueError('Persistent path and positive owner cap required')
        self.path, self.daily_cap_cents = path, daily_cap_cents
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, day TEXT NOT NULL, maximum INTEGER NOT NULL, actual INTEGER, claimed INTEGER NOT NULL DEFAULT 0, observed INTEGER NOT NULL DEFAULT 0)')

            if 'observed' not in {row[1] for row in db.execute('PRAGMA table_info(budget)')}:
                db.execute('ALTER TABLE budget ADD COLUMN observed INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE TABLE IF NOT EXISTS budget_halt (id INTEGER PRIMARY KEY CHECK(id=1), reason TEXT NOT NULL)')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def committed_cents(self):
        with self._connect() as db:
            return db.execute('SELECT COALESCE(SUM(COALESCE(actual, MAX(maximum, observed))), 0) FROM budget WHERE day=? OR actual IS NULL', (datetime.datetime.now(datetime.timezone.utc).date().isoformat(),)).fetchone()[0]

    def reserve(self, run_id: str, maximum_cents: int) -> str:
        if not isinstance(run_id, str) or not run_id or type(maximum_cents) is not int or maximum_cents <= 0:
            raise ValueError('Invalid reservation')
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            committed = db.execute('SELECT COALESCE(SUM(COALESCE(actual, MAX(maximum, observed))), 0) FROM budget WHERE day=? OR actual IS NULL', (day,)).fetchone()[0]
            if db.execute('SELECT 1 FROM budget_halt').fetchone() or committed + maximum_cents > self.daily_cap_cents:
                raise ValueError('Daily budget exhausted')
            reservation = uuid.uuid4().hex
            db.execute('INSERT INTO budget (id, run_id, day, maximum, actual) VALUES (?, ?, ?, ?, NULL)', (reservation, run_id, day, maximum_cents))
            return reservation

    def settle(self, reservation_id: str, actual_cents: int) -> None:
        if type(actual_cents) is not int or actual_cents < 0:
            raise ValueError('Invalid charge')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT maximum, actual, observed FROM budget WHERE id=?', (reservation_id,)).fetchone()
            if row is None or actual_cents < row[2] or (row[1] is not None and row[1] != actual_cents):
                raise ValueError('Invalid settlement')
            if row[1] is not None:
                return
            if actual_cents > row[0]:
                db.execute("INSERT OR IGNORE INTO budget_halt VALUES (1, 'Observed reservation overrun')")
            db.execute('UPDATE budget SET actual=?, day=? WHERE id=?', (actual_cents, datetime.datetime.now(datetime.timezone.utc).date().isoformat(), reservation_id))

    def validate_reservation(self, reservation_id: str, run_id: str, minimum_cents: int, *, consume: bool = False, owner_cap_cents: int | None = None) -> None:
        if owner_cap_cents is not None and (type(owner_cap_cents) is not int or owner_cap_cents <= 0):
            raise ValueError('Invalid owner ceiling')
        cap = min(self.daily_cap_cents, owner_cap_cents or self.daily_cap_cents)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT run_id, maximum, actual, claimed FROM budget WHERE id=?', (reservation_id,)).fetchone()
            committed = db.execute('SELECT COALESCE(SUM(COALESCE(actual, MAX(maximum, observed))), 0) FROM budget WHERE day=? OR actual IS NULL', (datetime.datetime.now(datetime.timezone.utc).date().isoformat(),)).fetchone()[0]
            if row is None or row[0] != run_id or row[2] is not None or row[1] - row[3] < minimum_cents or committed > cap or db.execute('SELECT 1 FROM budget_halt').fetchone():
                raise ValueError('Active sufficient reservation required')
            if consume:
                db.execute('UPDATE budget SET claimed=claimed+? WHERE id=?', (minimum_cents, reservation_id))

    def record_overrun(self, reservation_id: str, run_id: str, actual_cents: int) -> None:
        """Durably retain observed spend and halt authorization pending owner review."""
        if type(actual_cents) is not int or actual_cents < 0:
            raise ValueError('Invalid observed charge')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT run_id, actual FROM budget WHERE id=?', (reservation_id,)).fetchone()
            if row is None or row[0] != run_id or row[1] is not None:
                raise ValueError('Active reservation required for observed overrun')
            db.execute('UPDATE budget SET observed=observed+? WHERE id=?', (actual_cents, reservation_id))
            db.execute("INSERT OR IGNORE INTO budget_halt VALUES (1, 'Observed model bound overrun')")
