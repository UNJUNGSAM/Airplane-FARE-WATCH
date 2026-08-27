"""Gemini 서비스.

1. 자연어 감시 조건 파싱: "다낭, 나트랑, 푸꾸옥 티켓 중 가격이 다운되면 알려줘"
   → 구조화된 감시 조건 초안 **배열** (목적지·날짜·시간대 대안마다 객체 1개)
2. 핫딜 알림 시 가격 추세 분석 문장 생성

호출 안정성: 503(혼잡)·429(할당량) 같은 일시 오류는 지수 백오프로 재시도하고,
설정된 모델이 계속 실패하면 대체 모델을 순차 시도한다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from typing import Any, Optional

from app import config
from app.models import WatchCondition

logger = logging.getLogger(__name__)

# 설정 모델 실패 시 순차 시도할 대체 모델
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
]

_MAX_ATTEMPTS_PER_MODEL = 3


def _is_retryable(exc: Exception) -> bool:
    """503 혼잡 / 429 할당량 / 타임아웃 등 재시도 가능 오류 판별."""
    s = str(exc).upper()
    return any(k in s for k in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                                "OVERLOADED", "HIGH DEMAND", "DEADLINE", "TIMEOUT"))


def _is_auth_error(exc: Exception) -> bool:
    """API 키 오류 등 재시도해도 무의미한 오류 판별."""
    s = str(exc).upper()
    return any(k in s for k in ("401", "403", "API_KEY", "API KEY NOT", "PERMISSION"))

_PARSE_PROMPT_TEMPLATE = """오늘 날짜는 {today}입니다.
아래 한국어 요청을 항공권 가격 감시 조건(JSON 배열)으로 변환하세요.

요청: "{text}"

변환 규칙:
- 출력은 항상 JSON 배열이며, 각 원소는 감시 조건 객체 하나입니다.
- 목적지가 여러 개 언급되면("다낭, 나트랑, 푸꾸옥" 등) 각 목적지마다 객체를 하나씩 만듭니다.
- 출발 날짜나 시간대 대안이 여러 개면("23일 저녁 또는 24일 오전" 등) 그 조합마다 객체를 따로 만듭니다.
- 단, 전체 객체 수는 최대 8개로 제한합니다.
- 도시명은 가장 대표적인 공항의 IATA 코드로 변환합니다.
  (예: 서울→ICN, 김포→GMP, 도쿄→NRT, 오사카→KIX, 후쿠오카→FUK, 방콕→BKK,
   타이페이→TPE, 다낭→DAD, 나트랑→CXR, 푸꾸옥→PQC, 세부→CEB, 제주→CJU, 파리→CDG)
- 상대적 날짜("다음 달", "9월 말", "크리스마스" 등)는 오늘 날짜 기준 YYYY-MM-DD 절대 날짜로 계산합니다.
- 왕복 요청("귀국", "돌아오는", "왕복" 등)이면 반드시 trip_type="round"이고
  return_date를 채웁니다. 편도는 "one-way"입니다.
  ("3박 4일"처럼 숙박 일수만 있으면 depart_date + 숙박일수 = return_date)
- 가는 날 옵션과 오는 날 옵션이 여러 개면 순서대로 자연스럽게 페어링합니다.
  (예: 가는 날 "9/23 저녁 or 9/24 새벽" + 오는 날 "9/27 오후 or 9/28 새벽 2시 이전" →
   [9/23 출발 ~ 9/27 귀국], [9/24 출발 ~ 9/28 귀국] 두 조합을 만듭니다)
- 가는 편 출발 시간대는 dep_hour_from(이 시간 이후)/dep_hour_to(이 시간까지)에 넣습니다.
  dep_hour_to는 해당 시간에 출발하는 항공편까지 포함하는 의미입니다. (23시까지 = 23:00~23:59 포함)
  (예: "오후 8시 이후"→20과 23 / "새벽이나 오전"→0과 12 / "오전"→6과 12 / 언급 없으면 둘 다 null)
- 귀국편 출발 시간대는 ret_hour_from/ret_hour_to에 넣습니다.
  (예: "오후에 귀국"→12과 23 / "새벽 2시 이전 귀국"→0과 2 / 언급 없으면 둘 다 null)
- 경유 조건은 max_stops에 넣습니다. ("직항만"→0 / "경유 1회 이하"→1 / 언급 없으면 null)
- 금액 언급 시 통화를 판단해 currency에 반영하고 target_price는 숫자로 환산합니다. (40만원→400000, KRW)
- 인원 언급이 없으면 adults는 1입니다. 정보가 없는 필드는 null로 남깁니다.
- label은 "[도시명] M/D" 형태의 짧은 한국어로 작성합니다.
  시간대·경유 조건은 label에 넣지 마세요 (별도 필드로 표시됩니다).

