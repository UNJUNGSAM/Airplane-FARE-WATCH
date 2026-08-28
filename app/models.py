"""공용 데이터 모델 (Pydantic)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WatchCondition(BaseModel):
    """감시 조건 1건."""

    id: Optional[int] = None
    label: str = ""
    origin: str  # IATA 공항 코드 (예: ICN)
    destination: str  # IATA 공항 코드 (예: NRT)
    trip_type: Literal["one-way", "round"] = "one-way"
    depart_date: str  # YYYY-MM-DD
    return_date: Optional[str] = None  # 왕복일 때만
    adults: int = 1
    currency: str = "KRW"

    # --- 핫딜 판정 규칙 ---
    target_price: Optional[float] = None  # 목표가 (이하 도달 시 알림)
    drop_percent: float = 15.0  # 첫 관측가 대비 하락률 (%)
    percentile: float = 10.0  # 최근 30일 이력 하위 백분위 (%)
    cooldown_hours: float = 6.0  # 알림 쿨다운 (시간)

    # --- 출발 시간대 선호 (선택, 0~23시) ---
    dep_hour_from: Optional[int] = None  # 이 시간 이후 출발만 감시
    dep_hour_to: Optional[int] = None  # 이 시간까지 출발 포함 (23시=23:59까지)

    # --- 귀국 출발 시간대 선호 (왕복만, 선택) ---
    ret_hour_from: Optional[int] = None  # 귀국편은 이 시간 이후 출발
    ret_hour_to: Optional[int] = None  # 귀국편은 이 시간까지 출발 포함

    # --- 경유 필터 (선택) ---
    max_stops: Optional[int] = None  # None=전체, 0=직항만, 1=1회경유까지

    active: bool = True

    # --- 운영 메타 ---
    created_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_notified_at: Optional[str] = None
    last_notified_price: Optional[float] = None  # 재알림 억제 기준가
    first_seen_price: Optional[float] = None

    @property
    def route_label(self) -> str:
        base = f"{self.origin} → {self.destination}"
        if self.trip_type == "round" and self.return_date:
            base += f" → {self.origin}"
        return base


class FlightOffer(BaseModel):
    """조회된 항공편 오퍼 1건."""

    airline: str = ""
    airline_codes: List[str] = Field(default_factory=list)  # IATA 2글자 (로고 표시용)
    price: float
    currency: str = "KRW"
    departure: str = ""
    arrival: str = ""
    stops: int = 0
    layovers: Optional[str] = None
    is_best: bool = False


class DealDecision(BaseModel):
    """규칙 엔진의 핫딜 판정 결과."""

    should_notify: bool = False
    reasons: List[str] = Field(default_factory=list)
    detail: str = ""
