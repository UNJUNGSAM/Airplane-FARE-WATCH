"""딜 상태 판정 - 가격 이력 대비 현재가의 상대적 위치를 계산한다.

"지금 이 가격, 저번보다 싸진 건가?" 질문에 한눈에 답하기 위한 모듈.
"""
from __future__ import annotations

from typing import Any, Optional

# (제거) BADGE_CLASS: 표현 계층은 shared.LEVEL_STYLE 을 쓰므로 아무도 참조하지 않던
# 데드 코드였다. 도메인 모듈이 CSS 클래스를 아는 것 자체가 계층 위반이기도 하다.


def deal_status(
    stats: dict[str, Any], history: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """가격 통계(및 이력)로 현재가의 상대적 품질을 판정한다.

    Returns:
        level: best | good | normal | high | unknown
        emoji/label: 표시용
        discount_first: 첫 관측가 대비 할인율 (%)
        discount_avg: 30일 평균 대비 할인율 (%)
        trend_pct: 직전 확인 대비 변화율 (%)
    """
    count = int(stats.get("count") or 0)
    cur = stats.get("last")

    if count == 0 or cur is None:
        return {"level": "unknown", "emoji": "❓", "label": "데이터 수집 중",
                "discount_first": None, "discount_avg": None, "trend_pct": None}

    cur = float(cur)
    first = stats.get("first")
    avg = stats.get("avg")
    mn = stats.get("min")

    discount_first = round((first - cur) / first * 100, 1) if first else None
    discount_avg = round((avg - cur) / avg * 100, 1) if avg else None

    trend_pct: Optional[float] = None
    if history and len(history) >= 2:
        prev = float(history[-2]["price"])
        if prev > 0:
            trend_pct = round((cur - prev) / prev * 100, 1)

    if count >= 2 and mn is not None and cur <= mn + 1e-9:
        level, emoji, label = "best", "🔥", "역대 최저가!"
    elif avg and cur <= avg * 0.95:
        level, emoji, label = "good", "😊", "평균보다 저렴"
    elif avg and cur <= avg * 1.05:
        level, emoji, label = "normal", "😐", "평균 수준"
    else:
        level, emoji, label = "high", "🙁", "비싼 편"

    return {
        "level": level,
        "emoji": emoji,
        "label": label,
        "discount_first": discount_first,
        "discount_avg": discount_avg,
        "trend_pct": trend_pct,
    }