출력 예시 (설명·마크다운 없이 JSON만):
[
  {{"origin": "ICN", "destination": "DAD", "depart_date": "2026-09-23", "return_date": "2026-09-27",
    "trip_type": "round", "adults": 1, "target_price": null, "currency": "KRW",
    "dep_hour_from": 20, "dep_hour_to": 23, "ret_hour_from": 12, "ret_hour_to": 23,
    "max_stops": 0, "label": "다낭 9/23 ~ 9/27"}},
  {{"origin": "ICN", "destination": "CXR", "depart_date": "2026-09-24", "return_date": "2026-09-28",
    "trip_type": "round", "adults": 1, "target_price": null, "currency": "KRW",
    "dep_hour_from": 0, "dep_hour_to": 12, "ret_hour_from": 0, "ret_hour_to": 2,
    "max_stops": 0, "label": "나트랑 9/24 ~ 9/28"}}
]"""

_ANALYZE_PROMPT_TEMPLATE = """당신은 항공권 가격 분석가입니다. 아래 데이터를 보고
현재 가격이 좋은 딜인지 한국어로 최대 2문장으로 평가하세요. 숫자 근거를 반드시 포함하세요.

노선: {origin} → {destination} ({depart_date}{return_part})
현재 최저가: {current:,.0f} {currency}
최근 30일 데이터: 관측 {count}회 / 최저 {min_price} / 평균 {avg_price} / 첫 관측가 {first_price}

