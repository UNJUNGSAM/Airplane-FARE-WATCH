"""핫딜 판정 규칙 엔진.

세 가지 트리거를 평가하고 쿨다운으로 알림 스팸을 방지한다.
1) 목표가 도달  2) 첫 관측가 대비 하락률  3) 최근 30일 하위 백분위
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.database import KST, parse_dt
from app.models import DealDecision, WatchCondition


def evaluate_deal(
    watch: WatchCondition,
    current_price: float,
    stats: dict[str, Any],
    now: Optional[datetime] = None,
) -> DealDecision:
    """현재가와 이력 통계로 핫딜 여부를 판정한다."""
    cur = watch.currency or "KRW"
    fmt = lambda v: f"{v:,.0f}" if v is not None else "-"  # noqa: E731
    reasons: list[str] = []

    # 규칙 1) 목표가 도달
    if watch.target_price is not None and current_price <= watch.target_price:
        reasons.append(
            f"목표가 {fmt(watch.target_price)}{cur} 이하 도달 (현재 {fmt(current_price)}{cur})"
        )

    # 규칙 2) 첫 관측가 대비 하락률
    if (
        watch.first_seen_price
        and watch.drop_percent
        and watch.drop_percent > 0
        and current_price <= watch.first_seen_price * (1 - watch.drop_percent / 100.0)
    ):
        drop_pct = (1 - current_price / watch.first_seen_price) * 100
        reasons.append(
            f"첫 관측가 {fmt(watch.first_seen_price)}{cur} 대비 "
            f"{drop_pct:.1f}% 하락 (기준 {watch.drop_percent:.0f}%)"
        )

    # 규칙 3) 최근 30일 하위 백분위 (통계 10회 이상 쌓였을 때만)
    pct_value = stats.get("pct_value")
    count = int(stats.get("count") or 0)
    if pct_value is not None and count >= 10 and current_price <= pct_value:
        reasons.append(
            f"최근 30일 {count}회 관측 중 하위 {watch.percentile:.0f}% 백분위 진입"
        )

    if not reasons:
        return DealDecision(should_notify=False)

    # 쿨다운 검사 - 마지막 알림 이후 cooldown_hours 미경과 시 억제
    last_notified = parse_dt(watch.last_notified_at)
    if last_notified is not None:
        now_naive = (now or datetime.now(KST)).replace(tzinfo=None)
        elapsed_h = (now_naive - last_notified).total_seconds() / 3600.0
        if elapsed_h < watch.cooldown_hours:
            remaining = watch.cooldown_hours - elapsed_h
            return DealDecision(
                should_notify=False,
                reasons=reasons,
                detail=f"쿨다운 중 - {remaining:.1f}시간 후 재알림 가능",
            )

    # 재알림 억제 - 직전에 알린 가격보다 낮아졌을 때만 다시 알린다.
    # 가격이 저점에 며칠 머무르면 쿨다운이 지날 때마다 같은 알림이 반복되어
    # (6시간 기준 하루 4통) 알림 자체를 무시하게 되는 피로를 막는다.
    if (watch.last_notified_price is not None
            and current_price >= watch.last_notified_price):
        return DealDecision(
            should_notify=False,
            reasons=reasons,
            detail=(f"직전 알림가 {fmt(watch.last_notified_price)}{cur} 이하로 "
                    f"더 내려가면 다시 알립니다"),
        )

    return DealDecision(should_notify=True, reasons=reasons)
