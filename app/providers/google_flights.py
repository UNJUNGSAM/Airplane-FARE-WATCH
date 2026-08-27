"""Google Flights 제공자 (fast-flights 3.x 기반).

API 키 없이 Google Flights의 내부 조회 엔드포인트를 사용한다.
일시적 차단·네트워크 오류에 대비해 지수 백오프 재시도를 수행한다.

참고: fast-flights 3.1.0의 공식 파서(parse_js)는 가격 정보가 없는 일부
항공편 엔트리에서 IndexError로 전체 조회가 실패한다. 이를 우회하기 위해
라이브러리로 HTML만 가져오고(_tolerant_parse), 파싱은 이 모듈에서
관용적으로 수행한다 - 구조가 다른 엔트리는 건너뛴다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from app.models import FlightOffer, WatchCondition
from app.providers.base import FlightProvider

logger = logging.getLogger(__name__)


class FastFlightsError(RuntimeError):
    """모든 재시도 후에도 조회 실패."""


def parse_price(raw: Any) -> Optional[float]:
    """가격 값(숫자 또는 '₩123,400' 형태 문자열)을 float로 변환."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[^\d.]", "", str(raw).replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_time_pair(value: Any) -> tuple[int, int]:
    """Google이 생략한 시간 성분을 0으로 채운다. [8]→(8,0), [None,31]→(0,31)."""
    padded = [*(value or []), None, None]
    return (padded[0] or 0, padded[1] or 0)


def _fmt_datetime(date_tuple: Any, time_pair: Any) -> str:
    try:
        y, mo, d = date_tuple
        h, mi = _parse_time_pair(time_pair)
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    except Exception:  # noqa: BLE001 - 표시용이라 실패 시 빈 문자열
        return ""


