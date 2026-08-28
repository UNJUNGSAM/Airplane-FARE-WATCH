"""헤드리스 감시 실행기.

GitHub Actions 크론 또는 로컬 CLI에서 직접 실행한다.
    python monitor.py

모든 활성 감시 조건에 대해 가격 조회 → 기록 → 핫딜 판정 → 텔레그램 알림을 수행하고,
오래된 가격 이력을 정리한다.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 프로젝트 루트를 임포트 경로에 추가 (어느 위치에서 실행해도 동작)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.database import Database  # noqa: E402
from app.providers.google_flights import GoogleFlightsProvider  # noqa: E402
from app.services.checker import run_full_cycle  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("monitor")

    db = Database(config.DB_PATH)
    db.init_schema()

    watches = db.list_watches(active_only=True)
    if not watches:
        logger.info("활성 감시 조건이 없습니다. Streamlit 대시보드에서 조건을 등록하세요.")
        return 0
    if len(watches) > 20:
        # 20건 × 48회/일 ≈ 1,000회 조회. 구글이 요청을 차단하기 시작할 수 있는 규모다.
        logger.warning(
            "활성 조건이 %d건입니다. 하루 %d회 조회는 차단 위험이 있으니 "
            ".github/workflows/monitor.yml 의 cron 을 '0 * * * *'(1시간)로 늘리는 것을 권장합니다.",
            len(watches), len(watches) * 48,
        )

    provider = GoogleFlightsProvider()
    gemini = GeminiService()
    logger.info("Gemini 분석: %s | Telegram 알림: %s",
                "활성" if gemini.available else "비활성(키 없음)",
                "활성" if config.telegram_ready() else "비활성(키 없음)")

    summary = run_full_cycle(db, provider, gemini)
    failed = summary["total"] - summary["ok"]
    return 1 if failed == summary["total"] and summary["total"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
