"""SQLite 데이터 레이어.

감시 조건 / 가격 이력 / 항공편 스냅샷 / 알림 로그 테이블을 관리한다.
DB 파일은 저장소(data/flights.db)에 커밋되어 Streamlit Cloud의
휘발성 파일시스템 문제를 우회하며, GitHub Actions가 주기적으로 갱신한다.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from app.models import FlightOffer, WatchCondition

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT DEFAULT '',
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    trip_type TEXT NOT NULL DEFAULT 'one-way',
    depart_date TEXT NOT NULL,
    return_date TEXT,
    adults INTEGER NOT NULL DEFAULT 1,
    currency TEXT NOT NULL DEFAULT 'KRW',
    target_price REAL,
    drop_percent REAL NOT NULL DEFAULT 15,
    percentile REAL NOT NULL DEFAULT 10,
    cooldown_hours REAL NOT NULL DEFAULT 6,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    last_checked_at TEXT,
    last_notified_at TEXT,
    last_notified_price REAL,
    first_seen_price REAL,
    dep_hour_from INTEGER,
    dep_hour_to INTEGER,
    ret_hour_from INTEGER,
    ret_hour_to INTEGER,
    max_stops INTEGER
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watch_conditions(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    airline TEXT DEFAULT '',
    departure TEXT DEFAULT '',
    arrival TEXT DEFAULT '',
    stops INTEGER DEFAULT 0,
    provider TEXT DEFAULT 'google-flights',
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watch_conditions(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    reason TEXT DEFAULT '',
    message TEXT DEFAULT '',
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offer_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watch_conditions(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    airline TEXT DEFAULT '',
    airline_codes TEXT DEFAULT '[]',
    departure TEXT DEFAULT '',
    arrival TEXT DEFAULT '',
    stops INTEGER DEFAULT 0,
    rank INTEGER DEFAULT 0,
    checked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_watch ON price_history(watch_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_notif_watch ON notifications_log(watch_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_snap_watch ON offer_snapshots(watch_id, checked_at);
"""

_WATCH_COLS = [
    "id", "label", "origin", "destination", "trip_type", "depart_date",
    "return_date", "adults", "currency", "target_price", "drop_percent",
    "percentile", "cooldown_hours", "active", "created_at",
    "last_checked_at", "last_notified_at", "last_notified_price", "first_seen_price",
    "dep_hour_from", "dep_hour_to", "ret_hour_from", "ret_hour_to", "max_stops",
]

_UPDATABLE_COLS = {
    "label", "origin", "destination", "trip_type", "depart_date", "return_date",
    "adults", "currency", "target_price", "drop_percent", "percentile",
    "cooldown_hours", "active", "last_checked_at", "last_notified_at",
    "last_notified_price", "first_seen_price", "dep_hour_from", "dep_hour_to",
    "ret_hour_from", "ret_hour_to", "max_stops",
}


