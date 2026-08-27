"""실제 Gemini 자연어 파싱 라이브 테스트 (GEMINI_API_KEY 필요).

실행: python tests/live_gemini_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402


def main() -> int:
    if not config.gemini_ready():
        print("GEMINI_API_KEY 미설정 - 건너뜁니다.")
        return 0

    gemini = GeminiService()
    print(f"설정 모델: {config.GEMINI_MODEL}")

    text = ("9월 23일 오후 8시 이후 or 9월 24일 새벽이나 오전 ICN 출발해서 다낭, 나트랑, "
            "푸꾸옥도착, 9월 27일 오후나 28일 새벽 2시 이전에 ICN 귀국하는 왕복 직항 티켓 "
            "중에서 가격이 다운되면 알려줘")
    drafts = gemini.parse_watch_query(text)
    print(f"파싱된 조건: {len(drafts)}개")
    for d in drafts:
        print(f"  - {d['label']}: {d['origin']}→{d['destination']} "
              f"{d['depart_date']}~{d.get('return_date')} "
              f"가는편 {d.get('dep_hour_from')}~{d.get('dep_hour_to')} "
              f"귀국 {d.get('ret_hour_from')}~{d.get('ret_hour_to')} "
              f"경유 {d.get('max_stops')}")
    assert drafts, "파싱 결과가 비었습니다."
    assert all(d["destination"] in ("DAD", "CXR", "PQC") for d in drafts), \
        "다낭/나트랑/푸꾸옥 외의 목적지가 포함되었습니다."
    assert all(d["trip_type"] == "round" for d in drafts), \
        "왕복 요청이 편도로 파싱되었습니다."
    assert all(d.get("return_date") for d in drafts), \
        "귀국 날짜가 파싱되지 않았습니다."
    print("LIVE_GEMINI_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