평가 예시: "최근 30일 평균 512,000원보다 18% 낮고 첫 관측가와 비교해서도 하락 중이라 지금이 좋은 타이밍으로 보입니다."
"""


def _norm_iata(v: Any) -> Optional[str]:
    if v in (None, "", "null"):
        return None
    s = str(v).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", s):
        raise ValueError(f"IATA 공항 코드 형식이 아닙니다: {v!r}")
    return s


def _norm_date(v: Any) -> Optional[str]:
    if v in (None, "", "null"):
        return None
    s = str(v).strip()[:10]
    datetime.strptime(s, "%Y-%m-%d")  # 유효성 검증
    return s


def _norm_hour(v: Any) -> Optional[int]:
    if v in (None, "", "null"):
        return None
    try:
        h = int(v)
    except (TypeError, ValueError):
        return None
    return h if 0 <= h <= 23 else None


def _norm_stops(v: Any) -> Optional[int]:
    if v in (None, "", "null"):
        return None
    try:
        s = int(v)
    except (TypeError, ValueError):
        return None
    return s if 0 <= s <= 2 else None


def normalize_draft(item: Any) -> dict[str, Any]:
    """Gemini 응답 객체 1개를 검증·정규화하여 감시 조건 초안 dict로 만든다."""
    if not isinstance(item, dict):
        raise ValueError("조건 객체가 아닙니다")

    origin = _norm_iata(item.get("origin"))
    destination = _norm_iata(item.get("destination"))
    depart = _norm_date(item.get("depart_date"))
    if not origin or not destination or not depart:
        missing = [n for n, v in
                   (("출발지", origin), ("도착지", destination), ("가는 날", depart)) if not v]
        raise ValueError(f"필수 정보 누락: {', '.join(missing)}")

    trip_type = str(item.get("trip_type") or "one-way").strip()
    if trip_type not in ("one-way", "round"):
        trip_type = "round" if item.get("return_date") else "one-way"

    ret = _norm_date(item.get("return_date"))
    if trip_type == "round" and not ret:
        trip_type = "one-way"

    try:
        adults = max(1, int(item.get("adults") or 1))
    except (TypeError, ValueError):
        adults = 1

    target = item.get("target_price")
    try:
        target = float(target) if target not in (None, "", "null") else None
    except (TypeError, ValueError):
        target = None

    currency = str(item.get("currency") or config.DEFAULT_CURRENCY).strip().upper()

    label = str(item.get("label") or "").strip()
    if not label:
        label = f"{destination} {depart}"

    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart,
        "return_date": ret,
        "trip_type": trip_type,
        "adults": adults,
        "target_price": target,
        "currency": currency,
        "dep_hour_from": _norm_hour(item.get("dep_hour_from")),
        "dep_hour_to": _norm_hour(item.get("dep_hour_to")),
        "ret_hour_from": _norm_hour(item.get("ret_hour_from")),
        "ret_hour_to": _norm_hour(item.get("ret_hour_to")),
        "max_stops": _norm_stops(item.get("max_stops")),
        "label": label,
    }


class GeminiService:
    """google-genai SDK 래퍼. 키가 없으면 기능이 비활성화된다."""

    def __init__(self) -> None:
        self._client = None

    @property
    def available(self) -> bool:
        return config.gemini_ready()

    @property
    def client(self):
        if self._client is None:
            if not self.available:
                raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
            from google import genai

            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    # ------------------------------------------------------------------
    def _generate(self, prompt: str, json_mode: bool = False) -> str:
        """재시도 + 대체 모델 폴백이 적용된 generate_content 래퍼.

        - 재시도 가능 오류(503 혼잡, 429 할당량 등): 모델당 최대 3회 백오프 재시도
        - 그래도 실패하면 FALLBACK_MODELS를 순차 시도
        - API 키 오류는 즉시 상위로 전달
        """
        models = [config.GEMINI_MODEL] + [m for m in FALLBACK_MODELS if m != config.GEMINI_MODEL]
        last_exc: Exception | None = None

        for model in models:
            for attempt in range(1, _MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    kwargs: dict[str, Any] = {}
                    if json_mode:
                        kwargs["config"] = {"response_mime_type": "application/json"}
                    resp = self.client.models.generate_content(
                        model=model, contents=prompt, **kwargs
                    )
                    text = (resp.text or "").strip()
                    if text:
                        if model != config.GEMINI_MODEL:
                            logger.info("대체 모델 %s 로 호출 성공", model)
                        return text
                    last_exc = ValueError("Gemini 응답이 비어 있습니다.")
                    break  # 빈 응답은 재시도보다 다음 모델 시도가 효과적
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if _is_auth_error(exc):
                        raise RuntimeError(f"Gemini API 키 오류: {exc}") from exc
                    if _is_retryable(exc) and attempt < _MAX_ATTEMPTS_PER_MODEL:
                        wait = min(2 ** attempt, 6)
                        logger.warning("Gemini %s 일시 오류(시도 %d/%d, %ds 후 재시도): %s",
                                       model, attempt, _MAX_ATTEMPTS_PER_MODEL, wait, exc)
                        time.sleep(wait)
                        continue
                    logger.warning("Gemini %s 호출 실패, 다음 모델로 전환: %s", model, exc)
                    break  # 다음 모델로

        raise last_exc or RuntimeError("Gemini 호출에 실패했습니다.")

    # ------------------------------------------------------------------
    def parse_watch_query(self, text: str) -> list[dict[str, Any]]:
        """자연어 → 감시 조건 초안 배열 (목적지/날짜/시간대 대안별 1개씩)."""
        prompt = _PARSE_PROMPT_TEMPLATE.format(today=date.today().isoformat(), text=text.strip())
        raw = self._generate(prompt, json_mode=True)
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)

        # 단일 객체로 응답해도 배열로 통일 (구버전 호환)
        items = data if isinstance(data, list) else [data]

        drafts: list[dict[str, Any]] = []
        errors: list[str] = []
        for item in items:
            try:
                drafts.append(normalize_draft(item))
            except ValueError as exc:
                errors.append(str(exc))

        if not drafts:
            raise ValueError("; ".join(errors) or "감시 조건을 파싱하지 못했습니다.")
        return drafts[:8]

    # ------------------------------------------------------------------
    def analyze_deal(
        self, watch: WatchCondition, current_price: float, stats: dict[str, Any]
    ) -> str:
        """가격 이력 요약 기반 딜 품질 평가 문장. 실패 시 빈 문자열."""
        if not self.available or stats.get("count", 0) < 2:
            return ""
        try:
            fmt = lambda v: f"{v:,.0f}" if v is not None else "-"  # noqa: E731
            prompt = _ANALYZE_PROMPT_TEMPLATE.format(
                origin=watch.origin,
                destination=watch.destination,
                depart_date=watch.depart_date,
                return_part=f" ~ {watch.return_date}" if watch.return_date else "",
                current=current_price,
                currency=watch.currency,
                count=stats["count"],
                min_price=fmt(stats.get("min")),
                avg_price=fmt(stats.get("avg")),
                first_price=fmt(stats.get("first")),
            )
            return self._generate(prompt)
        except Exception as exc:  # noqa: BLE001 - 분석 실패는 알림 발송을 막지 않는다
            logger.warning("Gemini 딜 분석 실패: %s", exc)
            return ""