def now_str() -> str:
    """KST 기준 현재 시각 문자열 (naive ISO 형식)."""
    return datetime.now(KST).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _percentile(sorted_vals: list[float], pct: float) -> Optional[float]:
    """선형 보간 백분위 값."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _row_to_watch(row: sqlite3.Row) -> WatchCondition:
    d = dict(row)
    d["active"] = bool(d.get("active"))
    return WatchCondition(**d)


class Database:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        # busy_timeout: GitHub Actions 크론과 대시보드가 같은 파일을 동시에 만질 때
        # 즉시 "database is locked"로 죽지 않고 최대 5초 대기하도록 한다.
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """트랜잭션 커밋/롤백과 커넥션 종료를 함께 보장한다.

        sqlite3 커넥션의 `with` 블록은 커밋·롤백만 하고 close는 하지 않는다.
        기존 코드는 쿼리마다 새 커넥션을 열고 닫지 않아 GC 타이밍에 의존했다.
        """
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._tx() as conn:
            conn.executescript(_SCHEMA)
            # 구버전 DB 마이그레이션: 누락된 컬럼 추가
            cols = {r[1] for r in conn.execute("PRAGMA table_info(watch_conditions)").fetchall()}
            for col, col_type in (("dep_hour_from", "INTEGER"), ("dep_hour_to", "INTEGER"),
                                  ("ret_hour_from", "INTEGER"), ("ret_hour_to", "INTEGER"),
                                  ("max_stops", "INTEGER"), ("last_notified_price", "REAL")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE watch_conditions ADD COLUMN {col} {col_type}")

    # ------------------------------------------------------------------
    # 감시 조건 CRUD
    # ------------------------------------------------------------------
    def add_watch(self, w: WatchCondition) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO watch_conditions (
                    label, origin, destination, trip_type, depart_date, return_date,
                    adults, currency, target_price, drop_percent, percentile,
                    cooldown_hours, active, created_at, last_checked_at,
                    last_notified_at, first_seen_price, dep_hour_from, dep_hour_to,
                    ret_hour_from, ret_hour_to, max_stops
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    w.label, w.origin.upper(), w.destination.upper(), w.trip_type,
                    w.depart_date, w.return_date, max(1, w.adults), w.currency,
                    w.target_price, w.drop_percent, w.percentile, w.cooldown_hours,
                    int(w.active), w.created_at or now_str(), None, None, None,
                    w.dep_hour_from, w.dep_hour_to, w.ret_hour_from, w.ret_hour_to,
                    w.max_stops,
                ),
            )
            return int(cur.lastrowid)

    def get_watch(self, watch_id: int) -> Optional[WatchCondition]:
        with self._tx() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_WATCH_COLS)} FROM watch_conditions WHERE id = ?",
                (watch_id,),
            ).fetchone()
            return _row_to_watch(row) if row else None

    def list_watches(self, active_only: bool = False) -> list[WatchCondition]:
        q = f"SELECT {', '.join(_WATCH_COLS)} FROM watch_conditions"
        if active_only:
            q += " WHERE active = 1"
        q += " ORDER BY id"
        with self._tx() as conn:
            return [_row_to_watch(r) for r in conn.execute(q).fetchall()]

    def update_watch_fields(self, watch_id: int, **fields: Any) -> None:
        cols = [c for c in fields if c in _UPDATABLE_COLS]
        if not cols:
            return
        sets = ", ".join(f"{c} = ?" for c in cols)
        values = [fields[c] for c in cols] + [watch_id]
        with self._tx() as conn:
            conn.execute(f"UPDATE watch_conditions SET {sets} WHERE id = ?", values)

    def set_active(self, watch_id: int, active: bool) -> None:
        self.update_watch_fields(watch_id, active=int(active))

    def delete_watch(self, watch_id: int) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM watch_conditions WHERE id = ?", (watch_id,))

    def delete_all_watches(self) -> int:
        """모든 감시 조건 삭제 (이력·스냅샷·알림 로그도 CASCADE로 함께 삭제)."""
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM watch_conditions")
            return int(cur.rowcount or 0)

    # ------------------------------------------------------------------
    # 가격 이력
    # ------------------------------------------------------------------
    def add_price_record(
        self,
        watch_id: int,
        offer: FlightOffer,
        checked_at: Optional[str] = None,
        provider_name: str = "google-flights",
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO price_history
                    (watch_id, price, airline, departure, arrival, stops, provider, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    watch_id, float(offer.price), offer.airline or "", offer.departure or "",
                    offer.arrival or "", int(offer.stops or 0), provider_name,
                    checked_at or now_str(),
                ),
            )

    def get_history(self, watch_id: int, days: int = 30) -> list[dict[str, Any]]:
        cutoff = (datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        with self._tx() as conn:
            rows = conn.execute(
                """
                SELECT watch_id, price, airline, departure, arrival, stops, provider, checked_at
                FROM price_history
                WHERE watch_id = ? AND checked_at >= ?
                ORDER BY checked_at ASC, id ASC
                """,
                (watch_id, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    def price_stats(
        self,
        watch_id: int,
        days: int = 30,
        percentile: float = 10,
        history: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """가격 통계. 이미 조회한 이력이 있으면 history로 넘겨 재조회를 피한다.

        (대시보드는 조건마다 get_history를 부르고 price_stats가 또 같은 쿼리를
         돌려 조건 수 x 2회의 중복 조회가 발생하고 있었다.)
        """
        hist = self.get_history(watch_id, days=days) if history is None else history
        prices = [float(h["price"]) for h in hist]
        if not prices:
            return {"count": 0, "min": None, "max": None, "avg": None,
                    "first": None, "last": None, "pct_value": None}
        return {
            "count": len(prices),
            "min": min(prices),
            "max": max(prices),
            "avg": sum(prices) / len(prices),
            "first": prices[0],
            "last": prices[-1],
            "pct_value": _percentile(sorted(prices), percentile),
        }

    def prune_history(self, keep_days: int = 90, max_rows_per_watch: int = 1600) -> None:
        """오래된 이력 정리 - 저장소 커밋 크기 무한 증가 방지.

        행 상한은 30분 크론(하루 48회) 기준 33일치다. 1000행(≈21일)이던 때는
        price_stats의 30일 창이 조용히 21일로 잘려 '최근 30일' 표기와 모순이었다.
        """
        cutoff = (datetime.now(KST).replace(tzinfo=None) - timedelta(days=keep_days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        with self._tx() as conn:
            conn.execute("DELETE FROM price_history WHERE checked_at < ?", (cutoff,))
            conn.execute(
                """
                DELETE FROM price_history WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY watch_id
                                   ORDER BY checked_at DESC, id DESC
                               ) AS rn
                        FROM price_history
                    )
                    WHERE rn > ?
                )
                """,
                (max_rows_per_watch,),
            )

    # ------------------------------------------------------------------
    # 항공편 스냅샷 (조회 시 상위 N개 오퍼 저장)
    # ------------------------------------------------------------------
    def add_offer_snapshot(
        self,
        watch_id: int,
        offers: list[FlightOffer],
        checked_at: Optional[str] = None,
        top_n: int = 5,
    ) -> None:
        checked_at = checked_at or now_str()
        rows = [
            (
                watch_id, float(offer.price), offer.airline or "",
                json.dumps(offer.airline_codes or [], ensure_ascii=False),
                offer.departure or "", offer.arrival or "",
                int(offer.stops or 0), rank, checked_at,
            )
            for rank, offer in enumerate(offers[:top_n])
        ]
        if not rows:
            return
        with self._tx() as conn:  # 건별 execute 대신 한 번에 (executemany)
            conn.executemany(
                """
                INSERT INTO offer_snapshots
                    (watch_id, price, airline, airline_codes, departure,
                     arrival, stops, rank, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_latest_offers(self, watch_id: int) -> list[dict[str, Any]]:
        """가장 최근 조회 시점의 항공편 목록 (가격 오름차순)."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT MAX(checked_at) AS m FROM offer_snapshots WHERE watch_id = ?",
                (watch_id,),
            ).fetchone()
            if not row or not row["m"]:
                return []
            rows = conn.execute(
                """
                SELECT price, airline, airline_codes, departure, arrival, stops,
                       rank, checked_at
                FROM offer_snapshots
                WHERE watch_id = ? AND checked_at = ?
                ORDER BY rank ASC
                """,
                (watch_id, row["m"]),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["airline_codes"] = json.loads(d.get("airline_codes") or "[]")
            except (TypeError, ValueError):
                d["airline_codes"] = []
            out.append(d)
        return out

    def prune_snapshots(self, max_per_watch: int = 60) -> None:
        """감시 조건당 최근 N회 조회분만 유지."""
        with self._tx() as conn:
            conn.execute(
                """
                DELETE FROM offer_snapshots WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY watch_id
                                   ORDER BY checked_at DESC, id DESC
                               ) AS rn
                        FROM offer_snapshots
                    )
                    WHERE rn > ?
                )
                """,
                (max_per_watch,),
            )

    # ------------------------------------------------------------------
    # 알림 로그
    # ------------------------------------------------------------------
    def log_notification(self, watch_id: int, price: float, reason: str, message: str) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO notifications_log (watch_id, price, reason, message, sent_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (watch_id, float(price), reason, message, now_str()),
            )

    def prune_notifications(self, max_rows: int = 1000) -> None:
        """알림 로그 상한 유지 - 유일하게 정리 없이 무한히 쌓이던 테이블이다."""
        with self._tx() as conn:
            conn.execute(
                """
                DELETE FROM notifications_log WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (ORDER BY sent_at DESC, id DESC) AS rn
                        FROM notifications_log
                    )
                    WHERE rn > ?
                )
                """,
                (max_rows,),
            )

    def list_notifications(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._tx() as conn:
            rows = conn.execute(
                """
                SELECT n.id, n.watch_id, COALESCE(NULLIF(w.label, ''),
                        w.origin || ' → ' || w.destination) AS label,
                       n.price, n.reason, n.sent_at
                FROM notifications_log n
                LEFT JOIN watch_conditions w ON w.id = n.watch_id
                ORDER BY n.sent_at DESC, n.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
