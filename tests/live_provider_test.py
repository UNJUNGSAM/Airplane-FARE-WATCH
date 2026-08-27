"""실제 Google Flights 조회 라이브 테스트 (네트워크 필요).

실행: python tests/live_provider_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import WatchCondition  # noqa: E402
from app.providers.google_flights import GoogleFlightsProvider  # noqa: E402


def main() -> int:
    w = WatchCondition(
        origin="ICN", destination="NRT", trip_type="one-way",
        depart_date="2026-10-15", adults=1, currency="KRW",
    )
    offers = GoogleFlightsProvider().search(w)
    print(f"조회된 오퍼: {len(offers)}건")
    for o in offers[:3]:
        print(f"  {o.price:>10,.0f} {o.currency} | {o.airline} ({','.join(o.airline_codes)}) | "
              f"{o.departure}~{o.arrival} | 경유 {o.stops}")
    assert offers and offers[0].price > 0, "오퍼가 없거나 가격이 비정상입니다."
    assert offers[0].airline_codes, "항공사 코드가 파싱되지 않았습니다."

    # 출발 시간대 필터 파라미터 동작 확인 (0~23시 = 전체 시간)
    w2 = WatchCondition(
        origin="ICN", destination="NRT", trip_type="one-way",
        depart_date="2026-10-15", adults=1, currency="KRW",
        dep_hour_from=0, dep_hour_to=23,
    )
    offers2 = GoogleFlightsProvider().search(w2)
    print(f"시간대 필터 조회: {len(offers2)}건")
    assert offers2, "시간대 필터 조회 실패"
    print("LIVE_PROVIDER_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