class GoogleFlightsProvider(FlightProvider):
    name = "google-flights"
    MAX_RETRIES = 3

    def search(self, watch: WatchCondition) -> list[FlightOffer]:
        last_exc: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                offers = self._search_once(watch)
                if offers:
                    return offers
                logger.info("[%s] 조회 결과 없음 (시도 %d/%d)", watch.id, attempt, self.MAX_RETRIES)
                last_exc = FastFlightsError("조회된 항공편이 없습니다.")
            except Exception as exc:  # noqa: BLE001 - 재시도 후 상위로 전달
                last_exc = exc
                logger.warning(
                    "[%s] Google Flights 조회 실패 (시도 %d/%d): %s",
                    watch.id, attempt, self.MAX_RETRIES, exc,
                )
            if attempt < self.MAX_RETRIES:
                # 대시보드의 "전체 다시 조회"는 조건 수만큼 이 루프를 동기로 돈다.
                # 대기가 길수록 화면이 그대로 멈추므로 1초 → 2초로 낮춘다.
                time.sleep(2 ** (attempt - 1))
        raise last_exc or FastFlightsError("알 수 없는 조회 오류")

    def _search_once(self, watch: WatchCondition) -> list[FlightOffer]:
        html = self._fetch_html(watch)
        js = self._extract_data_js(html)
        offers = self._tolerant_parse(js, currency=(watch.currency or "KRW").upper())
        offers.sort(key=lambda o: o.price)
        return offers

    # ------------------------------------------------------------------
    def _fetch_html(self, watch: WatchCondition) -> str:
        from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html

        origin = watch.origin.upper()
        destination = watch.destination.upper()

        # 시간대·경유 필터 (Google Flights 네이티브 지원)
        # 가는 편과 오는 편에 서로 다른 시간대 필터를 적용한다.
        out_kwargs: dict[str, Any] = {}
        if watch.dep_hour_from is not None:
            out_kwargs["earliest_departure_hour"] = watch.dep_hour_from
        if watch.dep_hour_to is not None:
            out_kwargs["latest_departure_hour"] = watch.dep_hour_to
        if watch.max_stops is not None:
            out_kwargs["max_stops"] = watch.max_stops

        ret_kwargs: dict[str, Any] = {}
        if watch.max_stops is not None:
            ret_kwargs["max_stops"] = watch.max_stops
        if watch.ret_hour_from is not None:
            ret_kwargs["earliest_departure_hour"] = watch.ret_hour_from
        if watch.ret_hour_to is not None:
            ret_kwargs["latest_departure_hour"] = watch.ret_hour_to

        queries = [
            FlightQuery(
                date=watch.depart_date, from_airport=origin,
                to_airport=destination, **out_kwargs,
            )
        ]
        if watch.trip_type == "round":
            if not watch.return_date:
                raise ValueError("왕복 감시 조건에는 return_date가 필요합니다.")
            queries.append(
                FlightQuery(
                    date=watch.return_date, from_airport=destination,
                    to_airport=origin, **ret_kwargs,
                )
            )

        query = create_query(
            flights=queries,
            seat="economy",
            trip="round-trip" if watch.trip_type == "round" else "one-way",
            passengers=Passengers(adults=max(1, watch.adults)),
            currency=(watch.currency or "KRW").upper(),
            language="ko",
        )
        return fetch_flights_html(query)

    @staticmethod
    def _extract_data_js(html: str) -> str:
        from selectolax.lexbor import LexborHTMLParser

        script = LexborHTMLParser(html).css_first(r"script.ds\:1")
        if script is None:
            raise FastFlightsError("응답에서 데이터 스크립트를 찾을 수 없습니다 (차단 의심)")
        return script.text()

    @staticmethod
    def _tolerant_parse(js: str, currency: str) -> list[FlightOffer]:
        """라이브러리 parse_js의 관용적 재구현.

        Google 페이로드 구조: payload[3][0] = 항공편 엔트리 목록
          각 엔트리 k 에 대해:
            k[0][0]=타입, k[0][1]=항공사명 목록, k[0][2]=구간 목록,
            k[1][0]=[?, 가격]
        구조가 다른(가격 없는 등) 엔트리는 건너뛴다.
        """
        if "data:" not in js:
            raise FastFlightsError("응답에 data 필드가 없습니다")
        data = js.split("data:", 1)[1].rsplit(",", 1)[0]
        if data.endswith("errorHasStatus: true"):
            raise FastFlightsError("Google이 오류 응답을 반환했습니다")

        payload = json.loads(data)
        if len(payload) < 4 or not payload[3] or not payload[3][0]:
            return []

        # 항공사 코드 매핑 (payload[7][1][1] = [[코드, 이름], ...]) - 로고 표시용
        name_to_code: dict[str, str] = {}
        try:
            for code, name in (payload[7][1][1] or []):
                name_to_code[str(name)] = str(code)
        except (IndexError, TypeError, KeyError):
            pass

        offers: list[FlightOffer] = []
        skipped = 0

        for entry in payload[3][0]:
            try:
                flight = entry[0]
                price_raw = entry[1][0][1]
                price = parse_price(price_raw)
                if price is None or price <= 0:
                    skipped += 1
                    continue

                airlines = [str(a) for a in (flight[1] or [])]
                leg_list = flight[2] or []

                departure = arrival = ""
                mid_codes: list[str] = []
                if leg_list:
                    first_leg, last_leg = leg_list[0], leg_list[-1]
                    departure = _fmt_datetime(first_leg[20], first_leg[8])
                    arrival = _fmt_datetime(last_leg[21], last_leg[10])
                    for leg in leg_list[:-1]:
                        code = str(leg[6] or "")
                        if code and code not in mid_codes:
                            mid_codes.append(code)

                codes = [name_to_code[n] for n in airlines if n in name_to_code]

                offers.append(
                    FlightOffer(
                        airline=", ".join(dict.fromkeys(airlines)),
                        airline_codes=list(dict.fromkeys(codes)),
                        price=float(price),
                        currency=currency,
                        departure=departure,
                        arrival=arrival,
                        stops=max(0, len(leg_list) - 1),
                        layovers=", ".join(mid_codes) or None,
                        is_best=False,
                    )
                )
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                skipped += 1
                logger.debug("파싱 불가 엔트리 건너뜀(%s): %s", type(exc).__name__, exc)

        if skipped:
            logger.info("구조가 다른 %d개 엔트리를 건너뛰고 %d개 오퍼를 파싱했습니다",
                        skipped, len(offers))
        return offers
