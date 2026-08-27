"""텔레그램 봇 알림 서비스.

Bot API HTTP 엔드포인트를 직접 호출한다 (python-telegram-bot 불필요).
"""
from __future__ import annotations

import html
import logging
from typing import Optional

import requests

from app import config
from app.models import DealDecision, FlightOffer, WatchCondition

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def send_message(text: str) -> bool:
    """메시지 전송. 미설정/실패 시 False 반환 (감시 사이클은 계속 진행)."""
    if not config.telegram_ready():
        logger.warning("TELEGRAM_BOT_TOKEN/CHAT_ID 미설정 - 알림을 건너뜁니다.")
        return False
    url = f"{API_BASE}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("텔레그램 전송 실패: %s", exc)
        return False


def send_test_message() -> tuple[bool, str]:
    """연동 상태 점검을 위한 테스트 메시지 전송."""
    if not config.telegram_ready():
        return False, "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다."
    msg = (
        "🔔 <b>[FARE WATCH] 텔레그램 연동 테스트</b>\n\n"
        "정상적으로 연동되었습니다! 핫딜이 감지되면 이 채팅으로 즉시 알림이 발송됩니다."
    )
    ok = send_message(msg)
    if ok:
        return True, "테스트 메시지를 성공적으로 발송하였습니다. 텔레그램을 확인해 주세요."
    return False, "메시지 발송에 실패하였습니다. 봇 토큰과 Chat ID를 확인해 주세요."


def format_hot_deal(
    watch: WatchCondition,
    offer: FlightOffer,
    decision: DealDecision,
    analysis: Optional[str] = None,
) -> str:
    """핫딜 알림 메시지(HTML)를 구성한다."""
    esc = html.escape
    lines = ["🔥 <b>항공권 핫딜 알림!</b>", ""]

    title = esc(watch.label) if watch.label else esc(watch.route_label)
    lines.append(f"✈️ <b>{title}</b>")
    lines.append(
        f"📍 {esc(watch.origin)} → {esc(watch.destination)}"
        + (f" ({esc(watch.depart_date)})" if watch.depart_date else "")
    )
    if watch.trip_type == "round" and watch.return_date:
        lines.append(f"🔁 복귀: {esc(watch.return_date)}")
    lines.append("")
    lines.append(f"💰 최저가: <b>{offer.price:,.0f} {offer.currency}</b>")
    if offer.airline:
        lines.append(f"🏷 항공사: {esc(offer.airline)}")
    if offer.departure:
        lines.append(f"🛫 출발: {esc(offer.departure)}")
    if offer.arrival:
        lines.append(f"🛬 도착: {esc(offer.arrival)}")
    if offer.stops:
        layover = f" ({esc(offer.layovers)})" if offer.layovers else ""
        lines.append(f"⏸ 경유: {offer.stops}회{layover}")
    else:
        lines.append("⏸ 직항")

    lines.append("")
    lines.append("<b>알림 사유</b>")
    for r in decision.reasons:
        lines.append(f"• {esc(r)}")

    if analysis:
        lines.append("")
        lines.append(f"🤖 Gemini 분석: {esc(analysis)}")

    lines.append("")
    lines.append(_flights_link(watch))
    return "\n".join(lines)


def _flights_link(watch: WatchCondition) -> str:
    from urllib.parse import quote

    q = f"Flights from {watch.origin} to {watch.destination} on {watch.depart_date}"
    if watch.trip_type == "round" and watch.return_date:
        q += f" return {watch.return_date}"
    return f'🔗 <a href="https://www.google.com/travel/flights?q={quote(q)}">Google Flights에서 보기</a>'
