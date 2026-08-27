"""항공권 가격 제공자 추상 인터페이스.

향후 다른 데이터 소스(SerpAPI, Skyscanner 등) 추가 시
이 인터페이스를 구현한 클래스만 만들면 됩니다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import FlightOffer, WatchCondition


class FlightProvider(ABC):
    """감시 조건을 받아 항공편 오퍼 목록(가격 오름차순)을 반환한다."""

    name: str = "base"

    @abstractmethod
    def search(self, watch: WatchCondition) -> list[FlightOffer]:
        raise NotImplementedError
