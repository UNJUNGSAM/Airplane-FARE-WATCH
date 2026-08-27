"""감시 사이클 공용 실행 로직.

monitor.py(GitHub Actions 크론)와 Streamlit 대시보드의
"지금 확인" 버튼이 동일한 함수를 사용해 결과 일관성을 유지한다.
"""
from __future__ import annotations

import logging
from typing import Any

from app.database import Database, now_str
from app.models import WatchCondition
from app.providers.base import FlightProvider
from app.services import notifier
from app.services.gemini_service import GeminiService
from app.services.rule_engine import evaluate_deal

logger = logging.getLogger(__name__)


def check_watch(
    db: Database,
    provider: FlightProvider,
    gemini: GeminiService,
    watch: WatchCondition,
) -> dict[str, Any]:
    """감시 조건 1건에 대한 전체 사이클: 조회 → 기록 → 판정 → 알림.

    Returns:
        {"ok": bool, "watch_id": int, "price": float|None,
         "notified": bool, "reasons": [...], "error": str|None}
    """
    result: dict[str, Any] = {
        "ok": False, "watch_id": watch.id, "price": None,
        "notified": False, "reasons": [], "error": None,
    }

    # 1) 가격 조회
    try:
        offers = provider.search(watch)
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] 가격 조회 실패: %s", watch.id, exc)
        result["error"] = f"가격 조회 실패: {exc}"
        return result

    if not offers:
        result["error"] = "조회된 항공편이 없습니다."
        return result

    best = offers[0]
    now = now_str()

    # 2) 통계는 현재 가격 기록 '전'에 계산 (백분위 자기 참조 방지)
    stats = db.price_stats(watch.id, days=30, percentile=watch.percentile)

    # 3) 최저가 기록 + 상위 오퍼 스냅샷 저장 + 첫 관측가 저장
    db.add_price_record(watch.id, best, checked_at=now, provider_name=provider.name)
    db.add_offer_snapshot(watch.id, offers, checked_at=now, top_n=5)
    if watch.first_seen_price is None:
        db.update_watch_fields(watch.id, first_seen_price=best.price)
        watch.first_seen_price = best.price

    # 4) 핫딜 판정
    decision = evaluate_deal(watch, best.price, stats)

    # 5) 알림 발송
    if decision.should_notify:
        analysis = gemini.analyze_deal(watch, best.price, stats)
        message = notifier.format_hot_deal(watch, best, decision, analysis)
        if notifier.send_message(message):
            db.update_watch_fields(watch.id, last_notified_at=now)
            db.log_notification(watch.id, best.price, " | ".join(decision.reasons), message)
            result["notified"] = True
        else:
            result["error"] = "텔레그램 전송 실패"

    db.update_watch_fields(watch.id, last_checked_at=now)
    result.update(ok=True, price=best.price, reasons=decision.reasons)
    logger.info("[%s] 확인 완료 - 최저가 %.0f%s%s",
                watch.id, best.price, watch.currency,
                " (핫딜 알림!)" if result["notified"] else "")
    return result


def run_full_cycle(db: Database, provider: FlightProvider, gemini: GeminiService) -> dict[str, int]:
    """모든 활성 감시 조건을 순회 확인하고 요약 통계를 반환한다."""
    watches = db.list_watches(active_only=True)
    logger.info("감시 대상 %d개 조건 확인 시작", len(watches))

    ok_count = notified_count = 0
    for watch in watches:
        res = check_watch(db, provider, gemini, watch)
        if res["ok"]:
            ok_count += 1
        if res["notified"]:
            notified_count += 1

    db.prune_history()
    db.prune_snapshots()
    summary = {"total": len(watches), "ok": ok_count, "notified": notified_count}
    logger.info("사이클 완료 - 전체 %(total)d / 성공 %(ok)d / 알림 %(notified)d건", summary)
    return summary
