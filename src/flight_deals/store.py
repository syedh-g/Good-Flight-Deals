"""SQLite persistence: price history, search budget, and sent alerts."""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from flight_deals.models import Deal, Fare

# Append-only: each entry migrates the schema from version N to N+1.
_MIGRATIONS = [
    """
    CREATE TABLE observations (
        id INTEGER PRIMARY KEY,
        observed_at TEXT NOT NULL,
        airport TEXT NOT NULL,
        destination TEXT NOT NULL,
        country TEXT NOT NULL,
        price INTEGER NOT NULL,
        currency TEXT NOT NULL,
        outbound TEXT NOT NULL,
        inbound TEXT NOT NULL,
        airline TEXT,
        stops INTEGER
    );
    CREATE INDEX idx_observations_airport ON observations (airport, currency, observed_at);

    CREATE TABLE searches (
        id INTEGER PRIMARY KEY,
        searched_at TEXT NOT NULL,
        source TEXT NOT NULL
    );

    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY,
        alerted_at TEXT NOT NULL,
        airport TEXT NOT NULL,
        price INTEGER NOT NULL,
        currency TEXT NOT NULL
    );
    """,
    # v2: history is kept per named search so e.g. 2-week Asia trips aren't compared with
    # 1-week trips. Every row before this came from the original Europe-only search.
    """
    ALTER TABLE observations ADD COLUMN search TEXT NOT NULL DEFAULT 'europe';
    DROP INDEX idx_observations_airport;
    CREATE INDEX idx_observations_search ON observations (search, airport, currency, observed_at);
    """,
    # v3: keep each fare's deal score so alert thresholds can be tuned against real data.
    """
    ALTER TABLE observations ADD COLUMN zscore REAL;
    """,
]


def _ts(moment: datetime) -> str:
    """Timestamps are stored as UTC ISO strings, so they sort and group by date as text."""
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._migrate()

    @classmethod
    def open(cls, path: Path | str) -> Self:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(path))

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _migrate(self) -> None:
        (version,) = self._conn.execute("PRAGMA user_version").fetchone()
        for i, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            with self._conn:
                self._conn.executescript(script)
                self._conn.execute(f"PRAGMA user_version = {i}")

    def record_search(self, source: str, at: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO searches (searched_at, source) VALUES (?, ?)", (_ts(at), source)
            )

    def searches_since(self, since: datetime) -> int:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM searches WHERE searched_at >= ?", (_ts(since),)
        ).fetchone()
        return count

    def record_fares(
        self, search: str, scored: Iterable[tuple[Fare, float | None]], at: datetime
    ) -> None:
        """Store fares with their deal score (None when there wasn't enough history)."""
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO observations (observed_at, search, airport, destination, country,
                                          price, currency, outbound, inbound, airline, stops,
                                          zscore)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _ts(at),
                        search,
                        f.airport,
                        f.destination,
                        f.country,
                        f.price,
                        f.currency,
                        f.outbound.isoformat(),
                        f.inbound.isoformat(),
                        f.airline,
                        f.stops,
                        zscore,
                    )
                    for f, zscore in scored
                ],
            )

    def daily_lows(
        self, search: str, airport: str, currency: str, since: datetime, until: datetime
    ) -> list[int]:
        """Cheapest price per UTC day in [since, until), so extra runs on a day don't add weight."""
        rows = self._conn.execute(
            """
            SELECT MIN(price) FROM observations
            WHERE search = ? AND airport = ? AND currency = ?
              AND observed_at >= ? AND observed_at < ?
            GROUP BY substr(observed_at, 1, 10)
            ORDER BY substr(observed_at, 1, 10)
            """,
            (search, airport, currency, _ts(since), _ts(until)),
        )
        return [price for (price,) in rows]

    def lowest_alert_since(self, airport: str, currency: str, since: datetime) -> int | None:
        (price,) = self._conn.execute(
            """
            SELECT MIN(price) FROM alerts
            WHERE airport = ? AND currency = ? AND alerted_at >= ?
            """,
            (airport, currency, _ts(since)),
        ).fetchone()
        return price

    def record_alerts(self, deals: Iterable[Deal], at: datetime) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT INTO alerts (alerted_at, airport, price, currency) VALUES (?, ?, ?, ?)",
                [(_ts(at), d.fare.airport, d.fare.price, d.fare.currency) for d in deals],
            )
